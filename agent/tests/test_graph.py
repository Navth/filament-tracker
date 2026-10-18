from conftest import ScriptedLLM, final, reply, tool_use

from filament_agent.agent import FilamentAgent
from filament_agent.config import AgentConfig


def spool_remaining(service, sid):
    return service.get_spool(sid).remaining_g


def tool_results(request):
    """tool_result blocks in the last user message of a request."""
    content = request[-1]["content"]
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]


async def test_read_only_question():
    llm = ScriptedLLM(
        reply(tool_use("check_print_feasibility", grams=180, material="PETG")),
        reply(final("Yes, spool #4 has 600 g.", verdict="yes", grams_needed=180, grams_available=600, spool_ids=[4])),
    )
    from conftest import FIXTURE  # noqa: PLC0415

    from filament_agent.repository import FilamentService, FixtureBackend

    service = FilamentService(FixtureBackend.from_file(FIXTURE))
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "enough PETG for 180 g?")
    assert r.status == "answered"
    assert r.answer.verdict == "yes"
    assert [t["tool"] for t in r.trace] == ["check_print_feasibility"]
    assert r.usage["model_calls"] == 2
    # The first request carries the layered context, including the snapshot.
    first = llm.requests[0][0]["content"]
    assert "<workspace_snapshot>" in first and "spool #4 in slot 4" in first
    # Tool results go back as compact JSON.
    assert '"verdict":"yes"' in tool_results(llm.requests[1])[0]["content"]


async def test_write_needs_approval_and_runs_when_approved(service):
    call = tool_use("log_print", title="Clip", grams=12.5, slot=1)
    llm = ScriptedLLM(
        reply(call),
        reply(final("Logged.", spool_ids=[1], grams_available=495, actions_taken=["Logged 12.5 g on spool #1"])),
    )
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "log a 12.5 g clip on slot 1")
        assert r.status == "needs_approval"
        assert r.approval["actions"][0]["tool"] == "log_print"
        assert spool_remaining(service, 1) == 507.5  # nothing written yet
        assert (await agent.pending_approval("t"))["actions"][0]["id"] == call["id"]
        r = await agent.resume("t", True)
    assert r.status == "answered"
    assert spool_remaining(service, 1) == 495.0
    assert r.trace[0]["approved"] is True


async def test_declined_write_is_not_run(service):
    llm = ScriptedLLM(
        reply(tool_use("correct_spool_weight", spool_id=2, measured_g=100)),
        reply(final("Okay, I left it unchanged.")),
    )
    async with FilamentAgent(service, llm=llm) as agent:
        await agent.ask("t", "set spool 2 to 100 g")
        r = await agent.resume("t", False)
    assert r.status == "answered"
    assert spool_remaining(service, 2) == 209.7
    result = tool_results(llm.requests[1])[0]
    assert result["is_error"] and "declined" in result["content"]


async def test_verifier_rejects_wrong_numbers_then_accepts(service):
    llm = ScriptedLLM(
        reply(final("Spool 2 has 300 g.", verdict="yes", grams_needed=200, grams_available=300, spool_ids=[2])),
        reply(final("Tight: spool #2 has 209.7 g.", verdict="tight", grams_needed=200, grams_available=209.7,
                    spool_ids=[2])),
    )
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "200 g on spool 2?")
    feedback = tool_results(llm.requests[1])[0]
    assert feedback["is_error"]
    assert "grams_available=300" in feedback["content"] and "verdict 'yes'" in feedback["content"]
    assert r.answer.verdict == "tight" and r.answer.confidence == "high"


async def test_verifier_catches_claimed_actions_without_writes(service):
    llm = ScriptedLLM(
        reply(final("Done, logged it.", actions_taken=["Logged print"])),
        reply(final("I haven't logged anything yet. Which slot?")),
    )
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "log a print")
    assert "no change succeeded" in tool_results(llm.requests[1])[0]["content"]
    assert r.answer.actions_taken == []


async def test_text_reply_gets_nudged(service):
    llm = ScriptedLLM(reply({"type": "text", "text": "Hmm."}), reply(final("Here you go.")))
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "hi")
    assert r.answer.answer == "Here you go."
    assert "final_answer" in llm.requests[1][-1]["content"]


async def test_gives_up_after_max_steps(service):
    llm = ScriptedLLM(*[reply(tool_use("list_spools")) for _ in range(3)])
    async with FilamentAgent(service, llm=llm, config=AgentConfig(max_steps=3)) as agent:
        r = await agent.ask("t", "loop forever")
    assert r.answer.confidence == "low" and "too many steps" in r.answer.answer


async def test_refusal_ends_turn(service):
    llm = ScriptedLLM(reply({"type": "text", "text": ""}, stop="refusal"))
    async with FilamentAgent(service, llm=llm) as agent:
        r = await agent.ask("t", "...")
    assert r.answer.verdict == "unknown" and "can't help" in r.answer.answer


async def test_history_carries_over_and_compacts(service):
    cfg = AgentConfig(keep_recent_turns=2)
    llm = ScriptedLLM(*[reply(final(f"answer {i}")) for i in range(4)])
    async with FilamentAgent(service, llm=llm, config=cfg) as agent:
        for i in range(4):
            await agent.ask("t", f"question {i}")
    last = llm.requests[-1][0]["content"]
    assert "question 2" in last and "answer 2" in last  # recent turns verbatim
    assert "question 0" not in last  # older turns folded into the summary
    assert "<conversation_summary>" in last and llm.summaries
    # Separate threads don't share history.
    async with FilamentAgent(service, llm=ScriptedLLM(reply(final("x")))) as agent:
        await agent.ask("other", "fresh")
        assert "<recent_turns>" not in agent.llm.requests[0][0]["content"]
