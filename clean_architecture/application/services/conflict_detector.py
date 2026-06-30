"""ConflictDetector - detection of conflicts in a resolved schedule.

Independent of the solver: validates a posteriori that a solution (sessions
with assigned weeks) satisfies the hard constraints. Acts as a safety net and a
basis for quality reports.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List

from domain.entities.group import LabSession


@dataclass
class Conflict:
    kind: str
    description: str
    session_ids: List[int]


class ConflictDetector:
    """Detects subject, room, ordering and student conflicts."""

    def detect(self, sessions: List[LabSession]) -> List[Conflict]:
        scheduled = [s for s in sessions if s.is_scheduled]
        conflicts: List[Conflict] = []
        conflicts += self._same_subject_slot(scheduled)
        conflicts += self._same_room_slot(scheduled)
        conflicts += self._chronological_order(scheduled)
        conflicts += self._student_double_booking(scheduled)
        return conflicts

    # -- C1: no 2 sessions of the same subject at the same (week, day, block) -
    def _same_subject_slot(self, sessions: List[LabSession]) -> List[Conflict]:
        buckets = defaultdict(list)
        for s in sessions:
            buckets[(s.subject, s.week, s.slot.day_idx, s.slot.block_id)].append(s)
        out = []
        for (subj, week, d, b), grp in buckets.items():
            if len(grp) > 1:
                out.append(Conflict(
                    "C1", f"{subj}: {len(grp)} sessions in the same slot "
                    f"(week {week}, day {d}, block {b})",
                    [s.id for s in grp]))
        return out

    # -- C4: no 2 sessions in the same room at the same slot ----------------
    def _same_room_slot(self, sessions: List[LabSession]) -> List[Conflict]:
        buckets = defaultdict(list)
        for s in sessions:
            for room in s.lab_rooms:
                room = room.strip()
                if room:
                    buckets[(room, s.week, s.slot.day_idx, s.slot.block_id)].append(s)
        out = []
        for (room, week, d, b), grp in buckets.items():
            if len(grp) > 1:
                out.append(Conflict(
                    "C4", f"Room '{room}': {len(grp)} sessions in the same slot "
                    f"(week {week}, day {d}, block {b})",
                    [s.id for s in grp]))
        return out

    # -- C5: chronological order of sessions within a group -----------------
    def _chronological_order(self, sessions: List[LabSession]) -> List[Conflict]:
        by_group = defaultdict(list)
        for s in sessions:
            by_group[(s.subject, s.group_num)].append(s)
        out = []
        for key, grp in by_group.items():
            grp_sorted = sorted(grp, key=lambda x: x.session_num)
            for k in range(len(grp_sorted) - 1):
                if grp_sorted[k + 1].week is not None and \
                        grp_sorted[k].week is not None and \
                        grp_sorted[k + 1].week <= grp_sorted[k].week:
                    out.append(Conflict(
                        "C5", f"{key[0]} G{key[1]}: session {grp_sorted[k+1].session_num} "
                        f"(week {grp_sorted[k+1].week}) is not after session "
                        f"{grp_sorted[k].session_num} (week {grp_sorted[k].week})",
                        [grp_sorted[k].id, grp_sorted[k + 1].id]))
        return out

    # -- Student present in 2 sessions at the same slot ---------------------
    def _student_double_booking(self, sessions: List[LabSession]) -> List[Conflict]:
        buckets = defaultdict(list)
        for s in sessions:
            for sid in s.student_ids:
                buckets[(sid, s.week, s.slot.day_idx, s.slot.block_id)].append(s)
        out = []
        for (student, week, d, b), grp in buckets.items():
            if len(grp) > 1:
                out.append(Conflict(
                    "STUDENT", f"Student {student}: {len(grp)} simultaneous sessions "
                    f"(week {week}, day {d}, block {b})",
                    [s.id for s in grp]))
        return out
