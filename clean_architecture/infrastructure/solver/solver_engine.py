"""solver_engine.py - CP-SAT optimization engine.

Implements the SchedulingSolver interface of the application layer using
OR-Tools CP-SAT. It decides the WEEK of each LabSession while satisfying the
hard constraints (via ConstraintManager) and minimizing a multi-criteria
objective:

  - start anchoring : first sessions close to min_week
  - end anchoring   : last sessions close to max_week
  - even spacing between the sessions of a group
  - parity (soft) + reservations (soft)

It fully separates the CP-SAT logic from the rest of the application: another
engine can be substituted by implementing the same `solve()` interface.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from ortools.sat.python import cp_model

from domain.entities.group import Group, LabSession
from infrastructure.config.config_loader import AppSettings
from infrastructure.solver.constraint_manager import ConstraintManager


@dataclass
class SolveResult:
    """Result of a solve over one or several semesters."""
    sessions: List[LabSession]
    status: str
    objective_value: float = 0.0
    runs: List[dict] = field(default_factory=list)

    @property
    def is_feasible(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


class CPSATSolver:
    """CP-SAT engine for assigning session weeks."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    def _configure(self, solver: cp_model.CpSolver) -> None:
        s = self.settings.solver
        solver.parameters.random_seed = s.random_seed
        solver.parameters.relative_gap_limit = s.relative_gap
        solver.parameters.max_time_in_seconds = s.time_limit_seconds
        solver.parameters.num_search_workers = s.num_workers
        solver.parameters.log_search_progress = s.log_progress

    def solve_groups(self, groups: List[Group]) -> SolveResult:
        """Builds the sessions from the groups then solves per semester."""
        all_sessions: List[LabSession] = []
        sid = 0
        for g in groups:
            built = g.build_sessions(start_id=sid)
            all_sessions.extend(built)
            sid += len(built)
        return self.solve(all_sessions)

    def solve(self, sessions: List[LabSession]) -> SolveResult:
        by_sem: Dict[int, List[LabSession]] = defaultdict(list)
        for s in sessions:
            # infer the semester from the subject code prefix (S1_/S2_)
            sem = 2 if s.subject.startswith("S2_") else 1
            by_sem[sem].append(s)

        all_solved: List[LabSession] = []
        runs: List[dict] = []
        overall_status = "OPTIMAL"

        for sem in sorted(by_sem):
            sem_sessions = by_sem[sem]
            status, obj = self._solve_semester(sem, sem_sessions)
            runs.append({"semester": sem, "n_sessions": len(sem_sessions),
                        "status": status, "objective": obj})
            all_solved.extend(sem_sessions)
            if status == "INFEASIBLE":
                overall_status = "INFEASIBLE"
            elif status == "FEASIBLE" and overall_status != "INFEASIBLE":
                overall_status = "FEASIBLE"

        return SolveResult(sessions=all_solved, status=overall_status, runs=runs)

    def _solve_semester(self, semester: int, sessions: List[LabSession]):
        model = cp_model.CpModel()
        cm = ConstraintManager(model, self.settings, semester)
        week_vars = cm.create_week_variables(sessions)

        cm.add_no_same_subject_slot(sessions)
        by_room_slot = cm.add_no_same_room_slot(sessions)
        cm.add_chronological_order(sessions)
        resv_terms = cm.add_reservation_penalties(by_room_slot)
        parity_terms = cm.add_parity_penalties(sessions)

        objective_terms = self._build_objective(model, sessions, week_vars,
                                                resv_terms, parity_terms)
        model.Minimize(sum(objective_terms))

        solver = cp_model.CpSolver()
        self._configure(solver)
        status_code = solver.Solve(model)
        status = solver.StatusName(status_code)

        if status in ("OPTIMAL", "FEASIBLE"):
            for s in sessions:
                s.week = int(solver.Value(week_vars[s.id]))
            return status, solver.ObjectiveValue()
        return status, 0.0

    def _build_objective(self, model, sessions, week_vars, resv_terms, parity_terms):
        w = self.settings.objective_weights
        terms = []

        # Start/end anchoring + even spacing per group
        by_group = defaultdict(list)
        for s in sessions:
            by_group[(s.subject, s.group_num)].append(s)

        for grp in by_group.values():
            grp_sorted = sorted(grp, key=lambda x: x.session_num)
            if not grp_sorted:
                continue
            first, last = grp_sorted[0], grp_sorted[-1]

            # start anchoring: minimize (week_first - min_week)
            start_dev = model.NewIntVar(0, first.window.span, f"sdev_{first.id}")
            model.Add(start_dev >= week_vars[first.id] - first.window.min_week)
            terms.append(start_dev * w.get("anchor_start", 100))

            # end anchoring: minimize (max_week - week_last)
            end_dev = model.NewIntVar(0, last.window.span, f"edev_{last.id}")
            model.Add(end_dev >= last.window.max_week - week_vars[last.id])
            terms.append(end_dev * w.get("anchor_end", 100))

            # even spacing between consecutive sessions
            n = len(grp_sorted)
            if n >= 2:
                ideal_gap = max(1, first.window.span // n)
                for k in range(n - 1):
                    gap_dev = model.NewIntVar(0, first.window.span, f"gap_{grp_sorted[k].id}")
                    diff = week_vars[grp_sorted[k + 1].id] - week_vars[grp_sorted[k].id]
                    model.Add(gap_dev >= diff - ideal_gap)
                    model.Add(gap_dev >= ideal_gap - diff)
                    terms.append(gap_dev * w.get("even_spacing", 200))

        for t in parity_terms:
            terms.append(t * w.get("parity", 50))
        for t in resv_terms:
            terms.append(t * w.get("reservation", 100000))

        return terms if terms else [model.NewConstant(0)]
