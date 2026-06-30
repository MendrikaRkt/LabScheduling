"""Centralized monitoring dashboard.

Page independent from the main flow (wizard). It aggregates:
  - the solver metrics (variables, constraints, time, objective),
  - the dashboard of detected inconsistencies,
  - distribution charts (sessions per professor / day / block / week),
  - the validation logs in real time.

The data is produced by MonitoringService and ValidationReportBuilder; this
layer ONLY handles display.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from application.services.monitoring_service import (
    CONSTRAINT_LABELS,
    MonitoringService,
    SolverMetrics,
)
from application.services.validation_report import (
    ValidationReport,
    ValidationReportBuilder,
)
from application.use_cases.run_scheduling import RunSchedulingUseCase
from infrastructure.config.config_loader import get_settings
from presentation.components.demo_inputs import build_inputs
from presentation.components.ui_helpers import (
    page_header,
    section_header,
    stat_card,
)

_COLOR = px.colors.qualitative.Set2


def _run_monitoring(subject_codes, n_groups):
    """Runs an instrumented scheduling and stores metrics + report."""
    settings = get_settings()
    groups, profs = build_inputs(settings, subject_codes, n_groups=n_groups)
    uc = RunSchedulingUseCase(settings)
    result, elapsed = MonitoringService.timed_execute(uc, groups, profs)
    metrics = MonitoringService(settings).collect(result.sessions, result, elapsed)
    report = ValidationReportBuilder().build(result)
    st.session_state.mon_metrics = metrics
    st.session_state.mon_report = report
    st.session_state.mon_result = result


def render() -> None:
    page_header("Monitoring Dashboard",
                "Solver metrics, inconsistencies and distributions - centralized view")

    settings = get_settings()

    # -- Collection controls ------------------------------------------------
    with st.expander("Collection parameters", expanded=True):
        all_codes = list(settings.subjects.keys())
        default_codes = all_codes[: min(3, len(all_codes))]
        col1, col2 = st.columns([3, 1])
        with col1:
            subject_codes = st.multiselect(
                "Subjects to analyze", options=all_codes, default=default_codes)
        with col2:
            n_groups = st.number_input("Groups / subject", 1, 12, 3)
        if st.button("Run the metrics collection", type="primary"):
            if not subject_codes:
                st.warning("Select at least one subject.")
            else:
                with st.spinner("Building the model and solving..."):
                    _run_monitoring(subject_codes, int(n_groups))

    metrics: SolverMetrics = st.session_state.get("mon_metrics")
    report: ValidationReport = st.session_state.get("mon_report")
    if metrics is None:
        st.info("Run a collection to display the dashboard.")
        return

    # -- 1. Solver metrics overview -----------------------------------------
    section_header("Solver metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        stat_card("Status", metrics.status or "-")
    with c2:
        stat_card("Variables", metrics.n_variables,
                "\"week\" decision variables")
    with c3:
        stat_card("Constraints", metrics.total_constraints,
                "Total constraints posted (hard + soft)")
    with c4:
        stat_card("Solving time", f"{metrics.elapsed_seconds:.3f} s")
    with c5:
        stat_card("Planned sessions",
                f"{metrics.n_scheduled}/{metrics.n_sessions}",
                f"Rate: {metrics.scheduling_rate} %")

    # per-semester detail
    if metrics.semesters:
        srows = [{
            "Semester": f"S{m.semester}", "Sessions": m.n_sessions,
            "Variables": m.n_variables, "Constraints": m.total_constraints,
            "Status": m.status or "-", "Objective": round(m.objective, 1),
        } for m in metrics.semesters]
        st.dataframe(pd.DataFrame(srows), use_container_width=True, hide_index=True)

    # constraints distribution chart
    if metrics.constraints_by_kind:
        crows = [{
            "Constraint": CONSTRAINT_LABELS.get(k, k), "Count": v,
        } for k, v in metrics.constraints_by_kind.items()]
        fig = px.bar(pd.DataFrame(crows), x="Count", y="Constraint",
                    orientation="h", color="Constraint",
                    color_discrete_sequence=_COLOR,
                    title="Distribution of the model constraints")
        fig.update_layout(showlegend=False, height=320)
        st.plotly_chart(fig, use_container_width=True)

    # -- 2. Inconsistencies dashboard ---------------------------------------
    section_header("Detected inconsistencies")
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        stat_card("Total", report.total)
    with e2:
        stat_card("Errors", report.errors)
    with e3:
        stat_card("Warnings", report.warnings)
    with e4:
        stat_card("Infos", report.infos)

    if report.is_clean and report.total == 0:
        st.success("No inconsistency detected: schedule is consistent.")
    else:
        builder = ValidationReportBuilder()
        st.dataframe(pd.DataFrame(builder.to_rows(report)),
                    use_container_width=True, hide_index=True)
        by_cat = report.by_category()
        if by_cat:
            fig = px.pie(names=list(by_cat.keys()), values=list(by_cat.values()),
                        title="Inconsistencies by category",
                        color_discrete_sequence=_COLOR, hole=0.4)
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)

    # -- 3. Distribution charts ---------------------------------------------
    section_header("Session distributions")
    g1, g2 = st.columns(2)
    with g1:
        if metrics.sessions_per_professor:
            df = pd.DataFrame({
                "Professor": list(metrics.sessions_per_professor.keys()),
                "Sessions": list(metrics.sessions_per_professor.values()),
            })
            fig = px.bar(df, x="Sessions", y="Professor", orientation="h",
                        color="Sessions", color_continuous_scale="Blues",
                        title="Sessions per professor")
            fig.update_layout(height=360, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
    with g2:
        if metrics.sessions_per_day:
            df = pd.DataFrame({
                "Day": list(metrics.sessions_per_day.keys()),
                "Sessions": list(metrics.sessions_per_day.values()),
            })
            fig = px.bar(df, x="Day", y="Sessions", color="Day",
                        color_discrete_sequence=_COLOR,
                        title="Sessions per day")
            fig.update_layout(height=360, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    g3, g4 = st.columns(2)
    with g3:
        if metrics.sessions_per_block:
            df = pd.DataFrame({
                "Block": list(metrics.sessions_per_block.keys()),
                "Sessions": list(metrics.sessions_per_block.values()),
            })
            fig = px.bar(df, x="Block", y="Sessions", color="Block",
                        color_discrete_sequence=_COLOR,
                        title="Sessions per time block")
            fig.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    with g4:
        if metrics.sessions_per_week:
            df = pd.DataFrame({
                "Week": list(metrics.sessions_per_week.keys()),
                "Sessions": list(metrics.sessions_per_week.values()),
            })
            fig = px.line(df, x="Week", y="Sessions", markers=True,
                        title="Load per week")
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)

    # -- 4. Real-time validation logs ---------------------------------------
    section_header("Validation logs")
    result = st.session_state.get("mon_result")
    if result is not None and getattr(result, "report_lines", None):
        st.code("\n".join(result.report_lines), language="text")
    else:
        st.caption("No validation log available.")
