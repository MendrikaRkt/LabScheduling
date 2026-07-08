"""
simulation_engine.py — "What-if" infeasibility analysis (Phase 2, Feature 2).

This is a strictly READ-ONLY, side-effect-free analysis layer. It never runs
the real pipeline, never mutates the optimisation data, and never writes to the
``reports/`` or ``outputs/`` directories. It answers hypothetical questions:

    - "What happens to the bottlenecks if I DROP these groups?"
    - "What happens if I ADD extra rooms / time slots?"
    - "Which groups or resources should I change first?" (suggestions)

Two analysis levels are provided:

1. Capacity / bottleneck model (fast, deterministic) — mirrors the logic of
   ``pipeline.diagnose_infeasibility``: for every physical slot
   ``(room, day, block)`` and every subject slot ``(subject, day, block)`` the
   number of sessions that must fit (``needed``) is compared to the number of
   available weeks (``capacity``). A positive ``overflow`` marks a bottleneck.

2. Optional real CP-SAT dry-run (``dry_run_feasibility``) — builds the same hard
   constraints (C1/C4/C5) as the production solver on a hypothetical session
   list and reports whether it is feasible. Used for the "exclude groups"
   scenario where sessions are only REMOVED (so the reduced model stays valid).

All public functions carry type hints and docstrings, validate their inputs and
raise ``ValueError`` on malformed data.
"""

from __future__ import annotations

import copy
import glob
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Session model
# ---------------------------------------------------------------------------
# A "session" is one lab meeting that must be placed in some week. The keys used
# by this engine are a minimal, self-contained subset of the pipeline's richer
# session dict, so the engine can run without importing the whole pipeline.
#
#   group_id  : stable identifier of the owning group ("SUBJECT|GRUPO|SEM")
#   semester  : int
#   subject   : str
#   grupo     : original group number/label
#   program   : str (optional)
#   day_idx   : int (0=Mon .. 4=Fri)
#   block_id  : str
#   rooms     : list[str] of candidate lab rooms (may be empty if unknown)
#   min_week  : int
#   max_week  : int
#   nb_students : int (optional, for "affected students" reporting)
# ---------------------------------------------------------------------------

REQUIRED_SESSION_KEYS: Tuple[str, ...] = (
    "group_id", "day_idx", "block_id", "min_week", "max_week",
)

DEFAULT_REPORTS_DIR = "reports"


def make_group_id(subject: str, grupo: Any, semester: Any) -> str:
    """Return a stable group identifier used across the simulation engine."""
    return f"{subject}|{grupo}|S{semester}"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_sessions(sessions: Sequence[Dict[str, Any]]) -> None:
    """Raise ``ValueError`` if any session lacks a required key or is malformed."""
    if not isinstance(sessions, (list, tuple)):
        raise ValueError("sessions must be a list of dicts.")
    for i, s in enumerate(sessions):
        if not isinstance(s, dict):
            raise ValueError(f"session #{i} is not a dict.")
        for k in REQUIRED_SESSION_KEYS:
            if k not in s:
                raise ValueError(f"session #{i} missing required key '{k}'.")
        if int(s["min_week"]) > int(s["max_week"]):
            raise ValueError(
                f"session #{i} has min_week > max_week "
                f"({s['min_week']} > {s['max_week']})."
            )


# ---------------------------------------------------------------------------
# Capacity / bottleneck model
# ---------------------------------------------------------------------------

def _slot_groups(
    sessions: Sequence[Dict[str, Any]]
) -> Tuple[Dict[Tuple[str, int, str], List[Dict[str, Any]]],
           Dict[Tuple[str, int, str], List[Dict[str, Any]]]]:
    """Bucket sessions by physical slot (room,day,block) and subject slot.

    Returns ``(by_room_slot, by_subject_slot)``. A session with N candidate
    rooms is counted in each room bucket (matching the pipeline's C4 logic).
    """
    by_room: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = {}
    by_subj: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = {}
    for s in sessions:
        d = int(s["day_idx"])
        b = str(s["block_id"])
        for room in s.get("rooms", []) or []:
            room = str(room).strip()
            if room:
                by_room.setdefault((room, d, b), []).append(s)
        subj = str(s.get("subject", s["group_id"]))
        by_subj.setdefault((subj, d, b), []).append(s)
    return by_room, by_subj


def _capacity_of(group: Sequence[Dict[str, Any]]) -> int:
    """Number of distinct weeks available to a slot's sessions."""
    max_w = max(int(s["max_week"]) for s in group)
    min_w = min(int(s["min_week"]) for s in group)
    return max_w - min_w + 1


def analyze_bottlenecks(
    sessions: Sequence[Dict[str, Any]],
    extra_capacity: Optional[Dict[Tuple[str, int, str], int]] = None,
) -> Dict[str, Any]:
    """Compute slot-level bottlenecks for a hypothetical session list.

    Args:
        sessions: session dicts (see module docstring).
        extra_capacity: optional mapping ``(resource, day_idx, block_id) -> +weeks``
            adding capacity to matching room/subject slots (used by the
            "add resources" scenario).

    Returns:
        A dict with keys:
            ``feasible`` (bool): True when no slot overflows.
            ``n_sessions`` (int): total sessions considered.
            ``bottlenecks`` (list): each ``{kind, resource, day_idx, block_id,
                needed, capacity, overflow}`` sorted by descending overflow.
            ``total_overflow`` (int): sum of all overflows.
    """
    _validate_sessions(sessions)
    extra_capacity = extra_capacity or {}
    by_room, by_subj = _slot_groups(sessions)

    bottlenecks: List[Dict[str, Any]] = []

    def _scan(buckets: Dict[Tuple[str, int, str], List[Dict[str, Any]]],
              kind: str) -> None:
        for (resource, d, b), group in buckets.items():
            needed = len(group)
            capacity = _capacity_of(group) + int(extra_capacity.get((resource, d, b), 0))
            overflow = needed - capacity
            if overflow > 0:
                bottlenecks.append({
                    "kind": kind,
                    "resource": resource,
                    "day_idx": d,
                    "block_id": b,
                    "needed": needed,
                    "capacity": capacity,
                    "overflow": overflow,
                })

    _scan(by_room, "SALLE")
    _scan(by_subj, "MATIERE")
    bottlenecks.sort(key=lambda x: x["overflow"], reverse=True)

    return {
        "feasible": len(bottlenecks) == 0,
        "n_sessions": len(sessions),
        "bottlenecks": bottlenecks,
        "total_overflow": sum(b["overflow"] for b in bottlenecks),
    }


def _diff_metrics(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Return a before/after comparison of two bottleneck analyses."""
    return {
        "feasible_before": before["feasible"],
        "feasible_after": after["feasible"],
        "became_feasible": (not before["feasible"]) and after["feasible"],
        "n_sessions_before": before["n_sessions"],
        "n_sessions_after": after["n_sessions"],
        "n_bottlenecks_before": len(before["bottlenecks"]),
        "n_bottlenecks_after": len(after["bottlenecks"]),
        "total_overflow_before": before["total_overflow"],
        "total_overflow_after": after["total_overflow"],
        "overflow_reduction": before["total_overflow"] - after["total_overflow"],
    }


# ---------------------------------------------------------------------------
# Scenario 1 — exclude groups
# ---------------------------------------------------------------------------

def simulate_without_groups(
    sessions: Sequence[Dict[str, Any]],
    group_ids: Iterable[str],
) -> Dict[str, Any]:
    """Dry-run: recompute bottlenecks with the given groups REMOVED.

    Does not modify ``sessions``. Returns a result dict with ``before``,
    ``after``, ``diff`` bottleneck analyses plus ``removed_groups``,
    ``removed_sessions`` and ``affected_students`` (sum of nb_students of the
    removed sessions' groups).

    Raises ``ValueError`` on malformed sessions.
    """
    _validate_sessions(sessions)
    drop: Set[str] = {str(g) for g in group_ids}
    kept = [s for s in sessions if str(s["group_id"]) not in drop]
    removed = [s for s in sessions if str(s["group_id"]) in drop]

    before = analyze_bottlenecks(sessions)
    after = analyze_bottlenecks(kept)

    affected = 0
    seen: Set[str] = set()
    for s in removed:
        gid = str(s["group_id"])
        if gid not in seen:
            seen.add(gid)
            affected += int(s.get("nb_students", 0) or 0)

    return {
        "scenario": "exclude_groups",
        "removed_groups": sorted(seen),
        "removed_sessions": len(removed),
        "affected_students": affected,
        "before": before,
        "after": after,
        "diff": _diff_metrics(before, after),
    }


# ---------------------------------------------------------------------------
# Scenario 2 — add extra capacity (rooms / time slots)
# ---------------------------------------------------------------------------

def simulate_with_extra_capacity(
    sessions: Sequence[Dict[str, Any]],
    extra_slots: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Dry-run: recompute bottlenecks with additional room/time-slot capacity.

    Args:
        sessions: session dicts.
        extra_slots: each ``{resource, day_idx, block_id, weeks}`` where
            ``resource`` is a room name (or subject) whose slot gains ``weeks``
            extra usable weeks. ``weeks`` defaults to 1 if omitted.

    Returns a result dict with ``before``/``after``/``diff`` and
    ``added_capacity`` (total extra weeks injected).

    Raises ``ValueError`` on malformed sessions or slot descriptors.
    """
    _validate_sessions(sessions)
    extra_capacity: Dict[Tuple[str, int, str], int] = {}
    total_added = 0
    for i, slot in enumerate(extra_slots):
        if not isinstance(slot, dict):
            raise ValueError(f"extra_slots[{i}] is not a dict.")
        for k in ("resource", "day_idx", "block_id"):
            if k not in slot:
                raise ValueError(f"extra_slots[{i}] missing key '{k}'.")
        weeks = int(slot.get("weeks", 1))
        if weeks <= 0:
            raise ValueError(f"extra_slots[{i}].weeks must be positive.")
        key = (str(slot["resource"]).strip(), int(slot["day_idx"]),
               str(slot["block_id"]))
        extra_capacity[key] = extra_capacity.get(key, 0) + weeks
        total_added += weeks

    before = analyze_bottlenecks(sessions)
    after = analyze_bottlenecks(sessions, extra_capacity=extra_capacity)

    return {
        "scenario": "add_capacity",
        "added_capacity": total_added,
        "added_slots": len(extra_capacity),
        "before": before,
        "after": after,
        "diff": _diff_metrics(before, after),
    }


# ---------------------------------------------------------------------------
# Scenario 3 — automatic suggestions
# ---------------------------------------------------------------------------

def suggest_actions(
    sessions: Sequence[Dict[str, Any]],
    max_suggestions: int = 5,
) -> Dict[str, Any]:
    """Analyse bottlenecks and suggest concrete remediation actions.

    Returns a dict with:
        ``exclude_groups``: candidate group_ids to drop, ranked by how many
            distinct bottleneck slots they participate in.
        ``add_resources``: candidate ``{resource, day_idx, block_id, weeks}``
            additions that would clear the worst bottlenecks.
    """
    _validate_sessions(sessions)
    analysis = analyze_bottlenecks(sessions)
    bottlenecks = analysis["bottlenecks"]

    # Rank groups by participation in bottleneck slots.
    group_hits: Dict[str, int] = {}
    for b in bottlenecks:
        d, blk = b["day_idx"], b["block_id"]
        for s in sessions:
            if int(s["day_idx"]) == d and str(s["block_id"]) == blk:
                if b["kind"] == "SALLE" and b["resource"] not in (s.get("rooms") or []):
                    continue
                if b["kind"] == "MATIERE" and str(s.get("subject", "")) != b["resource"]:
                    continue
                gid = str(s["group_id"])
                group_hits[gid] = group_hits.get(gid, 0) + 1

    exclude = [
        {"group_id": gid, "bottleneck_slots": hits}
        for gid, hits in sorted(group_hits.items(),
                                key=lambda kv: kv[1], reverse=True)
    ][:max_suggestions]

    add_resources = [
        {
            "resource": b["resource"],
            "day_idx": b["day_idx"],
            "block_id": b["block_id"],
            "weeks": b["overflow"],
            "reason": (f"{b['kind']} '{b['resource']}' sature de {b['overflow']} "
                       f"seance(s) (besoin {b['needed']} / capacite {b['capacity']})."),
        }
        for b in bottlenecks[:max_suggestions]
    ]

    return {
        "feasible": analysis["feasible"],
        "exclude_groups": exclude,
        "add_resources": add_resources,
    }


# ---------------------------------------------------------------------------
# Optional real CP-SAT dry-run (feasibility only)
# ---------------------------------------------------------------------------

def dry_run_feasibility(
    sessions: Sequence[Dict[str, Any]],
    holidays: Optional[Set[Tuple[int, int]]] = None,
    time_limit: int = 20,
) -> Dict[str, Any]:
    """Build the C1/C4/C5 hard-constraint model and solve for feasibility only.

    This is a genuine solver dry-run (no objective). Valid for scenarios that
    only REMOVE sessions. Requires ``ortools``; if unavailable, returns
    ``{"status": "UNAVAILABLE"}``.

    Each session needs an integer ``session`` order key within its group for the
    C5 chronological constraint; if absent, sessions are ordered by list index.
    """
    _validate_sessions(sessions)
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return {"status": "UNAVAILABLE", "reason": "ortools not installed"}

    holidays = holidays or set()
    model = cp_model.CpModel()
    week_vars: Dict[int, Any] = {}
    for idx, s in enumerate(sessions):
        valid = [w for w in range(int(s["min_week"]), int(s["max_week"]) + 1)
                 if (w, int(s["day_idx"])) not in holidays]
        if not valid:
            valid = list(range(int(s["min_week"]), int(s["max_week"]) + 1))
        week_vars[idx] = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(valid), f"w_{idx}")

    # C1: no two sessions of the same subject share (week, day, block).
    from collections import defaultdict
    by_subj_slot = defaultdict(list)
    by_room_slot = defaultdict(list)
    by_group = defaultdict(list)
    for idx, s in enumerate(sessions):
        by_subj_slot[(str(s.get("subject", s["group_id"])), int(s["day_idx"]),
                      str(s["block_id"]))].append(idx)
        for room in (s.get("rooms") or []):
            room = str(room).strip()
            if room:
                by_room_slot[(room, int(s["day_idx"]), str(s["block_id"]))].append(idx)
        by_group[str(s["group_id"])].append((s.get("session", idx), idx))

    for grp in by_subj_slot.values():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                model.Add(week_vars[grp[i]] != week_vars[grp[j]])
    # C4: no two sessions in the same room share (week, day, block).
    for grp in by_room_slot.values():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                model.Add(week_vars[grp[i]] != week_vars[grp[j]])
    # C5: sessions of a group are strictly ordered by week.
    for grp in by_group.values():
        ordered = [idx for _, idx in sorted(grp, key=lambda t: t[0])]
        for k in range(len(ordered) - 1):
            model.Add(week_vars[ordered[k + 1]] > week_vars[ordered[k]])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = 8
    solver.parameters.random_seed = 42
    status = solver.Solve(model)
    names = {cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
             cp_model.INFEASIBLE: "INFEASIBLE", cp_model.UNKNOWN: "UNKNOWN"}
    return {
        "status": names.get(status, "UNKNOWN"),
        "feasible": status in (cp_model.OPTIMAL, cp_model.FEASIBLE),
        "wall_time_s": round(solver.WallTime(), 3),
        "n_sessions": len(sessions),
    }


# ---------------------------------------------------------------------------
# Best-effort loaders (read-only) for the Streamlit UI
# ---------------------------------------------------------------------------

def load_unplaced_students(reports_dir: str = DEFAULT_REPORTS_DIR) -> List[Dict[str, Any]]:
    """Read ``reports/unplaced_students.json`` (empty list if absent/invalid)."""
    path = os.path.join(reports_dir, "unplaced_students.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def load_solver_stats(reports_dir: str = DEFAULT_REPORTS_DIR) -> List[Dict[str, Any]]:
    """Read ``reports/solver_stats.json`` (empty list if absent/invalid)."""
    path = os.path.join(reports_dir, "solver_stats.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []


_BOTTLENECK_RE = re.compile(
    r"\[(SALLE|MATIÈRE|MATIERE)\s*\]\s+(.+?)\s{2,}(\S+)\s+(\S+)\s*:\s*"
    r"(\d+)\s+séances?\s*/\s*(\d+)\s+semaines?\s*\(excès?\s+(\d+)\)"
)


def load_bottlenecks_from_reports(
    reports_dir: str = DEFAULT_REPORTS_DIR,
) -> List[Dict[str, Any]]:
    """Parse ``reports/infeasibility_S*.txt`` files into bottleneck dicts.

    Returns a list of ``{kind, resource, day, block, needed, capacity,
    overflow, source_file}`` (best effort; unreadable files are skipped).
    """
    out: List[Dict[str, Any]] = []
    pattern = os.path.join(reports_dir, "infeasibility_S*.txt")
    for path in sorted(glob.glob(pattern)):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception:
            continue
        for m in _BOTTLENECK_RE.finditer(text):
            kind, resource, day, block, needed, cap, over = m.groups()
            out.append({
                "kind": "MATIERE" if kind.startswith("MATI") else "SALLE",
                "resource": resource.strip(),
                "day": day.strip(),
                "block": block.strip(),
                "needed": int(needed),
                "capacity": int(cap),
                "overflow": int(over),
                "source_file": os.path.basename(path),
            })
    return out


def build_sessions_from_group_composition(
    path: str,
    lab_rooms_by_subject: Optional[Dict[str, List[str]]] = None,
    sessions_per_group: int = 5,
    default_weeks: Tuple[int, int] = (1, 15),
) -> List[Dict[str, Any]]:
    """Best-effort reconstruction of a session list from group_composition.csv.

    The composition file gives subject/grupo/day/block/members but not rooms,
    session counts nor week windows. Missing pieces are filled with sensible
    defaults (``sessions_per_group`` = 5 per the 1 practice credit = 5 sessions
    rule; ``default_weeks`` = full semester window; rooms from
    ``lab_rooms_by_subject`` when provided).

    Returns an empty list if the file is missing or pandas is unavailable.
    """
    try:
        import pandas as pd
    except Exception:
        return []
    if not os.path.exists(path):
        return []
    try:
        df = pd.read_csv(path)
    except Exception:
        return []

    day_map = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Miercoles": 2,
               "Jueves": 3, "Viernes": 4,
               "Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3, "Vendredi": 4,
               "Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3,
               "Friday": 4}
    lab_rooms_by_subject = lab_rooms_by_subject or {}
    sessions: List[Dict[str, Any]] = []
    grouped = df.groupby(["semester", "subject", "grupo", "day", "block"],
                         dropna=False)
    for (sem, subject, grupo, day, block), rows in grouped:
        sem_num = int(str(sem).replace("S", "")) if str(sem).strip() else 0
        gid = make_group_id(subject, grupo, sem_num)
        nb_students = len(rows)
        rooms = [str(r).strip() for r in lab_rooms_by_subject.get(subject, [])
                 if str(r).strip()]
        d_idx = day_map.get(str(day).strip(), 0)
        for k in range(1, sessions_per_group + 1):
            sessions.append({
                "group_id": gid,
                "semester": sem_num,
                "subject": str(subject),
                "grupo": grupo,
                "day_idx": d_idx,
                "block_id": str(block),
                "rooms": rooms,
                "min_week": int(default_weeks[0]),
                "max_week": int(default_weeks[1]),
                "nb_students": nb_students,
                "session": k,
            })
    return sessions
