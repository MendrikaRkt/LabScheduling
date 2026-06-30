"""Refactored Streamlit application (presentation entry point).

Clearly separates the concerns:
  - business logic lives in application/ and domain/
  - I/O lives in infrastructure/
  - this layer ONLY handles display and UI orchestration.

Run with:  streamlit run presentation/app.py
"""
from __future__ import annotations

import os
import sys

# Allows running `streamlit run presentation/app.py` from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from application.use_cases.run_scheduling import RunSchedulingUseCase  # noqa: E402
from domain.entities.group import Group  # noqa: E402
from domain.entities.professor import Professor  # noqa: E402
from domain.value_objects import TimeSlot  # noqa: E402
from infrastructure.config.config_loader import get_settings  # noqa: E402
from infrastructure.errors import friendly_message  # noqa: E402
from infrastructure.logging_config import get_logger, setup_logging  # noqa: E402
from infrastructure.security import RateLimiter  # noqa: E402
from presentation.components.ui_helpers import wizard_stepper  # noqa: E402
from presentation.pages import (  # noqa: E402
    config_page,
    health_page,
    monitoring_dashboard,
    preview_sandbox,
    results_page,
)

# Configure logging once for the whole process.
setup_logging()
logger = get_logger("lab_scheduler.presentation")

# Throttle expensive solver runs: at most 10 launches per minute per session.
_SOLVER_RATE_LIMITER = RateLimiter(max_calls=10, period_seconds=60)

st.set_page_config(page_title="Laboratory Scheduler - Loyola",
                layout="wide")

# The presentation/pages modules expose render() functions and are NOT
# standalone Streamlit pages: we hide the auto-generated multipage navigation
# to keep only the radio menu driven below.
st.markdown(
    "<style>[data-testid='stSidebarNav']{display:none;}</style>",
    unsafe_allow_html=True,
)

STEPS = ["Configuration", "Run", "Results"]


def _demo_inputs():
    """Builds a small demonstration dataset.

    In production, these groups/professors come from the ingestion adapter
    (infrastructure/excel) from master_schedule.csv and the teaching
    assignment. Here, we illustrate the end-to-end flow without depending on
    the large files.
    """
    settings = get_settings()
    fisica = settings.subjects["S1_Física"]
    groups, profs = [], []
    for i, block in enumerate([1, 2, 3], start=1):
        groups.append(Group(
            subject="S1_Física", group_num=i, semester=1, curso_num=1,
            num_sessions=fisica.num_sessions,
            slot=TimeSlot(0, "Lunes", block, settings.time_blocks[block - 1].label),
            nb_students=12, lab_rooms=fisica.lab_rooms,
            window=fisica.window, program="GITI",
        ))
    profs.append(Professor(name="Merchán Riveros, María Camila",
                        practice_credits_by_subject={"S1_Física": 2}))
    profs.append(Professor(name="Fernández del Castillo, Rafael",
                        practice_credits_by_subject={"S1_Física": 1}))
    return groups, profs


def _wizard() -> None:
    """Main scheduling flow (step-by-step assistant)."""
    if "step" not in st.session_state:
        st.session_state.step = 0
    if "result" not in st.session_state:
        st.session_state.result = None

    wizard_stepper(STEPS, st.session_state.step)
    st.divider()

    step = st.session_state.step
    if step == 0:
        config_page.render()
        if st.button("Next", type="primary"):
            st.session_state.step = 1
            st.rerun()

    elif step == 1:
        st.markdown("## Run the scheduling")
        st.info("Demonstration with a reduced dataset (S1_Física, 3 groups). "
                "In production, groups and credits are ingested from the Excel "
                "files via infrastructure/excel.")
        if st.button("Run the solver", type="primary"):
            if not _SOLVER_RATE_LIMITER.allow("solver"):
                wait = int(_SOLVER_RATE_LIMITER.retry_after("solver")) + 1
                st.warning(f"Too many runs. Please wait {wait}s and try again.")
                return
            progress = st.progress(0, text="Preparing inputs...")
            try:
                groups, profs = _demo_inputs()
                progress.progress(35, text="CP-SAT solving in progress...")
                logger.info("Starting scheduling run (%d groups)", len(groups))
                uc = RunSchedulingUseCase()
                st.session_state.result = uc.execute(groups, profs)
                progress.progress(90, text="Building results...")
                st.session_state.groups = groups
                st.session_state.profs = profs
                progress.progress(100, text="Done.")
                logger.info("Scheduling run finished: status=%s",
                            st.session_state.result.status)
            except Exception as exc:
                logger.exception("Scheduling run failed: %s", exc)
                progress.empty()
                st.error(friendly_message(exc))
                return
            progress.empty()
            st.session_state.step = 2
            st.rerun()
        if st.button("Back"):
            st.session_state.step = 0
            st.rerun()

    elif step == 2:
        if st.session_state.result is None:
            st.warning("No result. Go back to the run step.")
        else:
            results_page.render(st.session_state.result)
            if st.button("Restart"):
                st.session_state.step = 0
                st.session_state.result = None
                st.rerun()


# Navigation: main flow + monitoring tools (separate from the wizard)
_PAGES = {
    "Scheduling assistant": "wizard",
    "Monitoring dashboard": "monitoring",
    "Sandbox (dry-run)": "sandbox",
    "Health & status": "health",
}


def main() -> None:
    st.title("Laboratory Session Scheduler")
    st.caption("Universidad Loyola Sevilla - Clean Architecture")

    with st.sidebar:
        st.header("Navigation")
        choice = st.radio("Go to", list(_PAGES.keys()), index=0)
        st.divider()
        st.caption("The dashboard and the sandbox are independent from the "
                "main generation flow.")

    page = _PAGES[choice]
    if page == "wizard":
        _wizard()
    elif page == "monitoring":
        monitoring_dashboard.render()
    elif page == "sandbox":
        preview_sandbox.render()
    elif page == "health":
        health_page.render()


if __name__ == "__main__":
    main()
