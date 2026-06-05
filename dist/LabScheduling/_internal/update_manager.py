"""
update_manager.py — Lightweight patch/update system for the packaged app.

TWO UPDATE CHANNELS
-------------------
The app ships as a PyInstaller bundle, so the Python modules live read-only
inside the .exe. Rebuilding + reinstalling for every small fix is heavy. This
module provides a light alternative AND coexists with full reinstalls.

  Channel A — Python patches (this module):
      A patch is a .zip containing newer .py files (app.py, pipeline_v5.py,
      excel_export.py, …) plus a small patch.json manifest. The user applies
      it from the app's "Updates" page (or drops it in the patches folder).
      On startup the app prepends the patch dir to sys.path, so the patched
      modules SHADOW the bundled ones — no rebuild, no admin rights.

  Channel B — Full installer:
      For major releases (or when Python / native libs change), ship a new
      LabScheduling_Setup_vX.Y.Z.exe. Because the Inno Setup AppId is constant,
      it upgrades in place over the previous install. This module only reports
      the version; it does not perform the .exe install.

PATCH LAYOUT
------------
    <workspace_parent>/patches/
        active/                 ← highest-priority .py overrides (on sys.path)
        applied.json            ← record of which patches were applied
    A patch .zip contains:
        patch.json              ← {"version":"1.0.1","min_app":"1.0.0","notes":"…"}
        *.py                    ← files to overlay into patches/active/

VERSIONING
----------
The base app version is read from a bundled VERSION.txt (written at build time).
The effective version is max(base, highest applied patch).
"""

from __future__ import annotations

import os
import re
import json
import zipfile
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

import app_paths

BASE_VERSION_FILE = "VERSION.txt"
DEFAULT_BASE_VERSION = "1.0.0"


# ────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────
def patches_root() -> Path:
    """Folder holding patch state, next to the workspace (writable)."""
    root = app_paths.workspace_root().parent / "patches"
    (root / "active").mkdir(parents=True, exist_ok=True)
    return root


def active_dir() -> Path:
    return patches_root() / "active"


def _applied_file() -> Path:
    return patches_root() / "applied.json"


# ────────────────────────────────────────────────────────────
# Version helpers
# ────────────────────────────────────────────────────────────
def _parse(v: str) -> tuple:
    """'1.2.10' -> (1,2,10); tolerant of junk."""
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


def base_version() -> str:
    found = app_paths.resolve_existing(BASE_VERSION_FILE)
    if found:
        try:
            return Path(found).read_text(encoding="utf-8").strip() or DEFAULT_BASE_VERSION
        except Exception:
            pass
    return DEFAULT_BASE_VERSION


def applied_patches() -> list[dict]:
    f = _applied_file()
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def effective_version() -> str:
    """Highest of base version and any applied patch versions."""
    versions = [base_version()] + [p.get("version", "0.0.0") for p in applied_patches()]
    return max(versions, key=_parse)


# ────────────────────────────────────────────────────────────
# sys.path activation (call once at startup, before importing app modules)
# ────────────────────────────────────────────────────────────
def activate_patches() -> str | None:
    """Prepend the active patch dir to sys.path so patched .py files win.

    Returns the active dir path if it contains any .py override, else None.
    Safe to call unconditionally and early.
    """
    import sys
    ad = active_dir()
    has_py = any(ad.glob("*.py"))
    if has_py:
        p = str(ad)
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
        return p
    return None


# ────────────────────────────────────────────────────────────
# Applying a patch
# ────────────────────────────────────────────────────────────
def inspect_patch(zip_path: str) -> dict:
    """Read patch.json from a patch zip without applying it."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            if "patch.json" not in z.namelist():
                return {"ok": False, "error": "patch.json missing in archive"}
            meta = json.loads(z.read("patch.json").decode("utf-8"))
        py_files = []
        with zipfile.ZipFile(zip_path) as z:
            py_files = [n for n in z.namelist() if n.endswith(".py")]
        return {"ok": True, "meta": meta, "py_files": py_files}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def apply_patch(zip_path: str) -> dict:
    """Apply a patch zip: validate, overlay .py files into active/, record it.

    Returns {ok, version, applied:[files], error}.
    """
    info = inspect_patch(zip_path)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "invalid patch")}

    meta = info["meta"]
    version = str(meta.get("version", "")).strip()
    if not version:
        return {"ok": False, "error": "patch.json has no 'version'"}

    # Guard: patch must target this app line
    min_app = str(meta.get("min_app", "0.0.0"))
    if _parse(base_version()) < _parse(min_app):
        return {
            "ok": False,
            "error": f"Patch requires app ≥ {min_app}; installed base is {base_version()}.",
        }

    ad = active_dir()
    applied_files = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(tmp)
            for name in os.listdir(tmp):
                if name.endswith(".py"):
                    shutil.copy2(os.path.join(tmp, name), ad / name)
                    applied_files.append(name)
    except Exception as e:
        return {"ok": False, "error": f"extraction failed: {e}"}

    # Record
    record = applied_patches()
    record.append({
        "version": version,
        "notes": meta.get("notes", ""),
        "files": applied_files,
        "applied_at": datetime.now().isoformat(timespec="seconds"),
    })
    try:
        _applied_file().write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    return {"ok": True, "version": version, "applied": applied_files, "error": None}


def revert_all_patches() -> dict:
    """Remove every applied .py override and clear the record (back to base)."""
    ad = active_dir()
    removed = 0
    try:
        for f in ad.glob("*.py"):
            f.unlink()
            removed += 1
        if _applied_file().exists():
            _applied_file().unlink()
    except Exception as e:
        return {"ok": False, "removed": removed, "error": str(e)}
    return {"ok": True, "removed": removed, "error": None}


# ────────────────────────────────────────────────────────────
# Build helper (developer side): create a patch zip from given .py files
# ────────────────────────────────────────────────────────────
def build_patch(version: str, files: list[str], out_zip: str,
                notes: str = "", min_app: str = "1.0.0") -> dict:
    """Package .py files + a manifest into a distributable patch zip.

    Run this on the developer machine, not inside the app.
    """
    try:
        manifest = {
            "version": version,
            "min_app": min_app,
            "notes": notes,
            "built_at": datetime.now().isoformat(timespec="seconds"),
            "files": [os.path.basename(f) for f in files],
        }
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("patch.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for f in files:
                z.write(f, os.path.basename(f))
        return {"ok": True, "zip": out_zip, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}