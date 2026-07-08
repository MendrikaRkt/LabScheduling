"""
ui_solver_constraints.py — Embeddable solver soft-constraint configuration UI.

Consolidation of the former standalone page ``pages/4_Configuration_Solveur.py``
into a reusable component so that the solver constraints appear as a section
of the single Configuration page in ``app.py`` (user request: one and only
one configuration page).

The component keeps the exact same behaviour as the standalone page:
- Preset profiles (Strict / Balanced / Relaxed) applied in one click.
- Per-constraint enable toggle and weight slider.
- Extreme-configuration warnings, live preview, validation.
- Persistence to ``config/solver_constraints.yaml`` via ``solver_config``.

All UI labels are in French per project convention; no emojis are used.
"""

from __future__ import annotations

import streamlit as st

import solver_config as sc


def render_solver_constraints_section() -> None:
    """Render the solver soft-constraint panel (embeddable in a tab).

    Uses ``st.session_state.solver_cfg`` as working state and persists to
    ``config/solver_constraints.yaml`` through :mod:`solver_config`.
    """
    st.caption(
        "Ajustez les contraintes SOUPLES (preferences) du solveur CP-SAT. "
        "Les contraintes DURES (C1 chevauchement, C4 semaines >= credits, "
        "C5 pas de double labo le meme jour) restent toujours actives et ne "
        "sont pas modifiables ici."
    )

    # Load current configuration into session state (once).
    if "solver_cfg" not in st.session_state:
        st.session_state.solver_cfg = sc.load_config()

    cfg = st.session_state.solver_cfg

    # ── Profile selector ──────────────────────────────────────────────
    st.markdown("##### Profil predefini")
    st.caption(
        "Appliquez un profil en un clic. 'Personnalise' apparait des que "
        "vous modifiez un poids manuellement."
    )

    current_profile = sc.detect_profile(cfg)
    col_a, col_b, col_c, col_d = st.columns([1, 1, 1, 2])
    with col_a:
        if st.button("Strict", use_container_width=True, key="scfg_strict"):
            st.session_state.solver_cfg = sc.apply_profile("Strict")
            _sync_widget_state()
            st.rerun()
    with col_b:
        if st.button("Equilibre (Balanced)", use_container_width=True,
                     key="scfg_balanced"):
            st.session_state.solver_cfg = sc.apply_profile("Balanced")
            _sync_widget_state()
            st.rerun()
    with col_c:
        if st.button("Detendu (Relaxed)", use_container_width=True,
                     key="scfg_relaxed"):
            st.session_state.solver_cfg = sc.apply_profile("Relaxed")
            _sync_widget_state()
            st.rerun()
    with col_d:
        st.metric("Profil actuel", current_profile)

    # ── Per-constraint controls ───────────────────────────────────────
    st.markdown("##### Reglage fin des contraintes souples")

    new_soft = {}
    for key in sc.SOFT_CONSTRAINT_KEYS:
        entry = cfg["soft_constraints"][key]
        label = sc.CONSTRAINT_LABELS_FR.get(key, key)
        help_txt = sc.CONSTRAINT_HELP_FR.get(key, "")
        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1:
                enabled = st.toggle(
                    "Activee", value=bool(entry["enabled"]),
                    key=f"scfg_en_{key}",
                )
            with c2:
                st.markdown(f"**{label}**")
                st.caption(help_txt)
            weight = st.slider(
                "Poids (importance relative)",
                min_value=sc.MIN_WEIGHT, max_value=1000,
                value=min(int(entry["weight"]), 1000),
                step=10, key=f"scfg_w_{key}",
                disabled=not enabled,
            )
            new_soft[key] = {"enabled": enabled, "weight": weight}

    # Rebuild the working config from the widgets.
    working_cfg = {
        "active_profile": sc.detect_profile({"soft_constraints": new_soft}),
        "soft_constraints": new_soft,
    }
    st.session_state.solver_cfg = working_cfg

    # ── Warnings for extreme configurations ───────────────────────────
    for w in sc.is_extreme(working_cfg):
        st.warning(w)

    # ── Live preview ──────────────────────────────────────────────────
    with st.expander("Apercu de la configuration effective"):
        summary = sc.config_summary(working_cfg)
        prev1, prev2 = st.columns(2)
        with prev1:
            st.markdown("**Poids effectifs (0 = desactivee)**")
            st.json(summary["weights"])
        with prev2:
            st.markdown("**Etat des contraintes**")
            st.json(summary["enabled"])

    errors = sc.validate_config(working_cfg)
    if errors:
        st.error("Configuration invalide :\n\n- " + "\n- ".join(errors))

    # ── Save / Reset ──────────────────────────────────────────────────
    save_col, reset_col = st.columns(2)
    with save_col:
        confirm = st.checkbox(
            "Je confirme l'enregistrement de cette configuration",
            key="scfg_confirm",
        )
        if st.button("Enregistrer la configuration du solveur", type="primary",
                     disabled=not confirm or bool(errors),
                     use_container_width=True, key="scfg_save"):
            try:
                path = sc.save_config(working_cfg)
                st.success(f"Configuration enregistree dans : {path}")
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Echec de l'enregistrement : {exc}")
    with reset_col:
        if st.button("Reinitialiser aux valeurs par defaut (Balanced)",
                     use_container_width=True, key="scfg_reset"):
            st.session_state.solver_cfg = sc.apply_profile("Balanced")
            _sync_widget_state()
            st.rerun()

    st.caption(
        "Rappel : si le fichier de configuration est absent ou invalide, le "
        "solveur applique automatiquement le profil 'Balanced' (comportement "
        "historique). La configuration est prise en compte au prochain "
        "lancement de l'optimisation."
    )


def _sync_widget_state() -> None:
    """Push the session config back into the widget keys after a profile
    change so toggles and sliders reflect the newly applied profile."""
    cfg = st.session_state.get("solver_cfg") or {}
    for key, entry in (cfg.get("soft_constraints") or {}).items():
        st.session_state[f"scfg_en_{key}"] = bool(entry.get("enabled", True))
        st.session_state[f"scfg_w_{key}"] = min(int(entry.get("weight", 0)), 1000)
