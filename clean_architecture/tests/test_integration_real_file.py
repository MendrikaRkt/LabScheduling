"""Optional integration test on the real Asignacion_2025-2026_v5.xlsx file.

Automatically skipped if the source file is not present (CI without data).

The file is searched in several portable locations so the test works both in
the original sandbox and in a local clone of the LabScheduling repository:
  - the LABSCHEDULING_ASSIGNMENT_FILE environment variable (highest priority)
  - the repository ``data/`` folder (two levels above this test file)
  - the repository root
  - the legacy sandbox upload path
"""
import os

import pytest

from infrastructure.config.config_loader import get_settings
from infrastructure.excel.excel_reader import ExcelReader, SubjectMatcher

_FILE_NAME = "Asignacion_2025-2026_v5.xlsx"
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _resolve_real_file() -> str:
    """Return the first existing candidate path for the assignment file."""
    candidates = [
        os.environ.get("LABSCHEDULING_ASSIGNMENT_FILE", ""),
        os.path.join(_REPO_ROOT, "data", _FILE_NAME),
        os.path.join(_REPO_ROOT, _FILE_NAME),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", _FILE_NAME),
        f"/home/ubuntu/Uploads/{_FILE_NAME}",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


REAL_FILE = _resolve_real_file()
pytestmark = pytest.mark.skipif(
    not REAL_FILE, reason="source file not available")


def test_real_file_loads_lab_subjects():
    settings = get_settings()
    matcher = SubjectMatcher.from_settings(settings)
    reader = ExcelReader(settings.sessions_per_credit)
    profs = reader.read_professor_credits(REAL_FILE, subject_matcher=matcher)
    # At least about twenty teachers with P credits
    assert len(profs) >= 20
    # Expected sessions must be positive integers
    subjects = {s for p in profs for s in p.subjects()}
    assert len(subjects) >= 15


def test_real_file_mecanismos_six_credits():
    settings = get_settings()
    matcher = SubjectMatcher.from_settings(settings)
    reader = ExcelReader(settings.sessions_per_credit)
    profs = reader.read_professor_credits(REAL_FILE, subject_matcher=matcher)
    total_p = sum(p.practice_credits("S1_Mecanismos") for p in profs)
    # Mecanismos = 6 P credits in total => 30 expected sessions
    assert round(total_p) == 6
