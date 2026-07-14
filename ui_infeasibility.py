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
    """Audit métier de la solution via diagnostics.audit_schedule (read-only).

    Retourne le dict d'audit ou None. ``mtime`` sert de clé de fraîcheur.
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
        return "inconnue"


def _render_diff(result: dict) -> None:
    """Render the before/after diff metrics of a simulation result."""
    diff = result["diff"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faisable avant", "Oui" if diff["feasible_before"] else "Non")
    c2.metric("Faisable après", "Oui" if diff["feasible_after"] else "Non")
    c3.metric("Goulots (après)", diff["n_bottlenecks_after"],
              delta=diff["n_bottlenecks_after"] - diff["n_bottlenecks_before"])
    c4.metric("Réduction dépassement", diff["overflow_reduction"],
              help="Nombre de semaines de demande excédentaire éliminées "
                   "par ce scénario.")
    if diff["became_feasible"]:
        st.success("Scénario prometteur : le planning devient FAISABLE.")
    elif diff["overflow_reduction"] > 0:
        st.info("Amélioration partielle : dépassement réduit mais non nul.")
    else:
        st.warning("Aucune amélioration mesurable avec ce scénario.")


_TYPE_LABELS_FR = {
    "tiny_group": "Groupe sous-dimensionné",
    "wrong_period": "Séance hors-période",
    "oversubscription": "Matière sur-souscrite",
    "bottleneck": "Goulot d'étranglement",
    "credit_overload": "Surcharge professeur",
}
_SEV_LABELS_FR = {
    "critique": "Critique",
    "avertissement": "Avertissement",
    "info": "Info",
}


def _render_business_audit() -> None:
    """Surface l'audit métier (diagnostics.audit_schedule) dans le simulateur.

    Démontre la thèse centrale : un statut solveur « OPTIMAL » ne garantit pas
    une solution CONFORME. Affiche les anomalies détectées dans le planning
    produit et le remède PROPOSÉ (chiffré) pour chacune.
    """
    st.header("Audit métier de la solution (au-delà du statut solveur)")
    st.caption(
        "Un statut solveur « OPTIMAL » signifie seulement que le modèle a "
        "trouvé une affectation des semaines respectant ses contraintes dures. "
        "Il ne garantit PAS que la solution est conforme aux règles de "
        "l'établissement : le pré-traitement peut absorber une infaisabilité "
        "en déformant la solution (groupes minuscules/solo, séances "
        "hors-période). Cet audit scanne le planning produit et propose un "
        "remède chiffré pour chaque anomalie (jamais appliqué automatiquement)."
    )

    sched = _find_schedule_source()
    if not sched:
        st.warning(
            "Planning optimisé introuvable (optimized_schedule_v5.csv). Lancez "
            "d'abord une optimisation pour alimenter l'audit."
        )
        return

    audit = _load_audit(sched, os.path.getmtime(sched))
    if audit is None:
        st.warning("Audit indisponible (lecture du planning impossible).")
        return

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Anomalies détectées", audit.get("n_total", 0))
    a2.metric("Dont critiques", audit.get("n_critical", 0))
    a3.metric("Groupes analysés", audit.get("n_groups_analyzed", 0))
    a4.metric("Verdict",
              "CONFORME" if audit.get("healthy") else "À CORRIGER")

    if audit.get("healthy"):
        st.success(
            "Aucune anomalie métier détectée : tous les groupes respectent la "
            "taille minimale et la période attendue pour leur niveau."
        )
        return

    st.error(
        f"{audit.get('n_total', 0)} anomalie(s) métier détectée(s) malgré un "
        f"statut solveur potentiellement « OPTIMAL » — la preuve que "
        f"« OPTIMAL » ≠ « conforme »."
    )

    by_type = audit.get("by_type", {})
    if by_type:
        st.markdown("**Synthèse par type d'anomalie**")
        st.table({
            "Type": [_TYPE_LABELS_FR.get(k, k) for k in by_type],
            "Nombre": list(by_type.values()),
        })

    st.markdown("**Détail des anomalies et remèdes proposés**")
    rows = []
    for an in audit.get("anomalies", []):
        rows.append({
            "Niveau": an.get("level", ""),
            "Sem.": an.get("semester", ""),
            "Matière": an.get("subject", ""),
            "Grp.": str(an.get("grupo", "")),
            "Sévérité": _SEV_LABELS_FR.get(an.get("severity"),
                                           an.get("severity", "")),
            "Anomalie": an.get("detail", ""),
            "Remède proposé (chiffré)": (an.get("remedy") or {}).get("text", ""),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "Ces mêmes anomalies et remèdes sont exportés dans la feuille Excel "
        "« Diagnostic & Remèdes » de chaque classeur généré."
    )
    st.divider()


def render() -> None:
    """Render the infeasibility simulator inside the main app navigation."""
    # NOTE: the page title is already rendered by app.py via page_header();
    # we intentionally do not repeat it here to avoid a duplicate heading.
    st.info(
        "Cet outil est en LECTURE SEULE. Aucune donnée d'optimisation réelle "
        "n'est modifiée. Les résultats sont des estimations basées sur le modèle "
        "de capacité (mêmes règles que le diagnostic du solveur)."
    )

    _render_business_audit()

    # ── Data loading (best effort, read-only) with freshness tracking ──
    _src = _find_sessions_source()
    sessions = _load_sessions(_src, os.path.getmtime(_src) if _src else 0.0)
    unplaced = se.load_unplaced_students()
    bottlenecks_reported = se.load_bottlenecks_from_reports()

    if not sessions:
        st.warning(
            "Aucune donnée de groupes trouvée (group_composition.csv). Lancez "
            "d'abord une optimisation pour alimenter le simulateur."
        )

    group_ids = sorted({str(s["group_id"]) for s in sessions})

    # ── At-a-glance summary of the latest run ──────────────────────────
    st.header("État du dernier run")

    baseline = se.analyze_bottlenecks(sessions) if sessions else None
    is_feasible = bool(baseline and baseline.get("feasible"))
    n_bottlenecks = len(baseline.get("bottlenecks", [])) if baseline else 0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Faisabilité estimée", "FAISABLE" if is_feasible else
              ("INFAISABLE" if baseline else "n/d"))
    m2.metric("Goulots détectés", n_bottlenecks,
              help="Créneaux (salle × jour × bloc) où la demande "
                   "en semaines dépasse la capacité disponible.")
    m3.metric("Étudiants non placés", len(unplaced),
              help="Étudiants sans groupe dans le dernier run réel "
                   "(reports/unplaced_students.json).")
    m4.metric("Groupes analysés", len(group_ids))

    if _src:
        st.caption(
            f"Source des données : "
            f"{os.path.relpath(_src, _ROOT) if _src.startswith(_ROOT) else _src} "
            f"(mise à jour : {_fmt_mtime(_src)})."
        )

    if baseline is not None:
        if is_feasible:
            st.success(
                "Aucun goulot détecté dans le dernier run : le planning est "
                "faisable en l'état. Vous pouvez tout de même explorer des "
                "scénarios hypothétiques ci-dessous (mode exploratoire)."
            )
        else:
            st.error(
                f"{n_bottlenecks} goulot(s) de capacité détecté(s). Consultez "
                "les suggestions automatiques ci-dessous pour identifier les "
                "actions correctives les plus efficaces."
            )

    if bottlenecks_reported:
        with st.expander("Goulots rapportés par le dernier diagnostic du solveur"):
            st.json(bottlenecks_reported)

    # ── Section 1 — Automatic suggestions ──────────────────────────────
    st.header("1. Suggestions automatiques")
    st.caption(
        "Analyse des goulots détectés pour proposer les groupes à exclure ou les "
        "ressources à ajouter, classés par impact décroissant. C'est le point de "
        "départ recommandé en cas d'infaisabilité."
    )

    _auto_analyze = (not is_feasible) and bool(sessions)
    if st.button("Analyser et suggérer", key="run_suggest",
                 disabled=not sessions) or (
            _auto_analyze and "sim_suggestions" not in st.session_state):
        try:
            st.session_state["sim_suggestions"] = se.suggest_actions(sessions)
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Échec de l'analyse : {exc}")

    sug = st.session_state.get("sim_suggestions")
    if sug:
        if sug["feasible"]:
            st.success("Aucun goulot détecté : le planning est faisable en "
                       "l'état. Aucune action corrective n'est nécessaire.")
        s1, s2 = st.columns(2)
        with s1:
            st.markdown("**Groupes à exclure (par impact)**")
            st.caption(
                "Retirer un groupe libère ses semaines de séances sur le "
                "créneau en tension. Impact = semaines libérées."
            )
            if sug["exclude_groups"]:
                st.dataframe(sug["exclude_groups"], use_container_width=True)
                st.session_state["suggested_exclude"] = [
                    g["group_id"] for g in sug["exclude_groups"]
                ]
            else:
                st.caption("Aucune suggestion d'exclusion.")
        with s2:
            st.markdown("**Ressources à ajouter**")
            st.caption(
                "Ouvrir des semaines supplémentaires sur un créneau "
                "(salle × jour × bloc) absorbe le dépassement détecté."
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
                st.markdown("**Résultat de la suggestion appliquée :**")
                _render_diff(result)
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Échec de la simulation : {exc}")

    # ── Section 2 — Exclude groups (manual scenario) ───────────────────
    st.header("2. Simulation manuelle : exclure des groupes")
    st.caption(
        "Sélectionnez des groupes à retirer pour estimer le gain de faisabilité "
        "et le nombre d'étudiants impactés. Utile pour tester une hypothèse "
        "précise (ex. un groupe signalé par le décanat)."
    )

    selected_groups = st.multiselect(
        "Groupes à exclure", options=group_ids, key="excl_groups",
    )
    run_excl = st.button("Lancer la simulation", key="run_excl",
                         disabled=not (sessions and selected_groups))
    if run_excl:
        try:
            result = se.simulate_without_groups(sessions, selected_groups)
            _render_diff(result)
            r1, r2 = st.columns(2)
            r1.metric("Sessions retirées", result["removed_sessions"],
                      help="Nombre de séances de laboratoire supprimées du "
                           "planning hypothétique.")
            r2.metric("Étudiants impactés", result["affected_students"],
                      help="Étudiants membres des groupes exclus, qui devraient "
                           "être replacés ailleurs.")
            with st.expander("Détails des goulots restants"):
                st.json(result["after"]["bottlenecks"][:20])
            # Optional real CP-SAT dry-run on the reduced session list.
            kept = [s for s in sessions
                    if str(s["group_id"]) not in set(selected_groups)]
            dry = se.dry_run_feasibility(kept, time_limit=15)
            st.caption(f"Vérification CP-SAT (dry-run) : statut = {dry.get('status')}, "
                       f"temps = {dry.get('wall_time_s', 'n/a')}s")
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Échec de la simulation : {exc}")

    # ── Section 3 — Add resources (manual scenario) ────────────────────
    st.header("3. Simulation manuelle : ajouter des ressources")
    st.caption(
        "Ajoutez de la capacité (salle × jour × bloc) et estimez le gain de "
        "placement potentiel. Utile pour négocier l'ouverture d'un créneau "
        "supplémentaire auprès de l'aulario."
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
            res_weeks = st.number_input("Semaines ajoutées", min_value=1,
                                        max_value=20, value=1, step=1)
        submitted = st.form_submit_button("Tester le scénario",
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
                st.metric("Capacité ajoutée (semaines)", result["added_capacity"])
                with st.expander("Détails des goulots restants"):
                    st.json(result["after"]["bottlenecks"][:20])
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Échec de la simulation : {exc}")
