"""Tests unitaires pour ``rebuild_student_constraints`` (TASK 1).

Couvre la conversion année→curso et la dérivation de ``student_busy`` à partir
d'une grille d'occupation synthétique (sans dépendre des vraies grilles Horarios).
"""

import rebuild_student_constraints as rsc


# ---------------------------------------------------------------------------
# ano_to_curso
# ---------------------------------------------------------------------------

def test_ano_to_curso_variants():
    assert rsc.ano_to_curso("Primero") == 1
    assert rsc.ano_to_curso("segundo") == 2
    assert rsc.ano_to_curso("3") == 3
    assert rsc.ano_to_curso("Cuarto") == 4


def test_ano_to_curso_unknown_and_nan():
    assert rsc.ano_to_curso(None) is None
    assert rsc.ano_to_curso("quinto") is None


# ---------------------------------------------------------------------------
# build_student_busy
# ---------------------------------------------------------------------------

def _grid():
    # (titulacion, curso) -> {(day_idx, block_id): course}
    return {
        ("GITIADE", 1): {(0, 1): "Física", (3, 1): "Química"},
        ("GITI", 2): {(1, 2): "Cálculo"},
    }


def test_build_student_busy_maps_slots():
    grid = _grid()
    year_map = {
        101: {("GITIADE", 1)},          # 2 créneaux
        102: {("GITI", 2)},             # 1 créneau
        103: set(),                     # année inconnue → aucun créneau
        104: {("XXXX", 1)},             # titulación absente de la grille
    }
    busy, stats = rsc.build_student_busy(grid, year_map)
    assert busy[101] == {(0, 1), (3, 1)}
    assert busy[102] == {(1, 2)}
    assert busy[103] == set()
    assert busy[104] == set()
    assert stats["students_total"] == 4
    assert stats["students_with_slots"] == 2
    assert stats["students_without_year"] == 1
    assert stats["total_busy_entries"] == 3


def test_build_student_busy_reports_missing_grid_keys():
    grid = _grid()
    year_map = {201: {("XXXX", 1)}}
    _busy, stats = rsc.build_student_busy(grid, year_map)
    assert ("XXXX", 1) in stats["missing_grid_keys"]
