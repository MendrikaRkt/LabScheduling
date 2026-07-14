"""
Tests pour diagnostics.py — audit d'anomalies métier + moteur de remèdes.

Ces tests valident que le module détecte correctement les anomalies FAISABLES-
MAIS-INCORRECTES (groupes minuscules, séances hors-période), propose un remède
chiffré pour chaque famille d'anomalie, et agrège correctement par
niveau × semestre. Module pur : aucun effet de bord, aucune dépendance
Streamlit.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import diagnostics as dg  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers de fabrication de lignes de planning
# ---------------------------------------------------------------------------

def _row(semester="S1", subject="Bioquimica", grupo="G1", curso_num=1,
         nb_students=12, time_block="08:30-10:30"):
    return {
        "semester": semester, "subject": subject, "grupo": grupo,
        "curso_num": curso_num, "nb_students": nb_students,
        "time_block": time_block, "session": 1, "week": 1, "day": "Lunes",
    }


# ---------------------------------------------------------------------------
# _period_of
# ---------------------------------------------------------------------------

def test_period_of_morning():
    assert dg._period_of("08:30-10:30") == "morning"
    assert dg._period_of("10:30-12:30") == "morning"


def test_period_of_afternoon():
    assert dg._period_of("15:00-17:00") == "afternoon"
    assert dg._period_of("19:00-21:00") == "afternoon"


def test_period_of_unknown():
    assert dg._period_of("99:99-99:99") is None
    assert dg._period_of("") is None


# ---------------------------------------------------------------------------
# _dedup_groups
# ---------------------------------------------------------------------------

def test_dedup_collapses_sessions_into_one_group():
    rows = [
        _row(grupo="G1", time_block="08:30-10:30"),
        _row(grupo="G1", time_block="10:30-12:30"),
        _row(grupo="G1", time_block="08:30-10:30"),
    ]
    groups = dg._dedup_groups(rows)
    assert len(groups) == 1
    g = groups[0]
    assert g["n_sessions"] == 3
    assert g["time_blocks"] == {"08:30-10:30", "10:30-12:30"}
    assert g["periods"] == {"morning"}


def test_dedup_keeps_distinct_groups():
    rows = [_row(grupo="G1"), _row(grupo="G2"), _row(subject="Fisica", grupo="G1")]
    groups = dg._dedup_groups(rows)
    assert len(groups) == 3


# ---------------------------------------------------------------------------
# detect_tiny_groups
# ---------------------------------------------------------------------------

def test_tiny_group_detected_below_min():
    rows = [_row(nb_students=3)]
    groups = dg._dedup_groups(rows)
    anomalies = dg.detect_tiny_groups(groups, min_group_size=7)
    assert len(anomalies) == 1
    assert anomalies[0]["type"] == "tiny_group"
    assert anomalies[0]["severity"] == dg.SEV_WARNING


def test_solo_group_is_critical():
    rows = [_row(nb_students=1)]
    groups = dg._dedup_groups(rows)
    anomalies = dg.detect_tiny_groups(groups, min_group_size=7)
    assert len(anomalies) == 1
    assert anomalies[0]["severity"] == dg.SEV_CRITICAL
    assert "SOLO" in anomalies[0]["detail"]


def test_healthy_group_not_flagged():
    rows = [_row(nb_students=12)]
    groups = dg._dedup_groups(rows)
    assert dg.detect_tiny_groups(groups, min_group_size=7) == []


def test_zero_students_ignored():
    rows = [_row(nb_students=0)]
    groups = dg._dedup_groups(rows)
    assert dg.detect_tiny_groups(groups, min_group_size=7) == []


# ---------------------------------------------------------------------------
# detect_wrong_period
# ---------------------------------------------------------------------------

def test_year1_afternoon_is_wrong():
    rows = [_row(curso_num=1, time_block="15:00-17:00")]
    groups = dg._dedup_groups(rows)
    anomalies = dg.detect_wrong_period(groups)
    assert len(anomalies) == 1
    assert anomalies[0]["type"] == "wrong_period"
    assert anomalies[0]["expected_period"] == "matin"
    assert anomalies[0]["severity"] == dg.SEV_CRITICAL


def test_year2_morning_is_wrong():
    rows = [_row(curso_num=2, time_block="08:30-10:30")]
    groups = dg._dedup_groups(rows)
    anomalies = dg.detect_wrong_period(groups)
    assert len(anomalies) == 1
    assert anomalies[0]["expected_period"] == "après-midi"


def test_year1_morning_is_correct():
    rows = [_row(curso_num=1, time_block="08:30-10:30")]
    groups = dg._dedup_groups(rows)
    assert dg.detect_wrong_period(groups) == []


def test_derogation_suppresses_wrong_period():
    rows = [_row(curso_num=1, time_block="15:00-17:00")]
    groups = dg._dedup_groups(rows)
    anomalies = dg.detect_wrong_period(groups, allow_afternoon_y1y3=True)
    assert anomalies == []


# ---------------------------------------------------------------------------
# propose_remedy
# ---------------------------------------------------------------------------

def test_remedy_for_tiny_group_quantified():
    anomaly = {"type": "tiny_group", "nb_students": 3, "min_group_size": 7,
               "subject": "Bioquimica", "grupo": "G1"}
    remedy = dg.propose_remedy(anomaly)
    assert remedy["action"] == "merge_or_relax_min"
    assert remedy["param"] == 4  # 7 - 3
    assert "+4" in remedy["text"]


def test_remedy_for_wrong_period():
    anomaly = {"type": "wrong_period", "expected_period": "matin",
               "subject": "Fisica", "grupo": "G2"}
    remedy = dg.propose_remedy(anomaly)
    assert remedy["action"] == "move_to_expected_period"
    assert remedy["param"] == "matin"


def test_remedy_for_oversubscription():
    anomaly = {"type": "oversubscription", "gap": 2, "subject": "Quimica",
               "single_prof": True}
    remedy = dg.propose_remedy(anomaly)
    assert remedy["action"] == "add_professor_or_reduce_groups"
    assert "PROF UNIQUE" in remedy["text"]


def test_remedy_for_credit_overload():
    anomaly = {"type": "credit_overload", "delta": 3, "professor": "Dupont"}
    remedy = dg.propose_remedy(anomaly)
    assert remedy["action"] == "rebalance_professor_load"
    assert "+3" in remedy["text"]


def test_remedy_unknown_type():
    remedy = dg.propose_remedy({"type": "mystery"})
    assert remedy["action"] == "review"


# ---------------------------------------------------------------------------
# audit_schedule
# ---------------------------------------------------------------------------

def test_audit_healthy_schedule():
    rows = [
        _row(curso_num=1, nb_students=12, time_block="08:30-10:30"),
        _row(curso_num=2, nb_students=10, time_block="15:00-17:00", grupo="G2"),
    ]
    report = dg.audit_schedule(rows)
    assert report["healthy"] is True
    assert report["n_total"] == 0
    assert report["n_critical"] == 0


def test_audit_detects_multiple_families():
    rows = [
        _row(curso_num=1, nb_students=1, time_block="08:30-10:30", grupo="G1"),
        _row(curso_num=1, nb_students=12, time_block="15:00-17:00", grupo="G2"),
    ]
    report = dg.audit_schedule(rows)
    assert report["healthy"] is False
    assert report["n_total"] == 2
    assert "tiny_group" in report["by_type"]
    assert "wrong_period" in report["by_type"]
    # chaque anomalie porte un remède
    for a in report["anomalies"]:
        assert "remedy" in a and a["remedy"]["text"]


def test_audit_merges_extra_anomalies():
    rows = [_row(nb_students=12)]
    extra = [{"type": "oversubscription", "gap": 1, "subject": "X",
              "severity": dg.SEV_CRITICAL, "level": "Primero", "semester": "S1"}]
    report = dg.audit_schedule(rows, extra_anomalies=extra)
    assert report["n_total"] == 1
    assert report["by_type"]["oversubscription"] == 1
    assert report["anomalies"][0]["remedy"]["action"] == \
        "add_professor_or_reduce_groups"


def test_audit_aggregates_by_level_semester():
    rows = [
        _row(curso_num=1, semester="S1", nb_students=1, grupo="G1"),
        _row(curso_num=1, semester="S1", nb_students=2, grupo="G2"),
    ]
    report = dg.audit_schedule(rows)
    key = "Primero · S1"
    assert key in report["by_level_semester"]
    assert report["by_level_semester"][key]["total"] == 2


def test_audit_critical_sorted_first():
    rows = [
        _row(curso_num=3, nb_students=5, time_block="08:30-10:30", grupo="GW"),
        _row(curso_num=1, nb_students=1, time_block="08:30-10:30", grupo="GS"),
    ]
    report = dg.audit_schedule(rows)
    # le groupe solo (critique) doit précéder le petit groupe (avertissement)
    assert report["anomalies"][0]["severity"] == dg.SEV_CRITICAL
