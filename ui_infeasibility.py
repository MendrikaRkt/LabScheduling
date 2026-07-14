"""
ui_infeasibility.py — Infeasibility "What-If" simulator (render module).

This is the same read-only simulator that previously lived under
``pages/4_Simulateur_Infaisabilite.py``. It has been converted into a
``render()`` module so it appears inside the app's single, consistent
sidebar navigation (radio) instead of as a separate Streamlit multipage
entry — see Point 4 of the consolidation request.

Read-only tool: it never modifies the real optimisation data; it only reads
existing artifacts from ``reports/`` and reconstructs a hypothetical session
list. All UI labels are in English per project convention; no emojis are used.
"""

from __future__ import annotations

import datetime
import os
import sys

import streamlit as st

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import simulation_engine as se  # noqa: E402

# app_paths gives the writable per-user workspace. At runtime run_app.py does
# os.chdir(workspace), so the pipeline writes its artifacts there (relative to
# the CWD) — NOT next to this source file. The simulator must therefore look in
# the CWD / workspace first; the _ROOT fallback only helps in dev-from-source.
try:
    import app_paths as _app_paths
except Exception:  # pragma: no cover - dev fallback
    _app_paths = None

# Optional: pull real lab rooms from the pipeline config to enrich sessions.
try:
    import pipeline as _pipeline
    _LAB_ROOMS = {
        subj: cfg.get("lab_rooms", [])
        for subj, cfg in getattr(_pipeline, "LAB_CONFIG", {}).items()
    }
except Exception:
    _LAB_ROOMS = {}


DAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

_REL_CANDIDATES = [
    os.path.join("outputs", "optimization", "group_composition.csv"),
    os.path.join("data_clean", "group_composition.csv"),
    "group_composition.csv",
]

_SCHEDULE_REL_CANDIDATES = [
    os.path.join("outputs", "optimization", "optimized_schedule_v5.csv"),
    "optimized_schedule_v5.csv",
]


def _find_schedule_source() -> str:
    """Localise optimized_schedule_v5.csv (CWD/workspace/source-tree)."""
    cands = [os.path.abspath(r) for r in _SCHEDULE_REL_CANDIDATES]
    if _app_paths is not None:
        for rel in _SCHEDULE_REL_CANDIDATES:
            try:
                cands.append(_app_paths.workspace_path(rel))
            except Exception:
                pass
    cands += [os.path.join(_ROOT, r) for r in _SCHEDULE_REL_CANDIDATES]
    for p in cands:
        if os.path.exists(p):
            return p
    return ""


def _load_audit(path: str, mtime: float):
    """Business audit of the solution via diagnostics.audit_schedule (read-only).

    Returns the audit dict or None. ``mtime`` is used as a freshness key.
    """
    if not path:
        return None
    try:
        import pandas as pd
        import diagnostics
    except Exception:
        return None
    try:
        df = pd.read_csv(path)
        rows = df.to_dict("records")
        min_group_size = getattr(diagnostics, "DEFAULT_MIN_GROUP_SIZE", 7)
        allow_pm, allow_am = False, False
        try:
            import pipeline
            min_group_size = int(getattr(pipeline, "MIN_GROUP_SIZE",
                                         min_group_size))
            allow_pm = bool(getattr(pipeline, "ALLOW_AFTERNOON_Y1Y3", False))
            allow_am = bool(getattr(pipeline, "ALLOW_MORNING_Y2Y4", False))
        except Exception:
            pass
        return diagnostics.audit_schedule(
            rows, min_group_size=min_group_size,
            allow_afternoon_y1y3=allow_pm, allow_morning_y2y4=allow_am)
    except Exception:
        return None


def _session_candidates() -> list:
    """Build the ordered list of places to look for group_composition.csv.

    Order matters: the pipeline writes into the CWD (workspace) at runtime, so
    CWD-relative and app_paths.workspace paths come first; the source-tree
    (_ROOT) paths are dev-from-source fallbacks only.
    """
    cands = []
    # 1) CWD-relative (this is where the running pipeline writes after chdir).
    for rel in _REL_CANDIDATES:
        cands.append(os.path.abspath(rel))
    # 2) Explicit workspace path via app_paths (robust when CWD is elsewhere).
    if _app_paths is not None:
        for rel in _REL_CANDIDATES:
            try:
                cands.append(_app_paths.workspace_path(rel))
            except Exception:
                pass
    # 3) Source-tree fallback (dev-from-source only).
    for rel in _REL_CANDIDATES:
        cands.append(os.path.join(_ROOT, rel))
    # De-duplicate while preserving order.
    seen, ordered = set(), []
    for p in cands:
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def _find_sessions_source() -> str:
    for path in _session_candidates():
        if os.path.exists(path):
            return path
    return ""


@st.cache_data(show_spinner=False)
def _load_sessions(path: str, mtime: float) -> list:
    """Reconstruct a hypothetical session list from group_composition.csv.

    ``mtime`` participates in the cache key so a fresh run invalidates the
    cache automatically.
    """
    if not path:
        return []
    sessions = se.build_sessions_from_group_composition(
        path, lab_rooms_by_subject=_LAB_ROOMS)
    return sessions or []


def _fmt_mtime(path: str) -> str:
    try:
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return "unknown"


def _render_diff(result: dict) -> None:
    """Render the before/after diff metrics of a simulation result."""
    diff = result["diff"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Feasible before", "Yes" if diff["feasible_before"] else "No")
    c2.metric("Feasible after", "Yes" if diff["feasible_after"] else "No")
    c3.metric("Bottlenecks (after)", diff["n_bottlenecks_after"],
              delta=diff["n_bottlenecks_after"] - diff["n_bottlenecks_before"])
    c4.metric("Overflow reduction", diff["overflow_reduction"],
              help="Number of weeks of excess demand removed by this "
                   "scenario.")
    if diff["became_feasible"]:
        st.success("Promising scenario: the schedule becomes FEASIBLE.")
    elif diff["overflow_reduction"] > 0:
        st.info("Partial improvement: overflow reduced but not eliminated.")
    else:
        st.warning("No measurable improvement with this scenario.")


_TYPE_LABELS_EN = {
    "tiny_group": "Under-sized group",
    "wrong_period": "Session outside period",
    "oversubscription": "Over-subscribed subject",
    "bottleneck": "Capacity bottleneck",
    "credit_overload": "Professor credit overload",
}
_SEV_LABELS_EN = {
    "critique": "Critical",
    "avertissement": "Warning",
    "info": "Info",
}


def _render_business_audit() -> None:
    """Surface the business audit (diagnostics.audit_schedule) in the simulator.

    Demonstrates the central thesis: a solver status of "OPTIMAL" does NOT
    guarantee a COMPLIANT solution. Shows the anomalies detected in the
    produced schedule and the PROPOSED (quantified) remedy for each.
    """
    st.header("Step 1 — Business audit of the solution "
              "(beyond the solver status)")
    st.caption(
        "A solver status of \u201cOPTIMAL\u201d only means the model found a "
        "week assignment that satisfies its hard constraints. It does NOT "
        "guarantee the solution complies with the institution's rules: "
        "pre-processing can absorb an infeasibility by distorting the "
        "solution (tiny/solo groups, sessions outside the expected period). "
        "This audit scans the produced schedule and proposes a quantified "
        "remedy for every anomaly (never applied automatically)."
    )

    sched = _find_schedule_source()
    if not sched:
        st.warning(
            "Optimised schedule not found (optimized_schedule_v5.csv). Run an "
            "optimisation first to feed the audit."
        )
        return

    audit = _load_audit(sched, os.path.getmtime(sched))
    if audit is None:
        st.warning("Audit unavailable (unable to read the schedule).")
        return

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Anomalies detected", audit.get("n_total", 0))
    a2.metric("Of which critical", audit.get("n_critical", 0))
    a3.metric("Groups analysed", audit.get("n_groups_analyzed", 0))
    a4.metric("Verdict",
              "COMPLIANT" if audit.get("healthy") else "TO FIX")

    if audit.get("healthy"):
        st.success(
            "No business anomaly detected: all groups respect the minimum "
            "size and the expected period for their year level."
        )
        return

    st.error(
        f"{audit.get('n_total', 0)} business anomaly(ies) detected despite a "
        f"potentially \u201cOPTIMAL\u201d solver status \u2014 the proof that "
        f"\u201cOPTIMAL\u201d \u2260 \u201ccompliant\u201d."
    )

    by_type = audit.get("by_type", {})
    if by_type:
        st.markdown("**Summary by anomaly type**")
        st.table({
            "Type": [_TYPE_LABELS_EN.get(k, k) for k in by_type],
            "Count": list(by_type.values()),
        })

    st.markdown("**Detailed anomalies and proposed remedies**")
    rows = []
    for an in audit.get("anomalies", []):
        rows.append({
            "Level": an.get("level", ""),
            "Sem.": an.get("semester", ""),
            "Subject": an.get("subject", ""),
            "Group": str(an.get("grupo", "")),
            "Severity": _SEV_LABELS_EN.get(an.get("severity"),
                                           an.get("severity", "")),
            "Anomaly": an.get("detail", ""),
            "Proposed remedy (quantified)": (
                an.get("remedy") or {}).get("text", ""),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "These same anomalies and remedies are exported to the "
        "\u201cBusiness Audit & Remedies\u201d Excel sheet of every generated "
        "workbook."
    )
    st.divider()


def render() -> None:
    """Render the infeasibility simulator inside the main app navigation."""
    # NOTE: the page title is already rendered by app.py via page_header();
    # we intentionally do not repeat it here to avoid a duplicate heading.
    st.info(
        "This tool is READ-ONLY. No real optimisation data is modified. The "
        "results are estimates based on the capacity model (same rules as the "
        "solver diagnostic). Work through the numbered steps below: audit the "
        "current solution, review the automatic suggestions, then test manual "
        "what-if scenarios until the schedule becomes feasible."
    )

    _render_business_audit()

    # ── Data loading (best effort, read-only) with freshness tracking ──
    _src = _find_sessions_source()
    sessions = _load_sessions(_src, os.path.getmtime(_src) if _src else 0.0)
    unplaced = se.load_unplaced_students()
    bottlenecks_reported = se.load_bottlenecks_from_reports()

    if not sessions:
        st.warning(
            "No group data found (group_composition.csv). Run an optimisation "
            "first to feed the simulator."
        )

    group_ids = sorted({str(s["group_id"]) for s in sessions})

    # ── At-a-glance summary of the latest run ──────────────────────────
    st.header("Step 2 — Latest run status")

    baseline = se.analyze_bottlenecks(sessions) if sessions else None
    is_feasible = bool(baseline and baseline.get("feasible"))
    n_bottlenecks = len(baseline.get("bottlenecks", [])) if baseline else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Estimated feasibility", "FEASIBLE" if is_feasible else
              ("INFEASIBLE" if baseline else "n/a"))
    m2.metric("Bottlenecks detected", n_bottlenecks,
              help="Slots (room × day × block) where week demand exceeds the "
                   "available capacity.")
    m3.metric("Unplaced students", len(unplaced),
              help="Students without a group in the last real run "
                   "(reports/unplaced_students.json).")
    m4.metric("Groups analysed", len(group_ids))

    if _src:
        st.caption(
            f"Data source: "
            f"{os.path.relpath(_src, _ROOT) if _src.startswith(_ROOT) else _src} "
            f"(updated: {_fmt_mtime(_src)})."
        )

    if baseline is not None:
        if is_feasible:
            st.success(
                "No bottleneck detected in the last run: the schedule is "
                "feasible as-is. You can still explore hypothetical scenarios "
                "below (exploratory mode)."
            )
        else:
            st.error(
                f"{n_bottlenecks} capacity bottleneck(s) detected. Review the "
                "automatic suggestions below to identify the most effective "
                "corrective actions."
            )

    if bottlenecks_reported:
        with st.expander("Bottlenecks reported by the last solver diagnostic"):
            st.dataframe(bottlenecks_reported, use_container_width=True)

    # ── Section 1 — Automatic suggestions ──────────────────────────────
    st.header("Step 3 — Automatic suggestions")
    st.caption(
        "Analyses the detected bottlenecks to propose groups to exclude or "
        "resources to add, ranked by decreasing impact. This is the "
        "recommended starting point when the schedule is infeasible."
    )

    _auto_analyze = (not is_feasible) and bool(sessions)
    if st.button("Analyse and suggest", key="run_suggest",
                 disabled=not sessions) or (
            _auto_analyze and "sim_suggestions" not in st.session_state):
        try:
            st.session_state["sim_suggestions"] = se.suggest_actions(sessions)
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Analysis failed: {exc}")

    sug = st.session_state.get("sim_suggestions")
    if sug:
        if sug["feasible"]:
            st.success("No bottleneck detected: the schedule is feasible "
                       "as-is. No corrective action is required.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Groups to exclude (by impact)**")
            st.caption(
                "Removing a group frees its session weeks on the congested "
                "slot. Impact = weeks freed."
            )
            if sug["exclude_groups"]:
                st.dataframe(sug["exclude_groups"], use_container_width=True)
                st.session_state["suggested_exclude"] = [
                    g["group_id"] for g in sug["exclude_groups"]
                ]
            else:
                st.caption("No exclusion suggestion.")
        with s2:
            st.markdown("**Resources to add**")
            st.caption(
                "Opening extra weeks on a slot (room × day × block) absorbs "
                "the detected overflow."
            )
            if sug["add_resources"]:
                st.dataframe(sug["add_resources"], use_container_width=True)
            else:
                st.caption("No resource suggestion.")

    if st.session_state.get("suggested_exclude"):
        if st.button("Apply the exclusion suggestion", key="apply_sug"):
            try:
                result = se.simulate_without_groups(
                    sessions, st.session_state["suggested_exclude"])
                st.markdown("**Result of the applied suggestion:**")
                _render_diff(result)
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Simulation failed: {exc}")

    # ── Section 2 — Exclude groups (manual scenario) ───────────────────
    st.header("Step 4 — Manual scenario: exclude groups")
    st.caption(
        "Select groups to remove to estimate the feasibility gain and the "
        "number of impacted students. Useful to test a specific hypothesis "
        "(e.g. a group flagged by the dean's office)."
    )

    selected_groups = st.multiselect(
        "Groups to exclude", options=group_ids, key="excl_groups",
    )
    run_excl = st.button("Run the simulation", key="run_excl",
                         disabled=not (sessions and selected_groups))
    if run_excl:
        try:
            result = se.simulate_without_groups(sessions, selected_groups)
            _render_diff(result)
            r1, r2 = st.columns(2)
            r1.metric("Sessions removed", result["removed_sessions"],
                      help="Number of lab sessions removed from the "
                           "hypothetical schedule.")
            r2.metric("Impacted students", result["affected_students"],
                      help="Students in the excluded groups, who would need "
                           "to be placed elsewhere.")
            with st.expander("Details of remaining bottlenecks"):
                st.dataframe(result["after"]["bottlenecks"][:20],
                             use_container_width=True)
            # Optional real CP-SAT dry-run on the reduced session list.
            kept = [s for s in sessions
                    if str(s["group_id"]) not in set(selected_groups)]
            dry = se.dry_run_feasibility(kept, time_limit=15)
            st.caption(f"CP-SAT check (dry-run): status = {dry.get('status')}, "
                       f"time = {dry.get('wall_time_s', 'n/a')}s")
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Simulation failed: {exc}")

    # ── Section 3 — Add resources (manual scenario) ────────────────────
    st.header("Step 5 — Manual scenario: add resources")
    st.caption(
        "Add capacity (room × day × block) and estimate the potential "
        "placement gain. Useful to negotiate opening an additional slot with "
        "the aulario (room booking office)."
    )

    with st.form("add_res_form"):
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            res_name = st.text_input("Room / resource", value="")
        with fc2:
            res_day = st.selectbox("Day", options=list(range(5)),
                                   format_func=lambda i: DAYS_EN[i])
        with fc3:
            res_block = st.text_input("Time block (block_id)", value="")
        with fc4:
            res_weeks = st.number_input("Weeks added", min_value=1,
                                        max_value=20, value=1, step=1)
        submitted = st.form_submit_button("Test the scenario",
                                          disabled=not sessions)

    if submitted:
        if not res_name.strip() or not res_block.strip():
            st.error("Please fill in the room and the time block.")
        else:
            try:
                extra = [{
                    "resource": res_name.strip(),
                    "day_idx": int(res_day),
                    "block_id": res_block.strip(),
                    "weeks": int(res_weeks),
                }]
                result = se.simulate_with_extra_capacity(sessions, extra)
                _render_diff(result)
                st.metric("Capacity added (weeks)", result["added_capacity"])
                with st.expander("Details of remaining bottlenecks"):
                    st.dataframe(result["after"]["bottlenecks"][:20],
                                 use_container_width=True)
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Simulation failed: {exc}")
