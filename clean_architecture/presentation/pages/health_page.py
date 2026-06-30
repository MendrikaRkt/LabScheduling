"""Health and status page.

Displays the result of the application health checks (dependencies, config) and
basic runtime information. Useful as an operational dashboard in production.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from infrastructure.health import check_health
from presentation.components.ui_helpers import page_header, section_header, stat_card


def render() -> None:
    page_header("Health & status",
                "Operational status of the application and its dependencies")

    report = check_health()

    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Status", report.status.upper())
    with c2:
        stat_card("Uptime", f"{report.uptime_seconds:.0f} s")
    with c3:
        stat_card("Python", report.python_version)

    if report.status == "ok":
        st.success("All systems operational.")
    else:
        st.error("One or more health checks failed. See the details below.")

    section_header("Checks")
    rows = [{"Check": c.name,
            "Status": "OK" if c.healthy else "FAIL",
            "Detail": c.detail} for c in report.checks]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.caption("This page reflects a live, deep health check. Container "
            "orchestrators should probe Streamlit's /_stcore/health endpoint "
            "for liveness, and this page for readiness diagnostics.")
