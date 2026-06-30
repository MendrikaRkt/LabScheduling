"""Tests de la re-vérification des contraintes post-solveur (P2.2).

Le solveur garantit C1 (pas deux groupes d'une même matière au même créneau),
C4 (pas deux groupes dans une même salle au même créneau) et C5 (séances d'un
groupe en ordre chronologique strict). On RE-VÉRIFIE C1/C4/C5 a posteriori,
symétriquement, dans `detect_conflicts`. Ces tests verrouillent en particulier
la détection C5 réintroduite par la recommandation P2.2.
"""

import pandas as pd

import reliability_metrics as rm


def _row(subject, grupo, session, week, day="Lunes", block="08:30",
         room="Lab A", semester=1):
    return {"subject": subject, "semester": semester, "grupo": grupo,
            "session": session, "week": week, "day": day,
            "time_block": block, "lab_rooms": room}


def test_detect_conflicts_empty_returns_all_keys():
    out = rm.detect_conflicts(pd.DataFrame(), pd.DataFrame())
    for k in ("c1_violations", "c4_violations", "c5_violations",
              "student_conflicts", "examples_c1", "examples_c4", "examples_c5"):
        assert k in out
    assert out["c5_violations"] == 0


def test_c5_conformant_schedule_has_no_violation():
    # Séances 1<2<3 en semaines strictement croissantes -> aucune violation.
    df = pd.DataFrame([
        _row("Física", 1, 1, 2),
        _row("Física", 1, 2, 5, day="Martes"),
        _row("Física", 1, 3, 9, block="10:30"),
    ])
    out = rm.detect_conflicts(df, pd.DataFrame())
    assert out["c5_violations"] == 0
    assert out["c1_violations"] == 0
    assert out["c4_violations"] == 0


def test_c5_out_of_order_is_flagged_with_example():
    # Séance 2 placée AVANT la séance 1 (semaine 3 < 8) -> violation C5.
    df = pd.DataFrame([
        _row("Química", 1, 1, 8, room="Lab B"),
        _row("Química", 1, 2, 3, room="Lab B", day="Martes"),
    ])
    out = rm.detect_conflicts(df, pd.DataFrame())
    assert out["c5_violations"] == 1
    assert len(out["examples_c5"]) == 1
    ex = out["examples_c5"][0]
    assert ex["subject"] == "Química"
    assert ex["grupo"] == 1
    assert ex["sessions"] == [1, 2]
    assert ex["weeks"] == [8, 3]


def test_c5_equal_weeks_is_a_violation():
    # Ordre NON strict (deux séances la même semaine) -> violation.
    df = pd.DataFrame([
        _row("Física", 2, 1, 4),
        _row("Física", 2, 2, 4, day="Jueves"),
    ])
    out = rm.detect_conflicts(df, pd.DataFrame())
    assert out["c5_violations"] == 1


def test_c5_single_session_group_is_not_a_violation():
    # Un groupe à une seule séance ne peut pas être « désordonné ».
    df = pd.DataFrame([_row("Física", 1, 1, 5)])
    out = rm.detect_conflicts(df, pd.DataFrame())
    assert out["c5_violations"] == 0


def test_c5_penalised_in_health_score():
    # Une violation C5 doit dégrader le score de santé global. Les conflits sont
    # imbriqués sous la clé 'conflicts' (forme renvoyée par compute_all_metrics).
    base = rm.compute_health_score(
        {"conflicts": {"c1_violations": 0, "c4_violations": 0,
                       "c5_violations": 0, "student_conflicts": 0}})
    with_c5 = rm.compute_health_score(
        {"conflicts": {"c1_violations": 0, "c4_violations": 0,
                       "c5_violations": 1, "student_conflicts": 0}})
    base_score, c5_score = base[0], with_c5[0]
    assert c5_score < base_score
    # Le pénalité C5 est de -50 points (au même rang que C1/C4).
    assert base_score - c5_score == 50
    # Le motif C5 doit apparaître dans la liste des problèmes signalés.
    assert any("C5" in issue for issue in with_c5[2])
