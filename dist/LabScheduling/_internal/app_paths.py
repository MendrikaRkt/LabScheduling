"""
app_paths.py — Single source of truth for file locations.

The app runs in two very different modes and must behave identically in both:

  • From source (development):   python app.py
        - resources and workspace are the current folder.
  • Frozen (PyInstaller .exe):   LabScheduling.exe
        - READ-ONLY resources live in the bundle (sys._MEIPASS),
        - WRITABLE data must live in a per-user folder (%APPDATA%),
          because the install dir under Program Files is read-only.

Two distinct concepts, never mix them:

  resource_path(rel)   -> a bundled, read-only file shipped with the app
                          (logo, generator scripts, default config, fonts…)

  workspace_path(rel)  -> a writable file the app reads AND writes at runtime
                          (outputs/, data_clean/, config/user_config.json,
                           versions/, prefs.json, runs.json…)

Import this everywhere instead of using bare relative paths.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "LabScheduling"


# ────────────────────────────────────────────────────────────
# Read-only bundled resources
# ────────────────────────────────────────────────────────────
def resource_root() -> Path:
    """Folder that contains bundled resources (read-only when frozen)."""
    if getattr(sys, "frozen", False):
        # PyInstaller unpacks data files here; fall back to the exe folder.
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> str:
    """Absolute path to a bundled read-only resource."""
    return str(resource_root().joinpath(*parts))


# ────────────────────────────────────────────────────────────
# Writable per-user workspace
# ────────────────────────────────────────────────────────────
def workspace_root() -> Path:
    """Per-user writable workspace; create it if needed.

    Honoured override: LABSCHED_DATA_DIR (set by the launcher / tests).
    """
    override = os.environ.get("LABSCHED_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = Path(os.path.expanduser("~")) / f".{APP_NAME.lower()}"

    ws = base / "workspace"
    try:
        ws.mkdir(parents=True, exist_ok=True)
    except Exception:
        import tempfile
        ws = Path(tempfile.gettempdir()) / APP_NAME / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
    return ws


def workspace_path(*parts: str) -> str:
    """Absolute path to a writable workspace file, creating parent dirs."""
    p = workspace_root().joinpath(*parts)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return str(p)


# ────────────────────────────────────────────────────────────
# Smart resolver: prefer the workspace copy, fall back to bundle
# ────────────────────────────────────────────────────────────
def resolve_existing(rel: str) -> str | None:
    """Return the first existing path for `rel`, checking the workspace first
    (user-generated / user-edited copy) then the bundled resource. Returns
    None if neither exists.
    """
    ws = workspace_root() / rel
    if ws.exists():
        return str(ws)
    res = resource_root() / rel
    if res.exists():
        return str(res)
    return None