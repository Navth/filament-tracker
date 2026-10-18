"""Typed data contracts shared by the repository, the MCP tools and the agent.

The MCP tools return these models, so every tool result the model sees has a
fixed, documented shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------- domain data


class Spool(BaseModel):
    id: int
    slot: int
    brand: str = ""
    material: str = "PLA"
    color: str = ""
    color_name: str = ""
    initial_g: float
    used_g: float
    remaining_g: float
    pct_left: int
    active: bool
    started_at: datetime | None = None
    ended_at: datetime | None = None
    print_count: int = 0
    note: str = ""


class Print(BaseModel):
    id: int
    title: str
    weight_g: float
    slot: int
    spool_id: int | None
    counted: bool
    source: Literal["cloud", "manual"]
    start_time: datetime | None = None
    end_time: datetime | None = None


class Settings(BaseModel):
    slot_count: int = 1
    last_sync: datetime | None = None


# --------------------------------------------------------------- tool results


class SpoolList(BaseModel):
    as_of: datetime
    spools: list[Spool]
    slot_count: int


class PrintList(BaseModel):
    prints: list[Print]
    total_returned: int


class SpoolUsage(BaseModel):
    spool_id: int
    label: str
    remaining_g: float
    used_in_window_g: float
    avg_g_per_day: float
    days_until_empty: float | None = Field(
        description="Remaining grams divided by average daily use; null when unused in the window."
    )


class UsageSummary(BaseModel):
    window_days: int
    total_used_g: float
    print_count: int
    by_material: dict[str, float]
    spools: list[SpoolUsage]


Verdict = Literal["yes", "tight", "no"]


class Candidate(BaseModel):
    spool_id: int
    label: str
    remaining_g: float
    margin_g: float = Field(description="remaining_g minus grams_needed")
    verdict: Verdict


class Feasibility(BaseModel):
    grams_needed: float
    safety_margin_pct: float
    material: str | None
    color: str | None
    verdict: Verdict | Literal["no_matching_spool"]
    best_spool_id: int | None
    candidates: list[Candidate]
    note: str


class WriteResult(BaseModel):
    ok: bool
    message: str
    spool: Spool | None = None


# --------------------------------------------------------------- agent output

AnswerVerdict = Literal["yes", "tight", "no", "not_applicable", "unknown"]


class AgentAnswer(BaseModel):
    """What the agent returns at the end of every turn (via the final_answer tool)."""

    answer: str = Field(description="The reply for the user, in plain language. Markdown allowed.")
    verdict: AnswerVerdict = Field(
        description="For 'do I have enough filament' questions: yes, tight, or no. "
        "Otherwise not_applicable, or unknown if the data can't tell."
    )
    grams_needed: float | None = Field(description="Grams the user asked about, if any.")
    grams_available: float | None = Field(
        description="Remaining grams on the spool(s) the answer relies on, if any."
    )
    spool_ids: list[int] = Field(description="IDs of the spools the answer is about.")
    actions_taken: list[str] = Field(description="Changes made this turn, e.g. 'Logged 12 g print'. Empty if none.")
    confidence: Literal["high", "medium", "low"]


def final_answer_schema() -> dict:
    """Strict JSON Schema for the final_answer tool (every key required)."""
    num_or_null = {"type": ["number", "null"]}
    return {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "verdict": {"type": "string", "enum": ["yes", "tight", "no", "not_applicable", "unknown"]},
            "grams_needed": num_or_null,
            "grams_available": num_or_null,
            "spool_ids": {"type": "array", "items": {"type": "integer"}},
            "actions_taken": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": [
            "answer",
            "verdict",
            "grams_needed",
            "grams_available",
            "spool_ids",
            "actions_taken",
            "confidence",
        ],
        "additionalProperties": False,
    }
