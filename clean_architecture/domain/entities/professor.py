"""Professor entity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from domain.rules import DEFAULT_SESSIONS_PER_CREDIT, credits_to_sessions
from domain.value_objects import Credits, CreditType


@dataclass
class Professor:
    """A professor and their credits per subject.

    `practice_credits_by_subject` maps a subject code -> official P credits
    (source of truth: teaching assignment / "Asignación docente"). It is the
    basis for computing the expected load (sessions = credits x
    sessions_per_credit).
    """
    name: str
    email: str = ""
    full_name: str = ""
    practice_credits_by_subject: Dict[str, float] = field(default_factory=dict)
    theory_credits_by_subject: Dict[str, float] = field(default_factory=dict)
    # Unavailability: whole days or specific slots (soft constraints)
    unavailable_days: List[int] = field(default_factory=list)
    unavailable_slots: List[tuple] = field(default_factory=list)  # (day_idx, block_id)

    def practice_credits(self, subject_code: str) -> float:
        return self.practice_credits_by_subject.get(subject_code, 0.0)

    def expected_sessions(self, subject_code: str,
                        sessions_per_credit: int = DEFAULT_SESSIONS_PER_CREDIT) -> int:
        """Expected sessions for this professor on this subject (P credits x N)."""
        return credits_to_sessions(self.practice_credits(subject_code),
                                sessions_per_credit)

    def total_practice_credits(self) -> float:
        return sum(self.practice_credits_by_subject.values())

    def subjects(self) -> List[str]:
        return sorted(self.practice_credits_by_subject.keys())

    def add_credits(self, subject_code: str, credits: Credits) -> None:
        if credits.credit_type == CreditType.PRACTICE:
            self.practice_credits_by_subject[subject_code] = (
                self.practice_credits_by_subject.get(subject_code, 0.0) + credits.amount
            )
        else:
            self.theory_credits_by_subject[subject_code] = (
                self.theory_credits_by_subject.get(subject_code, 0.0) + credits.amount
            )
