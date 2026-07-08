"""Tests for the Phase 2 infeasibility simulation engine (simulation_engine.py).

All tests use deterministic synthetic session lists, so they never depend on
real optimisation artifacts and can run in isolation.
"""

import pytest

import simulation_engine as se


def _oversubscribed_sessions():
    """5 sessions competing for the same room/subject slot with only 2 weeks."""
    return [
        {"group_id": f"X|{i}|S1", "subject": "X", "grupo": i,
         "day_idx": 0, "block_id": "b1", "rooms": ["Lab Z"],
         "min_week": 1, "max_week": 2, "nb_students": 10, "session": 1}
        for i in range(5)
    ]


def _feasible_sessions():
    """A single group of 3 chronological sessions with a wide window."""
    return [
        {"group_id": "Y|1|S1", "subject": "Y", "grupo": 1,
         "day_idx": 1, "block_id": "b2", "rooms": ["Lab A"],
         "min_week": 1, "max_week": 10, "nb_students": 8, "session": k}
        for k in range(1, 4)
    ]


def test_make_group_id_stable():
    assert se.make_group_id("Fisica", 2, 1) == "Fisica|2|S1"


def test_analyze_bottlenecks_detects_overflow():
    res = se.analyze_bottlenecks(_oversubscribed_sessions())
    assert res["feasible"] is False
    assert res["n_sessions"] == 5
    assert any(b["kind"] == "SALLE" for b in res["bottlenecks"])
    assert any(b["kind"] == "MATIERE" for b in res["bottlenecks"])
    assert res["total_overflow"] > 0


def test_analyze_bottlenecks_feasible_case():
    res = se.analyze_bottlenecks(_feasible_sessions())
    assert res["feasible"] is True
    assert res["bottlenecks"] == []
    assert res["total_overflow"] == 0


def test_analyze_bottlenecks_sorted_by_overflow():
    res = se.analyze_bottlenecks(_oversubscribed_sessions())
    overflows = [b["overflow"] for b in res["bottlenecks"]]
    assert overflows == sorted(overflows, reverse=True)


def test_validate_sessions_rejects_bad_window():
    bad = [{"group_id": "g", "day_idx": 0, "block_id": "b",
            "min_week": 5, "max_week": 2}]
    with pytest.raises(ValueError):
        se.analyze_bottlenecks(bad)


def test_validate_sessions_missing_key():
    bad = [{"group_id": "g", "day_idx": 0}]  # missing block_id/weeks
    with pytest.raises(ValueError):
        se.analyze_bottlenecks(bad)


def test_simulate_without_groups_becomes_feasible():
    sessions = _oversubscribed_sessions()
    result = se.simulate_without_groups(sessions, ["X|0|S1", "X|1|S1", "X|2|S1"])
    assert result["scenario"] == "exclude_groups"
    assert result["removed_sessions"] == 3
    assert result["affected_students"] == 30
    assert result["diff"]["became_feasible"] is True
    assert result["diff"]["overflow_reduction"] > 0


def test_simulate_without_groups_partial_improvement():
    sessions = _oversubscribed_sessions()
    result = se.simulate_without_groups(sessions, ["X|0|S1"])
    # Removing a single group reduces overflow but not to feasibility.
    assert result["diff"]["overflow_reduction"] > 0
    assert result["diff"]["became_feasible"] is False


def test_simulate_without_groups_does_not_mutate_input():
    sessions = _oversubscribed_sessions()
    n_before = len(sessions)
    se.simulate_without_groups(sessions, ["X|0|S1"])
    assert len(sessions) == n_before


def test_simulate_with_extra_capacity_clears_room_bottleneck():
    sessions = _oversubscribed_sessions()
    extra = [{"resource": "Lab Z", "day_idx": 0, "block_id": "b1", "weeks": 3}]
    result = se.simulate_with_extra_capacity(sessions, extra)
    assert result["scenario"] == "add_capacity"
    assert result["added_capacity"] == 3
    # Room bottleneck cleared -> fewer bottlenecks than before.
    assert result["diff"]["n_bottlenecks_after"] < result["diff"]["n_bottlenecks_before"]


def test_simulate_with_extra_capacity_rejects_bad_slot():
    sessions = _feasible_sessions()
    with pytest.raises(ValueError):
        se.simulate_with_extra_capacity(sessions, [{"resource": "R"}])


def test_simulate_with_extra_capacity_rejects_nonpositive_weeks():
    sessions = _feasible_sessions()
    with pytest.raises(ValueError):
        se.simulate_with_extra_capacity(
            sessions, [{"resource": "R", "day_idx": 0, "block_id": "b", "weeks": 0}])


def test_suggest_actions_ranks_groups_and_resources():
    sessions = _oversubscribed_sessions()
    sug = se.suggest_actions(sessions)
    assert sug["feasible"] is False
    assert len(sug["exclude_groups"]) > 0
    assert len(sug["add_resources"]) > 0
    # add_resources entries carry a positive weeks recommendation.
    assert all(r["weeks"] > 0 for r in sug["add_resources"])


def test_suggest_actions_feasible_returns_no_bottleneck():
    sug = se.suggest_actions(_feasible_sessions())
    assert sug["feasible"] is True
    assert sug["exclude_groups"] == []
    assert sug["add_resources"] == []


def test_dry_run_feasibility_infeasible_and_feasible():
    infeasible = se.dry_run_feasibility(_oversubscribed_sessions(), time_limit=10)
    assert infeasible["status"] in ("INFEASIBLE", "UNAVAILABLE")
    feasible = se.dry_run_feasibility(_feasible_sessions(), time_limit=10)
    assert feasible["status"] in ("OPTIMAL", "FEASIBLE", "UNAVAILABLE")


def test_load_helpers_missing_files_return_empty(tmp_path):
    empty_dir = str(tmp_path)
    assert se.load_unplaced_students(empty_dir) == []
    assert se.load_solver_stats(empty_dir) == []
    assert se.load_bottlenecks_from_reports(empty_dir) == []


def test_load_bottlenecks_parses_infeasibility_report(tmp_path):
    report = tmp_path / "infeasibility_S1_test.txt"
    report.write_text(
        "  [SALLE  ] Lab Z                            Lunes      b1"
        "           : 5 séances / 2 semaines (excès 3)\n"
        "  [MATIÈRE] X                                Lunes      b1"
        "           : 5 séances / 2 semaines (excès 3)\n",
        encoding="utf-8",
    )
    out = se.load_bottlenecks_from_reports(str(tmp_path))
    kinds = {b["kind"] for b in out}
    assert "SALLE" in kinds and "MATIERE" in kinds
    assert any(b["overflow"] == 3 for b in out)
