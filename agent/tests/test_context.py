from filament_agent.context import Turn, build_turn_message, compact_json, snapshot_text, split_history


def turns(n, size=40):
    return [Turn(f"q{i} " + "x" * size, f"a{i}") for i in range(n)]


def test_keeps_recent_turns_within_count():
    kept, overflow = split_history(turns(6), budget_tokens=10_000, keep_recent=4)
    assert [t.answer for t in kept] == ["a2", "a3", "a4", "a5"]
    assert [t.answer for t in overflow] == ["a0", "a1"]


def test_keeps_recent_turns_within_budget():
    # each turn is ~107 tokens, so only one fits in 150
    kept, overflow = split_history(turns(5, size=400), budget_tokens=150, keep_recent=4)
    assert [t.answer for t in kept] == ["a4"]  # newest always kept, the rest overflow
    assert len(overflow) == 4


def test_turn_message_layers_in_order():
    msg = build_turn_message("earlier stuff", [Turn("hi", "hello")], "SNAP", "how much PLA?")
    order = [msg.index(tag) for tag in ("<conversation_summary>", "<recent_turns>", "<workspace_snapshot>", "<question>")]
    assert order == sorted(order)


def test_snapshot_text():
    text = snapshot_text(
        {
            "as_of": "2026-10-18",
            "slot_count": 2,
            "spools": [
                {"id": 4, "slot": 1, "color_name": "blue", "brand": "Polymaker", "material": "PETG",
                 "remaining_g": 600.0, "initial_g": 750.0, "pct_left": 80}
            ],
        }
    )
    assert "spool #4 in slot 1: blue Polymaker PETG, 600 g left of 750 g (80%)" in text


def test_compact_json_truncates():
    out = compact_json({"x": "y" * 100}, max_chars=50)
    assert len(out) < 120 and "truncated" in out
