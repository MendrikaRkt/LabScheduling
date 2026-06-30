"""Tests for configuration loading (externalization of LAB_CONFIG)."""
from infrastructure.config.config_loader import get_settings


def test_all_subjects_loaded():
    s = get_settings()
    assert len(s.subjects) == 22


def test_subject_values_match_legacy():
    s = get_settings()
    fisica = s.subjects["S1_Física"]
    assert fisica.curso_num == 1
    assert fisica.num_sessions == 5
    assert fisica.window.min_week == 4
    assert fisica.window.max_week == 14
    assert fisica.shared_group == "S1_1er_anno"
    assert fisica.group_by_program is True


def test_credit_rule_default():
    assert get_settings().sessions_per_credit == 5


def test_friday_policy():
    f = get_settings().friday
    assert f.soft_cap == 125
    assert f.base_penalty == 8
    assert f.overcap_weight == 10


def test_holidays_parsed():
    s = get_settings()
    assert (7, 0) in s.holidays[1]   # Día de la Hispanidad
    assert (9, 4) in s.holidays[2]   # Semana Santa


def test_blocked_slots_parsed():
    s = get_settings()
    key = (1, "S1_Química")
    assert key in s.subject_blocked_slots
    assert (7, 2, 2) in s.subject_blocked_slots[key]
