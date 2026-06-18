"""Tests de cohérence des constantes du problème (Étape 6.1 / 6.3).

Garde-fou contre une dérive silencieuse des paramètres documentés dans
docs/PROBLEM_FORMULATION.md.
"""

import pipeline


def test_group_size_bounds_are_coherent():
    assert pipeline.MIN_GROUP_SIZE <= pipeline.PREFERRED_GROUP_SIZE
    assert pipeline.PREFERRED_GROUP_SIZE <= pipeline.MAX_GROUP_SIZE
    assert pipeline.MIN_GROUP_SIZE >= 1


def test_reproducibility_constants_present():
    assert isinstance(pipeline.RANDOM_SEED, int)
    assert 0.0 <= pipeline.SOLVER_RELATIVE_GAP < 1.0
    assert pipeline.SOLVER_TIME_LIMIT > 0


def test_semester_weeks_positive():
    assert pipeline.SEMESTER_1_WEEKS > 0
    assert pipeline.SEMESTER_2_WEEKS > 0


def test_friday_soft_cap_is_soft_not_zero():
    # Le plafond du vendredi est SOUPLE : il doit exister et être > 0.
    assert pipeline.FRIDAY_SOFT_CAP > 0


def test_days_contain_viernes():
    # Le suivi du goulot du vendredi dépend de la présence de 'Viernes'.
    assert "Viernes" in pipeline.DAYS
