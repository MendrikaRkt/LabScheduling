# -*- mode: python ; coding: utf-8 -*-
"""
LabScheduling.spec — PyInstaller build spec for the Lab Scheduling desktop app.

Build (on Windows, in this folder):
    pyinstaller LabScheduling.spec --noconfirm

Produces dist/LabScheduling/LabScheduling.exe (one-folder build — recommended
for Streamlit, far more reliable than --onefile because Streamlit loads many
data files at runtime).

Streamlit is awkward to freeze: it loads static assets, version metadata, and
discovers submodules dynamically. We therefore collect ALL of streamlit plus
the metadata of its key dependencies, and ship the app's own .py files and
resource folders as data so the bundled `streamlit run app.py` can find them.
"""

from PyInstaller.utils.hooks import (
    collect_all,
    copy_metadata,
    collect_data_files,
    collect_submodules,
)

block_cipher = None

# ── Collect Streamlit in full (modules + data + metadata) ──
st_datas, st_binaries, st_hidden = collect_all("streamlit")

# ── Collect OR-Tools in full — CRITICAL ──
# OR-Tools ships native extension modules (cp_model_helper, etc.) plus the
# DLLs/.so they depend on. PyInstaller's static analysis misses these, causing
# "DLL load failed while importing cp_model_helper" at runtime. collect_all
# pulls the binaries, data files AND hidden submodules so the CP-SAT solver
# works in the packaged app.
ort_datas, ort_binaries, ort_hidden = collect_all("ortools")

# ── Metadata several libraries query at runtime via importlib.metadata ──
meta_pkgs = [
    "streamlit", "altair", "pandas", "numpy", "pyarrow",
    "ortools", "openpyxl", "pillow", "tornado", "watchdog",
    "gitpython", "rich", "click", "blinker", "cachetools", "psutil",
    "tenacity", "toml", "validators", "packaging",
]
datas = []
for pkg in meta_pkgs:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

# ── App source files + resources shipped as data ──
#   These are read by the launcher / Streamlit at runtime.
datas += [
    ("app.py", "."),
    ("pipeline.py", "."),
    ("reliability_metrics.py", "."),
    ("version_manager.py", "."),
    ("manual_edit.py", "."),
    ("persistence.py", "."),
    ("app_paths.py", "."),
    ("excel_export.py", "."),
    ("loyola_theme.py", "."),
    ("excel_generator_core.py", "."),
    ("update_manager.py", "."),
    ("config_verify.py", "."),
    ("VERSION.txt", "."),
]

# Resource folders (use a glob-friendly collect; missing folders are skipped).
#
# SECURITY: never ship student-identifying artefacts inside the .exe. The
# pipeline GENERATES these into the per-user workspace at runtime; if a dev ran
# the pipeline from the source tree, copies may linger under data_clean/ and
# would otherwise be swept into the bundle. We exclude them by name.
import os
_PII_FILES = {
    "student_directory.csv",   # hash -> REAL name map (must stay local only)
    "group_composition.csv",   # student-to-group rows
    "student_busy.csv",        # per-student busy slots (ids)
    "enrollment_pairs.csv",
}
for folder in ("assets", "config", "data_clean"):
    if os.path.isdir(folder):
        for root, _dirs, files in os.walk(folder):
            for fn in files:
                if fn in _PII_FILES:
                    print(f"[spec] SKIP (PII, not bundled): {os.path.join(root, fn)}")
                    continue
                full = os.path.join(root, fn)
                datas.append((full, root))

datas += st_datas
datas += ort_datas   # OR-Tools data files (proto descriptors, etc.)

# ── Hidden imports PyInstaller's static analysis tends to miss ──
hidden = list(st_hidden)
hidden += ort_hidden          # full OR-Tools submodule list
hidden += collect_submodules("ortools")
hidden += collect_submodules("altair")
hidden += [
    "pandas", "numpy", "pyarrow", "openpyxl", "PIL", "PIL.Image",
    "reliability_metrics", "pipeline", "version_manager",
    "persistence", "manual_edit", "app_paths", "excel_export",
    "excel_generator_core",
    "loyola_theme", "update_manager", "config_verify",
    "streamlit.runtime.scriptrunner.magic_funcs",
]

a = Analysis(
    ["run_app.py"],
    pathex=["."],
    binaries=st_binaries + ort_binaries,   # CRITICAL: OR-Tools native DLLs/.so
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LabScheduling",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # set True temporarily if you need to see tracebacks
    disable_windowed_traceback=False,
    icon="assets/app_icon.ico" if os.path.exists("assets/app_icon.ico") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="LabScheduling",
)
