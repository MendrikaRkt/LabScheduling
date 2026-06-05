"""
manual_edit.py
==============

Backend module for post-generation manual editing of the planning.

This module is the engine behind the "Manual edit" page in the Streamlit app.
Its responsibilities:

    1. Load the current planning (schedule + groups + student availability)
    2. Validate that a proposed change does not break critical constraints
    3. Apply validated changes to in-memory dataframes
    4. Manage a "pending changes" basket (changes are not persisted until
       the user explicitly commits)
    5. Commit pending changes to disk (CSVs + Excel) and snapshot before commit

Architecture decisions (from spec):
    Q1 (1C): supports both moving a single session AND moving a whole group
    Q2 (2B): exposes a grid of free/busy slots for the UI to render
    Q3:     blocks C1, C4, student-conflict violations
            warns on C5 (ordering), holidays, C7 (year preference), week window
    Q6 (6A): used by a dedicated Streamlit page
    Q7 (7C): pending changes basket with commit / discard

Public API:
    EditSession(...)             top-level object owning the in-memory state
        load()                   load current planning into memory
        feasibility_grid(...)    return a grid of free/blocked slots for a group
        propose_move_session()   stage a single-session move
        propose_move_group()     stage a full-group move (all sessions)
        list_pending()           list staged changes
        discard_pending(idx)     remove one staged change
        discard_all_pending()    clear the basket
        commit(label)            apply all staged changes + create snapshot
        validate_move(...)       validate a move WITHOUT staging it
"""

import os
import shutil
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd


# =============================================================================
# CONSTANTS
# =============================================================================

SCHEDULE_CSV_PATH    = 'outputs/optimization/optimized_schedule_v5.csv'
GROUPS_CSV_PATH      = 'outputs/optimization/group_composition.csv'
STUDENT_BUSY_PATH    = 'data_clean/optimization/student_busy.csv'

# Spanish weekday names used throughout the project
DAYS_OF_WEEK = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
DAY_NAME_TO_INDEX = {name: idx for idx, name in enumerate(DAYS_OF_WEEK)}

# Time blocks (must match TIME_BLOCKS in pipeline.py)
TIME_BLOCKS = ['08:30-10:30', '10:30-12:30', '12:30-14:30',
               '15:00-17:00', '17:00-19:00', '19:00-21:00']

# Morning/afternoon split for C7 (year preference)
MORNING_BLOCKS = ['08:30-10:30', '10:30-12:30', '12:30-14:30']
AFTERNOON_BLOCKS = ['15:00-17:00', '17:00-19:00', '19:00-21:00']

# Group size policy (loaded from pipeline defaults — keep in sync)
PREFERRED_GROUP_SIZE = 12
MAX_GROUP_SIZE       = 15
MIN_GROUP_SIZE       = 7

# Shared-group families: when two subjects share student groups
# (e.g. Física and Química in 1st year share the same group composition),
# a swap in one subject should propose to apply the same swap in the others.
# Keys are the family identifier (matching LAB_CONFIG['shared_group'] in pipeline).
# Values are the list of subjects in that family.
SHARED_GROUP_FAMILIES: Dict[str, List[str]] = {
    'S1_1er_anno': ['S1_Física', 'S1_Química'],
}

# Reverse lookup: subject -> family identifier (or None if standalone)
def _build_subject_to_family() -> Dict[str, str]:
    """Build {subject: family_id} reverse mapping from SHARED_GROUP_FAMILIES."""
    mapping = {}
    for family_id, subjects in SHARED_GROUP_FAMILIES.items():
        for subj in subjects:
            mapping[subj] = family_id
    return mapping

SUBJECT_TO_FAMILY = _build_subject_to_family()

# Holidays as configured in the pipeline (semester -> {(week, day_idx): label})
# Keep this manually synced with pipeline.py HOLIDAYS.
HOLIDAYS = {
    1: {
        (7, 0): "Día de la Hispanidad",
    },
    2: {},
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PendingChange:
    """
    Represents one staged modification that has not yet been committed.

    Attributes:
        change_type:  'move_session' | 'move_group'
        description:  human-readable summary for the UI
        target:       dict identifying what's being modified (subject, grupo, session)
        before:       dict of original values
        after:        dict of new values
        warnings:     list of non-blocking concerns
        created_at:   timestamp when the change was staged
    """
    change_type: str
    description: str
    target: Dict
    before: Dict
    after: Dict
    warnings: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationResult:
    """
    Result of validating a proposed change.

    Attributes:
        is_valid:    True if the change can be applied (no hard blockers)
        blockers:    hard violations that prevent the change
                     (C1, C4, student conflict)
        warnings:    soft issues to surface to the user but not block
                     (C5, holidays, C7, week window, group size)
    """
    is_valid: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# =============================================================================
# EDIT SESSION
# =============================================================================

class EditSession:
    """
    Top-level controller for manual edits.

    Holds in-memory copies of the planning dataframes that get mutated as the
    user stages changes. The originals on disk are only modified when commit()
    is called.

    Typical usage:
        session = EditSession()
        session.load()
        grid = session.feasibility_grid(subject='S1_Física', grupo=5, session_num=3)
        result = session.propose_move_session(
            subject='S1_Física', grupo=5, session_num=3,
            new_week=8, new_day='Jueves', new_block='10:30-12:30'
        )
        if result.is_valid:
            session.commit(label='Fix Pedro conflict')
    """

    def __init__(self):
        # In-memory copies of the dataframes; loaded by load()
        self.schedule_df: Optional[pd.DataFrame] = None
        self.groups_df: Optional[pd.DataFrame] = None

        # Map: student_id -> set of (day_idx, block_id) for their "real" busy slots
        # (from courses, NOT including the labs we are scheduling)
        self.student_busy: Dict[str, Set[Tuple[int, int]]] = {}

        # Original schedule_df at load time, to compute diffs on commit
        self._original_schedule_df: Optional[pd.DataFrame] = None
        self._original_groups_df: Optional[pd.DataFrame] = None

        # Pending changes basket (workflow 7C)
        self.pending: List[PendingChange] = []

        # Has anything been loaded yet
        self.loaded: bool = False

    # ─────────────────────────────────────────────────────────────────────
    # LOADING
    # ─────────────────────────────────────────────────────────────────────

    def load(self) -> bool:
        """
        Load the current planning files into memory.

        Returns:
            True if all required files were loaded successfully.
        """
        if not os.path.exists(SCHEDULE_CSV_PATH):
            return False
        if not os.path.exists(GROUPS_CSV_PATH):
            return False

        self.schedule_df = pd.read_csv(SCHEDULE_CSV_PATH)
        self.groups_df = pd.read_csv(GROUPS_CSV_PATH)

        # Keep originals for diffing
        self._original_schedule_df = self.schedule_df.copy()
        self._original_groups_df = self.groups_df.copy()

        # Load student_busy.csv (optional — without it, student-conflict checks
        # fall back to checking against the planning itself, not their courses)
        self.student_busy = {}
        if os.path.exists(STUDENT_BUSY_PATH):
            try:
                busy_df = pd.read_csv(STUDENT_BUSY_PATH)
                # Format: student_id, day_idx, block_id (one row per busy slot)
                for student_id, grp in busy_df.groupby('student_id'):
                    self.student_busy[str(student_id)] = {
                        (int(r['day_idx']), int(r['block_id'])) for _, r in grp.iterrows()
                    }
            except Exception:
                # Non-critical: continue without it
                pass

        self.loaded = True
        return True

    # ─────────────────────────────────────────────────────────────────────
    # FEASIBILITY GRID
    # ─────────────────────────────────────────────────────────────────────

    def feasibility_grid(
        self,
        subject: str,
        grupo: int,
        session_num: Optional[int] = None,
        target_weeks: Optional[List[int]] = None,
    ) -> Dict:
        """
        Return a grid of valid/blocked slots for moving a session or group.

        For each (week, day, block) combination in `target_weeks`, indicates:
            - 'free':       no conflict, move is OK
            - 'self':       this is where the session currently is
            - 'conflict':   moving here would create a hard conflict
            - 'warning':    moving here is allowed but raises a soft warning

        Args:
            subject:      e.g. 'S1_Física'
            grupo:        group number (1, 2, ...)
            session_num:  if specified, grid is for a single session;
                          if None, grid is for moving the whole group
            target_weeks: list of weeks to evaluate; if None, uses all weeks
                          in the schedule

        Returns:
            dict mapping (week, day, block) -> dict with keys:
                {'status': 'free'|'self'|'conflict'|'warning',
                 'reasons': list of strings explaining why}
        """
        if not self.loaded:
            return {}

        # Determine which sessions are being considered
        if session_num is not None:
            target_mask = (
                (self.schedule_df['subject'] == subject)
                & (self.schedule_df['grupo'] == grupo)
                & (self.schedule_df['session'] == session_num)
            )
        else:
            target_mask = (
                (self.schedule_df['subject'] == subject)
                & (self.schedule_df['grupo'] == grupo)
            )

        target_sessions = self.schedule_df[target_mask]
        if len(target_sessions) == 0:
            return {}

        first_row = target_sessions.iloc[0]
        semester = int(first_row['semester'])

        # Default weeks: all weeks present in the schedule for this semester
        if target_weeks is None:
            target_weeks = sorted(
                self.schedule_df[self.schedule_df['semester'] == semester]['week'].unique()
            )
            target_weeks = [int(w) for w in target_weeks]

        # Current location(s)
        current_locations = {
            (int(r['week']), r['day'], r['time_block'])
            for _, r in target_sessions.iterrows()
        }

        grid = {}
        for week in target_weeks:
            for day in DAYS_OF_WEEK:
                for block in TIME_BLOCKS:
                    if (week, day, block) in current_locations:
                        grid[(week, day, block)] = {
                            'status': 'self',
                            'reasons': ['Position actuelle'],
                        }
                        continue

                    # Validate the move at this slot
                    if session_num is not None:
                        result = self.validate_move(
                            subject=subject, grupo=grupo, session_num=session_num,
                            new_week=week, new_day=day, new_block=block,
                        )
                    else:
                        result = self._validate_group_move(
                            subject=subject, grupo=grupo,
                            new_day=day, new_block=block,
                        )

                    if not result.is_valid:
                        grid[(week, day, block)] = {
                            'status': 'conflict',
                            'reasons': result.blockers,
                        }
                    elif result.warnings:
                        grid[(week, day, block)] = {
                            'status': 'warning',
                            'reasons': result.warnings,
                        }
                    else:
                        grid[(week, day, block)] = {
                            'status': 'free',
                            'reasons': [],
                        }
        return grid

    # ─────────────────────────────────────────────────────────────────────
    # VALIDATION
    # ─────────────────────────────────────────────────────────────────────

    def validate_move(
        self,
        subject: str,
        grupo: int,
        session_num: int,
        new_week: int,
        new_day: str,
        new_block: str,
    ) -> ValidationResult:
        """
        Validate moving a single session WITHOUT applying the change.

        Returns a ValidationResult with separated blockers and warnings.
        """
        if not self.loaded:
            return ValidationResult(False, blockers=['Edit session not loaded'])

        # Find the session being moved
        target_mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
            & (self.schedule_df['session'] == session_num)
        )
        target_rows = self.schedule_df[target_mask]
        if len(target_rows) == 0:
            return ValidationResult(False, blockers=[
                f"Session non trouvée : {subject} G{grupo} P{session_num}"
            ])
        target_row = target_rows.iloc[0]
        semester = int(target_row['semester'])
        lab_rooms = target_row['lab_rooms']

        blockers = []
        warnings = []

        # ───── HARD BLOCKERS ─────

        # C1: another session of the same subject at the same slot?
        c1_mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['semester'] == semester)
            & (self.schedule_df['week'] == new_week)
            & (self.schedule_df['day'] == new_day)
            & (self.schedule_df['time_block'] == new_block)
            & ~target_mask  # exclude the session being moved
        )
        c1_conflicts = self.schedule_df[c1_mask]
        if len(c1_conflicts) > 0:
            other_grupo = int(c1_conflicts.iloc[0]['grupo'])
            blockers.append(
                f"C1: une autre session de {self._clean_subject(subject)} "
                f"(Grupo {other_grupo}) est déjà à ce créneau"
            )

        # C4: another session in the same room at the same slot?
        # (Compare room sets — Física uses "Ciencias I + II" as 1 string)
        new_room_set = self._parse_rooms(lab_rooms)
        c4_mask = (
            (self.schedule_df['semester'] == semester)
            & (self.schedule_df['week'] == new_week)
            & (self.schedule_df['day'] == new_day)
            & (self.schedule_df['time_block'] == new_block)
            & ~target_mask
        )
        for _, other_row in self.schedule_df[c4_mask].iterrows():
            other_rooms = self._parse_rooms(other_row['lab_rooms'])
            if new_room_set & other_rooms:
                shared = ', '.join(new_room_set & other_rooms)
                blockers.append(
                    f"C4: salle déjà occupée ({shared}) par "
                    f"{self._clean_subject(other_row['subject'])} "
                    f"Grupo {int(other_row['grupo'])}"
                )
                break

        # Student conflict: any student in this group has another commitment at this slot?
        students_in_group = self._get_students_in_group(subject, grupo)
        day_idx = DAY_NAME_TO_INDEX.get(new_day, -1)
        block_idx = TIME_BLOCKS.index(new_block) + 1 if new_block in TIME_BLOCKS else -1

        if day_idx >= 0 and block_idx >= 0:
            slot_key = (day_idx, block_idx)
            students_with_conflict = []
            for student in students_in_group:
                # Check against external courses (student_busy.csv)
                busy_slots = self.student_busy.get(str(student), set())
                if slot_key in busy_slots:
                    # But: if the busy slot is a course of the SAME subject being moved,
                    # it's OK (lab replaces course principle)
                    # For simplicity here we treat it as a soft warning rather than
                    # a hard block since we can't easily distinguish.
                    students_with_conflict.append(student)

            if students_with_conflict:
                warnings.append(
                    f"{len(students_with_conflict)} étudiant(s) du groupe ont un cours "
                    f"à ce créneau (peut être normal si c'est le cours de la matière)"
                )

            # Check against other labs already scheduled at this slot
            other_labs_mask = (
                (self.schedule_df['semester'] == semester)
                & (self.schedule_df['week'] == new_week)
                & (self.schedule_df['day'] == new_day)
                & (self.schedule_df['time_block'] == new_block)
                & ~target_mask
            )
            other_labs = self.schedule_df[other_labs_mask]
            students_in_other_lab = set()
            for _, other_row in other_labs.iterrows():
                other_students = self._get_students_in_group(
                    other_row['subject'], int(other_row['grupo'])
                )
                students_in_other_lab.update(other_students)

            shared_students = students_in_group & students_in_other_lab
            if shared_students:
                blockers.append(
                    f"Conflit étudiant: {len(shared_students)} étudiant(s) sont déjà "
                    f"dans un autre lab à ce créneau"
                )

        # ───── SOFT WARNINGS ─────

        # C5: session ordering (P2 must be after P1, P3 after P2, etc.)
        # We need to check: with this move, are sessions still in chronological order?
        group_sessions = self.schedule_df[
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
            & (~target_mask)  # exclude the one we're moving
        ].sort_values('session')

        for _, other_session in group_sessions.iterrows():
            other_num = int(other_session['session'])
            other_week = int(other_session['week'])
            if other_num < session_num and other_week >= new_week:
                warnings.append(
                    f"C5: la session {other_num} (semaine {other_week}) devrait "
                    f"être AVANT la session {session_num} (vous voulez semaine {new_week})"
                )
            elif other_num > session_num and other_week <= new_week:
                warnings.append(
                    f"C5: la session {other_num} (semaine {other_week}) devrait "
                    f"être APRÈS la session {session_num} (vous voulez semaine {new_week})"
                )

        # Holiday check
        if (new_week, day_idx) in HOLIDAYS.get(semester, {}):
            holiday_name = HOLIDAYS[semester][(new_week, day_idx)]
            warnings.append(f"Jour férié : {holiday_name}")

        # C7: year preference (1st/3rd year = morning, 2nd/4th = afternoon)
        curso_num = int(target_row.get('curso_num', 0))
        if curso_num in [1, 3] and new_block in AFTERNOON_BLOCKS:
            warnings.append(
                f"C7: les {curso_num}ère année devraient être le matin, "
                f"pas {new_block}"
            )
        elif curso_num in [2, 4] and new_block in MORNING_BLOCKS:
            warnings.append(
                f"C7: les {curso_num}ème année devraient être l'après-midi, "
                f"pas {new_block}"
            )

        return ValidationResult(
            is_valid=(len(blockers) == 0),
            blockers=blockers,
            warnings=warnings,
        )

    def _validate_group_move(
        self,
        subject: str,
        grupo: int,
        new_day: str,
        new_block: str,
    ) -> ValidationResult:
        """
        Validate moving a WHOLE group to a new weekly slot (same day+block,
        sessions stay at their original weeks).

        Returns aggregated validation (worst-case across all sessions).
        """
        group_sessions = self.schedule_df[
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
        ]
        if len(group_sessions) == 0:
            return ValidationResult(False, blockers=['Group not found'])

        all_blockers = []
        all_warnings = []

        for _, row in group_sessions.iterrows():
            result = self.validate_move(
                subject=subject, grupo=grupo,
                session_num=int(row['session']),
                new_week=int(row['week']),  # week unchanged
                new_day=new_day, new_block=new_block,
            )
            all_blockers.extend(result.blockers)
            all_warnings.extend(result.warnings)

        # Deduplicate
        all_blockers = list(dict.fromkeys(all_blockers))
        all_warnings = list(dict.fromkeys(all_warnings))

        return ValidationResult(
            is_valid=(len(all_blockers) == 0),
            blockers=all_blockers,
            warnings=all_warnings,
        )

    # ─────────────────────────────────────────────────────────────────────
    # STAGING (pending changes basket)
    # ─────────────────────────────────────────────────────────────────────

    def propose_move_session(
        self,
        subject: str,
        grupo: int,
        session_num: int,
        new_week: int,
        new_day: str,
        new_block: str,
    ) -> ValidationResult:
        """
        Validate AND stage a single-session move.

        If validation passes, the change is added to the pending basket AND
        applied to the in-memory dataframe (so subsequent moves see the
        updated state). The disk files are NOT modified until commit().

        Returns the ValidationResult. If is_valid is False, the change is
        NOT staged.
        """
        result = self.validate_move(subject, grupo, session_num,
                                     new_week, new_day, new_block)
        if not result.is_valid:
            return result

        target_mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
            & (self.schedule_df['session'] == session_num)
        )
        target_idx = self.schedule_df[target_mask].index
        if len(target_idx) == 0:
            return ValidationResult(False, blockers=['Session disappeared'])

        # Capture before state
        old_row = self.schedule_df.loc[target_idx[0]]
        before = {
            'week': int(old_row['week']),
            'day': old_row['day'],
            'time_block': old_row['time_block'],
        }
        after = {
            'week': new_week,
            'day': new_day,
            'time_block': new_block,
        }

        # Apply to in-memory df
        self.schedule_df.loc[target_idx, 'week'] = new_week
        self.schedule_df.loc[target_idx, 'day'] = new_day
        self.schedule_df.loc[target_idx, 'time_block'] = new_block

        # Stage the change
        change = PendingChange(
            change_type='move_session',
            description=(
                f"{self._clean_subject(subject)} G{grupo} Práctica {session_num} : "
                f"S{before['week']} {before['day']} {before['time_block']} → "
                f"S{after['week']} {after['day']} {after['time_block']}"
            ),
            target={'subject': subject, 'grupo': grupo, 'session': session_num},
            before=before,
            after=after,
            warnings=result.warnings,
        )
        self.pending.append(change)

        return result

    def propose_move_group(
        self,
        subject: str,
        grupo: int,
        new_day: str,
        new_block: str,
    ) -> ValidationResult:
        """
        Validate AND stage a full-group move.

        Sessions keep their week numbers; only day+block change.
        """
        result = self._validate_group_move(subject, grupo, new_day, new_block)
        if not result.is_valid:
            return result

        target_mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
        )
        target_rows = self.schedule_df[target_mask]
        if len(target_rows) == 0:
            return ValidationResult(False, blockers=['Group not found'])

        old_day = target_rows.iloc[0]['day']
        old_block = target_rows.iloc[0]['time_block']

        # Apply to in-memory df
        self.schedule_df.loc[target_mask, 'day'] = new_day
        self.schedule_df.loc[target_mask, 'time_block'] = new_block

        # Also update group_composition.csv
        clean_subj = self._clean_subject(subject)
        grp_mask = (
            (self.groups_df['subject'] == clean_subj)
            & (self.groups_df['grupo'] == grupo)
        )
        self.groups_df.loc[grp_mask, 'day'] = new_day
        self.groups_df.loc[grp_mask, 'block'] = new_block

        change = PendingChange(
            change_type='move_group',
            description=(
                f"{clean_subj} G{grupo} (toutes sessions) : "
                f"{old_day} {old_block} → {new_day} {new_block}"
            ),
            target={'subject': subject, 'grupo': grupo},
            before={'day': old_day, 'time_block': old_block},
            after={'day': new_day, 'time_block': new_block},
            warnings=result.warnings,
        )
        self.pending.append(change)

        return result

    # ─────────────────────────────────────────────────────────────────────
    # SWAP STUDENTS BETWEEN GROUPS
    # ─────────────────────────────────────────────────────────────────────

    def _get_subject_family_members(self, subject: str) -> List[str]:
        """
        Return the list of subjects in the same shared_group family as `subject`.

        If the subject is not part of any family, returns [subject] (just itself).
        Only returns subjects that actually exist in the loaded schedule.
        """
        family_id = SUBJECT_TO_FAMILY.get(subject)
        if family_id is None:
            return [subject]
        # Filter to subjects that actually exist in the current schedule
        existing = set(self.schedule_df['subject'].unique())
        return [s for s in SHARED_GROUP_FAMILIES[family_id] if s in existing]

    def _student_is_in_group(self, student_id: str, subject: str, grupo: int) -> bool:
        """Check if a student is in (subject, grupo)."""
        students = self._get_students_in_group(subject, grupo)
        return str(student_id) in students

    def _get_group_slot(self, subject: str, grupo: int) -> Optional[Tuple[str, str]]:
        """
        Return the (day, time_block) at which a group is scheduled.

        Returns None if the group has no sessions. Uses the first session's slot
        as the canonical slot for the group (all sessions of a group share the
        same day+block in our pipeline).
        """
        mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
        )
        rows = self.schedule_df[mask]
        if len(rows) == 0:
            return None
        first_row = rows.iloc[0]
        return (first_row['day'], first_row['time_block'])

    def _is_student_free_at(
        self,
        student_id: str,
        day: str,
        time_block: str,
        exclude_subject: Optional[str] = None,
        exclude_grupo: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Check if a student is free at a given (day, time_block).

        A student is considered busy if:
        - They have an external course at that slot (from student_busy.csv), OR
        - They are in another lab group scheduled at that slot

        Args:
            exclude_subject/exclude_grupo: ignore conflicts in this specific group
                (used to exclude the group the student is being moved AWAY from)

        Returns:
            (is_free, reason) — reason is empty string if free
        """
        # Check external course conflicts
        day_idx = DAY_NAME_TO_INDEX.get(day, -1)
        block_idx = TIME_BLOCKS.index(time_block) + 1 if time_block in TIME_BLOCKS else -1

        if day_idx >= 0 and block_idx >= 0:
            busy_slots = self.student_busy.get(str(student_id), set())
            if (day_idx, block_idx) in busy_slots:
                return False, f"a un cours à {day} {time_block}"

        # Check lab group conflicts (other subjects/groups the student is in)
        if self.groups_df is None:
            return True, ''

        student_col = (
            'student_name' if 'student_name' in self.groups_df.columns
            else 'student_hash'
        )
        student_mask = self.groups_df[student_col].astype(str) == str(student_id)
        for _, row in self.groups_df[student_mask].iterrows():
            other_clean_subj = row['subject']
            other_grupo = int(row['grupo'])

            # Skip the excluded group (where the student is being moved FROM)
            if exclude_subject is not None and exclude_grupo is not None:
                if (self._clean_subject(exclude_subject) == other_clean_subj
                        and other_grupo == exclude_grupo):
                    continue

            # Find this group's slot in the schedule
            # We need to match S1_X or S2_X form, so search both
            for sem_prefix in ('S1_', 'S2_'):
                full_subj = f"{sem_prefix}{other_clean_subj}"
                slot = self._get_group_slot(full_subj, other_grupo)
                if slot is not None:
                    other_day, other_block = slot
                    if other_day == day and other_block == time_block:
                        return False, (
                            f"est dans {other_clean_subj} G{other_grupo} "
                            f"({day} {time_block})"
                        )
                    break

        return True, ''

    def _count_group_members(self, subject: str, grupo: int) -> int:
        """Count students in a (subject, grupo)."""
        return len(self._get_students_in_group(subject, grupo))

    def validate_swap(
        self,
        subject: str,
        grupo_a: int,
        student_a: str,
        grupo_b: int,
        student_b: Optional[str] = None,
        cascade_shared: bool = True,
    ) -> ValidationResult:
        """
        Validate a student swap between two groups WITHOUT applying it.

        Behavior:
        - If `student_b` is provided: swap student_a (in grupo_a) with student_b (in grupo_b)
        - If `student_b` is None: move student_a from grupo_a to grupo_b unilaterally

        Args:
            subject:         e.g. 'S1_Física'
            grupo_a:         source group of student_a
            student_a:       student identifier (student_name or student_hash)
            grupo_b:         destination group
            student_b:       optional, student identifier in grupo_b to swap with
            cascade_shared:  if True and the subject is part of a shared_group family,
                             the swap is validated across ALL subjects in the family

        Returns:
            ValidationResult with:
            - BLOCKERS: missing students, scheduling conflicts
            - WARNINGS: MAX/MIN group size violations, program mismatches
        """
        if not self.loaded:
            return ValidationResult(False, blockers=['Edit session not loaded'])

        blockers = []
        warnings = []

        # Determine which subjects this swap applies to
        if cascade_shared:
            subjects_to_check = self._get_subject_family_members(subject)
        else:
            subjects_to_check = [subject]

        # ───── Validate per-subject ─────
        for subj in subjects_to_check:
            # 1. Both students must exist in their respective groups
            if not self._student_is_in_group(student_a, subj, grupo_a):
                blockers.append(
                    f"{self._clean_subject(subj)}: l'étudiant {student_a} "
                    f"n'est pas dans G{grupo_a}"
                )
                continue

            if student_b is not None:
                if not self._student_is_in_group(student_b, subj, grupo_b):
                    blockers.append(
                        f"{self._clean_subject(subj)}: l'étudiant {student_b} "
                        f"n'est pas dans G{grupo_b}"
                    )
                    continue

            # 2. Get the slots of both groups
            slot_a = self._get_group_slot(subj, grupo_a)
            slot_b = self._get_group_slot(subj, grupo_b)
            if slot_a is None or slot_b is None:
                blockers.append(
                    f"{self._clean_subject(subj)}: groupe G{grupo_a} ou G{grupo_b} "
                    f"non planifié"
                )
                continue

            day_b, block_b = slot_b
            day_a, block_a = slot_a

            # 3. Student A moves to grupo_b's slot — check they're free there
            #    (excluding grupo_a since they're leaving it)
            free_a, reason_a = self._is_student_free_at(
                student_a, day_b, block_b,
                exclude_subject=subj, exclude_grupo=grupo_a,
            )
            if not free_a:
                blockers.append(
                    f"{self._clean_subject(subj)}: {student_a} ne peut pas rejoindre "
                    f"G{grupo_b} car il/elle {reason_a}"
                )

            # 4. Student B moves to grupo_a's slot — same check (only if swap)
            if student_b is not None:
                free_b, reason_b = self._is_student_free_at(
                    student_b, day_a, block_a,
                    exclude_subject=subj, exclude_grupo=grupo_b,
                )
                if not free_b:
                    blockers.append(
                        f"{self._clean_subject(subj)}: {student_b} ne peut pas rejoindre "
                        f"G{grupo_a} car il/elle {reason_b}"
                    )

            # 5. Group size warnings (only for unilateral move: swap preserves sizes)
            if student_b is None:
                size_a = self._count_group_members(subj, grupo_a)
                size_b = self._count_group_members(subj, grupo_b)
                # After move: grupo_a loses 1, grupo_b gains 1
                if size_a - 1 < MIN_GROUP_SIZE:
                    warnings.append(
                        f"{self._clean_subject(subj)}: G{grupo_a} passera à {size_a - 1} "
                        f"étudiant(s), en dessous du minimum recommandé ({MIN_GROUP_SIZE})"
                    )
                if size_b + 1 > MAX_GROUP_SIZE:
                    warnings.append(
                        f"{self._clean_subject(subj)}: G{grupo_b} passera à {size_b + 1} "
                        f"étudiant(s), au-dessus du maximum recommandé ({MAX_GROUP_SIZE})"
                    )

            # 6. Program coherence warning (if group_by_program=True in pipeline)
            # We check via the 'program' column in groups_df if present
            if 'program' in self.groups_df.columns and 'titulacion' in self.groups_df.columns:
                clean_subj = self._clean_subject(subj)
                # Get the dominant program of each group
                students_a = self.groups_df[
                    (self.groups_df['subject'] == clean_subj)
                    & (self.groups_df['grupo'] == grupo_a)
                ]
                students_b = self.groups_df[
                    (self.groups_df['subject'] == clean_subj)
                    & (self.groups_df['grupo'] == grupo_b)
                ]
                if len(students_a) > 0 and len(students_b) > 0:
                    program_a = students_a['titulacion'].mode().iloc[0] if 'titulacion' in students_a.columns and len(students_a['titulacion'].mode()) > 0 else ''
                    program_b = students_b['titulacion'].mode().iloc[0] if 'titulacion' in students_b.columns and len(students_b['titulacion'].mode()) > 0 else ''
                    if program_a and program_b and program_a != program_b:
                        # Check if student_a's program differs from group_b's dominant program
                        student_a_row = students_a[students_a[
                            'student_name' if 'student_name' in students_a.columns
                            else 'student_hash'
                        ].astype(str) == str(student_a)]
                        if len(student_a_row) > 0 and 'titulacion' in student_a_row.columns:
                            student_a_prog = student_a_row.iloc[0]['titulacion']
                            if student_a_prog != program_b:
                                warnings.append(
                                    f"{self._clean_subject(subj)}: {student_a} ({student_a_prog}) "
                                    f"rejoindra G{grupo_b} qui est majoritairement {program_b}"
                                )

        # Deduplicate
        blockers = list(dict.fromkeys(blockers))
        warnings = list(dict.fromkeys(warnings))

        return ValidationResult(
            is_valid=(len(blockers) == 0),
            blockers=blockers,
            warnings=warnings,
        )

    def propose_swap(
        self,
        subject: str,
        grupo_a: int,
        student_a: str,
        grupo_b: int,
        student_b: Optional[str] = None,
        cascade_shared: bool = True,
    ) -> ValidationResult:
        """
        Validate AND stage a student swap (or unilateral move).

        If validation passes:
            - For each subject in the cascade (or just the specified subject):
              the student(s) are reassigned in the in-memory groups_df
            - One PendingChange is created summarizing the swap

        Returns the ValidationResult.
        """
        result = self.validate_swap(
            subject, grupo_a, student_a, grupo_b, student_b, cascade_shared,
        )
        if not result.is_valid:
            return result

        # Determine subjects to apply this to
        if cascade_shared:
            subjects_to_apply = self._get_subject_family_members(subject)
        else:
            subjects_to_apply = [subject]

        # Apply to in-memory groups_df
        student_col = (
            'student_name' if 'student_name' in self.groups_df.columns
            else 'student_hash'
        )

        for subj in subjects_to_apply:
            clean_subj = self._clean_subject(subj)

            # Move student_a from grupo_a to grupo_b
            mask_a = (
                (self.groups_df['subject'] == clean_subj)
                & (self.groups_df['grupo'] == grupo_a)
                & (self.groups_df[student_col].astype(str) == str(student_a))
            )
            self.groups_df.loc[mask_a, 'grupo'] = grupo_b
            # Update day/block to match grupo_b's slot
            slot_b = self._get_group_slot(subj, grupo_b)
            if slot_b is not None:
                self.groups_df.loc[mask_a, 'day'] = slot_b[0]
                self.groups_df.loc[mask_a, 'block'] = slot_b[1]

            # Move student_b from grupo_b to grupo_a (if swap)
            if student_b is not None:
                mask_b = (
                    (self.groups_df['subject'] == clean_subj)
                    & (self.groups_df['grupo'] == grupo_b)
                    & (self.groups_df[student_col].astype(str) == str(student_b))
                )
                self.groups_df.loc[mask_b, 'grupo'] = grupo_a
                slot_a = self._get_group_slot(subj, grupo_a)
                if slot_a is not None:
                    self.groups_df.loc[mask_b, 'day'] = slot_a[0]
                    self.groups_df.loc[mask_b, 'block'] = slot_a[1]

        # Build the description
        clean_subj_label = self._clean_subject(subject)
        subjects_label = (
            ' + '.join(self._clean_subject(s) for s in subjects_to_apply)
            if cascade_shared and len(subjects_to_apply) > 1
            else clean_subj_label
        )

        if student_b is not None:
            desc = (
                f"Swap {student_a} ↔ {student_b} : "
                f"G{grupo_a} ↔ G{grupo_b} sur {subjects_label}"
            )
        else:
            desc = (
                f"Déplacement {student_a} : "
                f"G{grupo_a} → G{grupo_b} sur {subjects_label}"
            )

        change = PendingChange(
            change_type='swap_students',
            description=desc,
            target={
                'subject':         subject,
                'grupo_a':         grupo_a,
                'student_a':       student_a,
                'grupo_b':         grupo_b,
                'student_b':       student_b,
                'cascade_shared':  cascade_shared,
                'subjects_applied': subjects_to_apply,
            },
            before={},   # Not used for swap; description tells the story
            after={},
            warnings=result.warnings,
        )
        self.pending.append(change)

        return result

    def list_students_in_group(self, subject: str, grupo: int) -> List[Dict]:
        """
        List students in a (subject, grupo), sorted by name.

        Returns a list of dicts: {'id', 'name', 'titulacion'}.
        Useful for the UI to populate the student dropdowns.
        """
        if not self.loaded:
            return []
        clean_subj = self._clean_subject(subject)
        mask = (
            (self.groups_df['subject'] == clean_subj)
            & (self.groups_df['grupo'] == grupo)
        )
        rows = self.groups_df[mask]
        if len(rows) == 0:
            return []

        student_col = (
            'student_name' if 'student_name' in self.groups_df.columns
            else 'student_hash'
        )
        has_titulacion = 'titulacion' in self.groups_df.columns

        results = []
        for _, r in rows.iterrows():
            entry = {
                'id': str(r[student_col]),
                'name': str(r[student_col]),
                'titulacion': str(r['titulacion']) if has_titulacion else '',
            }
            results.append(entry)

        # Sort by name (case-insensitive)
        results.sort(key=lambda x: x['name'].lower())
        return results

    def list_all_groups(self, subject: str) -> List[Dict]:
        """
        List all groups of a subject with their key info.

        Returns: [{'grupo', 'day', 'block', 'size'}, ...]
        """
        if not self.loaded:
            return []

        clean_subj = self._clean_subject(subject)
        all_groups = sorted(self.groups_df[
            self.groups_df['subject'] == clean_subj
        ]['grupo'].unique().tolist())

        results = []
        for g in all_groups:
            slot = self._get_group_slot(subject, int(g))
            size = self._count_group_members(subject, int(g))
            results.append({
                'grupo':  int(g),
                'day':    slot[0] if slot else '',
                'block':  slot[1] if slot else '',
                'size':   size,
            })
        return results

    # ─────────────────────────────────────────────────────────────────────
    # PENDING BASKET MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────

    def list_pending(self) -> List[PendingChange]:
        """Return all currently staged changes."""
        return list(self.pending)

    def discard_pending(self, index: int) -> bool:
        """
        Remove one staged change by index. The in-memory state is rolled back
        to the original loaded state and then all OTHER pending changes are
        re-applied (since changes can depend on each other).
        """
        if index < 0 or index >= len(self.pending):
            return False

        # Rebuild state: reload, then replay all changes except `index`
        kept = [c for i, c in enumerate(self.pending) if i != index]
        self.pending = []
        self.schedule_df = self._original_schedule_df.copy()
        self.groups_df = self._original_groups_df.copy()
        for change in kept:
            self._replay_change(change)
        return True

    def discard_all_pending(self) -> None:
        """Discard all pending changes and revert to the loaded state."""
        self.pending = []
        if self._original_schedule_df is not None:
            self.schedule_df = self._original_schedule_df.copy()
        if self._original_groups_df is not None:
            self.groups_df = self._original_groups_df.copy()

    def _replay_change(self, change: PendingChange) -> None:
        """
        Re-apply a previously-validated change to the in-memory dataframe.
        Used when reconstructing state after discarding one change.
        """
        if change.change_type == 'move_session':
            t = change.target
            mask = (
                (self.schedule_df['subject'] == t['subject'])
                & (self.schedule_df['grupo'] == t['grupo'])
                & (self.schedule_df['session'] == t['session'])
            )
            self.schedule_df.loc[mask, 'week'] = change.after['week']
            self.schedule_df.loc[mask, 'day'] = change.after['day']
            self.schedule_df.loc[mask, 'time_block'] = change.after['time_block']
        elif change.change_type == 'move_group':
            t = change.target
            mask = (
                (self.schedule_df['subject'] == t['subject'])
                & (self.schedule_df['grupo'] == t['grupo'])
            )
            self.schedule_df.loc[mask, 'day'] = change.after['day']
            self.schedule_df.loc[mask, 'time_block'] = change.after['time_block']
            clean_subj = self._clean_subject(t['subject'])
            grp_mask = (
                (self.groups_df['subject'] == clean_subj)
                & (self.groups_df['grupo'] == t['grupo'])
            )
            self.groups_df.loc[grp_mask, 'day'] = change.after['day']
            self.groups_df.loc[grp_mask, 'block'] = change.after['time_block']
        elif change.change_type == 'swap_students':
            t = change.target
            # Re-invoke propose_swap to apply the change; pop our duplicate
            # entry since propose_swap will append a fresh one.
            self.propose_swap(
                subject=t['subject'],
                grupo_a=t['grupo_a'], student_a=t['student_a'],
                grupo_b=t['grupo_b'], student_b=t.get('student_b'),
                cascade_shared=t.get('cascade_shared', True),
            )
            # propose_swap already appended a new PendingChange; we'll restore
            # the original 'change' object below by popping the duplicate.
            if self.pending and self.pending[-1].change_type == 'swap_students':
                self.pending.pop()
            return  # The change is appended via the fallthrough below

        # Restore staged status (without re-validation)
        self.pending.append(change)

    # ─────────────────────────────────────────────────────────────────────
    # COMMIT
    # ─────────────────────────────────────────────────────────────────────

    def commit(self, label: str = '', description: str = '') -> Tuple[bool, str]:
        """
        Persist all staged changes:
            1. Create a snapshot of the CURRENT (pre-commit) disk state
            2. Write the in-memory dataframes to disk
            3. Clear the pending basket

        Args:
            label:       short label for the snapshot (e.g. "Pedro fix")
            description: longer description

        Returns:
            (success, message) tuple.
        """
        if not self.loaded:
            return False, "Edit session not loaded"
        if not self.pending:
            return False, "No pending changes to commit"

        # Step 1: snapshot the current disk state BEFORE we overwrite
        try:
            import version_manager as vm
            n_changes = len(self.pending)
            desc = (description or
                    f"Avant édition manuelle : {n_changes} modification(s) en attente")
            vm.create_snapshot(snapshot_type='auto', description=desc)
        except ImportError:
            # version_manager not available — proceed without snapshot
            pass
        except Exception as exc:
            # Non-blocking but worth surfacing
            return False, f"Échec snapshot pré-commit : {exc}"

        # Step 2: write the in-memory state to disk
        try:
            self.schedule_df.to_csv(SCHEDULE_CSV_PATH, index=False, encoding='utf-8-sig')
            self.groups_df.to_csv(GROUPS_CSV_PATH, index=False, encoding='utf-8-sig')
        except Exception as exc:
            return False, f"Échec écriture disque : {exc}"

        # Step 3: snapshot the NEW state (so user has a marker for "after edit")
        try:
            import version_manager as vm
            commit_label = label or f"Édition manuelle : {n_changes} modif(s)"
            # Pass the user-provided label so the snapshot uses an intuitive
            # name (e.g. 'Distribucion_Practicas_25-26_rev15'); falls back to
            # auto-generated default if `label` is empty.
            vm.create_snapshot(
                snapshot_type='milestone',
                description=commit_label,
                label=label if label else None,
            )
        except (ImportError, Exception):
            pass

        # Step 4: clear basket and refresh originals to reflect the new state
        committed_count = len(self.pending)
        self.pending = []
        self._original_schedule_df = self.schedule_df.copy()
        self._original_groups_df = self.groups_df.copy()

        return True, f"{committed_count} modification(s) appliquée(s) avec succès"

    # ─────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def _clean_subject(self, subject: str) -> str:
        """Strip 'S1_' or 'S2_' prefix from a subject name."""
        return subject.replace('S1_', '').replace('S2_', '')

    def _parse_rooms(self, room_str) -> Set[str]:
        """Parse a comma-separated room string into a set of cleaned names."""
        if pd.isna(room_str):
            return set()
        parts = str(room_str).split(',')
        return {p.strip() for p in parts if p.strip()}

    def _get_students_in_group(self, subject: str, grupo: int) -> Set[str]:
        """
        Return the set of student identifiers in a given (subject, grupo).

        The group_composition.csv uses subject names without the 'S1_'/'S2_'
        prefix, so we strip it for matching.
        """
        if self.groups_df is None:
            return set()
        clean_subj = self._clean_subject(subject)
        mask = (
            (self.groups_df['subject'] == clean_subj)
            & (self.groups_df['grupo'] == grupo)
        )
        rows = self.groups_df[mask]
        if len(rows) == 0:
            return set()

        # The student identifier column varies (student_name or student_hash)
        student_col = (
            'student_name' if 'student_name' in self.groups_df.columns
            else 'student_hash'
        )
        return set(rows[student_col].astype(str))

    # ─────────────────────────────────────────────────────────────────────
    # SUMMARY / LISTING
    # ─────────────────────────────────────────────────────────────────────

    def list_subjects(self) -> List[str]:
        """Return all distinct subjects in the schedule."""
        if not self.loaded:
            return []
        return sorted(self.schedule_df['subject'].unique().tolist())

    def list_groups(self, subject: str) -> List[int]:
        """Return all distinct group numbers for a given subject."""
        if not self.loaded:
            return []
        mask = self.schedule_df['subject'] == subject
        return sorted(self.schedule_df[mask]['grupo'].unique().tolist())

    def list_sessions(self, subject: str, grupo: int) -> List[Dict]:
        """
        Return all sessions of a given group, sorted by session number.

        Each entry is a dict with: session, week, day, time_block, lab_rooms.
        """
        if not self.loaded:
            return []
        mask = (
            (self.schedule_df['subject'] == subject)
            & (self.schedule_df['grupo'] == grupo)
        )
        rows = self.schedule_df[mask].sort_values('session')
        return [
            {
                'session': int(r['session']),
                'week': int(r['week']),
                'day': r['day'],
                'time_block': r['time_block'],
                'lab_rooms': r['lab_rooms'],
            }
            for _, r in rows.iterrows()
        ]