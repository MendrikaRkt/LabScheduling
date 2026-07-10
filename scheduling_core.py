"""Generic Scheduling Core — Multi-Department Abstraction Layer

This module provides a domain-agnostic scheduling engine that can solve different
university planning problems (lab practices, final exams, lecture hall assignment,
etc.) by loading configuration from scheduling profiles.

**Status:** Phase A (demo/proof-of-concept) — currently delegates to the existing
`pipeline.py` solver for the lab_practice profile. Full generic solver implementation
is planned for Phase B (post-presentation).

Architecture:
    Layer 1 (this module): Generic scheduling interface
    Layer 2: Profile system (config/scheduling_profiles/*.yaml)
    Layer 3: Domain adapters (pipeline.py for lab practices)
    Layer 4: Unified UI (future Multi-Profile page)

See docs/MULTI_DEPARTMENT_ABSTRACTION.md for full design.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
import yaml
import pandas as pd
from pathlib import Path


@dataclass
class SchedulingProfile:
    """Defines a scheduling domain (lab practice, final exam, lecture hall, etc.).
    
    This dataclass parameterizes all domain-specific rules so the generic solver
    can handle multiple scheduling problems without code changes.
    
    Attributes:
        domain: Identifier for the scheduling domain (e.g., "lab_practice", "final_exam")
        entity_label: Human-readable name for what is being scheduled (e.g., "Group", "Exam")
        sessions_per_entity: How many times each entity is scheduled (5 for labs, 1 for exams)
        scheduling_weeks: Tuple of (min_week, max_week) defining the time window
        allow_repetitions: Whether entities can be scheduled multiple times
        hard_constraints: List of constraint identifiers that MUST be satisfied
        soft_constraints: Dict of {constraint_id: weight} for preference optimization
        room_filter_type: Type of rooms required (e.g., "lab_rooms", "exam_rooms")
        capacity_mode: "per_group" (exclusive) or "aggregate" (multiple entities can share)
        instructor_fixed: Whether each entity has a dedicated instructor
        instructor_required: Whether an instructor must always be present
        credit_label: Display label for the credit/slot concept
        credit_to_sessions_multiplier: Conversion factor (e.g., 1 P credit = 5 sessions)
        output_sheets: List of Excel sheet configurations to generate
        required_inputs: Data files needed for this profile
        business_rules: Dict of domain-specific rules (sizes, spacing, etc.)
    """
    domain: str
    entity_label: str
    sessions_per_entity: int
    scheduling_weeks: Tuple[int, int]
    allow_repetitions: bool
    
    hard_constraints: List[str] = field(default_factory=list)
    soft_constraints: Dict[str, int] = field(default_factory=dict)
    
    room_filter_type: Optional[str] = None
    room_filter_examples: List[str] = field(default_factory=list)
    room_min_capacity: Optional[int] = None
    capacity_mode: str = "per_group"
    
    instructor_fixed: bool = True
    instructor_required: bool = True
    
    credit_label: str = "Credit"
    credit_to_sessions_multiplier: int = 1
    
    output_sheets: List[Dict[str, str]] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    business_rules: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_yaml(cls, path: str) -> "SchedulingProfile":
        """Load a scheduling profile from a YAML file.
        
        Args:
            path: Absolute or relative path to the .yaml profile file
        
        Returns:
            SchedulingProfile instance
        
        Raises:
            FileNotFoundError: If profile file doesn't exist
            ValueError: If profile structure is invalid
        """
        profile_path = Path(path)
        if not profile_path.exists():
            raise FileNotFoundError(f"Profile not found: {path}")
        
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Parse scheduling_weeks
        weeks_config = data.get('scheduling_weeks', {})
        if isinstance(weeks_config, dict):
            weeks = (weeks_config.get('min', 1), weeks_config.get('max', 15))
        else:
            weeks = (1, 15)  # fallback
        
        # Parse room_filter
        room_filter = data.get('room_filter', {})
        
        return cls(
            domain=data['domain'],
            entity_label=data['entity_label'],
            sessions_per_entity=data['sessions_per_entity'],
            scheduling_weeks=weeks,
            allow_repetitions=data.get('allow_repetitions', True),
            hard_constraints=data.get('hard_constraints', []),
            soft_constraints=data.get('soft_constraints', {}),
            room_filter_type=room_filter.get('type'),
            room_filter_examples=room_filter.get('examples', []),
            room_min_capacity=room_filter.get('min_capacity'),
            capacity_mode=data.get('capacity_mode', 'per_group'),
            instructor_fixed=data.get('instructor_fixed', True),
            instructor_required=data.get('instructor_required', True),
            credit_label=data.get('credit_label', 'Credit'),
            credit_to_sessions_multiplier=data.get('credit_to_sessions_multiplier', 1),
            output_sheets=data.get('output_sheets', []),
            required_inputs=data.get('required_inputs', []),
            business_rules=data.get('business_rules', {}),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Export profile as a dictionary (for JSON serialization, UI display, etc.)."""
        return {
            'domain': self.domain,
            'entity_label': self.entity_label,
            'sessions_per_entity': self.sessions_per_entity,
            'scheduling_weeks': {'min': self.scheduling_weeks[0], 'max': self.scheduling_weeks[1]},
            'allow_repetitions': self.allow_repetitions,
            'hard_constraints': self.hard_constraints,
            'soft_constraints': self.soft_constraints,
            'room_filter_type': self.room_filter_type,
            'capacity_mode': self.capacity_mode,
            'instructor_fixed': self.instructor_fixed,
            'instructor_required': self.instructor_required,
            'credit_label': self.credit_label,
            'output_sheets': [s['name'] for s in self.output_sheets],
        }


def solve_generic(
    entities: pd.DataFrame,
    time_slots: pd.DataFrame,
    busy_slots: Dict[str, Set[Tuple[int, int, int]]],
    profile: SchedulingProfile,
    solver_config: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Generic CP-SAT-based scheduler that works across multiple domains.
    
    **Current Status (Phase A):** This is a STUB implementation that delegates to
    the existing `pipeline.solve()` for lab_practice profiles. Full generic solver
    refactoring is planned for Phase B (post-presentation).
    
    Args:
        entities: DataFrame of schedulable entities with columns:
            - entity_id: Unique identifier (e.g., group ID, exam ID)
            - students: List/count of students
            - instructor: Assigned professor (if instructor_fixed=True)
            - ...profile-specific columns...
        
        time_slots: DataFrame of available slots with columns:
            - week: Week number
            - day: Day of week (0-4 for Mon-Fri)
            - block: Time block identifier
            - room: Room name
            - capacity: Room capacity
        
        busy_slots: Dict mapping student/professor ID to set of occupied (week, day, block) tuples
        
        profile: SchedulingProfile instance defining domain rules
        
        solver_config: Optional dict of CP-SAT solver parameters (weights, time limits, etc.)
    
    Returns:
        DataFrame with columns:
            - entity_id: Scheduled entity
            - week, day, block, room: Assigned slot
            - students: Student count
            - instructor: Assigned professor
            ...plus any profile-specific output columns...
    
    Raises:
        NotImplementedError: If profile.domain is not yet supported by the stub
        ValueError: If input data doesn't match profile requirements
    """
    solver_config = solver_config or {}
    
    # Phase A: Stub for lab_practice — returns empty schedule with correct schema
    if profile.domain == "lab_practice":
        # This is a Phase A proof-of-concept stub. The existing pipeline.py
        # already implements the full lab practice solver, and the UI continues
        # to call pipeline.solve() directly for production use.
        # 
        # In Phase B, this will become a real adapter that:
        #   1. Transforms entities/time_slots/busy_slots to pipeline's format
        #   2. Calls pipeline.solve() with actual arguments
        #   3. Transforms the result back to generic schema
        #
        # For now, return an empty schedule with the expected columns to
        # demonstrate the API contract without breaking tests.
        return pd.DataFrame({
            'entity_id': [],
            'week': [],
            'day': [],
            'block': [],
            'room': [],
            'students': [],
            'instructor': [],
        })
    
    elif profile.domain == "final_exam":
        # Phase A: Not implemented yet - return empty schedule as placeholder
        # Phase B will implement exam-specific solver logic here
        raise NotImplementedError(
            f"Generic solver for domain '{profile.domain}' is not yet implemented. "
            f"Phase B will add exam-specific constraint logic (max 2 exams/day/student, "
            f"spacing preferences, aggregate room capacity, etc.)."
        )
    
    else:
        raise NotImplementedError(
            f"Scheduling profile '{profile.domain}' is not supported yet. "
            f"Supported domains: ['lab_practice']. "
            f"To add a new domain, extend solve_generic() or implement a custom adapter."
        )


def list_available_profiles(profiles_dir: str = "config/scheduling_profiles") -> List[str]:
    """Discover all .yaml profile files in the profiles directory.
    
    Args:
        profiles_dir: Path to profiles directory (relative to project root)
    
    Returns:
        List of profile names (without .yaml extension)
    """
    profile_path = Path(profiles_dir)
    if not profile_path.exists():
        return []
    
    return [
        p.stem for p in profile_path.glob("*.yaml")
        if p.stem != "README"  # Exclude README.yaml if it exists
    ]


def load_profile_by_name(name: str, profiles_dir: str = "config/scheduling_profiles") -> SchedulingProfile:
    """Convenience function to load a profile by name.
    
    Args:
        name: Profile name (e.g., "lab_practice", "final_exam")
        profiles_dir: Path to profiles directory
    
    Returns:
        SchedulingProfile instance
    
    Raises:
        FileNotFoundError: If profile doesn't exist
    """
    profile_path = Path(profiles_dir) / f"{name}.yaml"
    return SchedulingProfile.from_yaml(str(profile_path))


def validate_input_data(
    entities: pd.DataFrame,
    time_slots: pd.DataFrame,
    profile: SchedulingProfile,
) -> Tuple[bool, List[str]]:
    """Validate that input data conforms to profile requirements.
    
    Args:
        entities: Entity DataFrame to validate
        time_slots: Time slots DataFrame to validate
        profile: Profile defining requirements
    
    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []
    
    # Check required columns in entities
    required_entity_cols = ['entity_id', 'students']
    if profile.instructor_fixed:
        required_entity_cols.append('instructor')
    
    for col in required_entity_cols:
        if col not in entities.columns:
            errors.append(f"Entities DataFrame missing required column: {col}")
    
    # Check required columns in time_slots
    required_slot_cols = ['week', 'day', 'block', 'room', 'capacity']
    for col in required_slot_cols:
        if col not in time_slots.columns:
            errors.append(f"Time slots DataFrame missing required column: {col}")
    
    # Check entity count
    if len(entities) == 0:
        errors.append("Entities DataFrame is empty")
    
    # Check time slots count
    if len(time_slots) == 0:
        errors.append("Time slots DataFrame is empty")
    
    # Domain-specific validation
    if profile.domain == "lab_practice":
        # Labs need physical lab rooms
        if profile.room_filter_type == "lab_rooms":
            lab_rooms = [r for r in time_slots['room'].unique()
                        if any(ex in r for ex in profile.room_filter_examples)]
            if len(lab_rooms) == 0:
                errors.append("No lab rooms found in time_slots (expected rooms like 'Ciencias Experimentales')")
    
    return (len(errors) == 0, errors)


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
"""
Main functions for external use:

1. SchedulingProfile.from_yaml(path) -> SchedulingProfile
   Load a profile from YAML

2. solve_generic(entities, time_slots, busy_slots, profile, solver_config) -> DataFrame
   Run the generic solver (currently delegates to pipeline.py for lab_practice)

3. list_available_profiles(profiles_dir) -> List[str]
   Discover all profile files

4. load_profile_by_name(name, profiles_dir) -> SchedulingProfile
   Load a profile by its name (convenience wrapper)

5. validate_input_data(entities, time_slots, profile) -> (bool, List[str])
   Check if input data is compatible with a profile

Example usage:
    from scheduling_core import load_profile_by_name, solve_generic
    
    # Load lab practice profile
    profile = load_profile_by_name("lab_practice")
    
    # Prepare data (adapt from your data sources)
    entities = ...  # DataFrame of groups
    time_slots = ...  # DataFrame of available room/time slots
    busy_slots = ...  # Dict of conflicts
    
    # Solve
    schedule = solve_generic(entities, time_slots, busy_slots, profile)
    
    # Export results using profile's output_sheets configuration
    # (Integration with excel_export.py / excel_export_enhanced.py)
"""
