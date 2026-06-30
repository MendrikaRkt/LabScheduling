"""Tests de la charge labo des professeurs (P1.2 de la comparaison fonctionnelle).

On vérifie la convention métier « 1 crédit P = 5 séances » et le comportement
« signaler, ne pas bloquer » de la validation budgétaire : un dépassement est
marqué (over_budget=True) mais la ligne reste présente — le système ne ré-affecte
ni ne supprime rien.

On teste la fonction PURE `professor_lab_load(assign_df, budgets_df)` avec des
DataFrames synthétiques : aucune dépendance au gros fichier Excel de production,
pour que la CI reste rapide et reproductible.
"""

import pandas as pd

import professor_credits as pc
from lab_constants import CREDIT_TO_SESSIONS


def _assign_df():
    """Affectation en forme longue : (prof_code, credits, char)."""
    return pd.DataFrame([
        {"prof_code": "AAA", "credits": 3.0, "char": "P"},   # 3 P -> 15 séances
        {"prof_code": "AAA", "credits": 2.0, "char": "T"},   # théorie : 0 séance labo
        {"prof_code": "BBB", "credits": 1.0, "char": "P"},   # 1 P -> 5 séances
    ])


def _budgets_df():
    """Crosswalk code -> (nom, budget). BBB n'a volontairement PAS de budget."""
    return pd.DataFrame([
        {"prof_code": "AAA", "prof_name": "Alice", "budget": 4.0,
         "src_total_credits": 5.0},
    ])


def test_credit_to_sessions_convention_is_five():
    # La convention validée par le coordinateur ne doit pas dériver.
    assert CREDIT_TO_SESSIONS == 5
    # Le module réexporte bien la constante centralisée (même valeur).
    assert pc.CREDIT_TO_SESSIONS == 5


def test_lab_sessions_equal_p_credits_times_five():
    load = pc.professor_lab_load(_assign_df(), _budgets_df(), default_budget=None)
    aaa = load[load.prof_code == "AAA"].iloc[0]
    bbb = load[load.prof_code == "BBB"].iloc[0]
    # 3 crédits P  -> 15 séances ; 1 crédit P -> 5 séances.
    assert aaa["lab_credits"] == 3.0
    assert aaa["lab_sessions"] == 3.0 * CREDIT_TO_SESSIONS == 15.0
    assert bbb["lab_sessions"] == 1.0 * CREDIT_TO_SESSIONS == 5.0


def test_theory_credits_excluded_from_lab_sessions():
    load = pc.professor_lab_load(_assign_df(), _budgets_df(), default_budget=None)
    aaa = load[load.prof_code == "AAA"].iloc[0]
    # Les 2 crédits T comptent dans la théorie et le total, jamais en séances labo.
    assert aaa["theory_credits"] == 2.0
    assert aaa["total_assigned"] == 5.0          # 3 P + 2 T
    assert aaa["lab_sessions"] == 15.0           # inchangé par la théorie


def test_over_budget_is_signalled_not_blocked():
    load = pc.professor_lab_load(_assign_df(), _budgets_df(), default_budget=None)
    aaa = load[load.prof_code == "AAA"].iloc[0]
    # total 5 cr > budget 4 -> dépassement SIGNALÉ...
    assert bool(aaa["over_budget"]) is True
    assert aaa["margin"] == 4.0 - 5.0            # marge négative
    # ...mais la ligne reste présente : on ne bloque ni ne ré-affecte rien.
    assert "AAA" in set(load["prof_code"])


def test_missing_budget_yields_absent_source_and_no_false_overflow():
    load = pc.professor_lab_load(_assign_df(), _budgets_df(), default_budget=None)
    bbb = load[load.prof_code == "BBB"].iloc[0]
    # Budget inconnu -> source "absent", pas de jugement de dépassement (NaN -> False).
    assert bbb["budget_source"] == "absent"
    assert pd.isna(bbb["budget"])
    assert bool(bbb["over_budget"]) is False
    # Le nom retombe sur le code quand le crosswalk ne le connaît pas.
    assert bbb["prof_name"] == "BBB"


def test_default_budget_fills_missing_and_marks_source():
    load = pc.professor_lab_load(_assign_df(), _budgets_df(), default_budget=10.0)
    bbb = load[load.prof_code == "BBB"].iloc[0]
    assert bbb["budget"] == 10.0
    assert bbb["budget_source"] == "défaut"
    # 1 cr total <= 10 -> pas de dépassement.
    assert bool(bbb["over_budget"]) is False
