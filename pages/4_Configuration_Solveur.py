"""
pages/4_Configuration_Solveur.py — Phase 2, Feature 1 UI.

Interactive panel to configure the solver's SOFT constraints: pick a preset
profile (Strict / Balanced / Relaxed), fine-tune individual weights, toggle
constraints on/off, preview the live configuration and save it to
``config/solver_constraints.yaml``.

Additive page: it does not touch the validated ``app.py`` navigation. All UI
labels are in French per project convention; no emojis are used.
"""

from __future__ import annotations

import os
import sys

import streamlit as st

# Make the repository root importable when Streamlit runs this file from pages/.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import solver_config as sc  # noqa: E402

try:
    import loyola_theme
except Exception:  # pragma: no cover - theme is cosmetic
    loyola_theme = None


st.set_page_config(
    page_title="Configuration du solveur — Universidad Loyola",
    page_icon="C",
    layout="wide",
)

if loyola_theme is not None:
    try:
        loyola_theme.inject_theme()
    except Exception:
        pass


st.title("Configuration des contraintes du solveur")
st.caption(
    "Ajustez les contraintes SOUPLES (preferences) du solveur CP-SAT. "
    "Les contraintes DURES (C1 chevauchement, C4 semaines >= credits, "
    "C5 pas de double labo le meme jour) restent toujours actives et ne sont "
    "pas modifiables ici."
)

# ---------------------------------------------------------------------------
# Load current configuration into session state (once).
# ---------------------------------------------------------------------------
if "solver_cfg" not in st.session_state:
    st.session_state.solver_cfg = sc.load_config()

cfg = st.session_state.solver_cfg


# ---------------------------------------------------------------------------
# Profile selector
# ---------------------------------------------------------------------------
st.subheader("1. Profil predefini")
st.write(
    "Appliquez un profil en un clic. 'Personnalise' apparait des que vous "
    "modifiez un poids manuellement."
)

profile_names = list(sc.PRESETS.keys())
current_profile = sc.detect_profile(cfg)
col_a, col_b, col_c, col_d = st.columns([1, 1, 1, 2])
with col_a:
    if st.button("Strict", use_container_width=True):
        st.session_state.solver_cfg = sc.apply_profile("Strict")
        st.rerun()
with col_b:
    if st.button("Equilibre (Balanced)", use_container_width=True):
        st.session_state.solver_cfg = sc.apply_profile("Balanced")
        st.rerun()
with col_c:
    if st.button("Detendu (Relaxed)", use_container_width=True):
        st.session_state.solver_cfg = sc.apply_profile("Relaxed")
        st.rerun()
with col_d:
    st.metric("Profil actuel", current_profile)


# ---------------------------------------------------------------------------
# Per-constraint controls
# ---------------------------------------------------------------------------
st.subheader("2. Reglage fin des contraintes souples")

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
                key=f"en_{key}",
            )
        with c2:
            st.markdown(f"**{label}**")
            st.caption(help_txt)
        weight = st.slider(
            "Poids (importance relative)",
            min_value=sc.MIN_WEIGHT, max_value=1000,
            value=min(int(entry["weight"]), 1000),
            step=10, key=f"w_{key}",
            disabled=not enabled,
        )
        new_soft[key] = {"enabled": enabled, "weight": weight}

# Rebuild the working config from the widgets.
working_cfg = {
    "active_profile": sc.detect_profile({"soft_constraints": new_soft}),
    "soft_constraints": new_soft,
}
st.session_state.solver_cfg = working_cfg


# ---------------------------------------------------------------------------
# Warnings for extreme configurations
# ---------------------------------------------------------------------------
warnings = sc.is_extreme(working_cfg)
for w in warnings:
    st.warning(w)


# ---------------------------------------------------------------------------
# Live preview
# ---------------------------------------------------------------------------
st.subheader("3. Apercu de la configuration")
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


# ---------------------------------------------------------------------------
# Save / Reset
# ---------------------------------------------------------------------------
st.subheader("4. Enregistrer / Reinitialiser")
save_col, reset_col = st.columns(2)

with save_col:
    confirm = st.checkbox("Je confirme l'enregistrement de cette configuration")
    if st.button("Enregistrer la configuration", type="primary",
                 disabled=not confirm or bool(errors),
                 use_container_width=True):
        try:
            path = sc.save_config(working_cfg)
            st.success(f"Configuration enregistree dans : {path}")
        except Exception as exc:  # pragma: no cover - UI feedback
            st.error(f"Echec de l'enregistrement : {exc}")

with reset_col:
    if st.button("Reinitialiser aux valeurs par defaut (Balanced)",
                 use_container_width=True):
        st.session_state.solver_cfg = sc.apply_profile("Balanced")
        st.rerun()

st.divider()
st.caption(
    "Rappel : si le fichier de configuration est absent ou invalide, le "
    "solveur applique automatiquement le profil 'Balanced' (comportement "
    "historique). La configuration est prise en compte au prochain lancement "
    "de l'optimisation."
)
