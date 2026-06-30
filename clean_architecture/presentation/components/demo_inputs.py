"""Builder of demonstration / simulation datasets.

In production, groups and professors come from the Excel ingestion
(infrastructure/excel). For the monitoring dashboard and the sandbox, this
module generates configurable inputs from the real configuration
(config.yaml), without depending on the large files.
"""
from __future__ import annotations

import math
from typing import List, Tuple

from domain.entities.group import Group
from domain.entities.professor import Professor
from domain.value_objects import TimeSlot
from infrastructure.config.config_loader import AppSettings


def build_inputs(settings: AppSettings, subject_codes: List[str],
                n_groups: int = 3,
                profs_per_subject: int = 2) -> Tuple[List[Group], List[Professor]]:
    """Builds consistent groups and professors for a simulation.

    Args:
        settings: application configuration (subjects, blocks, windows).
        subject_codes: codes of the subjects to include (e.g. ["S1_Física"]).
        n_groups: number of groups per subject.
        profs_per_subject: number of professors sharing the subject.

    The professors' P credits are calibrated to cover, in total, the number of
    planned sessions (so that the validation is globally consistent).
    """
    groups: List[Group] = []
    professors: List[Professor] = []
    spc = settings.sessions_per_credit

    for s_idx, code in enumerate(subject_codes):
        subj = settings.subjects.get(code)
        if subj is None:
            continue

        for i in range(1, n_groups + 1):
            block = settings.time_blocks[(i - 1) % len(settings.time_blocks)]
            day_idx = (i - 1) % max(1, len(settings.days) - 1)
            groups.append(Group(
                subject=code, group_num=i, semester=subj.semester,
                curso_num=subj.curso_num, num_sessions=subj.num_sessions,
                slot=TimeSlot(day_idx, settings.days[day_idx], block.id, block.label),
                nb_students=min(12, subj.max_students), lab_rooms=subj.lab_rooms,
                window=subj.window, program=subj.keywords[0] if subj.keywords else "",
            ))

        # P credits distributed to cover the subject's total sessions
        total_sessions = n_groups * subj.num_sessions
        total_credits = max(profs_per_subject, math.ceil(total_sessions / spc))
        base = total_credits // profs_per_subject
        rest = total_credits - base * profs_per_subject
        for p in range(profs_per_subject):
            credits = base + (1 if p < rest else 0)
            professors.append(Professor(
                name=f"Prof. {chr(65 + p)} - {subj.display_name}",
                practice_credits_by_subject={code: credits},
            ))

    return groups, professors
