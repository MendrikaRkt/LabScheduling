"""Tests for the multi-department scheduling abstraction (scheduling_core.py).

Phase A: Tests cover profile loading, validation, and the stub solve_generic API.
Full solver tests will be added in Phase B when solve_generic is fully implemented.
"""

import pytest
import pandas as pd
from pathlib import Path
import scheduling_core as sc


def test_load_lab_practice_profile():
    """Lab practice profile loads correctly with expected attributes."""
    profile = sc.load_profile_by_name("lab_practice")
    
    assert profile.domain == "lab_practice"
    assert profile.entity_label == "Group"
    assert profile.sessions_per_entity == 5
    assert profile.scheduling_weeks == (1, 15)
    assert profile.allow_repetitions is True
    assert "student_conflict" in profile.hard_constraints
    assert "room_capacity" in profile.hard_constraints
    assert profile.room_filter_type == "lab_rooms"
    assert profile.capacity_mode == "per_group"
    assert profile.instructor_fixed is True
    assert profile.credit_label == "P credit"
    assert profile.credit_to_sessions_multiplier == 5


def test_load_final_exam_profile():
    """Final exam profile loads correctly with exam-specific rules."""
    profile = sc.load_profile_by_name("final_exam")
    
    assert profile.domain == "final_exam"
    assert profile.entity_label == "Exam"
    assert profile.sessions_per_entity == 1  # One exam only
    assert profile.scheduling_weeks == (1, 2)  # 2-week exam period
    assert profile.allow_repetitions is False
    assert "max_exams_per_day_per_student" in profile.hard_constraints
    assert profile.room_filter_type == "exam_rooms"
    assert profile.room_min_capacity == 40  # Large rooms for exams
    assert profile.capacity_mode == "aggregate"  # Can share rooms
    assert profile.instructor_fixed is False  # Flexible proctoring
    assert profile.credit_label == "Exam slot"


def test_list_available_profiles():
    """Profile discovery finds both lab_practice and final_exam."""
    profiles = sc.list_available_profiles()
    
    assert "lab_practice" in profiles
    assert "final_exam" in profiles
    assert len(profiles) >= 2


def test_profile_from_yaml_missing_file():
    """Loading non-existent profile raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        sc.SchedulingProfile.from_yaml("config/scheduling_profiles/nonexistent.yaml")


def test_profile_to_dict():
    """Profile serializes to dict for JSON/UI display."""
    profile = sc.load_profile_by_name("lab_practice")
    d = profile.to_dict()
    
    assert d["domain"] == "lab_practice"
    assert d["entity_label"] == "Group"
    assert d["sessions_per_entity"] == 5
    assert d["scheduling_weeks"]["min"] == 1
    assert d["scheduling_weeks"]["max"] == 15
    assert "student_conflict" in d["hard_constraints"]
    assert d["output_sheets"] == [
        "Grupo de prácticas",
        "Vista profesor",
        "Vista profesor (tabla)",
        "Teacher View",
        "Validation",
    ]


def test_validate_input_data_missing_columns():
    """Input validation detects missing required columns."""
    profile = sc.load_profile_by_name("lab_practice")
    
    # Missing 'students' column
    bad_entities = pd.DataFrame({"entity_id": [1, 2]})
    time_slots = pd.DataFrame({
        "week": [1], "day": [0], "block": [0], "room": ["Lab1"], "capacity": [20]
    })
    
    is_valid, errors = sc.validate_input_data(bad_entities, time_slots, profile)
    
    assert not is_valid
    assert any("students" in err for err in errors)


def test_validate_input_data_empty_entities():
    """Input validation detects empty entities DataFrame."""
    profile = sc.load_profile_by_name("lab_practice")
    
    empty_entities = pd.DataFrame(columns=["entity_id", "students", "instructor"])
    time_slots = pd.DataFrame({
        "week": [1], "day": [0], "block": [0], "room": ["Lab1"], "capacity": [20]
    })
    
    is_valid, errors = sc.validate_input_data(empty_entities, time_slots, profile)
    
    assert not is_valid
    assert any("empty" in err.lower() for err in errors)


def test_validate_input_data_valid():
    """Input validation passes for well-formed data."""
    profile = sc.load_profile_by_name("lab_practice")
    
    entities = pd.DataFrame({
        "entity_id": [1, 2],
        "students": [15, 18],
        "instructor": ["Prof A", "Prof B"]
    })
    time_slots = pd.DataFrame({
        "week": [1, 2],
        "day": [0, 1],
        "block": [0, 1],
        "room": ["Ciencias Experimentales I", "Lab. Robótica"],
        "capacity": [20, 16]
    })
    
    is_valid, errors = sc.validate_input_data(entities, time_slots, profile)
    
    assert is_valid
    assert len(errors) == 0


def test_solve_generic_lab_practice_stub():
    """solve_generic for lab_practice returns a DataFrame (stub implementation)."""
    profile = sc.load_profile_by_name("lab_practice")
    
    entities = pd.DataFrame({
        "entity_id": [1],
        "students": [15],
        "instructor": ["Prof A"]
    })
    time_slots = pd.DataFrame({
        "week": [1], "day": [0], "block": [0],
        "room": ["Lab1"], "capacity": [20]
    })
    busy_slots = {}
    
    # Phase A: stub implementation returns an empty schedule
    # (Full implementation in Phase B will return actual assignments)
    result = sc.solve_generic(entities, time_slots, busy_slots, profile)
    
    assert isinstance(result, pd.DataFrame)
    # Stub returns empty DataFrame with correct columns
    expected_cols = ["entity_id", "week", "day", "block", "room", "students", "instructor"]
    assert all(col in result.columns for col in expected_cols)


def test_solve_generic_final_exam_not_implemented():
    """solve_generic for final_exam raises NotImplementedError (Phase A)."""
    profile = sc.load_profile_by_name("final_exam")
    
    entities = pd.DataFrame({
        "entity_id": [1],
        "students": [120],
        "instructor": ["Prof A"]
    })
    time_slots = pd.DataFrame({
        "week": [1], "day": [0], "block": [0],
        "room": ["Aula Magna"], "capacity": [200]
    })
    busy_slots = {}
    
    # Phase A: exam solver not yet implemented
    with pytest.raises(NotImplementedError, match="final_exam"):
        sc.solve_generic(entities, time_slots, busy_slots, profile)


def test_solve_generic_unknown_domain():
    """solve_generic raises NotImplementedError for unknown domains."""
    # Create a minimal custom profile
    profile = sc.SchedulingProfile(
        domain="custom_domain",
        entity_label="Task",
        sessions_per_entity=1,
        scheduling_weeks=(1, 10),
        allow_repetitions=False,
    )
    
    entities = pd.DataFrame({"entity_id": [1], "students": [10]})
    time_slots = pd.DataFrame({
        "week": [1], "day": [0], "block": [0],
        "room": ["Room1"], "capacity": [20]
    })
    busy_slots = {}
    
    with pytest.raises(NotImplementedError, match="custom_domain"):
        sc.solve_generic(entities, time_slots, busy_slots, profile)
