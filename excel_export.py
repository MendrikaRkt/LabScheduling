"""
excel_export.py — In-process generation of Daniel-format Excel files.

WHY THIS EXISTS
---------------
The app used to generate the S1/S2 deliverables by launching external scripts
with `subprocess.run([sys.executable, script])`. That works from source but
BREAKS in the packaged .exe, because there `sys.executable` is
LabScheduling.exe itself — so clicking "Generate" relaunched the whole app in a
new window instead of running the generator (the "new page" symptom).

This module instead imports the generator logic and calls it directly,
in-process. It also routes every file path through app_paths so the generated
workbooks land in the writable workspace, both from source and when frozen.

PUBLIC API
----------
    generate_semester(semester:int) -> dict   # 1 or 2
    generate_all() -> dict
    list_generated_files() -> list[str]

Each returns a small result dict: {ok, files:[...], log:str, error:str|None}.
"""

from __future__ import annotations

import io
import os
import sys
import importlib.util
from contextlib import redirect_stdout
from datetime import datetime

import app_paths


# ────────────────────────────────────────────────────────────
# Level definitions per semester (subjects grouped by year)
# Derived from the pipeline's LAB_CONFIG (curso_num) and Daniel's reference.
# ────────────────────────────────────────────────────────────
LEVELS_S1 = {
    1: {
        "label": "Primero",
        "subjects": ["S1_Física", "S1_Química"],
        "programs": ["IOI", "AERO", "IMR", "GITI", "MAT", "GITIADE", "IBIO"],
        "file": "Distribucion_Practicas_AUTO.xlsx",
        "naming": "number",
        "single": True,
    },
    2: {
        "label": "Segundo",
        "subjects": ["S1_Electrotecnia", "S1_Mecanismos", "S1_Termodinámica"],
        "programs": ["IOI", "IMR", "GITI", "GITIADE22"],
        "file": "Distribucion_Practicas_segundocurso_AUTO.xlsx",
        "naming": "letter",
        "single": False,
    },
    3: {
        "label": "Tercero",
        "subjects": [
            "S1_Tecnologías de Fabricación",
            "S1_Robótica y Automatización",
            "S1_Automatización Industrial",
        ],
        "programs": ["IOI", "IMR", "GITI", "GITIADE22", "PIIA"],
        "file": "Distribucion_Practicas_tercercurso_AUTO.xlsx",
        "naming": "letter",
        "single": False,
    },
}

LEVELS_S2 = {
    1: {
        "label": "Primero",
        "subjects": ["S2_Física II", "S2_Tecnología Medio Ambiente"],
        "programs": ["IOI", "AERO", "IMR", "GITI", "MAT", "GITIADE", "IBIO"],
        "file": "Distribucion_Practicas_AUTO.xlsx",
        "naming": "number",
        "single": True,
    },
    2: {
        "label": "Segundo",
        "subjects": [
            "S2_Resistencia de Materiales",
            "S2_Mecánica de Fluidos",
            "S2_Regulación Automática",
            "S2_Tecnología Electrónica",
            "S2_Electrónica y Automática",
            "S2_Informática y Com. Industriales",
            "S2_Métodos Numéricos",
            "S2_Modelado de Sistemas",
            "S2_Automatic Control",
        ],
        "programs": ["IOI", "IMR", "GITI", "GITIADE22"],
        "file": "Distribucion_Practicas_segundocurso_AUTO.xlsx",
        "naming": "letter",
        "single": False,
    },
    # NOTE: these three subjects are 3rd-year, 2nd-semester (confirmed against the
    # enrolment report — 'Ingeniería de Control', 'Control de Máquinas' and
    # 'Estructuras' are Curso 3 / 6º Semestre, NOT 4th year). They therefore
    # belong to "Tercero / Segundo semestre", giving 3rd year its second-semester
    # file. There is no 4th-year ("Cuarto") lab, so that folder is not produced.
    3: {
        "label": "Tercero",
        "subjects": [
            "S2_Ingeniería de Control",
            "S2_Control de Máquinas",
            "S2_Estructuras",
        ],
        "programs": ["IOI", "IMR", "GITI", "GITIADE22", "PIIA"],
        "file": "Distribucion_Practicas_tercercurso_AUTO.xlsx",
        "naming": "letter",
        "single": False,
    },
}

SEMESTER_FOLDER = {1: "Primer semestre", 2: "Segundo semestre"}


# ────────────────────────────────────────────────────────────
# Load the generator module (the validated openpyxl formatter)
# ────────────────────────────────────────────────────────────
_GEN_CACHE = None


def _load_generator():
    """Import the standalone Excel formatter module, once.

    Prefers the bundled standalone core (excel_generator_core.py). Falls back to
    the legacy 09_generate_exact_format_S1.py only if the core is absent, so the
    app keeps working whether or not the old scripts are present.
    """
    global _GEN_CACHE
    if _GEN_CACHE is not None:
        return _GEN_CACHE

    # 1) Preferred: the self-contained core module
    gen_file = app_paths.resolve_existing("excel_generator_core.py")
    # 2) Fallback: the legacy script (kept for backward compatibility)
    if gen_file is None:
        gen_file = app_paths.resolve_existing("09_generate_exact_format_S1.py")
    if gen_file is None:
        raise FileNotFoundError(
            "Excel generator module not found "
            "(expected excel_generator_core.py in the application files)."
        )

    spec = importlib.util.spec_from_file_location("_excel_gen_core", gen_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # The generator declares relative path constants at module level
    # ('outputs/...', 'config/...'). Re-point them at the writable workspace so
    # that, in the packaged .exe, config/user_config.json is read from the right
    # place and any incidental writes land in the workspace, not in a read-only
    # bundle dir. The build_* functions we call take DataFrames as arguments and
    # don't read files, but apply_user_config_overrides() reads USER_CONFIG_PATH.
    for const, rel in (
        ("SCHEDULE_CSV_PATH", "outputs/optimization/optimized_schedule_v5.csv"),
        ("GROUP_COMPOSITION_PATH", "outputs/optimization/group_composition.csv"),
        ("MASTER_SCHEDULE_PATH", "data_clean/master_schedule.csv"),
        ("SUPERVISION_PATH", "data_clean/optimization/subject_supervision.csv"),
        ("SUBJECT_PROFESSORS_PATH", "data_clean/optimization/subject_professors.csv"),
        ("USER_CONFIG_PATH", "config/user_config.json"),
        ("OUTPUT_BASE_DIR", "outputs/optimization/Curso_2025_2026"),
    ):
        if hasattr(mod, const):
            existing = app_paths.resolve_existing(rel)
            setattr(mod, const, existing or app_paths.workspace_path(rel))

    _GEN_CACHE = mod
    return mod


# ────────────────────────────────────────────────────────────
# Core: build all level workbooks for one semester
# ────────────────────────────────────────────────────────────
def _build_semester(gen, semester: int, levels: dict) -> list[str]:
    """Replicates the generator's main() loop, parameterised by semester,
    routing all paths through app_paths. Returns list of saved file paths.
    """
    import pandas as pd
    from openpyxl import Workbook

    sched_path = app_paths.resolve_existing(
        "outputs/optimization/optimized_schedule_v5.csv"
    )
    comp_path = app_paths.resolve_existing(
        "outputs/optimization/group_composition.csv"
    )
    master_path = app_paths.resolve_existing("data_clean/master_schedule.csv")

    if not sched_path:
        raise FileNotFoundError(
            "optimized_schedule_v5.csv not found — run the optimization first."
        )

    full_schedule = pd.read_csv(sched_path)
    sched = full_schedule[full_schedule["semester"] == semester].copy()
    print(f"  [OK] Schedule S{semester}: {len(sched)} sessions")

    # Groups
    student_id_column = "student_hash"
    groups = pd.DataFrame()
    if comp_path:
        all_groups = pd.read_csv(comp_path)
        subjects_clean = []
        for lvl in levels.values():
            subjects_clean.extend(
                [gen.strip_semester_prefix(s) for s in lvl["subjects"]]
            )
        groups = all_groups[all_groups["subject"].isin(subjects_clean)].copy()
        if len(groups):
            groups["grupo"] = groups["grupo"].astype(int)
        student_id_column = (
            "student_name" if "student_name" in groups.columns else "student_hash"
        )
        print(f"  [OK] Groups S{semester}: {len(groups)} entries")

    master_df = None
    if master_path:
        master_df = pd.read_csv(master_path, low_memory=False)
        print(f"  [OK] Master: {len(master_df)} rows")

    out_base = app_paths.workspace_path("outputs", "optimization", "Curso_2025_2026")
    saved = []
    name_map = _load_name_map()  # hash -> real name (local only); empty when names already present

    # Crédits de laboratoire (P) par professeur/matière — chargés UNE SEULE FOIS
    # par semestre (lecture de l'Asignación), puis réutilisés pour chaque niveau
    # afin d'alimenter la nouvelle feuille « Vue Professeur » (Partie 1).
    vp_credits, vp_names = ({}, {})
    if hasattr(gen, "_load_professor_lab_credits"):
        try:
            vp_credits, vp_names = gen._load_professor_lab_credits()
        except Exception as _e:
            print(f"  [WARN] Teacher View: credits unavailable ({_e})")

    for level_num, level_config in levels.items():
        subjects = level_config["subjects"]
        programs = level_config["programs"]

        level_schedule = sched[sched["subject"].isin(subjects)]
        if len(level_schedule) == 0:
            print(f"    [WARN] {level_config['label']}: no sessions, skipped")
            continue

        program_timetable = gen.build_program_timetable(master_df, programs, level_num)

        if len(groups) > 0:
            level_groups = groups[
                groups["subject"].isin(
                    [gen.strip_semester_prefix(s) for s in subjects]
                )
            ]
        else:
            level_groups = pd.DataFrame()

        wb = Workbook()
        wb.remove(wb.active)

        gen.build_grupos_sheet(
            wb, level_groups, subjects,
            level_config["naming"], level_config["single"],
            name_map=name_map,
        )
        gen.build_vista_profesor_sheet(wb, level_schedule, subjects)

        # NOUVELLE feuille consolidée centrée professeur (Partie 1).
        if hasattr(gen, "build_vue_professeur_consolidada_sheet"):
            gen.build_vue_professeur_consolidada_sheet(
                wb, level_schedule, subjects,
                credits_by_subject=vp_credits, names_by_subject=vp_names,
            )

        folder = os.path.join(out_base, level_config["label"], SEMESTER_FOLDER[semester])
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, level_config["file"])
        wb.save(out_path)
        saved.append(out_path)
        print(f"    [SAVED] {out_path}")

    return saved


# ────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────
def _load_name_map() -> dict:
    """Local hash->real-name map from student_directory.csv (workspace only).

    Lets the Excel show Daniel's real names even when the optimization outputs
    are anonymised (INCLUDE_REAL_NAMES=False in pipeline.py). This directory
    file lives in the workspace and must NEVER be embedded in the .exe or synced.
    """
    p = app_paths.resolve_existing("outputs/optimization/student_directory.csv")
    if not p:
        return {}
    try:
        import pandas as pd
        d = pd.read_csv(p, dtype=str)
        if "student_hash" in d.columns and "student_name" in d.columns:
            return dict(zip(d["student_hash"], d["student_name"]))
    except Exception:
        pass
    return {}


def generate_semester(semester: int) -> dict:
    """Generate all level workbooks for the given semester (1 or 2)."""
    levels = LEVELS_S1 if semester == 1 else LEVELS_S2
    buf = io.StringIO()
    try:
        gen = _load_generator()
        # Apply user config overrides (week counts etc.) if the generator
        # exposes that bridge — keeps Excel consistent with the UI settings.
        try:
            if hasattr(gen, "apply_user_config_overrides"):
                gen.apply_user_config_overrides()
        except Exception:
            pass
        with redirect_stdout(buf):
            files = _build_semester(gen, semester, levels)
        return {"ok": True, "files": files, "log": buf.getvalue(), "error": None}
    except Exception as e:
        import traceback, re
        _tb = traceback.format_exc()
        _tb = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[email]", _tb)
        _tb = re.sub(r"\b\d{6,}\b", "[id]", _tb)
        return {
            "ok": False, "files": [], "error": str(e),
            "log": buf.getvalue() + "\n" + _tb,
        }


def generate_all() -> dict:
    """Generate both semesters; returns a merged result."""
    r1 = generate_semester(1)
    r2 = generate_semester(2)
    return {
        "ok": r1["ok"] and r2["ok"],
        "files": r1["files"] + r2["files"],
        "log": f"━━ S1 ━━\n{r1['log']}\n━━ S2 ━━\n{r2['log']}",
        "error": "; ".join(x for x in (r1["error"], r2["error"]) if x) or None,
    }


def list_generated_files() -> list[str]:
    """All .xlsx currently present under the Curso_2025_2026 workspace tree."""
    root = app_paths.workspace_path("outputs", "optimization", "Curso_2025_2026")
    found = []
    if os.path.isdir(root):
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                if f.lower().endswith(".xlsx"):
                    found.append(os.path.join(dirpath, f))
    return sorted(found)