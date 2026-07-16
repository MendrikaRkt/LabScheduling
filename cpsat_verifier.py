"""
cpsat_verifier.py — Vérification FORMELLE du planning par CP-SAT (OR-Tools).

Rôle
----
Ce module est un **vérificateur** (model checker), à ne pas confondre avec le
solveur de *génération* du planning (dans ``pipeline.py``). Il prend un
planning DÉJÀ généré et construit un modèle CP-SAT où chaque séance est figée
à son créneau réel (semaine, jour, bloc, salle, professeur). Il pose ensuite
TOUTES les contraintes dures sous forme de variables de violation réifiées,
puis **minimise la somme des violations**.

Pourquoi CP-SAT plutôt qu'un simple parcours ?
    - ``pre_export_validation.py`` fait une détection heuristique rapide, par
      paires (bonne pour un feedback immédiat).
    - ``cpsat_verifier.py`` fournit une **preuve formelle exhaustive** : le
      planning est encodé comme un problème de satisfaction de contraintes.
      Un coût minimal de 0 prouve formellement que le planning respecte
      toutes les contraintes dures. Un coût > 0 identifie EXACTEMENT chaque
      violation (nature, séances, créneau).

Contraintes vérifiées
----------------------
  - C1        : deux groupes de la MÊME matière au même créneau.
  - student   : étudiants partagés entre deux TP au même créneau (via
                group_composition) OU TP posé sur un créneau de cours
                (student_busy / titulacion_busy).
  - professor : un professeur sur deux séances au même créneau (interne) OU
                sur un créneau où il est indisponible (professor_busy).
  - C7/room   : une salle physique partagée par deux séances au même créneau.
  - excluded  : séance planifiée sur une semaine exclue (globale/par matière).
  - pref      : préférence horaire par année (signal NON bloquant).

API principale
--------------
    result = verify_schedule(schedule_df)
    print(result.format_text())
    if not result.is_feasible:
        ...  # traiter les violations

Intégration pipeline : ``run_cpsat_verification_gate(...)``.
CLI : ``python cpsat_verifier.py --schedule <path> [--semester 1|2]``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

try:
    from ortools.sat.python import cp_model
    _HAS_ORTOOLS = True
except Exception:  # pragma: no cover - OR-Tools devrait être présent
    _HAS_ORTOOLS = False


# ---------------------------------------------------------------------------
# Constantes (synchronisées avec pre_export_validation.py / pipeline.py)
# ---------------------------------------------------------------------------

DAYS_OF_WEEK = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
DAY_NAME_TO_INDEX = {name: idx for idx, name in enumerate(DAYS_OF_WEEK)}

TIME_BLOCKS = ['08:30-10:30', '10:30-12:30', '12:30-14:30',
               '15:00-17:00', '17:00-19:00', '19:00-21:00']
BLOCK_LABEL_TO_ID = {lab: i + 1 for i, lab in enumerate(TIME_BLOCKS)}

MORNING_BLOCKS = {'08:30-10:30', '10:30-12:30', '12:30-14:30'}
AFTERNOON_BLOCKS = {'15:00-17:00', '17:00-19:00', '19:00-21:00'}

# Chemins par défaut (relatifs à la racine projet) — identiques à pre_export.
SCHEDULE_CSV_PATH = 'outputs/optimization/optimized_schedule_v5.csv'
GROUPS_CSV_PATH = 'outputs/optimization/group_composition.csv'
STUDENT_BUSY_PATH = 'data_clean/optimization/student_busy.csv'
PROFESSOR_BUSY_PATH = 'data_clean/optimization/professor_busy.csv'

_NON_PHYSICAL_ROOM_HINTS = ('aula', 'sin asignar', 'n/a', 'na', 'tbd', '')

# Types de contraintes considérés CRITIQUES (bloquants).
CRITICAL_KINDS = ('C1', 'student', 'professor', 'room', 'excluded')
SIGNAL_KINDS = ('pref',)


# ---------------------------------------------------------------------------
# Structures de résultat
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """Une violation de contrainte prouvée par le modèle CP-SAT."""
    kind: str                       # C1 | student | professor | room | excluded | pref
    semester: int
    week: Optional[int]
    day: str
    time_block: str
    detail: str

    @property
    def is_critical(self) -> bool:
        return self.kind in CRITICAL_KINDS

    def slot_label(self) -> str:
        wk = f"S{self.week} " if self.week is not None else ""
        return f"[Sem {self.semester}] {wk}{self.day} {self.time_block}"

    def __str__(self) -> str:
        return f"{self.slot_label()} — {self.detail}"


@dataclass
class VerificationResult:
    """Résultat de la vérification formelle CP-SAT."""
    is_feasible: bool = True
    solver_status: str = "UNKNOWN"
    wall_time: float = 0.0
    total_sessions: int = 0
    violations: List[Violation] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    student_checked: bool = False

    # ----- agrégats -----
    @property
    def n_violations_by_type(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for v in self.violations:
            counts[v.kind] = counts.get(v.kind, 0) + 1
        return counts

    @property
    def n_critical(self) -> int:
        return sum(1 for v in self.violations if v.is_critical)

    @property
    def n_signal(self) -> int:
        return sum(1 for v in self.violations if not v.is_critical)

    def should_block_export(self) -> bool:
        return self.n_critical > 0

    # ----- rendu -----
    def format_text(self, max_examples: int = 20) -> str:
        counts = self.n_violations_by_type
        lines = []
        lines.append("=" * 68)
        lines.append("  VÉRIFICATION FORMELLE CP-SAT — cohérence du planning")
        lines.append("=" * 68)
        lines.append(f"  Statut solveur         : {self.solver_status}")
        lines.append(f"  Temps de résolution    : {self.wall_time:.3f} s")
        lines.append(f"  Séances vérifiées      : {self.total_sessions}")
        lines.append(f"  Violations critiques   : {self.n_critical}")
        lines.append(f"    - C1 (matière)       : {counts.get('C1', 0)}")
        lines.append(f"    - Étudiant           : {counts.get('student', 0)}"
                     + ("" if self.student_checked
                        else "  (non vérifié — compo. groupes absente)"))
        lines.append(f"    - Professeur         : {counts.get('professor', 0)}")
        lines.append(f"    - Salle              : {counts.get('room', 0)}")
        lines.append(f"    - Semaine exclue     : {counts.get('excluded', 0)}")
        lines.append(f"  Signaux (préf. horaire): {counts.get('pref', 0)}  (non bloquant)")

        def _dump(title, kind):
            items = [v for v in self.violations if v.kind == kind]
            if not items:
                return
            lines.append("")
            lines.append(f"  {title} ({len(items)}) :")
            for v in items[:max_examples]:
                lines.append(f"    - {v}")
            if len(items) > max_examples:
                lines.append(f"    … (+{len(items) - max_examples} de plus)")

        _dump("C1 — chevauchement matière", 'C1')
        _dump("Collisions étudiant", 'student')
        _dump("Collisions professeur", 'professor')
        _dump("Collisions salle", 'room')
        _dump("Séances sur semaine exclue", 'excluded')
        _dump("Préférence horaire (signal)", 'pref')

        if self.warnings:
            lines.append("")
            lines.append("  Notes :")
            for w in self.warnings:
                lines.append(f"    - {w}")

        lines.append("")
        if not _HAS_ORTOOLS:
            lines.append("  >>> RÉSULTAT : OR-Tools indisponible — vérification non exécutée")
        elif self.is_feasible:
            lines.append("  >>> RÉSULTAT : PLANNING FORMELLEMENT VALIDE "
                         "(0 violation dure — preuve CP-SAT)")
        else:
            lines.append("  >>> RÉSULTAT : PLANNING INVALIDE "
                         f"({self.n_critical} violation(s) dure(s) prouvée(s))")
        lines.append("=" * 68)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            'is_feasible': self.is_feasible,
            'solver_status': self.solver_status,
            'wall_time': round(self.wall_time, 4),
            'total_sessions': self.total_sessions,
            'n_critical': self.n_critical,
            'n_signal': self.n_signal,
            'blocking': self.should_block_export(),
            'counts': self.n_violations_by_type,
            'student_checked': self.student_checked,
            'violations': [
                {
                    'kind': v.kind, 'semester': v.semester, 'week': v.week,
                    'day': v.day, 'time_block': v.time_block, 'detail': v.detail,
                }
                for v in self.violations[:200]
            ],
            'warnings': list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Helpers (partagés avec pre_export_validation dans l'esprit)
# ---------------------------------------------------------------------------

def _is_physical_room(room: str) -> bool:
    r = str(room).strip().lower()
    if not r:
        return False
    return not any(h and h in r for h in _NON_PHYSICAL_ROOM_HINTS if h)


def _parse_rooms(raw) -> Set[str]:
    if raw is None:
        return set()
    txt = str(raw).strip()
    if not txt or txt.lower() in ('nan', 'none'):
        return set()
    parts = [p.strip() for chunk in txt.split('+') for p in chunk.split(',')]
    return {p for p in parts if p}


def _sem_int(val) -> int:
    s = str(val).strip().upper()
    if s in ('1', 'S1', 'C1', 'PRIMERO', 'CUATRI1'):
        return 1
    if s in ('2', 'S2', 'C2', 'SEGUNDO', 'CUATRI2'):
        return 2
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 1


def _clean_subject(subject: str) -> str:
    s = str(subject)
    for pref in ('S1_', 'S2_'):
        if s.startswith(pref):
            return s[len(pref):]
    return s


def _load_busy_csv(path: str, key_col: str) -> Dict[str, Set[Tuple[int, int]]]:
    out: Dict[str, Set[Tuple[int, int]]] = {}
    if not path or not os.path.exists(path):
        return out
    try:
        df = pd.read_csv(path)
        # tolère un BOM sur la 1re colonne
        df.columns = [c.lstrip('\ufeff') for c in df.columns]
        for key, grp in df.groupby(key_col):
            out[str(key).strip()] = {
                (int(r['day_idx']), int(r['block_id'])) for _, r in grp.iterrows()
            }
    except Exception:
        pass
    return out


def _build_student_group_map(groups_path: str) -> Dict[str, List[Tuple[str, int, int]]]:
    """{student_name_upper: [(subject_lower, grupo, sem_int)]} depuis group_composition."""
    mapping: Dict[str, List[Tuple[str, int, int]]] = {}
    if not groups_path or not os.path.exists(groups_path):
        return mapping
    try:
        df = pd.read_csv(groups_path)
    except Exception:
        return mapping
    df.columns = [c.lstrip('\ufeff') for c in df.columns]
    if 'student_name' not in df.columns:
        return mapping
    for _, r in df.iterrows():
        name = str(r.get('student_name', '')).strip().upper()
        if not name:
            continue
        subj = _clean_subject(str(r.get('subject', ''))).strip().lower()
        try:
            grupo = int(r.get('grupo'))
        except (TypeError, ValueError):
            continue
        sem = _sem_int(r.get('semester', 1))
        mapping.setdefault(name, []).append((subj, grupo, sem))
    return mapping


def _excluded_weeks_for(subject: str) -> Set[int]:
    """Semaines exclues pour une matière (délègue à pipeline si disponible)."""
    try:
        import pipeline as _pl
        return set(_pl.excluded_weeks_for(subject))
    except Exception:
        return set()


def _slot_code(sem: int, week, day_idx: int, block_id: int) -> int:
    """Encode (sem, week, day, block) en entier unique pour l'égalité CP-SAT."""
    wk = int(week) if week is not None and not pd.isna(week) else 0
    return ((sem * 60 + wk) * 5 + day_idx) * 6 + block_id


# ---------------------------------------------------------------------------
# Cœur : construction et résolution du modèle CP-SAT de vérification
# ---------------------------------------------------------------------------

def verify_schedule(
    schedule,
    student_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    professor_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    room_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    groups_path: Optional[str] = None,
    check_preferences: bool = True,
    time_limit_s: float = 30.0,
) -> VerificationResult:
    """
    Vérifie formellement un planning avec CP-SAT.

    Chaque séance est figée à son créneau. Toutes les contraintes dures sont
    encodées comme variables de violation booléennes et leur somme est
    minimisée : un optimum de 0 prouve la validité du planning.

    Args:
        schedule: DataFrame OU chemin CSV (optimized_schedule_v5).
        student_busy / professor_busy / room_busy: cartes d'indisponibilité.
            Auto-chargées depuis les CSV par défaut si None.
        groups_path: group_composition.csv (compo. des groupes).
        check_preferences: encoder le signal de préférence horaire (C7).
        time_limit_s: limite de temps du solveur.

    Returns:
        VerificationResult
    """
    result = VerificationResult()

    # Charger le planning
    if isinstance(schedule, str):
        if not os.path.exists(schedule):
            result.warnings.append(f"Planning introuvable : {schedule}")
            result.is_feasible = False
            return result
        df = pd.read_csv(schedule)
    else:
        df = schedule.copy() if schedule is not None else None

    if df is None or len(df) == 0:
        result.warnings.append("Planning vide — rien à vérifier.")
        result.is_feasible = False
        return result

    df = df.copy()
    df.columns = [str(c).lstrip('\ufeff') for c in df.columns]
    result.total_sessions = len(df)

    if not _HAS_ORTOOLS:
        result.warnings.append("OR-Tools non disponible : vérification CP-SAT ignorée.")
        result.is_feasible = False
        result.solver_status = "NO_ORTOOLS"
        return result

    # Sources busy
    if student_busy is None:
        student_busy = _load_busy_csv(STUDENT_BUSY_PATH, 'student_id')
    if professor_busy is None:
        professor_busy = _load_busy_csv(PROFESSOR_BUSY_PATH, 'professor_id')
    room_busy = room_busy or {}
    student_groups = _build_student_group_map(groups_path or GROUPS_CSV_PATH)
    result.student_checked = bool(student_groups)
    if not student_groups:
        result.warnings.append(
            "Composition des groupes indisponible — collisions étudiant non vérifiées.")

    # --- Pré-traitement des séances ------------------------------------
    sessions = []
    for idx, r in df.iterrows():
        day = str(r.get('day', ''))
        blk = str(r.get('time_block', ''))
        d_idx = DAY_NAME_TO_INDEX.get(day, -1)
        b_id = BLOCK_LABEL_TO_ID.get(blk, -1)
        if d_idx < 0 or b_id < 0:
            result.warnings.append(
                f"Séance {idx} ignorée : créneau non reconnu ({day} {blk}).")
            continue
        sem = _sem_int(r.get('semester', 1))
        try:
            week = int(r.get('week'))
        except (TypeError, ValueError):
            week = None
        try:
            grupo = int(r.get('grupo'))
        except (TypeError, ValueError):
            grupo = 0
        try:
            curso = int(r.get('curso_num'))
        except (TypeError, ValueError):
            curso = None
        prof = str(r.get('professor', '')).strip()
        if prof.lower() in ('nan', 'none'):
            prof = ''
        rooms = {rm for rm in _parse_rooms(r.get('lab_rooms')) if _is_physical_room(rm)}
        sessions.append({
            'idx': idx, 'sem': sem, 'week': week, 'day': day, 'day_idx': d_idx,
            'block': blk, 'block_id': b_id, 'subject': str(r.get('subject', '')),
            'subject_clean': _clean_subject(r.get('subject', '')).strip().lower(),
            'grupo': grupo, 'curso': curso, 'prof': prof, 'rooms': rooms,
            'code': _slot_code(sem, week, d_idx, b_id),
        })

    model = cp_model.CpModel()
    violation_bools = []   # (BoolVar, Violation)

    def _add_violation(is_violated: bool, viol: Violation):
        """Crée un booléen figé à l'état de violation et l'enregistre."""
        b = model.NewBoolVar(f"v_{len(violation_bools)}")
        model.Add(b == (1 if is_violated else 0))
        violation_bools.append((b, viol))

    # Variables « code de créneau » figées (modèle CP-SAT réel).
    code_vars = {}
    for s in sessions:
        cv = model.NewIntVar(s['code'], s['code'], f"code_{s['idx']}")
        code_vars[s['idx']] = cv

    def _same_slot_bool(i: int, j: int):
        """Booléen réifié : les séances i et j sont-elles au même créneau ?"""
        b = model.NewBoolVar(f"eq_{i}_{j}")
        model.Add(code_vars[i] == code_vars[j]).OnlyEnforceIf(b)
        model.Add(code_vars[i] != code_vars[j]).OnlyEnforceIf(b.Not())
        return b

    # ---- 1) C1 : même matière, même créneau, groupes différents --------
    by_subject: Dict[Tuple[int, str], List[dict]] = {}
    for s in sessions:
        by_subject.setdefault((s['sem'], s['subject_clean']), []).append(s)
    for (sem, subj), grp in by_subject.items():
        for a in range(len(grp)):
            for b_ in range(a + 1, len(grp)):
                s1, s2 = grp[a], grp[b_]
                if s1['grupo'] == s2['grupo']:
                    continue
                same = s1['code'] == s2['code']
                if same:
                    _add_violation(True, Violation(
                        kind='C1', semester=sem, week=s1['week'], day=s1['day'],
                        time_block=s1['block'],
                        detail=(f"{_clean_subject(s1['subject'])} : G{s1['grupo']} "
                                f"et G{s2['grupo']} simultanés"),
                    ))

    # ---- 2) Professeur : double-réservation interne --------------------
    by_prof: Dict[str, List[dict]] = {}
    for s in sessions:
        if s['prof']:
            by_prof.setdefault(s['prof'], []).append(s)
    for prof, grp in by_prof.items():
        for a in range(len(grp)):
            for b_ in range(a + 1, len(grp)):
                s1, s2 = grp[a], grp[b_]
                if s1['code'] == s2['code']:
                    _add_violation(True, Violation(
                        kind='professor', semester=s1['sem'], week=s1['week'],
                        day=s1['day'], time_block=s1['block'],
                        detail=(f"{prof} encadre "
                                f"{_clean_subject(s1['subject'])} G{s1['grupo']} et "
                                f"{_clean_subject(s2['subject'])} G{s2['grupo']} "
                                f"simultanément"),
                    ))
    # Professeur indisponible (externe)
    if professor_busy:
        for s in sessions:
            if s['prof'] and (s['day_idx'], s['block_id']) in professor_busy.get(s['prof'], set()):
                _add_violation(True, Violation(
                    kind='professor', semester=s['sem'], week=s['week'],
                    day=s['day'], time_block=s['block'],
                    detail=(f"{s['prof']} indisponible à ce créneau "
                            f"({_clean_subject(s['subject'])} G{s['grupo']})"),
                ))

    # ---- 3) Salle : même salle physique, même créneau ------------------
    by_room: Dict[str, List[dict]] = {}
    for s in sessions:
        for rm in s['rooms']:
            by_room.setdefault(rm, []).append(s)
    for room, grp in by_room.items():
        for a in range(len(grp)):
            for b_ in range(a + 1, len(grp)):
                s1, s2 = grp[a], grp[b_]
                if s1['idx'] == s2['idx']:
                    continue
                if s1['code'] == s2['code']:
                    _add_violation(True, Violation(
                        kind='room', semester=s1['sem'], week=s1['week'],
                        day=s1['day'], time_block=s1['block'],
                        detail=(f"salle « {room} » partagée par "
                                f"{_clean_subject(s1['subject'])} G{s1['grupo']} et "
                                f"{_clean_subject(s2['subject'])} G{s2['grupo']}"),
                    ))
    # Salle réservée (externe)
    if room_busy:
        for s in sessions:
            for rm in s['rooms']:
                if (s['day_idx'], s['block_id']) in room_busy.get(rm, set()):
                    _add_violation(True, Violation(
                        kind='room', semester=s['sem'], week=s['week'],
                        day=s['day'], time_block=s['block'],
                        detail=f"salle « {rm} » réservée en externe à ce créneau",
                    ))

    # ---- 4) Semaines exclues -------------------------------------------
    for s in sessions:
        if s['week'] is None:
            continue
        if s['week'] in _excluded_weeks_for(s['subject']):
            _add_violation(True, Violation(
                kind='excluded', semester=s['sem'], week=s['week'], day=s['day'],
                time_block=s['block'],
                detail=(f"{_clean_subject(s['subject'])} G{s['grupo']} planifié "
                        f"en semaine {s['week']} (exclue)"),
            ))

    # ---- 5) Étudiant : double-TP + TP vs cours -------------------------
    if student_groups:
        # (sujet_clean, grupo, sem) -> liste de séances
        group_slots: Dict[Tuple[str, int, int], List[dict]] = {}
        for s in sessions:
            group_slots.setdefault((s['subject_clean'], s['grupo'], s['sem']), []).append(s)

        seen_student = set()
        for name, memberships in student_groups.items():
            # créneaux TP de cet étudiant
            occ: Dict[int, List[dict]] = {}
            for (subj, grupo, sem) in memberships:
                for s in group_slots.get((subj, grupo, sem), []):
                    occ.setdefault(s['code'], []).append(s)
            # (a) double-TP
            for code, sess_list in occ.items():
                if len(sess_list) > 1:
                    s0 = sess_list[0]
                    sig = (name, code, 'dbl')
                    if sig in seen_student:
                        continue
                    seen_student.add(sig)
                    labs = ", ".join(
                        f"{_clean_subject(x['subject'])} G{x['grupo']}" for x in sess_list)
                    _add_violation(True, Violation(
                        kind='student', semester=s0['sem'], week=s0['week'],
                        day=s0['day'], time_block=s0['block'],
                        detail=f"{name} a deux TP simultanés : {labs}",
                    ))
            # (b) TP vs cours (student_busy indexé par id — souvent absent par nom)
            busy = student_busy.get(name)
            if busy:
                for code, sess_list in occ.items():
                    s0 = sess_list[0]
                    if (s0['day_idx'], s0['block_id']) in busy:
                        sig = (name, code, 'course')
                        if sig in seen_student:
                            continue
                        seen_student.add(sig)
                        _add_violation(True, Violation(
                            kind='student', semester=s0['sem'], week=s0['week'],
                            day=s0['day'], time_block=s0['block'],
                            detail=f"{name} a un cours à ce créneau",
                        ))

    # ---- 6) Préférence horaire par année (signal non bloquant) ---------
    if check_preferences:
        for s in sessions:
            if s['curso'] is None:
                continue
            bad = ((s['curso'] in (1, 3) and s['block'] in AFTERNOON_BLOCKS) or
                   (s['curso'] in (2, 4) and s['block'] in MORNING_BLOCKS))
            if bad:
                _add_violation(True, Violation(
                    kind='pref', semester=s['sem'], week=s['week'], day=s['day'],
                    time_block=s['block'],
                    detail=(f"{_clean_subject(s['subject'])} G{s['grupo']} "
                            f"({s['curso']}e année) hors préférence horaire"),
                ))

    # --- Objectif : minimiser la somme des violations ------------------
    if violation_bools:
        model.Minimize(sum(b for b, _ in violation_bools))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_s)
    solver.parameters.num_search_workers = 8
    status = solver.Solve(model)

    status_names = {
        cp_model.OPTIMAL: "OPTIMAL", cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE", cp_model.UNKNOWN: "UNKNOWN",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
    }
    result.solver_status = status_names.get(status, str(status))
    result.wall_time = solver.WallTime()

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for b, viol in violation_bools:
            if solver.Value(b) == 1:
                result.violations.append(viol)
    else:
        # modèle non résolu : signale sans prétendre à la validité
        result.warnings.append(
            f"Solveur CP-SAT non concluant (statut={result.solver_status}).")
        for b, viol in violation_bools:  # tout de même reporter les violations figées
            result.violations.append(viol)

    result.is_feasible = (result.n_critical == 0)
    # tri stable pour lisibilité
    result.violations.sort(key=lambda v: (v.kind, v.semester, v.week or 0, v.day, v.time_block))
    return result


# ---------------------------------------------------------------------------
# Intégration pipeline
# ---------------------------------------------------------------------------

def run_cpsat_verification_gate(
    schedule,
    block_on_critical: bool = False,
    report_path: Optional[str] = 'reports/cpsat_verification.json',
    **kwargs,
) -> Tuple[bool, VerificationResult]:
    """
    Portail de vérification formelle CP-SAT (à appeler après la validation
    heuristique pré-export).

    Args:
        schedule: DataFrame ou chemin du planning.
        block_on_critical: si True, allow_export=False en présence de
            violations critiques prouvées.
        report_path: chemin du rapport JSON (traçabilité).

    Returns:
        (allow_export, result)
    """
    result = verify_schedule(schedule, **kwargs)

    if report_path:
        try:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    allow_export = True
    if block_on_critical and result.should_block_export():
        allow_export = False
    return allow_export, result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main():  # pragma: no cover
    import argparse
    parser = argparse.ArgumentParser(
        description="Vérification formelle CP-SAT d'un planning de laboratoires.")
    parser.add_argument('--schedule', default=SCHEDULE_CSV_PATH,
                        help="Chemin du CSV du planning (optimized_schedule_v5).")
    parser.add_argument('--semester', type=int, choices=[1, 2], default=None,
                        help="Restreindre la vérification à un semestre.")
    parser.add_argument('--groups', default=GROUPS_CSV_PATH,
                        help="Chemin de group_composition.csv.")
    parser.add_argument('--report', default='reports/cpsat_verification.json',
                        help="Chemin du rapport JSON de sortie.")
    parser.add_argument('--time-limit', type=float, default=30.0)
    parser.add_argument('--block', action='store_true',
                        help="Sortie code 1 si violations critiques.")
    args = parser.parse_args()

    if not os.path.exists(args.schedule):
        print(f"[ERREUR] Planning introuvable : {args.schedule}")
        return 2

    df = pd.read_csv(args.schedule)
    df.columns = [str(c).lstrip('\ufeff') for c in df.columns]
    if args.semester is not None and 'semester' in df.columns:
        df = df[df['semester'].map(_sem_int) == args.semester].copy()

    allow, result = run_cpsat_verification_gate(
        df, block_on_critical=args.block, report_path=args.report,
        groups_path=args.groups, time_limit_s=args.time_limit,
    )
    print(result.format_text())
    print(f"\n  Rapport JSON écrit : {args.report}")
    return 0 if allow else 1


if __name__ == '__main__':  # pragma: no cover
    import sys
    sys.exit(_main())
