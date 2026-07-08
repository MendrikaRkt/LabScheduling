"""Tests du module de supervision (monitoring.py).

Le module de supervision est une « tour de contrôle » : il agrège des
collecteurs PURS (sans Streamlit, défensifs) qui réutilisent les sources de
vérité existantes (reliability_metrics, lab_professor_assignment). Ces tests
verrouillent le comportement des collecteurs sur des données SYNTHÉTIQUES, sans
dépendre des gros fichiers Excel/CSV de production, afin que la CI reste rapide,
déterministe et reproductible.

Philosophie vérifiée ici : « l'affectation est une donnée ; le système la
valide, il ne la décide pas » — chaque collecteur SIGNALE les anomalies et se
dégrade proprement (renvoie une structure vide plutôt que de lever) lorsque les
entrées manquent.
"""

import json
import os

import pandas as pd
import pytest

import monitoring as mon


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _sess(subject, grupo, session, week, day="Lunes", block="08:30",
          room="Lab A", semester=1):
    """Une ligne de planning au schéma canonique (cf. master_schedule)."""
    return {"subject": subject, "semester": semester, "grupo": grupo,
            "session": session, "week": week, "day": day,
            "time_block": block, "lab_rooms": room, "nb_students": 3}


@pytest.fixture
def clean_schedule():
    """Planning conforme : C1/C4/C5 respectés, deux matières, trois groupes."""
    return pd.DataFrame([
        _sess("Física", 1, 1, 2),
        _sess("Física", 1, 2, 6, day="Martes"),
        _sess("Física", 2, 1, 3, day="Miércoles", room="Lab B"),
        _sess("Química", 1, 1, 4, day="Jueves", room="Lab C", semester=2),
        _sess("Química", 1, 2, 8, day="Jueves", room="Lab C", semester=2),
    ])


@pytest.fixture
def groups_with_duplicate():
    """Groupes : 'Ana' est dans 2 groupes de la même matière (anomalie)."""
    return pd.DataFrame([
        {"student_name": "Ana", "subject": "Física", "grupo": 1,
         "program": "GIM", "is_override": False},
        {"student_name": "Ana", "subject": "Física", "grupo": 2,
         "program": "GIM", "is_override": False},
        {"student_name": "Beto", "subject": "Física", "grupo": 1,
         "program": "GIM", "is_override": False},
        {"student_name": "Caro", "subject": "Química", "grupo": 1,
         "program": "GIE", "is_override": False},
    ])


# ---------------------------------------------------------------------------
# 2) estimate_model_size
# ---------------------------------------------------------------------------

def test_estimate_model_size_empty_returns_zeros():
    out = mon.estimate_model_size(pd.DataFrame())
    assert out["n_sessions"] == 0
    assert out["est_variables"] == 0
    assert out["total_constraints_est"] == 0
    assert "note" in out  # rappelle que c'est une estimation


def test_estimate_model_size_counts_sessions_and_c5():
    df = pd.DataFrame([
        _sess("Física", 1, 1, 2),
        _sess("Física", 1, 2, 6, day="Martes"),
        _sess("Física", 1, 3, 9, day="Miércoles"),
    ])
    out = mon.estimate_model_size(df)
    assert out["n_sessions"] == 3
    assert out["est_variables"] == 3
    # C5 = Σ (k-1) par (matière, groupe) = 3-1 = 2
    assert out["c5_constraints"] == 2


def test_estimate_model_size_detects_c1_and_c4_families():
    # Deux séances de la MÊME matière sur le MÊME créneau -> 1 famille C1.
    # Même salle, même créneau -> 1 famille C4.
    df = pd.DataFrame([
        _sess("Física", 1, 1, 2, room="Lab A"),
        _sess("Física", 2, 1, 2, room="Lab A"),
    ])
    out = mon.estimate_model_size(df)
    assert out["c1_families"] == 1
    assert out["c4_families"] == 1


# ---------------------------------------------------------------------------
# 3) collect_constraint_checks
# ---------------------------------------------------------------------------

def test_constraint_checks_clean_schedule_all_passed(clean_schedule):
    out = mon.collect_constraint_checks(clean_schedule, pd.DataFrame())
    assert out["all_passed"] is True
    codes = {c["code"] for c in out["checks"]}
    assert codes == {"C1", "C4", "C5", "STU"}
    assert all(c["passed"] for c in out["checks"])


def test_constraint_checks_flags_c5_violation():
    # Séance 2 placée AVANT la séance 1 -> violation C5 détectée par rm.
    df = pd.DataFrame([
        _sess("Química", 1, 1, 8),
        _sess("Química", 1, 2, 3, day="Martes"),
    ])
    out = mon.collect_constraint_checks(df, pd.DataFrame())
    assert out["c5_violations"] == 1
    assert out["all_passed"] is False
    c5 = next(c for c in out["checks"] if c["code"] == "C5")
    assert c5["passed"] is False


def test_constraint_checks_empty_is_graceful():
    out = mon.collect_constraint_checks(pd.DataFrame(), pd.DataFrame())
    assert out["all_passed"] is True  # rien à vérifier -> aucune violation
    assert "checks" in out


# ---------------------------------------------------------------------------
# 4) detect_student_group_duplicates
# ---------------------------------------------------------------------------

def test_detect_duplicate_student_across_groups(groups_with_duplicate):
    out = mon.detect_student_group_duplicates(groups_with_duplicate)
    assert out["count"] == 1
    ex = out["examples"][0]
    assert ex["student"] == "Ana"
    assert ex["subject"] == "Física"
    assert ex["groups"] == [1, 2]


def test_detect_duplicate_ignores_overrides():
    # Même étudiant dans 2 groupes mais placements arbitrés -> ignorés.
    df = pd.DataFrame([
        {"student_name": "Ana", "subject": "Física", "grupo": 1,
         "is_override": True},
        {"student_name": "Ana", "subject": "Física", "grupo": 2,
         "is_override": True},
    ])
    out = mon.detect_student_group_duplicates(df)
    assert out["count"] == 0


def test_detect_duplicate_empty_is_graceful():
    out = mon.detect_student_group_duplicates(pd.DataFrame())
    assert out["count"] == 0
    assert out["examples"] == []


# ---------------------------------------------------------------------------
# 5) collect_credit_compliance — chemins dégradés déterministes
# ---------------------------------------------------------------------------

def test_credit_compliance_empty_not_available():
    out = mon.collect_credit_compliance(pd.DataFrame())
    assert out["available"] is False
    assert out["rows"] == []
    assert out["n_over"] == 0


def test_credit_compliance_missing_columns_not_available():
    df = pd.DataFrame({"foo": [1, 2], "bar": [3, 4]})
    out = mon.collect_credit_compliance(df)
    assert out["available"] is False


# ---------------------------------------------------------------------------
# 8) collect_existing_labs / collect_enrollment
# ---------------------------------------------------------------------------

def test_existing_labs_summarises_subjects_and_groups(clean_schedule):
    out = mon.collect_existing_labs(clean_schedule)
    assert out["n_subjects"] == 2          # Física + Química
    assert out["n_sessions"] == 5
    # Física a 2 groupes, Química 1 -> 3 couples (matière, groupe)
    assert out["n_groups"] == 3
    subjects = {s["subject"] for s in out["per_subject"]}
    assert subjects == {"Física", "Química"}


def test_existing_labs_empty_is_graceful():
    out = mon.collect_existing_labs(pd.DataFrame())
    assert out == {"n_subjects": 0, "n_groups": 0, "n_sessions": 0,
                   "per_subject": []}


def test_enrollment_counts_students_and_overrides(groups_with_duplicate):
    out = mon.collect_enrollment(groups_with_duplicate)
    assert out["n_enrolments"] == 4
    assert out["n_students"] == 3          # Ana, Beto, Caro
    assert out["n_overrides"] == 0
    assert out["by_program"].get("GIM") == 3


# ---------------------------------------------------------------------------
# 9) Scénarios solveur / infaisabilité
# ---------------------------------------------------------------------------

def test_summarize_solver_runs_counts_by_status():
    runs = [
        {"status": "OPTIMAL", "n_sessions": 100, "wall_time_s": 1.5},
        {"status": "FEASIBLE", "n_sessions": 90, "wall_time_s": 2.0},
        {"status": "INFEASIBLE", "n_sessions": 0, "wall_time_s": 0.3},
    ]
    out = mon.summarize_solver_runs(runs)
    assert out["n_runs"] == 3
    assert out["by_status"]["OPTIMAL"] == 1
    assert out["by_status"]["INFEASIBLE"] == 1
    assert out["total_sessions"] == 190
    assert out["total_wall_time_s"] == pytest.approx(3.8)
    assert len(out["infeasible_runs"]) == 1


def test_summarize_solver_runs_empty_is_graceful():
    out = mon.summarize_solver_runs([])
    assert out["n_runs"] == 0
    assert out["infeasible_runs"] == []


def test_collect_infeasibility_reads_report_files(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "infeasibility_S1.txt").write_text(
        "Goulot détecté : salle Lab A saturée semaine 5\n", encoding="utf-8")
    stats = tmp_path / "solver_stats.json"
    stats.write_text(json.dumps([
        {"status": "INFEASIBLE", "n_sessions": 0, "semester": 2},
    ]), encoding="utf-8")

    out = mon.collect_infeasibility(reports_dir=str(reports),
                                    solver_stats_path=str(stats))
    assert len(out["files"]) == 1
    f = out["files"][0]
    assert f["name"] == "infeasibility_S1.txt"
    assert f["semester"] == "S1"
    assert "Goulot" in f["preview"]
    assert len(out["infeasible_runs"]) == 1


def test_collect_infeasibility_missing_dir_is_graceful(tmp_path):
    out = mon.collect_infeasibility(reports_dir=str(tmp_path / "nope"),
                                    solver_stats_path=str(tmp_path / "nope.json"))
    assert out["files"] == []
    assert out["infeasible_runs"] == []


# ---------------------------------------------------------------------------
# load_inputs / load_solver_runs — robustesse fichiers
# ---------------------------------------------------------------------------

def test_load_inputs_missing_file_not_available(tmp_path):
    out = mon.load_inputs(path=str(tmp_path / "absent.json"))
    assert out["available"] is False


def test_load_inputs_reads_config(tmp_path):
    cfg = tmp_path / "user_config.json"
    cfg.write_text(json.dumps({
        "global": {"preferred_size": 20, "default_max": 24},
        "subjects": {"Física": {}},
        "year_prefs": {"allow_afternoon_y1y3": True},
        "teachers": {"Prof X": {}},
        "teacher_rules": {},
        "meta": {"saved_at": "2026-01-01", "app_version": "1.0"},
    }), encoding="utf-8")
    out = mon.load_inputs(path=str(cfg))
    assert out["available"] is True
    assert out["global"]["preferred_size"] == 20
    assert "Física" in out["subjects"]


def test_load_solver_runs_missing_returns_empty(tmp_path):
    assert mon.load_solver_runs(path=str(tmp_path / "absent.json")) == []


# ---------------------------------------------------------------------------
# Agrégateur build_report
# ---------------------------------------------------------------------------

def test_build_report_structure_keys(clean_schedule, groups_with_duplicate,
                                     tmp_path):
    report = mon.build_report(
        clean_schedule, groups_with_duplicate,
        config_path=str(tmp_path / "absent.json"),
        solver_stats_path=str(tmp_path / "absent.json"),
        reports_dir=str(tmp_path / "noreports"))
    for key in ("inputs", "weights", "model_size", "constraints",
                "student_duplicates", "credit_compliance",
                "professor_conflicts", "free_busy", "existing_labs",
                "frequency", "enrollment", "solver", "infeasibility",
                "anomalies", "n_errors", "n_warnings", "n_infos"):
        assert key in report
    assert isinstance(report["anomalies"], list)
    assert report["n_errors"] >= 0


def test_collect_oversubscription_empty():
    """Cas limite : planning vide."""
    res = mon.collect_oversubscription(None)
    assert res["count"] == 0
    assert res["total_gap_groups"] == 0
    assert res["single_prof_count"] == 0
    assert res["items"] == []


def test_collect_oversubscription_no_lpa():
    """Cas défensif : si lab_professor_assignment est absent, renvoie count=0."""
    df = pd.DataFrame([
        {"subject": "Física", "grupo": 1, "week": 1, "semester": 1},
        {"subject": "Física", "grupo": 2, "week": 1, "semester": 1},
    ])
    # Sans mock de lpa, le collecteur renvoie count=0 (import exception catchée)
    res = mon.collect_oversubscription(df)
    assert res["count"] == 0
    assert res["items"] == []


def test_collect_oversubscription_on_real_data():
    """Test sur les vraies sorties du pipeline (si disponibles)."""
    import os
    sched_path = "outputs/optimization/optimized_schedule_v5.csv"
    if not os.path.exists(sched_path):
        pytest.skip("Vraies données absentes — test skippé")
    
    df = pd.read_csv(sched_path)
    res = mon.collect_oversubscription(df)
    
    # On s'attend à détecter les 14 matières sur-souscrites (cf. diagnostic)
    assert res["count"] >= 10, "Devrait détecter au moins 10 matières sur-souscrites"
    assert res["total_gap_groups"] > 0
    
    # Vérifier qu'on a bien les champs attendus
    if res["items"]:
        item = res["items"][0]
        assert "subject" in item
        assert "budget_groups" in item
        assert "planned_groups" in item
        assert "gap" in item
        assert item["gap"] > 0  # tous les items sont sur-souscrits
        assert "single_prof" in item
        assert "n_professors" in item


def test_build_report_flags_duplicate_and_missing_config(
        clean_schedule, groups_with_duplicate, tmp_path):
    report = mon.build_report(
        clean_schedule, groups_with_duplicate,
        config_path=str(tmp_path / "absent.json"),
        solver_stats_path=str(tmp_path / "absent.json"),
        reports_dir=str(tmp_path / "noreports"))
    cats = {a["category"] for a in report["anomalies"]}
    # Étudiant dupliqué -> avertissement « Inscriptions ».
    assert "Inscriptions" in cats
    # Aucune config -> info « Entrées ».
    assert "Entrées" in cats
    # Le planning est propre -> aucune erreur de contraintes.
    assert report["constraints"]["all_passed"] is True


def test_build_report_flags_constraint_error():
    # Planning avec violation C5 -> anomalie « error » catégorie Contraintes.
    df = pd.DataFrame([
        _sess("Química", 1, 1, 8),
        _sess("Química", 1, 2, 3, day="Martes"),
    ])
    report = mon.build_report(df, pd.DataFrame())
    severities = {a["severity"] for a in report["anomalies"]}
    assert "error" in severities
    assert report["n_errors"] >= 1


# ---------------------------------------------------------------------------
# Smoke test du rendu Streamlit
# ---------------------------------------------------------------------------
# Ce test instancie de FAUX helpers dont les signatures reproduisent EXACTEMENT
# celles d'app.py (notamment stat_card(label, value, desc="") — SANS argument
# `color`). Il aurait attrapé la régression `stat_card() got an unexpected
# keyword argument 'color'` avant livraison. On vérifie que render() ne lève
# jamais et n'appelle jamais safe_error (== aucune exception interne avalée).

class _FakeCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


class _FakeSt:
    """Streamlit factice : toute méthode inconnue est un no-op renvoyant un ctx."""
    def __getattr__(self, name):
        def _noop(*a, **k):
            return _FakeCtx()
        return _noop

    def columns(self, n):
        count = n if isinstance(n, int) else len(n)
        return [_FakeCtx() for _ in range(count)]


def _make_helpers():
    calls = {"safe_error": []}

    def section_header(title): pass
    # Signature IDENTIQUE à app.py : pas d'argument `color`.
    def stat_card(label, value, desc=""): pass
    def page_header(*a, **k): pass
    def safe_error(msg, e=None): calls["safe_error"].append((msg, e))

    helpers = {"page_header": page_header, "section_header": section_header,
               "stat_card": stat_card, "safe_error": safe_error}
    return helpers, calls


def test_render_smoke_with_data(monkeypatch):
    """render() ne doit jamais crasher ni avaler d'exception (données réelles)."""
    sched_path = "outputs/optimization/optimized_schedule_v5.csv"
    grp_path = "outputs/optimization/group_composition.csv"
    if not (os.path.exists(sched_path) and os.path.exists(grp_path)):
        pytest.skip("Vraies données absentes — test skippé")

    sched = pd.read_csv(sched_path)
    grp = pd.read_csv(grp_path)
    orig = mon.build_report
    monkeypatch.setattr(mon, "build_report", lambda *a, **k: orig(sched, grp))

    helpers, calls = _make_helpers()
    mon.render(_FakeSt(), helpers=helpers, t=lambda k, d=None: d or k)
    assert calls["safe_error"] == [], f"render a avalé une exception: {calls['safe_error']}"


def test_render_smoke_without_data(monkeypatch):
    """render() gère le cas 'aucune sur-souscription' (report vide) sans crasher."""
    orig = mon.build_report
    monkeypatch.setattr(mon, "build_report",
                        lambda *a, **k: orig(pd.DataFrame(), pd.DataFrame()))

    helpers, calls = _make_helpers()
    mon.render(_FakeSt(), helpers=helpers, t=lambda k, d=None: d or k)
    assert calls["safe_error"] == [], f"render a avalé une exception: {calls['safe_error']}"
