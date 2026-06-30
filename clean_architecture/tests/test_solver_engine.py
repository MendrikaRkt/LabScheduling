"""Lightweight integration tests for the CP-SAT engine and SchedulerService."""
from application.services.credit_system import CreditSystem
from application.services.scheduler_service import SchedulerService
from application.use_cases.run_scheduling import RunSchedulingUseCase
from domain.entities.group import Group
from domain.entities.professor import Professor
from domain.value_objects import TimeSlot, WeekWindow
from infrastructure.config.config_loader import get_settings
from infrastructure.solver.solver_engine import CPSATSolver


def _group(subject, num, sessions, day_idx, block, rooms, students=None):
    return Group(
        subject=subject, group_num=num, semester=1, curso_num=1,
        num_sessions=sessions,
        slot=TimeSlot(day_idx, "Lunes", block, "08:30-10:30"),
        nb_students=12, lab_rooms=rooms, window=WeekWindow(4, 14),
        student_ids=students or [],
    )


def test_solver_assigns_weeks_in_window():
    settings = get_settings()
    solver = CPSATSolver(settings)
    groups = [_group("S1_Física", 1, 5, 0, 1, ["Lab A"])]
    result = solver.solve_groups(groups)
    assert result.is_feasible
    weeks = sorted(s.week for s in result.sessions)
    assert all(4 <= w <= 14 for w in weeks)
    # strict chronological order (C5)
    assert weeks == sorted(set(weeks))


def test_solver_no_same_room_same_week():
    settings = get_settings()
    solver = CPSATSolver(settings)
    # 2 groups, same room, same slot -> must be in distinct weeks
    groups = [
        _group("S1_Física", 1, 3, 0, 1, ["Lab A"]),
        _group("S1_Química", 1, 3, 0, 1, ["Lab A"]),
    ]
    result = solver.solve_groups(groups)
    assert result.is_feasible
    fis = [s.week for s in result.sessions if s.subject == "S1_Física"]
    qui = [s.week for s in result.sessions if s.subject == "S1_Química"]
    # no common week on this shared slot
    assert set(fis).isdisjoint(set(qui))


def test_scheduler_service_allocates_professors_by_credits():
    settings = get_settings()
    cs = CreditSystem(settings.sessions_per_credit)
    service = SchedulerService(CPSATSolver(settings), cs)

    # 2 teachers: A=2 credits (10 sessions), B=1 credit (5 sessions)
    profs = [
        Professor(name="A", practice_credits_by_subject={"S1_Física": 2}),
        Professor(name="B", practice_credits_by_subject={"S1_Física": 1}),
    ]
    groups = [_group("S1_Física", i, 5, 0, b, ["Lab A"]) for i, b in
            zip(range(1, 4), [1, 2, 3])]
    result = service.schedule(groups, profs)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    # every group has an allocated teacher
    assert all(g.professor in ("A", "B") for g in groups)


def test_use_case_end_to_end():
    uc = RunSchedulingUseCase()
    profs = [Professor(name="A", practice_credits_by_subject={"S1_Física": 1})]
    groups = [_group("S1_Física", 1, 5, 0, 1, ["Lab A"])]
    result = uc.execute(groups, profs)
    assert result.status in ("OPTIMAL", "FEASIBLE")
