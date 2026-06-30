"""Group and LabSession entities."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from domain.value_objects import TimeSlot, WeekWindow


@dataclass
class LabSession:
    """A single laboratory session.

    The slot (day/block) is FIXED; the `week` is the variable decided by the
    CP-SAT solver. While unresolved, `week` is None.
    """
    id: int
    subject: str
    group_num: int
    session_num: int          # index of the session within the group's sequence
    curso_num: int
    slot: TimeSlot
    nb_students: int
    lab_rooms: List[str]
    window: WeekWindow
    program: str = ""
    student_ids: List[str] = field(default_factory=list)
    week: Optional[int] = None     # solver result
    professor: Optional[str] = None  # ONE responsible professor (allocation)

    @property
    def is_scheduled(self) -> bool:
        return self.week is not None


@dataclass
class Group:
    """A lab group: a set of students sharing a fixed slot and a sequence of
    `num_sessions` sessions for a given subject.
    """
    subject: str
    group_num: int
    semester: int
    curso_num: int
    num_sessions: int
    slot: TimeSlot
    nb_students: int
    lab_rooms: List[str]
    window: WeekWindow
    program: str = ""
    student_ids: List[str] = field(default_factory=list)
    professor: Optional[str] = None      # responsible professor (allocation)

    def build_sessions(self, start_id: int = 0) -> List[LabSession]:
        """Split the group into individual LabSession objects (1..num_sessions)."""
        sessions = []
        for k in range(1, self.num_sessions + 1):
            sessions.append(LabSession(
                id=start_id + k - 1,
                subject=self.subject,
                group_num=self.group_num,
                session_num=k,
                curso_num=self.curso_num,
                slot=self.slot,
                nb_students=self.nb_students,
                lab_rooms=list(self.lab_rooms),
                window=self.window,
                program=self.program,
                student_ids=list(self.student_ids),
                professor=self.professor,
            ))
        return sessions

    @property
    def key(self) -> tuple:
        return (self.subject, self.group_num)
