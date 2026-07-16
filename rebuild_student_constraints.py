"""
rebuild_student_constraints.py — Régénération CORRECTE de student_busy.csv
==========================================================================

CONTEXTE (cause racine des 99 collisions / 75,6 % des séances)
--------------------------------------------------------------
`student_busy.csv` était dérivé de `master_schedule.csv`, dont les créneaux
horaires NE CORRESPONDENT PAS aux emplois du temps réels 2025-2026 validés par
Daniel (grilles « Horarios »). Le solveur croyait donc certains créneaux libres
alors qu'ils étaient occupés par des cours magistraux → il y plaçait des labos
→ collisions C4 (théorie ↔ étudiant).

CORRECTION (P0)
---------------
Ce script régénère `student_busy.csv` à partir de la SOURCE DE VÉRITÉ : les
grilles Horarios (une par titulación et par année), via `horarios_grid.py`.

Principe : un étudiant de (titulación T, année A) est OCCUPÉ à tous les
créneaux où la grille Horarios de (T, A) place un cours magistral.

    student_busy[student_id] = ⋃  grid[(T, A)]   pour chaque (T, A) de l'étudiant

Sortie :
  • data_clean/optimization/student_busy.csv      (student_id, day_idx, block_id)
  • data_clean/optimization/titulacion_busy.csv   (grille par titulación/année)
  • reports/rebuild_student_constraints_report.txt (rapport de validation)

Usage :
    python rebuild_student_constraints.py                 # chemins par défaut
    python rebuild_student_constraints.py --verbose
    python rebuild_student_constraints.py --strict        # échoue si couverture < seuil
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from typing import Dict, Optional, Tuple

import pandas as pd

import horarios_grid as hg

SCRIPT_VERSION = "1.0.0"

# Chemins par défaut (résolus dans l'ordre).
STUDENT_DIRECTORY_CANDIDATES = [
    "data_clean/optimization/student_directory.csv",
    "/home/ubuntu/Shared/Uploads/student_directory.csv",
    "data/student_directory.csv",
]
GROUP_COMPOSITION_CANDIDATES = [
    "data_clean/optimization/group_composition.csv",
    "/home/ubuntu/Shared/Uploads/group_composition.csv",
    "data/group_composition.csv",
]

ANO_TO_CURSO = {
    "primero": 1, "segundo": 2, "tercero": 3, "cuarto": 4,
    "1": 1, "2": 2, "3": 3, "4": 4,
}

OUT_STUDENT_BUSY = "data_clean/optimization/student_busy.csv"
OUT_TITULACION_BUSY = "data_clean/optimization/titulacion_busy.csv"
OUT_REPORT = "reports/rebuild_student_constraints_report.txt"


def _resolve(cands) -> Optional[str]:
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None


def ano_to_curso(value) -> Optional[int]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return ANO_TO_CURSO.get(hg.strip_accents(str(value)))


def load_student_year_map(
    student_directory_path: str,
    group_composition_path: Optional[str],
) -> Tuple[Dict[int, set], pd.DataFrame]:
    """
    Construit la table student_id -> ensemble de (titulacion_norm, curso_num).

    - titulación : depuis student_directory (code court fiable) ;
    - année (curso) : depuis group_composition (colonne 'año'), jointe par nom.

    Retourne (mapping, table_debug).
    """
    sd = pd.read_csv(student_directory_path)
    sd.columns = [c.strip().lstrip("\ufeff") for c in sd.columns]
    sd["_name"] = sd["student_name"].astype(str).str.strip().str.upper()

    year_by_name = defaultdict(set)  # name -> {curso_num}
    if group_composition_path and os.path.exists(group_composition_path):
        gc = pd.read_csv(group_composition_path)
        gc.columns = [c.strip().lstrip("\ufeff") for c in gc.columns]
        name_col = "student_name" if "student_name" in gc.columns else None
        ano_col = "año" if "año" in gc.columns else (
            "ano" if "ano" in gc.columns else None)
        if name_col and ano_col:
            for _, row in gc.iterrows():
                nm = str(row[name_col]).strip().upper()
                cur = ano_to_curso(row[ano_col])
                if nm and cur:
                    year_by_name[nm].add(cur)

    mapping: Dict[int, set] = {}
    debug_rows = []
    for _, row in sd.iterrows():
        try:
            sid = int(row["student_id"])
        except Exception:
            continue
        tit = hg.normalize_titulacion(row.get("titulacion"))
        cursos = year_by_name.get(row["_name"], set())
        pairs = {(tit, c) for c in cursos} if cursos else set()
        mapping[sid] = pairs
        debug_rows.append({
            "student_id": sid,
            "titulacion": tit,
            "cursos": ",".join(str(c) for c in sorted(cursos)) or "?",
            "n_pairs": len(pairs),
        })
    return mapping, pd.DataFrame(debug_rows)


def build_student_busy(
    grid: dict,
    student_year_map: Dict[int, set],
) -> Tuple[Dict[int, set], Dict[str, int]]:
    """
    Dérive student_busy à partir de la grille d'occupation.

    Retourne (student_busy, stats).
    """
    student_busy: Dict[int, set] = {}
    stats = {
        "students_total": len(student_year_map),
        "students_with_slots": 0,
        "students_without_year": 0,
        "students_grid_missing": 0,
        "total_busy_entries": 0,
    }
    missing_keys = set()
    for sid, pairs in student_year_map.items():
        if not pairs:
            stats["students_without_year"] += 1
            student_busy[sid] = set()
            continue
        busy = set()
        had_grid = False
        for (tit, curso) in pairs:
            slots = hg.busy_slots_for(grid, tit, curso)
            if slots:
                had_grid = True
                busy |= slots
            else:
                missing_keys.add((tit, curso))
        student_busy[sid] = busy
        if busy:
            stats["students_with_slots"] += 1
            stats["total_busy_entries"] += len(busy)
        elif not had_grid:
            stats["students_grid_missing"] += 1
    stats["missing_grid_keys"] = sorted(missing_keys)
    return student_busy, stats


def write_outputs(grid: dict, student_busy: Dict[int, set],
                  out_student_busy: str, out_titulacion_busy: str) -> None:
    os.makedirs(os.path.dirname(out_student_busy) or ".", exist_ok=True)

    # student_busy.csv
    rows = []
    for sid, slots in student_busy.items():
        for (day_idx, block_id) in sorted(slots):
            rows.append({"student_id": sid, "day_idx": day_idx,
                         "block_id": block_id})
    sb_df = pd.DataFrame(rows, columns=["student_id", "day_idx", "block_id"])
    sb_df.to_csv(out_student_busy, index=False, encoding="utf-8-sig")

    # titulacion_busy.csv (grille lisible : occupation par titulación/année)
    trows = []
    for (tit, curso), slots in sorted(grid.items()):
        for (day_idx, block_id), course in sorted(slots.items()):
            trows.append({
                "titulacion": tit,
                "curso": curso,
                "day_idx": day_idx,
                "day": hg.DAYS[day_idx] if 0 <= day_idx < len(hg.DAYS) else day_idx,
                "block_id": block_id,
                "franja": hg.BLOCK_ID_TO_LABEL.get(block_id, block_id),
                "curso_magistral": course,
            })
    pd.DataFrame(trows).to_csv(out_titulacion_busy, index=False,
                               encoding="utf-8-sig")


def build_report(grid: dict, stats: dict, debug: pd.DataFrame) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("RAPPORT — Régénération de student_busy.csv (source : Horarios réels)")
    lines.append(f"Version script : {SCRIPT_VERSION}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("1. GRILLE D'OCCUPATION (source de vérité)")
    lines.append(hg.grid_summary(grid).to_string(index=False))
    lines.append("")
    lines.append("2. COUVERTURE ÉTUDIANTS")
    lines.append(f"   Étudiants traités              : {stats['students_total']}")
    lines.append(f"   Avec créneaux occupés dérivés  : {stats['students_with_slots']}")
    lines.append(f"   Sans année (curso) identifiée  : {stats['students_without_year']}")
    lines.append(f"   Sans grille correspondante     : {stats['students_grid_missing']}")
    lines.append(f"   Entrées student_busy générées  : {stats['total_busy_entries']}")
    if stats["students_total"]:
        cov = 100.0 * stats["students_with_slots"] / stats["students_total"]
        lines.append(f"   Taux de couverture             : {cov:.1f}%")
    lines.append("")
    if stats.get("missing_grid_keys"):
        lines.append("3. (titulación, curso) SANS GRILLE Horarios (à vérifier)")
        for (tit, curso) in stats["missing_grid_keys"]:
            n = int((debug["titulacion"] == tit).sum()) if not debug.empty else 0
            lines.append(f"   - {tit} / curso {curso}  (~{n} étudiants de cette titulación)")
        lines.append("")
    lines.append("4. VALIDATION")
    ok = stats["students_with_slots"] > 0
    lines.append(f"   student_busy non vide          : {'OUI' if ok else 'NON'}")
    lines.append("")
    return "\n".join(lines)


def rebuild(
    files_by_curso: Optional[Dict[int, str]] = None,
    student_directory_path: Optional[str] = None,
    group_composition_path: Optional[str] = None,
    out_student_busy: str = OUT_STUDENT_BUSY,
    out_titulacion_busy: str = OUT_TITULACION_BUSY,
    verbose: bool = False,
) -> Tuple[Dict[int, set], dict]:
    """API programmatique : régénère et écrit les fichiers, renvoie (busy, stats)."""
    grid = hg.load_occupancy_grid(files_by_curso, verbose=verbose)
    if not grid:
        raise RuntimeError(
            "Aucune grille Horarios chargée. Vérifiez les fichiers rev15/rev17/rev11.")

    sd_path = student_directory_path or _resolve(STUDENT_DIRECTORY_CANDIDATES)
    if not sd_path:
        raise FileNotFoundError("student_directory.csv introuvable.")
    gc_path = group_composition_path or _resolve(GROUP_COMPOSITION_CANDIDATES)

    year_map, debug = load_student_year_map(sd_path, gc_path)
    student_busy, stats = build_student_busy(grid, year_map)
    write_outputs(grid, student_busy, out_student_busy, out_titulacion_busy)

    report = build_report(grid, stats, debug)
    os.makedirs(os.path.dirname(OUT_REPORT) or ".", exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(report)
    if verbose:
        print(report)
    return student_busy, stats


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Régénère student_busy.csv depuis les grilles Horarios réelles.")
    p.add_argument("--rev1", help="xlsx 1er cours (curso 1)")
    p.add_argument("--rev2", help="xlsx 2e cours (curso 2)")
    p.add_argument("--rev3", help="xlsx 3e cours (curso 3)")
    p.add_argument("--student-directory")
    p.add_argument("--group-composition")
    p.add_argument("--out", default=OUT_STUDENT_BUSY)
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--strict", action="store_true",
                   help="Échoue si aucun créneau généré.")
    args = p.parse_args(argv)

    files_by_curso = None
    overrides = {1: args.rev1, 2: args.rev2, 3: args.rev3}
    if any(overrides.values()):
        files_by_curso = {}
        for curso, cands in hg.DEFAULT_HORARIOS_FILES.items():
            path = overrides.get(curso) or hg._resolve_path(cands)
            if path:
                files_by_curso[curso] = path

    print(f"[rebuild_student_constraints] version {SCRIPT_VERSION}")
    try:
        _, stats = rebuild(
            files_by_curso=files_by_curso,
            student_directory_path=args.student_directory,
            group_composition_path=args.group_composition,
            out_student_busy=args.out,
            verbose=args.verbose,
        )
    except Exception as e:
        print(f"  [ERREUR] {e}")
        return 1

    print(f"  [OK] {args.out} écrit "
          f"({stats['total_busy_entries']} entrées, "
          f"{stats['students_with_slots']}/{stats['students_total']} étudiants).")
    print(f"  [OK] Rapport : {OUT_REPORT}")
    if args.strict and stats["students_with_slots"] == 0:
        print("  [STRICT] Aucun créneau généré -> échec.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
