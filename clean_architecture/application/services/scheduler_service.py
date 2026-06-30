"""SchedulerService - scheduling orchestration.

Central application service that coordinates the other components WITHOUT
depending on their concrete implementations (dependency injection). It:

  1. resolves the weeks of the sessions (through an injected CP-SAT engine),
  2. allocates groups to professors in proportion to their P credits,
  3. detects residual conflicts,
  4. validates the consistency of credits vs planned sessions.

The professor-to-group allocation proportional to P credits is the core of the
fair workload distribution.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Protocol

from application.services.conflict_detector import Conflict, ConflictDetector
from application.services.credit_system import (
    AssignmentReporter,
    AssignmentStats,
    CreditDiscrepancy,
    CreditSystem,
    CreditValidator,
)
from domain.entities.group import Group, LabSession
from domain.entities.professor import Professor

logger = logging.getLogger(__name__)


class SchedulingSolver(Protocol):
    """Port (interface) that any optimization engine must implement."""

    def solve_groups(self, groups: List[Group]):  # -> SolveResult
        ...


@dataclass
class SchedulingResult:
    sessions: List[LabSession]
    status: str
    conflicts: List[Conflict] = field(default_factory=list)
    discrepancies: List[CreditDiscrepancy] = field(default_factory=list)
    runs: List[dict] = field(default_factory=list)
    report_lines: List[str] = field(default_factory=list)
    assignment_stats: AssignmentStats = field(default_factory=AssignmentStats)

    @property
    def is_valid(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE") and not self.conflicts


class SchedulerService:
    def __init__(self, solver: SchedulingSolver, credit_system: CreditSystem):
        self.solver = solver
        self.credit_system = credit_system
        self.conflict_detector = ConflictDetector()
        self.credit_validator = CreditValidator(credit_system)
        self.reporter = AssignmentReporter(credit_system)

    def schedule(self, groups: List[Group], professors: List[Professor],
                tolerance: int = 0) -> SchedulingResult:
        # 1. resolve the weeks
        result = self.solver.solve_groups(groups)
        sessions = result.sessions

        # 2. professor -> group allocation proportional to P credits
        #    (ONE responsible professor per group, hence per session)
        self.allocate_professors(groups, sessions, professors)

        # 3. residual conflicts
        conflicts = self.conflict_detector.detect(sessions)

        # 4. validation of credits vs planned sessions
        planned = self._planned_sessions(sessions)
        discrepancies = self.credit_validator.validate(professors, planned, tolerance)

        # 5. validation report (logs): expected vs assigned, overloads
        report_lines = self.reporter.log_report(professors, planned)
        stats = self.reporter.stats(professors, planned)

        return SchedulingResult(
            sessions=sessions, status=result.status, conflicts=conflicts,
            discrepancies=discrepancies, runs=getattr(result, "runs", []),
            report_lines=report_lines, assignment_stats=stats,
        )

    def allocate_professors(self, groups: List[Group], sessions: List[LabSession],
                            professors: List[Professor]) -> None:
        """Allocates each group of a subject to a professor while respecting the
        proportion of P credits (quota = expected sessions per professor).

        Algorithm: for each subject, compute every professor's session quota
        (P credits x N); assign groups to professors by filling the quotas (the
        professor with the largest remaining deficit receives the next group).
        This bounds overloads and corrects the gaps.
        """
        # session quota per (subject, professor)
        prof_by_subject: Dict[str, List[Professor]] = defaultdict(list)
        for p in professors:
            for subj in p.subjects():
                prof_by_subject[subj].append(p)

        sessions_by_group: Dict[tuple, List[LabSession]] = defaultdict(list)
        for s in sessions:
            sessions_by_group[(s.subject, s.group_num)].append(s)

        groups_by_subject: Dict[str, List[Group]] = defaultdict(list)
        for g in groups:
            groups_by_subject[g.subject].append(g)

        for subject, subj_groups in groups_by_subject.items():
            profs = prof_by_subject.get(subject, [])
            if not profs:
                continue
            # remaining deficit (expected sessions still to be filled)
            remaining = {p.name: p.expected_sessions(subject,
                        self.credit_system.sessions_per_credit) for p in profs}

            for g in sorted(subj_groups, key=lambda x: x.group_num):
                # professor with the largest remaining deficit
                best = max(profs, key=lambda p: remaining[p.name])
                g.professor = best.name
                grp_sessions = sessions_by_group.get(g.key, [])
                for s in grp_sessions:
                    s.professor = best.name  # type: ignore[attr-defined]
                remaining[best.name] -= len(grp_sessions) or g.num_sessions

    @staticmethod
    def _planned_sessions(sessions: List[LabSession]) -> Dict[tuple, int]:
        planned: Dict[tuple, int] = defaultdict(int)
        for s in sessions:
            prof = getattr(s, "professor", None)
            if prof:
                planned[(prof, s.subject)] += 1
        return planned
