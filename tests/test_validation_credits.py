"""Tests du rapport de validation des crédits (P1.2 de la comparaison fonctionnelle).

On teste les fonctions PURES de `validation_credits` (sans Excel ni planning réel) :
  - `_strip_prefix`         : alignement des libellés S1_/S2_ <-> source ;
  - `sessions_by_subject`   : comptage des séances/groupes par matière ;
  - `map_scheduled_to_asignacion` : mapping par mots-clés + repli nom exact ;
  - la convention « crédits × 5 = séances attendues ».

Aucune dépendance aux gros fichiers de production : la CI reste rapide.
"""

import pandas as pd

import validation_credits as vc
from lab_constants import CREDIT_TO_SESSIONS


def test_credit_to_sessions_shared_constant():
    # Même convention partagée dans tout le projet.
    assert vc.CREDIT_TO_SESSIONS == CREDIT_TO_SESSIONS == 5


def test_strip_prefix_aligns_semester_labels():
    assert vc._strip_prefix("S1_Física") == "Física"
    assert vc._strip_prefix("S2_Química") == "Química"
    # Sans préfixe : inchangé.
    assert vc._strip_prefix("Física") == "Física"


def test_sessions_by_subject_counts_sessions_and_groups():
    sched = pd.DataFrame([
        {"subject": "Física", "grupo": 1},
        {"subject": "Física", "grupo": 1},
        {"subject": "Física", "grupo": 2},
        {"subject": "Química", "grupo": 1},
    ])
    out = vc.sessions_by_subject(sched)
    # Física : 3 lignes (séances) réparties sur 2 groupes distincts.
    assert out["Física"]["sessions"] == 3
    assert out["Física"]["grupos"] == 2
    assert out["Química"]["sessions"] == 1
    assert out["Química"]["grupos"] == 1


def test_expected_sessions_follow_convention():
    # 6 crédits P -> 30 séances attendues (1 crédit = 5 séances).
    assert 6 * CREDIT_TO_SESSIONS == 30
    # 3 crédits P -> 15 séances ; 0 crédit -> 0 séance.
    assert 3 * CREDIT_TO_SESSIONS == 15
    assert 0 * CREDIT_TO_SESSIONS == 0


def test_map_scheduled_to_asignacion_uses_keywords():
    lab_config = {"S1_Física": {"keywords": ["fisica", "física"],
                                "keyword_exclude": []}}
    asig = ["Física I", "Física II", "Química General"]
    mapping = vc.map_scheduled_to_asignacion(["S1_Física"], asig, lab_config)
    # Les deux Física de la source sont rattachées à la matière planifiée.
    assert mapping["S1_Física"] == ["Física I", "Física II"]


def test_map_scheduled_to_asignacion_excludes_keywords():
    # 'keyword_exclude' doit écarter les faux positifs.
    lab_config = {"S1_Física": {"keywords": ["fisica", "física"],
                                "keyword_exclude": ["ii"]}}
    asig = ["Física I", "Física II"]
    mapping = vc.map_scheduled_to_asignacion(["S1_Física"], asig, lab_config)
    assert mapping["S1_Física"] == ["Física I"]


def test_map_scheduled_to_asignacion_exact_name_fallback():
    # Sans LAB_CONFIG, repli sur la correspondance EXACTE du nom dépouillé.
    mapping = vc.map_scheduled_to_asignacion(
        ["Química General"], ["Química General", "Física I"], {})
    assert mapping["Química General"] == ["Química General"]


def test_map_scheduled_no_match_returns_empty_list():
    # Matière planifiée sans correspondance -> liste vide (signalée, non bloquante).
    mapping = vc.map_scheduled_to_asignacion(
        ["MatièreInconnueXYZ"], ["Física I", "Química General"], {})
    assert mapping["MatièreInconnueXYZ"] == []
