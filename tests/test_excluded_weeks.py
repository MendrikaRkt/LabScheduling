"""Tests unitaires pour la fonctionnalité « semaines exclues » (TASK 3).

Vérifie ``pipeline.excluded_weeks_for`` : union des semaines exclues globales
et des semaines exclues par matière (cas d'usage : Chimie 1re/S1 exclut les
semaines 7, 8, 11, 12).
"""

import pipeline


def _reset():
    pipeline.EXCLUDED_WEEKS_ALL = []
    pipeline.LAB_CONFIG.clear()


def test_no_exclusions_returns_empty():
    _reset()
    assert pipeline.excluded_weeks_for("S1_Física") == set()


def test_per_subject_excluded_weeks():
    _reset()
    pipeline.LAB_CONFIG["S1_Química"] = {"excluded_weeks": [7, 8, 11, 12]}
    assert pipeline.excluded_weeks_for("S1_Química") == {7, 8, 11, 12}
    # Une autre matière n'est pas affectée.
    assert pipeline.excluded_weeks_for("S1_Física") == set()


def test_global_excluded_weeks_apply_to_all():
    _reset()
    pipeline.EXCLUDED_WEEKS_ALL = [1, 2]
    assert pipeline.excluded_weeks_for("S1_Física") == {1, 2}
    assert pipeline.excluded_weeks_for("S2_Biología") == {1, 2}


def test_global_and_per_subject_union():
    _reset()
    pipeline.EXCLUDED_WEEKS_ALL = [1, 2]
    pipeline.LAB_CONFIG["S1_Química"] = {"excluded_weeks": [7, 8]}
    assert pipeline.excluded_weeks_for("S1_Química") == {1, 2, 7, 8}


def test_malformed_values_ignored():
    _reset()
    pipeline.EXCLUDED_WEEKS_ALL = ["oops", None]
    pipeline.LAB_CONFIG["S1_X"] = {"excluded_weeks": ["bad"]}
    # Ne doit pas lever ; renvoie un set (vide ici car tout est invalide).
    assert isinstance(pipeline.excluded_weeks_for("S1_X"), set)


def teardown_module(module):
    _reset()
