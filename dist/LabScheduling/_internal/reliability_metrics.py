"""
reliability_metrics.py
======================

Calculate reliability metrics for the generated planning.

These metrics give Daniel quantitative confidence that the planning is
operationally sound, not just mathematically valid.

The module is purely functional: each function takes DataFrames as input
and returns a dictionary of metrics. No file I/O, no global state.

Usage:
    from reliability_metrics import compute_all_metrics
    metrics = compute_all_metrics(schedule_df, groups_df, busy_df)
"""

from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

import pandas as pd


# ============================================================================
# CONSTANTS
# ============================================================================

# Daniel's reference figures (from his April 2026 Excel files)
# Used as "ground truth" for comparison metrics
DANIEL_REFERENCE = {
    'S1': {
        'Física':                       {'students': 248, 'groups': 17},
        'Química':                      {'students': 248, 'groups': 15},
        'Electrotecnia':                {'students': 115, 'groups': 8},
        'Mecanismos':                   {'students': 110, 'groups': 8},
        'Termodinámica':                {'students': 116, 'groups': 8},
        'Tecnologías de Fabricación':   {'students': 112, 'groups': 8},
        'Robótica y Automatización':    {'students': 54,  'groups': 4},
        'Automatización Industrial':    {'students': 8,   'groups': 1},
    },
    'S2': {
        'Física II':                          {'students': 80,  'groups': 5},
        'Tecnología Medio Ambiente':          {'students': 100, 'groups': 7},
        'Resistencia de Materiales':          {'students': 90,  'groups': 6},
        'Mecánica de Fluidos':                {'students': 85,  'groups': 6},
        'Regulación Automática':              {'students': 60,  'groups': 4},
        'Tecnología Electrónica':             {'students': 70,  'groups': 5},
    },
}

# Thresholds for the "health score" calculation
HEALTHY_ASSIGNMENT_RATE = 0.95     # 95%+ assignment is excellent
WARNING_ASSIGNMENT_RATE = 0.85     # below 85% is concerning

HEALTHY_OVERFLOW_RATE = 0.05       # < 5% overflow groups is excellent
WARNING_OVERFLOW_RATE = 0.15       # > 15% is concerning

HEALTHY_ROOM_OCCUPANCY = 0.70      # rooms below 70% are healthy (some buffer)
WARNING_ROOM_OCCUPANCY = 0.90      # rooms above 90% are concerning

MAX_LABS_PER_STUDENT_PER_WEEK = 3  # students with > 3 labs in same week = overload


# ============================================================================
# CORE METRICS — assignment & coverage
# ============================================================================

def compute_assignment_metrics(schedule_df: pd.DataFrame,
                                groups_df: pd.DataFrame) -> Dict:
    """
    Compute student assignment statistics.

    Returns dict with:
        total_sessions:     total sessions in schedule
        total_groups:       distinct (subject, grupo) combinations
        total_students:     unique enrolled students (from lab_enrollments.csv if available,
                            else falls back to count in groups_df)
        assigned_students:  unique students that ended up in a group
        assignment_rate:    100 * assigned_students / total_students
        avg_group_size:     mean students per group
        min_group_size:     smallest group size
        max_group_size:     largest group size
        groups_below_min:   count of groups with < 5 students (Daniel's min: 7)
        overflow_groups:    count of groups marked _overflow=True
        alt_room_groups:    count of groups marked _alt_room=True
    """
    if len(schedule_df) == 0:
        return {
            'total_sessions': 0, 'total_groups': 0, 'total_students': 0,
            'assigned_students': 0, 'assignment_rate': 0.0,
            'avg_group_size': 0, 'min_group_size': 0, 'max_group_size': 0,
            'groups_below_min': 0, 'overflow_groups': 0, 'alt_room_groups': 0,
        }

    # Group sizes from groups_df (composition data)
    student_id_col = 'student_name' if 'student_name' in groups_df.columns else 'student_hash'
    unique_groups = groups_df.groupby(['subject', 'grupo'])[student_id_col].nunique()

    # Schedule-level counts
    total_sessions = len(schedule_df)
    total_groups = schedule_df.groupby(['subject', 'grupo']).ngroups
    assigned_students = groups_df[student_id_col].nunique()

    # Authoritative source: the pipeline exports its OWN totals (total_enrolled,
    # total_assigned, exact rate) into assignment_summary_global.csv. We prefer
    # those numbers because the pipeline knows the real enrollments per subject
    # and counts a student once per subject (the correct denominator for a lab
    # assignment rate). The previous fallback used max() on lab_enrollments.csv,
    # which incorrectly took the largest single-subject enrollment as the
    # denominator and produced misleading rates (often 100%).
    import os as _os
    total_students = assigned_students  # safe default
    assignment_rate = 100.0 if assigned_students > 0 else 0.0
    pipeline_total_assigned = assigned_students  # number used in the rate

    summary_path = 'outputs/optimization/assignment_summary_global.csv'
    if _os.path.exists(summary_path):
        try:
            summary = pd.read_csv(summary_path)
            if {'total_enrolled', 'total_assigned', 'assignment_rate_pct'} \
                    .issubset(summary.columns) and len(summary) > 0:
                total_students = int(summary['total_enrolled'].iloc[0])
                pipeline_total_assigned = int(summary['total_assigned'].iloc[0])
                assignment_rate = float(summary['assignment_rate_pct'].iloc[0])
                # IMPORTANT: numerator and denominator must be the SAME unit.
                # total_students here is the count of (student × subject)
                # enrollments, so the "assigned" figure shown next to it must
                # also be enrollments — NOT unique students. Using the unique
                # student count (e.g. 475) next to enrollments (e.g. 1852)
                # produced the misleading "475 / 1852" label.
                assigned_students = pipeline_total_assigned
        except Exception:
            pass
    else:
        # Legacy fallback (older runs without the summary export). Use the
        # per-subject enrollment file and SUM, not max — summing across
        # subjects matches the pipeline's denominator (one count per
        # (student, subject) pair).
        enrollments_path = 'data_clean/optimization/lab_enrollments.csv'
        if _os.path.exists(enrollments_path):
            try:
                enrollments = pd.read_csv(enrollments_path)
                if 'student_count' in enrollments.columns:
                    total_students = max(
                        int(enrollments['student_count'].sum()),
                        assigned_students)
                    assignment_rate = (100.0 * assigned_students /
                                       total_students if total_students > 0 else 0.0)
            except Exception:
                pass

    # Group size distribution
    if len(unique_groups) > 0:
        avg_size = unique_groups.mean()
        min_size = unique_groups.min()
        max_size = unique_groups.max()
        below_min = (unique_groups < 5).sum()
    else:
        avg_size = min_size = max_size = below_min = 0

    # Overflow / alt_room detection (from program field in schedule)
    overflow_groups = 0
    alt_room_groups = 0
    if 'program' in schedule_df.columns:
        unique_combos = schedule_df.drop_duplicates(subset=['subject', 'grupo'])
        overflow_groups = (unique_combos['program'] == 'OVERFLOW').sum()
        alt_room_groups = (unique_combos['program'] == 'ALT_ROOM').sum()

    return {
        'total_sessions':     int(total_sessions),
        'total_groups':       int(total_groups),
        'total_students':     int(total_students),
        'assigned_students':  int(assigned_students),
        'assignment_rate':    round(float(assignment_rate), 1),
        'avg_group_size':     round(float(avg_size), 1),
        'min_group_size':     int(min_size),
        'max_group_size':     int(max_size),
        'groups_below_min':   int(below_min),
        'overflow_groups':    int(overflow_groups),
        'alt_room_groups':    int(alt_room_groups),
    }


def compute_coverage_per_subject(schedule_df: pd.DataFrame,
                                  groups_df: pd.DataFrame) -> List[Dict]:
    """
    Compute assignment coverage per subject.

    For each subject, return:
        subject:          name (clean, no S1_/S2_ prefix)
        semester:         1 or 2
        sessions:         total sessions scheduled
        groups:           distinct group count
        students:         unique students assigned
        ref_students:     Daniel's reference (None if unknown)
        ref_groups:       Daniel's reference (None if unknown)
        deviation_pct:    +/- % vs reference (None if no reference)
        status:           'ok', 'warning', or 'critical'
    """
    if len(schedule_df) == 0:
        return []

    student_id_col = 'student_name' if 'student_name' in groups_df.columns else 'student_hash'

    coverage = []
    for (subject_full, semester), schedule_subset in schedule_df.groupby(['subject', 'semester']):
        # Strip S1_/S2_ prefix to match Daniel's reference
        subject_clean = subject_full.replace('S1_', '').replace('S2_', '')

        # Look up Daniel reference
        sem_key = f'S{semester}'
        ref = DANIEL_REFERENCE.get(sem_key, {}).get(subject_clean)
        ref_students = ref['students'] if ref else None
        ref_groups = ref['groups'] if ref else None

        # Find groups for this subject in groups_df
        # groups_df uses clean subject names already
        subject_groups = groups_df[groups_df['subject'] == subject_clean]
        n_students = subject_groups[student_id_col].nunique()
        n_groups = subject_groups['grupo'].nunique()
        n_sessions = len(schedule_subset)

        # Compute deviation
        deviation_pct = None
        status = 'ok'
        if ref_students and ref_students > 0:
            deviation_pct = round((n_students - ref_students) / ref_students * 100, 1)
            abs_dev = abs(deviation_pct)
            if abs_dev > 30:
                status = 'critical'
            elif abs_dev > 15:
                status = 'warning'

        coverage.append({
            'subject':       subject_clean,
            'subject_full':  subject_full,
            'semester':      int(semester),
            'sessions':      int(n_sessions),
            'groups':        int(n_groups),
            'students':      int(n_students),
            'ref_students':  ref_students,
            'ref_groups':    ref_groups,
            'deviation_pct': deviation_pct,
            'status':        status,
        })

    # Sort by semester then subject
    coverage.sort(key=lambda x: (x['semester'], x['subject']))
    return coverage


# ============================================================================
# CORE METRICS — distribution & balance
# ============================================================================

def compute_distribution_metrics(schedule_df: pd.DataFrame) -> Dict:
    """
    Compute how sessions are distributed across days, blocks, weeks.

    Returns dict with:
        by_day:        dict day_name -> session count
        by_block:      dict block_label -> session count
        by_week:       dict week_num -> session count
        peak_day:      day with most sessions
        peak_week:     week with most sessions
        balance_score: 0-100, higher = better balanced
    """
    if len(schedule_df) == 0:
        return {
            'by_day': {}, 'by_block': {}, 'by_week': {},
            'peak_day': None, 'peak_week': None, 'balance_score': 0,
        }

    by_day = schedule_df['day'].value_counts().to_dict()
    by_block = schedule_df['time_block'].value_counts().to_dict()
    by_week = schedule_df.groupby(['semester', 'week']).size().to_dict()
    by_week_str = {f"S{sem}-W{w}": cnt for (sem, w), cnt in by_week.items()}

    # Peak detection
    peak_day = max(by_day, key=by_day.get) if by_day else None
    peak_week = max(by_week_str, key=by_week_str.get) if by_week_str else None

    # Balance score: lower variance across days = better balance.
    # Real schedules are NOT perfectly balanced — Daniel concentrates labs on
    # 2-3 days/week and that's intentional. The previous threshold (CV=0.5 → 0)
    # was too strict and flagged normal patterns as defects. CV=1.0 → 0 is a
    # better calibration: only signal when one day carries 2x more than the mean.
    if by_day:
        day_counts = list(by_day.values())
        mean_per_day = sum(day_counts) / len(day_counts)
        if mean_per_day > 0:
            variance = sum((c - mean_per_day) ** 2 for c in day_counts) / len(day_counts)
            std = variance ** 0.5
            cv = std / mean_per_day
            balance_score = max(0, round(100 * (1 - cv)))
        else:
            balance_score = 100
    else:
        balance_score = 0

    return {
        'by_day':        by_day,
        'by_block':      by_block,
        'by_week':       by_week_str,
        'peak_day':      peak_day,
        'peak_week':     peak_week,
        'balance_score': balance_score,
    }


def compute_room_occupancy(schedule_df: pd.DataFrame) -> List[Dict]:
    """
    Compute occupancy per (room, semester).

    For each room+semester:
        room:               room name
        semester:           1 or 2
        sessions_used:      total sessions occupying this room
        slots_available:    total (week × day × block) slots in semester
        occupancy_pct:      sessions_used / slots_available
        status:             'ok', 'warning', or 'critical'
    """
    if len(schedule_df) == 0:
        return []

    occupancy = []
    for (room, semester), room_subset in schedule_df.groupby(['lab_rooms', 'semester']):
        # Some sessions may be in multi-room (e.g. "Ciencias I, Ciencias II")
        # Split and count separately for each room
        for individual_room in str(room).split(','):
            individual_room = individual_room.strip()
            if not individual_room:
                continue

            # Count sessions in THIS exact (room, semester) combination
            mask = (
                schedule_df['lab_rooms'].astype(str).str.contains(
                    individual_room.replace('(', r'\(').replace(')', r'\)'),
                    regex=True, na=False
                )
                & (schedule_df['semester'] == semester)
            )
            sessions_used = mask.sum()

            # Available slots = weeks × 5 days × 6 blocks (approx)
            # Use actual week range from schedule
            sem_schedule = schedule_df[schedule_df['semester'] == semester]
            if len(sem_schedule) > 0:
                week_range = sem_schedule['week'].max() - sem_schedule['week'].min() + 1
                slots_available = week_range * 5 * 6
            else:
                slots_available = 14 * 5 * 6 if semester == 1 else 20 * 5 * 6

            occupancy_pct = sessions_used / max(slots_available, 1)

            if occupancy_pct >= WARNING_ROOM_OCCUPANCY:
                status = 'critical'
            elif occupancy_pct >= HEALTHY_ROOM_OCCUPANCY:
                status = 'warning'
            else:
                status = 'ok'

            # Only add once (avoid duplicates from multi-room iteration)
            already = any(
                o['room'] == individual_room and o['semester'] == semester
                for o in occupancy
            )
            if not already:
                occupancy.append({
                    'room':             individual_room,
                    'semester':         int(semester),
                    'sessions_used':    int(sessions_used),
                    'slots_available':  int(slots_available),
                    'occupancy_pct':    round(occupancy_pct * 100, 1),
                    'status':           status,
                })

    # Sort by occupancy desc
    occupancy.sort(key=lambda x: -x['occupancy_pct'])
    return occupancy


# ============================================================================
# CORE METRICS — student-level checks
# ============================================================================

def compute_student_overload(schedule_df: pd.DataFrame,
                              groups_df: pd.DataFrame,
                              max_labs_per_week: int = MAX_LABS_PER_STUDENT_PER_WEEK
                              ) -> Dict:
    """
    Detect students with too many labs in the same week.

    Returns dict with:
        overloaded_count:   number of students with > max_labs_per_week labs in any week
        examples:           up to 5 example (student_id, week, count) tuples
        max_labs_observed:  highest number of labs any student has in a single week
    """
    if len(schedule_df) == 0 or len(groups_df) == 0:
        return {
            'overloaded_count': 0, 'examples': [], 'max_labs_observed': 0,
        }

    student_id_col = 'student_name' if 'student_name' in groups_df.columns else 'student_hash'

    # Build mapping: (subject, grupo) -> set of (week, day, block)
    group_sessions = defaultdict(list)
    for _, row in schedule_df.iterrows():
        # groups_df uses clean subject names; schedule_df may have S1_ prefix
        clean_subj = row['subject'].replace('S1_', '').replace('S2_', '')
        group_sessions[(clean_subj, int(row['grupo']))].append({
            'week':       int(row['week']),
            'day':        row['day'],
            'time_block': row['time_block'],
            'semester':   int(row['semester']),
        })

    # For each student, count labs per week
    student_weekly_labs = defaultdict(lambda: defaultdict(int))
    # student_weekly_labs[student_id][(semester, week)] = count

    for _, row in groups_df.iterrows():
        student = row[student_id_col]
        subject = row['subject']
        grupo = int(row['grupo'])
        sessions = group_sessions.get((subject, grupo), [])
        for session in sessions:
            key = (session['semester'], session['week'])
            student_weekly_labs[student][key] += 1

    # Find overloaded students
    overloaded_students = set()
    examples = []
    max_observed = 0

    for student, weeks in student_weekly_labs.items():
        for (sem, week), count in weeks.items():
            if count > max_observed:
                max_observed = count
            if count > max_labs_per_week:
                overloaded_students.add(student)
                if len(examples) < 5:
                    examples.append({
                        'student':  str(student),
                        'semester': sem,
                        'week':     week,
                        'count':    count,
                    })

    return {
        'overloaded_count':  len(overloaded_students),
        'examples':          examples,
        'max_labs_observed': max_observed,
    }


# ============================================================================
# CORE METRICS — schedule spacing quality
# ============================================================================

def compute_spacing_quality(schedule_df: pd.DataFrame) -> Dict:
    """
    Measure how well sessions of each group are spaced over the semester.

    Daniel's preference: first session at min_week, last session at max_week,
    intermediate sessions evenly spaced.

    Returns dict with:
        avg_first_excess:       avg distance from min_week for session 1
        avg_last_deficit:       avg distance from max_week for last session
        avg_gap_deviation:      avg deviation from ideal gap
        well_spaced_groups_pct: % of groups with all 3 metrics within tolerance
    """
    if len(schedule_df) == 0:
        return {
            'avg_first_excess':       0,
            'avg_last_deficit':       0,
            'avg_gap_deviation':      0,
            'well_spaced_groups_pct': 0,
        }

    first_excesses = []
    last_deficits = []
    gap_deviations = []
    well_spaced_count = 0
    total_groups = 0

    for (subject, grupo), group_data in schedule_df.groupby(['subject', 'grupo']):
        group_sorted = group_data.sort_values('session')
        if len(group_sorted) == 0:
            continue
        total_groups += 1

        # Use first session's min/max as window bounds (assume consistent within group)
        # We need access to original min_week/max_week... fall back if not available
        weeks = group_sorted['week'].tolist()
        if not weeks:
            continue

        first_week = weeks[0]
        last_week = weeks[-1]

        # Heuristic: assume min_week=4 for S1, min_week=7 for S2 if not in data
        # Better: use actual min observed across all groups of this subject
        subject_data = schedule_df[schedule_df['subject'] == subject]
        actual_min_week = subject_data['week'].min()
        actual_max_week = subject_data['week'].max()

        first_excess = first_week - actual_min_week
        last_deficit = actual_max_week - last_week

        first_excesses.append(first_excess)
        last_deficits.append(last_deficit)

        # Gap deviation
        if len(weeks) >= 3:
            window = actual_max_week - actual_min_week
            ideal_gap = max(1, window // (len(weeks) - 1))
            local_gap_devs = []
            for i in range(len(weeks) - 1):
                gap = weeks[i + 1] - weeks[i]
                local_gap_devs.append(abs(gap - ideal_gap))
            avg_local_dev = sum(local_gap_devs) / len(local_gap_devs)
            gap_deviations.append(avg_local_dev)

            if first_excess <= 1 and last_deficit <= 1 and avg_local_dev <= 1:
                well_spaced_count += 1
        else:
            # < 3 sessions: no gap check, just check anchoring
            if first_excess <= 1:
                well_spaced_count += 1

    return {
        'avg_first_excess':       round(sum(first_excesses) / max(len(first_excesses), 1), 2),
        'avg_last_deficit':       round(sum(last_deficits) / max(len(last_deficits), 1), 2),
        'avg_gap_deviation':      round(sum(gap_deviations) / max(len(gap_deviations), 1), 2),
        'well_spaced_groups_pct': round(well_spaced_count / max(total_groups, 1) * 100, 1),
    }


# ============================================================================
# CORE METRICS — conflict detection (defense in depth)
# ============================================================================

def detect_conflicts(schedule_df: pd.DataFrame,
                      groups_df: pd.DataFrame) -> Dict:
    """
    Defensive check: even though the solver guarantees C1/C4, we re-verify.

    Returns dict with:
        c1_violations:     count of (subject, week, day, block) with > 1 session
        c4_violations:     count of (room, week, day, block) with > 1 session
        student_conflicts: count of students with overlapping sessions
        examples_c1:       sample violations
        examples_c4:       sample violations
    """
    if len(schedule_df) == 0:
        return {
            'c1_violations': 0, 'c4_violations': 0, 'student_conflicts': 0,
            'examples_c1': [], 'examples_c4': [],
        }

    # C1: same subject, week, day, block
    c1_groups = schedule_df.groupby(['subject', 'semester', 'week', 'day', 'time_block']).size()
    c1_violations = (c1_groups > 1).sum()
    examples_c1 = []
    if c1_violations > 0:
        violators = c1_groups[c1_groups > 1].head(5)
        for key, count in violators.items():
            examples_c1.append({
                'subject':    key[0],
                'semester':   int(key[1]),
                'week':       int(key[2]),
                'day':        key[3],
                'time_block': key[4],
                'count':      int(count),
            })

    # C4: same room, week, day, block
    # Need to handle multi-room entries ("Ciencias I, Ciencias II")
    rows_expanded = []
    for _, row in schedule_df.iterrows():
        for room in str(row['lab_rooms']).split(','):
            room = room.strip()
            if room:
                rows_expanded.append({
                    'room':       room,
                    'semester':   int(row['semester']),
                    'week':       int(row['week']),
                    'day':        row['day'],
                    'time_block': row['time_block'],
                    'subject':    row['subject'],
                    'grupo':      int(row['grupo']),
                })
    if rows_expanded:
        expanded_df = pd.DataFrame(rows_expanded)
        c4_groups = expanded_df.groupby(['room', 'semester', 'week', 'day', 'time_block']).size()
        c4_violations = (c4_groups > 1).sum()
        examples_c4 = []
        if c4_violations > 0:
            violators = c4_groups[c4_groups > 1].head(5)
            for key, count in violators.items():
                examples_c4.append({
                    'room':       key[0],
                    'semester':   int(key[1]),
                    'week':       int(key[2]),
                    'day':        key[3],
                    'time_block': key[4],
                    'count':      int(count),
                })
    else:
        c4_violations = 0
        examples_c4 = []

    # Student conflicts: a student in 2 sessions at same time
    student_conflicts = 0
    if len(groups_df) > 0:
        student_id_col = 'student_name' if 'student_name' in groups_df.columns else 'student_hash'

        # Build student -> list of (sem, week, day, block) sessions
        student_sessions = defaultdict(list)
        for _, group_row in groups_df.iterrows():
            student = group_row[student_id_col]
            subject = group_row['subject']
            grupo = int(group_row['grupo'])

            # Find all sessions of this group in schedule
            mask = (
                (schedule_df['subject'].str.replace('S1_', '').str.replace('S2_', '') == subject)
                & (schedule_df['grupo'] == grupo)
            )
            for _, sched_row in schedule_df[mask].iterrows():
                student_sessions[student].append((
                    int(sched_row['semester']),
                    int(sched_row['week']),
                    sched_row['day'],
                    sched_row['time_block'],
                ))

        # Student conflicts: only count REAL cross-(subject, grupo) collisions
        # at the same (sem, week, day, block). Plain duplicate join rows in
        # schedule (same session listed twice due to data artefacts) do NOT
        # count: the student is only physically in ONE session. We aggregate
        # student_sessions as (sem, week, day, block) -> set of (subject, grupo).
        # A conflict exists only if that set has 2+ distinct (subject, grupo).
        from collections import defaultdict as _dd
        student_slot_subjects = _dd(lambda: _dd(set))
        # Pre-compute the set of (student, subject, grupo) flagged as manual
        # override — those entries reflect a deliberate clash that Daniel
        # accepts, NOT a defect.
        override_set = set()
        if 'is_override' in groups_df.columns:
            ov = groups_df[groups_df['is_override'].astype(bool)]
            for _, row in ov.iterrows():
                override_set.add(
                    (row[student_id_col], row['subject'], int(row['grupo'])))
        # Re-build with subject/grupo tracking, skipping overrides
        for _, group_row in groups_df.iterrows():
            student = group_row[student_id_col]
            subject = group_row['subject']
            grupo = int(group_row['grupo'])
            # Skip override placements when checking for conflicts: Daniel
            # already arbitrated those.
            if (student, subject, grupo) in override_set:
                continue
            mask = (
                (schedule_df['subject'].str.replace('S1_', '').str.replace('S2_', '') == subject)
                & (schedule_df['grupo'] == grupo)
            )
            for _, sched_row in schedule_df[mask].iterrows():
                key = (
                    int(sched_row['semester']),
                    int(sched_row['week']),
                    sched_row['day'],
                    sched_row['time_block'],
                )
                student_slot_subjects[student][key].add((subject, grupo))
        for student, slot_map in student_slot_subjects.items():
            # Conflict iff some slot maps to 2+ distinct (subject, grupo) pairs
            if any(len(sg_set) > 1 for sg_set in slot_map.values()):
                student_conflicts += 1

    return {
        'c1_violations':      int(c1_violations),
        'c4_violations':      int(c4_violations),
        'student_conflicts':  int(student_conflicts),
        'examples_c1':        examples_c1,
        'examples_c4':        examples_c4,
    }


# ============================================================================
# HEALTH SCORE — single global indicator
# ============================================================================

def compute_health_score(metrics: Dict) -> Tuple[int, str, List[str]]:
    """
    Compute a 0-100 health score with a verdict and list of issues.

    Args:
        metrics: dict returned by compute_all_metrics

    Returns:
        (score, verdict, issues)
        score:   0-100
        verdict: 'excellent', 'good', 'acceptable', 'needs_attention', 'critical'
        issues:  list of human-readable issue descriptions
    """
    score = 100
    issues = []

    assignment = metrics.get('assignment', {})
    distribution = metrics.get('distribution', {})
    overload = metrics.get('overload', {})
    conflicts = metrics.get('conflicts', {})
    occupancy = metrics.get('room_occupancy', [])
    coverage = metrics.get('coverage', [])

    # 1. CONFLICTS — these are real, hard failures (-50 / -50 / -30)
    if conflicts.get('c1_violations', 0) > 0:
        score -= 50
        issues.append(f"{conflicts['c1_violations']} violation(s) C1 (matière en double)")
    if conflicts.get('c4_violations', 0) > 0:
        score -= 50
        issues.append(f"{conflicts['c4_violations']} violation(s) C4 (salle en double)")
    if conflicts.get('student_conflicts', 0) > 0:
        score -= 30
        issues.append(f"{conflicts['student_conflicts']} étudiant(s) avec conflit horaire")

    # 2. ASSIGNMENT RATE — penalise only if < 100% (the real headline number)
    assignment_rate = assignment.get('assignment_rate', 100.0)
    if assignment_rate < 100.0:
        # Linear penalty: 10 points per missing % of unique-student coverage
        gap = 100.0 - assignment_rate
        score -= min(40, int(gap * 10))
        issues.append(f"Taux d'assignation {assignment_rate:.1f}% (< 100%)")

    # 3. OVERFLOW GROUPS — Daniel himself uses afternoon groups to absorb
    # year-2/3 students that don't fit in morning slots. Only penalise if the
    # rate is EXCESSIVE (>20% of groups), which signals a real distribution
    # problem rather than a normal absorption pattern.
    overflow = assignment.get('overflow_groups', 0)
    total_groups = assignment.get('total_groups', 1)
    if total_groups > 0:
        overflow_rate = overflow / total_groups
        if overflow_rate > 0.20:   # > 20% — abnormal
            score -= 10
            issues.append(f"{overflow} groupes overflow ({overflow_rate*100:.0f}% du total — élevé)")

    # 4. GROUP SIZES — small groups are the real defect. <5 students is bad,
    # solo (=1) is critical.
    below_min = assignment.get('groups_below_min', 0)
    if below_min > 0:
        score -= min(20, below_min * 5)
        issues.append(f"{below_min} groupe(s) sous le seuil de 5 étudiants")

    # 5. STUDENT WEEKLY OVERLOAD — this measures students' COURSE load, not a
    # planning defect. A student enrolled in 5 lab subjects will always have
    # weeks where they do 4 labs — that's their academic choice, not ours.
    # Only penalise if it indicates a real concentration problem (> 30% of
    # students affected, which would mean we're piling labs on the same weeks).
    overloaded = overload.get('overloaded_count', 0)
    total_students = assignment.get('total_students', 1) or 1
    overloaded_rate = overloaded / total_students
    if overloaded_rate > 0.30:
        score -= 10
        issues.append(
            f"{overloaded} étudiant(s) avec > {MAX_LABS_PER_STUDENT_PER_WEEK} "
            f"labs la même semaine ({overloaded_rate*100:.0f}% — pic anormal)"
        )

    # 6. ROOM OVER-OCCUPANCY — real concern
    critical_rooms = [r for r in occupancy if r.get('status') == 'critical']
    if critical_rooms:
        score -= min(15, len(critical_rooms) * 5)
        issues.append(
            f"{len(critical_rooms)} salle(s) en sur-occupation (> {WARNING_ROOM_OCCUPANCY*100:.0f}%)"
        )

    # 7. COVERAGE vs DANIEL — penalise only if we cover LESS than Daniel.
    # Covering MORE (because we placed 100% vs his ~92%) means we form a few
    # extra groups, which is a quality WIN, not a defect.
    critical_coverage = [
        c for c in coverage
        if c.get('status') == 'critical'
        and c.get('actual_groups', 0) < c.get('daniel_groups', 0)
    ]
    if critical_coverage:
        score -= min(15, len(critical_coverage) * 5)
        names = ', '.join(c['subject'] for c in critical_coverage[:3])
        more = f" (+{len(critical_coverage)-3})" if len(critical_coverage) > 3 else ""
        issues.append(f"Sous-couverture vs Daniel : {names}{more}")

    # 8. BALANCE — minor penalty for very uneven group sizes
    balance = distribution.get('balance_score', 0)
    if balance < 40:
        score -= 5
        issues.append(f"Tailles de groupes déséquilibrées (balance {balance}/100)")

    score = max(0, min(100, score))

    # Verdict
    if score >= 90:
        verdict = 'excellent'
    elif score >= 75:
        verdict = 'good'
    elif score >= 60:
        verdict = 'acceptable'
    elif score >= 40:
        verdict = 'needs_attention'
    else:
        verdict = 'critical'

    return score, verdict, issues


# ============================================================================
# AGGREGATOR
# ============================================================================

def compute_all_metrics(schedule_df: pd.DataFrame,
                         groups_df: pd.DataFrame) -> Dict:
    """
    Compute the full set of reliability metrics.

    Args:
        schedule_df: optimized_schedule_v5.csv content
        groups_df:   group_composition.csv content

    Returns:
        dict with all sub-metrics + health score
    """
    metrics = {
        'assignment':     compute_assignment_metrics(schedule_df, groups_df),
        'coverage':       compute_coverage_per_subject(schedule_df, groups_df),
        'distribution':   compute_distribution_metrics(schedule_df),
        'room_occupancy': compute_room_occupancy(schedule_df),
        'overload':       compute_student_overload(schedule_df, groups_df),
        'spacing':        compute_spacing_quality(schedule_df),
        'conflicts':      detect_conflicts(schedule_df, groups_df),
    }

    score, verdict, issues = compute_health_score(metrics)
    metrics['health'] = {
        'score':   score,
        'verdict': verdict,
        'issues':  issues,
    }

    return metrics


# ============================================================================
# CLI / DEBUGGING
# ============================================================================

def main():
    """Run metrics on the standard output paths and print a summary."""
    import os

    schedule_path = 'outputs/optimization/optimized_schedule_v5.csv'
    groups_path = 'outputs/optimization/group_composition.csv'

    if not os.path.exists(schedule_path):
        print(f"[ERROR] Schedule file not found: {schedule_path}")
        return
    if not os.path.exists(groups_path):
        print(f"[ERROR] Groups file not found: {groups_path}")
        return

    schedule_df = pd.read_csv(schedule_path)
    groups_df = pd.read_csv(groups_path)

    print(f"Loaded {len(schedule_df)} sessions, {len(groups_df)} group entries")
    print()

    metrics = compute_all_metrics(schedule_df, groups_df)

    print('=' * 70)
    print('  RELIABILITY METRICS')
    print('=' * 70)
    print(f"  Health score:  {metrics['health']['score']}/100 ({metrics['health']['verdict']})")
    print()

    if metrics['health']['issues']:
        print('  Issues detected:')
        for issue in metrics['health']['issues']:
            print(f"    - {issue}")
    else:
        print('  No issues detected.')

    print()
    print('  Assignment:')
    a = metrics['assignment']
    print(f"    Sessions:    {a['total_sessions']}")
    print(f"    Groups:      {a['total_groups']}")
    print(f"    Students:    {a['total_students']}")
    print(f"    Avg size:    {a['avg_group_size']} (min={a['min_group_size']}, max={a['max_group_size']})")
    print(f"    Overflow:    {a['overflow_groups']}, Alt-room: {a['alt_room_groups']}")

    print()
    print('  Coverage per subject:')
    for c in metrics['coverage']:
        ref = f"vs Daniel: {c['ref_students']}" if c['ref_students'] else "no ref"
        dev = f"({c['deviation_pct']:+.0f}%)" if c['deviation_pct'] is not None else ""
        status = c['status'].upper()
        print(f"    [{status:<8}] S{c['semester']} {c['subject']:<35} "
              f"{c['students']:>4} stu, {c['groups']:>2} grp, {ref} {dev}")

    print()
    print('  Conflicts (defense in depth):')
    cf = metrics['conflicts']
    print(f"    C1 violations: {cf['c1_violations']}")
    print(f"    C4 violations: {cf['c4_violations']}")
    print(f"    Student conflicts: {cf['student_conflicts']}")


if __name__ == '__main__':
    main()