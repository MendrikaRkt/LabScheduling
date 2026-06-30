"""validation_report.py - Generation of inconsistency reports.

Centralizes, in a structured format usable by the UI, every inconsistency
detected during a scheduling run:

  - residual hard conflicts (C1, C4, C5, students) via ConflictDetector,
  - load gaps (overload / underload) credits vs sessions,
  - quality alerts (unscheduled sessions, professors without assignment).

The report assigns a SEVERITY to each entry (ERROR / WARNING / INFO) and
provides synthetic views (counters) and detailed views (rows) ready for the
monitoring dashboard.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List

from application.services.scheduler_service import SchedulingResult

# Normalized severities
SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

SEVERITY_TAG = {
    SEVERITY_ERROR: "[ERROR]",
    SEVERITY_WARNING: "[WARN]",
    SEVERITY_INFO: "[INFO]",
}


@dataclass
class ValidationIssue:
    """A single inconsistency detected in the schedule."""
    severity: str          # ERROR / WARNING / INFO
    category: str          # e.g. "Conflict C1", "Credit overload"
    message: str
    detail: str = ""

    @property
    def tag(self) -> str:
        return SEVERITY_TAG.get(self.severity, "[-]")


@dataclass
class ValidationReport:
    """Full inconsistency report with summary counters."""
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == SEVERITY_ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == SEVERITY_WARNING)

    @property
    def infos(self) -> int:
        return sum(1 for i in self.issues if i.severity == SEVERITY_INFO)

    @property
    def total(self) -> int:
        return len(self.issues)

    @property
    def is_clean(self) -> bool:
        return self.errors == 0 and self.warnings == 0

    def by_category(self) -> Dict[str, int]:
        return dict(Counter(i.category for i in self.issues))

    def by_severity(self) -> Dict[str, int]:
        return {
            SEVERITY_ERROR: self.errors,
            SEVERITY_WARNING: self.warnings,
            SEVERITY_INFO: self.infos,
        }


class ValidationReportBuilder:
    """Builds a ValidationReport from a SchedulingResult."""

    # conflict -> severity mapping (hard conflicts are errors)
    _CONFLICT_SEVERITY = {
        "C1": SEVERITY_ERROR,
        "C4": SEVERITY_ERROR,
        "C5": SEVERITY_ERROR,
        "STUDENT": SEVERITY_ERROR,
    }

    def build(self, result: SchedulingResult) -> ValidationReport:
        report = ValidationReport()

        # 1. global solver status
        if result.status == "INFEASIBLE":
            report.issues.append(ValidationIssue(
                SEVERITY_ERROR, "Solver",
                "The model is INFEASIBLE: no solution satisfies the hard "
                "constraints.",
                "Relax some constraints or widen the windows."))
        elif result.status == "FEASIBLE":
            report.issues.append(ValidationIssue(
                SEVERITY_INFO, "Solver",
                "FEASIBLE solution found (not proven optimal).",
                "Increase the time limit to aim for the optimum."))

        # 2. residual hard conflicts
        for c in result.conflicts:
            sev = self._CONFLICT_SEVERITY.get(c.kind, SEVERITY_WARNING)
            report.issues.append(ValidationIssue(
                sev, f"Conflict {c.kind}", c.description,
                f"Sessions involved: {c.session_ids}"))

        # 3. load gaps (official credits vs planned sessions)
        for d in result.discrepancies:
            if d.is_overload:
                report.issues.append(ValidationIssue(
                    SEVERITY_WARNING, "Credit overload",
                    f"{d.professor} - {d.subject}: +{d.delta} session(s)",
                    f"Expected {d.expected_sessions}, planned {d.planned_sessions}"))
            elif d.is_underload:
                report.issues.append(ValidationIssue(
                    SEVERITY_WARNING, "Credit underload",
                    f"{d.professor} - {d.subject}: {d.delta} session(s)",
                    f"Expected {d.expected_sessions}, planned {d.planned_sessions}"))

        # 4. unscheduled sessions
        unscheduled = [s for s in result.sessions if not s.is_scheduled]
        if unscheduled:
            report.issues.append(ValidationIssue(
                SEVERITY_ERROR, "Unscheduled sessions",
                f"{len(unscheduled)} session(s) without an assigned week.",
                "Check the week windows and the holidays."))

        # 5. sessions without an assigned professor
        no_prof = [s for s in result.sessions
                if not getattr(s, "professor", None)]
        if no_prof:
            report.issues.append(ValidationIssue(
                SEVERITY_WARNING, "Sessions without professor",
                f"{len(no_prof)} session(s) without a responsible professor.",
                "Check the professors' P credits for these subjects."))

        return report

    def to_rows(self, report: ValidationReport) -> List[dict]:
        """Rows ready for a table (dataframe)."""
        return [{
            "Severity": f"{i.tag} {i.severity}",
            "Category": i.category,
            "Message": i.message,
            "Detail": i.detail,
        } for i in report.issues]
