"""Tests unitaires pour ``cpsat_verifier`` — vérification formelle CP-SAT.

Vérifie que le modèle CP-SAT prouve correctement la validité (0 violation) ou
identifie chaque type de violation dure (C1, professeur, salle, semaine exclue,
étudiant) ainsi que le signal de préférence horaire.

Tous les plannings sont synthétiques : aucune dépendance aux gros fichiers de
production.
"""

import json

import pandas as pd
import pytest

import cpsat_verifier as cpv


def _row(sem, subject, grupo, week, day, blk, room="Lab Alpha",
         professor="", curso_num=1, session=1):
    return {
        "semester": sem, "subject": subject, "program": "GITI",
        "curso_num": curso_num, "grupo": grupo, "session": session,
        "week": week, "day": day, "time_block": blk, "nb_students": 10,
        "lab_rooms": room, "professor": professor,
    }


# ---------------------------------------------------------------------------
# Planning propre → formellement valide
# ---------------------------------------------------------------------------

def test_clean_schedule_is_feasible():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 2, "Lunes", "08:30-10:30",
             room="Lab Alpha", professor="Prof A"),
        _row(1, "S1_Física", 2, 2, "Martes", "08:30-10:30",
             room="Lab Beta", professor="Prof B"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert res.is_feasible
    assert res.n_critical == 0
    assert res.total_sessions == 2
    assert res.solver_status in ("OPTIMAL", "FEASIBLE")
    assert not res.should_block_export()


# ---------------------------------------------------------------------------
# C1 — même matière, deux groupes, même créneau
# ---------------------------------------------------------------------------

def test_c1_same_subject_two_groups_same_slot():
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    c1 = [v for v in res.violations if v.kind == "C1"]
    assert len(c1) == 1
    assert not res.is_feasible
    assert res.should_block_export()


# ---------------------------------------------------------------------------
# Professeur — double-réservation interne
# ---------------------------------------------------------------------------

def test_professor_internal_double_booking():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 3, "Lunes", "10:30-12:30",
             room="Lab A", professor="Dr X"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30",
             room="Lab B", professor="Dr X"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    profs = [v for v in res.violations if v.kind == "professor"]
    assert len(profs) == 1
    assert not res.is_feasible


# ---------------------------------------------------------------------------
# Professeur — indisponibilité externe (professor_busy)
# ---------------------------------------------------------------------------

def test_professor_external_unavailability():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 3, "Lunes", "10:30-12:30", professor="Dr Y"),
    ])
    # Lunes = day_idx 0, 10:30-12:30 = block_id 2
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={"Dr Y": {(0, 2)}},
        groups_path="/no.csv")
    profs = [v for v in res.violations if v.kind == "professor"]
    assert len(profs) == 1
    assert "indisponible" in profs[0].detail


# ---------------------------------------------------------------------------
# Salle — double-booking d'une salle physique
# ---------------------------------------------------------------------------

def test_room_double_booking():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 4, "Jueves", "15:00-17:00", room="Lab Shared"),
        _row(1, "S1_Química", 3, 4, "Jueves", "15:00-17:00", room="Lab Shared"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    rooms = [v for v in res.violations if v.kind == "room"]
    assert len(rooms) == 1
    assert not res.is_feasible


def test_non_physical_room_ignored():
    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 4, "Jueves", "15:00-17:00", room="Aula"),
        _row(1, "S1_Química", 3, 4, "Jueves", "15:00-17:00", room="Aula"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert [v for v in res.violations if v.kind == "room"] == []


# ---------------------------------------------------------------------------
# Semaine exclue
# ---------------------------------------------------------------------------

def test_excluded_week_detected(monkeypatch):
    # Force la semaine 7 comme exclue pour toutes les matières.
    monkeypatch.setattr(cpv, "_excluded_weeks_for", lambda subject: {7})
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 7, "Lunes", "08:30-10:30"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    excl = [v for v in res.violations if v.kind == "excluded"]
    assert len(excl) == 1
    assert excl[0].week == 7
    assert not res.is_feasible


# ---------------------------------------------------------------------------
# Étudiant — TP posé sur un créneau de cours (student_busy par nom)
# ---------------------------------------------------------------------------

def test_student_course_collision(tmp_path):
    groups = pd.DataFrame([
        {"año": "Primero", "semester": "S1", "subject": "Física", "grupo": 1,
         "program": "GITI", "day": "Lunes", "block": "08:30-10:30",
         "student_name": "PEREZ, ANA", "titulacion": "GITI", "is_override": False},
    ])
    gpath = tmp_path / "groups.csv"
    groups.to_csv(gpath, index=False)

    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 5, "Lunes", "08:30-10:30"),
    ])
    # ANA a un cours Lunes (0) au bloc 1 → collision TP vs cours
    res = cpv.verify_schedule(
        df, student_busy={"PEREZ, ANA": {(0, 1)}}, professor_busy={},
        groups_path=str(gpath))
    assert res.student_checked
    studs = [v for v in res.violations if v.kind == "student"]
    assert len(studs) == 1


def test_student_double_tp(tmp_path):
    groups = pd.DataFrame([
        {"año": "Primero", "semester": "S1", "subject": "Física", "grupo": 1,
         "program": "GITI", "day": "Lunes", "block": "08:30-10:30",
         "student_name": "GOMEZ, LUIS", "titulacion": "GITI", "is_override": False},
        {"año": "Primero", "semester": "S1", "subject": "Química", "grupo": 2,
         "program": "GITI", "day": "Lunes", "block": "08:30-10:30",
         "student_name": "GOMEZ, LUIS", "titulacion": "GITI", "is_override": False},
    ])
    gpath = tmp_path / "groups.csv"
    groups.to_csv(gpath, index=False)

    df = pd.DataFrame([
        _row(1, "S1_Física", 1, 5, "Lunes", "08:30-10:30"),
        _row(1, "S1_Química", 2, 5, "Lunes", "08:30-10:30"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path=str(gpath))
    studs = [v for v in res.violations if v.kind == "student"]
    assert len(studs) == 1
    assert "deux TP" in studs[0].detail


# ---------------------------------------------------------------------------
# Préférence horaire (signal non bloquant)
# ---------------------------------------------------------------------------

def test_preference_signal_non_blocking():
    df = pd.DataFrame([
        # 1re année placée l'après-midi → hors préférence (signal)
        _row(1, "S1_Física", 1, 5, "Lunes", "15:00-17:00", curso_num=1),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    prefs = [v for v in res.violations if v.kind == "pref"]
    assert len(prefs) == 1
    assert res.is_feasible          # signal non bloquant
    assert not res.should_block_export()


# ---------------------------------------------------------------------------
# Rapport : sérialisation + rendu texte
# ---------------------------------------------------------------------------

def test_report_to_dict_and_text():
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    res = cpv.verify_schedule(
        df, student_busy={}, professor_busy={}, groups_path="/no.csv")
    d = res.to_dict()
    assert d["blocking"] is True
    assert d["counts"].get("C1") == 1
    js = json.dumps(d, ensure_ascii=False)
    assert "C1" in js
    txt = res.format_text()
    assert "VÉRIFICATION FORMELLE CP-SAT" in txt
    assert "INVALIDE" in txt


# ---------------------------------------------------------------------------
# Planning vide → géré gracieusement
# ---------------------------------------------------------------------------

def test_empty_schedule():
    res = cpv.verify_schedule(
        pd.DataFrame([]), student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert not res.is_feasible
    assert res.total_sessions == 0
    assert res.warnings


def test_missing_file_path():
    res = cpv.verify_schedule("/does/not/exist.csv")
    assert not res.is_feasible
    assert res.warnings


# ---------------------------------------------------------------------------
# Porte d'intégration pipeline
# ---------------------------------------------------------------------------

def test_verification_gate_blocks_when_requested(tmp_path):
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    report_path = tmp_path / "cpsat.json"
    allow, res = cpv.run_cpsat_verification_gate(
        df, block_on_critical=True, report_path=str(report_path),
        student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert allow is False
    assert res.n_critical >= 1
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["blocking"] is True


def test_verification_gate_allows_when_non_blocking(tmp_path):
    df = pd.DataFrame([
        _row(1, "S1_Química", 1, 3, "Lunes", "10:30-12:30", room="Lab A"),
        _row(1, "S1_Química", 2, 3, "Lunes", "10:30-12:30", room="Lab B"),
    ])
    report_path = tmp_path / "cpsat.json"
    allow, res = cpv.run_cpsat_verification_gate(
        df, block_on_critical=False, report_path=str(report_path),
        student_busy={}, professor_busy={}, groups_path="/no.csv")
    assert allow is True
    assert res.n_critical >= 1
    assert report_path.exists()
