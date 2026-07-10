"""
Tests for schedule_validation and validation_sheet.

These are read-only, additive validation utilities. The tests exercise the
report structure, the hard/indicator classification, the proportional scoring,
and the Excel sheet builder — without touching any generation logic.
"""

import os
import sys

import pytest
from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schedule_validation as sv  # noqa: E402
import validation_sheet as vs  # noqa: E402


@pytest.fixture(scope="module")
def report():
    return sv.validate_schedule()


def test_report_has_expected_keys(report):
    for key in ("status", "reliability_score", "checks", "counts",
                "teacher_load", "solver", "reliability_formula"):
        assert key in report


def test_status_is_valid(report):
    assert report["status"] in ("PASS", "WARN", "FAIL", "NO_DATA")


def test_score_in_range(report):
    assert 0.0 <= report["reliability_score"] <= 100.0


def test_hard_and_indicator_checks_present(report):
    checks = report["checks"]
    for hard in ("room_conflicts", "student_theory_conflicts",
                 "student_lab_double_booking"):
        assert hard in checks
        assert checks[hard].get("kind") == "hard"
    for indic in ("professor_double_booking", "professor_busy"):
        assert indic in checks
        assert checks[indic].get("kind") == "indicator"


def test_indicator_never_forces_fail(report):
    # If only indicator checks fail (no hard violation), status must not be FAIL.
    checks = report["checks"]
    hard_fail = any(
        not checks[n].get("passed", True)
        for n in ("room_conflicts", "student_theory_conflicts",
                  "student_lab_double_booking")
        if checks[n].get("checkable", True)
    )
    if not hard_fail:
        assert report["status"] != "FAIL"


def test_room_conflicts_have_totals(report):
    chk = report["checks"]["room_conflicts"]
    assert "affected" in chk and "total" in chk
    assert chk["affected"] <= chk["total"] or chk["total"] == 0


def test_build_validation_sheet_creates_tab(report):
    wb = Workbook()
    wb.remove(wb.active)
    ws = vs.build_validation_sheet(wb, report)
    assert ws.title == "Validation"
    assert ws["A1"].value == "Schedule validation and reliability"
    assert ws.max_row > 10


def test_build_validation_sheet_custom_title(report):
    wb = Workbook()
    wb.remove(wb.active)
    ws = vs.build_validation_sheet(wb, report, sheet_title="Fiabilidad")
    assert ws.title == "Fiabilidad"


def test_effective_busy_context_available():
    ctx = sv.build_effective_busy_context()
    # Context should either build successfully or degrade gracefully.
    assert "available" in ctx
    if ctx["available"]:
        assert 1 in ctx["student_busy_sem"]
        assert 2 in ctx["student_busy_sem"]
