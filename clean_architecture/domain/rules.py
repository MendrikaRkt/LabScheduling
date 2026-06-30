"""Pure business rules.

These functions depend on no infrastructure (no Excel, no solver, no Streamlit).
They encode the core business invariants of the domain and are therefore the
most critical components to cover with unit tests.
"""
from __future__ import annotations

# -----------------------------------------------------------------------------
# FUNDAMENTAL RULE: 1 practice (P) credit = N laboratory sessions.
# Historically N = 5 at Universidad Loyola. The value is configurable through
# the configuration file (config.yaml -> credit_system.sessions_per_credit) but
# the default stays 5 to preserve the existing behaviour.
# -----------------------------------------------------------------------------
DEFAULT_SESSIONS_PER_CREDIT = 5


def credits_to_sessions(practice_credits: float,
                        sessions_per_credit: int = DEFAULT_SESSIONS_PER_CREDIT) -> int:
    """Convert P credits into the expected number of sessions.

    >>> credits_to_sessions(3)
    15
    >>> credits_to_sessions(2, sessions_per_credit=5)
    10
    """
    if practice_credits < 0:
        raise ValueError("practice_credits must be >= 0")
    if sessions_per_credit <= 0:
        raise ValueError("sessions_per_credit must be > 0")
    return int(round(practice_credits * sessions_per_credit))


def sessions_to_credits(sessions: int,
                        sessions_per_credit: int = DEFAULT_SESSIONS_PER_CREDIT) -> float:
    """Inverse: derive the P credits equivalent to a number of sessions."""
    if sessions_per_credit <= 0:
        raise ValueError("sessions_per_credit must be > 0")
    return sessions / sessions_per_credit


def is_morning_year(curso_num: int) -> bool:
    """Odd years (1, 3) -> morning slots; even years (2, 4) -> afternoon slots."""
    return curso_num % 2 == 1


def friday_placement_penalty(day_idx: int, num_sessions: int,
                            current_friday_load: int,
                            friday_idx: int = 4,
                            soft_cap: int = 125,
                            base_penalty: int = 8,
                            overcap_weight: int = 10) -> int:
    """SOFT penalty subtracted from a group's Friday placement score.

    Reproduces the Friday anti-bottleneck logic: a constant penalty plus an
    escalation beyond a soft cap. It never forbids Friday (the day stays
    selectable if no other alternative exists).
    """
    if day_idx != friday_idx:
        return 0
    penalty = base_penalty
    projected = current_friday_load + max(0, int(num_sessions or 0))
    if projected > soft_cap:
        penalty += (projected - soft_cap) * overcap_weight
    return penalty
