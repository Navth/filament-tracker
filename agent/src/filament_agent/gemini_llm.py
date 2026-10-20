"""Gemini via Google's Gen AI SDK, behind the same LLM interface as Claude.

The graph stores conversations in one neutral shape (text / tool_use /
tool_result blocks). This adapter translates to Gemini ``Content`` objects on
the way out and back on the way in. Gemini's own parts (including thought
signatures, which Gemini requires back on later function-calling turns) are
kept in an extra ``gemini_parts`` block and replayed verbatim.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types

from .context import SUMMARY_PROMPT
from .llm import LLMResponse

REFUSAL_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


class Throttle:
    """Spaces requests to stay under a requests-per-minute limit (free tier)."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        if not self.interval:
            return
        async with self._lock:
            delay = self._next - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next = max(time.monotonic(), self._next) + self.interval


_THROTTLES: dict[float, Throttle] = {}


def shared_throttle(rpm: float) -> Throttle:
    """One throttle per process and limit, shared by every agent instance (evals run many)."""
    if rpm not in _THROTTLES:
        _THROTTLES[rpm] = Throttle(rpm)
    return _THROTTLES[rpm]


def make_client() -> genai.Client:
    return genai.Client(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=6, initial_delay=2.0, max_delay=60.0, jitter=1.0)
        )
    )


# ------------------------------------------------------------------ translation


def _tool_names(messages: list[dict[str, Any]]) -> dict[str, str]:
    names = {}
    for m in messages:
        if m["role"] == "assistant" and isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "tool_use":
                    names[b["id"]] = b["name"]
    return names


def to_contents(messages: list[dict[str, Any]]) -> list[types.Content]:
    names = _tool_names(messages)
    contents = []
    for m in messages:
        blocks = m["content"]
        if isinstance(blocks, str):
            contents.append(types.Content(role="user" if m["role"] == "user" else "model",
                                          parts=[types.Part(text=blocks)]))
            continue
        if m["role"] == "assistant":
            raw = next((b["parts"] for b in blocks if b.get("type") == "gemini_parts"), None)
            if raw is not None:
                parts = [types.Part.model_validate(p) for p in raw]
            else:
                parts = []
                for b in blocks:
                    if b.get("type") == "text" and b.get("text"):
                        parts.append(types.Part(text=b["text"]))
                    elif b.get("type") == "tool_use":
                        parts.append(types.Part(function_call=types.FunctionCall(
                            id=b["id"], name=b["name"], args=b.get("input") or {})))
            contents.append(types.Content(role="model", parts=parts or [types.Part(text="")]))
            continue
        parts = []
        for b in blocks:
            if b.get("type") == "text":
                parts.append(types.Part(text=b["text"]))
            elif b.get("type") == "tool_result":
                raw = b.get("content")
                try:
                    value = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    value = raw
                key = "error" if b.get("is_error") else "result"
                parts.append(types.Part(function_response=types.FunctionResponse(
                    id=b["tool_use_id"], name=names.get(b["tool_use_id"], "unknown"), response={key: value})))
        contents.append(types.Content(role="user", parts=parts))
    return contents


def to_declarations(tools: list[dict[str, Any]]) -> list[types.Tool]:
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(name=t["name"], description=t.get("description", ""),
                                  parameters_json_schema=t["input_schema"])
        for t in tools
    ])]


def from_response(resp: types.GenerateContentResponse, model: str) -> LLMResponse:
    usage = resp.usage_metadata
    common = {
        "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
        "output_tokens": ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0,
        "cache_read_tokens": (usage.cached_content_token_count or 0) if usage else 0,
        "model": resp.model_version or model,
    }
    if not resp.candidates:
        blocked = resp.prompt_feedback and resp.prompt_feedback.block_reason
        return LLMResponse(content=[], stop_reason="refusal" if blocked else "end_turn", **common)
    cand = resp.candidates[0]
    parts = (cand.content.parts if cand.content else None) or []
    blocks: list[dict[str, Any]] = []
    for p in parts:
        if p.function_call:
            fc = p.function_call
            blocks.append({"type": "tool_use", "id": fc.id or f"call_{uuid.uuid4().hex[:12]}",
                           "name": fc.name, "input": dict(fc.args or {})})
        elif p.text and not p.thought:
            blocks.append({"type": "text", "text": p.text})
    # Keep Gemini's parts (with the ids we assigned) so the next request replays them exactly.
    raw = []
    ids = iter(b["id"] for b in blocks if b["type"] == "tool_use")
    for p in parts:
        d = p.to_json_dict()
        if p.function_call:
            d["function_call"]["id"] = next(ids)
        raw.append(d)
    blocks.append({"type": "gemini_parts", "parts": raw})

    reason = cand.finish_reason.name if cand.finish_reason else "STOP"
    if reason == "MAX_TOKENS":
        stop = "max_tokens"
    elif reason in REFUSAL_REASONS:
        stop = "refusal"
    elif any(b["type"] == "tool_use" for b in blocks):
        stop = "tool_use"
    else:
        stop = "end_turn"
    return LLMResponse(content=blocks, stop_reason=stop, **common)


# ------------------------------------------------------------------ client


@dataclass
class GeminiLLM:
    # Not "gemini-flash-latest": on the free tier that alias (gemini-3.8-flash) took ~150 s
    # per call in Oct 2026, versus ~2 s for gemini-3.5-flash.
    model: str = os.environ.get("FT_GEMINI_MODEL", "gemini-3.5-flash")
    thinking_level: str | None = os.environ.get("FT_GEMINI_THINKING") or None  # minimal|low|medium|high
    max_output_tokens: int = int(os.environ.get("FT_AGENT_MAX_TOKENS", "16000"))
    rpm: float = float(os.environ.get("FT_GEMINI_RPM", "8"))
    client: genai.Client = field(default_factory=make_client)

    def _config(self, system: str, tools: list[dict[str, Any]] | None) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=system,
            tools=to_declarations(tools) if tools else None,
            max_output_tokens=self.max_output_tokens,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level.upper())
            if self.thinking_level else None,
        )

    async def create(self, system, messages, tools):
        await shared_throttle(self.rpm).wait()
        resp = await self.client.aio.models.generate_content(
            model=self.model, contents=to_contents(messages), config=self._config(system, tools)
        )
        return from_response(resp, self.model)

    async def summarize(self, previous, transcript):
        await shared_throttle(self.rpm).wait()
        resp = await self.client.aio.models.generate_content(
            model=self.model,
            contents=f"<current_summary>\n{previous or '(none)'}\n</current_summary>\n\n"
                     f"<turns_to_fold_in>\n{transcript}\n</turns_to_fold_in>",
            config=types.GenerateContentConfig(system_instruction=SUMMARY_PROMPT),
        )
        return (resp.text or "").strip() or previous
