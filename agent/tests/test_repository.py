import pytest

from filament_agent.repository import color_name


def remaining(service):
    return {s.id: s.remaining_g for s in service.list_spools(include_archived=True).spools}


def test_remaining_matches_sql_view_math(service):
    # initial - counted prints - adjustments; ignored and unassigned prints don't count
    assert remaining(service) == {1: 507.5, 2: 209.7, 3: 60.0, 4: 600.0, 5: 0.0}


def test_list_spools_hides_archived_by_default(service):
    assert [s.id for s in service.list_spools().spools] == [4, 3, 2, 1]


@pytest.mark.parametrize(
    "grams, kwargs, verdict, best",
    [
        (180, {"material": "petg"}, "yes", 4),
        (200, {"spool_id": 2}, "tight", 2),  # 209.7 >= 200 but < 220 (10% margin)
        (250, {"spool_id": 2}, "no", 2),
        (56, {"color": "red"}, "tight", 3),  # 60 g left, needs 61.6 with margin
        (900, {}, "no", 4),  # best = most filament left
    ],
)
def test_feasibility(service, grams, kwargs, verdict, best):
    f = service.check_feasibility(grams, **kwargs)
    assert (f.verdict, f.best_spool_id) == (verdict, best)


def test_feasibility_no_match_and_archived_ignored(service):
    assert service.check_feasibility(10, material="TPU").verdict == "no_matching_spool"
    assert 5 not in [c.spool_id for c in service.check_feasibility(10, material="PETG").candidates]


def test_feasibility_rejects_bad_grams(service):
    with pytest.raises(ValueError):
        service.check_feasibility(0)


def test_usage_summary_window(service):
    u = service.usage_summary(30)
    assert u.total_used_g == 1177.8
    assert u.print_count == 9
    red = next(s for s in u.spools if s.spool_id == 3)
    assert red.used_in_window_g == 190
    assert red.days_until_empty == pytest.approx(60 / red.avg_g_per_day, abs=0.1)


def test_log_print_charges_loaded_spool(service):
    r = service.log_print("Test clip", 12.5, slot=1)
    assert r.ok and r.spool.id == 1
    assert remaining(service)[1] == 495.0


def test_log_print_validates_slot(service):
    with pytest.raises(ValueError):
        service.log_print("x", 5, slot=9)


def test_correct_spool_sets_exact_value(service):
    r = service.correct_spool(2, 150)
    assert r.spool.remaining_g == 150
    assert remaining(service)[2] == 150


def test_correct_unknown_spool(service):
    with pytest.raises(LookupError):
        service.correct_spool(99, 10)


def test_color_name():
    assert color_name("#000000") == "black"
    assert color_name("#1E5ADC") == "blue"
    assert color_name("Galaxy Black") == "galaxy black"
