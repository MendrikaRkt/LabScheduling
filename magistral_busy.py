"""
magistral_busy.py — Contrainte dure « pas de TP sur un cours magistral »
=========================================================================

CONTEXTE
--------
Les fichiers Excel finaux plaçaient des séances de laboratoire (TP) sur des
créneaux déjà occupés par un cours magistral de la MÊME titulación (même année),
ce qui produisait des *collisions* (un étudiant ne peut pas être en TP et en
cours magistral simultanément).

La correction historique (``rebuild_student_constraints`` /
``pipeline.build_corrected_timetables``) dérivait l'occupation depuis les
grilles « Horarios » réelles de Daniel, MAIS uniquement lorsque
``student_directory.csv`` + ``group_composition.csv`` étaient présents pour
mapper chaque étudiant à son (titulación, année). En leur absence, aucune
contrainte n'était appliquée → les collisions réapparaissaient.

CE MODULE
---------
Fournit une contrainte **de niveau titulación** (degree-level), dérivée
DIRECTEMENT de la grille Horarios réelle et du programme de chaque étudiant
(``student_program``, déjà construit par le pipeline), SANS dépendre de
``student_directory.csv``.

Principe (identique à la règle métier existante) :
  • un étudiant de (titulación T, année A) est OCCUPÉ à tout créneau où la
    grille Horarios de (T, A) place un cours magistral ;
  • EXCEPTION « le lab remplace le cours » : le créneau d'un cours magistral
    qui correspond à la matière même du lab reste DISPONIBLE pour ce lab
    (récupéré via ``student_subject_slots``).

Ainsi, quand ``form_groups`` choisit le créneau d'un groupe, aucun créneau de
cours magistral d'une AUTRE matière n'est retenu → zéro collision.

Philosophie du projet : « le système valide, il ne décide jamais » — ici il
s'agit d'une contrainte de satisfaction (interdire un créneau physiquement
impossible), pas d'un choix arbitraire.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Optional, Set, Tuple

try:
    import horarios_grid as hg
except Exception:  # pragma: no cover - horarios_grid doit être présent
    hg = None


def build_curso_of_subject(lab_config: dict) -> Dict[str, int]:
    """Retourne {subject_key: curso_num} depuis LAB_CONFIG."""
    return {subj: int(cfg.get("curso_num"))
            for subj, cfg in lab_config.items()
            if cfg.get("curso_num") is not None}


def student_curso_map(
    subject_students: Dict[str, list],
    curso_of_subject: Dict[str, int],
) -> Dict[object, Set[int]]:
    """
    Déduit, pour chaque étudiant, l'ensemble des années (curso) auxquelles il
    est rattaché — via les matières de lab auxquelles il est inscrit.

    Retourne {student_id: {curso_num, ...}}.
    """
    out: Dict[object, Set[int]] = defaultdict(set)
    for subject, ids in subject_students.items():
        curso = curso_of_subject.get(subject)
        if curso is None:
            continue
        for sid in ids:
            out[sid].add(int(curso))
    return out


def compute_magistral_busy(
    student_program: Dict[object, str],
    subject_students: Dict[str, list],
    lab_config: dict,
    grid: Optional[dict] = None,
    matches_subject: Optional[Callable[[str, str, dict], bool]] = None,
) -> Tuple[Dict[object, Set[Tuple[int, int]]],
           Dict[object, Dict[str, Set[Tuple[int, int]]]],
           dict]:
    """
    Calcule l'occupation « cours magistral » par étudiant, au niveau titulación.

    Paramètres
    ----------
    student_program : {student_id: code_titulación}   (ex. 'GITI', 'IOI'…)
    subject_students : {subject_key: [student_id, …]}  (inscriptions labs)
    lab_config : LAB_CONFIG (contient curso_num, keywords, shared_group…)
    grid : grille Horarios chargée (hg.load_occupancy_grid()); chargée si None
    matches_subject : fonction (course_name, subject, config) -> bool
                      (règle « le lab remplace le cours de la même matière »)

    Retour
    ------
    (magistral_busy, own_subject_slots, stats)
      magistral_busy[sid]              = { (day_idx, block_id), … }  (AUTRES matières)
      own_subject_slots[sid][subject]  = { (day_idx, block_id), … }  (matière du lab)
      stats                            = dict de métriques (couverture, etc.)
    """
    if grid is None:
        if hg is None:
            raise RuntimeError("horarios_grid indisponible.")
        grid = hg.load_occupancy_grid()

    if matches_subject is None:
        matches_subject = _default_matches_subject

    curso_of_subject = build_curso_of_subject(lab_config)
    curso_map = student_curso_map(subject_students, curso_of_subject)

    # Ensemble global des étudiants concernés par un lab.
    all_ids: Set[object] = set()
    for ids in subject_students.values():
        all_ids.update(ids)

    magistral_busy: Dict[object, Set[Tuple[int, int]]] = {}
    own_subject_slots: Dict[object, Dict[str, Set[Tuple[int, int]]]] = defaultdict(
        lambda: defaultdict(set))

    stats = {
        "students_total": len(all_ids),
        "students_with_program": 0,
        "students_with_busy": 0,
        "total_busy_slots": 0,
        "missing_grid_keys": set(),
    }

    _norm = hg.normalize_titulacion if hg is not None else (lambda x: str(x).strip().upper())

    for sid in all_ids:
        prog_raw = student_program.get(sid)
        if not prog_raw:
            magistral_busy[sid] = set()
            continue
        stats["students_with_program"] += 1
        prog = _norm(prog_raw)
        cursos = curso_map.get(sid, set())

        busy: Set[Tuple[int, int]] = set()
        had_grid = False
        for curso in cursos:
            slots_map = grid.get((prog, curso))
            if not slots_map:
                stats["missing_grid_keys"].add((prog, curso))
                continue
            had_grid = True
            for (day_idx, block_id), course in slots_map.items():
                # Le créneau appartient-il à la matière d'un lab de l'étudiant ?
                own = False
                for subject, cfg in lab_config.items():
                    if curso_of_subject.get(subject) != curso:
                        continue
                    if matches_subject(course, subject, cfg):
                        own_subject_slots[sid][subject].add((day_idx, block_id))
                        own = True
                if not own:
                    busy.add((day_idx, block_id))
        magistral_busy[sid] = busy
        if busy:
            stats["students_with_busy"] += 1
            stats["total_busy_slots"] += len(busy)

    stats["missing_grid_keys"] = sorted(stats["missing_grid_keys"])
    return magistral_busy, own_subject_slots, stats


def apply_to_student_busy(
    student_busy: Dict[object, Set[Tuple[int, int]]],
    student_subject_slots,
    student_program: Dict[object, str],
    subject_students: Dict[str, list],
    lab_config: dict,
    grid: Optional[dict] = None,
    matches_subject: Optional[Callable[[str, str, dict], bool]] = None,
    verbose: bool = True,
) -> dict:
    """
    Fusionne la contrainte « cours magistral » (niveau titulación) DANS les
    structures existantes du pipeline, en place.

      • student_busy[sid]              ∪= créneaux magistraux d'AUTRES matières
      • student_subject_slots[sid][s]  ∪= créneaux du cours remplacé par le lab s

    Retourne les statistiques. Ne « libère » jamais un créneau : on n'ajoute que
    des occupations (contrainte plus stricte, jamais plus laxiste).
    """
    magistral_busy, own_slots, stats = compute_magistral_busy(
        student_program, subject_students, lab_config,
        grid=grid, matches_subject=matches_subject,
    )

    for sid, slots in magistral_busy.items():
        if slots:
            student_busy.setdefault(sid, set()).update(slots)
    for sid, by_subject in own_slots.items():
        for subject, slots in by_subject.items():
            student_subject_slots[sid][subject].update(slots)

    if verbose:
        print(f"  [CONTRAINTE Horarios] cours magistraux (niveau titulación) "
              f"appliqués : {stats['students_with_busy']}/{stats['students_total']} "
              f"étudiants occupés, {stats['total_busy_slots']} créneaux bloqués.")
        if stats["missing_grid_keys"]:
            keys = ", ".join(f"{t}/{c}" for t, c in stats["missing_grid_keys"])
            print(f"  [CONTRAINTE Horarios] (titulación, curso) sans grille : {keys}")

    return stats


def build_subject_semester(lab_config: dict) -> Dict[str, int]:
    """Retourne {subject_key: semester} depuis LAB_CONFIG."""
    return {subj: int(cfg.get("semester"))
            for subj, cfg in lab_config.items()
            if cfg.get("semester") is not None}


def build_magistral_busy_by_sem(
    student_program: Dict[object, str],
    subject_students: Dict[str, list],
    lab_config: dict,
    grid_sem: Optional[dict] = None,
    matches_subject: Optional[Callable[[str, str, dict], bool]] = None,
) -> Tuple[Dict[int, Dict[object, Set[Tuple[int, int]]]],
           Dict[object, Dict[str, Set[Tuple[int, int]]]],
           dict]:
    """
    Occupation « cours magistral » par SEMESTRE et par étudiant, au niveau
    titulación, dérivée de la grille Horarios réelle **par semestre**
    (``horarios_grid.load_occupancy_grid_semester``).

    Retour
    ------
    (mag_by_sem, own_subject_slots, stats)
      mag_by_sem[sem][sid]            = { (day_idx, block_id), ... }
          → occupation magistrale COMPLÈTE (toutes matières) de la titulación
            de l'étudiant pour ce semestre. L'exception « le lab remplace le
            cours de sa propre matière » n'est PAS retirée ici : elle est gérée
            en aval par ``form_groups`` via ``student_subject_slots`` (soustrait
            ``own_slots`` matière par matière → gère aussi les groupes partagés).
      own_subject_slots[sid][subject] = { (day_idx, block_id), ... }
          → créneaux du cours magistral correspondant à la matière du lab
            ``subject`` (à injecter dans ``student_subject_slots``).
      stats                           = métriques (couverture, clés manquantes).
    """
    if grid_sem is None:
        if hg is None:
            raise RuntimeError("horarios_grid indisponible.")
        grid_sem = hg.load_occupancy_grid_semester()

    if matches_subject is None:
        matches_subject = _default_matches_subject

    curso_of_subject = build_curso_of_subject(lab_config)
    sem_of_subject = build_subject_semester(lab_config)
    curso_map = student_curso_map(subject_students, curso_of_subject)

    # Inscriptions : {student_id: {subject, ...}} pour savoir quels créneaux
    # « propres » (matière remplacée) libérer pour cet étudiant.
    enrolled_subjects: Dict[object, Set[str]] = defaultdict(set)
    for subject, ids in subject_students.items():
        for sid in ids:
            enrolled_subjects[sid].add(subject)

    all_ids: Set[object] = set()
    for ids in subject_students.values():
        all_ids.update(ids)

    mag_by_sem: Dict[int, Dict[object, Set[Tuple[int, int]]]] = {
        1: defaultdict(set), 2: defaultdict(set)}
    own_subject_slots: Dict[object, Dict[str, Set[Tuple[int, int]]]] = defaultdict(
        lambda: defaultdict(set))

    stats = {
        "students_total": len(all_ids),
        "students_with_program": 0,
        "students_with_busy": 0,
        "total_busy_slots": 0,
        "missing_grid_keys": set(),
    }

    _norm = hg.normalize_titulacion if hg is not None else (lambda x: str(x).strip().upper())

    for sid in all_ids:
        prog_raw = student_program.get(sid)
        if not prog_raw:
            continue
        stats["students_with_program"] += 1
        prog = _norm(prog_raw)
        cursos = curso_map.get(sid, set())
        my_subjects = enrolled_subjects.get(sid, set())
        touched = False

        for curso in cursos:
            for sem in (1, 2):
                slots_map = grid_sem.get((prog, curso, sem))
                if not slots_map:
                    stats["missing_grid_keys"].add((prog, curso, sem))
                    continue
                for (day_idx, block_id), course in slots_map.items():
                    # Occupation complète pour ce semestre.
                    mag_by_sem[sem][sid].add((day_idx, block_id))
                    touched = True
                    stats["total_busy_slots"] += 1
                    # Le créneau correspond-il à une matière de lab de l'étudiant
                    # pour CE curso ET CE semestre ? → créneau « propre ».
                    for subject in my_subjects:
                        if curso_of_subject.get(subject) != curso:
                            continue
                        if sem_of_subject.get(subject) != sem:
                            continue
                        cfg = lab_config.get(subject, {})
                        if matches_subject(course, subject, cfg):
                            own_subject_slots[sid][subject].add((day_idx, block_id))
        if touched:
            stats["students_with_busy"] += 1

    stats["missing_grid_keys"] = sorted(stats["missing_grid_keys"])
    # Convertit les defaultdict internes en dict standard.
    mag_by_sem = {sem: dict(d) for sem, d in mag_by_sem.items()}
    return mag_by_sem, own_subject_slots, stats


def apply_magistral_by_sem(
    student_subject_slots,
    student_program: Dict[object, str],
    subject_students: Dict[str, list],
    lab_config: dict,
    grid_sem: Optional[dict] = None,
    matches_subject: Optional[Callable[[str, str, dict], bool]] = None,
    verbose: bool = True,
) -> Tuple[Dict[int, Dict[object, Set[Tuple[int, int]]]],
           Dict[int, Dict[object, Dict[str, Set[Tuple[int, int]]]]],
           dict]:
    """
    Prépare la contrainte magistrale **par semestre** pour ``form_groups``.

    La contrainte est SPÉCIFIQUE À LA MATIÈRE placée : au moment de poser un
    groupe de la matière ``S``, les créneaux INTERDITS sont
    ``mag_full[sem][sid] − own[sem][sid][S']`` (S' parcourant le groupe partagé
    de ``S``). Autrement dit : TOUS les cours magistraux de la titulación de
    l'étudiant SAUF ceux de la matière ``S`` elle-même (exception « le lab
    remplace le cours de SA PROPRE matière »). Ceci évite qu'un lab d'une AUTRE
    matière n'occupe le créneau magistral d'une matière que l'étudiant suit
    aussi (fuite de l'ancienne agrégation « own » toutes matières confondues).

    Retour
    ------
    (mag_full_by_sem, own_by_sem_subject, stats)
      mag_full_by_sem[sem][sid]            = occupation magistrale COMPLÈTE.
      own_by_sem_subject[sem][sid][subject] = créneaux magistraux de la matière
                                              ``subject`` (exception à autoriser).

    Augmente aussi ``student_subject_slots`` (rétro-compat), mais la contrainte
    dure côté ``form_groups`` s'appuie sur les deux structures ci-dessus.
    N'ajoute jamais de disponibilité (contrainte plus stricte, jamais plus laxiste).
    """
    mag_by_sem, own_slots, stats = build_magistral_busy_by_sem(
        student_program, subject_students, lab_config,
        grid_sem=grid_sem, matches_subject=matches_subject,
    )

    # Créneaux « propres » (cours remplacé par le lab de la MÊME matière),
    # dérivés de la GRILLE (pas du master), indexés PAR SEMESTRE ET PAR MATIÈRE.
    sem_of_subject = build_subject_semester(lab_config)
    own_by_sem_subject: Dict[int, Dict[object, Dict[str, Set[Tuple[int, int]]]]] = {
        1: {}, 2: {}}
    for sid, by_subject in own_slots.items():
        for subject, slots in by_subject.items():
            student_subject_slots[sid][subject].update(slots)
            sem = sem_of_subject.get(subject)
            if sem in (1, 2):
                own_by_sem_subject[sem].setdefault(sid, {}).setdefault(
                    subject, set()).update(slots)

    # Statistiques indicatives : nombre de créneaux magistraux « autres matières »
    # dans le pire cas (occupation complète moins l'union des créneaux propres),
    # à titre de reporting uniquement — la contrainte réelle est par-matière.
    n_forbidden = {1: 0, 2: 0}
    for sem in (1, 2):
        for sid, slots in mag_by_sem.get(sem, {}).items():
            own_union = set()
            for s2 in own_by_sem_subject[sem].get(sid, {}).values():
                own_union |= s2
            n_forbidden[sem] += len(set(slots) - own_union)

    if verbose:
        print(f"  [CONTRAINTE Horarios/sem] cours magistraux appliqués : "
              f"{stats['students_with_busy']}/{stats['students_total']} étudiants ; "
              f"créneaux INTERDITS (autres matières) S1={n_forbidden[1]}, S2={n_forbidden[2]}.")
        if stats["missing_grid_keys"]:
            keys = ", ".join(f"{t}/{c}/S{s}" for t, c, s in stats["missing_grid_keys"])
            print(f"  [CONTRAINTE Horarios/sem] (titulación, curso, sem) sans grille : {keys}")

    return mag_by_sem, own_by_sem_subject, stats


def _default_matches_subject(course_name: str, subject: str, config: dict) -> bool:
    """Repli minimal si aucune fonction de correspondance n'est fournie."""
    if not course_name:
        return False
    course = str(course_name).strip().lower()
    for kw in config.get("keywords", []):
        if kw and str(kw).strip().lower() in course:
            for ex in config.get("keyword_exclude", []):
                if ex and str(ex).strip().lower() in course:
                    return False
            return True
    return False
