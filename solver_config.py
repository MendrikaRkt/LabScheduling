"""
solver_config.py — Configurable soft-constraint system for the CP-SAT solver
(Phase 2, Feature 1).

This module is an ADDITIVE layer: it never changes the solver logic. It only
provides a validated way to read, validate and describe the WEIGHTS and the
ENABLE flags of the four soft constraints handled by ``pipeline.solve()``:

    - semester_anchor_first : pull each group's FIRST session towards the
      start of its allowed window (current default weight = 100).
    - semester_anchor_last  : pull each group's LAST session towards the end of
      its allowed window (current default weight = 100).
    - spacing               : keep sessions of a group evenly spaced
      (current default weight = 200).
    - parity                : alternate odd/even weeks between parallel groups
      (current default weight = 50, mirrors PARITY_PENALTY_WEIGHT).

Backward compatibility guarantee
--------------------------------
If ``config/solver_constraints.yaml`` is absent or invalid, ``load_config()``
returns :data:`DEFAULT_CONFIG`, whose weights and flags reproduce EXACTLY the
values hard-coded in the validated ``pipeline.solve()``. The solver therefore
behaves identically to before Phase 2 when no configuration file is present.

The hard constraints (C1/C4/C5) and the reserved-slot penalty are intentionally
NOT exposed here: they are correctness constraints, not preferences.
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except Exception:  # pragma: no cover - yaml is a declared dependency
    yaml = None  # type: ignore

try:
    import app_paths
except Exception:  # pragma: no cover - app_paths always present in app runtime
    app_paths = None  # type: ignore


# ---------------------------------------------------------------------------
# Canonical keys and validated defaults
# ---------------------------------------------------------------------------

#: Ordered list of the soft-constraint keys the solver understands.
SOFT_CONSTRAINT_KEYS: Tuple[str, ...] = (
    "semester_anchor_first",
    "semester_anchor_last",
    "spacing",
    "parity",
)

#: Human-readable French labels for the UI (values only; keys stay canonical).
CONSTRAINT_LABELS_FR: Dict[str, str] = {
    "semester_anchor_first": "Ancrage debut de semestre (1re seance)",
    "semester_anchor_last": "Ancrage fin de semestre (derniere seance)",
    "spacing": "Espacement regulier des seances",
    "parity": "Alternance de parite entre groupes paralleles",
}

#: Short French help text for each soft constraint.
CONSTRAINT_HELP_FR: Dict[str, str] = {
    "semester_anchor_first": (
        "Penalise les premieres seances placees trop tard dans la fenetre "
        "autorisee. Poids eleve = demarrage plus precoce."
    ),
    "semester_anchor_last": (
        "Penalise les dernieres seances placees trop tot. Poids eleve = "
        "occupation jusqu'a la fin du semestre."
    ),
    "spacing": (
        "Penalise les ecarts irreguliers entre seances successives d'un "
        "groupe. Poids eleve = espacement plus uniforme."
    ),
    "parity": (
        "Encourage les groupes paralleles a occuper des semaines de parite "
        "opposee (paires/impaires). Poids eleve = alternance plus stricte."
    ),
}

#: Weight bounds accepted by the validator (inclusive).
MIN_WEIGHT = 0
MAX_WEIGHT = 100_000

#: Above this weight the UI shows an "extreme configuration" warning.
EXTREME_WEIGHT = 10_000

#: The validated baseline. Weights reproduce the hard-coded pipeline values.
DEFAULT_CONFIG: Dict[str, Any] = {
    "active_profile": "Balanced",
    "soft_constraints": {
        "semester_anchor_first": {"enabled": True, "weight": 100},
        "semester_anchor_last": {"enabled": True, "weight": 100},
        "spacing": {"enabled": True, "weight": 200},
        "parity": {"enabled": True, "weight": 50},
    },
}

#: The three shipped preset profiles.
PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "Strict": {
        "semester_anchor_first": {"enabled": True, "weight": 300},
        "semester_anchor_last": {"enabled": True, "weight": 300},
        "spacing": {"enabled": True, "weight": 500},
        "parity": {"enabled": True, "weight": 150},
    },
    "Balanced": {
        "semester_anchor_first": {"enabled": True, "weight": 100},
        "semester_anchor_last": {"enabled": True, "weight": 100},
        "spacing": {"enabled": True, "weight": 200},
        "parity": {"enabled": True, "weight": 50},
    },
    "Relaxed": {
        "semester_anchor_first": {"enabled": True, "weight": 30},
        "semester_anchor_last": {"enabled": True, "weight": 30},
        "spacing": {"enabled": False, "weight": 50},
        "parity": {"enabled": False, "weight": 10},
    },
}

#: Default location of the YAML file, relative to the app root.
CONFIG_REL_PATH = os.path.join("config", "solver_constraints.yaml")


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def default_config_path() -> str:
    """Return the best path for the constraints file.

    Prefers a workspace/user copy when :mod:`app_paths` is available, otherwise
    falls back to the plain relative path used from the source tree.
    """
    if app_paths is not None:
        found = app_paths.resolve_existing(CONFIG_REL_PATH)
        if found:
            return found
        # No file yet: point at the writable workspace location.
        try:
            return app_paths.workspace_path("config", "solver_constraints.yaml")
        except Exception:
            pass
    return CONFIG_REL_PATH


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_config(cfg: Any) -> List[str]:
    """Validate a configuration mapping and return a list of error messages.

    An empty list means the configuration is valid. Messages are plain English
    and reference the offending key, so the UI can surface them directly.
    """
    errors: List[str] = []

    if not isinstance(cfg, dict):
        return ["Configuration root must be a mapping (got "
                f"{type(cfg).__name__})."]

    profile = cfg.get("active_profile", "Balanced")
    if not isinstance(profile, str):
        errors.append("'active_profile' must be a string.")
    elif profile not in PRESETS and profile != "Custom":
        errors.append(
            f"'active_profile' = '{profile}' is unknown. Expected one of "
            f"{sorted(PRESETS)} or 'Custom'."
        )

    soft = cfg.get("soft_constraints")
    if not isinstance(soft, dict):
        errors.append("'soft_constraints' must be a mapping.")
        return errors

    for key in SOFT_CONSTRAINT_KEYS:
        if key not in soft:
            errors.append(f"Missing soft constraint '{key}'.")
            continue
        entry = soft[key]
        if not isinstance(entry, dict):
            errors.append(f"'{key}' must be a mapping with 'enabled'/'weight'.")
            continue
        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            errors.append(f"'{key}.enabled' must be a boolean.")
        weight = entry.get("weight")
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            errors.append(f"'{key}.weight' must be a number.")
        elif not (MIN_WEIGHT <= weight <= MAX_WEIGHT):
            errors.append(
                f"'{key}.weight' = {weight} out of range "
                f"[{MIN_WEIGHT}, {MAX_WEIGHT}]."
            )

    unknown = set(soft) - set(SOFT_CONSTRAINT_KEYS)
    if unknown:
        errors.append(f"Unknown soft constraint(s): {sorted(unknown)}.")

    return errors


def _merge_with_defaults(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a full config: user values layered on top of DEFAULT_CONFIG."""
    merged = copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(cfg, dict):
        return merged
    if isinstance(cfg.get("active_profile"), str):
        merged["active_profile"] = cfg["active_profile"]
    soft = cfg.get("soft_constraints")
    if isinstance(soft, dict):
        for key in SOFT_CONSTRAINT_KEYS:
            entry = soft.get(key)
            if isinstance(entry, dict):
                if isinstance(entry.get("enabled"), bool):
                    merged["soft_constraints"][key]["enabled"] = entry["enabled"]
                w = entry.get("weight")
                if isinstance(w, (int, float)) and not isinstance(w, bool):
                    merged["soft_constraints"][key]["weight"] = int(w)
    return merged


# ---------------------------------------------------------------------------
# Loading / saving
# ---------------------------------------------------------------------------

def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate the solver constraint configuration.

    Falls back to :data:`DEFAULT_CONFIG` (validated baseline) if the file is
    missing, unreadable, malformed or invalid, guaranteeing the solver keeps
    its pre-Phase-2 behaviour. Partial files are completed with defaults.
    """
    resolved = path or default_config_path()
    if not resolved or not os.path.exists(resolved) or yaml is None:
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(resolved, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except Exception:
        return copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return copy.deepcopy(DEFAULT_CONFIG)
    merged = _merge_with_defaults(raw)
    if validate_config(merged):
        # Even merged config is invalid -> stay on the safe baseline.
        return copy.deepcopy(DEFAULT_CONFIG)
    return merged


def save_config(cfg: Dict[str, Any], path: Optional[str] = None) -> str:
    """Validate then persist a configuration as YAML. Returns the written path.

    Raises ``ValueError`` with the joined error messages if invalid, and
    ``RuntimeError`` if PyYAML is unavailable.
    """
    errors = validate_config(cfg)
    if errors:
        raise ValueError("Invalid solver configuration: " + "; ".join(errors))
    if yaml is None:
        raise RuntimeError("PyYAML is required to save the configuration.")
    target = path or default_config_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, sort_keys=False, allow_unicode=True)
    return target


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def apply_profile(profile_name: str) -> Dict[str, Any]:
    """Return a full config dict built from a named preset profile.

    Raises ``KeyError`` if the profile name is unknown.
    """
    if profile_name not in PRESETS:
        raise KeyError(
            f"Unknown profile '{profile_name}'. Expected one of "
            f"{sorted(PRESETS)}."
        )
    return {
        "active_profile": profile_name,
        "soft_constraints": copy.deepcopy(PRESETS[profile_name]),
    }


def detect_profile(cfg: Dict[str, Any]) -> str:
    """Return the preset name matching ``cfg`` weights/flags, else 'Custom'."""
    soft = cfg.get("soft_constraints", {})
    for name, preset in PRESETS.items():
        if all(
            soft.get(k, {}).get("enabled") == preset[k]["enabled"]
            and soft.get(k, {}).get("weight") == preset[k]["weight"]
            for k in SOFT_CONSTRAINT_KEYS
        ):
            return name
    return "Custom"


# ---------------------------------------------------------------------------
# Accessors used by the solver
# ---------------------------------------------------------------------------

def is_enabled(cfg: Dict[str, Any], key: str) -> bool:
    """Return whether a soft constraint is active (defaults to True)."""
    return bool(cfg.get("soft_constraints", {}).get(key, {}).get("enabled", True))


def get_weight(cfg: Dict[str, Any], key: str, default: int = 0) -> int:
    """Return the EFFECTIVE weight of a soft constraint.

    Returns 0 when the constraint is disabled, so the solver can simply skip a
    zero-weighted objective term.
    """
    entry = cfg.get("soft_constraints", {}).get(key, {})
    if not entry.get("enabled", True):
        return 0
    w = entry.get("weight", default)
    try:
        return int(w)
    except (TypeError, ValueError):
        return int(default)


def config_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return a compact, JSON-serialisable summary for solver_stats.json."""
    soft = cfg.get("soft_constraints", {})
    return {
        "active_profile": detect_profile(cfg),
        "declared_profile": cfg.get("active_profile", "Balanced"),
        "weights": {
            k: get_weight(cfg, k) for k in SOFT_CONSTRAINT_KEYS
        },
        "enabled": {
            k: is_enabled(cfg, k) for k in SOFT_CONSTRAINT_KEYS
        },
    }


def is_extreme(cfg: Dict[str, Any]) -> List[str]:
    """Return a list of French warnings for extreme/degenerate configurations."""
    warnings: List[str] = []
    if not any(is_enabled(cfg, k) for k in SOFT_CONSTRAINT_KEYS):
        warnings.append(
            "Toutes les contraintes souples sont desactivees : le solveur ne "
            "cherchera plus a optimiser le placement (premiere solution "
            "faisable uniquement)."
        )
    for key in SOFT_CONSTRAINT_KEYS:
        if is_enabled(cfg, key) and get_weight(cfg, key) >= EXTREME_WEIGHT:
            warnings.append(
                f"Poids tres eleve pour '{CONSTRAINT_LABELS_FR.get(key, key)}' "
                f"({get_weight(cfg, key)}) : peut ecraser les autres objectifs."
            )
    return warnings
