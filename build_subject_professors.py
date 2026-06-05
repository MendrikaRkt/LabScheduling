#!/usr/bin/env python3
"""
build_subject_professors.py
===========================
Build data_clean/optimization/subject_professors.csv — the mapping
    subject (LAB_CONFIG key)  ->  eligible professor NAMES
used by the Excel "Vista profesor" sheet to show, for each lab session, the
professor(s) qualified to run it.

WHY A SEPARATE SCRIPT
---------------------
The optimization pipeline consumes only master_schedule.csv (a timetable). The
authoritative professor↔subject information lives in the official enrolment
report `informeDetalleGruposPorCurso` (its 'Actividad' + 'Docentes' columns).
This script converts that report into the small CSV the generator reads, the
same way build_professor_table.py produces subject_supervision.csv. Re-run it
whenever a new enrolment report is issued.

WHAT IT DOES
------------
1. Parses the report. The file is Excel-2003 SpreadsheetML (XML) saved with a
   .xls extension — NOT a binary .xls — so we read it as XML (xlrd/openpyxl
   would both fail). A genuine binary .xls or .xlsx is also handled via pandas.
2. Pulls LAB_CONFIG out of pipeline.py (keywords / keyword_exclude / semester /
   curso_num) WITHOUT importing the pipeline (brace-matched literal + eval with
   stubbed constants — no side effects, no heavy imports).
3. Matches each report row to a LAB_CONFIG subject by KEYWORD + SEMESTER, using
   the course year only as a tie-breaker. Year is deliberately NOT a hard filter
   because the report and LAB_CONFIG disagree on it for some subjects (e.g.
   Ingeniería de Control / Control de Máquinas / Estructuras are 'curso 4' in
   LAB_CONFIG but appear as Curso 3 in the report).
4. Writes subject,professors (names '; '-joined, de-duplicated, sorted).

USAGE
-----
    python build_subject_professors.py \
        --report informeDetalleGruposPorCurso.xls \
        --pipeline pipeline.py \
        --out data_clean/optimization/subject_professors.csv

All arguments have sensible defaults (report in CWD, pipeline.py in CWD, output
under data_clean/optimization/).
"""
from __future__ import annotations
import argparse, csv, os, re, sys
from collections import defaultdict


# ────────────────────────────────────────────────────────────
# LAB_CONFIG extraction (no pipeline import)
# ────────────────────────────────────────────────────────────
def load_lab_config(pipeline_path: str) -> dict:
    src = open(pipeline_path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")
    i = src.index("LAB_CONFIG = {")
    j = src.index("{", i)
    depth = 0
    end = None
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                end = k + 1
                break
    if end is None:
        raise ValueError("Could not locate the LAB_CONFIG literal in pipeline.py")
    literal = src[j:end]
    # Stub any UPPERCASE constants referenced inside the literal (group sizes etc.)
    stub = {name: 15 for name in set(re.findall(r"\b[A-Z_][A-Z0-9_]{3,}\b", literal))}
    cfg = eval(literal, stub)  # literal is a dict of dicts; safe given stubs
    return {
        k: {
            "curso_num": v.get("curso_num"),
            "semester": v.get("semester"),
            "keywords": [s.lower() for s in v.get("keywords", [])],
            "keyword_exclude": [s.lower() for s in v.get("keyword_exclude", [])],
        }
        for k, v in cfg.items()
    }


# ────────────────────────────────────────────────────────────
# Report reading: SpreadsheetML (XML) or real binary xls/xlsx
# ────────────────────────────────────────────────────────────
def read_report_rows(report_path: str) -> list[dict]:
    """Return a list of {column_name: value} dicts for the first worksheet."""
    head = open(report_path, "rb").read(4096)
    is_xml = head.lstrip()[:5] == b"<?xml" or b"urn:schemas-microsoft-com:office:spreadsheet" in head

    if is_xml:
        import xml.etree.ElementTree as ET
        NS = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}
        root = ET.parse(report_path).getroot()
        ws = root.find(".//ss:Worksheet", NS)
        if ws is None:
            raise ValueError("No worksheet found in SpreadsheetML report")
        out_rows = []
        for row in ws.findall(".//ss:Row", NS):
            col = 0
            cells = {}
            for cell in row.findall("ss:Cell", NS):
                idx = cell.get("{urn:schemas-microsoft-com:office:spreadsheet}Index")
                if idx:
                    col = int(idx) - 1
                data = cell.find("ss:Data", NS)
                cells[col] = data.text if data is not None else None
                col += 1
            out_rows.append(cells)
        if not out_rows:
            return []
        header = out_rows[0]
        ncols = (max(max(r) for r in out_rows if r) + 1) if any(out_rows) else 0
        names = [str(header.get(c, f"col{c}")).strip() for c in range(ncols)]
        return [{names[c]: r.get(c) for c in range(ncols)} for r in out_rows[1:]]

    # Genuine binary spreadsheet → pandas
    import pandas as pd
    engine = "xlrd" if report_path.lower().endswith(".xls") else None
    df = pd.read_excel(report_path, engine=engine, dtype=str)
    return df.to_dict("records")


def _col(row: dict, *candidates: str):
    """Case-insensitive column getter tolerant of accents/spacing."""
    norm = {re.sub(r"\s+", " ", str(k)).strip().lower(): k for k in row}
    for cand in candidates:
        key = norm.get(cand.lower())
        if key is not None:
            return row[key]
    return None


def split_profs(cell) -> list[str]:
    if not cell:
        return []
    out = []
    for chunk in str(cell).replace(";", ",").split(","):
        n = chunk.strip()
        if n and n.lower() != "nan":
            out.append(n)
    return out


# ────────────────────────────────────────────────────────────
# Matching
# ────────────────────────────────────────────────────────────
def build_mapping(rows: list[dict], cfg: dict):
    subj_profs = defaultdict(set)
    collisions = []
    for r in rows:
        act = str(_col(r, "Actividad") or "").lower()
        cuat = str(_col(r, "Cuat.", "Cuat", "Cuatrimestre") or "").upper()
        docentes = _col(r, "Docentes", "Docente")
        try:
            curso = int(str(_col(r, "Curso") or "").strip())
        except (ValueError, TypeError):
            curso = None
        if not act:
            continue
        sem = 1 if cuat.startswith("1C") else (2 if cuat.startswith("2C") else None)
        if sem is None:
            continue
        matches = [
            key for key, c in cfg.items()
            if c["semester"] == sem
            and any(kw in act for kw in c["keywords"])
            and not any(ex in act for ex in c["keyword_exclude"])
        ]
        if not matches:
            continue
        if len(matches) > 1 and curso is not None:
            narrowed = [k for k in matches if cfg[k]["curso_num"] == curso]
            if narrowed:
                matches = narrowed
        if len(matches) > 1:
            collisions.append((_col(r, "Actividad"), cuat, list(matches)))
        for key in matches:
            for p in split_profs(docentes):
                subj_profs[key].add(p)
    return subj_profs, collisions


# ────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build subject_professors.csv from the enrolment report.")
    ap.add_argument("--report", default="informeDetalleGruposPorCurso.xls")
    ap.add_argument("--pipeline", default="pipeline.py")
    ap.add_argument("--out", default="data_clean/optimization/subject_professors.csv")
    args = ap.parse_args(argv)

    if not os.path.exists(args.report):
        print(f"[ERROR] report not found: {args.report}", file=sys.stderr)
        return 2
    if not os.path.exists(args.pipeline):
        print(f"[ERROR] pipeline.py not found: {args.pipeline}", file=sys.stderr)
        return 2

    cfg = load_lab_config(args.pipeline)
    rows = read_report_rows(args.report)
    print(f"[info] report rows: {len(rows)} | LAB_CONFIG subjects: {len(cfg)}")

    subj_profs, collisions = build_mapping(rows, cfg)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    written, missing = 0, []
    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["subject", "professors"])
        for key in cfg:
            profs = sorted(subj_profs.get(key, []))
            if profs:
                w.writerow([key, "; ".join(profs)])
                written += 1
            else:
                missing.append(key)

    print(f"[ok] wrote {written}/{len(cfg)} subjects -> {args.out}")
    if missing:
        print(f"[warn] no professors matched for: {missing}")
        print("       (check the subject's LAB_CONFIG keywords against the report's 'Actividad' text)")
    if collisions:
        print("[warn] rows that matched more than one subject (kept in all):")
        for a, c, m in collisions:
            print(f"       {a!r} [{c}] -> {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())