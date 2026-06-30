"""Tests for the Excel reader: subject matcher + P/TP credit parsing."""
import openpyxl
import pytest

from infrastructure.config.config_loader import get_settings
from infrastructure.excel.excel_reader import (
    COL_ASIGNATURA,
    COL_CREDITOS_P,
    COL_CREDITOS_T,
    COL_CURSO,
    COL_SEMESTRE,
    ExcelReader,
    ProfessorAssignment,
    SubjectMatcher,
    _normalize,
)


# --- SubjectMatcher ----------------------------------------------------------
def test_matcher_from_settings_basic():
    m = SubjectMatcher.from_settings(get_settings())
    assert m.match("Física I", semester=1) == "S1_Física"
    assert m.match("Física II", semester=2) == "S2_Física II"
    assert m.match("Química General", semester=1) == "S1_Química"


def test_matcher_keyword_exclude():
    # "Física II" must NOT match S1_Física (excluded)
    m = SubjectMatcher.from_settings(get_settings())
    assert m.match("Física II", semester=2) != "S1_Física"


def test_matcher_semester_disambiguation():
    m = SubjectMatcher.from_settings(get_settings())
    # Without the right semester, Física II must not be returned for S1
    assert m.match("Mecanismos y Elementos de Máquinas", semester=1) == "S1_Mecanismos"


def test_matcher_returns_none_for_unknown():
    m = SubjectMatcher.from_settings(get_settings())
    assert m.match("Asignatura Inexistente XYZ") is None


def test_normalize_strips_accents():
    assert _normalize("  Física  II ") == "fisica ii"


# --- Fixture: small synthetic workbook ---------------------------------------
def _make_workbook(tmp_path):
    """Create a mini workbook reproducing the 'Asignacion docente' structure."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Asignacion docente"
    # header row (ignored by header=None but filled for realism)
    ws.append(["h"] * 80)
    ncols = 80

    def make_row(asig, curso, sem, cred_t, cred_p, profs):
        row = [None] * ncols
        row[COL_ASIGNATURA] = asig
        row[COL_CURSO] = curso
        row[COL_SEMESTRE] = sem
        row[COL_CREDITOS_T] = cred_t
        row[COL_CREDITOS_P] = cred_p
        # secondary columns (full names): 68-79
        bis = [(68, 69, 70), (71, 72, 73), (74, 75, 76), (77, 78, 79)]
        for (nc, cc, tc), (name, cr, tp) in zip(bis, profs):
            row[nc], row[cc], row[tc] = name, cr, tp
        return row

    # Física I: 2 teachers in pure practice (P)
    ws.append(make_row("Física I", 1, 1, 6, 5,
                    [("Prof A", 3, "P"), ("Prof B", 2, "P")]))
    # Robótica: 2 teachers in TP (theory+practice combined), P ratio=5/(6+5)
    ws.append(make_row("Robótica y Automatización", 3, 1, 6, 5,
                    [("Prof C", 6, "TP"), ("Prof D", 5, "TP")]))
    # A pure-theory subject (must be ignored for P credits)
    ws.append(make_row("Álgebra", 1, 1, 6, 0, [("Prof E", 6, "T")]))

    path = tmp_path / "mini.xlsx"
    wb.save(path)
    return str(path)


def test_read_assignments_pure_practice(tmp_path):
    path = _make_workbook(tmp_path)
    reader = ExcelReader(sessions_per_credit=5)
    assignments = reader.read_assignments(path)
    fisica = [a for a in assignments if a.subject_label == "Física I"]
    assert len(fisica) == 2
    by_prof = {a.professor: a for a in fisica}
    assert by_prof["Prof A"].practice_credits == 3
    assert by_prof["Prof A"].expected_sessions == 15
    assert by_prof["Prof B"].expected_sessions == 10


def test_read_assignments_tp_split(tmp_path):
    path = _make_workbook(tmp_path)
    reader = ExcelReader(sessions_per_credit=5)
    assignments = reader.read_assignments(path)
    robo = {a.professor: a for a in assignments
            if a.subject_label == "Robótica y Automatización"}
    # P ratio = 5/(6+5) = 0.4545 ; Prof C: 6 * 0.4545 ~ 2.727
    assert robo["Prof C"].practice_credits == pytest.approx(2.727, abs=0.01)
    assert robo["Prof D"].practice_credits == pytest.approx(2.273, abs=0.01)
    # conservation: sum of P credits ~ P credits of the row (5)
    total = sum(a.practice_credits for a in robo.values())
    assert total == pytest.approx(5.0, abs=0.01)


def test_read_assignments_skips_theory(tmp_path):
    path = _make_workbook(tmp_path)
    reader = ExcelReader(sessions_per_credit=5)
    assignments = reader.read_assignments(path)
    assert all(a.subject_label != "Álgebra" for a in assignments)


def test_read_professor_credits_aggregates(tmp_path):
    path = _make_workbook(tmp_path)
    reader = ExcelReader(sessions_per_credit=5)
    profs = reader.read_professor_credits(path)
    names = {p.name for p in profs}
    assert "Prof A" in names
    assert "Prof E" not in names  # pure theory -> no P credits
    prof_a = next(p for p in profs if p.name == "Prof A")
    assert prof_a.practice_credits("Física I") == 3


def test_read_missing_file_raises():
    reader = ExcelReader()
    with pytest.raises(FileNotFoundError):
        reader.read_assignments("/no/such/file.xlsx")
