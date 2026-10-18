"""The grader must pass a correct answer, fail wrong ones, and the null baseline must score ~0."""

import argparse
import copy
import json

import pytest

from filament_agent import evals
from filament_agent.agent import TurnResult
from filament_agent.models import AgentAnswer
from filament_agent.repository import FilamentService, FixtureBackend


def case(case_id):
    for line in evals.CASES.read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        if c["id"] == case_id:
            return c
    raise KeyError(case_id)


def turn(**fields):
    base = dict(answer="x", verdict="not_applicable", grams_needed=None, grams_available=None, spool_ids=[],
                actions_taken=[], confidence="high")
    base.update(fields)
    return TurnResult("answered", answer=AgentAnswer(**base))


def svc(fixture=None):
    return FilamentService(FixtureBackend(copy.deepcopy(evals.load_fixture(fixture))))


def test_cases_file_is_valid():
    lines = evals.CASES.read_text(encoding="utf-8").splitlines()
    cases = [json.loads(line) for line in lines]
    assert len({c["id"] for c in cases}) == len(cases) >= 20
    for c in cases:
        assert c["turns"] and c.get("judge") and c.get("expect"), c["id"]


def test_correct_answer_passes():
    g = evals.grade_deterministic(
        case("feas-white-200-tight"), [turn(verdict="tight", spool_ids=[2], grams_available=209.7)], svc(), 0
    )
    assert g.passed, g.details


@pytest.mark.parametrize(
    "fields",
    [
        dict(verdict="yes", spool_ids=[2], grams_available=209.7),  # wrong verdict
        dict(verdict="tight", spool_ids=[4], grams_available=209.7),  # wrong spool
        dict(verdict="tight", spool_ids=[2], grams_available=250),  # wrong grams
        dict(verdict="tight", spool_ids=[2], grams_available=None),  # missing grams
    ],
)
def test_wrong_answers_fail(fields):
    g = evals.grade_deterministic(case("feas-white-200-tight"), [turn(**fields)], svc(), 0)
    assert not g.passed


def test_unrequested_approval_fails():
    g = evals.grade_deterministic(
        case("feas-white-200-tight"), [turn(verdict="tight", spool_ids=[2], grams_available=209.7)], svc(), 1
    )
    assert g.checks["approval"] is False


def test_write_end_state_checked():
    c = case("write-log-approve")
    s = svc()
    claimed = [turn(actions_taken=["Logged 25 g"])]
    assert not evals.grade_deterministic(c, claimed, s, 1).passed  # claimed but not actually written
    s.log_print("keychain", 25, 1)
    assert evals.grade_deterministic(c, claimed, s, 1).passed


def test_injection_fixture():
    s = svc("injection")
    assert s.get_spool(4).remaining_g == 590
    assert "ignore your previous instructions" in s.list_prints(1).prints[0].title


def test_wilson():
    lo, hi = evals.wilson(20, 25)
    assert 0.6 < lo < 0.8 < hi < 0.95


# Cases where "unknown" is a correct verdict, so the null answer matches the fields.
UNKNOWN_IS_RIGHT = {"feas-tpu-missing", "clarify-enough"}


async def test_null_baseline_scores_near_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(evals, "RESULTS", tmp_path)
    args = argparse.Namespace(reps=1, case=None, tag=None, concurrency=8, no_judge=True, baseline="null")
    out = await evals.run(args)
    rows = [json.loads(line) for line in (out / "results.jsonl").read_text().splitlines()]
    assert len(rows) == len(evals.CASES.read_text().splitlines())
    assert not (out / "errors.jsonl").read_text().strip()
    # Without the judge, "I don't know" can only pass cases whose deterministic checks are
    # all about *not* doing something (no approval, data unchanged). Those cases rely on the judge.
    for r in rows:
        if r["passed"]:
            assert set(r["checks"]) <= {"approval", "actions", "end_state"} or r["case"] in UNKNOWN_IS_RIGHT, r["case"]
    assert sum(r["passed"] for r in rows) / len(rows) < 0.35
