"""HTTP API for the web app (``ft-agent serve``).

    POST /chat           {thread_id, message}    ask a question
    POST /chat/approve   {thread_id, decisions}  answer a pending approval
    GET  /chat/{thread}                          recent turns + pending approval
    GET  /healthz

Every /chat request needs ``Authorization: Bearer <Supabase access token>``.
The token is checked with Supabase Auth, and the agent then reads and writes
with that same token, so row-level security applies exactly as in the web app.
The user id never comes from the client: threads are stored under
``<verified user id>:<thread_id>``, so one user can't open another's thread.

Checkpoints go to Postgres when ``FT_AGENT_DATABASE_URL`` is set (needed on
Cloud Run, where the disk is per-instance), otherwise to a local SQLite file.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .agent import FilamentAgent, TurnResult
from .config import AgentConfig, config_dir
from .llm import LLM, make_llm
from .repository import FilamentService, FixtureBackend, SupabaseBackend

log = logging.getLogger("filament_agent.server")

DEMO_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "demo.json"
THREAD_ID = r"^[A-Za-z0-9_-]{1,64}$"
MAX_MESSAGE_CHARS = 4000


@dataclass(frozen=True)
class Caller:
    user_id: str
    email: str
    token: str


class AuthError(Exception):
    pass


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


# ------------------------------------------------------------------ auth

Verifier = Callable[[str], Awaitable[Caller]]


def supabase_verifier(url: str, key: str, allowed_emails: list[str]) -> Verifier:
    """Checks a token with Supabase Auth (GET /auth/v1/user), which also catches revoked sessions."""
    http = httpx.AsyncClient(timeout=10)

    async def verify(token: str) -> Caller:
        r = await http.get(
            f"{url.rstrip('/')}/auth/v1/user",
            headers={"apikey": key, "Authorization": f"Bearer {token}"},
        )
        if r.status_code in (401, 403):
            raise AuthError("Session expired. Sign in again.")
        r.raise_for_status()
        user = r.json()
        email = str(user.get("email") or "")
        if allowed_emails and email.lower() not in allowed_emails:
            raise AuthError("This account isn't allowed to use the agent.")
        return Caller(user_id=str(user["id"]), email=email, token=token)

    return verify


async def demo_verifier(token: str) -> Caller:
    """Demo mode without Supabase: any token works and maps to its own demo workspace."""
    return Caller(user_id="demo-" + hashlib.sha256(token.encode()).hexdigest()[:16], email="", token=token)


def _bearer(request: Request) -> str:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Missing bearer token.")
    return token.strip()


# ------------------------------------------------------------------ storage


def sqlite_checkpointer(path: Path) -> AbstractAsyncContextManager[Any]:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    return AsyncSqliteSaver.from_conn_string(str(path))


@asynccontextmanager
async def postgres_checkpointer(url: str, schema: str = "agent") -> AsyncIterator[Any]:
    """Postgres checkpoints in their own schema, so they're never exposed through PostgREST."""
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool
    except ImportError as e:  # pragma: no cover - depends on installed extras
        raise RuntimeError('FT_AGENT_DATABASE_URL needs: pip install "filament-agent[postgres]"') from e

    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
        raise RuntimeError(f"Invalid FT_AGENT_DB_SCHEMA: {schema!r}")
    async with await AsyncConnection.connect(url, autocommit=True) as conn:
        await conn.execute(f"create schema if not exists {schema}")
    kwargs = {
        "autocommit": True,
        "prepare_threshold": None,
        "row_factory": dict_row,
        "options": f"-c search_path={schema}",
    }
    async with AsyncConnectionPool(url, kwargs=kwargs, min_size=1, max_size=5, open=False) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        yield saver


def default_checkpointer(demo: bool) -> AbstractAsyncContextManager[Any]:
    url = os.environ.get("FT_AGENT_DATABASE_URL")
    if url:
        return postgres_checkpointer(url, os.environ.get("FT_AGENT_DB_SCHEMA", "agent"))
    name = "server-threads-demo.sqlite" if demo else "server-threads.sqlite"
    return sqlite_checkpointer(Path(os.environ.get("FT_AGENT_DB") or config_dir() / name))


# ------------------------------------------------------------------ requests


class ChatRequest(BaseModel):
    thread_id: str = Field(pattern=THREAD_ID)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ApproveRequest(BaseModel):
    thread_id: str = Field(pattern=THREAD_ID)
    decisions: bool | dict[str, bool]


def _turn_json(result: TurnResult) -> dict[str, Any]:
    out = asdict(result)
    out["answer"] = result.answer.model_dump(mode="json") if result.answer else None
    return out


async def _body(request: Request, model: type[BaseModel]) -> Any:
    try:
        return model.model_validate(await request.json())
    except ValidationError as e:
        err = e.errors()[0]
        field = ".".join(str(p) for p in err["loc"])
        raise HttpError(400, f"{field}: {err['msg']}" if field else err["msg"]) from e
    except ValueError as e:
        raise HttpError(400, "Invalid JSON body.") from e


class _NoModel:
    """Stand-in model for requests that only read thread state."""

    async def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Any:
        raise RuntimeError("no model on read-only requests")

    async def summarize(self, previous: str, transcript: str) -> str:
        raise RuntimeError("no model on read-only requests")


_NO_MODEL = _NoModel()


def _missing_key(e: Exception) -> bool:
    """The model SDKs raise these when no API key is configured."""
    text = str(e)
    return (isinstance(e, TypeError) and "authentication" in text) or (
        isinstance(e, ValueError) and ("API key" in text or "api_key" in text)
    )


# ------------------------------------------------------------------ app


def create_app(
    *,
    demo: bool = False,
    verify: Verifier | None = None,
    service_for: Callable[[Caller], FilamentService] | None = None,
    llm: LLM | None = None,
    config: AgentConfig | None = None,
    checkpointer: Callable[[], AbstractAsyncContextManager[Any]] | None = None,
) -> Starlette:
    """Builds the app. The keyword arguments exist so tests can swap in fakes."""
    cfg = config or AgentConfig()
    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY")
    allowed = [e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()]

    if verify is None:
        if url and key:
            verify = supabase_verifier(url, key, allowed)
        elif demo:
            log.warning("Demo mode without SUPABASE_URL: any bearer token is accepted (demo data only).")
            verify = demo_verifier
        else:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (see agent/.env.example)")

    if service_for is None:
        if demo:
            # Each caller gets their own copy of the demo data, kept for the life of the process.
            workspaces: dict[str, FilamentService] = {}

            def service_for(caller: Caller) -> FilamentService:
                if caller.user_id not in workspaces:
                    workspaces[caller.user_id] = FilamentService(FixtureBackend.from_file(DEMO_FIXTURE))
                return workspaces[caller.user_id]

        else:
            assert url and key

            def service_for(caller: Caller) -> FilamentService:
                return FilamentService(SupabaseBackend(url, key, lambda: caller.token))

    locks: dict[str, asyncio.Lock] = {}
    model: list[LLM] = [llm] if llm else []

    def get_llm() -> LLM:
        if not model:
            model.append(make_llm(cfg))
        return model[0]

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with (checkpointer or (lambda: default_checkpointer(demo)))() as saver:
            app.state.saver = saver
            yield

    async def authed(request: Request) -> Caller:
        try:
            return await verify(_bearer(request))
        except AuthError as e:
            raise HttpError(401, str(e)) from e
        except httpx.HTTPError as e:
            log.warning("auth check failed: %s", e)
            raise HttpError(502, "Couldn't reach Supabase to check the session.") from e

    @asynccontextmanager
    async def open_thread(
        request: Request, caller: Caller, thread_id: str, *, read_only: bool = False
    ) -> AsyncIterator[tuple[FilamentAgent, str]]:
        key = f"{caller.user_id}:{thread_id}"
        lock = locks.setdefault(key, asyncio.Lock())
        if lock.locked() and not read_only:
            raise HttpError(409, "This conversation is still busy with the previous message.")
        service = service_for(caller)
        # Reading thread state never calls the model, so it works without an API key.
        agent = FilamentAgent(
            service,
            llm=_NO_MODEL if read_only else get_llm(),
            config=cfg,
            checkpointer=request.app.state.saver,
        )
        try:
            if read_only:
                async with agent:
                    yield agent, key
            else:
                async with lock, agent:
                    yield agent, key
        finally:
            http = getattr(service.backend, "_http", None)
            if isinstance(http, httpx.Client):
                http.close()

    async def run(fn: Callable[[], Awaitable[JSONResponse]]) -> JSONResponse:
        try:
            return await fn()
        except HttpError as e:
            return JSONResponse({"error": e.message}, status_code=e.status)
        except Exception as e:
            if _missing_key(e):
                return JSONResponse({"error": "The agent has no model API key configured."}, status_code=503)
            log.exception("chat request failed")
            return JSONResponse({"error": "The agent hit an error. Try again."}, status_code=500)

    async def chat(request: Request) -> JSONResponse:
        async def go() -> JSONResponse:
            caller = await authed(request)
            body: ChatRequest = await _body(request, ChatRequest)
            async with open_thread(request, caller, body.thread_id) as (agent, key):
                if await agent.pending_approval(key):
                    raise HttpError(409, "Approve or decline the pending change first.")
                result = await agent.ask(key, body.message.strip())
            return JSONResponse(_turn_json(result))

        return await run(go)

    async def approve(request: Request) -> JSONResponse:
        async def go() -> JSONResponse:
            caller = await authed(request)
            body: ApproveRequest = await _body(request, ApproveRequest)
            async with open_thread(request, caller, body.thread_id) as (agent, key):
                pending = await agent.pending_approval(key)
                if not pending:
                    raise HttpError(409, "Nothing is waiting for approval in this conversation.")
                decisions = body.decisions
                if isinstance(decisions, dict):
                    ids = [a["id"] for a in pending["actions"]]
                    unknown = set(decisions) - set(ids)
                    if unknown:
                        raise HttpError(400, f"Unknown action id(s): {', '.join(sorted(unknown))}")
                    decisions = {i: decisions.get(i, False) for i in ids}
                result = await agent.resume(key, decisions)
            return JSONResponse(_turn_json(result))

        return await run(go)

    async def thread(request: Request) -> JSONResponse:
        async def go() -> JSONResponse:
            caller = await authed(request)
            thread_id = request.path_params["thread_id"]
            if not re.match(THREAD_ID, thread_id):
                raise HttpError(400, "Invalid thread id.")
            async with open_thread(request, caller, thread_id, read_only=True) as (agent, key):
                pending = await agent.pending_approval(key)
                snap = await agent.graph.aget_state(agent._cfg(key))
            values = snap.values or {}
            return JSONResponse(
                {
                    "thread_id": thread_id,
                    "history": values.get("history") or [],
                    "pending_approval": pending,
                    # The question that's waiting on the approval (not in history until the turn ends).
                    "pending_question": values.get("question") if pending else None,
                }
            )

        return await run(go)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "demo": demo})

    return Starlette(
        routes=[
            Route("/healthz", healthz),
            Route("/chat", chat, methods=["POST"]),
            Route("/chat/approve", approve, methods=["POST"]),
            Route("/chat/{thread_id}", thread, methods=["GET"]),
        ],
        lifespan=lifespan,
    )


def serve(demo: bool, host: str, port: int) -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(demo=demo), host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")
