"""Subject entity (a laboratory course)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from domain.value_objects import WeekWindow


@dataclass
class Subject:
    """A subject configured for practical (lab) work.

    Corresponds to an entry of the former LAB_CONFIG, but as a validated and
    self-documenting business object.
    """
    code: str                       # e.g. "S1_Física"
    curso_num: int                  # year 1, 2, 3
    semester: int                   # 1 or 2
    num_sessions: int               # sessions per group
    window: WeekWindow              # time window
    max_students: int
    lab_rooms: List[str]
    keywords: List[str] = field(default_factory=list)
    keyword_exclude: List[str] = field(default_factory=list)
    group_by_program: bool = False
    shared_group: str | None = None
    simultaneous_rooms: bool = False
    intro_session_paired: bool = False

    def __post_init__(self):
        if self.num_sessions < 0:
            raise ValueError(f"{self.code}: num_sessions must be >= 0")
        if self.max_students <= 0:
            raise ValueError(f"{self.code}: max_students must be > 0")
        if not self.lab_rooms:
            raise ValueError(f"{self.code}: at least one room is required")

    @property
    def is_morning(self) -> bool:
        return self.curso_num % 2 == 1

    @property
    def display_name(self) -> str:
        """Readable name without the semester prefix (S1_/S2_)."""
        return self.code.split("_", 1)[1] if "_" in self.code else self.code
