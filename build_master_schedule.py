"""
build_master_schedule.py — Script de jointure VERSIONNÉ (Étape 6.7)
==================================================================

Reconstruit `data_clean/master_schedule.csv` à partir des deux fichiers
sources Excel, en INSTRUMENTANT la jointure avec la couche qualité
(`data_quality.py`) pour rendre visible toute perte d'étudiants.

    alumnos (report_AlumnosGruposCentroDecanos.xlsx)   clé : MixtoID
        ⋈  (inner)
    aulario (revisionAulario.xlsx)                     clé : mixtoID

Chaque ligne d'inscription d'un étudiant est jointe aux créneaux (`h1_*`,
renommés `slot_*`) de son groupe mixte.

------------------------------------------------------------------------------
⚠️  AVERTISSEMENT IMPORTANT — périmètre & reproductibilité
------------------------------------------------------------------------------
Ce script produit un master **fonctionnel et auditable**, mais il n'est PAS
garanti d'être identique « octet pour octet » au master historique de
production. Raison documentée dans l'audit (§3) : la chaîne ETL d'origine
applique en amont des règles de *normalisation horaire* (p. ex. des créneaux
`08:00` de l'aulario apparaissent `08:30` dans le master) et un filtrage des
activités de laboratoire dont la règle exacte n'est pas fournie avec les
sources. Ce script :
  • réalise la jointure clé documentée (MixtoID),
  • dérive les colonnes `slot_jour_semaine`, `slot_hora_inicio_min`,
    `slot_hora_fin_min`,
  • mesure et journalise la fuite (étudiants orphelins) via la couche QA,
mais conserve les horaires SOURCES tels quels (pas de snapping inventé).

Le master canonique reste celui produit par l'ETL officiel ; ce script sert
de **référence reproductible et instrumentée** pour régénérer/diagnostiquer
la jointure et détecter les régressions de couverture.

Usage :
    python build_master_schedule.py \
        --alumnos data_clean/report_AlumnosGruposCentroDecanos.xlsx \
        --aulario data_clean/revisionAulario.xlsx \
        --out     data_clean/master_schedule_rebuilt.csv

Version du script : 1.0.0
"""

from __future__ import annotations

import argparse
import os
import sys

import pandas as pd

try:
    import data_quality as dq
except Exception:  # pragma: no cover - QA optionnelle
    dq = None


SCRIPT_VERSION = "1.0.0"

# Renommage h1_* (aulario) -> slot_* (master), tel qu'observé dans le master.
H1_TO_SLOT = {
    "h1_dia": "slot_dia",
    "h1_dia_fin": "slot_dia_fin",
    "h1_repeticion": "slot_repeticion",
    "h1_hora_inicio": "slot_hora_inicio",
    "h1_hora_fin": "slot_hora_fin",
    "h1_aula": "slot_aula",
    "h1_capacidad_aula": "slot_capacidad_aula",
}

# Jours FR/ES de la semaine (lundi=0) — cohérent avec le pipeline.
WEEKDAY_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes",
              "Sábado", "Domingo"]


def _to_minutes(value) -> "int | None":
    """'08:30' -> 510. Robuste aux NaN / formats inattendus."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    if not s or ":" not in s:
        return None
    try:
        h, m = s.split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:
        return None


def build_master(alumnos_path: str, aulario_path: str) -> pd.DataFrame:
    """Réalise la jointure documentée et dérive les colonnes calculées."""
    alumnos = pd.read_excel(alumnos_path)
    aulario = pd.read_excel(aulario_path)

    for col in ("MixtoID",):
        if col not in alumnos.columns:
            raise ValueError(f"Colonne '{col}' absente du fichier alumnos.")
    if "mixtoID" not in aulario.columns:
        raise ValueError("Colonne 'mixtoID' absente du fichier aulario.")

    # Clé de jointure normalisée (chaîne) des deux côtés.
    alumnos = alumnos.copy()
    aulario = aulario.copy()
    alumnos["mixto_id"] = alumnos["MixtoID"].astype(str)
    aulario["mixto_id"] = aulario["mixtoID"].astype(str)

    aulario = aulario.rename(columns=H1_TO_SLOT)

    # Jointure interne : une ligne par (étudiant × créneau de son groupe).
    master = alumnos.merge(aulario, on="mixto_id", how="inner",
                           suffixes=("", "_aul"))

    # --- Colonnes dérivées --------------------------------------------------
    if "slot_dia" in master.columns:
        dia = pd.to_datetime(master["slot_dia"], errors="coerce")
        master["slot_jour_semaine"] = dia.dt.weekday.map(
            lambda d: WEEKDAY_ES[int(d)] if pd.notna(d) else None
        )
    if "slot_hora_inicio" in master.columns:
        master["slot_hora_inicio_min"] = master["slot_hora_inicio"].map(_to_minutes)
    if "slot_hora_fin" in master.columns:
        master["slot_hora_fin_min"] = master["slot_hora_fin"].map(_to_minutes)

    return master


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Jointure instrumentée alumnos ⋈ aulario -> master_schedule."
    )
    parser.add_argument("--alumnos",
                        default="data_clean/report_AlumnosGruposCentroDecanos.xlsx")
    parser.add_argument("--aulario",
                        default="data_clean/revisionAulario.xlsx")
    parser.add_argument("--out", default="data_clean/master_schedule_rebuilt.csv")
    parser.add_argument("--strict", action="store_true",
                        help="Échoue (code 2) si la QA détecte une fuite.")
    args = parser.parse_args(argv)

    print(f"[build_master_schedule] version {SCRIPT_VERSION}")
    for path in (args.alumnos, args.aulario):
        if not os.path.exists(path):
            print(f"  [ERREUR] fichier introuvable : {path}")
            return 1

    master = build_master(args.alumnos, args.aulario)
    print(f"  Jointure : {len(master)} lignes, "
          f"{master['AlumnoID'].nunique() if 'AlumnoID' in master else 0} "
          f"étudiants.")

    # --- Contrôle qualité (anti-fuite) -------------------------------------
    if dq is not None:
        report = dq.run_data_quality_checks(
            master, None, None,
            alumnos_path=args.alumnos, aulario_path=args.aulario,
            strict=False, write_report=True,
        )
        join = report.get("join", {})
        if join.get("available"):
            print(f"  [QA] Inscrits bruts : {join['raw_students']} | "
                  f"dans master : {join['master_students']} | "
                  f"perdus : {join['lost_students']} ({join['loss_pct']} %)")
        if args.strict and not report.get("ok"):
            print("  [STRICT] Fuite détectée -> échec volontaire.")
            return 2
    else:
        print("  [QA] module data_quality indisponible (contrôle ignoré).")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    master.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(f"  Écrit : {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
