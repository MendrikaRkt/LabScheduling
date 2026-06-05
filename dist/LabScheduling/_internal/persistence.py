"""
persistence.py — Persistent memory for the Lab Scheduling app.

Stores user preferences (language, theme), the advanced configuration, and a
lightweight history of optimisation runs in a per-user, writable location that
survives application restarts and works when the app is packaged as a Windows
.exe (where the install folder under Program Files is read-only).

Layout of the data directory:
    <data_dir>/
        prefs.json        # language, theme, advanced_config
        runs.json         # list of past run summaries (most recent first)

Resolution of <data_dir>:
    Windows : %APPDATA%/LabScheduling           (e.g. C:/Users/<you>/AppData/Roaming/LabScheduling)
    macOS   : ~/Library/Application Support/LabScheduling
    Linux   : $XDG_DATA_HOME/LabScheduling  or  ~/.local/share/LabScheduling

A LABSCHED_DATA_DIR environment variable, if set, overrides everything (useful
for the packaged launcher and for tests).
"""

from __future__ import annotations

import os
import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

APP_DIR_NAME = "LabScheduling"
PREFS_FILE = "prefs.json"
RUNS_FILE = "runs.json"
MAX_RUNS = 50  # cap the history so the file never grows unbounded


# ════════════════════════════════════════════════════════════
# Directory resolution
# ════════════════════════════════════════════════════════════
def get_data_dir() -> Path:
    """Return a writable per-user data directory, creating it if needed."""
    override = os.environ.get("LABSCHED_DATA_DIR")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        root = os.environ.get("APPDATA") or os.path.expanduser("~")
        base = Path(root) / APP_DIR_NAME
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    else:
        root = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
        base = Path(root) / APP_DIR_NAME
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Last-resort fallback so the app never crashes on a locked-down machine
        base = Path(tempfile.gettempdir()) / APP_DIR_NAME
        base.mkdir(parents=True, exist_ok=True)
    return base


def _path(filename: str) -> Path:
    return get_data_dir() / filename


# ════════════════════════════════════════════════════════════
# Low-level atomic JSON read / write
# ════════════════════════════════════════════════════════════
def _read_json(path: Path, default):
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def _write_json(path: Path, data) -> bool:
    """Atomic write: dump to a temp file in the same dir, then replace."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)  # atomic on the same filesystem
        return True
    except Exception:
        return False


# ════════════════════════════════════════════════════════════
# Preferences (language, theme, advanced configuration)
# ════════════════════════════════════════════════════════════
def load_prefs() -> dict:
    """Load persisted preferences. Always returns a dict (possibly empty)."""
    data = _read_json(_path(PREFS_FILE), {})
    return data if isinstance(data, dict) else {}


def save_prefs(prefs: dict) -> bool:
    """Persist the full preferences dict."""
    payload = dict(prefs)
    payload["_saved_at"] = datetime.now().isoformat(timespec="seconds")
    return _write_json(_path(PREFS_FILE), payload)


def update_prefs(**changes) -> bool:
    """Merge a few keys into the persisted preferences and save."""
    prefs = load_prefs()
    prefs.update(changes)
    return save_prefs(prefs)


# ════════════════════════════════════════════════════════════
# Run history
# ════════════════════════════════════════════════════════════
def load_runs() -> list:
    """Return the list of past run summaries (most recent first)."""
    data = _read_json(_path(RUNS_FILE), [])
    return data if isinstance(data, list) else []


def record_run(summary: dict) -> bool:
    """Prepend a run summary to the history (capped at MAX_RUNS).

    `summary` is a free-form dict; a timestamp is added automatically.
    Typical keys: assignment_rate, reliability_score, sessions, groups,
    conflicts, semester1_sessions, semester2_sessions.
    """
    runs = load_runs()
    entry = dict(summary)
    entry.setdefault("timestamp", datetime.now().isoformat(timespec="seconds"))
    runs.insert(0, entry)
    runs = runs[:MAX_RUNS]
    return _write_json(_path(RUNS_FILE), runs)


def clear_runs() -> bool:
    return _write_json(_path(RUNS_FILE), [])


# ════════════════════════════════════════════════════════════
# Convenience for the Streamlit app
# ════════════════════════════════════════════════════════════
def hydrate_session(st, defaults: dict) -> None:
    """Populate st.session_state from disk on first load of a session.

    Restores `lang`, `theme_choice`, and `advanced_config` if they were saved
    previously. Falls back to the provided defaults otherwise. Safe to call
    once per session (guarded by a flag).
    """
    if st.session_state.get("_persistence_hydrated"):
        return
    prefs = load_prefs()

    if "lang" in prefs and prefs["lang"] in ("en", "es", "fr"):
        st.session_state["lang"] = prefs["lang"]

    if "theme_choice" in prefs:
        st.session_state["theme_choice"] = prefs["theme_choice"]

    # Merge saved advanced_config over the defaults so new keys added in a
    # later version are still present even with an older saved file.
    if isinstance(prefs.get("advanced_config"), dict):
        merged = dict(defaults.get("advanced_config", {}))
        merged.update(prefs["advanced_config"])
        st.session_state["advanced_config"] = merged

    st.session_state["_persistence_hydrated"] = True


def persist_now(st) -> bool:
    """Snapshot the current preferences from session_state to disk."""
    return save_prefs({
        "lang": st.session_state.get("lang", "en"),
        "theme_choice": st.session_state.get("theme_choice", "auto"),
        "advanced_config": st.session_state.get("advanced_config", {}),
    })