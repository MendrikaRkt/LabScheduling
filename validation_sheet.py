"""
validation_sheet.py
====================

Render the final reliability report (from ``schedule_validation``) into a
styled Excel worksheet — the "Validación" tab — that is appended to every
generated workbook (Daniel format) and can also be exported on its own.

Design goals
------------
* Purely additive: it never touches the existing sheets or their logic; it
  only *adds* a "Validación" sheet to a workbook it is handed.
* Read-only with respect to the schedule: it consumes the report dict produced
  by :func:`schedule_validation.validate_schedule`.
* Content is in Spanish to match Daniel's other sheets (Horarios, Grupos
  alumnos, Vista profesor). Code and comments stay in English.
* Loyola visual identity (navy #1B3A6F, gold #FFCC00).

Usage
-----
    from openpyxl import Workbook
    from schedule_validation import validate_schedule
    import validation_sheet

    wb = Workbook()
    report = validate_schedule()
    validation_sheet.build_validation_sheet(wb, report)
    wb.save("out.xlsx")
"""

from __future__ import annotations

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ── Loyola palette ─────────────────────────────────────────────────────────
NAVY = "1B3A6F"
NAVY_DEEP = "0F2344"
GOLD = "FFCC00"
GOOD = "2E9E6B"
GOOD_BG = "E3F5EC"
WARN = "B8860B"
WARN_BG = "FBF3DC"
BAD = "C0392B"
BAD_BG = "FBE4E1"
GREY_BG = "F2F5FA"
WHITE = "FFFFFF"

_THIN = Side(style="thin", color="C7D2E4")
BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

# Spanish labels for the five checks + group sizing
CHECK_LABELS_ES = {
    "room_conflicts": "Conflictos de aula",
    "student_theory_conflicts": "Conflicto teoría-estudiante",
    "student_lab_double_booking": "Doble reserva de laboratorio (estudiante)",
    "professor_double_booking": "Doble asignación de profesor",
    "professor_busy": "Profesor ocupado (horario docente)",
    "group_sizing": "Tamaño de los grupos",
}
CHECK_KIND_ES = {"hard": "Restricción dura", "indicator": "Indicador"}
# Spanish detail text (the sheet matches Daniel's language). The validation
# module stores French detail; we localise it here for the Excel output.
CHECK_DETAILS_ES = {
    "room_conflicts": "Un aula física acoge un solo grupo por (semestre, semana, día, franja).",
    "student_theory_conflicts": "Ningún estudiante en laboratorio sobre una franja de clase teórica ocupada (mismo semestre).",
    "student_lab_double_booking": "Ningún estudiante con dos sesiones de laboratorio en la misma (semestre, semana, día, franja).",
    "professor_double_booking": "Indicador (asignación posterior a la optimización, no restringida por el solver): profesor sin doble sesión en la misma (semestre, semana, día, franja).",
    "professor_busy": "Indicador (asignación posterior a la optimización): sesión sobre una franja de clase teórica del profesor (mismo semestre, salvo la hora sustituida).",
    "group_sizing": "Tamaño de grupo dentro de la política (mín. 7 / preferido 12 / máx. 15).",
}
STATUS_ES = {
    "PASS": "APTO",
    "WARN": "APTO CON AVISOS",
    "FAIL": "NO APTO",
    "NO_DATA": "SIN DATOS",
}


def _title(ws, row, text, ncols=6):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(name="Calibri", size=16, bold=True, color=WHITE)
    c.fill = PatternFill("solid", fgColor=NAVY)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 30
    return row + 1


def _section(ws, row, text, ncols=6):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.font = Font(name="Calibri", size=12, bold=True, color=NAVY_DEEP)
    c.fill = PatternFill("solid", fgColor=GOLD)
    c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[row].height = 22
    return row + 1


def _kv(ws, row, key, value, key_col=1, val_col=2, val_span=5):
    kc = ws.cell(row=row, column=key_col, value=key)
    kc.font = Font(bold=True, color=NAVY_DEEP)
    kc.fill = PatternFill("solid", fgColor=GREY_BG)
    kc.alignment = Alignment(vertical="center", indent=1)
    kc.border = BORDER
    if val_span > 1:
        ws.merge_cells(start_row=row, start_column=val_col,
                       end_row=row, end_column=val_col + val_span - 1)
    vc = ws.cell(row=row, column=val_col, value=value)
    vc.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
    vc.border = BORDER
    for col in range(val_col, val_col + val_span):
        ws.cell(row=row, column=col).border = BORDER
    return row + 1


def _status_colors(status):
    return {
        "PASS": (GOOD, GOOD_BG),
        "WARN": (WARN, WARN_BG),
        "FAIL": (BAD, BAD_BG),
        "NO_DATA": (WARN, WARN_BG),
    }.get(status, (WARN, WARN_BG))


def build_validation_sheet(workbook, report, sheet_title="Validación"):
    """Append a styled 'Validación' sheet built from a validation *report*.

    Parameters
    ----------
    workbook : openpyxl.Workbook
    report   : dict returned by schedule_validation.validate_schedule()
    sheet_title : str
    """
    ws = workbook.create_sheet(sheet_title)
    ws.sheet_view.showGridLines = False
    widths = [34, 20, 16, 16, 16, 22]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row = 1
    row = _title(ws, row, "Validación y fiabilidad de la planificación")
    row += 1

    # ── Global verdict ─────────────────────────────────────────────────
    status = report.get("status", "NO_DATA")
    fg, bg = _status_colors(status)
    ws.merge_cells(start_row=row, start_column=1, end_row=row + 1, end_column=2)
    v = ws.cell(row=row, column=1, value=STATUS_ES.get(status, status))
    v.font = Font(size=20, bold=True, color=WHITE)
    v.fill = PatternFill("solid", fgColor=fg)
    v.alignment = Alignment(horizontal="center", vertical="center")
    for rr in (row, row + 1):
        for cc in (1, 2):
            ws.cell(row=rr, column=cc).fill = PatternFill("solid", fgColor=fg)

    score = report.get("reliability_score", 0.0)
    ws.merge_cells(start_row=row, start_column=3, end_row=row + 1, end_column=4)
    sc = ws.cell(row=row, column=3, value=f"{score:.1f} / 100")
    sc.font = Font(size=20, bold=True, color=NAVY_DEEP)
    sc.fill = PatternFill("solid", fgColor=bg)
    sc.alignment = Alignment(horizontal="center", vertical="center")
    for rr in (row, row + 1):
        for cc in (3, 4):
            ws.cell(row=rr, column=cc).fill = PatternFill("solid", fgColor=bg)
    lbl = ws.cell(row=row, column=5, value="Índice de fiabilidad")
    lbl.font = Font(size=10, italic=True, color=NAVY_DEEP)
    ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=6)
    solver = report.get("solver", {})
    slv = ws.cell(row=row + 1, column=5,
                  value=f"Solver: {solver.get('status', 'N/D')}")
    slv.font = Font(size=10, bold=True, color=NAVY_DEEP)
    ws.merge_cells(start_row=row + 1, start_column=5, end_row=row + 1, end_column=6)
    ws.row_dimensions[row].height = 24
    ws.row_dimensions[row + 1].height = 24
    row += 3

    # ── Key counts ─────────────────────────────────────────────────────
    row = _section(ws, row, "Resumen de la planificación")
    counts = report.get("counts", {})
    row = _kv(ws, row, "Sesiones de laboratorio", counts.get("sessions", 0))
    row = _kv(ws, row, "Grupos de prácticas", counts.get("groups", 0))
    row = _kv(ws, row, "Asignaturas", counts.get("subjects", 0))
    row = _kv(ws, row, "Semestres", counts.get("semesters", 0))
    row = _kv(ws, row, "Estudiantes implicados", counts.get("students", 0))
    row += 1

    # ── Checks table ───────────────────────────────────────────────────
    row = _section(ws, row, "Controles de conflicto")
    headers = ["Control", "Tipo", "Estado", "Conflictos",
               "Afectados / Total", "Detalle"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font = Font(bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 24
    row += 1

    checks = report.get("checks", {})
    order = ["room_conflicts", "student_theory_conflicts",
             "student_lab_double_booking", "professor_double_booking",
             "professor_busy", "group_sizing"]
    for name in order:
        chk = checks.get(name)
        if not chk:
            continue
        checkable = chk.get("checkable", True)
        passed = chk.get("passed", True)
        kind = chk.get("kind") or ("hard" if name != "group_sizing" else "indicator")
        if not checkable:
            state, sfg, sbg = "N/D", WARN, WARN_BG
        elif passed:
            state, sfg, sbg = "OK", GOOD, GOOD_BG
        elif kind == "indicator":
            state, sfg, sbg = "AVISO", WARN, WARN_BG
        else:
            state, sfg, sbg = "CONFLICTO", BAD, BAD_BG
        affected = chk.get("affected")
        total = chk.get("total")
        aff_total = (f"{affected} / {total}"
                     if affected is not None and total is not None else "—")
        values = [
            CHECK_LABELS_ES.get(name, name),
            CHECK_KIND_ES.get(kind, kind),
            state,
            chk.get("count", 0),
            aff_total,
            CHECK_DETAILS_ES.get(name, chk.get("detail", "")),
        ]
        for c, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=c, value=val)
            cell.border = BORDER
            cell.alignment = Alignment(
                vertical="center",
                horizontal="center" if c in (2, 3, 4, 5) else "left",
                wrap_text=(c == 6), indent=0 if c in (2, 3, 4, 5) else 1)
            if c == 3:
                cell.font = Font(bold=True, color=sfg)
                cell.fill = PatternFill("solid", fgColor=sbg)
        ws.row_dimensions[row].height = 30
        row += 1
    row += 1

    # ── Reliability formula ────────────────────────────────────────────
    row = _section(ws, row, "Fórmula del índice de fiabilidad")
    formula_es = (
        "índice = 100 × Σ[ peso × (1 − entidades_en_conflicto / entidades_totales) ] "
        "/ Σ pesos × (1.0 si solver OPTIMAL/FACTIBLE, en caso contrario 0.9). "
        "Restricciones duras y pesos: conflictos de aula 40, "
        "conflicto teoría-estudiante 30, doble reserva de laboratorio 30. "
        "Estado: APTO si no hay violación dura; APTO CON AVISOS si el residuo ≤ 1 % "
        "de las entidades o hay indicadores señalados; NO APTO si > 1 %. "
        "Los controles de profesor (doble asignación, profesor ocupado) son "
        "INDICADORES de calidad — la asignación docente se realiza después de la "
        "optimización, fuera del modelo CP-SAT; bajan el estado a AVISO pero nunca "
        "a NO APTO."
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row + 2, end_column=6)
    fcell = ws.cell(row=row, column=1, value=formula_es)
    fcell.font = Font(size=10, color=NAVY_DEEP)
    fcell.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
    for rr in range(row, row + 3):
        for cc in range(1, 7):
            ws.cell(row=rr, column=cc).border = BORDER
    row += 4

    # ── Teacher load (top entries) ─────────────────────────────────────
    teacher_load = report.get("teacher_load", [])
    if teacher_load:
        row = _section(ws, row, "Carga docente (sesiones por profesor)")
        thdr = ["Profesor", "Sesiones", "Grupos", "Asignaturas"]
        for c, h in enumerate(thdr, start=1):
            cell = ws.cell(row=row, column=c, value=h)
            cell.font = Font(bold=True, color=WHITE)
            cell.fill = PatternFill("solid", fgColor=NAVY)
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER
        ws.merge_cells(start_row=row, start_column=4, end_row=row, end_column=6)
        row += 1
        for entry in teacher_load[:25]:
            pc = ws.cell(row=row, column=1, value=entry.get("professor", ""))
            pc.border = BORDER
            pc.alignment = Alignment(vertical="center", indent=1)
            for col, key in ((2, "sessions"), (3, "groups")):
                cc = ws.cell(row=row, column=col, value=entry.get(key, 0))
                cc.alignment = Alignment(horizontal="center")
                cc.border = BORDER
            subj = entry.get("subjects", 0)
            if isinstance(subj, list):
                subj = ", ".join(subj)
            ws.merge_cells(start_row=row, start_column=4, end_row=row, end_column=6)
            scell = ws.cell(row=row, column=4, value=subj)
            scell.alignment = Alignment(horizontal="center", vertical="center",
                                        wrap_text=True)
            for cc in range(4, 7):
                ws.cell(row=row, column=cc).border = BORDER
            row += 1
        row += 1

    # ── Examples of residual conflicts ─────────────────────────────────
    problem_checks = [
        (name, chk) for name, chk in checks.items()
        if chk.get("examples") and not chk.get("passed", True)
    ]
    if problem_checks:
        row = _section(ws, row, "Ejemplos de conflictos residuales")
        for name, chk in problem_checks:
            hc = ws.cell(row=row, column=1,
                         value=CHECK_LABELS_ES.get(name, name))
            hc.font = Font(bold=True, color=NAVY_DEEP)
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
            row += 1
            for ex in chk.get("examples", [])[:10]:
                txt = "; ".join(f"{k}={v}" for k, v in ex.items())
                ec = ws.cell(row=row, column=1, value=txt)
                ec.font = Font(size=9, color="333333")
                ec.alignment = Alignment(wrap_text=True, indent=1)
                ws.merge_cells(start_row=row, start_column=1,
                               end_row=row, end_column=6)
                row += 1
            row += 1

    ws.sheet_view.showGridLines = False
    return ws
