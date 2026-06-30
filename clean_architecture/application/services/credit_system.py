"""credit_system.py - Professor credit system.

Encapsulates the business rule "1 P credit = N sessions" and provides the
validation of gaps between the EXPECTED load (official credits) and the PLANNED
load (sessions actually allocated). This is the component that detects load
inconsistencies between professors and their assignments.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List

from domain.entities.professor import Professor
from domain.rules import DEFAULT_SESSIONS_PER_CREDIT, credits_to_sessions

logger = logging.getLogger(__name__)


@dataclass
class CreditDiscrepancy:
    """Gap between expected and planned sessions for a (professor, subject)."""
    professor: str
    subject: str
    expected_sessions: int
    planned_sessions: int

    @property
    def delta(self) -> int:
        return self.planned_sessions - self.expected_sessions

    @property
    def is_overload(self) -> bool:
        return self.delta > 0

    @property
    def is_underload(self) -> bool:
        return self.delta < 0

    @property
    def is_balanced(self) -> bool:
        return self.delta == 0


class CreditSystem:
    """Computes expected loads from the official P credits."""

    def __init__(self, sessions_per_credit: int = DEFAULT_SESSIONS_PER_CREDIT):
        if sessions_per_credit <= 0:
            raise ValueError("sessions_per_credit must be > 0")
        self.sessions_per_credit = sessions_per_credit

    def expected_sessions(self, practice_credits: float) -> int:
        return credits_to_sessions(practice_credits, self.sessions_per_credit)

    def expected_by_professor(self, professors: List[Professor]) -> Dict[tuple, int]:
        """Returns {(professor, subject): expected_sessions}."""
        result: Dict[tuple, int] = {}
        for prof in professors:
            for subject, credits in prof.practice_credits_by_subject.items():
                result[(prof.name, subject)] = self.expected_sessions(credits)
        return result

    def quota(self, professor: Professor, subject: str) -> int:
        """Session quota of a professor for a subject (= P credits x N)."""
        return self.expected_sessions(professor.practice_credits(subject))


class CreditValidator:
    """Compares the expected load to the planned load and lists the gaps."""

    def __init__(self, credit_system: CreditSystem):
        self.credit_system = credit_system

    def validate(self, professors: List[Professor],
                planned_sessions: Dict[tuple, int],
                tolerance: int = 0) -> List[CreditDiscrepancy]:
        """Detects the gaps.

        Args:
            professors: list of professors with their P credits.
            planned_sessions: {(prof_name, subject): nb_planned_sessions}.
            tolerance: absolute gap tolerated without being reported.

        Returns:
            List of gaps where |delta| > tolerance, sorted by |delta| desc.
        """
        expected = self.credit_system.expected_by_professor(professors)

        # Union of expected and planned keys
        keys = set(expected) | set(planned_sessions)
        discrepancies: List[CreditDiscrepancy] = []
        for (prof, subject) in keys:
            exp = expected.get((prof, subject), 0)
            plan = planned_sessions.get((prof, subject), 0)
            disc = CreditDiscrepancy(prof, subject, exp, plan)
            if abs(disc.delta) > tolerance:
                discrepancies.append(disc)

        discrepancies.sort(key=lambda d: abs(d.delta), reverse=True)
        return discrepancies

    def summary(self, discrepancies: List[CreditDiscrepancy]) -> Dict[str, int]:
        """Synthetic KPIs of the detected gaps."""
        return {
            "total": len(discrepancies),
            "overloads": sum(1 for d in discrepancies if d.is_overload),
            "underloads": sum(1 for d in discrepancies if d.is_underload),
            "max_overload": max((d.delta for d in discrepancies), default=0),
            "max_underload": min((d.delta for d in discrepancies), default=0),
        }


@dataclass
class AssignmentStats:
    """Global statistics of the professor assignment."""
    professors: int = 0
    pairs: int = 0                 # number of (professor, subject) pairs
    expected_total: int = 0        # expected sessions (credits x N)
    assigned_total: int = 0        # sessions actually assigned
    balanced: int = 0
    overloaded: int = 0
    underloaded: int = 0
    max_overload: int = 0
    max_underload: int = 0


class AssignmentReporter:
    """Produces a readable validation report of the professor assignment.

    For each (professor, subject) pair, it compares:
      - the EXPECTED sessions (official P credits x sessions_per_credit),
      - the ASSIGNED sessions in the schedule.
    It detects overloads / underloads and computes global statistics. It backs
    the logs and the "Validation" sheet of the Excel export.
    """

    def __init__(self, credit_system: CreditSystem):
        self.credit_system = credit_system

    def build_rows(self, professors: List[Professor],
                assigned: Dict[tuple, int]) -> List[CreditDiscrepancy]:
        """One CreditDiscrepancy row per (professor, subject) pair, sorted."""
        expected = self.credit_system.expected_by_professor(professors)
        keys = set(expected) | set(assigned)
        rows = [
            CreditDiscrepancy(prof, subject,
                            expected.get((prof, subject), 0),
                            assigned.get((prof, subject), 0))
            for (prof, subject) in keys
        ]
        rows.sort(key=lambda d: (d.professor, d.subject))
        return rows

    def stats(self, professors: List[Professor],
            assigned: Dict[tuple, int]) -> AssignmentStats:
        rows = self.build_rows(professors, assigned)
        s = AssignmentStats(
            professors=len({r.professor for r in rows}),
            pairs=len(rows),
            expected_total=sum(r.expected_sessions for r in rows),
            assigned_total=sum(r.planned_sessions for r in rows),
            balanced=sum(1 for r in rows if r.is_balanced),
            overloaded=sum(1 for r in rows if r.is_overload),
            underloaded=sum(1 for r in rows if r.is_underload),
            max_overload=max((r.delta for r in rows), default=0),
            max_underload=min((r.delta for r in rows), default=0),
        )
        return s

    def report_lines(self, professors: List[Professor],
                    assigned: Dict[tuple, int]) -> List[str]:
        """Report text lines (expected vs assigned + overloads)."""
        rows = self.build_rows(professors, assigned)
        s = self.stats(professors, assigned)
        lines: List[str] = []
        lines.append("=" * 72)
        lines.append("VALIDATION REPORT - Professor assignment")
        lines.append("=" * 72)
        lines.append(
            f"Rule: 1 P credit = {self.credit_system.sessions_per_credit} sessions")
        lines.append(
            f"Professors: {s.professors} | (professor, subject) pairs: {s.pairs}")
        lines.append(
            f"Expected sessions: {s.expected_total} | assigned: {s.assigned_total}")
        lines.append(
            f"Balanced: {s.balanced} | Overloaded: {s.overloaded} | "
            f"Underloaded: {s.underloaded}")
        lines.append(
            f"Max overload gap: +{s.max_overload} | "
            f"underload: {s.max_underload}")
        lines.append("-" * 72)
        for r in rows:
            if r.is_balanced:
                tag = "OK   "
            elif r.is_overload:
                tag = "OVER+"
            else:
                tag = "UNDER"
            lines.append(
                f"[{tag}] {r.professor:<32.32} | {r.subject:<28.28} | "
                f"expected {r.expected_sessions:>3} | assigned {r.planned_sessions:>3} | "
                f"d {r.delta:+d}")
        lines.append("=" * 72)
        return lines

    def log_report(self, professors: List[Professor],
                assigned: Dict[tuple, int]) -> List[str]:
        """Emits the report through the logger and returns the lines."""
        lines = self.report_lines(professors, assigned)
        for ln in lines:
            logger.info(ln)
        return lines
