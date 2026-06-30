"""Results page: schedule, conflicts and credit audit."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from application.services.scheduler_service import SchedulingResult
from presentation.components.ui_helpers import (
    discrepancy_badge,
    page_header,
    section_header,
    stat_card,
)


def render(result: SchedulingResult) -> None:
    page_header("Results", "Resolved schedule, conflicts and credit audit")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Solver status", result.status)
    with c2:
        stat_card("Planned sessions",
                sum(1 for s in result.sessions if s.is_scheduled))
    with c3:
        stat_card("Conflicts", len(result.conflicts))
    with c4:
        stat_card("Credit gaps", len(result.discrepancies))

    # --- Schedule -----------------------------------------------------------
    section_header("Session schedule")
    rows = [{
        "Subject": s.subject, "Group": f"G{s.group_num}", "Session": s.session_num,
        "Week": s.week, "Day": s.slot.day, "Block": s.slot.block_label,
        "Professor": getattr(s, "professor", "") or "-",
    } for s in sorted(result.sessions, key=lambda x: (x.subject, x.group_num, x.session_num))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # --- Credit audit -------------------------------------------------------
    section_header("Credit audit vs planned sessions")
    if not result.discrepancies:
        st.success("No gap detected: load consistent with the official P credits.")
    else:
        drows = [{
            "Professor": d.professor, "Subject": d.subject,
            "Expected": d.expected_sessions, "Planned": d.planned_sessions,
            "Status": discrepancy_badge(d.delta),
        } for d in result.discrepancies]
        st.dataframe(pd.DataFrame(drows), use_container_width=True, hide_index=True)

    # --- Conflicts ----------------------------------------------------------
    if result.conflicts:
        section_header("Detected conflicts")
        for c in result.conflicts:
            st.warning(f"[{c.kind}] {c.description}")
