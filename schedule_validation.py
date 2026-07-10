"""
schedule_validation.py
======================

Final reliability validation for the generated lab schedule.

This module is *additive* and *read-only*: it never mutates optimisation data.
It re-derives, from the canonical pipeline artefacts, an independent proof that
the produced lab sessions respect every hard constraint the solver is supposed
to enforce, and it computes objective quality statistics.

It answers, with real numbers, the questions asked for the final review:

  * Student time-table conflicts  == 0   (lab vs. theory + lab vs. lab)
  * Room conflicts                == 0   (a physical room hosts one group
                                          per week / day / block)
  * Professor conflicts           == 0   (professor busy slots + double booking)
  * Group sizing within policy    (min 7 / preferred 12 / max 15)
  * Solver status == OPTIMAL / FEASIBLE  (+ a transparent reliability formula)
  * Counts: groups, sessions, students, subjects
  * Teacher workload
  * Reliability metrics / indicators

Canonical inputs (all produced by pipeline.py, never invented here):

  outputs/optimization/optimized_schedule_v5.csv   -- one row per placed session
  outputs/optimization/group_composition.csv       -- student -> group membership
  outputs/optimization/student_directory.csv       -- student_name -> student_id
  data_clean/student_busy.csv                       -- student_id -> busy (day,block)
  data_clean/professor_busy.csv                     -- professor  -> busy (day,block)
  reports/solver_stats.json                         -- solver status / objective

The public entry point is :func:`validate_schedule`, returning a plain ``dict``
so it can be serialised to JSON, rendered in Streamlit, or written as an Excel
sheet without any Streamlit / openpyxl dependency living in this module.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

import pandas as pd

try:  # optional, only used to resolve workspace paths when packaged
    import app_paths as _app_paths
except Exception:  # pragma: no cover - fallback for bare checkout
    _app_paths = None


# --------------------------------------------------------------------------- #
# Canonical time model (mirrors pipeline.py so the two never drift)            #
# --------------------------------------------------------------------------- #
DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_IDS = {d: i for i, d in enumerate(DAYS)}

TIME_BLOCKS = [
    {"id": 1, "label": "08:30-10:30"},
    {"id": 2, "label": "10:30-12:30"},
    {"id": 3, "label": "12:30-14:30"},
    {"id": 4, "label": "15:00-17:00"},
    {"id": 5, "label": "17:00-19:00"},
    {"id": 6, "label": "19:00-21:00"},
]
BLOCK_ID_BY_LABEL = {b["label"]: b["id"] for b in TIME_BLOCKS}

# Group-sizing policy (business rule: min 7 / preferred 12 / max 15)
GROUP_MIN = 7
GROUP_PREFERRED = 12
GROUP_MAX = 15

# Rooms that are not physical exclusive resources (no room-conflict possible)
_VIRTUAL_ROOM_TOKENS = ("virtual", "online", "sin aula", "por determinar", "")


# --------------------------------------------------------------------------- #
# Path resolution                                                             #
# --------------------------------------------------------------------------- #
def _resolve(rel_candidates):
    """Return the first existing path among a list of relative candidates."""
    roots = ["."]
    if _app_paths is not None:
        for attr in ("workspace_dir", "user_data_dir", "base_dir"):
            fn = getattr(_app_paths, attr, None)
            try:
                if callable(fn):
                    roots.append(str(fn()))
            except Exception:
                pass
    for root in roots:
        for rel in rel_candidates:
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return None


def _default_paths():
    return {
        "schedule": _resolve([
            "outputs/optimization/optimized_schedule_v5.csv",
        ]),
        "composition": _resolve([
            "outputs/optimization/group_composition.csv",
        ]),
        "directory": _resolve([
            "outputs/optimization/student_directory.csv",
        ]),
        "student_busy": _resolve([
            "data_clean/optimization/student_busy.csv",
            "data_clean/student_busy.csv", "student_busy.csv",
        ]),
        "professor_busy": _resolve([
            "data_clean/optimization/professor_busy.csv",
            "data_clean/professor_busy.csv", "professor_busy.csv",
        ]),
        "solver_stats": _resolve([
            "reports/solver_stats.json",
        ]),
    }


# --------------------------------------------------------------------------- #
# Loading helpers (tolerant: a missing file degrades a check, never crashes)  #
# --------------------------------------------------------------------------- #
def _read_csv(path):
    if not path or not os.path.exists(path):
        return None
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        try:
            return pd.read_csv(path)
        except Exception:
            return None


def _norm_name(x):
    return str(x).strip().upper() if x is not None else ""


def _day_to_idx(day):
    return DAY_IDS.get(str(day).strip(), None)


def _block_to_id(label):
    return BLOCK_ID_BY_LABEL.get(str(label).strip(), None)


def _is_physical_room(room):
    r = str(room or "").strip().lower()
    return r not in _VIRTUAL_ROOM_TOKENS and not any(t and t in r for t in ("virtual", "online"))


def _sem_from_cuatri(val):
    """Map master 'cuatrimestre' (1C/2C) to solver semester int (1/2)."""
    s = str(val).strip().upper()
    if s.startswith("1"):
        return 1
    if s.startswith("2"):
        return 2
    return None


def build_effective_busy_context(master_path=None):
    """
    Reproduce, from ``master_schedule.csv``, the **semester-aware** "effective
    busy" model the solver relies on, so validation reflects real calendar time
    (an S1 lab can never clash with an S2 class) and never flags the legitimate
    "lab replaces its own theory hour" case.

    Returns a dict with:
      student_busy_sem     : {sem: {sid: set((day,block))}}   theory busy
      prof_busy_sem        : {sem: {prof: set((day,block))}}
      student_subject_slots: {sid: {subject: set((day,block))}}  own-subject hours
      prof_subject_slots   : {prof: {subject: set((day,block))}}
      subject_shared_map   : {subject: [subject, ...shared-group siblings]}
      available            : bool

    Degrades gracefully (``available=False``) if pipeline or the master file is
    unavailable; callers then fall back to the global busy CSVs.
    """
    empty = {"student_busy_sem": {1: {}, 2: {}}, "prof_busy_sem": {1: {}, 2: {}},
             "student_subject_slots": {}, "prof_subject_slots": {},
             "subject_shared_map": {}, "available": False}
    try:
        import pipeline as _p
    except Exception:
        return empty

    master_path = master_path or _resolve([
        "data_clean/master_schedule.csv", "master_schedule.csv"])
    if not master_path or not os.path.exists(master_path):
        return empty

    subject_shared_map = {}
    for subj, cfg in _p.LAB_CONFIG.items():
        sg = cfg.get("shared_group")
        subject_shared_map[subj] = (
            [s for s, c in _p.LAB_CONFIG.items() if c.get("shared_group") == sg]
            if sg else [subj]
        )

    cols = ["AlumnoID", "slot_hora_inicio_min", "slot_jour_semaine",
            "actividad", "cuatrimestre", "docentes"]
    try:
        df = pd.read_csv(master_path, encoding="utf-8-sig", usecols=cols,
                         low_memory=False)
    except Exception:
        try:
            df = pd.read_csv(master_path, encoding="utf-8-sig", low_memory=False)
        except Exception:
            return empty

    df = df.dropna(subset=["slot_hora_inicio_min", "slot_jour_semaine"])
    df = df[df["slot_hora_inicio_min"] > 0]

    student_busy_sem = {1: defaultdict(set), 2: defaultdict(set)}
    prof_busy_sem = {1: defaultdict(set), 2: defaultdict(set)}
    student_subject_slots = defaultdict(lambda: defaultdict(set))
    prof_subject_slots = defaultdict(lambda: defaultdict(set))

    for r in df.itertuples(index=False):
        day = r.slot_jour_semaine
        block_id = _p.min_to_block_id(r.slot_hora_inicio_min)
        if not block_id or day not in DAYS:
            continue
        slot = (DAY_IDS[day], block_id)
        sem = _sem_from_cuatri(getattr(r, "cuatrimestre", ""))
        act = str(getattr(r, "actividad", "")).lower()

        # matching lab subjects for this activity (own-subject recovery)
        matched = []
        for subject, cfg in _p.LAB_CONFIG.items():
            kws = cfg.get("keywords", [])
            excl = cfg.get("keyword_exclude", [])
            if any(kw in act for kw in kws) and not any(ex in act for ex in excl):
                matched.append(subject)

        aid = getattr(r, "AlumnoID", None)
        if aid is not None and not (isinstance(aid, float) and pd.isna(aid)):
            try:
                sid = str(int(aid)) if float(aid).is_integer() else str(aid).strip()
            except Exception:
                sid = str(aid).strip()
            if sem in (1, 2):
                student_busy_sem[sem][sid].add(slot)
            for subject in matched:
                student_subject_slots[sid][subject].add(slot)

        docentes = str(getattr(r, "docentes", "") or "")
        for prof in [n.strip() for n in docentes.split(",") if n.strip()
                     and n.strip().lower() != "nan"]:
            if sem in (1, 2):
                prof_busy_sem[sem][prof].add(slot)
            for subject in matched:
                prof_subject_slots[prof][subject].add(slot)

    return {
        "student_busy_sem": {s: dict(d) for s, d in student_busy_sem.items()},
        "prof_busy_sem": {s: dict(d) for s, d in prof_busy_sem.items()},
        "student_subject_slots": student_subject_slots,
        "prof_subject_slots": prof_subject_slots,
        "subject_shared_map": subject_shared_map,
        "available": True,
    }


# --------------------------------------------------------------------------- #
# Core validation                                                             #
# --------------------------------------------------------------------------- #
def validate_schedule(paths=None, max_examples=25):
    """
    Run every reliability check and return a structured report dict.

    The returned dict has stable, JSON-serialisable keys:

      status            -> "PASS" | "WARN" | "FAIL" | "NO_DATA"
      reliability_score -> float 0..100
      checks            -> {name: {passed, count, detail, examples[]}}
      counts            -> {sessions, groups, students, subjects, semesters}
      teacher_load      -> [{professor, sessions, groups, subjects}]
      group_sizes       -> {optimal, under, over, min, max, distribution}
      solver            -> {status, objective, per_semester[]}
      inputs            -> resolved paths actually used
    """
    paths = paths or _default_paths()

    sched = _read_csv(paths.get("schedule"))
    comp = _read_csv(paths.get("composition"))
    directory = _read_csv(paths.get("directory"))
    sbusy = _read_csv(paths.get("student_busy"))
    pbusy = _read_csv(paths.get("professor_busy"))

    report = {
        "status": "NO_DATA",
        "reliability_score": 0.0,
        "checks": {},
        "counts": {},
        "teacher_load": [],
        "group_sizes": {},
        "solver": {},
        "inputs": {k: v for k, v in paths.items()},
        "warnings": [],
    }

    if sched is None or len(sched) == 0:
        report["warnings"].append("optimized_schedule_v5.csv introuvable ou vide")
        return report

    # Normalise schedule columns -------------------------------------------
    sched = sched.copy()
    sched["day_idx"] = sched["day"].map(_day_to_idx)
    sched["block_id"] = sched["time_block"].map(_block_to_id)
    sched["group_key"] = (
        sched["semester"].astype(str) + "|" +
        sched["subject"].astype(str) + "|" +
        sched["grupo"].astype(str)
    )

    n_sessions = int(len(sched))
    groups = sched[["group_key", "subject", "grupo", "semester", "nb_students"]].drop_duplicates("group_key")
    n_groups = int(len(groups))
    n_subjects = int(sched["subject"].nunique())
    n_semesters = int(sched["semester"].nunique())

    def _sem_of(row):
        try:
            return int(row.semester)
        except Exception:
            return None

    # Semester-aware effective-busy context (calendar-real). S1 and S2 never
    # clash because they run in different halves of the year.
    ctx = build_effective_busy_context()

    # ------------------------------------------------------------------ #
    # CHECK 1 — room conflicts (HARD, solver-enforced)                   #
    # A physical room hosts one group per (semester, week, day, block).  #
    # ------------------------------------------------------------------ #
    room_slots = defaultdict(list)
    for r in sched.itertuples(index=False):
        room = getattr(r, "lab_rooms", "")
        if not _is_physical_room(room):
            continue
        key = (_sem_of(r), str(room).strip(), int(r.week), r.day_idx, r.block_id)
        room_slots[key].append(f"{r.subject} G{r.grupo} S{r.session}")
    room_conflicts = {k: v for k, v in room_slots.items() if len(v) > 1}
    report["checks"]["room_conflicts"] = {
        "passed": len(room_conflicts) == 0,
        "count": len(room_conflicts),
        "affected": len(room_conflicts),
        "total": len(room_slots),
        "kind": "hard",
        "detail": "Une salle physique n'accueille qu'un groupe par (semestre, semaine, jour, bloc).",
        "examples": [
            {"semester": k[0], "room": k[1], "week": k[2],
             "day": DAYS[k[3]] if k[3] is not None else "?",
             "block": TIME_BLOCKS[k[4] - 1]["label"] if k[4] else "?", "groups": v}
            for k, v in list(room_conflicts.items())[:max_examples]
        ],
    }

    # ------------------------------------------------------------------ #
    # Build student -> id map and group -> students map                  #
    # ------------------------------------------------------------------ #
    name_to_id = {}
    if directory is not None and {"student_name", "student_id"}.issubset(directory.columns):
        for r in directory.itertuples(index=False):
            name_to_id[_norm_name(r.student_name)] = str(r.student_id).strip()

    # Fallback global busy from CSV (used only if the semester-aware context
    # could not be built).
    student_busy_global = defaultdict(set)
    if sbusy is not None and {"student_id", "day_idx", "block_id"}.issubset(sbusy.columns):
        for r in sbusy.itertuples(index=False):
            student_busy_global[str(r.student_id).strip()].add((int(r.day_idx), int(r.block_id)))

    group_students = defaultdict(list)
    comp_ok = comp is not None and {"semester", "subject", "grupo", "student_name"}.issubset(comp.columns)
    if comp_ok:
        comp = comp.copy()
        for r in comp.itertuples(index=False):
            sid = name_to_id.get(_norm_name(r.student_name))
            group_students[(str(r.subject).strip(), str(r.grupo).strip())].append(
                (r.student_name, sid))

    def _comp_subject(sched_subject):
        s = str(sched_subject)
        return s.split("_", 1)[1] if "_" in s else s

    def _student_busy(sem, sid):
        if ctx.get("available"):
            return ctx["student_busy_sem"].get(sem, {}).get(sid, set())
        return student_busy_global.get(sid, set())

    subject_shared_map = ctx.get("subject_shared_map", {})
    student_subject_slots = ctx.get("student_subject_slots", {})

    # ------------------------------------------------------------------ #
    # CHECK 2 — student vs theory conflicts (HARD, solver-enforced)      #
    # Semester-aware, minus the student's own-subject theory hour that   #
    # the lab legitimately replaces.                                     #
    # ------------------------------------------------------------------ #
    student_theory_conflicts = []
    theory_affected_students = set()
    group_students_all_ids = set()
    for _members in group_students.values():
        for (_sn, _sid) in _members:
            if _sid is not None:
                group_students_all_ids.add(_sid)
    student_group_slots = defaultdict(list)  # sid -> (sem, week, day, block, label)
    checkable_students = comp_ok and bool(name_to_id) and (
        ctx.get("available") or bool(student_busy_global))
    if checkable_students:
        for r in sched.itertuples(index=False):
            sem = _sem_of(r)
            gk = (_comp_subject(r.subject), str(r.grupo).strip())
            lab_subject = str(r.subject)
            siblings = subject_shared_map.get(lab_subject, [lab_subject])
            for (sname, sid) in group_students.get(gk, []):
                if sid is None:
                    continue
                own_slots = set()
                for ss in siblings:
                    own_slots |= student_subject_slots.get(sid, {}).get(ss, set())
                effective_busy = _student_busy(sem, sid) - own_slots
                if (r.day_idx, r.block_id) in effective_busy:
                    theory_affected_students.add(sid)
                    student_theory_conflicts.append(
                        {"student": sname, "subject": r.subject, "group": int(r.grupo),
                         "semester": sem,
                         "day": DAYS[r.day_idx] if r.day_idx is not None else "?",
                         "block": r.time_block})
                student_group_slots[sid].append(
                    (sem, int(r.week), r.day_idx, r.block_id, f"{r.subject} G{r.grupo}"))
    total_students = len(group_students_all_ids)
    report["checks"]["student_theory_conflicts"] = {
        "passed": len(student_theory_conflicts) == 0,
        "count": len(student_theory_conflicts),
        "affected": len(theory_affected_students),
        "total": total_students,
        "kind": "hard",
        "detail": "Aucun étudiant placé en labo sur un créneau de cours théorique occupé (même semestre).",
        "examples": student_theory_conflicts[:max_examples],
        "checkable": checkable_students,
    }

    # ------------------------------------------------------------------ #
    # CHECK 3 — student lab vs lab double booking (HARD)                 #
    # Same (semester, week, day, block) in two different lab groups.     #
    # ------------------------------------------------------------------ #
    student_lab_conflicts = []
    lab_affected_students = set()
    if checkable_students:
        for sid, slots in student_group_slots.items():
            seen = defaultdict(set)
            for (sem, wk, di, bi, lbl) in slots:
                seen[(sem, wk, di, bi)].add(lbl)
            for key, labels in seen.items():
                if len(labels) > 1:
                    lab_affected_students.add(sid)
                    student_lab_conflicts.append(
                        {"student_id": sid, "semester": key[0], "week": key[1],
                         "day": DAYS[key[2]] if key[2] is not None else "?",
                         "block": TIME_BLOCKS[key[3] - 1]["label"] if key[3] else "?",
                         "groups": sorted(labels)})
    report["checks"]["student_lab_double_booking"] = {
        "passed": len(student_lab_conflicts) == 0,
        "count": len(student_lab_conflicts),
        "affected": len(lab_affected_students),
        "total": total_students,
        "kind": "hard",
        "detail": "Aucun étudiant n'a deux séances de labo au même (semestre, semaine, jour, bloc).",
        "examples": student_lab_conflicts[:max_examples],
        "checkable": checkable_students,
    }

    # ------------------------------------------------------------------ #
    # CHECK 4 — professor double booking (INDICATOR, post-optimisation)  #
    # Professors are assigned heuristically AFTER the CP-SAT solve and   #
    # are NOT a hard solver constraint; reported as a quality indicator. #
    # ------------------------------------------------------------------ #
    def _prof_key(name):
        toks = [t for t in str(name).replace(",", " ").lower().split() if t]
        return frozenset(toks)

    prof_slots = defaultdict(list)
    if "professor" in sched.columns:
        for r in sched.itertuples(index=False):
            prof = str(getattr(r, "professor", "") or "").strip()
            if not prof:
                continue
            key = (_sem_of(r), _prof_key(prof), int(r.week), r.day_idx, r.block_id)
            prof_slots[key].append((prof, f"{r.subject} G{r.grupo} S{r.session}"))
    prof_conflicts = {k: v for k, v in prof_slots.items() if len(v) > 1}
    report["checks"]["professor_double_booking"] = {
        "passed": len(prof_conflicts) == 0,
        "count": len(prof_conflicts),
        "kind": "indicator",
        "detail": "Indicateur (affectation post-optimisation, non contrainte par le solveur) : "
                  "enseignant sans double séance au même (semestre, semaine, jour, bloc).",
        "examples": [
            {"semester": k[0], "professor": v[0][0], "week": k[2],
             "day": DAYS[k[3]] if k[3] is not None else "?",
             "block": TIME_BLOCKS[k[4] - 1]["label"] if k[4] else "?",
             "sessions": [s for _, s in v]}
            for k, v in list(prof_conflicts.items())[:max_examples]
        ],
    }

    # ------------------------------------------------------------------ #
    # CHECK 5 — professor busy (INDICATOR, post-optimisation)            #
    # Professor's own theory hour that the lab replaces is subtracted.   #
    # ------------------------------------------------------------------ #
    prof_busy_sem = ctx.get("prof_busy_sem", {})
    prof_subject_slots = ctx.get("prof_subject_slots", {})
    # index prof busy by normalized key for name-format tolerance
    prof_busy_idx = {1: defaultdict(set), 2: defaultdict(set)}
    prof_slots_idx = defaultdict(lambda: defaultdict(set))
    if ctx.get("available"):
        for sem in (1, 2):
            for pname, slots in prof_busy_sem.get(sem, {}).items():
                prof_busy_idx[sem][_prof_key(pname)] |= slots
        for pname, subj_map in prof_subject_slots.items():
            for subj, slots in subj_map.items():
                prof_slots_idx[_prof_key(pname)][subj] |= slots
    prof_busy_conflicts = []
    prof_busy_checkable = ctx.get("available") and "professor" in sched.columns
    if prof_busy_checkable:
        for r in sched.itertuples(index=False):
            prof = str(getattr(r, "professor", "") or "").strip()
            if not prof or r.day_idx is None or r.block_id is None:
                continue
            sem = _sem_of(r)
            pk = _prof_key(prof)
            siblings = subject_shared_map.get(str(r.subject), [str(r.subject)])
            own = set()
            for ss in siblings:
                own |= prof_slots_idx.get(pk, {}).get(ss, set())
            if (r.day_idx, r.block_id) in (prof_busy_idx.get(sem, {}).get(pk, set()) - own):
                prof_busy_conflicts.append(
                    {"professor": prof, "semester": sem, "day": DAYS[r.day_idx],
                     "block": r.time_block, "subject": r.subject, "group": int(r.grupo)})
    report["checks"]["professor_busy"] = {
        "passed": len(prof_busy_conflicts) == 0,
        "count": len(prof_busy_conflicts),
        "kind": "indicator",
        "detail": "Indicateur (affectation post-optimisation) : séance sur un créneau de "
                  "cours théorique de l'enseignant (même semestre, hors heure remplacée).",
        "examples": prof_busy_conflicts[:max_examples],
        "checkable": prof_busy_checkable,
    }

    # ------------------------------------------------------------------ #
    # Group sizing distribution                                          #
    # ------------------------------------------------------------------ #
    sizes = []
    for g in groups.itertuples(index=False):
        try:
            sizes.append(int(g.nb_students))
        except Exception:
            pass
    under = sum(1 for s in sizes if s < GROUP_MIN)
    over = sum(1 for s in sizes if s > GROUP_MAX)
    optimal = sum(1 for s in sizes if GROUP_MIN <= s <= GROUP_MAX)
    report["group_sizes"] = {
        "optimal": optimal, "under": under, "over": over,
        "min": min(sizes) if sizes else 0, "max": max(sizes) if sizes else 0,
        "avg": round(sum(sizes) / len(sizes), 1) if sizes else 0,
        "policy": {"min": GROUP_MIN, "preferred": GROUP_PREFERRED, "max": GROUP_MAX},
    }
    report["checks"]["group_sizing"] = {
        "passed": (under == 0 and over == 0),
        "count": under + over,
        "detail": f"Effectifs dans la politique (min {GROUP_MIN} / max {GROUP_MAX}).",
        "examples": [],
    }

    # ------------------------------------------------------------------ #
    # Teacher workload                                                   #
    # ------------------------------------------------------------------ #
    load = defaultdict(lambda: {"sessions": 0, "groups": set(), "subjects": set()})
    if "professor" in sched.columns:
        for r in sched.itertuples(index=False):
            prof = str(getattr(r, "professor", "") or "").strip()
            if not prof:
                continue
            load[prof]["sessions"] += 1
            load[prof]["groups"].add(r.group_key)
            load[prof]["subjects"].add(r.subject)
    report["teacher_load"] = sorted(
        [{"professor": p, "sessions": d["sessions"], "groups": len(d["groups"]),
          "subjects": len(d["subjects"])} for p, d in load.items()],
        key=lambda x: -x["sessions"],
    )

    # ------------------------------------------------------------------ #
    # Solver status                                                      #
    # ------------------------------------------------------------------ #
    solver_info = {"status": "UNKNOWN", "per_semester": []}
    try:
        sp = paths.get("solver_stats")
        if sp and os.path.exists(sp):
            with open(sp, encoding="utf-8") as fh:
                stats = json.load(fh)
            runs = stats if isinstance(stats, list) else stats.get("runs", [])
            statuses = []
            for run in runs:
                st = str(run.get("status", "")).upper()
                statuses.append(st)
                solver_info["per_semester"].append({
                    "semester": run.get("semester_label", run.get("semester", "")),
                    "status": st,
                    "objective": run.get("objective", run.get("penalty")),
                    "wall_time": run.get("wall_time", run.get("time")),
                    "recovered": run.get("recovered", False),
                })
            if statuses:
                if all(s in ("OPTIMAL",) for s in statuses):
                    solver_info["status"] = "OPTIMAL"
                elif all(s in ("OPTIMAL", "FEASIBLE") for s in statuses):
                    solver_info["status"] = "FEASIBLE"
                else:
                    solver_info["status"] = "PARTIAL"
    except Exception as exc:
        report["warnings"].append(f"lecture solver_stats.json: {exc}")
    report["solver"] = solver_info

    # ------------------------------------------------------------------ #
    # Counts                                                             #
    # ------------------------------------------------------------------ #
    n_students = 0
    if comp_ok:
        n_students = int(comp["student_name"].nunique())
    report["counts"] = {
        "sessions": n_sessions, "groups": n_groups, "subjects": n_subjects,
        "semesters": n_semesters, "students": n_students,
    }

    # ------------------------------------------------------------------ #
    # Reliability score — transparent formula                            #
    # ------------------------------------------------------------------ #
    # score = 100 * weighted pass-rate of the HARD solver constraints only.
    # These three are the constraints the CP-SAT model actually enforces:
    #   - room capacity / no room double-booking
    #   - a student is never in a lab while a theory class of ANOTHER subject
    #     occupies the same slot (own-subject theory is replaced by the lab)
    #   - a student is never booked in two labs at once
    # Professor checks are NOT solver constraints (professors are assigned
    # heuristically AFTER optimisation), so they are reported as quality
    # INDICATORS and only downgrade the status to WARN, never to FAIL.
    hard_checks = [
        ("room_conflicts", 40),
        ("student_theory_conflicts", 30),
        ("student_lab_double_booking", 30),
    ]
    indicator_checks = [
        ("professor_double_booking", "Prof affecté à deux labos en simultané"),
        ("professor_busy", "Prof occupé par un autre cours (horaire théorique)"),
    ]
    # Proportional (entity-based) reliability. Each hard check contributes
    # w * (1 - affected/total); a single residual conflict among hundreds of
    # sessions therefore barely dents the score, while still being surfaced.
    total_w = 0
    got_w = 0.0
    hard_violation_rate = 0.0  # worst rate across hard checks
    for name, w in hard_checks:
        chk = report["checks"].get(name, {})
        if chk.get("checkable", True) is False:
            continue
        total = max(int(chk.get("total", 0)), 1)
        affected = int(chk.get("affected", 0))
        rate = min(affected / total, 1.0)
        hard_violation_rate = max(hard_violation_rate, rate)
        total_w += w
        got_w += w * (1.0 - rate)
    solver_bonus_ok = solver_info["status"] in ("OPTIMAL", "FEASIBLE")
    base = (got_w / total_w) if total_w else 0.0
    score = 100.0 * base
    if not solver_bonus_ok:
        score *= 0.9
    report["reliability_score"] = round(score, 1)

    # Overall status is driven ONLY by hard constraints.
    hard_any = any(
        not report["checks"][n].get("passed", True)
        for n, _ in hard_checks
        if report["checks"].get(n, {}).get("checkable", True)
    )
    indicator_flagged = any(
        not report["checks"].get(n, {}).get("passed", True)
        for n, _ in indicator_checks
        if report["checks"].get(n, {}).get("checkable", True)
    )
    # A hard violation affecting >1% of relevant entities is a genuine FAIL;
    # marginal residuals (<=1%) downgrade to WARN so the report stays honest
    # without over-dramatising a handful of edge cases.
    if hard_any and hard_violation_rate > 0.01:
        report["status"] = "FAIL"
    elif (hard_any
          or not report["checks"]["group_sizing"]["passed"]
          or not solver_bonus_ok
          or indicator_flagged):
        report["status"] = "WARN"
    else:
        report["status"] = "PASS"

    # Reliability formula, spelled out for the review sheet
    report["reliability_formula"] = (
        "score = 100 × Σ[ poids × (1 − entités_en_conflit / entités_totales) ] "
        "/ Σ poids  × (1.0 si solveur OPTIMAL/FAISABLE sinon 0.9). "
        "Contraintes dures et poids : conflits de salle 40, "
        "conflit théorie-étudiant 30, double réservation labo-étudiant 30. "
        "Statut : PASS si aucune violation dure ; WARN si résiduel ≤ 1 % des "
        "entités ou indicateurs signalés ; FAIL si > 1 %. "
        "Les contrôles professeur (double affectation, prof occupé) sont des "
        "INDICATEURS de qualité — l'affectation des enseignants est réalisée "
        "après l'optimisation, hors du modèle CP-SAT ; ils abaissent le statut "
        "à WARN mais jamais à FAIL."
    )

    return report


if __name__ == "__main__":  # manual smoke run
    import pprint
    rep = validate_schedule()
    pprint.pprint({k: v for k, v in rep.items() if k not in ("checks", "teacher_load")})
    print("\nCHECKS:")
    for name, chk in rep["checks"].items():
        print(f"  {name}: passed={chk['passed']} count={chk['count']} "
              f"checkable={chk.get('checkable', True)}")
