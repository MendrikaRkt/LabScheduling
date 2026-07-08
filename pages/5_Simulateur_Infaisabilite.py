"""
pages/5_Simulateur_Infaisabilite.py — Phase 2, Feature 2 UI.

A read-only "What-If" tool to explore how the schedule feasibility would change
if some groups were excluded or extra room/time-slot capacity were added. It
never modifies the real optimisation data; it only reads existing artifacts
from ``reports/`` and reconstructs a hypothetical session list.

Additive page: it does not touch the validated ``app.py`` navigation. All UI
labels are in French per project convention; no emojis are used.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import simulation_engine as se  # noqa: E402

try:
    import loyola_theme
except Exception:  # pragma: no cover - theme is cosmetic
    loyola_theme = None

# Optional: pull real lab rooms from the pipeline config to enrich sessions.
try:
    import pipeline as _pipeline
    _LAB_ROOMS = {
        subj: cfg.get("lab_rooms", [])
        for subj, cfg in getattr(_pipeline, "LAB_CONFIG", {}).items()
    }
except Exception:
    _LAB_ROOMS = {}


st.set_page_config(
    page_title="Simulateur d'infaisabilite — Universidad Loyola",
    page_icon="S",
    layout="wide",
)

if loyola_theme is not None:
    try:
        loyola_theme.inject_theme()
    except Exception:
        pass


DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]

st.title("Simulateur d'infaisabilite (analyse What-If)")
st.info(
    "Cet outil est en LECTURE SEULE. Aucune donnee d'optimisation reelle n'est "
    "modifiee. Les resultats sont des estimations basees sur le modele de "
    "capacite (memes regles que le diagnostic du solveur)."
)


# ---------------------------------------------------------------------------
# Data loading (best effort, read-only)
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_sessions() -> list:
    """Reconstruct a hypothetical session list from group_composition.csv."""
    candidates = [
        os.path.join(_ROOT, "data_clean", "group_composition.csv"),
        os.path.join(_ROOT, "group_composition.csv"),
        "/home/ubuntu/Shared/Uploads/group_composition.csv",
    ]
    for path in candidates:
        if os.path.exists(path):
            sessions = se.build_sessions_from_group_composition(
                path, lab_rooms_by_subject=_LAB_ROOMS)
            if sessions:
                return sessions
    return []


sessions = _load_sessions()
unplaced = se.load_unplaced_students()
bottlenecks_reported = se.load_bottlenecks_from_reports()

if not sessions:
    st.warning(
        "Aucune donnee de groupes trouvee (group_composition.csv). Lancez "
        "d'abord une optimisation pour alimenter le simulateur."
    )

group_ids = sorted({str(s["group_id"]) for s in sessions})


def _render_diff(result: dict) -> None:
    """Render the before/after diff metrics of a simulation result."""
    diff = result["diff"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faisable avant", "Oui" if diff["feasible_before"] else "Non")
    c2.metric("Faisable apres", "Oui" if diff["feasible_after"] else "Non")
    c3.metric("Goulots (apres)", diff["n_bottlenecks_after"],
              delta=diff["n_bottlenecks_after"] - diff["n_bottlenecks_before"])
    c4.metric("Reduction depassement", diff["overflow_reduction"])
    if diff["became_feasible"]:
        st.success("Scenario prometteur : le planning devient FAISABLE.")
    elif diff["overflow_reduction"] > 0:
        st.info("Amelioration partielle : depassement reduit mais non nul.")
    else:
        st.warning("Aucune amelioration mesurable avec ce scenario.")


# ---------------------------------------------------------------------------
# Section 1 — Exclude groups
# ---------------------------------------------------------------------------
st.header("1. Simulation : exclure des groupes")
st.caption(
    "Selectionnez des groupes a retirer pour estimer le gain de faisabilite et "
    "le nombre d'etudiants impactes."
)

selected_groups = st.multiselect(
    "Groupes a exclure", options=group_ids, key="excl_groups",
)
run_excl = st.button("Lancer la simulation", key="run_excl",
                     disabled=not (sessions and selected_groups))
if run_excl:
    try:
        result = se.simulate_without_groups(sessions, selected_groups)
        _render_diff(result)
        r1, r2 = st.columns(2)
        r1.metric("Sessions retirees", result["removed_sessions"])
        r2.metric("Etudiants impactes", result["affected_students"])
        with st.expander("Details des goulots restants"):
            st.json(result["after"]["bottlenecks"][:20])
        # Optional real CP-SAT dry-run on the reduced session list.
        kept = [s for s in sessions
                if str(s["group_id"]) not in set(selected_groups)]
        dry = se.dry_run_feasibility(kept, time_limit=15)
        st.caption(f"Verification CP-SAT (dry-run) : statut = {dry.get('status')}, "
                   f"temps = {dry.get('wall_time_s', 'n/a')}s")
    except Exception as exc:  # pragma: no cover - UI feedback
        st.error(f"Echec de la simulation : {exc}")


# ---------------------------------------------------------------------------
# Section 2 — Add resources
# ---------------------------------------------------------------------------
st.header("2. Simulation : ajouter des ressources")
st.caption(
    "Ajoutez de la capacite (salle x jour x bloc) et estimez le gain de "
    "placement potentiel."
)

with st.form("add_res_form"):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        res_name = st.text_input("Salle / ressource", value="")
    with fc2:
        res_day = st.selectbox("Jour", options=list(range(5)),
                               format_func=lambda i: DAYS_FR[i])
    with fc3:
        res_block = st.text_input("Bloc horaire (block_id)", value="")
    with fc4:
        res_weeks = st.number_input("Semaines ajoutees", min_value=1,
                                    max_value=20, value=1, step=1)
    submitted = st.form_submit_button("Tester le scenario",
                                      disabled=not sessions)

if submitted:
    if not res_name.strip() or not res_block.strip():
        st.error("Veuillez renseigner la salle et le bloc horaire.")
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
            st.metric("Capacite ajoutee (semaines)", result["added_capacity"])
            with st.expander("Details des goulots restants"):
                st.json(result["after"]["bottlenecks"][:20])
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Echec de la simulation : {exc}")


# ---------------------------------------------------------------------------
# Section 3 — Automatic suggestions
# ---------------------------------------------------------------------------
st.header("3. Suggestions automatiques")
st.caption(
    "Analyse des goulots detectes pour proposer des groupes a exclure ou des "
    "ressources a ajouter."
)

if unplaced:
    st.metric("Etudiants non places (dernier run)", len(unplaced))
if bottlenecks_reported:
    with st.expander("Goulots rapportes par le dernier diagnostic"):
        st.json(bottlenecks_reported)

if st.button("Analyser et suggerer", key="run_suggest", disabled=not sessions):
    try:
        sug = se.suggest_actions(sessions)
        if sug["feasible"]:
            st.success("Aucun goulot detecte : le planning est faisable en l'etat.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Groupes a exclure (par impact)**")
            if sug["exclude_groups"]:
                st.dataframe(sug["exclude_groups"], use_container_width=True)
                st.session_state["suggested_exclude"] = [
                    g["group_id"] for g in sug["exclude_groups"]
                ]
            else:
                st.caption("Aucune suggestion d'exclusion.")
        with s2:
            st.markdown("**Ressources a ajouter**")
            if sug["add_resources"]:
                st.dataframe(sug["add_resources"], use_container_width=True)
            else:
                st.caption("Aucune suggestion de ressource.")
    except Exception as exc:  # pragma: no cover - UI feedback
        st.error(f"Echec de l'analyse : {exc}")

if st.session_state.get("suggested_exclude"):
    if st.button("Appliquer la suggestion d'exclusion", key="apply_sug"):
        try:
            result = se.simulate_without_groups(
                sessions, st.session_state["suggested_exclude"])
            st.markdown("**Resultat de la suggestion appliquee :**")
            _render_diff(result)
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Echec de la simulation : {exc}")
