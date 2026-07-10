"""
ui_infeasibility.py — Infeasibility "What-If" simulator (render module).

This is the same read-only simulator that previously lived under
``pages/4_Simulateur_Infaisabilite.py``. It has been converted into a
``render()`` module so it appears inside the app's single, consistent
sidebar navigation (radio) instead of as a separate Streamlit multipage
entry — see Point 4 of the consolidation request.

Read-only tool: it never modifies the real optimisation data; it only reads
existing artifacts from ``reports/`` and reconstructs a hypothetical session
list. All UI labels are in French per project convention; no emojis are used.
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


DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi"]

_REL_CANDIDATES = [
    os.path.join("outputs", "optimization", "group_composition.csv"),
    os.path.join("data_clean", "group_composition.csv"),
    "group_composition.csv",
]


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
        return "inconnue"


def _render_diff(result: dict) -> None:
    """Render the before/after diff metrics of a simulation result."""
    diff = result["diff"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faisable avant", "Oui" if diff["feasible_before"] else "Non")
    c2.metric("Faisable apres", "Oui" if diff["feasible_after"] else "Non")
    c3.metric("Goulots (apres)", diff["n_bottlenecks_after"],
              delta=diff["n_bottlenecks_after"] - diff["n_bottlenecks_before"])
    c4.metric("Reduction depassement", diff["overflow_reduction"],
              help="Nombre de semaines de demande excedentaire eliminees "
                   "par ce scenario.")
    if diff["became_feasible"]:
        st.success("Scenario prometteur : le planning devient FAISABLE.")
    elif diff["overflow_reduction"] > 0:
        st.info("Amelioration partielle : depassement reduit mais non nul.")
    else:
        st.warning("Aucune amelioration mesurable avec ce scenario.")


def render() -> None:
    """Render the infeasibility simulator inside the main app navigation."""
    # NOTE: the page title is already rendered by app.py via page_header();
    # we intentionally do not repeat it here to avoid a duplicate heading.
    st.info(
        "Cet outil est en LECTURE SEULE. Aucune donnee d'optimisation reelle "
        "n'est modifiee. Les resultats sont des estimations basees sur le modele "
        "de capacite (memes regles que le diagnostic du solveur)."
    )

    # ── Data loading (best effort, read-only) with freshness tracking ──
    _src = _find_sessions_source()
    sessions = _load_sessions(_src, os.path.getmtime(_src) if _src else 0.0)
    unplaced = se.load_unplaced_students()
    bottlenecks_reported = se.load_bottlenecks_from_reports()

    if not sessions:
        st.warning(
            "Aucune donnee de groupes trouvee (group_composition.csv). Lancez "
            "d'abord une optimisation pour alimenter le simulateur."
        )

    group_ids = sorted({str(s["group_id"]) for s in sessions})

    # ── At-a-glance summary of the latest run ──────────────────────────
    st.header("Etat du dernier run")

    baseline = se.analyze_bottlenecks(sessions) if sessions else None
    is_feasible = bool(baseline and baseline.get("feasible"))
    n_bottlenecks = len(baseline.get("bottlenecks", [])) if baseline else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Faisabilite estimee", "FAISABLE" if is_feasible else
              ("INFAISABLE" if baseline else "n/d"))
    m2.metric("Goulots detectes", n_bottlenecks,
              help="Creneaux (salle x jour x bloc) ou matieres dont la demande "
                   "en semaines depasse la capacite disponible.")
    m3.metric("Etudiants non places", len(unplaced),
              help="Etudiants sans groupe dans le dernier run reel "
                   "(reports/unplaced_students.json).")
    m4.metric("Groupes analyses", len(group_ids))

    if _src:
        st.caption(
            f"Source des donnees : "
            f"{os.path.relpath(_src, _ROOT) if _src.startswith(_ROOT) else _src} "
            f"(mise a jour : {_fmt_mtime(_src)})."
        )

    if baseline is not None:
        if is_feasible:
            st.success(
                "Aucun goulot detecte dans le dernier run : le planning est "
                "faisable en l'etat. Vous pouvez tout de meme explorer des "
                "scenarios hypothetiques ci-dessous (mode exploratoire)."
            )
        else:
            st.error(
                f"{n_bottlenecks} goulot(s) de capacite detecte(s). Consultez "
                "les suggestions automatiques ci-dessous pour identifier les "
                "actions correctives les plus efficaces."
            )

    if bottlenecks_reported:
        with st.expander("Goulots rapportes par le dernier diagnostic du solveur"):
            st.json(bottlenecks_reported)

    # ── Section 1 — Automatic suggestions ──────────────────────────────
    st.header("1. Suggestions automatiques")
    st.caption(
        "Analyse des goulots detectes pour proposer les groupes a exclure ou les "
        "ressources a ajouter, classes par impact decroissant. C'est le point de "
        "depart recommande en cas d'infaisabilite."
    )

    _auto_analyze = (not is_feasible) and bool(sessions)
    if st.button("Analyser et suggerer", key="run_suggest",
                 disabled=not sessions) or (
            _auto_analyze and "sim_suggestions" not in st.session_state):
        try:
            st.session_state["sim_suggestions"] = se.suggest_actions(sessions)
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Echec de l'analyse : {exc}")

    sug = st.session_state.get("sim_suggestions")
    if sug:
        if sug["feasible"]:
            st.success("Aucun goulot detecte : le planning est faisable en "
                       "l'etat. Aucune action corrective n'est necessaire.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Groupes a exclure (par impact)**")
            st.caption(
                "Retirer un groupe libere ses semaines de seances sur le "
                "creneau en tension. Impact = semaines liberees."
            )
            if sug["exclude_groups"]:
                st.dataframe(sug["exclude_groups"], use_container_width=True)
                st.session_state["suggested_exclude"] = [
                    g["group_id"] for g in sug["exclude_groups"]
                ]
            else:
                st.caption("Aucune suggestion d'exclusion.")
        with s2:
            st.markdown("**Ressources a ajouter**")
            st.caption(
                "Ouvrir des semaines supplementaires sur un creneau "
                "(salle x jour x bloc) absorbe le depassement detecte."
            )
            if sug["add_resources"]:
                st.dataframe(sug["add_resources"], use_container_width=True)
            else:
                st.caption("Aucune suggestion de ressource.")

    if st.session_state.get("suggested_exclude"):
        if st.button("Appliquer la suggestion d'exclusion", key="apply_sug"):
            try:
                result = se.simulate_without_groups(
                    sessions, st.session_state["suggested_exclude"])
                st.markdown("**Resultat de la suggestion appliquee :**")
                _render_diff(result)
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Echec de la simulation : {exc}")

    # ── Section 2 — Exclude groups (manual scenario) ───────────────────
    st.header("2. Simulation manuelle : exclure des groupes")
    st.caption(
        "Selectionnez des groupes a retirer pour estimer le gain de faisabilite "
        "et le nombre d'etudiants impactes. Utile pour tester une hypothese "
        "precise (ex. un groupe signale par le decanat)."
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
            r1.metric("Sessions retirees", result["removed_sessions"],
                      help="Nombre de seances de laboratoire supprimees du "
                           "planning hypothetique.")
            r2.metric("Etudiants impactes", result["affected_students"],
                      help="Etudiants membres des groupes exclus, qui devraient "
                           "etre replaces ailleurs.")
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

    # ── Section 3 — Add resources (manual scenario) ────────────────────
    st.header("3. Simulation manuelle : ajouter des ressources")
    st.caption(
        "Ajoutez de la capacite (salle x jour x bloc) et estimez le gain de "
        "placement potentiel. Utile pour negocier l'ouverture d'un creneau "
        "supplementaire aupres de l'aulario."
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
