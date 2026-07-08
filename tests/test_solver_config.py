"""Tests du paramétrage et du warm-start du solveur (Étapes 6.4 / 6.5)."""

from ortools.sat.python import cp_model

import pipeline


def test_configure_solver_sets_reproducible_params():
    solver = cp_model.CpSolver()
    pipeline.configure_solver(solver, time_limit=10)
    p = solver.parameters
    assert p.random_seed == pipeline.RANDOM_SEED
    assert abs(p.relative_gap_limit - pipeline.SOLVER_RELATIVE_GAP) < 1e-9
    assert p.max_time_in_seconds == 10
    assert p.num_search_workers == 8


def test_configure_solver_default_time_limit():
    solver = cp_model.CpSolver()
    pipeline.configure_solver(solver)
    assert solver.parameters.max_time_in_seconds == pipeline.SOLVER_TIME_LIMIT


def _toy_sessions():
    return [
        {"id": "s1", "subject": "X", "grupo": 1, "session": 1,
         "min_week": 1, "max_week": 10},
        {"id": "s2", "subject": "X", "grupo": 1, "session": 2,
         "min_week": 1, "max_week": 10},
        {"id": "s3", "subject": "X", "grupo": 1, "session": 3,
         "min_week": 1, "max_week": 10},
    ]


def test_add_week_hints_counts_and_is_nonbinding():
    model = cp_model.CpModel()
    sessions = _toy_sessions()
    week_vars = {
        s["id"]: model.NewIntVar(s["min_week"], s["max_week"], s["id"])
        for s in sessions
    }
    n_hints = pipeline.add_week_hints(model, week_vars, sessions)
    assert n_hints == 3
    # Les hints ne doivent pas rendre le modèle infaisable : on ajoute l'ordre
    # chronologique (C5) et on résout.
    for k in range(len(sessions) - 1):
        model.Add(week_vars[sessions[k + 1]["id"]]
                  > week_vars[sessions[k]["id"]])
    solver = cp_model.CpSolver()
    pipeline.configure_solver(solver, time_limit=5)
    status = solver.Solve(model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_record_solver_run_appends_entry():
    pipeline.SOLVER_RUNS.clear()
    model = cp_model.CpModel()
    x = model.NewIntVar(0, 5, "x")
    model.Add(x == 3)
    model.Maximize(x)
    solver = cp_model.CpSolver()
    pipeline.configure_solver(solver, time_limit=5)
    status = solver.Solve(model)
    entry = pipeline.record_solver_run(1, "test", status, solver, n_sessions=1)
    assert entry["semester"] == 1
    assert entry["status"] in ("OPTIMAL", "FEASIBLE")
    assert len(pipeline.SOLVER_RUNS) == 1
    pipeline.SOLVER_RUNS.clear()


def test_diagnose_infeasibility_flags_oversubscribed_slot():
    # 5 séances qui exigent la même salle/même créneau mais seulement 2 semaines
    # disponibles -> goulot SALLE détecté.
    sessions = [
        {"id": f"s{i}", "subject": "X", "grupo": i, "session": 1,
         "day_idx": 0, "block_id": "b1", "lab_rooms": "Lab Z",
         "min_week": 1, "max_week": 2}
        for i in range(5)
    ]
    bottlenecks = pipeline.diagnose_infeasibility(sessions, sem=1,
                                                  sem_holidays=set(),
                                                  label="test")
    assert any(b["kind"] == "SALLE" for b in bottlenecks)
    worst = bottlenecks[0]
    assert worst["needed"] > worst["capacity"]



# ---------------------------------------------------------------------------
# Phase 2 — configurable soft-constraint system (module solver_config)
# ---------------------------------------------------------------------------
import solver_config as sc


def test_default_config_is_valid_and_balanced():
    assert sc.validate_config(sc.DEFAULT_CONFIG) == []
    assert sc.detect_profile(sc.DEFAULT_CONFIG) == "Balanced"


def test_default_weights_match_historical_pipeline_values():
    # Backward compatibility: defaults must reproduce hard-coded pipeline values.
    cfg = sc.DEFAULT_CONFIG
    assert sc.get_weight(cfg, "semester_anchor_first") == 100
    assert sc.get_weight(cfg, "semester_anchor_last") == 100
    assert sc.get_weight(cfg, "spacing") == 200
    assert sc.get_weight(cfg, "parity") == 50


def test_apply_profile_strict_and_relaxed():
    strict = sc.apply_profile("Strict")
    relaxed = sc.apply_profile("Relaxed")
    assert sc.get_weight(strict, "spacing") == 500
    assert sc.detect_profile(strict) == "Strict"
    # Relaxed disables spacing/parity -> effective weight 0.
    assert sc.is_enabled(relaxed, "spacing") is False
    assert sc.get_weight(relaxed, "spacing") == 0


def test_apply_profile_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        sc.apply_profile("DoesNotExist")


def test_get_weight_zero_when_disabled():
    cfg = {"active_profile": "Custom",
           "soft_constraints": {
               "semester_anchor_first": {"enabled": False, "weight": 999},
               "semester_anchor_last": {"enabled": True, "weight": 100},
               "spacing": {"enabled": True, "weight": 200},
               "parity": {"enabled": True, "weight": 50}}}
    assert sc.get_weight(cfg, "semester_anchor_first") == 0
    assert sc.is_enabled(cfg, "semester_anchor_first") is False


def test_validate_config_flags_bad_weight_and_flag():
    bad = {"active_profile": "Balanced",
           "soft_constraints": {
               "semester_anchor_first": {"enabled": "yes", "weight": -5},
               "semester_anchor_last": {"enabled": True, "weight": 100},
               "spacing": {"enabled": True, "weight": 200},
               "parity": {"enabled": True, "weight": 50}}}
    errors = sc.validate_config(bad)
    assert any("enabled" in e for e in errors)
    assert any("weight" in e for e in errors)


def test_validate_config_flags_unknown_profile_and_missing_key():
    bad = {"active_profile": "Nope", "soft_constraints": {"spacing": {"weight": 1}}}
    errors = sc.validate_config(bad)
    assert any("active_profile" in e for e in errors)
    assert any("Missing soft constraint" in e for e in errors)


def test_load_config_missing_file_returns_default(tmp_path):
    missing = str(tmp_path / "no_such.yaml")
    cfg = sc.load_config(missing)
    assert sc.validate_config(cfg) == []
    assert sc.detect_profile(cfg) == "Balanced"


def test_save_and_reload_roundtrip(tmp_path):
    target = str(tmp_path / "solver_constraints.yaml")
    strict = sc.apply_profile("Strict")
    sc.save_config(strict, target)
    reloaded = sc.load_config(target)
    assert sc.detect_profile(reloaded) == "Strict"
    assert sc.get_weight(reloaded, "spacing") == 500


def test_save_invalid_config_raises(tmp_path):
    import pytest
    target = str(tmp_path / "bad.yaml")
    bad = {"active_profile": "Balanced", "soft_constraints": {}}
    with pytest.raises(ValueError):
        sc.save_config(bad, target)


def test_config_summary_shape_and_extreme_detection():
    cfg = sc.apply_profile("Balanced")
    summary = sc.config_summary(cfg)
    assert set(summary["weights"]) == set(sc.SOFT_CONSTRAINT_KEYS)
    assert summary["active_profile"] == "Balanced"
    # All disabled -> extreme warning.
    all_off = {"active_profile": "Custom",
               "soft_constraints": {
                   k: {"enabled": False, "weight": 0}
                   for k in sc.SOFT_CONSTRAINT_KEYS}}
    assert sc.is_extreme(all_off)


def test_load_config_partial_file_merges_defaults(tmp_path):
    import yaml
    target = str(tmp_path / "partial.yaml")
    with open(target, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"soft_constraints":
                        {"spacing": {"enabled": True, "weight": 321}}}, fh)
    cfg = sc.load_config(target)
    # Overridden value kept, missing ones filled from defaults.
    assert sc.get_weight(cfg, "spacing") == 321
    assert sc.get_weight(cfg, "parity") == 50
