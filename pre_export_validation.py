"""
pre_export_validation.py — Contrôle de fiabilité AVANT l'export Excel (TASK 5).

Objectif
--------
Valider le planning COMPLET juste avant les exports (format Daniel, Vista…)
afin de garantir qu'aucune collision critique ne parte en production. Ce
module est volontairement autonome : il ne dépend pas de ``pipeline`` et peut
être appelé sur un DataFrame en mémoire OU sur le CSV ``optimized_schedule_v5``.

Il détecte :
  - C1  : deux séances de la MÊME matière au même créneau (semestre, semaine,
          jour, bloc) — chevauchement matière.
  - C4  : une même salle physique occupée par deux séances au même créneau.
  - Professeur : un même professeur encadrant deux séances au même créneau,
          ou placé sur un créneau où il est indisponible (professor_busy).
  - Étudiant : un étudiant présent dans deux TP au même créneau, ou un TP
          placé là où l'étudiant a un cours (student_busy).  [best-effort :
          nécessite la composition des groupes]
  - C7  : préférence horaire par année (1re/3e = matin, 2e/4e = après-midi).
          NON bloquant — compté comme signal de qualité.

Sévérité
--------
CRITIQUE (bloque l'export) : C1, C4, collisions étudiant, collisions
professeur (double-réservation interne).  Les indisponibilités externes
(professor_busy/room_busy) et C7 sont des AVERTISSEMENTS (non bloquants) car
elles peuvent être « attendues » (contrainte relâchée en amont).

API principale
--------------
    report = validate_complete_schedule(schedule, student_busy, professor_busy,
                                         room_busy)
    if report.should_block_export():
        ...  # bloquer l'export
    print(report.format_text())
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd


# ---------------------------------------------------------------------------
# Constantes (synchronisées avec pipeline.py / manual_edit.py)
# ---------------------------------------------------------------------------

DAYS_OF_WEEK = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
DAY_NAME_TO_INDEX = {name: idx for idx, name in enumerate(DAYS_OF_WEEK)}

TIME_BLOCKS = ['08:30-10:30', '10:30-12:30', '12:30-14:30',
               '15:00-17:00', '17:00-19:00', '19:00-21:00']
BLOCK_LABEL_TO_ID = {lab: i + 1 for i, lab in enumerate(TIME_BLOCKS)}

MORNING_BLOCKS = ['08:30-10:30', '10:30-12:30', '12:30-14:30']
AFTERNOON_BLOCKS = ['15:00-17:00', '17:00-19:00', '19:00-21:00']

# Chemins par défaut (relatifs à la racine projet)
SCHEDULE_CSV_PATH = 'outputs/optimization/optimized_schedule_v5.csv'
GROUPS_CSV_PATH = 'outputs/optimization/group_composition.csv'
STUDENT_BUSY_PATH = 'data_clean/optimization/student_busy.csv'
PROFESSOR_BUSY_PATH = 'data_clean/optimization/professor_busy.csv'

# Salles "logiques" à ignorer pour C4 (pas des salles physiques uniques)
_NON_PHYSICAL_ROOM_HINTS = ('aula', 'sin asignar', 'n/a', 'na', 'tbd', '')


# ---------------------------------------------------------------------------
# Structures de résultat
# ---------------------------------------------------------------------------

@dataclass
class Collision:
    """Une collision détectée, avec assez de contexte pour l'afficher."""
    kind: str                 # 'C1' | 'C4' | 'student' | 'professor' | 'C7'
    semester: int
    week: Optional[int]
    day: str
    time_block: str
    detail: str               # message lisible

    def slot_label(self) -> str:
        wk = f"S{self.week} " if self.week is not None else ""
        return f"[Sem {self.semester}] {wk}{self.day} {self.time_block}"

    def __str__(self) -> str:
        return f"{self.slot_label()} — {self.detail}"


@dataclass
class ValidationReport:
    """
    Rapport de validation complet.

    Listes de collisions par type + score de qualité (0-100) + agrégats.
    """
    c1: List[Collision] = field(default_factory=list)          # chevauchement matière
    c4: List[Collision] = field(default_factory=list)          # salle
    student: List[Collision] = field(default_factory=list)     # étudiant
    professor: List[Collision] = field(default_factory=list)   # professeur
    c7: List[Collision] = field(default_factory=list)          # préférence horaire
    warnings: List[str] = field(default_factory=list)          # notes (checks non exécutés…)
    total_sessions: int = 0
    quality_score: float = 100.0
    student_checked: bool = False   # la vérif étudiant a-t-elle pu tourner ?

    # ----- agrégats -----
    @property
    def n_critical(self) -> int:
        """Nombre de collisions CRITIQUES (bloquantes)."""
        return len(self.c1) + len(self.c4) + len(self.student) + len(self.professor)

    @property
    def n_total(self) -> int:
        return self.n_critical + len(self.c7)

    def should_block_export(self) -> bool:
        """True si au moins une collision critique impose de bloquer l'export."""
        return self.n_critical > 0

    # ----- rendu -----
    def format_text(self, max_examples: int = 15) -> str:
        lines = []
        lines.append("=" * 68)
        lines.append("  VALIDATION PRÉ-EXPORT — fiabilité du planning")
        lines.append("=" * 68)
        lines.append(f"  Séances analysées      : {self.total_sessions}")
        lines.append(f"  Score de qualité       : {self.quality_score:.1f}/100")
        lines.append(f"  Collisions critiques   : {self.n_critical}")
        lines.append(f"    - C1 (matière)       : {len(self.c1)}")
        lines.append(f"    - C4 (salle)         : {len(self.c4)}")
        lines.append(f"    - Étudiant           : {len(self.student)}"
                     + ("" if self.student_checked else "  (non vérifié — compo. groupes absente)"))
        lines.append(f"    - Professeur         : {len(self.professor)}")
        lines.append(f"  Signaux qualité (C7)   : {len(self.c7)}  (non bloquant)")

        def _dump(title, items):
            if not items:
                return
            lines.append("")
            lines.append(f"  {title} ({len(items)}) :")
            for c in items[:max_examples]:
                lines.append(f"    - {c}")
            if len(items) > max_examples:
                lines.append(f"    … (+{len(items) - max_examples} de plus)")

        _dump("C1 — chevauchement matière", self.c1)
        _dump("C4 — salle occupée", self.c4)
        _dump("Collisions étudiant", self.student)
        _dump("Collisions professeur", self.professor)
        _dump("C7 — préférence horaire (signal)", self.c7)

        if self.warnings:
            lines.append("")
            lines.append("  Notes :")
            for w in self.warnings:
                lines.append(f"    - {w}")

        lines.append("")
        if self.should_block_export():
            lines.append("  >>> RÉSULTAT : EXPORT BLOQUÉ (collisions critiques présentes)")
        else:
            lines.append("  >>> RÉSULTAT : OK — aucune collision critique, export autorisé")
        lines.append("=" * 68)
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            'total_sessions': self.total_sessions,
            'quality_score': round(self.quality_score, 2),
            'n_critical': self.n_critical,
            'blocking': self.should_block_export(),
            'counts': {
                'C1': len(self.c1), 'C4': len(self.c4),
                'student': len(self.student), 'professor': len(self.professor),
                'C7': len(self.c7),
            },
            'student_checked': self.student_checked,
            'examples': {
                'C1': [str(c) for c in self.c1[:25]],
                'C4': [str(c) for c in self.c4[:25]],
                'student': [str(c) for c in self.student[:25]],
                'professor': [str(c) for c in self.professor[:25]],
                'C7': [str(c) for c in self.c7[:25]],
            },
            'warnings': list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_physical_room(room: str) -> bool:
    r = str(room).strip().lower()
    if not r:
        return False
    return not any(h and h in r for h in _NON_PHYSICAL_ROOM_HINTS if h)


def _parse_rooms(raw) -> Set[str]:
    """'Ciencias I + Ciencias II' -> {'Ciencias I', 'Ciencias II'}."""
    if raw is None:
        return set()
    txt = str(raw).strip()
    if not txt or txt.lower() in ('nan', 'none'):
        return set()
    parts = [p.strip() for chunk in txt.split('+') for p in chunk.split(',')]
    return {p for p in parts if p}


def _sem_int(val) -> int:
    """Normalise un semestre en 1/2 depuis 1, 2, 'S1', 'C1'…"""
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
    """Charge un CSV busy (key_col, day_idx, block_id) -> {key: {(day,block)}}."""
    out: Dict[str, Set[Tuple[int, int]]] = {}
    if not path or not os.path.exists(path):
        return out
    try:
        df = pd.read_csv(path)
        for key, grp in df.groupby(key_col):
            out[str(key).strip()] = {
                (int(r['day_idx']), int(r['block_id'])) for _, r in grp.iterrows()
            }
    except Exception:
        pass
    return out


def _build_student_group_map(groups_path: str) -> Dict[str, List[Tuple[str, int]]]:
    """
    Construit {student_name_upper: [(subject_display, grupo), …]} depuis
    group_composition.csv. Utilisé pour rattacher un étudiant à ses TP.
    """
    mapping: Dict[str, List[Tuple[str, int]]] = {}
    if not groups_path or not os.path.exists(groups_path):
        return mapping
    try:
        df = pd.read_csv(groups_path)
    except Exception:
        return mapping
    if 'student_name' not in df.columns:
        return mapping
    for _, r in df.iterrows():
        name = str(r.get('student_name', '')).strip().upper()
        if not name:
            continue
        subj = str(r.get('subject', '')).strip()
        try:
            grupo = int(r.get('grupo'))
        except (TypeError, ValueError):
            continue
        mapping.setdefault(name, []).append((subj, grupo))
    return mapping


def _subject_matches(sched_subject: str, comp_subject: str) -> bool:
    """'S1_Física' ~ 'Física' (comparaison par suffixe, insensible casse)."""
    a = _clean_subject(sched_subject).strip().lower()
    b = str(comp_subject).strip().lower()
    if not a or not b:
        return False
    return a == b or a.endswith(b) or b.endswith(a)


# ---------------------------------------------------------------------------
# Cœur de la validation
# ---------------------------------------------------------------------------

def validate_complete_schedule(
    schedule,
    student_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    professor_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    room_busy: Optional[Dict[str, Set[Tuple[int, int]]]] = None,
    groups_path: Optional[str] = None,
) -> ValidationReport:
    """
    Valide le planning complet et renvoie un :class:`ValidationReport`.

    Args:
        schedule: DataFrame du planning OU chemin vers optimized_schedule_v5.csv.
            Colonnes attendues : semester, subject, grupo, session, week, day,
            time_block, lab_rooms, professor, curso_num (optionnelle).
        student_busy: {student_id: {(day_idx, block_id)}} indisponibilités
            « cours » des étudiants. Si None, chargé depuis STUDENT_BUSY_PATH.
        professor_busy: {professor: {(day_idx, block_id)}}. Si None, chargé
            depuis PROFESSOR_BUSY_PATH.
        room_busy: {room: {(day_idx, block_id)}} réservations externes de salles
            (optionnel, aucune source par défaut).
        groups_path: chemin de group_composition.csv (pour la vérif étudiant).
            Si None, GROUPS_CSV_PATH.

    Returns:
        ValidationReport
    """
    # 1) Charger le planning
    if isinstance(schedule, str):
        df = pd.read_csv(schedule)
    else:
        df = schedule.copy()

    report = ValidationReport()
    if df is None or len(df) == 0:
        report.warnings.append("Planning vide — rien à valider.")
        report.quality_score = 0.0
        return report

    # Normalisation colonnes
    df = df.copy()
    df['_sem'] = df['semester'].map(_sem_int)
    df['_prof'] = df.get('professor', '').astype(str).str.strip() if 'professor' in df.columns else ''
    report.total_sessions = len(df)

    # Sources busy (auto-chargement si non fourni)
    if student_busy is None:
        student_busy = _load_busy_csv(STUDENT_BUSY_PATH, 'student_id')
    if professor_busy is None:
        professor_busy = _load_busy_csv(PROFESSOR_BUSY_PATH, 'professor_id')
    room_busy = room_busy or {}

    # 2) C1 — chevauchement matière (même subject, même créneau, grupos ≠)
    slot_cols = ['_sem', 'week', 'day', 'time_block']
    for (sem, subj), sub in df.groupby(['_sem', 'subject']):
        for (wk, day, blk), rows in sub.groupby(['week', 'day', 'time_block']):
            grupos = sorted({int(g) for g in rows['grupo']})
            if len(grupos) > 1:
                report.c1.append(Collision(
                    kind='C1', semester=int(sem), week=int(wk), day=str(day),
                    time_block=str(blk),
                    detail=(f"{_clean_subject(subj)} : {len(grupos)} groupes "
                            f"simultanés (G{', G'.join(map(str, grupos))})"),
                ))

    # 3) C4 — salle occupée par 2 séances au même créneau
    for (sem, wk, day, blk), rows in df.groupby(slot_cols):
        room_users: Dict[str, List[str]] = {}
        for _, r in rows.iterrows():
            for room in _parse_rooms(r.get('lab_rooms')):
                if not _is_physical_room(room):
                    continue
                who = f"{_clean_subject(r['subject'])} G{int(r['grupo'])}"
                room_users.setdefault(room, []).append(who)
        for room, users in room_users.items():
            if len(users) > 1:
                report.c4.append(Collision(
                    kind='C4', semester=int(sem), week=int(wk), day=str(day),
                    time_block=str(blk),
                    detail=f"salle « {room} » partagée par {', '.join(users)}",
                ))

    # 4) Professeur — double-réservation interne + indisponibilité externe
    if '_prof' in df.columns:
        for (sem, wk, day, blk), rows in df.groupby(slot_cols):
            prof_users: Dict[str, List[str]] = {}
            for _, r in rows.iterrows():
                prof = str(r.get('_prof', '')).strip()
                if not prof or prof.lower() in ('nan', 'none'):
                    continue
                who = f"{_clean_subject(r['subject'])} G{int(r['grupo'])}"
                prof_users.setdefault(prof, []).append(who)
            for prof, users in prof_users.items():
                if len(users) > 1:
                    report.professor.append(Collision(
                        kind='professor', semester=int(sem), week=int(wk),
                        day=str(day), time_block=str(blk),
                        detail=f"{prof} encadre {', '.join(users)} simultanément",
                    ))

        # Indisponibilité externe (professor_busy) — AVERTISSEMENT
        if professor_busy:
            for _, r in df.iterrows():
                prof = str(r.get('_prof', '')).strip()
                if not prof:
                    continue
                d_idx = DAY_NAME_TO_INDEX.get(str(r['day']), -1)
                b_id = BLOCK_LABEL_TO_ID.get(str(r['time_block']), -1)
                if d_idx < 0 or b_id < 0:
                    continue
                if (d_idx, b_id) in professor_busy.get(prof, set()):
                    report.warnings.append(
                        f"[prof indispo] {prof} placé {r['day']} {r['time_block']} "
                        f"(S{int(r['week'])}) alors qu'il est marqué occupé "
                        f"({_clean_subject(r['subject'])} G{int(r['grupo'])})"
                    )

    # 5) Salle — réservation externe (room_busy) — AVERTISSEMENT
    if room_busy:
        for _, r in df.iterrows():
            d_idx = DAY_NAME_TO_INDEX.get(str(r['day']), -1)
            b_id = BLOCK_LABEL_TO_ID.get(str(r['time_block']), -1)
            if d_idx < 0 or b_id < 0:
                continue
            for room in _parse_rooms(r.get('lab_rooms')):
                if (d_idx, b_id) in room_busy.get(room, set()):
                    report.warnings.append(
                        f"[salle réservée] {room} utilisée {r['day']} "
                        f"{r['time_block']} malgré une réservation externe"
                    )

    # 6) Étudiant — best-effort (nécessite la compo. des groupes)
    _validate_students(df, report, student_busy, groups_path or GROUPS_CSV_PATH)

    # 7) C7 — préférence horaire par année (signal, non bloquant)
    if 'curso_num' in df.columns:
        for _, r in df.iterrows():
            try:
                curso = int(r['curso_num'])
            except (TypeError, ValueError):
                continue
            blk = str(r['time_block'])
            bad = ((curso in (1, 3) and blk in AFTERNOON_BLOCKS) or
                   (curso in (2, 4) and blk in MORNING_BLOCKS))
            if bad:
                report.c7.append(Collision(
                    kind='C7', semester=_sem_int(r['semester']),
                    week=int(r['week']) if not pd.isna(r['week']) else None,
                    day=str(r['day']), time_block=blk,
                    detail=(f"{_clean_subject(r['subject'])} G{int(r['grupo'])} "
                            f"({curso}e année) hors préférence horaire"),
                ))

    # 8) Score de qualité
    report.quality_score = _compute_quality_score(report)
    return report


def _validate_students(df, report, student_busy, groups_path):
    """Détecte les collisions étudiant (double-TP + TP vs cours)."""
    student_groups = _build_student_group_map(groups_path)
    if not student_groups:
        report.warnings.append(
            "Composition des groupes indisponible — collisions étudiant non vérifiées."
        )
        report.student_checked = False
        return
    report.student_checked = True

    # Index : (subject_display, grupo) -> liste de (sem, week, day, block)
    # On rattache chaque groupe du planning à un libellé matière « display ».
    group_slots: Dict[Tuple[str, int], List[Tuple[int, int, str, str]]] = {}
    for _, r in df.iterrows():
        key = (_clean_subject(r['subject']).strip().lower(), int(r['grupo']))
        group_slots.setdefault(key, []).append(
            (_sem_int(r['semester']), int(r['week']), str(r['day']), str(r['time_block']))
        )

    seen = set()   # dédup (student, sem, week, day, block, kind)
    for name, memberships in student_groups.items():
        # Créneaux TP de cet étudiant
        occ: Dict[Tuple[int, int, str, str], List[str]] = {}
        for (comp_subj, grupo) in memberships:
            key = (str(comp_subj).strip().lower(), grupo)
            for slot in group_slots.get(key, []):
                occ.setdefault(slot, []).append(f"{comp_subj} G{grupo}")

        # (a) double-TP au même (sem, week, day, block)
        for slot, labs in occ.items():
            if len(labs) > 1:
                sem, wk, day, blk = slot
                sig = (name, sem, wk, day, blk, 'dbl')
                if sig in seen:
                    continue
                seen.add(sig)
                report.student.append(Collision(
                    kind='student', semester=sem, week=wk, day=day, time_block=blk,
                    detail=f"{name} a deux TP simultanés : {', '.join(labs)}",
                ))

        # (b) TP placé là où l'étudiant a un cours (student_busy)
        busy = student_busy.get(name) or student_busy.get(str(name))
        # student_busy est indexé par id, pas par nom : ignore si absent
        if not busy:
            continue
        for slot, labs in occ.items():
            sem, wk, day, blk = slot
            d_idx = DAY_NAME_TO_INDEX.get(day, -1)
            b_id = BLOCK_LABEL_TO_ID.get(blk, -1)
            if d_idx < 0 or b_id < 0:
                continue
            if (d_idx, b_id) in busy:
                sig = (name, sem, wk, day, blk, 'course')
                if sig in seen:
                    continue
                seen.add(sig)
                report.student.append(Collision(
                    kind='student', semester=sem, week=wk, day=day, time_block=blk,
                    detail=f"{name} a un cours à ce créneau ({', '.join(labs)})",
                ))


def _compute_quality_score(report: ValidationReport) -> float:
    """
    Score 0-100. Les collisions critiques pèsent lourd ; C7 légèrement.

    100 = planning parfait. Chaque collision critique retire des points
    (proportionnellement au nombre de séances pour rester interprétable).
    """
    n = max(report.total_sessions, 1)
    # Pénalités (par collision, en points de pourcentage) — critiques fortes.
    pen_critical = 100.0 * report.n_critical / n * 1.5
    pen_c7 = 100.0 * len(report.c7) / n * 0.25
    score = 100.0 - pen_critical - pen_c7
    return max(0.0, min(100.0, score))


# ---------------------------------------------------------------------------
# Intégration pipeline
# ---------------------------------------------------------------------------

def run_pre_export_gate(
    schedule,
    block_on_critical: bool = True,
    report_path: Optional[str] = 'reports/pre_export_validation.json',
    **kwargs,
) -> Tuple[bool, ValidationReport]:
    """
    Portail de validation à appeler AVANT les exports Excel.

    Args:
        schedule: DataFrame ou chemin du planning.
        block_on_critical: si True, renvoie allow=False en cas de collision
            critique (l'appelant décide de bloquer l'export).
        report_path: si fourni, écrit le rapport JSON pour traçabilité.

    Returns:
        (allow_export, report)
          allow_export = False s'il faut bloquer (collisions critiques).
    """
    report = validate_complete_schedule(schedule, **kwargs)

    # Traçabilité : rapport JSON
    if report_path:
        try:
            import json
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    allow_export = True
    if block_on_critical and report.should_block_export():
        allow_export = False
    return allow_export, report


if __name__ == '__main__':  # pragma: no cover
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else SCHEDULE_CSV_PATH
    rep = validate_complete_schedule(path)
    print(rep.format_text())
    sys.exit(1 if rep.should_block_export() else 0)
