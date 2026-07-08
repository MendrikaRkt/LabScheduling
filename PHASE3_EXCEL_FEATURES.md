# Phase 3 — Enhanced Excel Exports

Phase 3 adds a richer, analysis-oriented Excel export layer on top of the
validated Daniel-format exporters. It is **purely additive**: `excel_export.py`
and `excel_generator_core.py` are never modified, and the `standard` format
delegates straight to them so existing deliverables remain identical.

## What you get

1. **Color-coded group export** — one stable, colour-blind-safe colour per
   group (consistent across every sheet), a **Legend** sheet, conditional
   formatting for over-/under-subscribed groups, alternating row shading,
   Loyola-branded headers (navy `#003366` / gold `#FFCC00`), frozen panes,
   auto-filters, and cell comments (professor + room-capacity proxy).
2. **Five analysis sheets** —
   - **Room Utilization** (sessions/students per room, utilisation %, bar chart,
     conditional formatting `>=80%` green / `50-80%` amber / `<50%` red).
   - **Professor Workload** (sessions, subjects, groups, students, bar chart).
   - **Student Placement** (per-subject status with a global placement banner).
   - **Time Slot Analysis** (Days x Time-blocks heatmap + per-room breakdown).
   - **Quality Metrics** (KPIs from `reports/kpi_report.json` and solver runs
     from `reports/solver_stats.json`, with traffic-light status).
3. **Advanced filtering & formatting** — auto-filters, dropdown data-validation
   pickers (Semester / Subject / Professor / Room / Day / Block), workbook-level
   named ranges, and optional sheet protection that leaves filters usable.
4. **Template system** — branded `.xlsx` templates with `{{TOKEN}}`
   placeholders (`{{GROUP}}`, `{{PROFESSOR}}`, `{{ROOM}}`, `{{SUBJECT}}`,
   `{{SEMESTER}}`, `{{DAY}}`, `{{BLOCK}}`, `{{DATE}}`, `{{TITLE}}`), with
   discovery, validation and rendering.

## Formats

| Format | Description |
|--------|-------------|
| `standard` | Daniel-format workbooks (delegates to `excel_export.py`). Backward compatible. |
| `summary` | Overview + Groups + Legend + Student Placement + Quality Metrics. |
| `enhanced` | All sheets, all formatting (default). |
| `detailed` | All sheets + protected sheets (filters stay usable). |

## Using it from the UI

Open the **"Exports avances (classeurs enrichis)"** section at the bottom of the **Export** page in `app.py` (component `ui_advanced_exports.py`) in the
Streamlit app. Choose a perimeter (both semesters / S1 / S2), a format, a colour
scheme (Loyola / Default / Monochrome), tick the sheets and formatting options,
preview the data, then **Generer le classeur** and download. The lower section
renders a template from user-supplied values.

## Using it from code

```python
import export_manager as m

# Enhanced workbook for semester 1, Loyola palette.
res = m.export_with_format("enhanced", semester=1, color_scheme="loyola")
print(res["ok"], res["file"])

# Override individual sheets/formatting.
res = m.export_with_format(
    "enhanced", semester=None,
    overrides={"time_slot_analysis": False, "protect_sheets": True},
)

# Render a template.
res = m.render_template(
    "loyola_schedule_template.xlsx",
    {"TITLE": "Distribucion de Practicas", "SEMESTER": "1",
     "SUBJECT": "Fisica", "GROUP": "G1", "PROFESSOR": "Prof",
     "ROOM": "Ciencias Exp. I", "DAY": "Lunes", "BLOCK": "12:30-14:30"},
)
```

Lower-level building (no file I/O) is available via
`excel_export_enhanced.build_enhanced_workbook(...)`, which returns an openpyxl
`Workbook`.

## Configuration

`config/export_preferences.yaml` controls the default format, default colour
scheme, the templates directory, and per-format flag overrides. A missing or
invalid file falls back to built-in defaults, so the exporter always works.

## Group sizing thresholds

Mirrors `pipeline.py`: min = 7, preferred = 12, max = 15.

- **Optimal**: `7 <= students <= 15` (green `#009E73`)
- **Under-utilized**: `students < 7` (orange `#E69F00`)
- **Over-subscribed**: `students > 15` (vermillion `#D55E00`)

## Accessibility

Colours use a colour-blind-safe (Okabe-Ito derived) palette, and status is also
encoded by a text label and a fill pattern so meaning survives greyscale and
colour-blindness. Per-group colours are deterministic and stable across sheets.

## Regenerating the template

```bash
python templates/build_loyola_template.py
```

This rewrites `templates/loyola_schedule_template.xlsx` deterministically; the
generator is kept in the repo so the binary can be reviewed and rebuilt.

## Tests

`tests/test_excel_enhanced.py` and `tests/test_export_manager.py` add 52 tests
(colour helpers, thresholds, every sheet builder, charts, conditional
formatting, comments, data validation, named ranges, format resolution,
preferences, the `standard` delegation path, and the template engine). The full
suite passes at **174 tests**.
