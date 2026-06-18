"""
kpi_report.py — Mesure de la qualité du planning (Étape 6.6)
============================================================

Calcule des indicateurs (KPIs) objectifs à CHAQUE exécution, pour ne pas se
contenter d'un « ça tourne » (cf. AUDIT_OPTIMISATION_COMPLET.md §6.6) :

  • Placement     : % d'étudiants effectivement placés (anti-fuite overflow).
  • Groupes       : nombre total, nombre d'overflow, distribution des tailles.
  • Équilibrage   : nombre de séances par jour (suivi du goulot du vendredi).
  • Salles        : taux d'occupation par salle / créneau.
  • Solveur       : statut, objectif, gap, temps (depuis SOLVER_RUNS).

Module sans effet de bord à l'import et testable isolément.
"""

from __future__ import annotations

import os
import json
import statistics
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Optional

import pandas as pd


KPI_JSON_PATH = "reports/kpi_report.json"
KPI_TEXT_PATH = "reports/kpi_report.txt"


def compute_kpis(
    results_df: Optional[pd.DataFrame],
    all_groups: List[Dict],
    dq_report: Optional[Dict] = None,
    solver_runs: Optional[List[Dict]] = None,
) -> Dict:
    """Calcule l'ensemble des KPIs. Robuste aux entrées vides/partielles."""
    kpi: Dict = {"generated_at": datetime.now().isoformat(timespec="seconds")}

    # --- Groupes -----------------------------------------------------------
    sizes = [int(g.get("nb_students", 0)) for g in all_groups]
    n_overflow = sum(1 for g in all_groups if g.get("_overflow"))
    n_recovered = sum(1 for g in all_groups if g.get("_recovered"))
    kpi["groups"] = {
        "total": len(all_groups),
        "overflow": n_overflow,
        "recovered": n_recovered,
        "size_min": min(sizes) if sizes else 0,
        "size_max": max(sizes) if sizes else 0,
        "size_mean": round(statistics.mean(sizes), 2) if sizes else 0,
        "size_std": round(statistics.pstdev(sizes), 2) if len(sizes) > 1 else 0,
    }

    # --- Placement (depuis la réconciliation QA) ---------------------------
    if dq_report and dq_report.get("grouping"):
        g = dq_report["grouping"]
        kpi["placement"] = {
            "enrolled": g.get("total_enrolled", 0),
            "placed": g.get("total_placed", 0),
            "unplaced": g.get("total_unplaced", 0),
            "placement_pct": g.get("global_placement_pct", 0.0),
        }

    # --- Équilibrage par jour + occupation salles (depuis le planning) -----
    if results_df is not None and len(results_df) > 0:
        df = results_df
        if "day" in df.columns:
            day_counts = Counter(df["day"].dropna())
            kpi["day_balance"] = dict(sorted(day_counts.items(),
                                             key=lambda kv: kv[0]))
            kpi["friday_sessions"] = int(day_counts.get("Viernes", 0))
        if "lab_rooms" in df.columns:
            room_counts: Counter = Counter()
            for rooms in df["lab_rooms"].dropna():
                for r in str(rooms).split(","):
                    r = r.strip()
                    if r:
                        room_counts[r] += 1
            kpi["room_sessions"] = dict(room_counts.most_common())
        kpi["total_sessions"] = int(len(df))

    # --- Solveur -----------------------------------------------------------
    if solver_runs:
        kpi["solver"] = solver_runs
        statuses = [r.get("status") for r in solver_runs]
        kpi["solver_summary"] = {
            "runs": len(solver_runs),
            "optimal": statuses.count("OPTIMAL"),
            "feasible": statuses.count("FEASIBLE"),
            "infeasible": statuses.count("INFEASIBLE"),
            "max_wall_time_s": max((r.get("wall_time_s", 0)
                                    for r in solver_runs), default=0),
        }

    return kpi


def render_text(kpi: Dict) -> str:
    """Rapport KPI lisible (console + fichier)."""
    L: List[str] = []
    add = L.append
    add("=" * 64)
    add("  RAPPORT KPI — QUALITÉ DU PLANNING (Étape 6.6)")
    add(f"  Généré : {kpi.get('generated_at', '')}")
    add("=" * 64)

    pl = kpi.get("placement")
    if pl:
        add("\n[Placement étudiants]")
        add(f"    Inscrits : {pl['enrolled']}  |  Placés : {pl['placed']}  "
            f"|  Non placés : {pl['unplaced']}  ({pl['placement_pct']} %)")

    gr = kpi.get("groups", {})
    add("\n[Groupes]")
    add(f"    Total : {gr.get('total', 0)}  |  Overflow : {gr.get('overflow', 0)}"
        f"  |  Récupérés : {gr.get('recovered', 0)}")
    add(f"    Tailles : min={gr.get('size_min')}  moy={gr.get('size_mean')}"
        f"  max={gr.get('size_max')}  écart-type={gr.get('size_std')}")

    if "day_balance" in kpi:
        add("\n[Équilibrage par jour (séances)]")
        for day, n in kpi["day_balance"].items():
            flag = "  ⚠️ goulot" if day == "Viernes" else ""
            add(f"    {day:12s} : {n}{flag}")

    if "room_sessions" in kpi:
        add("\n[Occupation salles (séances)]")
        for room, n in list(kpi["room_sessions"].items())[:12]:
            add(f"    {room:35s} : {n}")

    if "solver_summary" in kpi:
        s = kpi["solver_summary"]
        add("\n[Solveur]")
        add(f"    Runs : {s['runs']}  |  OPTIMAL : {s['optimal']}  "
            f"|  FEASIBLE : {s['feasible']}  |  INFEASIBLE : {s['infeasible']}")
        add(f"    Temps max : {s['max_wall_time_s']} s")
        for r in kpi.get("solver", []):
            extra = ""
            if "objective" in r:
                extra = f" obj={r['objective']:.0f} gap={r.get('gap', '?')}"
            rec = " (repli)" if r.get("recovered") else ""
            add(f"       S{r['semester']}{rec:7s} {r['status']:10s} "
                f"{r['n_sessions']} sess, {r['wall_time_s']}s{extra}")

    add("=" * 64)
    return "\n".join(L)


def write_reports(kpi: Dict) -> None:
    try:
        os.makedirs("reports", exist_ok=True)
        with open(KPI_JSON_PATH, "w", encoding="utf-8") as fh:
            json.dump(kpi, fh, ensure_ascii=False, indent=2)
        with open(KPI_TEXT_PATH, "w", encoding="utf-8") as fh:
            fh.write(render_text(kpi))
    except Exception:
        pass


def generate_kpi_report(results_df, all_groups, dq_report=None,
                        solver_runs=None, write=True, echo=True) -> Dict:
    """Point d'entrée appelé par le pipeline."""
    kpi = compute_kpis(results_df, all_groups, dq_report, solver_runs)
    if write:
        write_reports(kpi)
    if echo:
        print(render_text(kpi))
    return kpi
