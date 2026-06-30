"""Domain value objects.

A *value object* is immutable and defined solely by the value of its attributes
(it has no identity of its own). They model business concepts without a
lifecycle: time slot, week window, credits...
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List


class Period(str, Enum):
    """Time-of-day period of a time block."""
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class CreditType(str, Enum):
    """Type of credit held by a professor."""
    THEORY = "T"      # Teoría (lectures)
    PRACTICE = "P"    # Prácticas (laboratory)


@dataclass(frozen=True)
class TimeBlock:
    """A 2-hour time block (e.g. 08:30-10:30)."""
    id: int
    label: str
    start: int      # minutes since midnight
    end: int
    period: Period

    @property
    def is_morning(self) -> bool:
        return self.period == Period.MORNING


@dataclass(frozen=True)
class TimeSlot:
    """A fixed weekly slot: one day + one time block.

    The solver does NOT decide the slot (it is fixed when groups are formed) —
    it only decides the *week* of each session.
    """
    day_idx: int        # 0=Lunes .. 4=Viernes
    day: str
    block_id: int
    block_label: str

    def key(self) -> tuple:
        return (self.day_idx, self.block_id)


@dataclass(frozen=True)
class WeekWindow:
    """Time window [min_week, max_week] allowed for a subject."""
    min_week: int
    max_week: int

    def __post_init__(self):
        if self.min_week > self.max_week:
            raise ValueError(
                f"Invalid window: min_week({self.min_week}) > max_week({self.max_week})"
            )

    def weeks(self) -> List[int]:
        return list(range(self.min_week, self.max_week + 1))

    @property
    def span(self) -> int:
        return self.max_week - self.min_week + 1


@dataclass(frozen=True)
class Credits:
    """A professor's credits for a subject (theory or practice)."""
    amount: float
    credit_type: CreditType

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("The number of credits cannot be negative.")

    @property
    def is_practice(self) -> bool:
        return self.credit_type == CreditType.PRACTICE
