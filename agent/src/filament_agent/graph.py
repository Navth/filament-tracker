"""The agent as a LangGraph state machine.

    prepare ─► call_model ─┬─► run_tools ─────────────► call_model
                           ├─► approve (interrupt) ─► run_tools
                           ├─► nudge ───────────────► call_model
                           ├─► verify ─┬─► call_model   (answer failed a check)
                           │           └─► finish ─► END
                           └─► give_up ─► finish

* Every state change is checkpointed, so a turn paused for approval can be
  resumed later (even from another process) with Command(resume=...).
* Write tools (anything the MCP server doesn't mark read-only) pause the
  graph with interrupt() until the user approves or declines.
* The final answer comes back through a strict ``final_answer`` tool and is
  validated with Pydantic, then checked against the data by deterministic
  gates before the user sees it.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from mcp.client.client import Client
from pydantic import ValidationError

from .config import AgentConfig
from .context import (
    SYSTEM_PROMPT,
    Turn,
    build_turn_message,
    compact_json,
    snapshot_text,
    split_history,
)
from .llm import LLM, LLMResponse
from .models import AgentAnswer, final_answer_schema

FINAL_ANSWER_TOOL = {
    "name": "final_answer",
    "description": "Give the user your answer and end the turn. Call exactly once, on its own, as the last step.",
    "input_schema": final_answer_schema(),
    "strict": True,
}

DECLINED = "The user declined this action, so it was not done. Don't retry it."


class AgentState(TypedDict, total=False):
    # carried across turns
    history: list[dict[str, str]]
    summary: str
    # this turn
    question: str
    messages: list[dict[str, Any]]
    pending_calls: list[dict[str, Any]]
    approvals: dict[str, bool]
    steps: int
    nudged: bool
    verify_failures: int
    stop_reason: str | None
    answer: dict[str, Any] | None
    trace: list[dict[str, Any]]
    usage: dict[str, int]
    served_models: list[str]


# ------------------------------------------------------------------ tools


class Toolbox:
    """MCP tools as Claude tool definitions, plus a way to call them."""

    def __init__(self, client: Client, tools: list[Any]):
        self.client = client
        self.specs = [
            {"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in tools
        ] + [FINAL_ANSWER_TOOL]
        self.writes = {t.name for t in tools if not (t.annotations and t.annotations.read_only_hint)}

    @classmethod
    async def connect(cls, client: Client) -> Toolbox:
        return cls(client, (await client.list_tools()).tools)

    def is_write(self, name: str) -> bool:
        return name in self.writes

    async def call(self, name: str, args: dict[str, Any]) -> tuple[Any, bool]:
        result = await self.client.call_tool(name, args)
        if result.structured_content is not None and not result.is_error:
            return result.structured_content, False
        text = "\n".join(getattr(c, "text", "") for c in result.content)
        try:
            return json.loads(text), bool(result.is_error)
        except ValueError:
            return text, bool(result.is_error)


# ------------------------------------------------------------------ helpers


def _add_usage(state: AgentState, resp: LLMResponse) -> dict[str, int]:
    u = dict(state.get("usage") or {})
    u["input_tokens"] = u.get("input_tokens", 0) + resp.input_tokens
    u["output_tokens"] = u.get("output_tokens", 0) + resp.output_tokens
    u["cache_read_tokens"] = u.get("cache_read_tokens", 0) + resp.cache_read_tokens
    u["model_calls"] = u.get("model_calls", 0) + 1
    return u


def _result_block(call_id: str, content: Any, is_error: bool) -> dict[str, Any]:
    text = content if isinstance(content, str) else compact_json(content)
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return block


def _fallback_answer(text: str) -> dict[str, Any]:
    return AgentAnswer(
        answer=text,
        verdict="unknown",
        grams_needed=None,
        grams_available=None,
        spool_ids=[],
        actions_taken=[],
        confidence="low",
    ).model_dump()


# ------------------------------------------------------------------ graph


def build_graph(llm: LLM, tools: Toolbox, config: AgentConfig | None = None, checkpointer: Any = None):
    cfg = config or AgentConfig()

    async def prepare(state: AgentState) -> AgentState:
        history = [Turn.from_dict(t) for t in state.get("history") or []]
        recent, _ = split_history(history, cfg.history_budget_tokens, cfg.keep_recent_turns)
        spools, err = await tools.call("list_spools", {})
        snapshot = snapshot_text(spools) if not err else f"(snapshot unavailable: {spools})"
        content = build_turn_message(state.get("summary", ""), recent, snapshot, state["question"])
        return {
            "messages": [{"role": "user", "content": content}],
            "pending_calls": [],
            "approvals": {},
            "steps": 0,
            "nudged": False,
            "verify_failures": 0,
            "stop_reason": None,
            "answer": None,
            "trace": [],
            "usage": {},
            "served_models": [],
        }

    async def call_model(state: AgentState) -> AgentState:
        resp = await llm.create(SYSTEM_PROMPT, state["messages"], tools.specs)
        return {
            "messages": state["messages"] + [{"role": "assistant", "content": resp.content}],
            "pending_calls": resp.tool_calls,
            "stop_reason": resp.stop_reason,
            "steps": state.get("steps", 0) + 1,
            "usage": _add_usage(state, resp),
            "served_models": (state.get("served_models") or []) + ([resp.model] if resp.model else []),
        }

    def route(state: AgentState) -> str:
        calls = state.get("pending_calls") or []
        if state.get("stop_reason") in ("refusal", "max_tokens"):
            return "give_up"
        if any(c["name"] == "final_answer" for c in calls):
            return "verify"
        if state.get("steps", 0) >= cfg.max_steps:
            return "give_up"
        if not calls:
            return "give_up" if state.get("nudged") else "nudge"
        if any(tools.is_write(c["name"]) for c in calls):
            return "approve"
        return "run_tools"

    async def nudge(state: AgentState) -> AgentState:
        msg = {"role": "user", "content": "Please give your answer by calling the final_answer tool."}
        return {"messages": state["messages"] + [msg], "nudged": True}

    async def approve(state: AgentState) -> AgentState:
        writes = [c for c in state["pending_calls"] if tools.is_write(c["name"])]
        # Pauses the graph. Resume with Command(resume=True/False) or {"<call id>": bool}.
        decision = interrupt(
            {
                "type": "approval",
                "actions": [{"id": c["id"], "tool": c["name"], "input": c["input"]} for c in writes],
            }
        )
        if isinstance(decision, dict):
            approvals = {c["id"]: bool(decision.get(c["id"], decision.get("approved", False))) for c in writes}
        else:
            approvals = {c["id"]: bool(decision) for c in writes}
        return {"approvals": approvals}

    async def run_tools(state: AgentState) -> AgentState:
        results, trace = [], list(state.get("trace") or [])
        approvals = state.get("approvals") or {}
        for call in state["pending_calls"]:
            name, args = call["name"], call.get("input") or {}
            entry: dict[str, Any] = {"tool": name, "input": args}
            if tools.is_write(name) and not approvals.get(call["id"], False):
                results.append(_result_block(call["id"], DECLINED, True))
                trace.append({**entry, "approved": False, "is_error": True})
                continue
            if tools.is_write(name):
                entry["approved"] = True
            try:
                out, is_error = await tools.call(name, args)
            except Exception as e:  # transport problems shouldn't kill the turn
                out, is_error = f"Tool failed: {e}", True
            results.append(_result_block(call["id"], out, is_error))
            trace.append({**entry, "is_error": is_error})
        return {
            "messages": state["messages"] + [{"role": "user", "content": results}],
            "pending_calls": [],
            "approvals": {},
            "trace": trace,
        }

    async def verify(state: AgentState) -> AgentState:
        calls = state["pending_calls"]
        final = next(c for c in calls if c["name"] == "final_answer")
        problems: list[str] = []
        answer: AgentAnswer | None = None
        try:
            answer = AgentAnswer.model_validate(final["input"])
        except ValidationError as e:
            problems.append(f"final_answer input is invalid: {e.errors()[:3]}")
        if len(calls) > 1:
            problems.append("final_answer must be called on its own, after other tools have returned.")
        if answer is not None:
            problems += await _check_answer(answer, state.get("trace") or [])
        if not problems or state.get("verify_failures", 0) >= 2:
            ans = answer.model_dump() if answer else _fallback_answer("Sorry, I couldn't put together an answer.")
            if problems:
                ans["confidence"] = "low"
            return {"answer": ans, "pending_calls": []}
        # Send the problems back as the final_answer tool's error and let the model fix them.
        blocks = [
            _result_block(c["id"], "Not run: final_answer must be called alone.", True)
            for c in calls
            if c is not final
        ] + [_result_block(final["id"], "Answer rejected:\n- " + "\n- ".join(problems), True)]
        trace = list(state.get("trace") or []) + [{"tool": "final_answer", "rejected": problems}]
        return {
            "messages": state["messages"] + [{"role": "user", "content": blocks}],
            "verify_failures": state.get("verify_failures", 0) + 1,
            "pending_calls": [],
            "trace": trace,
        }

    async def _check_answer(answer: AgentAnswer, trace: list[dict[str, Any]]) -> list[str]:
        """Deterministic gates: the structured fields must agree with the data."""
        problems = []
        cited = {}
        for sid in answer.spool_ids:
            spool, err = await tools.call("get_spool", {"spool_id": sid})
            if err:
                problems.append(f"spool_ids contains {sid}, which doesn't exist.")
            else:
                cited[sid] = spool
        if answer.grams_available is not None and cited:
            values = [s["remaining_g"] for s in cited.values()]
            if all(abs(answer.grams_available - v) > 1 for v in values + [sum(values)]):
                problems.append(
                    f"grams_available={answer.grams_available:g} doesn't match the cited spools "
                    f"({', '.join(f'#{k}: {v["remaining_g"]:g} g' for k, v in cited.items())})."
                )
        if answer.verdict in ("yes", "tight", "no") and answer.grams_needed and len(cited) == 1:
            sid = next(iter(cited))
            check, err = await tools.call("check_print_feasibility", {"grams": answer.grams_needed, "spool_id": sid})
            if not err and check.get("verdict") in ("yes", "tight", "no") and check["verdict"] != answer.verdict:
                problems.append(
                    f"verdict '{answer.verdict}' disagrees with check_print_feasibility for spool #{sid} "
                    f"('{check['verdict']}')."
                )
        writes_ok = [t for t in trace if t.get("approved") and not t.get("is_error")]
        if answer.actions_taken and not writes_ok:
            problems.append("actions_taken lists changes, but no change succeeded this turn.")
        if writes_ok and not answer.actions_taken:
            problems.append("A change succeeded this turn; list it in actions_taken.")
        return problems

    async def give_up(state: AgentState) -> AgentState:
        reason = state.get("stop_reason")
        if reason == "refusal":
            text = "Sorry, I can't help with that request."
        elif state.get("steps", 0) >= cfg.max_steps:
            text = "Sorry, that took too many steps. Could you ask in a simpler way?"
        else:
            last = state["messages"][-1]["content"] if state.get("messages") else []
            text = "".join(b.get("text", "") for b in last if isinstance(b, dict)).strip() or (
                "Sorry, I couldn't put together an answer."
            )
        return {"answer": _fallback_answer(text), "pending_calls": []}

    async def finish(state: AgentState) -> AgentState:
        history = [Turn.from_dict(t) for t in state.get("history") or []]
        history.append(Turn(question=state["question"], answer=state["answer"]["answer"]))
        kept, overflow = split_history(history, cfg.history_budget_tokens, cfg.keep_recent_turns)
        summary = state.get("summary", "")
        if overflow:
            summary = await llm.summarize(summary, "\n\n".join(t.render() for t in overflow))
        return {"history": [t.to_dict() for t in kept], "summary": summary}

    g = StateGraph(AgentState)
    for name, fn in [
        ("prepare", prepare),
        ("call_model", call_model),
        ("nudge", nudge),
        ("approve", approve),
        ("run_tools", run_tools),
        ("verify", verify),
        ("give_up", give_up),
        ("finish", finish),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "prepare")
    g.add_edge("prepare", "call_model")
    g.add_conditional_edges(
        "call_model", route, ["verify", "approve", "run_tools", "nudge", "give_up"]
    )
    g.add_edge("nudge", "call_model")
    g.add_edge("approve", "run_tools")
    g.add_edge("run_tools", "call_model")
    g.add_conditional_edges("verify", lambda s: "finish" if s.get("answer") else "call_model", ["finish", "call_model"])
    g.add_edge("give_up", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
