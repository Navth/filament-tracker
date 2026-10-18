"""High-level API: ask questions, handle approvals, keep threads."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from mcp.client.client import Client

from .config import AgentConfig
from .graph import Toolbox, build_graph
from .llm import LLM, make_llm
from .mcp_server import build_server
from .models import AgentAnswer
from .repository import FilamentService


@dataclass
class TurnResult:
    status: Literal["answered", "needs_approval"]
    answer: AgentAnswer | None = None
    approval: dict[str, Any] | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    stop_reason: str | None = None
    served_models: list[str] = field(default_factory=list)


class FilamentAgent:
    """Wires the service, its MCP server, the model and the graph together.

    The MCP server runs in-process (``Client(server)``); swap in
    ``StdioServerParameters`` to talk to a separate ``ft-mcp`` process instead.

        async with FilamentAgent(service) as agent:
            result = await agent.ask("t1", "Do I have enough PETG for a 180 g print?")
            if result.status == "needs_approval":
                result = await agent.resume("t1", True)
    """

    def __init__(
        self,
        service: FilamentService,
        llm: LLM | None = None,
        config: AgentConfig | None = None,
        checkpointer: Any = None,
    ):
        self.service = service
        self.config = config or AgentConfig()
        self.llm = llm or make_llm(self.config)
        self.checkpointer = checkpointer or InMemorySaver()
        self._stack = AsyncExitStack()
        self.graph: Any = None

    async def __aenter__(self) -> FilamentAgent:
        client = await self._stack.enter_async_context(Client(build_server(self.service)))
        toolbox = await Toolbox.connect(client)
        self.graph = build_graph(self.llm, toolbox, self.config, self.checkpointer)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._stack.aclose()

    @staticmethod
    def _cfg(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    async def ask(self, thread_id: str, question: str) -> TurnResult:
        out = await self.graph.ainvoke({"question": question}, self._cfg(thread_id))
        return self._result(out)

    async def resume(self, thread_id: str, decision: bool | dict[str, bool]) -> TurnResult:
        """Answer a pending approval: True/False for all actions, or {call_id: bool}."""
        out = await self.graph.ainvoke(Command(resume=decision), self._cfg(thread_id))
        return self._result(out)

    async def pending_approval(self, thread_id: str) -> dict[str, Any] | None:
        snap = await self.graph.aget_state(self._cfg(thread_id))
        for task in snap.tasks:
            for intr in task.interrupts:
                return intr.value
        return None

    @staticmethod
    def _result(out: dict[str, Any]) -> TurnResult:
        common = {
            "trace": out.get("trace") or [],
            "usage": out.get("usage") or {},
            "stop_reason": out.get("stop_reason"),
            "served_models": out.get("served_models") or [],
        }
        interrupts = out.get("__interrupt__") or []
        if interrupts:
            return TurnResult("needs_approval", approval=interrupts[0].value, **common)
        return TurnResult("answered", answer=AgentAnswer.model_validate(out["answer"]), **common)
