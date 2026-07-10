"""
ui_solver_constraints.py — Embeddable solver soft-constraint configuration UI.

Consolidation of the former standalone page ``pages/4_Configuration_Solveur.py``
into a reusable component so that the solver constraints appear as a section
of the single Configuration page in ``app.py`` (user request: one and only
one configuration page).

The component keeps the exact same behaviour as the standalone page:
- Preset profiles (Strict / Balanced / Relaxed) applied in one click.
- Per-constraint enable toggle and weight slider.
- Extreme-configuration warnings, live preview, validation.
- Persistence to ``config/solver_constraints.yaml`` via ``solver_config``.

All UI labels are in English per project convention; no emojis are used.
"""

from __future__ import annotations

import streamlit as st

import solver_config as sc


def _label(key: str) -> str:
    """English label with a French fallback if the EN map is unavailable."""
    en = getattr(sc, "CONSTRAINT_LABELS_EN", {})
    return en.get(key, sc.CONSTRAINT_LABELS_FR.get(key, key))


def _help(key: str) -> str:
    """English one-line help with a French fallback."""
    en = getattr(sc, "CONSTRAINT_HELP_EN", {})
    return en.get(key, sc.CONSTRAINT_HELP_FR.get(key, ""))


def render_solver_constraints_section() -> None:
    """Render the solver soft-constraint panel (embeddable in a tab).

    Uses ``st.session_state.solver_cfg`` as working state and persists to
    ``config/solver_constraints.yaml`` through :mod:`solver_config`.
    """
    st.caption(
        "Tune the SOFT (preference) constraints of the CP-SAT solver. "
        "The HARD constraints (C1 overlap, C4 weeks >= credits, C5 no double "
        "lab on the same day) are always active and cannot be changed here."
    )

    # Load current configuration into session state (once).
    if "solver_cfg" not in st.session_state:
        st.session_state.solver_cfg = sc.load_config()

    cfg = st.session_state.solver_cfg

    # ── Profile selector ──────────────────────────────────────────────
    st.markdown("##### Preset profile")
    st.caption(
        "Apply a profile in one click. 'Custom' appears as soon as you "
        "change a weight manually."
    )

    current_profile = sc.detect_profile(cfg)
    col_a, col_b, col_c, col_d = st.columns([1, 1, 1, 2])
    with col_a:
        if st.button("Strict", use_container_width=True, key="scfg_strict"):
            st.session_state.solver_cfg = sc.apply_profile("Strict")
            _sync_widget_state()
            st.rerun()
    with col_b:
        if st.button("Balanced", use_container_width=True,
                     key="scfg_balanced"):
            st.session_state.solver_cfg = sc.apply_profile("Balanced")
            _sync_widget_state()
            st.rerun()
    with col_c:
        if st.button("Relaxed", use_container_width=True,
                     key="scfg_relaxed"):
            st.session_state.solver_cfg = sc.apply_profile("Relaxed")
            _sync_widget_state()
            st.rerun()
    with col_d:
        st.metric("Current profile", current_profile)

    # ── Per-constraint controls ───────────────────────────────────────
    st.markdown("##### Fine tuning of soft constraints")
    st.caption(
        "Each constraint below is a PREFERENCE, not a rule: the solver tries "
        "to honour it but may trade it off for a globally better schedule. "
        "Toggle it off to ignore it entirely, or raise/lower its weight to "
        "make it more or less important relative to the others."
    )

    details = getattr(sc, "CONSTRAINT_DETAIL_EN", {})

    new_soft = {}
    for key in sc.SOFT_CONSTRAINT_KEYS:
        entry = cfg["soft_constraints"][key]
        label = _label(key)
        help_txt = _help(key)
        detail = details.get(key, {})
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1:
                enabled = st.toggle(
                    "Enabled", value=bool(entry["enabled"]),
                    key=f"scfg_en_{key}",
                )
            with c2:
                st.markdown(f"**{label}**")
                st.caption(help_txt)
            weight = st.slider(
                "Weight (relative importance)",
                min_value=sc.MIN_WEIGHT, max_value=1000,
                value=min(int(entry["weight"]), 1000),
                step=10, key=f"scfg_w_{key}",
                disabled=not enabled,
            )
            if detail:
                st.markdown(
                    f"- **Purpose:** {detail.get('purpose', '')}\n"
                    f"- **Effect of the weight:** {detail.get('effect', '')}\n"
                    f"- **Typical values:** {detail.get('typical', '')}"
                )
            new_soft[key] = {"enabled": enabled, "weight": weight}

    # Rebuild the working config from the widgets.
    working_cfg = {
        "active_profile": sc.detect_profile({"soft_constraints": new_soft}),
        "soft_constraints": new_soft,
    }
    st.session_state.solver_cfg = working_cfg

    # ── Warnings for extreme configurations ───────────────────────────
    for w in sc.is_extreme(working_cfg):
        st.warning(w)

    # ── Live preview ──────────────────────────────────────────────────
    with st.expander("Preview of the effective configuration"):
        summary = sc.config_summary(working_cfg)
        prev1, prev2 = st.columns(2)
        with prev1:
            st.markdown("**Effective weights (0 = disabled)**")
            st.json(summary["weights"])
        with prev2:
            st.markdown("**Constraint states**")
            st.json(summary["enabled"])

    errors = sc.validate_config(working_cfg)
    if errors:
        st.error("Invalid configuration:\n\n- " + "\n- ".join(errors))

    # ── Save / Reset ──────────────────────────────────────────────────
    save_col, reset_col = st.columns(2)
    with save_col:
        confirm = st.checkbox(
            "I confirm saving this configuration",
            key="scfg_confirm",
        )
        if st.button("Save solver configuration", type="primary",
                     disabled=not confirm or bool(errors),
                     use_container_width=True, key="scfg_save"):
            try:
                path = sc.save_config(working_cfg)
                st.success(f"Configuration saved to: {path}")
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Save failed: {exc}")
    with reset_col:
        if st.button("Reset to defaults (Balanced)",
                     use_container_width=True, key="scfg_reset"):
            st.session_state.solver_cfg = sc.apply_profile("Balanced")
            _sync_widget_state()
            st.rerun()

    st.caption(
        "Reminder: if the configuration file is missing or invalid, the "
        "solver automatically applies the 'Balanced' profile (historical "
        "behaviour). The configuration is applied on the next optimization "
        "run and is recorded in reports/solver_stats.json and in the "
        "Validation Excel sheet for traceability."
    )


def _sync_widget_state() -> None:
    """Push the session config back into the widget keys after a profile
    change so toggles and sliders reflect the newly applied profile."""
    cfg = st.session_state.get("solver_cfg") or {}
    for key, entry in (cfg.get("soft_constraints") or {}).items():
        st.session_state[f"scfg_en_{key}"] = bool(entry.get("enabled", True))
        st.session_state[f"scfg_w_{key}"] = min(int(entry.get("weight", 0)), 1000)
