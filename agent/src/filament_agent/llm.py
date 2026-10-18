"""The model behind the agent, behind a small interface so tests can script it."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from .config import AgentConfig
from .context import SUMMARY_PROMPT

FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass
class LLMResponse:
    content: list[dict[str, Any]]  # assistant content blocks as plain dicts (sent back unchanged)
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]

    @property
    def text(self) -> str:
        return "".join(b.get("text", "") for b in self.content if b.get("type") == "text")


def echo_content(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make assistant content safe to send back after a mid-output fallback.

    Before the last ``fallback`` block only text survives (the declined model's
    thinking and tool calls are dropped); everything after it is kept as is.
    """
    marks = [i for i, b in enumerate(blocks) if b.get("type") == "fallback"]
    if not marks:
        return blocks
    cut = marks[-1]
    return [b for b in blocks[:cut] if b.get("type") == "text"] + blocks[cut:]


class LLM(Protocol):
    async def create(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMResponse: ...
    async def summarize(self, previous: str, transcript: str) -> str: ...


@dataclass
class ClaudeLLM:
    """Claude via the official Anthropic SDK."""

    config: AgentConfig = field(default_factory=AgentConfig)
    client: anthropic.AsyncAnthropic = field(default_factory=anthropic.AsyncAnthropic)

    def _extra(self) -> dict[str, Any]:
        # On a safety decline the API re-runs the request on a fallback model it picks.
        if self.config.fallbacks:
            return {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        return {}

    async def create(self, system, messages, tools):
        resp = await self.client.beta.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            # Tools render before the system prompt, so this one breakpoint caches both.
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
            tools=tools,
            output_config={"effort": self.config.effort},
            **self._extra(),
        )
        usage = resp.usage
        return LLMResponse(
            content=echo_content([b.model_dump(mode="json", exclude_none=True) for b in resp.content]),
            stop_reason=resp.stop_reason,
            input_tokens=(usage.input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
            + (usage.cache_read_input_tokens or 0),
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            model=resp.model,
        )

    async def summarize(self, previous, transcript):
        resp = await self.client.beta.messages.create(
            model=self.config.model,
            max_tokens=2000,
            system=SUMMARY_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"<current_summary>\n{previous or '(none)'}\n</current_summary>\n\n"
                    f"<turns_to_fold_in>\n{transcript}\n</turns_to_fold_in>",
                }
            ],
            output_config={"effort": "low"},
            **self._extra(),
        )
        if resp.stop_reason == "refusal":
            return previous
        return "".join(b.text for b in resp.content if b.type == "text").strip() or previous


def make_llm(config: AgentConfig | None = None) -> LLM:
    """The model the config asks for: Gemini (default) or Claude."""
    config = config or AgentConfig()
    if config.provider == "claude":
        return ClaudeLLM(config)
    if config.provider == "gemini":
        from .gemini_llm import GeminiLLM

        return GeminiLLM()
    raise ValueError(f"unknown FT_AGENT_PROVIDER {config.provider!r} (use gemini or claude)")
