"""
data_quality.py — Couche de contrôle qualité des données (Étape 6.2)
====================================================================

Objectif (cf. AUDIT_OPTIMISATION_COMPLET.md §6.2 et §3) :
  • Séparer explicitement la responsabilité « qualité des données » du reste
    du pipeline.
  • Garantir qu'AUCUN étudiant n'est perdu silencieusement, ni lors de la
    jointure aulario⋈alumnos, ni lors de la formation des groupes / overflow.
  • Journaliser toute fuite (orphelins) dans un rapport lisible et auditable.

Principe de conception :
  • Par défaut, les contrôles sont NON BLOQUANTS : ils journalisent des
    avertissements et renvoient un rapport structuré (le pipeline continue).
  • En mode strict (`strict=True`), une fuite déclenche une AssertionError —
    utile pour les tests de non-régression et la CI.

Le module est volontairement SANS effet de bord à l'import et testable
isolément (aucune dépendance au reste du pipeline).
"""

from __future__ import annotations

import os
import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Iterable

import pandas as pd


DATA_QUALITY_REPORT_PATH = "reports/data_quality_report.txt"
DATA_QUALITY_JSON_PATH = "reports/data_quality_report.json"


class DataQualityError(AssertionError):
    """Levée en mode strict lorsqu'une fuite de données est détectée."""


# --------------------------------------------------------------------------- #
#  1. Intégrité du master_schedule (colonnes & clés)                          #
# --------------------------------------------------------------------------- #
def check_master_integrity(
    df: pd.DataFrame,
    required_columns: Iterable[str] = ("AlumnoID", "actividad"),
) -> Dict:
    """
    Vérifie la présence des colonnes critiques et l'absence de clés vides.

    Renvoie un dict {ok, missing_columns, n_rows, n_students, warnings}.
    Ne lève jamais (diagnostic pur).
    """
    warnings: List[str] = []
    required = list(required_columns)
    missing = [c for c in required if c not in df.columns]

    n_students = int(df["AlumnoID"].nunique()) if "AlumnoID" in df.columns else 0
    if "AlumnoID" in df.columns:
        n_null_ids = int(df["AlumnoID"].isna().sum())
        if n_null_ids:
            warnings.append(
                f"{n_null_ids} ligne(s) avec AlumnoID vide (ignorées en aval)."
            )

    return {
        "ok": not missing,
        "missing_columns": missing,
        "n_rows": int(len(df)),
        "n_students": n_students,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
#  2. Réconciliation de la jointure aulario ⋈ alumnos (clé MixtoID)           #
# --------------------------------------------------------------------------- #
def reconcile_join(
    master_df: pd.DataFrame,
    alumnos_path: Optional[str] = None,
    aulario_path: Optional[str] = None,
) -> Dict:
    """
    Compare le nombre d'étudiants présents dans le fichier d'inscriptions BRUT
    à ceux qui ont survécu à la jointure (présents dans master_schedule).

    Les « orphelins » sont les étudiants inscrits dont le MixtoID n'a AUCUN
    horaire correspondant dans l'aulario (donc absents du master).

    Si `alumnos_path` est absent / introuvable, on ne peut pas mesurer la
    fuite de jointure : on renvoie {available: False} (non bloquant).
    """
    result: Dict = {"available": False}
    if not alumnos_path or not os.path.exists(alumnos_path):
        return result

    try:
        alumnos = pd.read_excel(alumnos_path)
    except Exception as exc:  # lecture impossible -> non bloquant
        return {"available": False, "error": f"lecture alumnos: {exc}"}

    if "AlumnoID" not in alumnos.columns or "MixtoID" not in alumnos.columns:
        return {"available": False, "error": "colonnes AlumnoID/MixtoID absentes"}

    raw_students = set(alumnos["AlumnoID"].dropna().astype(str))
    master_students = (
        set(master_df["AlumnoID"].dropna().astype(str))
        if "AlumnoID" in master_df.columns
        else set()
    )
    lost = raw_students - master_students

    # Détail des activités orphelines (pour le rapport)
    orphan_activities: Dict[str, int] = {}
    if aulario_path and os.path.exists(aulario_path):
        try:
            aul = pd.read_excel(aulario_path, usecols=lambda c: c in ("mixtoID",))
            aul_mixto = set(aul["mixtoID"].dropna().astype(str))
            orphan_rows = alumnos[~alumnos["MixtoID"].astype(str).isin(aul_mixto)]
            if "Actividad" in orphan_rows.columns:
                orphan_activities = (
                    orphan_rows["Actividad"].value_counts().head(15).to_dict()
                )
        except Exception:
            pass

    result = {
        "available": True,
        "raw_students": len(raw_students),
        "master_students": len(master_students),
        "lost_students": len(lost),
        "loss_pct": round(100 * len(lost) / len(raw_students), 2)
        if raw_students
        else 0.0,
        "lost_ids_sample": sorted(lost)[:30],
        "orphan_activities": orphan_activities,
    }
    return result


# --------------------------------------------------------------------------- #
#  3. Réconciliation de la formation des groupes (anti-fuite overflow)        #
# --------------------------------------------------------------------------- #
def reconcile_grouping(
    subject_students: Dict[str, List],
    all_groups: List[Dict],
) -> Dict:
    """
    Pour chaque matière de labo : combien d'étudiants étaient INSCRITS, combien
    ont été PLACÉS dans un groupe (y compris overflow), combien restent NON
    PLACÉS. Détecte la « perte silencieuse » signalée dans l'audit (§5.2).

    Renvoie un dict avec le détail par matière et un total global.
    """
    # Étudiants placés par matière (union des student_ids des groupes)
    placed_by_subject: Dict[str, set] = defaultdict(set)
    for g in all_groups:
        subj = g.get("subject")
        for sid in g.get("student_ids", []):
            placed_by_subject[subj].add(str(sid))

    per_subject = []
    total_enrolled = total_placed = total_unplaced = 0
    for subject, students in subject_students.items():
        enrolled = {str(s) for s in students}
        placed = placed_by_subject.get(subject, set()) & enrolled
        # Les overflow peuvent placer des étudiants : on compte aussi les placés
        # de cette matière même si l'appariement strict ci-dessus rate un id.
        placed_all = placed_by_subject.get(subject, set())
        effective_placed = placed if placed else (placed_all & enrolled)
        unplaced = enrolled - placed_all
        n_enr, n_pl, n_un = len(enrolled), len(enrolled) - len(unplaced), len(unplaced)
        per_subject.append(
            {
                "subject": subject,
                "enrolled": n_enr,
                "placed": n_pl,
                "unplaced": n_un,
                "placement_pct": round(100 * n_pl / n_enr, 1) if n_enr else 100.0,
            }
        )
        total_enrolled += n_enr
        total_placed += n_pl
        total_unplaced += n_un

    per_subject.sort(key=lambda r: r["unplaced"], reverse=True)
    return {
        "per_subject": per_subject,
        "total_enrolled": total_enrolled,
        "total_placed": total_placed,
        "total_unplaced": total_unplaced,
        "global_placement_pct": round(100 * total_placed / total_enrolled, 2)
        if total_enrolled
        else 100.0,
    }


# --------------------------------------------------------------------------- #
#  4. Orchestration : exécute tous les contrôles + écrit les rapports         #
# --------------------------------------------------------------------------- #
def run_data_quality_checks(
    master_df: pd.DataFrame,
    subject_students: Optional[Dict[str, List]] = None,
    all_groups: Optional[List[Dict]] = None,
    alumnos_path: Optional[str] = None,
    aulario_path: Optional[str] = None,
    strict: bool = False,
    write_report: bool = True,
) -> Dict:
    """
    Point d'entrée unique appelé par le pipeline.

    strict=True  -> lève DataQualityError dès qu'une fuite est détectée
                    (utilisé par les tests / la CI).
    strict=False -> journalise des avertissements, renvoie le rapport
                    (comportement par défaut en production : non bloquant).
    """
    report: Dict = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "integrity": check_master_integrity(master_df),
    }

    if alumnos_path:
        report["join"] = reconcile_join(master_df, alumnos_path, aulario_path)

    if subject_students is not None and all_groups is not None:
        report["grouping"] = reconcile_grouping(subject_students, all_groups)

    # Collecte des problèmes
    problems: List[str] = []
    if not report["integrity"]["ok"]:
        problems.append(
            f"Colonnes manquantes : {report['integrity']['missing_columns']}"
        )
    join = report.get("join", {})
    if join.get("available") and join.get("lost_students", 0) > 0:
        problems.append(
            f"Jointure : {join['lost_students']} étudiant(s) perdu(s) "
            f"({join['loss_pct']} %) — orphelins sans horaire."
        )
    grp = report.get("grouping", {})
    if grp and grp.get("total_unplaced", 0) > 0:
        problems.append(
            f"Formation des groupes : {grp['total_unplaced']} étudiant(s) "
            f"NON placé(s) dans un groupe."
        )

    report["problems"] = problems
    report["ok"] = not problems

    if write_report:
        _write_reports(report)

    if strict and problems:
        raise DataQualityError("; ".join(problems))

    return report


def _write_reports(report: Dict) -> None:
    """Écrit le rapport en JSON (machine) et en texte (humain)."""
    try:
        os.makedirs("reports", exist_ok=True)
        with open(DATA_QUALITY_JSON_PATH, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        with open(DATA_QUALITY_REPORT_PATH, "w", encoding="utf-8") as fh:
            fh.write(render_text_report(report))
    except Exception:
        # L'écriture du rapport ne doit jamais casser le pipeline.
        pass


def render_text_report(report: Dict) -> str:
    """Rend un rapport lisible (utilisé pour l'affichage console et le fichier)."""
    lines: List[str] = []
    add = lines.append
    add("=" * 64)
    add("  RAPPORT QUALITÉ DES DONNÉES (Étape 6.2)")
    add(f"  Généré : {report.get('generated_at', '')}")
    add("=" * 64)

    integ = report.get("integrity", {})
    add("\n[1] Intégrité master_schedule")
    add(f"    Lignes        : {integ.get('n_rows', 0)}")
    add(f"    Étudiants     : {integ.get('n_students', 0)}")
    add(f"    Colonnes OK   : {'oui' if integ.get('ok') else 'NON'}")
    for w in integ.get("warnings", []):
        add(f"    [WARN] {w}")

    join = report.get("join", {})
    if join.get("available"):
        add("\n[2] Réconciliation jointure (aulario ⋈ alumnos)")
        add(f"    Étudiants bruts (inscriptions) : {join['raw_students']}")
        add(f"    Étudiants dans master          : {join['master_students']}")
        add(f"    Perdus (orphelins)             : {join['lost_students']} "
            f"({join['loss_pct']} %)")
        if join.get("orphan_activities"):
            add("    Activités orphelines (top) :")
            for act, n in join["orphan_activities"].items():
                add(f"       - {act} : {n}")
    elif "join" in report:
        add("\n[2] Réconciliation jointure : fichier source indisponible (ignoré)")

    grp = report.get("grouping", {})
    if grp:
        add("\n[3] Réconciliation formation des groupes (anti-fuite overflow)")
        add(f"    Inscrits  : {grp['total_enrolled']}")
        add(f"    Placés    : {grp['total_placed']}")
        add(f"    NON placés: {grp['total_unplaced']} "
            f"(placement global {grp['global_placement_pct']} %)")
        worst = [r for r in grp["per_subject"] if r["unplaced"] > 0][:10]
        if worst:
            add("    Matières avec étudiants non placés :")
            for r in worst:
                add(f"       - {r['subject']:35s} {r['unplaced']:3d} non placés "
                    f"/ {r['enrolled']} inscrits ({r['placement_pct']} %)")

    add("\n[4] Verdict")
    if report.get("ok"):
        add("    ✅ Aucune fuite détectée.")
    else:
        add("    ⚠️  Problèmes détectés :")
        for p in report.get("problems", []):
            add(f"       - {p}")
    add("=" * 64)
    return "\n".join(lines)
