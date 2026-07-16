"""Tests unitaires pour ``horarios_grid`` (TASK 1/2).

Couvre la normalisation des titulaciones, la conversion des libellés de
créneaux, le parsing d'une mini-grille « Horarios » synthétique et
``busy_slots_for``.
"""

import pandas as pd

import horarios_grid as hg


# ---------------------------------------------------------------------------
# normalize_titulacion
# ---------------------------------------------------------------------------

def test_normalize_titulacion_strips_year_suffix():
    assert hg.normalize_titulacion("GITIADE22") == "GITIADE"
    assert hg.normalize_titulacion("GITI ") == "GITI"
    assert hg.normalize_titulacion("giti13") == "GITI"


def test_normalize_titulacion_handles_none_and_nan():
    assert hg.normalize_titulacion(None) == ""
    assert hg.normalize_titulacion(float("nan")) == ""


# ---------------------------------------------------------------------------
# libellés de créneaux
# ---------------------------------------------------------------------------

def test_block_label_to_id_canonicalises():
    assert hg.block_label_to_id("08:30 - 10:30") == 1
    assert hg.block_label_to_id("8:30-10:30") == 1
    assert hg.block_label_to_id("inconnu") is None


def test_strip_accents():
    assert hg.strip_accents("Miércoles") == "miercoles"
    assert hg.strip_accents(None) == ""


# ---------------------------------------------------------------------------
# parse_horarios_sheet — mini-grille synthétique
# ---------------------------------------------------------------------------

def _synthetic_sheet():
    # Ligne d'en-tête : code titulación puis les 5 jours.
    # Lignes suivantes : libellé de créneau + cours par jour.
    return pd.DataFrame([
        ["GITIADE22", "Lunes", "Martes", "Miércoles", "Jueves", "Viernes"],
        ["08:30-10:30", "Física", "", "", "Química", ""],
        ["10:30-12:30", "", "Cálculo", "", "", ""],
    ])


def test_parse_horarios_sheet_builds_grid():
    grid = hg.parse_horarios_sheet(_synthetic_sheet(), curso_num=1)
    key = ("GITIADE", 1)
    assert key in grid
    # Lunes (day_idx 0), bloc 1 → Física
    assert grid[key][(0, 1)] == "Física"
    # Jueves (day_idx 3), bloc 1 → Química
    assert grid[key][(3, 1)] == "Química"
    # Martes (day_idx 1), bloc 2 → Cálculo
    assert grid[key][(1, 2)] == "Cálculo"


def test_busy_slots_for_returns_occupied_slots():
    grid = hg.parse_horarios_sheet(_synthetic_sheet(), curso_num=1)
    slots = hg.busy_slots_for(grid, "GITIADE22", 1)
    assert (0, 1) in slots
    assert (3, 1) in slots
    assert (1, 2) in slots
    # Année inexistante → vide
    assert hg.busy_slots_for(grid, "GITIADE22", 4) == set()


def test_grid_summary_dataframe():
    grid = hg.parse_horarios_sheet(_synthetic_sheet(), curso_num=1)
    summary = hg.grid_summary(grid)
    assert isinstance(summary, pd.DataFrame)
    assert "n_slots_ocupados" in summary.columns
    assert int(summary["n_slots_ocupados"].iloc[0]) == 3
