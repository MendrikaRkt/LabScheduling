"""constraint_manager.py - CP-SAT solver constraint management.

Posts the constraints on a CP-SAT model from the domain LabSession objects.
The solver only decides the WEEK of each session (the day/block slot is fixed
upstream). It faithfully reproduces the constraints of the former pipeline:

  C1     - no 2 sessions of the same subject at the same (week, day, block)
  C4     - no 2 sessions in the same room at the same slot
  C5     - chronological order of sessions within a group
  RESV   - reserved slots (soft penalty)
  PARITY - even/odd alternation between groups (soft penalty)

Each method returns the (soft) penalty terms to be aggregated into the
objective by the SolverEngine.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from ortools.sat.python import cp_model

from domain.entities.group import LabSession
from infrastructure.config.config_loader import AppSettings


class ConstraintManager:
    """Builds the variables and constraints of a semester on a CP-SAT model."""

    def __init__(self, model: cp_model.CpModel, settings: AppSettings, semester: int):
        self.model = model
        self.settings = settings
        self.semester = semester
        self.week_vars: Dict[int, cp_model.IntVar] = {}
        self.counts: Dict[str, int] = defaultdict(int)

    # -- Decision variables: the week of each session ----------------------
    def create_week_variables(self, sessions: List[LabSession]) -> Dict[int, cp_model.IntVar]:
        holidays = self.settings.holidays.get(self.semester, {})
        for s in sessions:
            valid = [w for w in s.window.weeks()
                    if (w, s.slot.day_idx) not in holidays]
            if not valid:
                valid = s.window.weeks()
            self.week_vars[s.id] = self.model.NewIntVarFromDomain(
                cp_model.Domain.FromValues(valid), f"w_{s.id}")
        return self.week_vars

    # -- C1: same subject, same slot -> distinct weeks ---------------------
    def add_no_same_subject_slot(self, sessions: List[LabSession]) -> None:
        buckets = defaultdict(list)
        for s in sessions:
            buckets[(s.subject, s.slot.day_idx, s.slot.block_id)].append(s)
        for grp in buckets.values():
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    self.model.Add(self.week_vars[grp[i].id] != self.week_vars[grp[j].id])
                    self.counts["C1"] += 1

    # -- C4: same room, same slot -> distinct weeks ------------------------
    def add_no_same_room_slot(self, sessions: List[LabSession]) -> Dict[tuple, list]:
        by_room_slot = defaultdict(list)
        for s in sessions:
            for room in s.lab_rooms:
                room = room.strip()
                if room:
                    by_room_slot[(room, s.slot.day_idx, s.slot.block_id)].append(s)
        for grp in by_room_slot.values():
            for i in range(len(grp)):
                for j in range(i + 1, len(grp)):
                    self.model.Add(self.week_vars[grp[i].id] != self.week_vars[grp[j].id])
                    self.counts["C4"] += 1
        return by_room_slot

    # -- C5: chronological order of a group's sessions ---------------------
    def add_chronological_order(self, sessions: List[LabSession]) -> None:
        by_group = defaultdict(list)
        for s in sessions:
            by_group[(s.subject, s.group_num)].append(s)
        for grp in by_group.values():
            grp_sorted = sorted(grp, key=lambda x: x.session_num)
            for k in range(len(grp_sorted) - 1):
                self.model.Add(
                    self.week_vars[grp_sorted[k + 1].id] > self.week_vars[grp_sorted[k].id])
                self.counts["C5"] += 1

    # -- RESV: reserved slots (soft penalty) -------------------------------
    def add_reservation_penalties(self, by_room_slot: Dict[tuple, list]) -> List[cp_model.IntVar]:
        terms: List[cp_model.IntVar] = []
        for (sem, subj), slots in self.settings.subject_blocked_slots.items():
            if sem != self.semester:
                continue
            subject = self.settings.subjects.get(subj)
            rooms = [r.strip() for r in (subject.lab_rooms if subject else []) if r.strip()]
            for (w, d, b) in slots:
                for room in rooms:
                    for s in by_room_slot.get((room, d, b), []):
                        if not (s.window.min_week <= w <= s.window.max_week):
                            continue
                        in_resv = self.model.NewBoolVar(f"resv_{s.id}_{w}")
                        self.model.Add(self.week_vars[s.id] == w).OnlyEnforceIf(in_resv)
                        self.model.Add(self.week_vars[s.id] != w).OnlyEnforceIf(in_resv.Not())
                        terms.append(in_resv)
        self.counts["RESV"] = len(terms)
        return terms

    # -- PARITY: even/odd alternation between groups (soft) ----------------
    def add_parity_penalties(self, sessions: List[LabSession]) -> List[cp_model.IntVar]:
        if not self.settings.parity_enabled:
            return []
        subj_groups = defaultdict(set)
        sess_count = defaultdict(lambda: defaultdict(int))
        for s in sessions:
            subj_groups[s.subject].add(s.group_num)
            sess_count[s.subject][s.group_num] += 1

        penalties: List[cp_model.IntVar] = []
        for subj, groups in subj_groups.items():
            groups_sorted = sorted(groups)
            max_sess = max(sess_count[subj].values()) if sess_count[subj] else 0
            if len(groups_sorted) < 2 or max_sess < 3:
                continue
            for gi, group_num in enumerate(groups_sorted):
                target_parity = gi % 2
                grp_sessions = [s for s in sessions
                                if s.subject == subj and s.group_num == group_num]
                for s in grp_sessions:
                    wv = self.week_vars[s.id]
                    parity_bit = self.model.NewIntVar(0, 1, f"par_{s.id}")
                    half = self.model.NewIntVar(
                        s.window.min_week // 2, s.window.max_week // 2 + 1, f"half_{s.id}")
                    self.model.Add(wv == 2 * half + parity_bit)
                    if target_parity == 0:
                        penalties.append(parity_bit)
                    else:
                        inv = self.model.NewIntVar(0, 1, f"invpar_{s.id}")
                        self.model.Add(inv == 1 - parity_bit)
                        penalties.append(inv)
        self.counts["PARITY"] = len(penalties)
        return penalties
