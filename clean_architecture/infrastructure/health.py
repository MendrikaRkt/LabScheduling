"""Application health checks.

Provides a deep health check used both by the UI (a status panel) and by
deployment tooling. The check verifies that the critical dependencies are
importable and that the configuration loads correctly, which catches the most
common production misconfigurations early.
"""
from __future__ import annotations

import importlib
import platform
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List

from infrastructure.logging_config import get_logger

logger = get_logger(__name__)

# Process start time, used to report uptime.
_START_TIME = time.time()

# Third-party packages that must be importable for the app to work.
_REQUIRED_PACKAGES = ["streamlit", "ortools", "openpyxl", "pandas", "yaml"]


@dataclass
class HealthCheck:
    """Result of a single named check."""
    name: str
    healthy: bool
    detail: str = ""


@dataclass
class HealthReport:
    """Aggregated health report."""
    status: str = "ok"                       # "ok" or "error"
    uptime_seconds: float = 0.0
    python_version: str = ""
    checks: List[HealthCheck] = field(default_factory=list)

    def to_dict(self) -> Dict:
        data = asdict(self)
        return data


def _check_packages() -> List[HealthCheck]:
    results: List[HealthCheck] = []
    for pkg in _REQUIRED_PACKAGES:
        try:
            importlib.import_module(pkg)
            results.append(HealthCheck(f"package:{pkg}", True, "importable"))
        except Exception as exc:  # pragma: no cover - environment dependent
            results.append(HealthCheck(f"package:{pkg}", False, str(exc)))
    return results


def _check_config() -> HealthCheck:
    try:
        from infrastructure.config.config_loader import get_settings
        settings = get_settings()
        n = len(settings.subjects)
        if n == 0:
            return HealthCheck("config", False, "no subjects loaded")
        return HealthCheck("config", True, f"{n} subjects loaded")
    except Exception as exc:
        return HealthCheck("config", False, str(exc))


def check_health() -> HealthReport:
    """Run all health checks and return an aggregated report."""
    checks: List[HealthCheck] = []
    checks.extend(_check_packages())
    checks.append(_check_config())

    healthy = all(c.healthy for c in checks)
    report = HealthReport(
        status="ok" if healthy else "error",
        uptime_seconds=round(time.time() - _START_TIME, 1),
        python_version=platform.python_version(),
        checks=checks,
    )
    if not healthy:
        failed = [c.name for c in checks if not c.healthy]
        logger.error("Health check failed: %s", ", ".join(failed))
    return report


def is_healthy() -> bool:
    """Return True if all health checks pass."""
    return check_health().status == "ok"
