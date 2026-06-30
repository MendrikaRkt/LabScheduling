"""Use case: run the complete end-to-end scheduling workflow.

Application entry point that assembles the dependencies (configuration, engine,
services) and returns a result usable by the presentation layer. It is the
clean replacement of the former monolithic `run_pipeline(df)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from application.services.credit_system import CreditSystem
from application.services.scheduler_service import SchedulerService, SchedulingResult
from domain.entities.group import Group
from domain.entities.professor import Professor
from infrastructure.config.config_loader import AppSettings, get_settings
from infrastructure.errors import SolverError
from infrastructure.logging_config import get_logger
from infrastructure.solver.solver_engine import CPSATSolver

logger = get_logger(__name__)


@dataclass
class RunSchedulingUseCase:
    """Assembles and runs the scheduling."""
    settings: Optional[AppSettings] = None

    def __post_init__(self):
        if self.settings is None:
            self.settings = get_settings()
        self.credit_system = CreditSystem(self.settings.sessions_per_credit)
        self.solver = CPSATSolver(self.settings)
        self.service = SchedulerService(self.solver, self.credit_system)

    def execute(self, groups: List[Group], professors: List[Professor],
                tolerance: int = 0) -> SchedulingResult:
        if not groups:
            raise ValueError("No group to schedule.")
        logger.info("Executing scheduling: %d groups, %d professors",
                    len(groups), len(professors))
        try:
            result = self.service.schedule(groups, professors, tolerance)
        except Exception as exc:
            logger.exception("Scheduling failed: %s", exc)
            raise SolverError(str(exc)) from exc
        logger.info("Scheduling completed: status=%s", result.status)
        return result

    def export_excel(self, path: str, result: SchedulingResult,
                    groups: List[Group], professors: List[Professor]) -> str:
        # local import to avoid a hard dependency on openpyxl when unused
        from infrastructure.excel.excel_generator import ExcelGenerator
        generator = ExcelGenerator(self.credit_system, self.settings.days)
        return generator.generate(path, groups, result.sessions, professors)
