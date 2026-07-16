"""
horarios_grid.py — Lecture d'emplois du temps RÉELS (grilles « Horarios »)
==========================================================================

Ce module lit les grilles *Horarios* (une grille par titulación et par année)
telles qu'elles apparaissent dans les fichiers officiels validés par Daniel :

    Distribucion_Practicas_25-26_rev15.xlsx          → 1er cours (curso 1)
    Distribucion_Practicas_segundocurso_25-26_rev17  → 2e cours (curso 2)
    Distribucion_Practicas_tercercurso_25-26_rev11   → 3e cours (curso 3)

Chaque onglet « Horarios » contient plusieurs mini-grilles disposées en
2 colonnes (bloc gauche = colonnes 0..5, bloc droit = colonnes 7..12) et
empilées verticalement. Une grille ressemble à :

    IOI          Lunes  Martes  Miércoles  Jueves  Viernes
    08:30-10:30  MAT I  EXPRES  QUIM       FIS I   FIS I
    10:30-12:30  QUIM   ...     ...        ...     ...
    12:30-14:30  ...
    16:00-18:00  ...

Le module produit une **grille d'occupation** :

    grid[(titulacion_code, curso_num)][(day_idx, block_id)] = "NOM DU COURS"

qui est la SOURCE DE VÉRITÉ des créneaux réellement occupés par les cours
magistraux. C'est cette grille — et non `master_schedule.csv` — qui doit
servir à dériver `student_busy` (cf. rapport de collisions : le master
contenait des créneaux décalés → 99 collisions).

Réutilisé par :
  • rebuild_student_constraints.py  (régénération de student_busy.csv)
  • excel_generator_core.py         (onglet « Horarios » de sortie)
  • pre_export_validation.py        (validation titulación vs Horarios)

Aucune dépendance au reste du projet : seulement pandas.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

import pandas as pd

# ── Constantes de temps / jours (alignées sur pipeline.TIME_BLOCKS) ─────────
DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_IDS = {d: i for i, d in enumerate(DAYS)}
# Variantes normalisées (sans accent / casse) -> index
_DAY_NORM = {
    "lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4,
}

# Correspondance libellé de créneau -> block_id du solveur (1..6).
# Les fichiers réels utilisent parfois « 16:00-18:00 » (1er/3e cours,
# après-midi) et parfois « 15:00-17:00 » (2e cours). Les deux sont mappés
# sur le bloc 4 (premier bloc d'après-midi du solveur), afin de rester
# cohérent avec pipeline.TIME_BLOCKS.
BLOCK_LABEL_TO_ID: Dict[str, int] = {
    "08:30-10:30": 1,
    "10:30-12:30": 2,
    "12:30-14:30": 3,
    "15:00-17:00": 4,
    "16:00-18:00": 4,
    "17:00-19:00": 5,
    "19:00-21:00": 6,
}
BLOCK_ID_TO_LABEL: Dict[int, str] = {
    1: "08:30-10:30", 2: "10:30-12:30", 3: "12:30-14:30",
    4: "16:00-18:00", 5: "17:00-19:00", 6: "19:00-21:00",
}

# Codes de titulación reconnus dans les grilles Horarios.
KNOWN_TITULACIONES = {
    "IOI", "AERO", "IMR", "GITI", "MAT", "GITIADE", "IBIO",
    "IEM", "IINFTV", "ISW",
}

# Fichiers officiels par défaut (curso -> chemins candidats).
DEFAULT_HORARIOS_FILES: Dict[int, List[str]] = {
    1: [
        "/home/ubuntu/Uploads/Distribucion_Practicas_25-26_rev15.xlsx",
        "data/Distribucion_Practicas_25-26_rev15.xlsx",
    ],
    2: [
        "/home/ubuntu/Uploads/Distribucion_Practicas_segundocurso_25-26_rev17.xlsx",
        "data/Distribucion_Practicas_segundocurso_25-26_rev17.xlsx",
    ],
    3: [
        "/home/ubuntu/Uploads/Distribucion_Practicas_tercercurso_25-26_rev11.xlsx",
        "data/Distribucion_Practicas_tercercurso_25-26_rev11.xlsx",
    ],
}

_TIME_RE = re.compile(r"^\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s*$")


def strip_accents(text: str) -> str:
    """Minuscule sans accents, pour comparaisons robustes."""
    if text is None:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def normalize_titulacion(code) -> str:
    """
    Normalise un code de titulación pour la mise en correspondance.
    Ex. 'GITIADE22' -> 'GITIADE', 'GITI ' -> 'GITI'.
    Retire les suffixes numériques d'année de plan (…22, …13, …21).
    """
    if code is None or (isinstance(code, float) and pd.isna(code)):
        return ""
    s = str(code).strip().upper()
    s = re.sub(r"\s+", "", s)
    # Retire un suffixe numérique final (plan d'études) : GITIADE22 -> GITIADE
    s = re.sub(r"\d+$", "", s)
    return s


def _normalize_block_label(label: str) -> Optional[str]:
    """'08:30 - 10:30' / '8:30-10:30' -> '08:30-10:30' canonique."""
    if label is None:
        return None
    m = _TIME_RE.match(str(label).replace("\n", " ").strip())
    if not m:
        return None
    start, end = m.group(1), m.group(2)

    def _pad(t: str) -> str:
        h, mm = t.split(":")
        return f"{int(h):02d}:{mm}"

    return f"{_pad(start)}-{_pad(end)}"


def block_label_to_id(label: str) -> Optional[int]:
    """Libellé de créneau -> block_id (1..6), ou None si inconnu."""
    canon = _normalize_block_label(label)
    if canon is None:
        return None
    return BLOCK_LABEL_TO_ID.get(canon)


def _clean_cell(value) -> str:
    """Nettoie un libellé de cours (retire retours ligne / espaces)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _detect_header_columns(row: List) -> List[int]:
    """
    Détecte les colonnes de départ des mini-grilles sur une ligne d'en-tête.
    Un en-tête = une cellule 'titulación' suivie de 'Lunes' à la colonne+1.
    Retourne la liste des indices de colonne où commence une grille.
    """
    starts = []
    for ci in range(len(row) - 1):
        cell = _clean_cell(row[ci])
        nxt = strip_accents(_clean_cell(row[ci + 1]))
        if cell and nxt == "lunes":
            starts.append(ci)
    return starts


def parse_horarios_sheet(df: pd.DataFrame, curso_num: int,
                         grid: Optional[dict] = None) -> dict:
    """
    Analyse une feuille « Horarios » (lue sans en-tête) et remplit `grid`.

    grid[(titulacion_code, curso_num)][(day_idx, block_id)] = course_name

    Retourne le dictionnaire `grid` (créé s'il n'est pas fourni).
    """
    if grid is None:
        grid = {}

    n_rows = len(df)
    r = 0
    while r < n_rows:
        row = df.iloc[r].tolist()
        starts = _detect_header_columns(row)
        if not starts:
            r += 1
            continue

        # Pour chaque grille détectée sur cette ligne d'en-tête.
        for col0 in starts:
            titard = _clean_cell(row[col0])
            tit = normalize_titulacion(titard)
            if not tit:
                continue
            key = (tit, int(curso_num))
            grid.setdefault(key, {})

            # Colonnes des 5 jours (col0+1 .. col0+5).
            day_cols = list(range(col0 + 1, col0 + 6))

            # Parcourt les lignes suivantes jusqu'à un nouvel en-tête / fin.
            rr = r + 1
            while rr < n_rows:
                next_row = df.iloc[rr].tolist()
                # Nouvelle ligne d'en-tête => on arrête ce bloc.
                if _detect_header_columns(next_row):
                    break
                blk_label = _clean_cell(next_row[col0]) if col0 < len(next_row) else ""
                bid = block_label_to_id(blk_label)
                if bid is not None:
                    for di, dc in enumerate(day_cols):
                        if dc < len(next_row):
                            course = _clean_cell(next_row[dc])
                            if course:
                                grid[key][(di, bid)] = course
                rr += 1
        # Avance après la ligne d'en-tête (les mini-grilles se recouvrant
        # en hauteur sont gérées par le scan interne ci-dessus).
        r += 1

    return grid


def _resolve_path(candidates: List[str]) -> Optional[str]:
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def load_occupancy_grid(
    files_by_curso: Optional[Dict[int, str]] = None,
    sheet_name: str = "Horarios",
    verbose: bool = False,
) -> dict:
    """
    Charge la grille d'occupation depuis les fichiers Horarios officiels.

    files_by_curso : {curso_num: chemin_xlsx}. Si None, utilise les chemins
    par défaut (DEFAULT_HORARIOS_FILES) et prend le premier existant.

    Retourne grid[(titulacion, curso_num)][(day_idx, block_id)] = course.
    """
    grid: dict = {}
    if files_by_curso is None:
        files_by_curso = {}
        for curso, cands in DEFAULT_HORARIOS_FILES.items():
            path = _resolve_path(cands)
            if path:
                files_by_curso[curso] = path

    for curso_num, path in sorted(files_by_curso.items()):
        if not path or not os.path.exists(path):
            if verbose:
                print(f"  [horarios] curso {curso_num}: fichier absent ({path})")
            continue
        try:
            xl = pd.ExcelFile(path)
        except Exception as e:  # pragma: no cover
            if verbose:
                print(f"  [horarios] curso {curso_num}: lecture échouée ({e})")
            continue
        target = sheet_name if sheet_name in xl.sheet_names else None
        if target is None:
            for s in xl.sheet_names:
                if strip_accents(s) == strip_accents(sheet_name):
                    target = s
                    break
        if target is None:
            if verbose:
                print(f"  [horarios] curso {curso_num}: onglet '{sheet_name}' absent")
            continue
        df = xl.parse(target, header=None)
        before = sum(len(v) for v in grid.values())
        parse_horarios_sheet(df, curso_num, grid)
        after = sum(len(v) for v in grid.values())
        if verbose:
            n_tit = len([k for k in grid if k[1] == curso_num])
            print(f"  [horarios] curso {curso_num} ({os.path.basename(path)}): "
                  f"{n_tit} titulaciones, +{after - before} créneaux")

    return grid


def busy_slots_for(grid: dict, titulacion: str, curso_num: int) -> set:
    """
    Retourne l'ensemble des (day_idx, block_id) occupés pour une
    (titulación, année) donnée, en normalisant le code de titulación.
    """
    tit = normalize_titulacion(titulacion)
    key = (tit, int(curso_num)) if curso_num is not None else None
    slots = set()
    if key is not None and key in grid:
        slots.update(grid[key].keys())
    return slots


def grid_summary(grid: dict) -> pd.DataFrame:
    """Résumé lisible : une ligne par (titulación, curso) avec nb de créneaux."""
    rows = []
    for (tit, curso), slots in sorted(grid.items()):
        rows.append({
            "titulacion": tit,
            "curso": curso,
            "n_slots_ocupados": len(slots),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    g = load_occupancy_grid(verbose=True)
    print("\n=== Résumé grille d'occupation ===")
    print(grid_summary(g).to_string(index=False))
