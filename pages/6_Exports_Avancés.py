"""
pages/6_Exports_Avancés.py — Phase 3 UI: enhanced Excel exports.

A read-only export console that builds richer, analysis-oriented Excel
workbooks on demand (colour-coded groups, room/professor/placement/time-slot
analysis, quality metrics), plus a small template renderer. It never modifies
the validated exporters or the optimisation data — it only reads existing
artifacts and writes new workbooks into the workspace.

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

import excel_export_enhanced as enhanced  # noqa: E402
import export_manager as manager  # noqa: E402
from excel_export_enhanced import ExportOptions  # noqa: E402

try:
    import loyola_theme
except Exception:  # pragma: no cover - theme is cosmetic
    loyola_theme = None


st.set_page_config(
    page_title="Exports avances — Universidad Loyola",
    page_icon="E",
    layout="wide",
)

if loyola_theme is not None:
    try:
        loyola_theme.inject_theme()
    except Exception:
        pass


st.title("Exports Excel avances")
st.info(
    "Cet outil est en LECTURE SEULE. Il ne modifie ni les donnees "
    "d'optimisation ni les exports valides (format Daniel). Il genere de "
    "nouveaux classeurs enrichis a partir des resultats existants."
)

prefs = manager.load_preferences()

# ────────────────────────────────────────────────────────────
# Sidebar-like configuration block
# ────────────────────────────────────────────────────────────
col_cfg, col_prev = st.columns([1, 1])

with col_cfg:
    st.subheader("Configuration")

    semester_label = st.selectbox(
        "Perimetre",
        ["Les deux semestres", "Semestre 1", "Semestre 2"],
        index=0,
    )
    semester = {"Les deux semestres": None, "Semestre 1": 1, "Semestre 2": 2}[
        semester_label
    ]

    fmt_labels = {
        "standard": "Standard (format Daniel, compatibilite)",
        "summary": "Resume (groupes + placement + qualite)",
        "enhanced": "Enrichi (toutes les feuilles)",
        "detailed": "Detaille (enrichi + feuilles protegees)",
    }
    default_fmt = prefs.get("default_format", "enhanced")
    fmt_keys = list(fmt_labels.keys())
    format_type = st.selectbox(
        "Format d'export",
        fmt_keys,
        index=fmt_keys.index(default_fmt) if default_fmt in fmt_keys else 2,
        format_func=lambda k: fmt_labels[k],
    )

    scheme_labels = {
        "loyola": "Loyola (bleu marine / or)",
        "default": "Defaut (bleu)",
        "monochrome": "Monochrome (gris)",
    }
    default_scheme = prefs.get("default_color_scheme", "loyola")
    scheme_keys = list(scheme_labels.keys())
    color_scheme = st.selectbox(
        "Palette de couleurs",
        scheme_keys,
        index=scheme_keys.index(default_scheme) if default_scheme in scheme_keys else 0,
        format_func=lambda k: scheme_labels[k],
    )

    st.markdown("**Feuilles a inclure**")
    base_opts = manager.resolve_options(format_type)
    c1, c2 = st.columns(2)
    with c1:
        opt_groups = st.checkbox("Groupes (couleurs)", value=base_opts.color_coded_groups)
        opt_legend = st.checkbox("Legende", value=base_opts.legend)
        opt_rooms = st.checkbox("Utilisation des salles", value=base_opts.room_utilization)
        opt_profs = st.checkbox("Charge des professeurs", value=base_opts.professor_workload)
    with c2:
        opt_place = st.checkbox("Placement des etudiants", value=base_opts.student_placement)
        opt_slots = st.checkbox("Analyse des creneaux", value=base_opts.time_slot_analysis)
        opt_quality = st.checkbox("Metriques de qualite", value=base_opts.quality_metrics)

    st.markdown("**Options de mise en forme**")
    c3, c4 = st.columns(2)
    with c3:
        opt_cf = st.checkbox("Mise en forme conditionnelle", value=base_opts.conditional_formatting)
        opt_filter = st.checkbox("Filtres automatiques", value=base_opts.auto_filter)
        opt_freeze = st.checkbox("Volets figes", value=base_opts.freeze_panes)
    with c4:
        opt_dv = st.checkbox("Listes deroulantes", value=base_opts.data_validation)
        opt_named = st.checkbox("Plages nommees", value=base_opts.named_ranges)
        opt_comments = st.checkbox("Commentaires de cellule", value=base_opts.cell_comments)
        opt_protect = st.checkbox("Proteger les feuilles", value=base_opts.protect_sheets)

    overrides = {
        "color_coded_groups": opt_groups,
        "legend": opt_legend,
        "room_utilization": opt_rooms,
        "professor_workload": opt_profs,
        "student_placement": opt_place,
        "time_slot_analysis": opt_slots,
        "quality_metrics": opt_quality,
        "conditional_formatting": opt_cf,
        "auto_filter": opt_filter,
        "freeze_panes": opt_freeze,
        "data_validation": opt_dv,
        "named_ranges": opt_named,
        "cell_comments": opt_comments,
        "protect_sheets": opt_protect,
    }

# ────────────────────────────────────────────────────────────
# Preview: quick data summary (read-only, no file written)
# ────────────────────────────────────────────────────────────
with col_prev:
    st.subheader("Apercu des donnees")
    try:
        sched = enhanced.load_schedule(semester)
        kpi = enhanced.load_kpi()
        if len(sched) == 0:
            st.warning(
                "Aucun planning trouve. Lancez d'abord l'optimisation pour "
                "generer outputs/optimization/optimized_schedule_v5.csv."
            )
        else:
            n_groups = sched.groupby(["semester", "subject", "grupo"]).ngroups
            m1, m2, m3 = st.columns(3)
            m1.metric("Seances", int(len(sched)))
            m2.metric("Groupes", int(n_groups))
            m3.metric("Salles", int(sched["lab_rooms"].nunique()))
            placement = (kpi or {}).get("placement", {})
            if placement:
                p1, p2 = st.columns(2)
                p1.metric("Inscrits", placement.get("enrolled", "n/d"))
                p2.metric("Placement %", placement.get("placement_pct", "n/d"))

            # Small preview table of the first groups.
            summary = enhanced._group_summary(sched)[:12]
            if summary:
                import pandas as pd
                prev = pd.DataFrame(summary)[
                    ["semester", "subject", "grupo", "students", "day",
                     "time_block", "room"]
                ]
                prev["status"] = prev["students"].map(
                    lambda n: enhanced._STATUS_STYLE[enhanced.group_status(n)][1]
                )
                st.dataframe(prev, use_container_width=True, hide_index=True)
    except Exception as exc:  # pragma: no cover - UI guard
        st.error(f"Erreur lors du chargement des donnees: {exc}")

st.divider()

# ────────────────────────────────────────────────────────────
# Generate + download
# ────────────────────────────────────────────────────────────
st.subheader("Generation")
if st.button("Generer le classeur", type="primary"):
    with st.spinner("Generation en cours..."):
        result = manager.export_with_format(
            format_type,
            semester=semester,
            color_scheme=color_scheme,
            overrides=overrides if format_type != "standard" else None,
        )
    if result.get("ok"):
        st.success("Classeur genere avec succes.")
        files = result.get("files") or ([result.get("file")] if result.get("file") else [])
        for path in files:
            if path and os.path.isfile(path):
                with open(path, "rb") as fh:
                    st.download_button(
                        label=f"Telecharger {os.path.basename(path)}",
                        data=fh.read(),
                        file_name=os.path.basename(path),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{path}",
                    )
    else:
        st.error(f"Echec de la generation: {result.get('error')}")

# ────────────────────────────────────────────────────────────
# Template renderer
# ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Modeles (templates)")
templates = manager.list_templates()
if not templates:
    st.caption("Aucun modele disponible dans le dossier templates/.")
else:
    tpl = st.selectbox("Modele", templates)
    report = manager.validate_template(tpl)
    if report["ok"]:
        st.caption(
            f"Variables detectees: {', '.join(report['placeholders']) or 'aucune'}"
            + (f" | Inconnues: {', '.join(report['unknown'])}" if report["unknown"] else "")
        )
    with st.form("tpl_form"):
        cc1, cc2 = st.columns(2)
        with cc1:
            v_title = st.text_input("TITLE", "Distribucion de Practicas")
            v_sem = st.text_input("SEMESTER", "1")
            v_subject = st.text_input("SUBJECT", "")
            v_group = st.text_input("GROUP", "")
        with cc2:
            v_prof = st.text_input("PROFESSOR", "")
            v_room = st.text_input("ROOM", "")
            v_day = st.text_input("DAY", "")
            v_block = st.text_input("BLOCK", "")
        submitted = st.form_submit_button("Generer depuis le modele")
    if submitted:
        ctx = {
            "TITLE": v_title, "SEMESTER": v_sem, "SUBJECT": v_subject,
            "GROUP": v_group, "PROFESSOR": v_prof, "ROOM": v_room,
            "DAY": v_day, "BLOCK": v_block,
        }
        res = manager.render_template(tpl, ctx)
        if res.get("ok"):
            st.success("Modele rempli.")
            if res.get("missing"):
                st.caption(f"Variables non fournies: {', '.join(res['missing'])}")
            path = res["file"]
            with open(path, "rb") as fh:
                st.download_button(
                    label=f"Telecharger {os.path.basename(path)}",
                    data=fh.read(),
                    file_name=os.path.basename(path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.error(f"Echec: {res.get('error')}")
