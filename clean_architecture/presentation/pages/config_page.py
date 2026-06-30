"""Configuration page: displays the externalized config (config.yaml)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from infrastructure.config.config_loader import get_settings
from presentation.components.ui_helpers import page_header, section_header, stat_card


def render() -> None:
    page_header("Configuration", "Parameters loaded from config/config.yaml")
    settings = get_settings()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Configured subjects", len(settings.subjects))
    with c2:
        stat_card("Sessions / P credit", settings.sessions_per_credit)
    with c3:
        stat_card("Friday cap", settings.friday.soft_cap)
    with c4:
        stat_card("Solver limit (s)", settings.solver.time_limit_seconds)

    section_header("Laboratory subjects")
    rows = []
    for code, subj in settings.subjects.items():
        rows.append({
            "Code": code,
            "Year": subj.curso_num,
            "Sem.": subj.semester,
            "Sessions/group": subj.num_sessions,
            "Window": f"W{subj.window.min_week}-W{subj.window.max_week}",
            "Max students": subj.max_students,
            "Rooms": ", ".join(subj.lab_rooms),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("CP-SAT solver parameters"):
        st.json({
            "random_seed": settings.solver.random_seed,
            "relative_gap": settings.solver.relative_gap,
            "time_limit_seconds": settings.solver.time_limit_seconds,
            "num_workers": settings.solver.num_workers,
            "objective_weights": settings.objective_weights,
        })
