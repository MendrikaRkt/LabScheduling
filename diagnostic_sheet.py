"""
diagnostic_sheet.py
===================

Rendu de la feuille Excel « Diagnostic & Remèdes ».

Cette feuille matérialise, pour le jury et l'établissement, la thèse centrale
du projet : un statut solveur « OPTIMAL » ne prouve PAS que la solution est
correcte. Le pré-traitement peut absorber une infaisabilité en déformant la
solution (groupes minuscules/solo, séances hors-période, sur-souscription,
surcharge professeur). Cette feuille LISTE ces anomalies détectées par
``diagnostics.audit_schedule``, les compte par NIVEAU × SEMESTRE, et affiche
pour chacune un REMÈDE PROPOSÉ et chiffré — jamais appliqué automatiquement.

Conception
----------
* Purement additive : n'altère aucune autre feuille ni la logique de génération.
* Read-only : consomme le dict produit par ``diagnostics.audit_schedule``.
* Contenu en FRANÇAIS (demande de l'utilisateur).
* Identité visuelle Loyola (marine #1B3A6F, or #FFCC00), pas de rouge/vert vif —
  le sens est toujours renforcé par un libellé texte explicite.

Utilisation
-----------
    from openpyxl import Workbook
    import diagnostics, diagnostic_sheet

    report = diagnostics.audit_schedule(rows)
    wb = Workbook()
    diagnostic_sheet.build_diagnostic_sheet(wb, report)
    wb.save("out.xlsx")
"""

from __future__ import annotations

from typing import Any, Dict, List

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# On réutilise la palette et les briques de style de validation_sheet pour
# garantir une cohérence visuelle parfaite entre les deux feuilles d'analyse.
from validation_sheet import (
    BAD, BAD_BG, BORDER, GOOD, GOOD_BG, GOLD, GREY_BG, NAVY, NAVY_DEEP,
    WARN, WARN_BG, WHITE, _plain_table, _section, _title,
)

import diagnostics as _dg


# English labels per anomaly type.
_TYPE_LABELS = {
    "tiny_group": "Under-sized group",
    "wrong_period": "Session outside period",
    "oversubscription": "Over-subscribed subject",
    "bottleneck": "Capacity bottleneck",
    "credit_overload": "Professor credit overload",
}

# English labels per severity + colours (text, background).
_SEV_LABELS = {
    _dg.SEV_CRITICAL: "Critical",
    _dg.SEV_WARNING: "Warning",
    _dg.SEV_INFO: "Info",
}
_SEV_COLORS = {
    _dg.SEV_CRITICAL: (BAD, BAD_BG),
    _dg.SEV_WARNING: (WARN, WARN_BG),
    _dg.SEV_INFO: (GOOD, GOOD_BG),
}


def _kpi_band(ws, row, report: Dict[str, Any]) -> int:
    """Bandeau de synthèse : total, critiques, groupes analysés, verdict."""
    n_total = report.get("n_total", 0)
    n_crit = report.get("n_critical", 0)
    n_groups = report.get("n_groups_analyzed", 0)
    healthy = report.get("healthy", n_total == 0)

    cells = [
        ("Anomalies detected", n_total,
         (GOOD if n_total == 0 else BAD), (GOOD_BG if n_total == 0 else BAD_BG)),
        ("Of which critical", n_crit,
         (GOOD if n_crit == 0 else BAD), (GOOD_BG if n_crit == 0 else BAD_BG)),
        ("Groups analysed", n_groups, NAVY_DEEP, GREY_BG),
        ("Verdict", "COMPLIANT" if healthy else "TO FIX",
         (GOOD if healthy else BAD), (GOOD_BG if healthy else BAD_BG)),
    ]
    for i, (label, value, fg, bg) in enumerate(cells):
        col = 1 + i
        lc = ws.cell(row=row, column=col, value=label)
        lc.font = Font(bold=True, size=9, color=NAVY_DEEP)
        lc.fill = PatternFill("solid", fgColor=GREY_BG)
        lc.alignment = Alignment(horizontal="center", vertical="center",
                                 wrap_text=True)
        lc.border = BORDER
        vc = ws.cell(row=row + 1, column=col, value=value)
        vc.font = Font(bold=True, size=18, color=fg)
        vc.fill = PatternFill("solid", fgColor=bg)
        vc.alignment = Alignment(horizontal="center", vertical="center")
        vc.border = BORDER
    ws.row_dimensions[row].height = 24
    ws.row_dimensions[row + 1].height = 34
    return row + 2


def build_diagnostic_sheet(workbook, report: Dict[str, Any],
                           sheet_title="Business Audit & Remedies"):
    """Build the « Business Audit & Remedies » sheet in *workbook*.

    Args:
        workbook: target openpyxl workbook.
        report: dict returned by ``diagnostics.audit_schedule``.
        sheet_title: worksheet tab name.
    """
    # Nettoie la feuille par défaut vide si présente.
    if "Sheet" in workbook.sheetnames and len(workbook.sheetnames) == 1:
        ws = workbook["Sheet"]
        ws.title = sheet_title
    else:
        ws = workbook.create_sheet(title=sheet_title)

    # Largeurs de colonnes (7 colonnes utiles).
    widths = [22, 10, 10, 26, 14, 40, 46]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    row = 1
    row = _title(ws, row,
                 "Business Audit & Remedies — Beyond the solver status",
                 ncols=7)

    # Explanatory banner (the project's core thesis).
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    intro = ws.cell(row=row, column=1, value=(
        "A solver status of \"OPTIMAL\" does NOT guarantee a COMPLIANT solution. "
        "Pre-processing can absorb an infeasibility by deforming the solution. "
        "This sheet lists the business anomalies detected and proposes a "
        "quantified remedy for each one (to be decided by the user, never "
        "applied automatically)."))
    intro.font = Font(size=10, italic=True, color=NAVY_DEEP)
    intro.alignment = Alignment(vertical="top", wrap_text=True, indent=1)
    ws.row_dimensions[row].height = 46
    row += 1
    row += 1

    # Bandeau KPI.
    row = _kpi_band(ws, row, report)
    row += 1

    # Cas sain : message et sortie anticipée.
    if report.get("healthy", report.get("n_total", 0) == 0):
        row = _section(ws, row, "Result", ncols=7)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
        c = ws.cell(row=row, column=1, value=(
            "No business anomaly detected: every group meets the minimum size "
            "and the expected period for its year level. The solution is "
            "compliant with the rules that were checked."))
        c.font = Font(size=11, color=NAVY_DEEP)
        c.fill = PatternFill("solid", fgColor=GOOD_BG)
        c.alignment = Alignment(vertical="center", wrap_text=True, indent=1)
        ws.row_dimensions[row].height = 40
        ws.freeze_panes = "A2"
        return ws

    # Summary by anomaly type.
    row = _section(ws, row, "Summary by anomaly type", ncols=7)
    by_type = report.get("by_type", {})
    type_rows = [
        [_TYPE_LABELS.get(k, k), v]
        for k, v in sorted(by_type.items(), key=lambda kv: -kv[1])
    ]
    row = _plain_table(ws, row, ["Anomaly type", "Count"], type_rows,
                       col_widths=[30, 12])
    row += 1

    # Reconciliation by year level × semester.
    row = _section(ws, row, "Breakdown by year level × semester", ncols=7)
    bls = report.get("by_level_semester", {})
    ls_rows = []
    for key in sorted(bls.keys()):
        d = bls[key]
        ls_rows.append([
            key,
            d.get("tiny_group", 0),
            d.get("wrong_period", 0),
            d.get("oversubscription", 0)
            + d.get("bottleneck", 0) + d.get("credit_overload", 0),
            d.get("total", 0),
        ])
    row = _plain_table(
        ws, row,
        ["Year level · Semester", "Under-sized\ngroups", "Outside\nperiod",
         "Other", "Total"],
        ls_rows, col_widths=[24, 12, 12, 12, 10])
    row += 1

    # Detailed anomalies + proposed remedies.
    row = _section(ws, row, "Detailed anomalies and proposed remedies",
                   ncols=7)

    headers = ["Level", "Sem.", "Group", "Subject", "Severity",
               "Anomaly", "Proposed remedy (quantified)"]
    for c, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=c, value=h)
        cell.font = Font(bold=True, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[row].height = 26
    row += 1

    for a in report.get("anomalies", []):
        sev = a.get("severity", _dg.SEV_INFO)
        fg, bg = _SEV_COLORS.get(sev, (NAVY_DEEP, GREY_BG))
        remedy = a.get("remedy", {}) or {}
        values = [
            a.get("level", ""),
            a.get("semester", ""),
            str(a.get("grupo", "")),
            a.get("subject", ""),
            _SEV_LABELS.get(sev, sev),
            a.get("detail", ""),
            remedy.get("text", ""),
        ]
        for c, val in enumerate(values, start=1):
            cell = ws.cell(row=row, column=c, value=val)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       indent=1)
            if c == 5:  # colonne sévérité colorée
                cell.font = Font(bold=True, color=fg)
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.alignment = Alignment(horizontal="center",
                                           vertical="center")
            elif c in (1, 4):
                cell.font = Font(bold=True, color=NAVY_DEEP)
        ws.row_dimensions[row].height = 42
        row += 1

    ws.freeze_panes = "A2"
    return ws
