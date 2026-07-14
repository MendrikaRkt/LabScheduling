# -*- coding: utf-8 -*-
"""
Tests pour ui_validation.py — validation préventive des paramètres de
configuration AVANT lancement du solveur.

Ces tests valident que le module (pur, sans Streamlit) :
- accepte une configuration saine (aucune erreur, aucun avertissement) ;
- détecte les combinaisons bloquantes de paramètres globaux
  (min > max, semaine de départ hors semestre, taille préférée > max) ;
- détecte les surcharges de matière invalides (fenêtre trop courte,
  min > max, aucune salle, aucune séance) ;
- émet des avertissements non bloquants (seuil métier, capacité extrême,
  incohérence année → période) ;
- agrège correctement via validate_all et calcule le verdict is_blocking.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui_validation as v  # noqa: E402


# ---------------------------------------------------------------------------
# Fabriques d'objets de configuration
# ---------------------------------------------------------------------------

def _valid_global():
    return {
        "min_size": 7,
        "preferred_size": 12,
        "default_max": 15,
        "computer_lab_max": 24,
        "reduced_max_size": 12,
        "start_week": 4,
        "s1_total_weeks": 14,
        "s2_total_weeks": 20,
    }


def _valid_override():
    return {
        "num_sessions": 5,
        "max_students": 15,
        "min_size": 7,
        "min_week": 4,
        "max_week": 12,
        "lab_rooms": ["Electrónica"],
        "keywords": ["fisica"],
        "schedule_pref": "morning",
        "curso_num": 1,
    }


def _codes(issues):
    return {i.code for i in issues}


# ---------------------------------------------------------------------------
# Paramètres globaux — cas sains
# ---------------------------------------------------------------------------

def test_global_valid_has_no_issue():
    assert v.validate_global_params(_valid_global()) == []


def test_global_defaults_are_valid_on_empty_dict():
    # Les valeurs par défaut internes doivent produire une config saine.
    assert v.validate_global_params({}) == []


# ---------------------------------------------------------------------------
# Paramètres globaux — erreurs bloquantes
# ---------------------------------------------------------------------------

def test_global_min_greater_than_max_is_blocking_error():
    cfg = _valid_global()
    cfg["min_size"] = 20
    issues = v.validate_global_params(cfg)
    codes = _codes(issues)
    assert "G_MIN_GT_MAX" in codes
    err = next(i for i in issues if i.code == "G_MIN_GT_MAX")
    assert err.level == v.LEVEL_ERROR
    assert err.is_blocking is True
    assert err.hint  # une indication de valeurs acceptables est fournie


def test_global_preferred_greater_than_max_is_error():
    cfg = _valid_global()
    cfg["preferred_size"] = 18
    issues = v.validate_global_params(cfg)
    assert "G_PREF_GT_MAX" in _codes(issues)


def test_global_start_week_beyond_s1_is_error():
    cfg = _valid_global()
    cfg["start_week"] = 15  # >= s1_total_weeks (14)
    issues = v.validate_global_params(cfg)
    codes = _codes(issues)
    assert "G_START_WEEK_GE_S1" in codes
    assert any(i.level == v.LEVEL_ERROR for i in issues)


def test_global_start_week_below_one_is_error():
    cfg = _valid_global()
    cfg["start_week"] = 0
    assert "G_START_WEEK_LT_1" in _codes(v.validate_global_params(cfg))


# ---------------------------------------------------------------------------
# Paramètres globaux — avertissements non bloquants
# ---------------------------------------------------------------------------

def test_global_min_below_policy_is_warning_only():
    cfg = _valid_global()
    cfg["min_size"] = 3  # sous le seuil métier (7) mais <= max
    issues = v.validate_global_params(cfg)
    warn = next(i for i in issues if i.code == "G_MIN_BELOW_POLICY")
    assert warn.level == v.LEVEL_WARNING
    assert warn.is_blocking is False


def test_global_computer_max_below_standard_is_warning():
    cfg = _valid_global()
    cfg["computer_lab_max"] = 10
    assert "G_COMPUTER_LT_MAX" in _codes(v.validate_global_params(cfg))


def test_global_s2_shorter_than_s1_is_warning():
    cfg = _valid_global()
    cfg["s2_total_weeks"] = 12
    assert "G_S2_LT_S1" in _codes(v.validate_global_params(cfg))


# ---------------------------------------------------------------------------
# Surcharges par matière
# ---------------------------------------------------------------------------

def test_subject_valid_has_no_issue():
    assert v.validate_subject_override("Fisica", _valid_override()) == []


def test_subject_window_too_small_is_error():
    ov = _valid_override()
    ov["min_week"], ov["max_week"], ov["num_sessions"] = 4, 6, 5  # 3 < 5
    issues = v.validate_subject_override("Fisica", ov)
    err = next(i for i in issues if i.code == "S_WINDOW_TOO_SMALL")
    assert err.level == v.LEVEL_ERROR
    assert err.scope == "Fisica"


def test_subject_window_exact_is_warning():
    ov = _valid_override()
    ov["min_week"], ov["max_week"], ov["num_sessions"] = 4, 8, 5  # 5 == 5
    codes = _codes(v.validate_subject_override("Fisica", ov))
    assert "S_WINDOW_TIGHT" in codes


def test_subject_min_greater_than_max_is_error():
    ov = _valid_override()
    ov["min_size"], ov["max_students"] = 10, 6
    issues = v.validate_subject_override("Quimica", ov)
    assert "S_MIN_GT_MAX" in _codes(issues)


def test_subject_no_room_is_error():
    ov = _valid_override()
    ov["lab_rooms"] = []
    err = next(i for i in v.validate_subject_override("Fisica", ov)
              if i.code == "S_NO_ROOM")
    assert err.level == v.LEVEL_ERROR


def test_subject_no_session_is_error():
    ov = _valid_override()
    ov["num_sessions"] = 0
    assert "S_NO_SESSION" in _codes(v.validate_subject_override("Fisica", ov))


def test_subject_no_keyword_is_warning():
    ov = _valid_override()
    ov["keywords"] = []
    issues = v.validate_subject_override("Fisica", ov)
    warn = next(i for i in issues if i.code == "S_NO_KEYWORD")
    assert warn.level == v.LEVEL_WARNING


def test_subject_period_mismatch_is_warning_when_not_allowed():
    ov = _valid_override()
    ov["schedule_pref"] = "afternoon"  # année 1 attend le matin
    issues = v.validate_subject_override(
        "Fisica", ov, curso_num=1, year_prefs={}
    )
    assert "S_PERIOD_MISMATCH" in _codes(issues)


def test_subject_period_mismatch_suppressed_when_allowed():
    ov = _valid_override()
    ov["schedule_pref"] = "afternoon"
    issues = v.validate_subject_override(
        "Fisica", ov, curso_num=1,
        year_prefs={"allow_afternoon_y1y3": True},
    )
    assert "S_PERIOD_MISMATCH" not in _codes(issues)


# ---------------------------------------------------------------------------
# Agrégation validate_all + ValidationReport
# ---------------------------------------------------------------------------

def test_validate_all_clean_config_not_blocking():
    cfg = dict(_valid_global())
    cfg["subject_overrides"] = {"Fisica": _valid_override()}
    report = v.validate_all(cfg)
    assert report.is_blocking is False
    assert report.is_clean is True
    assert report.summary()["errors"] == 0


def test_validate_all_collects_global_and_subject_errors():
    cfg = dict(_valid_global())
    cfg["min_size"] = 30  # erreur globale
    bad = _valid_override()
    bad["lab_rooms"] = []  # erreur matière
    cfg["subject_overrides"] = {"Fisica": bad}
    report = v.validate_all(cfg)
    assert report.is_blocking is True
    codes = _codes(report.issues)
    assert "G_MIN_GT_MAX" in codes
    assert "S_NO_ROOM" in codes


def test_validate_all_handles_non_dict_gracefully():
    assert v.validate_all(None).issues == []
    assert v.validate_all("nope").issues == []


def test_validate_all_ignores_malformed_override_entries():
    cfg = dict(_valid_global())
    cfg["subject_overrides"] = {"Bad": "not-a-dict", "Ok": _valid_override()}
    report = v.validate_all(cfg)
    assert report.is_blocking is False


def test_report_sorted_issues_orders_errors_first():
    cfg = dict(_valid_global())
    cfg["min_size"] = 30            # erreur
    cfg["computer_lab_max"] = 5     # avertissement
    report = v.validate_all(cfg)
    ordered = report.sorted_issues()
    assert ordered[0].level == v.LEVEL_ERROR


def test_summary_counts_are_consistent():
    cfg = dict(_valid_global())
    cfg["min_size"] = 30
    cfg["computer_lab_max"] = 5
    report = v.validate_all(cfg)
    s = report.summary()
    assert s["total"] == s["errors"] + s["warnings"] + s["infos"]
