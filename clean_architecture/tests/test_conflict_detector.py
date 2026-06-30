"""Tests for the conflict detector."""
from application.services.conflict_detector import ConflictDetector
from domain.entities.group import LabSession
from domain.value_objects import TimeSlot, WeekWindow


def _session(sid, subject, group, sess_num, week, day_idx=0, block=1,
            rooms=("Lab A",), students=()):
    return LabSession(
        id=sid, subject=subject, group_num=group, session_num=sess_num,
        curso_num=1, slot=TimeSlot(day_idx, "Lunes", block, "08:30-10:30"),
        nb_students=12, lab_rooms=list(rooms), window=WeekWindow(1, 14),
        student_ids=list(students), week=week,
    )


def test_no_conflict_clean_schedule():
    sessions = [
        _session(0, "S1_Física", 1, 1, 4),
        _session(1, "S1_Física", 1, 2, 6),
    ]
    assert ConflictDetector().detect(sessions) == []


def test_same_subject_slot_conflict():
    # 2 groups, same subject, same slot, same week -> C1
    sessions = [
        _session(0, "S1_Física", 1, 1, 5, day_idx=0, block=1),
        _session(1, "S1_Física", 2, 1, 5, day_idx=0, block=1),
    ]
    conflicts = ConflictDetector().detect(sessions)
    assert any(c.kind == "C1" for c in conflicts)


def test_same_room_conflict():
    sessions = [
        _session(0, "S1_Física", 1, 1, 5, rooms=("Lab X",)),
        _session(1, "S1_Química", 1, 1, 5, rooms=("Lab X",)),
    ]
    conflicts = ConflictDetector().detect(sessions)
    assert any(c.kind == "C4" for c in conflicts)


def test_chronological_order_violation():
    # session 2 (week 4) before session 1 (week 6) -> C5
    sessions = [
        _session(0, "S1_Física", 1, 1, 6),
        _session(1, "S1_Física", 1, 2, 4),
    ]
    conflicts = ConflictDetector().detect(sessions)
    assert any(c.kind == "C5" for c in conflicts)


def test_student_double_booking():
    sessions = [
        _session(0, "S1_Física", 1, 1, 5, students=("alu1",)),
        _session(1, "S1_Química", 1, 1, 5, rooms=("Lab B",), students=("alu1",)),
    ]
    conflicts = ConflictDetector().detect(sessions)
    assert any(c.kind == "STUDENT" for c in conflicts)
