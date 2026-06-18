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
