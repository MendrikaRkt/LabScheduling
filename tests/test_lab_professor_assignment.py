"""Tests de l'affectation des professeurs aux groupes (P0.1 / P1.2).

Couvre :
  - les briques pures `_allocate_groups` (plus fort reste) et `effective_p_credits`
    (crédits P effectifs sommant au budget) ;
  - la canonicalisation des libellés (`canonical_subject_key`, `_strip_semester_prefix`) ;
  - `assign_schedule_groups` : répartition proportionnelle des groupes RÉELLEMENT
    planifiés, au prorata des crédits P (via le cache committé, fp=None) ;
  - `assign_professors_to_schedule_df` : le NOUVEAU point d'entrée « niveau planning »
    de la recommandation P0.1 (persistance d'un professeur par séance), y compris son
    comportement « signaler, ne pas décider » (chaîne vide quand l'affectation est
    indéterminée, jamais d'exception métier).

Les tests s'appuient sur le cache committé `data_clean/optimizarion/
lab_professor_weights.json` : aucune dépendance au gros Excel de production,
la CI reste rapide et reproductible.
"""

import pandas as pd

import lab_professor_assignment as lpa
from lab_constants import CREDIT_TO_SESSIONS, SESSIONS_PER_GROUP


# --------------------------------------------------------------------------- #
# Constantes & canonicalisation
# --------------------------------------------------------------------------- #
def test_constants_centralised():
    assert CREDIT_TO_SESSIONS == 5
    assert SESSIONS_PER_GROUP == 5
    assert lpa.CREDIT_TO_SESSIONS == 5
    assert lpa.SESSIONS_PER_GROUP == 5


def test_strip_semester_prefix():
    assert lpa._strip_semester_prefix("S1_Física") == "Física"
    assert lpa._strip_semester_prefix("S2_Química") == "Química"
    assert lpa._strip_semester_prefix("Física") == "Física"


def test_canonical_subject_key_aligns_aliases_and_prefixes():
    # « Física » (libellé court) et « S1_Física » (préfixe semestre) désignent la
    # même clé canonique que la source (« Física I »).
    assert lpa.canonical_subject_key("Física") == "fisica i"
    assert lpa.canonical_subject_key(
        lpa._strip_semester_prefix("S1_Física")) == "fisica i"


# --------------------------------------------------------------------------- #
# _allocate_groups : plus fort reste
# --------------------------------------------------------------------------- #
def test_allocate_groups_exact_integer_weights():
    # Poids entiers sommant à n_groups -> chacun reçoit exactement son poids.
    assert lpa._allocate_groups([2, 1, 1], 4) == [2, 1, 1]


def test_allocate_groups_largest_remainder_preserves_total():
    alloc = lpa._allocate_groups([5, 3, 3, 2, 2], 6)
    # La somme des groupes alloués égale TOUJOURS n_groups.
    assert sum(alloc) == 6
    # Le plus gros poids reçoit le plus de groupes.
    assert alloc[0] == max(alloc)


def test_allocate_groups_zero_weight_or_zero_groups():
    assert lpa._allocate_groups([0, 0, 0], 5) == [0, 0, 0]
    assert lpa._allocate_groups([1, 2], 0) == [0, 0]


# --------------------------------------------------------------------------- #
# effective_p_credits : crédits P effectifs sommant au budget
# --------------------------------------------------------------------------- #
def test_effective_p_credits_pure_blocks_sum_to_budget():
    rows = [{"char": "P", "credits_block": 3.0},
            {"char": "P", "credits_block": 2.0}]
    eff = lpa.effective_p_credits(rows, 5.0)
    assert eff == [3.0, 2.0]
    assert abs(sum(eff) - 5.0) < 1e-9


def test_effective_p_credits_overassignment_scaled_down():
    # Σ P purs = 5 mais budget = 4 -> réduction au prorata pour sommer à 4.
    rows = [{"char": "P", "credits_block": 3.0},
            {"char": "P", "credits_block": 2.0}]
    eff = lpa.effective_p_credits(rows, 4.0)
    assert abs(sum(eff) - 4.0) < 1e-9
    assert eff[0] > eff[1]   # proportions conservées


def test_effective_p_credits_tp_receives_residual():
    # 1 bloc P pur (2) + 1 bloc TP (4) avec budget 5 -> résidu 3 au bloc TP.
    rows = [{"char": "P", "credits_block": 2.0},
            {"char": "TP", "credits_block": 4.0}]
    eff = lpa.effective_p_credits(rows, 5.0)
    assert eff == [2.0, 3.0]
    assert abs(sum(eff) - 5.0) < 1e-9


# --------------------------------------------------------------------------- #
# assign_schedule_groups : répartition proportionnelle (cache committé)
# --------------------------------------------------------------------------- #
def test_assign_schedule_groups_fisica_proportional():
    # Física : poids P [5,3,3,2,2] (Σ=15). Pour 6 groupes planifiés, le plus fort
    # reste donne 2 groupes au prof majoritaire, 1 aux quatre autres.
    gmap = lpa.assign_schedule_groups(None, {"fisica i": [1, 2, 3, 4, 5, 6]})
    assert len(gmap) == 6
    counts = {}
    for prof in gmap.values():
        counts[prof] = counts.get(prof, 0) + 1
    assert sum(counts.values()) == 6
    assert max(counts.values()) == 2          # le prof majoritaire (Patricio)
    assert sorted(counts.values()) == [1, 1, 1, 1, 2]


# --------------------------------------------------------------------------- #
# assign_professors_to_schedule_df : NOUVEAU point d'entrée P0.1
# --------------------------------------------------------------------------- #
def _fisica_schedule(n_groups=6, sessions_per_group=SESSIONS_PER_GROUP):
    """Planning synthétique Física : n_groups × 5 séances (préfixe S1_)."""
    rows = []
    for grp in range(1, n_groups + 1):
        for s in range(1, sessions_per_group + 1):
            rows.append({"subject": "S1_Física", "grupo": grp, "session": s})
    return pd.DataFrame(rows)


def test_assign_professors_to_schedule_df_fisica_all_assigned():
    df = _fisica_schedule(n_groups=6)        # 6 groupes × 5 = 30 séances
    profs = lpa.assign_professors_to_schedule_df(df, fp=None)
    # Une valeur par ligne, dans le même ordre.
    assert len(profs) == len(df) == 30
    # Toutes les séances sont affectées (aucune chaîne vide).
    assert all(p for p in profs)
    df = df.assign(professor=profs)
    # 5 professeurs distincts, le majoritaire couvre 2 groupes = 10 séances.
    by_prof = df.groupby("professor").size()
    assert by_prof.nunique() <= 2            # soit 5 séances, soit 10
    assert by_prof.max() == 2 * SESSIONS_PER_GROUP   # 10 séances
    assert by_prof.sum() == 30


def test_assign_professors_to_schedule_df_consistent_with_group_map():
    # Le professeur par séance doit coïncider avec l'affectation par groupe.
    df = _fisica_schedule(n_groups=6)
    profs = lpa.assign_professors_to_schedule_df(df, fp=None)
    df = df.assign(professor=profs)
    gmap = lpa.assign_schedule_groups(None, {"fisica i": [1, 2, 3, 4, 5, 6]})
    for _, row in df.iterrows():
        assert row["professor"] == gmap[("fisica i", row["grupo"])]


def test_assign_professors_empty_df_returns_empty_list():
    assert lpa.assign_professors_to_schedule_df(pd.DataFrame(), fp=None) == []
    assert lpa.assign_professors_to_schedule_df(None, fp=None) == []


def test_assign_professors_missing_columns_signals_blank():
    # Colonnes attendues absentes -> une chaîne vide par ligne (signalé, non bloquant).
    df = pd.DataFrame([{"foo": 1}, {"foo": 2}])
    assert lpa.assign_professors_to_schedule_df(df, fp=None) == ["", ""]


def test_assign_professors_unknown_subject_signals_blank_not_raises():
    # Matière hors source : chaîne vide, JAMAIS d'exception (« signaler, ne pas décider »).
    df = pd.DataFrame([{"subject": "S1_MatièreInconnueXYZ", "grupo": 1,
                        "session": 1}])
    out = lpa.assign_professors_to_schedule_df(df, fp=None)
    assert out == [""]
