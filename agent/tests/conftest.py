from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest

from filament_agent.llm import LLMResponse
from filament_agent.repository import FilamentService, FixtureBackend

FIXTURE = Path(__file__).parent / "fixtures" / "demo.json"
_ids = itertools.count(1)


@pytest.fixture
def service() -> FilamentService:
    return FilamentService(FixtureBackend.from_file(FIXTURE))


def tool_use(name: str, **args: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{next(_ids)}", "name": name, "input": args}


def final(answer: str = "ok", **fields: Any) -> dict[str, Any]:
    body = {
        "answer": answer,
        "verdict": "not_applicable",
        "grams_needed": None,
        "grams_available": None,
        "spool_ids": [],
        "actions_taken": [],
        "confidence": "high",
    }
    body.update(fields)
    return tool_use("final_answer", **body)


def reply(*blocks: dict[str, Any], stop: str | None = None) -> LLMResponse:
    has_tool = any(b["type"] == "tool_use" for b in blocks)
    return LLMResponse(content=list(blocks), stop_reason=stop or ("tool_use" if has_tool else "end_turn"),
                       input_tokens=100, output_tokens=20)


class ScriptedLLM:
    """Returns pre-written responses in order and records every request."""

    def __init__(self, *responses: LLMResponse):
        self.responses = list(responses)
        self.requests: list[list[dict[str, Any]]] = []
        self.summaries: list[str] = []

    async def create(self, system, messages, tools):
        self.requests.append([dict(m) for m in messages])
        if not self.responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self.responses.pop(0)

    async def summarize(self, previous, transcript):
        self.summaries.append(transcript)
        return f"summary of {transcript.count('User:')} turn(s)"
