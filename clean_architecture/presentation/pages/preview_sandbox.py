"""Preview sandbox (dry-run mode).

Allows SIMULATING a configuration BEFORE generating any Excel file:
  - select subjects and number of groups,
  - tune the objective weights and the solver time limit,
  - run a "dry-run" solve (no Excel produced),
  - preview the professor->session assignments and key metrics.

We work on a COPY of the configuration (copy.deepcopy) so we never mutate
the singleton cached by get_settings().
"""
from __future__ import annotations

import copy

import pandas as pd
import streamlit as st

from application.services.monitoring_service import MonitoringService
from application.services.validation_report import ValidationReportBuilder
from application.use_cases.run_scheduling import RunSchedulingUseCase
from infrastructure.config.config_loader import get_settings
from presentation.components.demo_inputs import build_inputs
from presentation.components.ui_helpers import (
    page_header,
    section_header,
    stat_card,
)

# Adjustable weights exposed in the UI (key -> label)
_WEIGHT_LABELS = {
    "anchor_start": "Start anchor (close to min_week)",
    "anchor_end": "End anchor (close to max_week)",
    "even_spacing": "Even spacing",
    "parity": "Even/odd parity",
    "reservation": "Reservation compliance",
}


def render() -> None:
    page_header("Preview sandbox",
                "Simulate and test a configuration in dry-run mode (no Excel)")

    settings = get_settings()
    all_codes = list(settings.subjects.keys())

    # -- Scenario selection -------------------------------------------------
    section_header("1. Scenario to simulate")
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        subject_codes = st.multiselect(
            "Subjects", options=all_codes,
            default=all_codes[: min(2, len(all_codes))])
    with col2:
        n_groups = st.number_input("Groups / subject", 1, 12, 3)
    with col3:
        profs_per_subject = st.number_input("Teachers / subject", 1, 6, 2)

    # -- Weight / constraint tuning -----------------------------------------
    section_header("2. Objective weight tuning")
    weights = dict(settings.objective_weights)
    cols = st.columns(len(_WEIGHT_LABELS))
    new_weights = {}
    for col, (key, label) in zip(cols, _WEIGHT_LABELS.items()):
        with col:
            current = int(weights.get(key, 0))
            new_weights[key] = st.number_input(
                label, min_value=0, max_value=1_000_000,
                value=current, step=10, key=f"w_{key}")

    cset1, cset2 = st.columns(2)
    with cset1:
        max_limit = max(60, int(settings.solver.time_limit_seconds))
        time_limit = st.slider("Solver time limit (s)", 1, max_limit,
                            int(settings.solver.time_limit_seconds))
    with cset2:
        parity_enabled = st.checkbox("Enable parity (soft)",
                                    value=bool(settings.parity_enabled))

    # -- Run dry-run --------------------------------------------------------
    section_header("3. Run the simulation (dry-run)")
    st.caption("Dry-run mode solves the model in memory without writing an "
            "Excel file.")
    if st.button("Simulate", type="primary"):
        if not subject_codes:
            st.warning("Select at least one subject.")
            return
        # COPY the config so we do not mutate the global cache
        sim_settings = copy.deepcopy(settings)
        sim_settings.objective_weights = {**weights, **new_weights}
        sim_settings.solver.time_limit_seconds = int(time_limit)
        sim_settings.parity_enabled = bool(parity_enabled)

        with st.spinner("Running dry-run solve..."):
            groups, profs = build_inputs(
                sim_settings, subject_codes, n_groups=int(n_groups),
                profs_per_subject=int(profs_per_subject))
            uc = RunSchedulingUseCase(sim_settings)
            result, elapsed = MonitoringService.timed_execute(uc, groups, profs)
            metrics = MonitoringService(sim_settings).collect(
                result.sessions, result, elapsed)
            report = ValidationReportBuilder().build(result)
        st.session_state.sandbox = {
            "result": result, "metrics": metrics, "report": report,
        }

    sandbox = st.session_state.get("sandbox")
    if not sandbox:
        st.info("Configure a scenario then run the simulation.")
        return

    result = sandbox["result"]
    metrics = sandbox["metrics"]
    report = sandbox["report"]

    # -- Simulation results -------------------------------------------------
    section_header("Simulation result")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Status", metrics.status or "-")
    with c2:
        stat_card("Time", f"{metrics.elapsed_seconds:.3f} s")
    with c3:
        stat_card("Sessions", f"{metrics.n_scheduled}/{metrics.n_sessions}")
    with c4:
        stat_card("Inconsistencies", report.total,
                f"{report.errors} error(s), {report.warnings} warning(s)")

    if report.total:
        with st.expander(f"View the {report.total} inconsistency(ies)"):
            st.dataframe(pd.DataFrame(ValidationReportBuilder().to_rows(report)),
                        use_container_width=True, hide_index=True)

    # -- Assignment preview -------------------------------------------------
    section_header("Assignment preview")
    rows = [{
        "Subject": s.subject, "Group": f"G{s.group_num}",
        "Session": s.session_num, "Week": s.week,
        "Day": s.slot.day, "Block": s.slot.block_label,
        "Room": ", ".join(s.lab_rooms),
        "Teacher": getattr(s, "professor", "") or "-",
    } for s in sorted(result.sessions,
                    key=lambda x: (x.subject, x.group_num, x.session_num))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # per-professor summary
    if metrics.sessions_per_professor:
        st.markdown("**Load per teacher (assigned sessions)**")
        prow = [{"Teacher": k, "Sessions": v}
                for k, v in metrics.sessions_per_professor.items()]
        st.dataframe(pd.DataFrame(prow), use_container_width=True, hide_index=True)

    st.success("Dry-run finished: no data written to disk. "
            "Adjust the weights then re-run to compare.")
