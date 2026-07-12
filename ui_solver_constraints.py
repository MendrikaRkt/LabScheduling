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
    st.info(
        "**What presets change:** Presets optimize the **temporal placement** of sessions "
        "(which week each session lands in). They do **not** change global headcounts "
        "(total sessions/groups/students), which are determined by group formation rules "
        "and the academic calendar. Strict/Balanced/Relaxed will always return OPTIMAL "
        "status with the same aggregate stats — the differences are in the week-by-week "
        "distribution (visible in the Excel Week column and detailed schedule reports).",
        icon="ℹ️"
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



# ─────────────────────────────────────────────────────────────────────────────
# Constraints reference (C1–C9) — read-only documentation table
# ─────────────────────────────────────────────────────────────────────────────
# Authoritative, human-readable summary of every academic / operational
# constraint the scheduler accounts for. This is documentation only: it renders
# a table and changes no solver behaviour. Sources: docs/PROBLEM_FORMULATION.md,
# pipeline.solve() hard constraints, and schedule_validation.py checks.

# Each row: (id, name, type, enforcement, description, relaxation)
_CONSTRAINTS_REFERENCE = [
    (
        "C1", "Subject slot conflict", "Hard", "CP-SAT + construction",
        "Two groups of the same subject sharing the same slot (day, block) "
        "are placed in different weeks.",
        "None — always enforced.",
    ),
    (
        "C2", "Student vs theory clash", "Hard", "Validated",
        "A student is never scheduled for a lab session at the same slot as "
        "one of their theory courses.",
        "None — a violation is a blocking conflict.",
    ),
    (
        "C3", "Group sizing / capacity", "Hard", "By construction",
        "Lab group size respects the operational policy "
        "(min 7 / preferred 12 / max 15 students per group).",
        "Under/over-sized groups are flagged as an indicator when a formation "
        "cannot be split cleanly.",
    ),
    (
        "C4", "Room conflict", "Hard", "CP-SAT",
        "A physical room hosts a single group per (day, block, week) — "
        "no double room booking.",
        "None — always enforced.",
    ),
    (
        "C5", "Session chronological order", "Hard", "CP-SAT",
        "Sessions of the same group run in order: práctica k+1 is in a later "
        "week than práctica k.",
        "None — always enforced.",
    ),
    (
        "C6", "Student lab double-booking", "Hard", "CP-SAT",
        "A student is never placed in two lab sessions in the same "
        "(day, block, week).",
        "None — always enforced.",
    ),
    (
        "C7", "Year → time-of-day preference", "Hard", "By construction",
        "Blocks are filtered per academic year so cohorts land in their "
        "expected morning / afternoon window.",
        "Applied at group construction; not re-checked after manual edits.",
    ),
    (
        "C8", "External room reservation", "Soft (quasi-hard)", "Penalty 100 000",
        "Avoid weeks where a room is reserved by an external activity. The "
        "very high penalty makes it behave almost like a hard rule.",
        "Relaxable: the solver may still use a reserved week if there is no "
        "feasible alternative.",
    ),
    (
        "C9", "Friday-evening avoidance", "Soft (relaxed)", "Placement penalty",
        "Labs are steered away from late Friday blocks (17:00–21:00).",
        "Relaxed by design: handled as a placement penalty in the heuristic — "
        "Friday evening is discouraged but never forbidden.",
    ),
]

_TYPE_COLORS = {
    "Hard": ("var(--good-bg)", "var(--good)"),
    "Soft (quasi-hard)": ("var(--warn-bg)", "var(--warn)"),
    "Soft (relaxed)": ("var(--surface-2)", "var(--cyan)"),
}


def render_constraints_reference() -> None:
    """Render the full C1–C9 constraints reference as a styled table.

    Read-only documentation — does not affect solver behaviour.
    """
    st.markdown("##### Constraints reference (C1–C9)")
    st.caption(
        "Every academic and operational constraint enforced by the scheduler. "
        "Hard constraints are guaranteed (by the CP-SAT solver or by "
        "construction); soft constraints are preferences that may be relaxed "
        "when no feasible alternative exists."
    )

    rows_html = []
    for cid, name, ctype, enf, desc, relax in _CONSTRAINTS_REFERENCE:
        bg, fg = _TYPE_COLORS.get(ctype, ("var(--surface-2)", "var(--ink-soft)"))
        badge = (
            f"<span style='display:inline-block;padding:2px 10px;border-radius:999px;"
            f"background:{bg};color:{fg};font-size:0.72rem;font-weight:600;"
            f"white-space:nowrap;'>{ctype}</span>"
        )
        rows_html.append(
            "<tr style='border-bottom:1px solid var(--line);'>"
            f"<td style='padding:10px 12px;font-family:var(--font-mono);"
            f"font-weight:600;color:var(--cyan);vertical-align:top;'>{cid}</td>"
            f"<td style='padding:10px 12px;font-weight:600;color:var(--ink);"
            f"vertical-align:top;'>{name}</td>"
            f"<td style='padding:10px 12px;vertical-align:top;'>{badge}</td>"
            f"<td style='padding:10px 12px;color:var(--ink-soft);font-size:0.82rem;"
            f"vertical-align:top;white-space:nowrap;'>{enf}</td>"
            f"<td style='padding:10px 12px;color:var(--ink-soft);font-size:0.86rem;"
            f"line-height:1.5;vertical-align:top;'>{desc}</td>"
            f"<td style='padding:10px 12px;color:var(--ink-mute);font-size:0.82rem;"
            f"line-height:1.5;vertical-align:top;'>{relax}</td>"
            "</tr>"
        )

    header_cells = "".join(
        f"<th style='padding:11px 12px;text-align:left;font-size:0.72rem;"
        f"text-transform:uppercase;letter-spacing:0.06em;color:var(--ink-mute);"
        f"border-bottom:2px solid var(--line-bright);white-space:nowrap;'>{h}</th>"
        for h in ("ID", "Name", "Type", "Enforcement", "Description", "Relaxation")
    )

    table_html = (
        "<div style='overflow-x:auto;border:1px solid var(--line);"
        "border-radius:var(--radius);background:var(--surface);margin:6px 0 10px;'>"
        "<table style='width:100%;border-collapse:collapse;font-family:var(--font-body);'>"
        f"<thead><tr>{header_cells}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

    st.caption(
        "Note: professor double-booking and professor-busy checks are tracked "
        "as post-optimization **indicators** (surfaced in the Validation sheet), "
        "not as hard solver constraints — professor assignment is finalized by "
        "the coordinator."
    )
