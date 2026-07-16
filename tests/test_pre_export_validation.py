"""Tests unitaires pour ``pre_export_validation`` (TASK 5).

Vérifie la détection des collisions critiques (C1 matière, C4 salle,
double-réservation professeur), le signal C7, le score de qualité, la
sérialisation du rapport et la porte pré-export ``run_pre_export_gate``.

Aucune dépendance aux gros fichiers de production : tous les plannings sont
construits synthétiquement (avec ``student_busy``/``professor_busy`` explicites).
"""

import json

import pandas as pd
import pytest

import pre_export_validation as pev


def _row(sem, subject, grupo, week, day, blk, room="Lab Alpha",
         professor="", curso_num=1, session=1):
    return {
        "semester": sem, "subject": subject, "grupo": grupo,
        "session": session, "week": week, "day": day, "time_block": blk,
        "nb_students": 10, "lab_rooms": room, "professor": professor,
        "curso_num": curso_num,
    }


# ---------------------------------------------------------------------------
# Planning propre → aucun conflit critique
# ---------------------------------------------------------------------------

def test_clean_schedule_has_no_critical_collision():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 2, "Lunes", "08:30-10:30",
             room="Lab Alpha", professor="Prof A"),
        _row(1, "S1_Física", 2, 2, "Martes", "08:30-10:30",
             room="Lab Beta", professor="Prof B"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/does/not/exist.csv")
    assert rep.n_critical == 0
    assert not rep.should_block_export()
    assert rep.total_sessions == 2
    assert rep.quality_score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# C1 — même matière, deux groupes, même créneau
# ---------------------------------------------------------------------------

def test_c1_same_subject_two_groups_same_slot():
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert len(rep.c1) == 1
    assert rep.c1[0].kind == "C1"
    assert rep.should_block_export()


# ---------------------------------------------------------------------------
# C4 — deux séances partagent une salle physique au même créneau
# ---------------------------------------------------------------------------

def test_c4_room_double_booked():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 4, "Jueves", "15:00-17:00", room="Lab Shared"),
        _row(1, "S1_Biología", 1, 4, "Jueves", "15:00-17:00", room="Lab Shared"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert len(rep.c4) == 1
    assert rep.c4[0].kind == "C4"
    assert rep.should_block_export()


def test_c4_ignores_non_physical_rooms():
    # « Aula ... » n'est pas une salle physique unique → pas de C4.
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 4, "Jueves", "15:00-17:00", room="Aula 101"),
        _row(1, "S1_Biología", 1, 4, "Jueves", "15:00-17:00", room="Aula 101"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert len(rep.c4) == 0


# ---------------------------------------------------------------------------
# Professeur — double-réservation interne (CRITIQUE)
# ---------------------------------------------------------------------------

def test_professor_internal_double_booking_is_critical():
    df = pd.DataFrame([
        _row(1, "S1_Mecanismos", 7, 5, "Viernes", "17:00-19:00",
             room="Lab A", professor="Parody Martín, Álvaro"),
        _row(1, "S1_Termodinámica", 7, 5, "Viernes", "17:00-19:00",
             room="Lab B", professor="Parody Martín, Álvaro"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert len(rep.professor) == 1
    assert "Parody" in rep.professor[0].detail
    assert rep.should_block_export()


def test_professor_external_busy_is_warning_only():
    # Le prof est marqué occupé (day_idx=0 Lunes, block_id=1 08:30) mais c'est
    # un simple AVERTISSEMENT (non bloquant).
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 2, "Lunes", "08:30-10:30",
             professor="Prof Ext"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={"Prof Ext": {(0, 1)}},
        groups_path="/no.csv")
    assert len(rep.professor) == 0          # pas de collision critique
    assert any("prof indispo" in w for w in rep.warnings)
    assert not rep.should_block_export()


# ---------------------------------------------------------------------------
# C7 — préférence horaire (signal, non bloquant)
# ---------------------------------------------------------------------------

def test_c7_is_signal_not_blocking():
    # 1re année placée l'après-midi → hors préférence (C7), non bloquant.
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 2, "Lunes", "17:00-19:00", curso_num=1),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert len(rep.c7) == 1
    assert rep.n_critical == 0
    assert not rep.should_block_export()


# ---------------------------------------------------------------------------
# Rapport : sérialisation + rendu texte
# ---------------------------------------------------------------------------

def test_report_to_dict_and_format_text():
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    rep = pev.validate_complete_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    d = rep.to_dict()
    assert d["blocking"] is True
    assert d["counts"]["C1"] == 1
    assert "n_critical" in d
    txt = rep.format_text()
    assert "VALIDATION PRÉ-EXPORT" in txt
    assert "EXPORT BLOQUÉ" in txt


def test_empty_schedule():
    rep = pev.validate_complete_schedule(
        pd.DataFrame(), student_busy={}, professor_busy={})
    assert rep.total_sessions == 0
    assert rep.warnings


# ---------------------------------------------------------------------------
# Porte pré-export
# ---------------------------------------------------------------------------

def test_gate_blocks_when_configured(tmp_path):
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    report_path = tmp_path / "pev.json"
    allow, rep = pev.run_pre_export_gate(
        df, block_on_critical=True, report_path=str(report_path),
        student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert allow is False
    assert rep.n_critical >= 1
    assert report_path.exists()
    saved = json.loads(report_path.read_text())
    assert saved["blocking"] is True


def test_gate_allows_when_non_blocking(tmp_path):
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    report_path = tmp_path / "pev.json"
    allow, rep = pev.run_pre_export_gate(
        df, block_on_critical=False, report_path=str(report_path),
        student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert allow is True                     # non bloquant → export autorisé
    assert rep.n_critical >= 1               # mais collisions bien détectées
    assert report_path.exists()
