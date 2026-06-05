"""
config_verify.py — Prove that what the user configured was actually applied.

The pipeline writes two files:
  • config/user_config.json     — what the APP sent (the user's intent)
  • config/applied_config.json  — what the pipeline ACTUALLY used (read-back)

This module diffs them, parameter by parameter, so the UI can show an honest
"applied / not applied" verdict for every setting. It also reads the real
assignment summary so the Results page never shows hard-coded numbers.
"""

from __future__ import annotations

import json
import os

try:
    import app_paths
    _PATHS = True
except Exception:
    _PATHS = False


def _resolve(rel: str):
    if _PATHS:
        return app_paths.resolve_existing(rel)
    return rel if os.path.exists(rel) else None


def _load(rel: str):
    p = _resolve(rel)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────
# Config reconciliation
# ────────────────────────────────────────────────────────────
def verify_config() -> dict:
    """Compare user_config.json against applied_config.json.

    Returns:
        {
          available: bool,          # both files present
          rows: [ {scope, param, requested, applied, ok} ],
          n_ok: int, n_total: int,
          applied_at: str | None,
        }
    """
    user = _load("config/user_config.json")
    applied = _load("config/applied_config.json")

    if not user or not applied:
        return {"available": False, "rows": [], "n_ok": 0, "n_total": 0,
                "applied_at": (applied or {}).get("meta", {}).get("applied_at")}

    rows = []

    def _cmp(scope, param, requested, applied_val):
        # Normalise for comparison: numbers vs numeric strings, list order/sets
        def norm(x):
            if isinstance(x, bool):
                return x
            if isinstance(x, (int, float)):
                return float(x)
            if isinstance(x, list):
                return sorted(str(i) for i in x)
            if isinstance(x, str):
                s = x.strip()
                try:
                    return float(s)
                except ValueError:
                    return s
            return x
        ok = norm(requested) == norm(applied_val)
        rows.append({
            "scope": scope, "param": param,
            "requested": requested, "applied": applied_val, "ok": ok,
        })

    # Global
    ug = user.get("global", {})
    ag = applied.get("global", {})
    for k, v in ug.items():
        _cmp("global", k, v, ag.get(k))

    # Year prefs
    uy = user.get("year_prefs", {})
    ay = applied.get("year_prefs", {})
    for k, v in uy.items():
        _cmp("year_prefs", k, v, ay.get(k))

    # Per-subject
    us = user.get("subjects", {})
    as_ = applied.get("subjects", {})
    for subj, overrides in us.items():
        applied_subj = as_.get(subj, {})
        for k, v in overrides.items():
            # keywords/keyword_exclude are merged server-side; only verify the
            # numeric / room parameters that must match exactly.
            if k in ("num_sessions", "max_students", "min_week", "max_week", "lab_rooms"):
                _cmp(f"subject:{subj}", k, v, applied_subj.get(k))

    n_ok = sum(1 for r in rows if r["ok"])
    return {
        "available": True,
        "rows": rows,
        "n_ok": n_ok,
        "n_total": len(rows),
        "applied_at": applied.get("meta", {}).get("applied_at"),
    }


# ────────────────────────────────────────────────────────────
# Real assignment summary (no hard-coded numbers)
# ────────────────────────────────────────────────────────────
def assignment_summary() -> dict:
    """Read the real global assignment summary written by the pipeline.

    Returns a dict with whatever columns are present, plus an 'available' flag.
    """
    import csv
    p = _resolve("outputs/optimization/assignment_summary_global.csv")
    if not p:
        return {"available": False}
    try:
        with open(p, encoding="utf-8-sig", newline="") as f:
            row = next(csv.DictReader(f))
        out = {"available": True}
        out.update(row)
        return out
    except Exception:
        return {"available": False}