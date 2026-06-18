"""Tests de la couche QA (Étape 6.2 / 6.3)."""

import pandas as pd
import pytest

import data_quality as dq


def test_integrity_ok_when_columns_present():
    df = pd.DataFrame({"AlumnoID": [1, 2], "actividad": ["x", "y"]})
    rep = dq.check_master_integrity(df)
    assert rep["ok"] is True
    assert rep["missing_columns"] == []
    assert rep["n_students"] == 2


def test_integrity_flags_missing_columns():
    df = pd.DataFrame({"foo": [1]})
    rep = dq.check_master_integrity(df)
    assert rep["ok"] is False
    assert "AlumnoID" in rep["missing_columns"]


def test_integrity_warns_on_null_ids():
    df = pd.DataFrame({"AlumnoID": [1, None], "actividad": ["a", "b"]})
    rep = dq.check_master_integrity(df)
    assert rep["warnings"], "un AlumnoID vide doit générer un avertissement"


def test_reconcile_grouping_detects_unplaced(synthetic_subject_students,
                                             synthetic_groups):
    rep = dq.reconcile_grouping(synthetic_subject_students, synthetic_groups)
    # Mat A a 4 inscrits (1,2,3,10) mais seul 1,2,3 sont placés -> 1 non placé
    assert rep["total_enrolled"] == 7
    assert rep["total_unplaced"] == 1
    assert rep["total_placed"] == 6
    assert 0 <= rep["global_placement_pct"] <= 100


def test_reconcile_grouping_all_placed():
    subj = {"X": [1, 2]}
    groups = [{"subject": "X", "student_ids": [1, 2], "nb_students": 2}]
    rep = dq.reconcile_grouping(subj, groups)
    assert rep["total_unplaced"] == 0
    assert rep["global_placement_pct"] == 100.0


def test_reconcile_join_unavailable_without_source():
    df = pd.DataFrame({"AlumnoID": [1]})
    rep = dq.reconcile_join(df, alumnos_path=None)
    assert rep["available"] is False


def test_run_checks_strict_raises_on_unplaced(synthetic_master_df,
                                              synthetic_subject_students,
                                              synthetic_groups):
    # actividad absente + étudiant non placé -> strict doit lever
    with pytest.raises(dq.DataQualityError):
        dq.run_data_quality_checks(
            synthetic_master_df,
            synthetic_subject_students,
            synthetic_groups,
            strict=True,
            write_report=False,
        )


def test_run_checks_nonstrict_returns_report(synthetic_master_df,
                                             synthetic_subject_students,
                                             synthetic_groups):
    rep = dq.run_data_quality_checks(
        synthetic_master_df,
        synthetic_subject_students,
        synthetic_groups,
        strict=False,
        write_report=False,
    )
    assert "integrity" in rep
    assert "grouping" in rep
    assert rep["grouping"]["total_unplaced"] == 1
