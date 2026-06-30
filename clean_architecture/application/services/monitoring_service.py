"""monitoring_service.py - Collection of the solver metrics.

Cross-cutting application service that INSTRUMENTS the scheduling without
modifying the CP-SAT engine. It provides:

  - the real count of the model's variables and constraints (per semester),
  - the solving time and the objective value,
  - distributions usable by the dashboard (sessions per professor, per day,
    per block, per week).

These metrics feed the `monitoring_dashboard` page and the `preview_sandbox`.
The constraint collection reuses `ConstraintManager` on a throwaway CP-SAT
model: this yields the REAL counters (C1, C4, C5, RESV, PARITY) without
duplicating the business logic.
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from domain.entities.group import Group, LabSession
from domain.entities.professor import Professor
from infrastructure.config.config_loader import AppSettings


@dataclass
class SemesterMetrics:
    """Metrics of a semester (one CP-SAT sub-model per semester)."""
    semester: int
    n_sessions: int = 0
    n_variables: int = 0          # "week" decision variables
    constraints: Dict[str, int] = field(default_factory=dict)
    status: str = ""
    objective: float = 0.0

    @property
    def total_constraints(self) -> int:
        return sum(self.constraints.values())


@dataclass
class SolverMetrics:
    """Overview of the solving metrics."""
    status: str = ""
    elapsed_seconds: float = 0.0
    n_sessions: int = 0
    n_scheduled: int = 0
    n_variables: int = 0
    total_constraints: int = 0
    constraints_by_kind: Dict[str, int] = field(default_factory=dict)
    semesters: List[SemesterMetrics] = field(default_factory=list)
    sessions_per_professor: Dict[str, int] = field(default_factory=dict)
    sessions_per_day: Dict[str, int] = field(default_factory=dict)
    sessions_per_block: Dict[str, int] = field(default_factory=dict)
    sessions_per_week: Dict[int, int] = field(default_factory=dict)

    @property
    def scheduling_rate(self) -> float:
        if self.n_sessions == 0:
            return 0.0
        return round(100.0 * self.n_scheduled / self.n_sessions, 1)


# Human-readable labels of the constraint families
CONSTRAINT_LABELS = {
    "C1": "C1 - Same subject / slot",
    "C4": "C4 - Same room / slot",
    "C5": "C5 - Chronological order",
    "RESV": "RESV - Reserved slots (soft)",
    "PARITY": "PARITY - Even/odd alternation (soft)",
}


class MonitoringService:
    """Instruments the scheduling and aggregates usable metrics."""

    def __init__(self, settings: AppSettings):
        self.settings = settings

    # ---------------------------------------------------------------- timing
    @staticmethod
    def timed_execute(use_case, groups: List[Group], professors: List[Professor],
                    tolerance: int = 0):
        """Runs the use case while measuring the solving time.

        Returns: (result, elapsed_seconds)
        """
        start = time.perf_counter()
        result = use_case.execute(groups, professors, tolerance)
        elapsed = time.perf_counter() - start
        return result, elapsed

    # ----------------------------------------------------- model counting
    def count_model(self, sessions: List[LabSession]) -> List[SemesterMetrics]:
        """Rebuilds the CP-SAT model per semester (without solving it) to count
        the variables and constraints actually posted.
        """
        # local imports: collecting metrics does not impose ortools on the rest
        # of the application if it is not used.
        from ortools.sat.python import cp_model

        from infrastructure.solver.constraint_manager import ConstraintManager

        by_sem: Dict[int, List[LabSession]] = defaultdict(list)
        for s in sessions:
            sem = 2 if s.subject.startswith("S2_") else 1
            by_sem[sem].append(s)

        metrics: List[SemesterMetrics] = []
        for sem in sorted(by_sem):
            sem_sessions = by_sem[sem]
            model = cp_model.CpModel()
            cm = ConstraintManager(model, self.settings, sem)
            week_vars = cm.create_week_variables(sem_sessions)
            cm.add_no_same_subject_slot(sem_sessions)
            by_room_slot = cm.add_no_same_room_slot(sem_sessions)
            cm.add_chronological_order(sem_sessions)
            cm.add_reservation_penalties(by_room_slot)
            cm.add_parity_penalties(sem_sessions)
            metrics.append(SemesterMetrics(
                semester=sem,
                n_sessions=len(sem_sessions),
                n_variables=len(week_vars),
                constraints=dict(cm.counts),
            ))
        return metrics

    # --------------------------------------------------------- final aggregation
    def collect(self, sessions: List[LabSession],
                result=None, elapsed: float = 0.0) -> SolverMetrics:
        """Builds the complete SolverMetrics object from the resolved sessions
        and, if available, the scheduling result.
        """
        sem_metrics = self.count_model(sessions)

        # merge the statuses / objectives from the solver runs
        runs_by_sem = {}
        status = ""
        if result is not None:
            status = getattr(result, "status", "")
            for run in getattr(result, "runs", []) or []:
                runs_by_sem[run.get("semester")] = run
        for m in sem_metrics:
            run = runs_by_sem.get(m.semester)
            if run:
                m.status = run.get("status", "")
                m.objective = float(run.get("objective", 0.0))

        constraints_by_kind: Counter = Counter()
        for m in sem_metrics:
            constraints_by_kind.update(m.constraints)

        # distributions
        per_prof: Counter = Counter()
        per_day: Counter = Counter()
        per_block: Counter = Counter()
        per_week: Counter = Counter()
        n_scheduled = 0
        for s in sessions:
            prof = getattr(s, "professor", None) or "- unassigned"
            per_prof[prof] += 1
            per_day[s.slot.day] += 1
            per_block[s.slot.block_label] += 1
            if s.is_scheduled:
                n_scheduled += 1
                per_week[s.week] += 1

        return SolverMetrics(
            status=status,
            elapsed_seconds=round(elapsed, 3),
            n_sessions=len(sessions),
            n_scheduled=n_scheduled,
            n_variables=sum(m.n_variables for m in sem_metrics),
            total_constraints=sum(constraints_by_kind.values()),
            constraints_by_kind=dict(constraints_by_kind),
            semesters=sem_metrics,
            sessions_per_professor=dict(per_prof.most_common()),
            sessions_per_day=dict(per_day),
            sessions_per_block=dict(per_block),
            sessions_per_week=dict(sorted(per_week.items())),
        )
