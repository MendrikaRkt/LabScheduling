"""
ui_advanced_exports.py — Embeddable advanced Excel export UI.

Consolidation of the former standalone page ``pages/6_Exports_Avancés.py``
into a reusable component so that the enhanced export options live inside
the single Export page of ``app.py`` (user request: the advanced options
must apply directly where the Excel files are generated).

The component keeps the exact same behaviour as the standalone page:
- Format selector (standard / summary / enhanced / detailed).
- Colour scheme selector (Loyola / default / monochrome).
- Per-sheet and formatting option checkboxes.
- Read-only data preview, generation with download buttons.
- Template renderer ({{TOKEN}} substitution).

All UI labels are in French per project convention; no emojis are used.
"""

from __future__ import annotations

import os

import streamlit as st

import excel_export_enhanced as enhanced
import export_manager as manager


def render_advanced_exports_section() -> None:
    """Render the advanced export console (embeddable in the Export page)."""
    st.info(
        "Ces options generent des classeurs ENRICHIS (groupes en couleurs, "
        "analyses salles/professeurs/placement/creneaux, metriques de "
        "qualite) a partir des resultats existants. Les exports valides "
        "(format Daniel) ci-dessus ne sont jamais modifies."
    )

    prefs = manager.load_preferences()

    col_cfg, col_prev = st.columns([1, 1])

    with col_cfg:
        st.markdown("##### Configuration de l'export")

        semester_label = st.selectbox(
            "Perimetre",
            ["Les deux semestres", "Semestre 1", "Semestre 2"],
            index=0,
            key="advx_sem",
        )
        semester = {"Les deux semestres": None, "Semestre 1": 1,
                    "Semestre 2": 2}[semester_label]

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
            key="advx_fmt",
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
            index=(scheme_keys.index(default_scheme)
                   if default_scheme in scheme_keys else 0),
            format_func=lambda k: scheme_labels[k],
            key="advx_scheme",
        )

        st.markdown("**Feuilles a inclure**")
        base_opts = manager.resolve_options(format_type)
        c1, c2 = st.columns(2)
        with c1:
            opt_groups = st.checkbox("Groupes (couleurs)",
                                     value=base_opts.color_coded_groups,
                                     key="advx_groups")
            opt_legend = st.checkbox("Legende", value=base_opts.legend,
                                     key="advx_legend")
            opt_rooms = st.checkbox("Utilisation des salles",
                                    value=base_opts.room_utilization,
                                    key="advx_rooms")
            opt_profs = st.checkbox("Charge des professeurs",
                                    value=base_opts.professor_workload,
                                    key="advx_profs")
        with c2:
            opt_place = st.checkbox("Placement des etudiants",
                                    value=base_opts.student_placement,
                                    key="advx_place")
            opt_slots = st.checkbox("Analyse des creneaux",
                                    value=base_opts.time_slot_analysis,
                                    key="advx_slots")
            opt_quality = st.checkbox("Metriques de qualite",
                                      value=base_opts.quality_metrics,
                                      key="advx_quality")

        st.markdown("**Options de mise en forme**")
        c3, c4 = st.columns(2)
        with c3:
            opt_cf = st.checkbox("Mise en forme conditionnelle",
                                 value=base_opts.conditional_formatting,
                                 key="advx_cf")
            opt_filter = st.checkbox("Filtres automatiques",
                                     value=base_opts.auto_filter,
                                     key="advx_filter")
            opt_freeze = st.checkbox("Volets figes",
                                     value=base_opts.freeze_panes,
                                     key="advx_freeze")
        with c4:
            opt_dv = st.checkbox("Listes deroulantes",
                                 value=base_opts.data_validation,
                                 key="advx_dv")
            opt_named = st.checkbox("Plages nommees",
                                    value=base_opts.named_ranges,
                                    key="advx_named")
            opt_comments = st.checkbox("Commentaires de cellule",
                                       value=base_opts.cell_comments,
                                       key="advx_comments")
            opt_protect = st.checkbox("Proteger les feuilles",
                                      value=base_opts.protect_sheets,
                                      key="advx_protect")

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

    # ── Preview: quick data summary (read-only, no file written) ──────
    with col_prev:
        st.markdown("##### Apercu des donnees")
        try:
            sched = enhanced.load_schedule(semester)
            kpi = enhanced.load_kpi()
            if len(sched) == 0:
                st.warning(
                    "Aucun planning trouve. Lancez d'abord l'optimisation "
                    "pour generer "
                    "outputs/optimization/optimized_schedule_v5.csv."
                )
            else:
                n_groups = sched.groupby(
                    ["semester", "subject", "grupo"]).ngroups
                m1, m2, m3 = st.columns(3)
                m1.metric("Seances", int(len(sched)))
                m2.metric("Groupes", int(n_groups))
                m3.metric("Salles", int(sched["lab_rooms"].nunique()))
                placement = (kpi or {}).get("placement", {})
                if placement:
                    p1, p2 = st.columns(2)
                    p1.metric("Inscrits", placement.get("enrolled", "n/d"))
                    p2.metric("Placement %",
                              placement.get("placement_pct", "n/d"))

                summary = enhanced._group_summary(sched)[:12]
                if summary:
                    import pandas as pd
                    prev = pd.DataFrame(summary)[
                        ["semester", "subject", "grupo", "students", "day",
                         "time_block", "room"]
                    ]
                    prev["status"] = prev["students"].map(
                        lambda n: enhanced._STATUS_STYLE[
                            enhanced.group_status(n)][1]
                    )
                    st.dataframe(prev, use_container_width=True,
                                 hide_index=True)
        except Exception as exc:  # pragma: no cover - UI guard
            st.error(f"Erreur lors du chargement des donnees: {exc}")

    # ── Generate + download ───────────────────────────────────────────
    st.markdown("##### Generation")
    if st.button("Generer le classeur enrichi", type="primary",
                 key="advx_generate"):
        with st.spinner("Generation en cours..."):
            result = manager.export_with_format(
                format_type,
                semester=semester,
                color_scheme=color_scheme,
                overrides=overrides if format_type != "standard" else None,
            )
        if result.get("ok"):
            st.success("Classeur genere avec succes.")
            files = result.get("files") or (
                [result.get("file")] if result.get("file") else [])
            for path in files:
                if path and os.path.isfile(path):
                    with open(path, "rb") as fh:
                        st.download_button(
                            label=f"Telecharger {os.path.basename(path)}",
                            data=fh.read(),
                            file_name=os.path.basename(path),
                            mime=("application/vnd.openxmlformats-"
                                  "officedocument.spreadsheetml.sheet"),
                            key=f"advx_dl_{path}",
                        )
        else:
            st.error(f"Echec de la generation: {result.get('error')}")

    # ── Template renderer ─────────────────────────────────────────────
    with st.expander("Modeles (templates)"):
        templates = manager.list_templates()
        if not templates:
            st.caption("Aucun modele disponible dans le dossier templates/.")
        else:
            tpl = st.selectbox("Modele", templates, key="advx_tpl")
            report = manager.validate_template(tpl)
            if report["ok"]:
                st.caption(
                    "Variables detectees: "
                    + (", ".join(report["placeholders"]) or "aucune")
                    + (f" | Inconnues: {', '.join(report['unknown'])}"
                       if report["unknown"] else "")
                )
            with st.form("advx_tpl_form"):
                cc1, cc2 = st.columns(2)
                with cc1:
                    v_title = st.text_input("TITLE",
                                            "Distribucion de Practicas")
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
                    "TITLE": v_title, "SEMESTER": v_sem,
                    "SUBJECT": v_subject, "GROUP": v_group,
                    "PROFESSOR": v_prof, "ROOM": v_room,
                    "DAY": v_day, "BLOCK": v_block,
                }
                res = manager.render_template(tpl, ctx)
                if res.get("ok"):
                    st.success("Modele rempli.")
                    if res.get("missing"):
                        st.caption("Variables non fournies: "
                                   + ", ".join(res["missing"]))
                    path = res["file"]
                    with open(path, "rb") as fh:
                        st.download_button(
                            label=f"Telecharger {os.path.basename(path)}",
                            data=fh.read(),
                            file_name=os.path.basename(path),
                            mime=("application/vnd.openxmlformats-"
                                  "officedocument.spreadsheetml.sheet"),
                            key="advx_tpl_dl",
                        )
                else:
                    st.error(f"Echec: {res.get('error')}")
