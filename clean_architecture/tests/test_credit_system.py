"""Tests for the credit system - the most critical business rule."""
import pytest

from application.services.credit_system import (
    CreditDiscrepancy,
    CreditSystem,
    CreditValidator,
)
from domain.entities.professor import Professor
from domain.rules import credits_to_sessions, sessions_to_credits
from domain.value_objects import Credits, CreditType


# --- Rule: 1 P credit = 5 sessions -------------------------------------------
@pytest.mark.parametrize("credits,expected", [(3, 15), (2, 10), (5, 25), (0, 0)])
def test_credits_to_sessions(credits, expected):
    assert credits_to_sessions(credits) == expected


def test_credits_to_sessions_custom_factor():
    assert credits_to_sessions(3, sessions_per_credit=4) == 12


def test_sessions_to_credits_roundtrip():
    assert sessions_to_credits(15) == 3.0


def test_negative_credits_raises():
    with pytest.raises(ValueError):
        credits_to_sessions(-1)


def test_zero_factor_raises():
    with pytest.raises(ValueError):
        credits_to_sessions(3, sessions_per_credit=0)


# --- CreditSystem ------------------------------------------------------------
def test_expected_by_professor():
    p = Professor(name="Parody", practice_credits_by_subject={"S1_Mecanismos": 6})
    cs = CreditSystem(sessions_per_credit=5)
    expected = cs.expected_by_professor([p])
    assert expected[("Parody", "S1_Mecanismos")] == 30


# --- CreditValidator: gap detection (report case) ----------------------------
def test_validator_detects_overload():
    # Parody: expected 30, planned 50 -> +20 (real case from the report)
    p = Professor(name="Parody", practice_credits_by_subject={"S1_Mecanismos": 6})
    cs = CreditSystem(5)
    validator = CreditValidator(cs)
    discrepancies = validator.validate([p], {("Parody", "S1_Mecanismos"): 50})
    assert len(discrepancies) == 1
    d = discrepancies[0]
    assert d.delta == 20
    assert d.is_overload


def test_validator_detects_underload():
    p = Professor(name="Parrales", practice_credits_by_subject={"S2_Mecánica de Fluidos": 9})
    cs = CreditSystem(5)
    validator = CreditValidator(cs)
    # expected 45, planned 28 -> -17
    disc = validator.validate([p], {("Parrales", "S2_Mecánica de Fluidos"): 28})
    assert disc[0].delta == -17
    assert disc[0].is_underload


def test_validator_respects_tolerance():
    p = Professor(name="X", practice_credits_by_subject={"S1_Química": 2})
    cs = CreditSystem(5)
    validator = CreditValidator(cs)
    # expected 10, planned 8 -> -2, tolerated if tolerance>=2
    assert validator.validate([p], {("X", "S1_Química"): 8}, tolerance=2) == []
    assert len(validator.validate([p], {("X", "S1_Química"): 8}, tolerance=1)) == 1


def test_validator_summary():
    profs = [
        Professor(name="A", practice_credits_by_subject={"S1": 2}),
        Professor(name="B", practice_credits_by_subject={"S2": 4}),
    ]
    cs = CreditSystem(5)
    v = CreditValidator(cs)
    disc = v.validate(profs, {("A", "S1"): 15, ("B", "S2"): 10})
    summary = v.summary(disc)
    assert summary["total"] == 2
    assert summary["overloads"] == 1   # A: +5
    assert summary["underloads"] == 1  # B: -10
    assert summary["max_overload"] == 5
    assert summary["max_underload"] == -10


def test_professor_add_credits():
    p = Professor(name="Z")
    p.add_credits("S1_Física", Credits(3, CreditType.PRACTICE))
    p.add_credits("S1_Física", Credits(2, CreditType.PRACTICE))
    assert p.practice_credits("S1_Física") == 5
    assert p.expected_sessions("S1_Física") == 25
