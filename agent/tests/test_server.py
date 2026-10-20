from contextlib import asynccontextmanager

import pytest
from conftest import FIXTURE, ScriptedLLM, final, reply, tool_use
from langgraph.checkpoint.memory import InMemorySaver
from starlette.testclient import TestClient

from filament_agent.repository import FilamentService, FixtureBackend
from filament_agent.server import AuthError, Caller, create_app

TOKENS = {"tok-a": "user-a", "tok-b": "user-b"}
A = {"Authorization": "Bearer tok-a"}
B = {"Authorization": "Bearer tok-b"}


async def fake_verify(token: str) -> Caller:
    if token not in TOKENS:
        raise AuthError("Session expired. Sign in again.")
    return Caller(user_id=TOKENS[token], email="", token=token)


@asynccontextmanager
async def memory_saver():
    yield InMemorySaver()


def make_client(*responses):
    services: dict[str, FilamentService] = {}

    def service_for(caller: Caller) -> FilamentService:
        return services.setdefault(caller.user_id, FilamentService(FixtureBackend.from_file(FIXTURE)))

    app = create_app(
        verify=fake_verify, service_for=service_for, llm=ScriptedLLM(*responses), checkpointer=memory_saver
    )
    return TestClient(app), services


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": "Basic tok-a"}])
def test_requires_a_valid_token(headers):
    client, _ = make_client()
    with client:
        r = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=headers)
        assert r.status_code == 401
        assert client.get("/chat/t1", headers=headers).status_code == 401


def test_rejects_bad_input():
    client, _ = make_client()
    with client:
        assert client.post("/chat", json={"thread_id": "../x", "message": "hi"}, headers=A).status_code == 400
        assert client.post("/chat", json={"thread_id": "t1", "message": ""}, headers=A).status_code == 400
        assert client.post("/chat", content=b"not json", headers=A).status_code == 400
        assert client.get("/chat/bad%20id", headers=A).status_code == 400


def test_answer_then_history():
    client, _ = make_client(
        reply(tool_use("check_print_feasibility", grams=180, material="PETG")),
        reply(final("Yes, spool #4 has 600 g.", verdict="yes", grams_needed=180, grams_available=600, spool_ids=[4])),
    )
    with client:
        r = client.post("/chat", json={"thread_id": "t1", "message": "enough PETG for 180 g?"}, headers=A)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "answered"
        assert body["answer"]["verdict"] == "yes" and body["answer"]["spool_ids"] == [4]
        state = client.get("/chat/t1", headers=A).json()
        assert state["history"][0]["question"] == "enough PETG for 180 g?"
        assert state["pending_approval"] is None and state["pending_question"] is None


def test_write_approval_flow_and_isolation():
    call = tool_use("log_print", title="Clip", grams=12.5, slot=1)
    client, services = make_client(
        reply(call),
        reply(final("Logged.", spool_ids=[1], grams_available=495, actions_taken=["Logged 12.5 g on spool #1"])),
    )
    with client:
        r = client.post("/chat", json={"thread_id": "t1", "message": "log a 12.5 g clip on slot 1"}, headers=A)
        assert r.json()["status"] == "needs_approval"
        assert r.json()["approval"]["actions"][0]["id"] == call["id"]

        # The pending approval has to be answered before a new question.
        assert client.post("/chat", json={"thread_id": "t1", "message": "x"}, headers=A).status_code == 409
        # Another user with the same thread id sees an empty thread and can't approve anything.
        other = client.get("/chat/t1", headers=B).json()
        assert other["history"] == [] and other["pending_approval"] is None
        assert client.post("/chat/approve", json={"thread_id": "t1", "decisions": True}, headers=B).status_code == 409
        # Unknown action ids are rejected.
        bad = client.post("/chat/approve", json={"thread_id": "t1", "decisions": {"nope": True}}, headers=A)
        assert bad.status_code == 400

        state = client.get("/chat/t1", headers=A).json()
        assert state["pending_approval"]["actions"][0]["tool"] == "log_print"
        assert state["pending_question"] == "log a 12.5 g clip on slot 1"
        r = client.post("/chat/approve", json={"thread_id": "t1", "decisions": {call["id"]: True}}, headers=A)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "answered"
        assert r.json()["answer"]["actions_taken"] == ["Logged 12.5 g on spool #1"]
    assert services["user-a"].get_spool(1).remaining_g == 495.0
    assert "user-b" not in services or services["user-b"].get_spool(1).remaining_g == 507.5


def test_approve_without_pending():
    client, _ = make_client()
    with client:
        r = client.post("/chat/approve", json={"thread_id": "t1", "decisions": False}, headers=A)
        assert r.status_code == 409


def test_missing_model_key_is_a_clear_error(monkeypatch):
    class NoKey:
        async def create(self, *a):
            raise TypeError('Could not resolve authentication method. Expected the api_key to be set.')

        async def summarize(self, *a):
            return ""

    app = create_app(
        verify=fake_verify,
        service_for=lambda c: FilamentService(FixtureBackend.from_file(FIXTURE)),
        llm=NoKey(),
        checkpointer=memory_saver,
    )
    with TestClient(app) as client:
        r = client.post("/chat", json={"thread_id": "t1", "message": "hi"}, headers=A)
        assert r.status_code == 503
