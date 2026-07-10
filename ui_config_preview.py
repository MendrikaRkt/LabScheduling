"""
ui_config_preview.py — Embeddable "Overview" panel for the Configuration page.

Point 1 of the refinement request: add a preview/overview panel to the
Configuration page showing, at a glance:
  * the loaded input files (Aulario, Alumnos) with row/column counts;
  * the main generation parameters (group sizes, calendar weeks, active
    solver profile, number of customized subjects);
  * a compact data summary (unique students, courses, subjects);
  * launch buttons to jump straight to the optimization step.

The panel is purely additive and read-only with respect to configuration
data: it only reads ``st.session_state`` and sets ``_nav_to`` when a launch
button is pressed (the same mechanism the wizard navigation already uses).

All labels are in English per project convention; no emojis are used.
"""

from __future__ import annotations

import streamlit as st

try:
    import solver_config as sc
except Exception:  # pragma: no cover - defensive import
    sc = None


def _fmt_int(value) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def _active_solver_profile() -> str:
    """Return the active solver profile name, or 'Balanced' as fallback."""
    if sc is None:
        return "Balanced"
    try:
        cfg = st.session_state.get("solver_cfg") or sc.load_config()
        return sc.detect_profile(cfg)
    except Exception:
        return "Balanced"


def render_config_preview() -> None:
    """Render the Configuration overview panel.

    Meant to be called once at the top of the Configuration page so it is
    visible whatever tab the user is on.
    """
    adv = st.session_state.get("advanced_config", {}) or {}
    aul = st.session_state.get("aulario_df")
    alu = st.session_state.get("alumnos_df")

    with st.container(border=True):
        st.markdown("#### Overview")
        st.caption(
            "Snapshot of the inputs and the main parameters that will be used "
            "on the next optimization run."
        )

        # ── Loaded input files ────────────────────────────────────────
        st.markdown("##### Loaded input files")
        f1, f2 = st.columns(2)
        with f1:
            if aul is not None:
                st.success(
                    f"**Aulario (rooms/timetable)**\n\n"
                    f"{_fmt_int(len(aul))} rows x {aul.shape[1]} columns"
                )
            else:
                st.warning("**Aulario** not loaded")
        with f2:
            if alu is not None:
                st.success(
                    f"**Alumnos (student enrolments)**\n\n"
                    f"{_fmt_int(len(alu))} rows x {alu.shape[1]} columns"
                )
            else:
                st.warning("**Alumnos** not loaded")

        # ── Data summary ──────────────────────────────────────────────
        st.markdown("##### Data summary")
        d1, d2, d3 = st.columns(3)
        n_students = "-"
        n_courses = "-"
        if alu is not None:
            if "AlumnoID" in alu.columns:
                n_students = _fmt_int(alu["AlumnoID"].nunique())
            else:
                n_students = _fmt_int(len(alu))
            if "MixtoID" in alu.columns:
                n_courses = _fmt_int(alu["MixtoID"].nunique())
        with d1:
            st.metric("Unique students", n_students)
        with d2:
            st.metric("Courses / groups (MixtoID)", n_courses)
        with d3:
            n_overrides = len(adv.get("subject_overrides", {}) or {})
            st.metric("Customized subjects", n_overrides)

        # ── Main generation parameters ────────────────────────────────
        st.markdown("##### Main generation parameters")
        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.metric("Preferred group size", adv.get("preferred_size", 12))
        with p2:
            st.metric("Default max size", adv.get("default_max", 15))
        with p3:
            st.metric("Min group size", adv.get("min_size", 7))
        with p4:
            st.metric("Start week", adv.get("start_week", 4))

        p5, p6, p7, p8 = st.columns(4)
        with p5:
            st.metric("S1 total weeks", adv.get("s1_total_weeks", 14))
        with p6:
            st.metric("S2 total weeks", adv.get("s2_total_weeks", 20))
        with p7:
            st.metric("Computer lab max", adv.get("computer_lab_max", 24))
        with p8:
            st.metric("Solver profile", _active_solver_profile())

        # Teacher availability rules configured (optional constraints)
        n_wd = len(adv.get("teacher_unavailable_weekdays", {}) or {})
        n_slots = len(adv.get("teacher_unavailability", {}) or {})
        if n_wd or n_slots:
            st.caption(
                f"Teacher availability rules: {n_wd} teacher(s) with blocked "
                f"weekdays, {n_slots} teacher(s) with blocked time slots."
            )

        # ── Launch buttons ────────────────────────────────────────────
        st.markdown("##### Launch")
        data_ok = aul is not None and alu is not None
        b1, b2 = st.columns(2)
        with b1:
            if st.button(
                "Go to optimization ->",
                type="primary",
                use_container_width=True,
                disabled=not data_ok,
                key="cfg_preview_go_optimize",
                help=None if data_ok
                else "Load both Excel files in the Data step first",
            ):
                st.session_state["_nav_to"] = "optimize"
                st.rerun()
        with b2:
            if st.button(
                "Back to data",
                use_container_width=True,
                key="cfg_preview_back_data",
            ):
                st.session_state["_nav_to"] = "data"
                st.rerun()

        if not data_ok:
            st.info(
                "Both input files must be loaded before the optimization can "
                "run. Use the Data step to load them."
            )
