"""Tests de la contrainte dure « pas de TP sur un cours magistral »
(``magistral_busy``) et de la propriété MATIÈRE-CONSCIENTE de la vue
``pipeline._SemesterAwareLabBusy``.

Objectif métier : un lab ne doit jamais être posé sur un créneau où la grille
Horarios réelle place un cours magistral d'une AUTRE matière que celle du lab —
y compris lorsqu'il s'agit d'une matière que l'étudiant suit aussi (c'est la
fuite corrigée : ex. un lab « Modelado » posé sur le magistral « Mecánica de
fluidos » d'un étudiant inscrit aux deux).

Les tests n'utilisent AUCUN fichier de production : la grille Horarios est
fournie en argument (``grid_sem``) sous forme synthétique.
"""

from collections import defaultdict

import magistral_busy as mb


# --- Données synthétiques -------------------------------------------------

def _lab_config():
    # Deux matières de lab, même titulación/année/semestre.
    return {
        "S1_A": {"curso_num": 1, "semester": 1, "keywords": ["aaa"]},
        "S1_B": {"curso_num": 1, "semester": 1, "keywords": ["bbb"]},
    }


def _matches(course, subject, cfg):
    course = (course or "").lower()
    return any(str(kw).lower() in course for kw in cfg.get("keywords", []))


def _grid_sem():
    # Grille (titulación 'GITI', année 1, semestre 1) : trois créneaux magistraux
    #   (0,1) = cours "AAA"   -> matière propre de S1_A
    #   (0,2) = cours "BBB"   -> matière propre de S1_B
    #   (0,3) = cours "OTHER" -> aucune matière de lab
    return {("GITI", 1, 1): {(0, 1): "AAA course",
                             (0, 2): "BBB course",
                             (0, 3): "OTHER course"}}


def _student_subject_slots():
    return defaultdict(lambda: defaultdict(set))


# --- Tests build_magistral_busy_by_sem ------------------------------------

def test_full_magistral_and_own_slots():
    """mag_full contient TOUS les créneaux ; own indexe la matière propre."""
    student_program = {100: "GITI"}
    subject_students = {"S1_A": [100], "S1_B": [100]}
    mag, own, stats = mb.build_magistral_busy_by_sem(
        student_program, subject_students, _lab_config(),
        grid_sem=_grid_sem(), matches_subject=_matches,
    )
    assert mag[1][100] == {(0, 1), (0, 2), (0, 3)}
    assert own[100]["S1_A"] == {(0, 1)}
    assert own[100]["S1_B"] == {(0, 2)}


def test_other_subject_slot_is_forbidden():
    """Le créneau (0,3) 'OTHER' (aucune matière de lab) est toujours interdit."""
    mag, own, _ = mb.build_magistral_busy_by_sem(
        {100: "GITI"}, {"S1_A": [100]}, _lab_config(),
        grid_sem=_grid_sem(), matches_subject=_matches,
    )
    assert (0, 3) in mag[1][100]
    # (0,3) n'est la matière propre d'aucun lab de l'étudiant.
    assert (0, 3) not in own[100].get("S1_A", set())


# --- Test propriété MATIÈRE-CONSCIENTE via _SemesterAwareLabBusy ----------

def test_subject_aware_view_forbids_other_subject_own_magistral():
    """Cœur de la correction : quand on place S1_A, le magistral PROPRE de S1_B
    (créneau (0,2)) doit RESTER interdit — sinon un lab de A pourrait écraser le
    cours magistral de B suivi par le même étudiant (la fuite historique)."""
    import pipeline as P

    student_subject_slots = _student_subject_slots()
    mag_full, own_by_sem_subject, _ = mb.apply_magistral_by_sem(
        student_subject_slots,
        {100: "GITI"},
        {"S1_A": [100], "S1_B": [100]},
        _lab_config(),
        grid_sem=_grid_sem(),
        matches_subject=_matches,
        verbose=False,
    )

    # Pas de groupe partagé ici : chaque matière n'autorise QUE son propre créneau.
    shared_map = {"S1_A": ["S1_A"], "S1_B": ["S1_B"]}
    real = defaultdict(set)
    view = P._SemesterAwareLabBusy(real, mag_full, own_by_sem_subject, shared_map)
    view.set_semester(1)

    # Placement de S1_A : interdits = tous les magistraux SAUF le propre de A.
    view.set_subject("S1_A")
    forbidden_A = view.get(100)
    assert (0, 1) not in forbidden_A          # propre de A -> autorisé
    assert (0, 2) in forbidden_A              # propre de B -> INTERDIT (anti-fuite)
    assert (0, 3) in forbidden_A              # autre cours -> interdit

    # Placement de S1_B : symétrique.
    view.set_subject("S1_B")
    forbidden_B = view.get(100)
    assert (0, 2) not in forbidden_B          # propre de B -> autorisé
    assert (0, 1) in forbidden_B              # propre de A -> INTERDIT
    assert (0, 3) in forbidden_B


def test_shared_group_own_exception_is_union():
    """Pour un groupe partagé, l'exception « matière propre » couvre TOUS les
    partenaires du groupe (ex. Física ↔ Química), sans quoi ces placements
    légitimes seraient sur-bloqués."""
    import pipeline as P

    mag_full = {1: {100: {(0, 1), (0, 2), (0, 3)}}}
    own_by_sem_subject = {1: {100: {"S1_A": {(0, 1)}, "S1_B": {(0, 2)}}}}
    # S1_A et S1_B partagent le même groupe -> l'exception est l'union.
    shared_map = {"S1_A": ["S1_A", "S1_B"], "S1_B": ["S1_A", "S1_B"]}
    view = P._SemesterAwareLabBusy(defaultdict(set), mag_full,
                                   own_by_sem_subject, shared_map)
    view.set_semester(1)
    view.set_subject("S1_A")
    forbidden = view.get(100)
    assert (0, 1) not in forbidden            # propre de A
    assert (0, 2) not in forbidden            # propre du partenaire B (autorisé)
    assert (0, 3) in forbidden                # autre cours -> interdit


def test_real_hard_block_is_never_relaxed():
    """Le canal DUR réel (autre lab au même créneau) n'est jamais neutralisé
    par l'exception magistrale : .get() renvoie toujours l'union avec le réel."""
    import pipeline as P

    real = defaultdict(set)
    real[100].add((4, 6))                     # l'étudiant a déjà un lab en (4,6)
    mag_full = {1: {100: {(0, 1)}}}
    own_by_sem_subject = {1: {100: {"S1_A": {(0, 1)}}}}
    view = P._SemesterAwareLabBusy(real, mag_full, own_by_sem_subject,
                                   {"S1_A": ["S1_A"]})
    view.set_semester(1)
    view.set_subject("S1_A")
    got = view.get(100)
    assert (4, 6) in got                      # blocage dur réel préservé
    # __getitem__ renvoie le set réel mutable (pour _propagate_busy).
    assert view[100] is real[100]
