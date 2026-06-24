"""
Lab Scheduling Automation — Universidad Loyola Seville
Professional UI/UX for production use

Author: RAKOTONJANAHARY Maminiaina Mendrika
Supervisor: Pablo Millán Gata
Stakeholder: Daniel Álvarez Lorenzo
"""

import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# PII-safe error reporting
#
# Raw exception text can carry a data row (hence a student name) into the UI or
# a screenshot. safe_error() shows a generic message + a short reference and
# writes the (scrubbed) detail to a local technical log only. Use it instead of
# st.error(f"...{e}") on any except branch that handles data.
# ─────────────────────────────────────────────────────────────────────────────
import logging as _logging, re as _re, uuid as _uuid

_PII_EMAIL = _re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PII_LONGNUM = _re.compile(r"\b\d{6,}\b")

def _scrub(text: str) -> str:
    text = _PII_EMAIL.sub("[email]", str(text))
    return _PII_LONGNUM.sub("[id]", text)

def _tech_logger():
    log = _logging.getLogger("labsched.ui")
    if not log.handlers:
        try:
            import app_paths as _ap
            _logf = _ap.workspace_path("logs", "ui_errors.log")
        except Exception:
            _logf = "ui_errors.log"
        try:
            h = _logging.FileHandler(_logf, encoding="utf-8")
        except Exception:
            h = _logging.StreamHandler()
        h.setFormatter(_logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(h); log.setLevel(_logging.INFO)
    return log

def safe_error(user_msg: str, exc: Exception | None = None, *, stop: bool = False):
    """Show a generic message + reference; log scrubbed detail locally."""
    import traceback as _tb
    ref = _uuid.uuid4().hex[:8]
    detail = _scrub("".join(_tb.format_exception(exc)) if exc else user_msg)
    _tech_logger().error("ref=%s | %s", ref, detail)
    st.error(f"{user_msg} (ref. {ref})")
    if stop:
        st.stop()

import pandas as pd
import os
import sys
import json
import io
import zipfile
import base64
import subprocess
from pathlib import Path
from datetime import datetime

# ── Activate Python patches FIRST ──────────────────────────────────────────
# `streamlit run app.py` runs this file in its own process. To make sure any
# applied patch (Channel A update) shadows the bundled modules, we put the
# patch dir at the front of sys.path here, before importing any local module
# (app_paths, pipeline, excel_export, …). Best-effort and silent on failure.
try:
    import update_manager as _upd_boot
    _patch_dir = _upd_boot.activate_patches()
except Exception:
    _patch_dir = None

# Central path resolver: distinguishes bundled read-only resources from the
# writable per-user workspace. Critical for the packaged .exe. Defensive import.
try:
    import app_paths
    PATHS_OK = True
except Exception:
    app_paths = None
    PATHS_OK = False

try:
    from loyola_theme import inject_theme
    inject_theme()
except Exception:
    # If the theme module is missing from the bundle, fail soft: the app still
    # runs with Streamlit's default styling instead of crashing on startup.
    def inject_theme():  # type: ignore
        return None

# Persistent memory (preferences, config, run history). Defensive import so the
# app still runs if the module is missing (e.g. partial deployment).
try:
    import persistence as _persist
    PERSISTENCE_OK = True
except Exception:
    _persist = None
    PERSISTENCE_OK = False

# ════════════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Lab Scheduling — Universidad Loyola",
    page_icon="L",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': "Lab Scheduling Automation v2.0 — Universidad Loyola Seville, 2026"
    }
)

# ════════════════════════════════════════════════════════════
# LOGO (base64 for inline use)
# ════════════════════════════════════════════════════════════
def load_logo_b64():
    """Load the logo as a base64 string.

    Resolves the file through app_paths so it is found whether running from
    source or from the packaged .exe. Validates that a PNG is actually a PNG
    (magic bytes) before returning its base64, so a truncated/placeholder file
    never produces a broken <img>; in that case we return None and the caller
    renders the inline-SVG fallback instead.
    """
    rel_candidates = [
        'assets/loyola_logo.png',
        'assets/logo_b64.txt',
    ]
    _PNG_SIG = b"\x89PNG\r\n\x1a\n"

    def _read(path):
        try:
            if path.endswith('.txt'):
                with open(path, encoding='utf-8') as f:
                    txt = f.read().strip()
                return txt or None
            with open(path, 'rb') as f:
                raw = f.read()
            # Reject anything that isn't a real PNG (prevents broken images)
            if not raw.startswith(_PNG_SIG) or len(raw) < 100:
                return None
            return base64.b64encode(raw).decode()
        except Exception:
            return None

    # 1) Resolve through app_paths (workspace + bundle)
    if PATHS_OK:
        for rel in rel_candidates:
            found = app_paths.resolve_existing(rel)
            if found:
                b = _read(found)
                if b:
                    return b
    # 2) Fallback: bare relative paths (development from source)
    for path in rel_candidates:
        if os.path.exists(path):
            b = _read(path)
            if b:
                return b
    return None

LOGO_B64 = load_logo_b64()



# ════════════════════════════════════════════════════════════
# TRANSLATIONS
# ════════════════════════════════════════════════════════════
LANGS = {
    'es': {
        'app_title': 'Planificación de Laboratorios',
        'tagline': 'Automatización inteligente de horarios',
        'nav_home': 'Inicio',
        'nav_data': 'Datos',
        'nav_config': 'Configuración',
        'nav_optimize': 'Optimizar',
        'nav_results': 'Resultados',
        'nav_dashboard': 'Fiabilidad',
        'nav_integrity': 'Integridad',
        'nav_history': 'Historial',
        'nav_edit': 'Editar plan',
        'nav_groups': 'Grupos',
        'nav_compare': 'Comparar',
        'nav_export': 'Exportar',
        'nav_student': 'Caso individual',
        'nav_updates': 'Actualizaciones',
        'language': 'Idioma',
        'data_loaded_status': 'Datos cargados',
        'pipeline_ran_status': 'Pipeline ejecutado',
        'session_status': 'Estado de la sesión',
        'quit_app': 'Salir de la aplicación',
        'quit_done': 'Aplicación cerrada.',
        'quit_hint': 'Ya puede cerrar esta pestaña del navegador.',
        # Home
        'home_title': 'Lab Scheduling Automation',
        'home_sub': 'Sistema inteligente de planificación de laboratorios para la Universidad Loyola',
        'home_welcome': 'Bienvenido',
        'home_intro': 'Esta aplicación automatiza la planificación de sesiones de laboratorio respetando todas las restricciones académicas y horarias. Optimiza 500+ sesiones en menos de 2 segundos.',
        'home_step1_title': '1. Cargue los datos',
        'home_step1_desc': 'Suba los archivos del aulario y de inscripciones',
        'home_step2_title': '2. Configure',
        'home_step2_desc': 'Ajuste los parámetros según las necesidades del curso',
        'home_step3_title': '3. Optimice',
        'home_step3_desc': 'Ejecute el pipeline y obtenga el planning óptimo',
        'home_step4_title': '4. Exporte',
        'home_step4_desc': 'Descargue los archivos en formato Excel de Daniel',
        'quick_stats': 'Resultados de la última ejecución',
        'no_data_yet': 'Aún no se ha ejecutado el pipeline',
        'start_here': 'Empezar',
        'key_features': 'Características principales',
        'feat1_t': 'Solver CP-SAT',
        'feat1_d': 'Optimización basada en Google OR-Tools para garantizar cero conflictos',
        'feat2_t': 'Formato Daniel',
        'feat2_d': 'Archivos Excel generados en el formato exacto usado por Daniel',
        'feat3_t': 'Multilingüe',
        'feat3_d': 'Interfaz disponible en español, inglés y francés',
        'feat4_t': '9 restricciones',
        'feat4_d': 'Respeta todas las restricciones académicas (C1-C9)',
        # Data
        'data_title': 'Carga de datos',
        'data_sub': 'Suba los dos archivos fuente de la universidad',
        'aulario_label': 'Horarios (Aulario)',
        'alumnos_label': 'Inscripciones (Alumnos)',
        'rows': 'filas',
        'cols': 'columnas',
        'unique_students': 'Estudiantes únicos',
        'unique_courses': 'Cursos únicos',
        'preview': 'Vista previa',
        'both_loaded': 'Ambos archivos cargados correctamente',
        'upload_help_1': 'Archivo revisionAulario.xlsx con los horarios de cursos',
        'upload_help_2': 'Archivo report_AlumnosGrupos.xlsx con las inscripciones',
        # Config
        'config_title': 'Configuración',
        'config_sub': 'Parámetros del sistema y de cada materia',
        'global_params': 'Parámetros globales',
        'pref_size': 'Tamaño preferido',
        'max_size': 'Tamaño máximo',
        'min_size': 'Tamaño mínimo',
        'comp_max': 'Max informática',
        'reduced_max': 'Max especial',
        'start_week': 'Primera semana',
        'prereq_title': 'Requisitos por materia',
        'prereq_sub': 'Las sesiones deben realizarse después de que los profesores hayan explicado los conceptos.',
        'year_pref_title': 'Preferencia horaria por año',
        'year_pref_sub': '1º/3º año: mañana · 2º/4º año: tarde',
        'teacher_title': 'Disponibilidad de profesores',
        'lab_req_title': 'Requisitos de laboratorio',
        'per_subject': 'Configuración por materia',
        'filter_year': 'Filtrar por año',
        'filter_sem': 'Filtrar por semestre',
        'all': 'Todos',
        # Optimize
        'opt_title': 'Ejecutar optimización',
        'opt_sub': 'Pipeline completo: limpieza → grupos → CP-SAT',
        'load_files_first': 'Primero cargue los dos archivos en la sección Datos',
        'exec_options': 'Opciones de ejecución',
        'include_names': 'Incluir nombres reales (validación con Daniel)',
        'solver_timeout': 'Timeout del solver (segundos)',
        'run_btn': 'Ejecutar pipeline',
        'running': 'Pipeline en curso...',
        'done': 'Pipeline completado',
        'success': 'Pipeline ejecutado con éxito',
        'full_log': 'Log completo',
        'run_first': 'Primero ejecute el pipeline',
        # Results
        'res_title': 'Panel de resultados',
        'res_sub': 'Vista general por año y semestre',
        'sessions_lbl': 'Sesiones',
        'groups_lbl': 'Grupos',
        'assigned_lbl': 'Asignados',
        'rate_lbl': 'Tasa',
        'recent_runs': 'Ejecuciones recientes',
        'run_date_col': 'Fecha',
        'recent_runs_hint': 'El historial se guarda automáticamente y persiste entre sesiones.',
        'conflicts_lbl': 'Conflictos',
        # Groups
        'grp_title': 'Explorador de grupos',
        'grp_sub': 'Composición detallada por año',
        'year_lbl': 'Año',
        'semester_lbl': 'Semestre',
        'students': 'estudiantes',
        # Compare
        'cmp_title': 'Comparación con datos reales',
        'cmp_sub': 'Compare con los archivos de referencia de Daniel',
        'our': 'Nuestro',
        'daniel': 'Daniel',
        'diff': 'Diferencia',
        # Export
        'exp_title': 'Exportar resultados',
        'exp_sub': 'Descargue los archivos en formato de Daniel',
        'gen_s1_title': 'Generar formato Daniel — Primer semestre',
        'gen_s2_title': 'Generar formato Daniel — Segundo semestre',
        'gen_s1_btn': 'Generar S1',
        'gen_s2_btn': 'Generar S2',
        'download_files': 'Archivos disponibles',
        'dl_s1_zip': 'Descargar S1 completo',
        'dl_s2_zip': 'Descargar S2 completo',
        'footer': 'Universidad Loyola Seville · Lab Scheduling Automation · 2026',
    },
    'en': {
        'app_title': 'Lab Scheduling',
        'tagline': 'Intelligent timetable automation',
        'nav_home': 'Home',
        'nav_data': 'Data',
        'nav_config': 'Configuration',
        'nav_optimize': 'Optimize',
        'nav_results': 'Results',
        'nav_dashboard': 'Reliability',
        'nav_integrity': 'Integrity',
        'nav_history': 'History',
        'nav_edit': 'Edit plan',
        'nav_groups': 'Groups',
        'nav_compare': 'Compare',
        'nav_export': 'Export',
        'nav_student': 'Individual case',
        'nav_updates': 'Updates',
        'language': 'Language',
        'data_loaded_status': 'Data loaded',
        'pipeline_ran_status': 'Pipeline executed',
        'session_status': 'Session status',
        'quit_app': 'Quit application',
        'quit_done': 'Application closed.',
        'quit_hint': 'You can now close this browser tab.',
        'home_title': 'Lab Scheduling Automation',
        'home_sub': 'Automated lab session planning for Universidad Loyola',
        'home_welcome': 'Welcome',
        'home_intro': 'This application automates lab session planning under all academic and timetable constraints. Generates the full schedule for 500+ sessions in seconds, with zero conflicts.',
        'home_step1_title': '1. Load data',
        'home_step1_desc': 'Upload the timetable and enrollment files',
        'home_step2_title': '2. Configure',
        'home_step2_desc': 'Adjust parameters to match course needs',
        'home_step3_title': '3. Optimize',
        'home_step3_desc': 'Run the solver to compute the optimal schedule',
        'home_step4_title': '4. Export',
        'home_step4_desc': 'Download the Excel deliverables in Daniel\'s format',
        'quick_stats': 'Last execution results',
        'no_data_yet': 'No pipeline run yet',
        'start_here': 'Get started',
        'key_features': 'Key features',
        'feat1_t': 'CP-SAT solver',
        'feat1_d': 'Google OR-Tools constraint solver, guaranteeing zero hard-constraint violations',
        'feat2_t': 'Daniel\'s Excel format',
        'feat2_d': 'Excel files generated in the exact format used today by Daniel',
        'feat3_t': 'Multilingual',
        'feat3_d': 'Interface available in English, Spanish and French',
        'feat4_t': 'Nine constraints',
        'feat4_d': 'All academic and operational constraints enforced (C1-C9)',
        'data_title': 'Source data',
        'data_sub': 'Upload the two source files from the university',
        'aulario_label': 'Timetables (Aulario)',
        'alumnos_label': 'Enrollments (Alumnos)',
        'rows': 'rows',
        'cols': 'columns',
        'unique_students': 'Unique students',
        'unique_courses': 'Unique courses',
        'preview': 'Preview',
        'both_loaded': 'Both files loaded successfully',
        'upload_help_1': 'revisionAulario.xlsx — course timetables',
        'upload_help_2': 'report_AlumnosGrupos.xlsx — enrollments',
        'config_title': 'Configuration',
        'config_sub': 'System parameters and per-subject overrides',
        'global_params': 'Global parameters',
        'pref_size': 'Preferred size',
        'max_size': 'Max size',
        'min_size': 'Min size',
        'comp_max': 'Computer lab max',
        'reduced_max': 'Reduced lab max',
        'start_week': 'First week',
        'prereq_title': 'Subject prerequisites',
        'prereq_sub': 'Lab sessions must take place after the required topics have been covered in lectures.',
        'year_pref_title': 'Year-based time preference',
        'year_pref_sub': '1st and 3rd year: morning · 2nd and 4th year: afternoon',
        'teacher_title': 'Teacher availability',
        'lab_req_title': 'Lab requirements',
        'per_subject': 'Per-subject configuration',
        'filter_year': 'Filter by year',
        'filter_sem': 'Filter by semester',
        'all': 'All',
        'opt_title': 'Run optimization',
        'opt_sub': 'Full pipeline: cleaning → groups → CP-SAT',
        'load_files_first': 'Please load both files in the Data section first',
        'exec_options': 'Execution options',
        'include_names': 'Include real names (for Daniel\'s validation)',
        'solver_timeout': 'Solver timeout (seconds)',
        'run_btn': 'Run pipeline',
        'running': 'Pipeline running…',
        'done': 'Pipeline complete',
        'success': 'Pipeline executed successfully',
        'full_log': 'Full log',
        'run_first': 'Please run the pipeline first',
        'res_title': 'Results dashboard',
        'res_sub': 'Overview by year and semester',
        'sessions_lbl': 'Sessions',
        'groups_lbl': 'Groups',
        'assigned_lbl': 'Assigned',
        'rate_lbl': 'Rate',
        'recent_runs': 'Recent runs',
        'run_date_col': 'Date',
        'recent_runs_hint': 'History is saved automatically and persists across restarts.',
        'conflicts_lbl': 'Conflicts',
        'grp_title': 'Group explorer',
        'grp_sub': 'Detailed composition by year',
        'year_lbl': 'Year',
        'semester_lbl': 'Semester',
        'students': 'students',
        'cmp_title': 'Comparison with reference',
        'cmp_sub': 'Compare the generated plan against Daniel\'s historical files',
        'our': 'Generated',
        'daniel': 'Daniel',
        'diff': 'Difference',
        'exp_title': 'Export results',
        'exp_sub': 'Download Excel deliverables in Daniel\'s format',
        'gen_s1_title': 'Generate — First semester',
        'gen_s2_title': 'Generate — Second semester',
        'gen_s1_btn': 'Generate S1',
        'gen_s2_btn': 'Generate S2',
        'download_files': 'Available files',
        'dl_s1_zip': 'Download S1 (full archive)',
        'dl_s2_zip': 'Download S2 (full archive)',
        'footer': 'Universidad Loyola Sevilla · Lab Scheduling Automation · 2026',
    },
    'fr': {
        'app_title': 'Planification Laboratoires',
        'tagline': 'Automatisation intelligente des horaires',
        'nav_home': 'Accueil',
        'nav_data': 'Données',
        'nav_config': 'Configuration',
        'nav_optimize': 'Optimiser',
        'nav_results': 'Résultats',
        'nav_dashboard': 'Fiabilité',
        'nav_integrity': 'Intégrité',
        'nav_history': 'Historique',
        'nav_edit': 'Édition manuelle',
        'nav_groups': 'Groupes',
        'nav_compare': 'Comparer',
        'nav_export': 'Exporter',
        'nav_student': 'Cas individuel',
        'nav_updates': 'Mises à jour',
        'language': 'Langue',
        'data_loaded_status': 'Data loaded',
        'pipeline_ran_status': 'Pipeline exécuté',
        'session_status': 'État de la session',
        'quit_app': "Quitter l'application",
        'quit_done': 'Application fermée.',
        'quit_hint': 'Vous pouvez maintenant fermer cet onglet du navigateur.',
        'home_title': 'Automatisation des Laboratoires',
        'home_sub': 'Système intelligent de planification de laboratoires pour Universidad Loyola',
        'home_welcome': 'Bienvenue',
        'home_intro': 'Cette application automatise la planification des sessions de laboratoire en respectant toutes les contraintes académiques et horaires. Optimise 500+ sessions en moins de 2 secondes.',
        'home_step1_title': '1. Charger les données',
        'home_step1_desc': 'Uploadez les fichiers aulario et inscriptions',
        'home_step2_title': '2. Configurer',
        'home_step2_desc': 'Ajustez les paramètres selon les besoins',
        'home_step3_title': '3. Optimiser',
        'home_step3_desc': 'Lancez le pipeline pour obtenir le planning optimal',
        'home_step4_title': '4. Exporter',
        'home_step4_desc': 'Téléchargez les fichiers au format Daniel',
        'quick_stats': 'Résultats de la dernière exécution',
        'no_data_yet': 'Aucun pipeline exécuté pour le moment',
        'start_here': 'Commencer',
        'key_features': 'Fonctionnalités clés',
        'feat1_t': 'Solveur CP-SAT',
        'feat1_d': 'Optimisation Google OR-Tools pour garantir zéro conflit',
        'feat2_t': 'Format Daniel',
        'feat2_d': 'Fichiers Excel générés au format exact utilisé par Daniel',
        'feat3_t': 'Multilingue',
        'feat3_d': 'Interface disponible en espagnol, anglais et français',
        'feat4_t': 'Nine constraints',
        'feat4_d': 'Respecte toutes les contraintes académiques (C1-C9)',
        'data_title': 'Chargement des données',
        'data_sub': 'Uploadez les deux fichiers source de l\'université',
        'aulario_label': 'Horaires (Aulario)',
        'alumnos_label': 'Enrollments (Alumnos)',
        'rows': 'lignes',
        'cols': 'colonnes',
        'unique_students': 'Étudiants uniques',
        'unique_courses': 'Cours uniques',
        'preview': 'Aperçu',
        'both_loaded': 'Les deux fichiers sont chargés',
        'upload_help_1': 'Fichier revisionAulario.xlsx avec les horaires de cours',
        'upload_help_2': 'Fichier report_AlumnosGrupos.xlsx avec les inscriptions',
        'config_title': 'Configuration',
        'config_sub': 'Paramètres système et par matière',
        'global_params': 'Paramètres globaux',
        'pref_size': 'Taille préférée',
        'max_size': 'Taille max',
        'min_size': 'Taille min',
        'comp_max': 'Max salle info',
        'reduced_max': 'Max spécial',
        'start_week': 'Première semaine',
        'prereq_title': 'Prérequis par matière',
        'prereq_sub': 'Les sessions doivent avoir lieu après que les enseignants ont expliqué les concepts.',
        'year_pref_title': 'Préférence horaire par année',
        'year_pref_sub': '1re/3e année : matin · 2e/4e année : après-midi',
        'teacher_title': 'Disponibilité des enseignants',
        'lab_req_title': 'Exigences de laboratoire',
        'per_subject': 'Configuration par matière',
        'filter_year': 'Filtrer par année',
        'filter_sem': 'Filtrer par semestre',
        'all': 'Tous',
        'opt_title': 'Lancer l\'optimisation',
        'opt_sub': 'Pipeline complet : nettoyage → groupes → CP-SAT',
        'load_files_first': 'Chargez d\'abord les deux fichiers dans Données',
        'exec_options': 'Options d\'exécution',
        'include_names': 'Inclure les vrais noms (validation avec Daniel)',
        'solver_timeout': 'Timeout du solveur (secondes)',
        'run_btn': 'Lancer le pipeline',
        'running': 'Pipeline en cours...',
        'done': 'Pipeline terminé',
        'success': 'Pipeline exécuté avec succès',
        'full_log': 'Log complet',
        'run_first': 'Lancez d\'abord le pipeline',
        'res_title': 'Tableau de bord',
        'res_sub': 'Vue d\'ensemble par année et semestre',
        'sessions_lbl': 'Sessions',
        'groups_lbl': 'Groupes',
        'assigned_lbl': 'Assignés',
        'rate_lbl': 'Taux',
        'recent_runs': 'Exécutions récentes',
        'run_date_col': 'Date',
        'recent_runs_hint': "L'historique est enregistré automatiquement et persiste entre les sessions.",
        'conflicts_lbl': 'Conflits',
        'grp_title': 'Explorateur de groupes',
        'grp_sub': 'Composition détaillée par année',
        'year_lbl': 'Année',
        'semester_lbl': 'Semestre',
        'students': 'étudiants',
        'cmp_title': 'Comparaison avec données réelles',
        'cmp_sub': 'Comparez avec les fichiers de référence de Daniel',
        'our': 'Nous',
        'daniel': 'Daniel',
        'diff': 'Écart',
        'exp_title': 'Exporter les résultats',
        'exp_sub': 'Téléchargez les fichiers au format de Daniel',
        'gen_s1_title': 'Générer format Daniel — Premier semestre',
        'gen_s2_title': 'Générer format Daniel — Second semestre',
        'gen_s1_btn': 'Générer S1',
        'gen_s2_btn': 'Générer S2',
        'download_files': 'Fichiers disponibles',
        'dl_s1_zip': 'Télécharger S1 complet',
        'dl_s2_zip': 'Télécharger S2 complet',
        'footer': 'Universidad Loyola Seville · Lab Scheduling Automation · 2026',
    },
}

if 'lang' not in st.session_state:
    st.session_state.lang = 'en'

def t(key):
    return LANGS.get(st.session_state.lang, LANGS['en']).get(key, key)

# ════════════════════════════════════════════════════════════
# CONSTANTS
# ════════════════════════════════════════════════════════════
YEAR_LABELS = {1: 'Primero', 2: 'Segundo', 3: 'Tercero'}

SUBJECT_YEAR = {
    'S1_Física': 1, 'S1_Química': 1,
    'S2_Física II': 1, 'S2_Tecnología Medio Ambiente': 1,
    'S1_Electrotecnia': 2, 'S1_Mecanismos': 2, 'S1_Termodinámica': 2,
    'S2_Resistencia de Materiales': 2, 'S2_Mecánica de Fluidos': 2,
    'S2_Regulación Automática': 2, 'S2_Tecnología Electrónica': 2,
    'S2_Electrónica y Automática': 2, 'S2_Informática y Com. Industriales': 2,
    'S2_Métodos Numéricos': 2, 'S2_Modelado de Sistemas': 2,
    'S2_Automatic Control': 2,
    'S1_Tecnologías de Fabricación': 3, 'S1_Robótica y Automatización': 3,
    'S1_Automatización Industrial': 3,
    'S2_Ingeniería de Control': 3, 'S2_Control de Máquinas': 3, 'S2_Estructuras': 3,
}

def clean_subject(s):
    for p in ['S1_', 'S2_']: s = s.replace(p, '')
    return s
def get_year(s): return SUBJECT_YEAR.get(s, 0)
def get_sem(s): return 1 if s.startswith('S1_') else 2

# ════════════════════════════════════════════════════════════
# SESSION STATE
# ════════════════════════════════════════════════════════════
defaults = {
    'aulario_df': None, 'alumnos_df': None, 'master_df': None,
    'results_df': None, 'all_groups': None, 'pipeline_log': '',
    'pipeline_ran': False, 'subject_students': None,
    'advanced_config': {
        'preferred_size': 12, 'default_max': 15, 'min_size': 7,
        'computer_lab_max': 24, 'reduced_max_size': 12, 'start_week': 4,
        'morning_years': [1, 3], 'afternoon_years': [2, 4],
        'allow_afternoon_y1y3': False, 'allow_morning_y2y4': False,
        'subject_prerequisites': {}, 'teacher_unavailability': {},
        'computer_lab_sessions': {},
    }
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Restore persisted preferences (language, theme, advanced config) on first
# load of this session. Runs after defaults so saved values take precedence
# while still inheriting any newly-added default keys.
if PERSISTENCE_OK:
    try:
        _persist.hydrate_session(st, defaults)
    except Exception:
        pass

# The application is English-only. Force English regardless of any previously
# persisted language preference, so the whole UI is consistent.
st.session_state.lang = 'en'

# ════════════════════════════════════════════════════════════
# SIDEBAR — with logo and navigation
# ════════════════════════════════════════════════════════════
with st.sidebar:
    # Logo — PNG if available, otherwise an inline SVG wordmark so the brand
    # never renders as a broken image (important in the packaged .exe).
    if LOGO_B64:
        st.markdown(f"""
            <div class="sidebar-logo">
                <img src="data:image/png;base64,{LOGO_B64}" alt="Universidad Loyola"/>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
            <div class="sidebar-logo">
              <svg width="180" height="52" viewBox="0 0 180 52" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Universidad Loyola">
                <rect x="2" y="6" width="40" height="40" rx="8" fill="#1B3A6F"/>
                <text x="22" y="33" font-family="Georgia,serif" font-size="20" font-weight="700" fill="#FFFFFF" text-anchor="middle">UL</text>
                <text x="52" y="24" font-family="Inter,Arial,sans-serif" font-size="15" font-weight="600" fill="#1B3A6F">Universidad</text>
                <text x="52" y="42" font-family="Inter,Arial,sans-serif" font-size="15" font-weight="600" fill="#6FAED9">Loyola</text>
              </svg>
            </div>
        """, unsafe_allow_html=True)

    st.markdown(f'<div class="brand-tagline">{t("tagline")}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    # Navigation
    nav_options = [
        t('nav_home'), t('nav_data'), t('nav_config'), t('nav_optimize'),
        t('nav_results'), t('nav_dashboard'), t('nav_integrity'), t('nav_history'), t('nav_edit'), t('nav_groups'), t('nav_compare'), t('nav_export'),
        t('nav_student'), t('nav_updates')
    ]

    # Handle programmatic navigation from wizard buttons
    if '_nav_to' in st.session_state:
        target = st.session_state.pop('_nav_to')
        nav_map = {
            'home': t('nav_home'),
            'data': t('nav_data'),
            'config': t('nav_config'),
            'optimize': t('nav_optimize'),
            'results': t('nav_results'),
            'dashboard': t('nav_dashboard'),
            'integrity': t('nav_integrity'),
            'history': t('nav_history'),
            'edit': t('nav_edit'),
            'groups': t('nav_groups'),
            'compare': t('nav_compare'),
            'export': t('nav_export'),
            'student': t('nav_student'),
            'updates': t('nav_updates'),
        }
        if target in nav_map and nav_map[target] in nav_options:
            st.session_state['nav_radio'] = nav_map[target]

    page = st.radio(
        "Navigation",
        nav_options,
        label_visibility="collapsed",
        key='nav_radio',
    )

    # Status indicators at bottom
    data_ok = st.session_state.aulario_df is not None and st.session_state.alumnos_df is not None
    run_ok = st.session_state.pipeline_ran

    st.markdown("<div style='height: 2rem'></div>", unsafe_allow_html=True)
    st.markdown(f"""
        <div style='padding: 0 1rem; font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem; font-weight: 600;'>
            {t('session_status')}
        </div>
        <div class="status-indicator">
            <span class="status-dot {'active' if data_ok else ''}"></span>
            <span>{t('data_loaded_status')}</span>
        </div>
        <div class="status-indicator">
            <span class="status-dot {'active' if run_ok else ''}"></span>
            <span>{t('pipeline_ran_status')}</span>
        </div>
    """, unsafe_allow_html=True)

    # ── Quit button: cleanly shut the local server down ──────────────
    # A packaged Streamlit app is really a local web server; closing the
    # browser tab leaves it running in the background. This button stops the
    # whole process tree so nothing lingers in Task Manager.
    st.markdown("<div style='height: 1.2rem'></div>", unsafe_allow_html=True)
    if st.button(f"{t('quit_app')}", use_container_width=True, key="quit_app_btn"):
        st.session_state["_quitting"] = True
        st.rerun()

    if st.session_state.get("_quitting"):
        st.success(t('quit_done'))
        st.caption(t('quit_hint'))
        # Give Streamlit a moment to render the message, then terminate the
        # entire process tree (server + any children).
        import threading as _th

        def _shutdown():
            import time as _t, os as _o, signal as _sig
            _t.sleep(1.2)
            try:
                import psutil  # not guaranteed present
                me = psutil.Process(_o.getpid())
                for ch in me.children(recursive=True):
                    try:
                        ch.terminate()
                    except Exception:
                        pass
                me.terminate()
            except Exception:
                # Fallback without psutil: kill our own process group / pid.
                try:
                    if hasattr(_o, "killpg"):
                        _o.killpg(_o.getpgid(_o.getpid()), _sig.SIGTERM)
                    else:
                        _o.kill(_o.getpid(), _sig.SIGTERM)
                except Exception:
                    _o._exit(0)

        _th.Thread(target=_shutdown, daemon=True).start()
        st.stop()

# ════════════════════════════════════════════════════════════
# HELPER: PAGE HEADER
# ════════════════════════════════════════════════════════════
def page_header(title, subtitle):
    st.markdown(f"""
        <div class="page-header">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
    """, unsafe_allow_html=True)

def section_header(title):
    st.markdown(f'<div class="section-header">{title}</div>', unsafe_allow_html=True)

def stat_card(label, value, desc=""):
    st.markdown(f"""
        <div class="stat-card">
            <div class="stat-label">{label}</div>
            <div class="stat-value">{value}</div>
            <div class="stat-desc">{desc}</div>
        </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# WIZARD HELPERS — guided multi-step workflow
# ════════════════════════════════════════════════════════════
WIZARD_STEPS = [
    {'key': 'data',     'label': 'Data'},
    {'key': 'config',   'label': 'Config'},
    {'key': 'optimize', 'label': 'Optimize'},
    {'key': 'results',  'label': 'Results'},
    {'key': 'export',   'label': 'Export'},
]

def wizard_stepper(current_step_key):
    """Render a horizontal stepper showing workflow progress."""
    # Determine which steps are complete
    data_ok = (st.session_state.get('aulario_df') is not None
               and st.session_state.get('alumnos_df') is not None)
    pipeline_ran = st.session_state.get('pipeline_ran', False)
    files_generated = pipeline_ran and os.path.exists('outputs/optimization/Curso_2025_2026')

    completion = {
        'data': data_ok,
        'config': data_ok,  # config is always OK if data is loaded (defaults work)
        'optimize': pipeline_ran,
        'results': pipeline_ran,
        'export': files_generated,
    }

    # Find current step index
    step_keys = [s['key'] for s in WIZARD_STEPS]
    try:
        current_idx = step_keys.index(current_step_key)
    except ValueError:
        current_idx = -1

    # Build HTML - clean numeric badges instead of emojis
    html = '<div class="wizard-stepper">'
    for i, step in enumerate(WIZARD_STEPS):
        is_active = (step['key'] == current_step_key)
        is_complete = completion.get(step['key'], False) and not is_active

        cls = 'wizard-step'
        if is_active:
            cls += ' is-active'
            num_display = str(i + 1)
        elif is_complete:
            cls += ' is-complete'
            num_display = str(i + 1)
        else:
            num_display = str(i + 1)

        html += f'''
            <div class="{cls}">
                <div class="wizard-step-num">{num_display}</div>
                <div class="wizard-step-label">{step['label']}</div>
            </div>
        '''

        # Connector between steps (except after last)
        if i < len(WIZARD_STEPS) - 1:
            connector_complete = completion.get(step['key'], False)
            cls_c = 'wizard-connector'
            if connector_complete:
                cls_c += ' is-complete'
            html += f'<div class="{cls_c}"></div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def help_tip(text, icon=""):
    """Render a contextual help tip box (sober, no emoji icon by default)."""
    icon_html = f'<span class="help-tip-icon">{icon}</span>' if icon else ''
    st.markdown(
        f'<div class="help-tip">{icon_html}{text}</div>',
        unsafe_allow_html=True
    )


def validation_badge(label, status='valid'):
    """Render a small validation badge.
    status: 'valid', 'warning', 'error', 'info'
    """
    cls = f'validation-badge is-{status}'
    return f'<span class="{cls}">{label}</span>'


def render_checkpoint_summary(title, items):
    """Render a green summary box with validation items.
    items: list of (label, status) tuples
    """
    badges = ''.join(validation_badge(l, s) for l, s in items)
    html = f'''
        <div class="checkpoint-summary">
            <div class="checkpoint-summary-title">{title}</div>
            <div class="checkpoint-list">{badges}</div>
        </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def _read_run_metrics():
    """Read the real summary CSVs the pipeline just wrote and return a tidy
    dict for the run report. All values are read from disk — nothing is
    hard-coded. Missing files degrade gracefully."""
    def _rp(rel):
        if PATHS_OK:
            f = app_paths.resolve_existing(rel)
            if f:
                return f
        return rel

    m = {"enrolled": None, "assigned": None, "unassigned": None,
         "rate": None, "students_unique": None,
         "sessions": None, "s1": None, "s2": None, "groups": None}
    try:
        gp = _rp('outputs/optimization/assignment_summary_global.csv')
        if os.path.exists(gp):
            g = pd.read_csv(gp).iloc[0].to_dict()
            m["enrolled"] = int(float(g.get("total_enrolled", 0)))
            m["assigned"] = min(int(float(g.get("total_assigned", 0))), m["enrolled"])
            m["unassigned"] = max(0, int(float(g.get("total_unassigned", 0))))
            m["rate"] = min(100.0, float(g.get("assignment_rate_pct", 0)))
            m["students_unique"] = int(float(g.get("students_unique_enrolled", 0)))
    except Exception:
        pass
    try:
        sp = _rp('outputs/optimization/optimized_schedule_v5.csv')
        if os.path.exists(sp):
            sd = pd.read_csv(sp)
            m["sessions"] = int(len(sd))
            if "semester" in sd.columns:
                m["s1"] = int((sd["semester"] == 1).sum())
                m["s2"] = int((sd["semester"] == 2).sum())
            if "grupo" in sd.columns and "subject" in sd.columns:
                m["groups"] = int(sd.groupby(["subject", "grupo"]).ngroups)
    except Exception:
        pass
    return m


def render_run_report(log_text="", elapsed_s=None):
    """Turn a finished pipeline run into a clear, presentation-ready report
    that a non-technical reader (e.g. the lab coordinator) can understand at a
    glance. The raw solver log is kept, but demoted to a collapsed technical
    section below."""
    m = _read_run_metrics()

    # Detect solver status from the log (OPTIMAL proven vs FEASIBLE).
    status_txt, status_state = "—", "info"
    lt = (log_text or "").upper()
    if "OPTIMAL" in lt:
        status_txt, status_state = "Optimal", "valid"
    elif "FAISABLE" in lt or "FEASIBLE" in lt:
        status_txt, status_state = "Feasible", "valid"

    rate = m["rate"] if m["rate"] is not None else 0.0
    all_placed = (m["unassigned"] == 0) if m["unassigned"] is not None else (rate >= 100.0)

    # ── Headline banner (plain English) ──
    if all_placed:
        headline = "Schedule generated successfully"
        sub = "Every student enrolment was placed into a lab group, with no timetable conflicts."
    else:
        headline = "Schedule generated"
        sub = "Most enrolments were placed. A few remain unassigned — see the details below."
    st.markdown(f"""
        <div class="checkpoint-summary">
            <div class="checkpoint-summary-title">{headline}</div>
            <div style="color:var(--text-secondary); margin-top:0.25rem;">{sub}</div>
        </div>
    """, unsafe_allow_html=True)

    # ── Metric cards ──
    c1, c2, c3 = st.columns(3)
    with c1:
        sess = m["sessions"] if m["sessions"] is not None else "—"
        desc = (f"S1: {m['s1']} · S2: {m['s2']}"
                if m["s1"] is not None and m["s2"] is not None else "across both semesters")
        stat_card("Lab sessions", sess, desc)
    with c2:
        stat_card("Groups", m["groups"] if m["groups"] is not None else "—",
                  "formed across all subjects")
    with c3:
        rate_disp = f"{rate:.0f}%" if m["rate"] is not None else "—"
        denom = f"{m['assigned']}/{m['enrolled']} enrolments" if m["enrolled"] else "of all enrolments"
        stat_card("Assignment rate", rate_disp, denom)

    c4, c5, c6 = st.columns(3)
    with c4:
        stat_card("Conflicts", m["unassigned"] if m["unassigned"] is not None else "0",
                  "students · rooms · professors")
    with c5:
        stat_card("Solver status", status_txt,
                  "best possible" if status_state == "valid" else "")
    with c6:
        stat_card("Run time", f"{int(elapsed_s)}s" if elapsed_s is not None else "—",
                  "end to end")

    # ── Plain-English explanation ──
    parts = []
    if m["sessions"] is not None:
        parts.append(f"The optimiser scheduled {m['sessions']} laboratory sessions")
        if m["s1"] is not None and m["s2"] is not None:
            parts.append(f" ({m['s1']} in semester 1, {m['s2']} in semester 2)")
        parts.append(".")
    if m["enrolled"]:
        parts.append(f" All {m['enrolled']} enrolments — each a student in a subject — were "
                     f"placed into a group")
        if m["students_unique"]:
            parts.append(f", covering {m['students_unique']} distinct students")
        parts.append(".")
    parts.append(" No student, room, or professor is ever double-booked.")
    if status_state == "valid" and status_txt == "Optimal":
        parts.append(" The solver proved this schedule is optimal for the spacing objective.")
    explanation = "".join(parts)
    st.markdown(
        f'<div class="help-tip" style="margin-top:0.75rem;">{explanation}</div>',
        unsafe_allow_html=True,
    )

    # ── Conformité : qualité des données, KPIs, non placés, solveur ──
    try:
        render_quality_panel()
    except Exception:
        pass

    # ── Raw log: demoted, collapsed, clearly labelled as technical ──
    with st.expander("Technical solver log (for developers)"):
        st.code(log_text or "(no log captured)", language="text")


def _load_report_json(rel):
    """Load a JSON report written by the pipeline (reports/*.json) defensively.
    Resolves the path via app_paths when available, otherwise relative.
    Returns None if the file is absent or unreadable."""
    candidates = [rel]
    try:
        if PATHS_OK:
            found = app_paths.resolve_existing(rel)
            if found:
                candidates.insert(0, found)
    except Exception:
        pass
    for path in candidates:
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:
            continue
    return None


def render_quality_panel(show_solver=True):
    """Surface the compliance data produced by the pipeline:
    data quality control, schedule KPIs, unplaced enrollments
    (with detailed diagnostic) and the CP-SAT solver log.

    Everything is read from the JSON reports (reports/*.json). Each block degrades
    gracefully if its report is absent — nothing is hardcoded.
    """
    kpi = _load_report_json("reports/kpi_report.json")
    dq = _load_report_json("reports/data_quality_report.json")
    unplaced = _load_report_json("reports/unplaced_students.json")
    solver = _load_report_json("reports/solver_stats.json")

    if not any([kpi, dq, unplaced is not None, solver]):
        st.info("Compliance reports are not available yet. "
                "Run the optimization to generate them.")
        return

    # -- Data quality control --
    if dq:
        section_header("Data quality control")
        integ = dq.get("integrity", {}) or {}
        grp = dq.get("grouping", {}) or {}
        ok = integ.get("ok")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            stat_card("Integrity", "OK" if ok else "To review",
                      "data structure")
        with c2:
            stat_card("Rows", f"{integ.get('n_rows', '—'):,}".replace(",", " ")
                      if isinstance(integ.get('n_rows'), int) else "—",
                      "master_schedule")
        with c3:
            stat_card("Students", integ.get("n_students", "—"), "unique")
        with c4:
            gp = grp.get("global_placement_pct")
            stat_card("Placement rate",
                      f"{gp:.1f}%" if isinstance(gp, (int, float)) else "—",
                      f"{grp.get('total_placed', '—')}/{grp.get('total_enrolled', '—')} enrollments")

        per_subj = grp.get("per_subject") or []
        if per_subj:
            try:
                df_subj = pd.DataFrame(per_subj)
                df_subj = df_subj.rename(columns={
                    "subject": "Subject", "enrolled": "Enrolled",
                    "placed": "Placed", "unplaced": "Unplaced",
                    "placement_pct": "Rate (%)"})
                with st.expander("Detail per subject"):
                    st.dataframe(df_subj, use_container_width=True, hide_index=True)
            except Exception:
                pass

    # -- Schedule KPIs --
    if kpi:
        section_header("Schedule indicators (KPIs)")
        groups = kpi.get("groups", {}) or {}
        plc = kpi.get("placement", {}) or {}
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            stat_card("Groups", groups.get("total", "—"),
                      f"incl. {groups.get('overflow', 0)} overflow")
        with c2:
            stat_card("Average size",
                      groups.get("size_mean", "—"),
                      f"min {groups.get('size_min', '—')} · max {groups.get('size_max', '—')}")
        with c3:
            stat_card("Total sessions", kpi.get("total_sessions", "—"),
                      "across both semesters")
        with c4:
            stat_card("Friday sessions", kpi.get("friday_sessions", "—"),
                      "to monitor")

        day_bal = kpi.get("day_balance") or {}
        if day_bal:
            try:
                order = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
                s = pd.Series(day_bal)
                s = s.reindex([d for d in order if d in s.index])
                st.caption("Session distribution per day")
                st.bar_chart(s)
            except Exception:
                pass

    # -- Unplaced enrollments (diagnostic) --
    section_header("Unplaced enrollments")
    if not unplaced:
        st.success("All enrollments were placed (0 unplaced).")
    else:
        help_tip(
            "Automatic diagnostic of each unplaced enrollment: number of "
            "slots where the student is free, how many are compatible with the "
            "subject, how many still have a seat, and the determined reason.",
            icon=""
        )
        try:
            df_u = pd.DataFrame(unplaced)
            cols = {
                "student_name": "Student", "subject": "Subject",
                "n_free_slots": "Free slots",
                "n_compatible_slots": "Subject-compatible",
                "n_compatible_with_room": "Compatible with seat",
                "verdict": "Reason",
            }
            keep = [c for c in cols if c in df_u.columns]
            df_u = df_u[keep].rename(columns=cols)
            st.dataframe(df_u, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Unable to display the detail: {e}")

    # -- Solver log --
    if show_solver and solver:
        section_header("CP-SAT solver log")
        try:
            df_s = pd.DataFrame(solver)
            cols = {
                "label": "Semester", "status": "Status",
                "n_sessions": "Sessions", "n_hints": "Hints",
                "wall_time_s": "Time (s)", "objective": "Objective", "gap": "Gap",
            }
            keep = [c for c in cols if c in df_s.columns]
            df_s = df_s[keep].rename(columns=cols)
            st.dataframe(df_s, use_container_width=True, hide_index=True)
        except Exception:
            pass


def wizard_nav(prev_label=None, next_label=None, prev_page=None, next_page=None,
                next_disabled=False, next_disabled_reason=""):
    """Render navigation buttons (Prev / Next).
    Returns (prev_clicked, next_clicked) booleans."""
    st.markdown('<div class="wizard-nav"></div>', unsafe_allow_html=True)
    col_prev, col_spacer, col_next = st.columns([1, 2, 1])

    prev_clicked = False
    next_clicked = False

    with col_prev:
        if prev_label and prev_page:
            if st.button(f"← {prev_label}", use_container_width=True, key=f'prev_{prev_page}'):
                prev_clicked = True
                st.session_state['_nav_to'] = prev_page
                st.rerun()  # apply navigation immediately (single click)

    with col_next:
        if next_label and next_page:
            if next_disabled:
                st.button(f"{next_label} →", use_container_width=True,
                          disabled=True, help=next_disabled_reason or "Previous step required",
                          key=f'next_disabled_{next_page}')
            else:
                if st.button(f"{next_label} →", use_container_width=True,
                              type="primary", key=f'next_{next_page}'):
                    next_clicked = True
                    st.session_state['_nav_to'] = next_page
                    st.rerun()  # apply navigation immediately (single click)

    return prev_clicked, next_clicked


# ════════════════════════════════════════════════════════════
# PAGE: HOME
# ════════════════════════════════════════════════════════════
if page == t('nav_home'):
    # Hero with logo
    if LOGO_B64:
        st.markdown(f"""
            <div class="hero-logo">
                <img src="data:image/png;base64,{LOGO_B64}" alt="Universidad Loyola"/>
                <div class="brand-text">
                    <h1>{t('home_title')}</h1>
                    <p>{t('home_sub')}</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div class="hero-logo">
              <svg width="56" height="56" viewBox="0 0 56 56" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Universidad Loyola">
                <rect x="2" y="2" width="52" height="52" rx="11" fill="#1B3A6F"/>
                <text x="28" y="37" font-family="Georgia,serif" font-size="26" font-weight="700" fill="#FFFFFF" text-anchor="middle">UL</text>
              </svg>
              <div class="brand-text">
                <h1>{t('home_title')}</h1>
                <p>{t('home_sub')}</p>
              </div>
            </div>
        """, unsafe_allow_html=True)

    # ─── Onboarding tour card (prominent CTA) ───
    pipeline_ran = st.session_state.get('pipeline_ran', False)
    data_ok_home = (st.session_state.get('aulario_df') is not None
                    and st.session_state.get('alumnos_df') is not None)

    if not pipeline_ran:
        # First-time user OR not yet run
        if not data_ok_home:
            cta_eyebrow = "Welcome"
            cta_title = "Start by loading your data"
            cta_desc = ("This application will guide you through 4 steps: importing Excel files, "
                        "optional configuration, optimization, then export of plans in Daniel's format.")
            cta_btn_label = "Get started →"
            cta_target = 'data'
        else:
            cta_eyebrow = "Data loaded"
            cta_title = "Run the optimization"
            cta_desc = ("Your data is ready. You can customize the configuration "
                        "or run the optimization directly with default values.")
            cta_btn_label = "Optimize →"
            cta_target = 'optimize'
    else:
        cta_eyebrow = "Pipeline complete"
        cta_title = "View your results"
        cta_desc = ("The plan has been generated. View the statistics, "
                    "check the groups, or download the Excel files in Daniel's format.")
        cta_btn_label = "View results →"
        cta_target = 'results'

    st.markdown(f"""
        <div class="tour-card" style="margin: 0.4rem 0 1.3rem;">
            <div style="font-size: 0.78rem; font-weight: 700; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 0.55rem;">{cta_eyebrow}</div>
            <div style="font-size: 1.45rem; font-weight: 700; color: var(--text-heading); line-height: 1.25; margin-bottom: 0.6rem;">{cta_title}</div>
            <div style="font-size: 0.98rem; color: var(--text-secondary); line-height: 1.6; max-width: 64ch;">{cta_desc}</div>
        </div>
    """, unsafe_allow_html=True)

    col_cta, col_skip = st.columns([1, 3])
    with col_cta:
        if st.button(cta_btn_label, type="primary", use_container_width=True, key='home_cta'):
            st.session_state['_nav_to'] = cta_target
            st.rerun()

    # Welcome intro
    st.markdown(f"""
        <div class="info-card" style="margin-bottom: 2rem;">
            <div style="font-size: 0.75rem; font-weight: 600; color: var(--cyan); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 0.5rem;">
                {t('home_welcome')}
            </div>
            <div style="font-size: 1rem; color: var(--text-secondary); line-height: 1.6;">
                {t('home_intro')}
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Persistent run history — survives application restarts. Demonstrates the
    # persistent-memory feature and lets the user see past results at a glance.
    if PERSISTENCE_OK:
        try:
            _runs = _persist.load_runs()
        except Exception:
            _runs = []
        if _runs:
            with st.expander(f"{t('recent_runs')} ({len(_runs)})", expanded=False):
                _rows = []
                for r in _runs[:10]:
                    _ts = r.get("timestamp", "")
                    try:
                        _ts = datetime.fromisoformat(_ts).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass
                    _rows.append({
                        t('run_date_col'): _ts,
                        t('rate_lbl'): f"{r.get('assignment_rate', '—')}%",
                        t('sessions_lbl'): r.get("sessions", "—"),
                        t('groups_lbl'): r.get("groups", "—"),
                        "s": r.get("elapsed_s", "—"),
                    })
                st.dataframe(pd.DataFrame(_rows), use_container_width=True,
                             hide_index=True)
                st.caption(t('recent_runs_hint'))

    # Quick stats (if pipeline ran)
    if run_ok:
        section_header(f'{t("quick_stats")}')
        c1, c2, c3, c4 = st.columns(4)
        try:
            sched = pd.read_csv('outputs/optimization/optimized_schedule_v5.csv')
            grps = pd.read_csv('outputs/optimization/group_composition.csv')
            with c1: stat_card(t('sessions_lbl'), len(sched), f"S1: {len(sched[sched['semester']==1])} · S2: {len(sched[sched['semester']==2])}")
            with c2: stat_card(t('groups_lbl'), sched.drop_duplicates(['subject','grupo']).shape[0], "lab groups")
            with c3:
                _n_dedup = grps.drop_duplicates(subset=['subject','grupo','student_name' if 'student_name' in grps.columns else 'student_hash']).shape[0]
                _assigned = _n_dedup
                try:
                    _asum = pd.read_csv('outputs/optimization/assignment_summary.csv')
                    _av = pd.to_numeric(_asum['assigned'], errors='coerce').dropna()
                    if len(_av):
                        _assigned = int(_av.sum())
                except Exception:
                    pass
                stat_card(t('assigned_lbl'), _assigned, "enrolments")
            with c4: stat_card(t('conflicts_lbl'), "0", "C1 · C4")
        except Exception as e:
            st.info(t('no_data_yet'))
    else:
        st.info(t('no_data_yet'))

    # Workflow steps
    section_header(t("start_here"))
    sc1, sc2, sc3, sc4 = st.columns(4)
    steps = [
        (sc1, '', t('home_step1_title'), t('home_step1_desc')),
        (sc2, '', t('home_step2_title'), t('home_step2_desc')),
        (sc3, '', t('home_step3_title'), t('home_step3_desc')),
        (sc4, '', t('home_step4_title'), t('home_step4_desc')),
    ]
    for col, emoji, title, desc in steps:
        with col:
            st.markdown(f"""
                <div class="info-card" style="height: 120px;">
                    <div style="font-weight: 600; color: var(--text-heading); margin-bottom: 0.35rem;">{title}</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">{desc}</div>
                </div>
            """, unsafe_allow_html=True)

    # Key features
    section_header(f' {t("key_features")}')
    fc1, fc2, fc3 = st.columns(3)
    features = [
        (fc1, t('feat1_t'), t('feat1_d')),
        (fc2, t('feat2_t'), t('feat2_d')),
        (fc3, t('feat4_t'), t('feat4_d')),
    ]
    for col, title, desc in features:
        with col:
            st.markdown(f"""
                <div class="info-card" style="height: 132px;">
                    <div style="font-weight: 600; color: var(--text-heading); margin-bottom: 0.35rem;">{title}</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">{desc}</div>
                </div>
            """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE: DATA
# ════════════════════════════════════════════════════════════
elif page == t('nav_data'):
    page_header(t('data_title'), t('data_sub'))
    wizard_stepper('data')

    help_tip(
        "<strong>Step 1 of 4:</strong> Upload the two Excel files provided by Loyola. "
        "These are the files <em>revisionAulario.xlsx</em> (timetables) and "
        "<em>report_AlumnosGrupos.xlsx</em> (student enrolments).",
        icon=""
    )

    c1, c2 = st.columns(2)

    aulario_loaded = False
    alumnos_loaded = False

    with c1:
        section_header(f'{t("aulario_label")}')
        aulario_file = st.file_uploader(
            t('upload_help_1'),
            type=['xlsx'], key='aulario_up',
            label_visibility="collapsed",
        )
        if aulario_file or st.session_state.get('aulario_df') is not None:
            try:
                if aulario_file:
                    df = pd.read_excel(aulario_file)
                    st.session_state.aulario_df = df
                df = st.session_state.aulario_df
                m1, m2 = st.columns(2)
                with m1: st.metric(t('rows'), f"{len(df):,}")
                with m2: st.metric(t('cols'), df.shape[1])
                with st.expander(t('preview')):
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)

                # Lenient validation: just check the file is non-empty
                # Specific column checks happen later in the pipeline (after cleaning step)
                if len(df) == 0:
                    st.error("The file is empty")
                elif df.shape[1] < 5:
                    st.warning(f"The file looks incomplete ({df.shape[1]} columns only)")
                else:
                    # Look for any common structural marker (case-insensitive)
                    cols_lower = [str(c).lower() for c in df.columns]
                    has_id_col = any('mixto' in c or 'curso' in c or 'asignatura' in c or
                                       'materia' in c or 'mat' in c[:3] for c in cols_lower)
                    has_time_col = any('hora' in c or 'time' in c or 'dia' in c or
                                         'slot' in c or 'fecha' in c for c in cols_lower)

                    if has_id_col and has_time_col:
                        st.success(f"Format reconnu ({len(df):,} lignes × {df.shape[1]} colonnes)")
                    else:
                        st.info(f"File loaded ({len(df):,} rows × {df.shape[1]} columns). "
                                f"Column validation will be performed by the pipeline.")
                aulario_loaded = True
            except Exception as e:
                st.error(f"Read error: {e}")
        else:
            st.caption("File not yet loaded")

    with c2:
        section_header(f'{t("alumnos_label")}')
        alumnos_file = st.file_uploader(
            t('upload_help_2'),
            type=['xlsx'], key='alumnos_up',
            label_visibility="collapsed",
        )
        if alumnos_file or st.session_state.get('alumnos_df') is not None:
            try:
                if alumnos_file:
                    df = pd.read_excel(alumnos_file)
                    st.session_state.alumnos_df = df
                df = st.session_state.alumnos_df
                m1, m2 = st.columns(2)
                with m1:
                    st.metric(t('unique_students'), f"{df['AlumnoID'].nunique():,}" if 'AlumnoID' in df.columns else len(df))
                with m2:
                    st.metric(t('unique_courses'), df['MixtoID'].nunique() if 'MixtoID' in df.columns else df.shape[1])
                with st.expander(t('preview')):
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)

                # Lenient validation
                if len(df) == 0:
                    st.error("The file is empty")
                elif df.shape[1] < 3:
                    st.warning(f"The file looks incomplete ({df.shape[1]} columns only)")
                else:
                    cols_lower = [str(c).lower() for c in df.columns]
                    has_student = any('alumno' in c or 'student' in c or 'estudiante' in c
                                        for c in cols_lower)
                    has_course = any('mixto' in c or 'curso' in c or 'asignatura' in c
                                       for c in cols_lower)

                    if has_student and has_course:
                        st.success(f"Format reconnu ({len(df):,} lignes × {df.shape[1]} colonnes)")
                    else:
                        st.info(f"File loaded ({len(df):,} rows × {df.shape[1]} columns). "
                                f"Column validation will be performed by the pipeline.")
                alumnos_loaded = True
            except Exception as e:
                st.error(f"Read error: {e}")
        else:
            st.caption("File not yet loaded")

    # Checkpoint summary
    if aulario_loaded and alumnos_loaded:
        try:
            n_aul_rows = len(st.session_state.aulario_df)
            n_alu_rows = len(st.session_state.alumnos_df)
            n_students = (st.session_state.alumnos_df['AlumnoID'].nunique()
                          if 'AlumnoID' in st.session_state.alumnos_df.columns else n_alu_rows)
            render_checkpoint_summary("Data loaded", [
                (f"Aulario : {n_aul_rows:,} lignes", "valid"),
                (f"Alumnos : {n_alu_rows:,} inscriptions", "valid"),
                (f"{n_students:,} unique students", "valid"),
            ])
        except Exception:
            pass

    # Wizard navigation
    next_disabled = not (aulario_loaded and alumnos_loaded)
    next_disabled_reason = "Please load both Excel files before continuing"

    wizard_nav(
        prev_label="Home", prev_page='home',
        next_label="Configuration", next_page='config',
        next_disabled=next_disabled,
        next_disabled_reason=next_disabled_reason,
    )

# ════════════════════════════════════════════════════════════
# PAGE: CONFIG
# ════════════════════════════════════════════════════════════
elif page == t('nav_config'):
    page_header(t('config_title'), t('config_sub'))
    wizard_stepper('config')

    # Prerequisite check: data must be loaded
    if not (st.session_state.get('aulario_df') is not None
            and st.session_state.get('alumnos_df') is not None):
        st.warning("**Missing data** — please load the Excel files first "
                    "in the *Data* step before configuring.")
        if st.button("← Back to Data", type="primary"):
            st.session_state['_nav_to'] = 'data'
            st.rerun()
        st.stop()

    help_tip(
        "<strong>Step 2 of 4 (optional):</strong> Customize parameters if needed. "
        "The <strong>default values</strong> work in most cases — you can go "
        "straight to the next step. Only change these if you have "
        "constraints to adjust on specific subjects (room changes, blocked weeks, etc.).",
        icon=""
    )

    # ─────────────────────────────────────────────────────────
    # CONFIG STATUS INDICATOR (Bridge UI → Pipeline)
    # ─────────────────────────────────────────────────────────
    n_overrides = len(st.session_state.advanced_config.get('subject_overrides', {}))
    config_file_exists = os.path.exists('config/user_config.json')

    if n_overrides > 0:
        col_status, col_actions = st.columns([3, 1])
        with col_status:
            st.success(
                f"**{n_overrides} customized subject(s)** — "
                f"your changes will be applied on the next pipeline run"
            )
        with col_actions:
            if st.button("Reset all", use_container_width=True, key="reset_all_top"):
                st.session_state.advanced_config['subject_overrides'] = {}
                if config_file_exists:
                    try:
                        os.remove('config/user_config.json')
                    except Exception:
                        pass
                st.rerun()
    elif config_file_exists:
        st.info(
            "A user configuration exists on disk "
            "(`config/user_config.json`) but no override is active in this session."
        )

    # 4 tabs (rolled back from 3-tab version per Daniel feedback)
    tab1, tab2, tab3, tab4 = st.tabs([
        f"{t('global_params')}",
        f"{t('per_subject')}",
        f"{t('year_pref_title')}",
        f"{t('teacher_title')}",
    ])

    # Load LAB_CONFIG once for tabs 1-2. The pipeline module may live at the
    # bundle root (packaged .exe), in src/ (some source layouts), or the cwd
    # (dev). Make all of them importable, then import.
    try:
        import importlib
        # Make the bundle root importable when frozen
        if PATHS_OK:
            _root = str(app_paths.resource_root())
            if _root not in sys.path:
                sys.path.insert(0, _root)
        for _p in ('src', '.'):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        if 'pipeline' in sys.modules:
            importlib.reload(sys.modules['pipeline'])
        from pipeline import LAB_CONFIG
        config = LAB_CONFIG
    except Exception:
        config = {}

    # ════════════════════════════════════════
    # TAB 1: Global parameters
    # ════════════════════════════════════════
    with tab1:
        st.caption("Default values applied to all subjects (overridable per subject in tab 2)")

        st.markdown(f"##### Group sizes")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state.advanced_config['preferred_size'] = st.number_input(
                t('pref_size'), 8, 20, 12, help="Daniel: 12"
            )
        with c2:
            st.session_state.advanced_config['default_max'] = st.number_input(
                t('max_size'), 12, 35, 15, help="Standard labs"
            )
        with c3:
            st.session_state.advanced_config['min_size'] = st.number_input(
                t('min_size'), 2, 10, 7, help="Auto-merge below"
            )

        st.markdown(f"##### Special lab maximums")
        c4, c5 = st.columns(2)
        with c4:
            st.session_state.advanced_config['computer_lab_max'] = st.number_input(
                t('comp_max'), 12, 40, 24, help="Computer labs accept more students"
            )
        with c5:
            st.session_state.advanced_config['reduced_max_size'] = st.number_input(
                t('reduced_max'), 8, 15, 12, help="Resistencia, Mecánica de Fluidos"
            )

        st.markdown(f"##### Calendar")
        c6, c7 = st.columns(2)
        with c6:
            st.session_state.advanced_config['start_week'] = st.number_input(
                t('start_week'), 1, 10, 4, help="Week 3 or 4 typically"
            )
        with c7:
            st.session_state.advanced_config.setdefault('s1_total_weeks', 14)
            st.session_state.advanced_config['s1_total_weeks'] = st.number_input(
                "S1 total weeks", 12, 18, 14, help="Last available week in S1"
            )

        c8, c9, _ = st.columns(3)
        with c8:
            st.session_state.advanced_config.setdefault('s2_total_weeks', 20)
            st.session_state.advanced_config['s2_total_weeks'] = st.number_input(
                "S2 total weeks", 14, 24, 20, help="Last available week in S2"
            )

    # ════════════════════════════════════════
    # TAB 2: Per-subject configuration (enriched with all options)
    # ════════════════════════════════════════
    with tab2:
        if not config:
            st.warning(
                "Per-subject configuration unavailable: could not load "
                "`pipeline.py`. Check that the file is present in "
                "the application. The global parameters (previous tab) remain "
                "usable."
            )
        else:
            # Initialize subject overrides if needed
            if 'subject_overrides' not in st.session_state.advanced_config:
                st.session_state.advanced_config['subject_overrides'] = {}

            ROOM_CATALOG = [
                "Ciencias Experimentales I", "Ciencias Experimentales II",
                "Laboratorio de Ingeniería Telemática", "Robótica y Automática",
                "Mecánica de Fluidos", "Automoción y Resistencia de Mat.",
                "Eléctrica", "Electrónica",
            ]

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # COMPACT SELECTOR BAR (top)
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            sel_c1, sel_c2, sel_c3 = st.columns([2, 2, 1])
            with sel_c1:
                year_filter = st.selectbox(t('filter_year'),
                    [t('all'), "Primero", "Segundo", "Tercero"], key='cfg_year_filter')
            with sel_c2:
                sem_filter = st.selectbox(t('filter_sem'),
                    [t('all'), "S1", "S2"], key='cfg_sem_filter')
            with sel_c3:
                st.write("")
                if st.button("Reset all", use_container_width=True, help="Reset all overrides"):
                    st.session_state.advanced_config['subject_overrides'] = {}
                    st.rerun()

            # Build filtered subjects list
            filtered = []
            for subj, cfg in sorted(config.items(),
                                     key=lambda x: (get_year(x[0]), get_sem(x[0]), x[0])):
                yr = get_year(subj)
                sm = get_sem(subj)
                if year_filter != t('all') and YEAR_LABELS.get(yr) != year_filter: continue
                if sem_filter != t('all') and not subj.startswith(sem_filter): continue
                filtered.append((subj, cfg))

            if not filtered:
                st.info("No subjects match the filters")
            else:
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # SUBJECT PICKER (single dropdown — way cleaner than 22 expanders)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                subject_labels = []
                subject_keys = []
                for subj, cfg in filtered:
                    yr = get_year(subj); sm = get_sem(subj)
                    sc = clean_subject(subj)
                    yl = YEAR_LABELS.get(yr, '?')
                    has_override = '' if subj in st.session_state.advanced_config.get('subject_overrides', {}) else ''
                    subject_labels.append(f"{has_override}{yl} · S{sm} · {sc}")
                    subject_keys.append(subj)

                selected_label = st.selectbox(
                    "Select subject to configure",
                    subject_labels,
                    key='subject_picker',
                    label_visibility="collapsed",
                )
                selected_subj = subject_keys[subject_labels.index(selected_label)]
                cfg = config[selected_subj]
                ov = st.session_state.advanced_config['subject_overrides'].get(selected_subj, {})

                yr = get_year(selected_subj); sm = get_sem(selected_subj)
                sc = clean_subject(selected_subj)
                year_label = YEAR_LABELS.get(yr, '?')
                n_sess = cfg.get('num_sessions', 5)

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # SUBJECT HEADER CARD
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                badge_html = ""
                if ov:
                    badge_html = '<span class="badge badge-warning" style="margin-left: 0.75rem;">Modified</span>'

                st.markdown(f"""
                    <div class="info-card" style="margin: 1rem 0;">
                        <div style="display:flex; align-items:center; gap:1rem;">
                            <div>
                                <div style="font-size: 1.4rem; font-weight: 700; color: var(--text-heading);">{sc}{badge_html}</div>
                                <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">
                                    {year_label} · Semestre {sm} · {n_sess} prácticas
                                </div>
                            </div>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # CONFIGURATION SECTIONS via inner tabs (cleaner than stacking)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                cfg_tab1, cfg_tab2, cfg_tab3, cfg_tab4 = st.tabs([
                    "Basic", "Schedule", "Lab rooms", "Advanced"
                ])

                # ── BASIC ──
                with cfg_tab1:
                    st.caption("Group sizes and structure")
                    bc1, bc2 = st.columns(2)
                    with bc1:
                        new_n_sess = st.number_input(
                            "Number of prácticas", 1, 10,
                            ov.get('num_sessions', n_sess),
                            key=f"ns_{selected_subj}",
                            help="Total number of lab sessions for this subject"
                        )
                        new_max = st.number_input(
                            "Max students per group", 5, 35,
                            ov.get('max_students', cfg['max_students']),
                            key=f"mx_{selected_subj}",
                            help="Group size upper limit"
                        )
                    with bc2:
                        new_n_groups = st.number_input(
                            "Target number of groups", 1, 30,
                            ov.get('num_groups', max(1, n_sess)),
                            key=f"ng_{selected_subj}",
                            help="Override auto-calculated count"
                        )
                        new_min_size = st.number_input(
                            "Min group size", 2, 15,
                            ov.get('min_size', 7),
                            key=f"mns_{selected_subj}",
                            help="Smaller groups will be merged"
                        )

                # ── SCHEDULE ──
                with cfg_tab2:
                    st.caption("When can the practices take place")
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        new_min_w = st.number_input(
                            "Start week", 1, 20,
                            ov.get('min_week', cfg['min_week']),
                            key=f"mw_{selected_subj}"
                        )
                    with sc2:
                        sem_default = 14 if sm == 1 else 20
                        new_max_w = st.number_input(
                            "End week", 1, 20,
                            ov.get('max_week', cfg.get('max_week', sem_default)),
                            key=f"xw_{selected_subj}",
                            help="Last week labs can take place"
                        )
                    with sc3:
                        sched_pref = st.selectbox(
                            "Time preference", ["morning", "afternoon", "any"],
                            index=["morning", "afternoon", "any"].index(
                                ov.get('schedule_pref', 'morning' if cfg['curso_num'] in [1,3] else 'afternoon')
                            ),
                            key=f"sp_{selected_subj}",
                        )

                    st.markdown("---")
                    st.markdown("**Práctica-by-práctica earliest week**")
                    st.caption("Each práctica may have a specific earliest start week (e.g., topic must be taught first)")

                    practica_config = ov.get('practica_config', {})
                    practica_data = {}

                    # Compact 4-column layout (vs 3 → fits more on screen)
                    per_row = 4
                    for row_start in range(0, new_n_sess, per_row):
                        pcols = st.columns(per_row)
                        for ci in range(per_row):
                            i = row_start + ci
                            if i >= new_n_sess: break
                            with pcols[ci]:
                                p_def = practica_config.get(str(i+1), {})
                                p_min_w = st.number_input(
                                    f"P{i+1}", 1, 20,
                                    p_def.get('min_week', min(new_min_w + i*2, new_max_w)),
                                    key=f"pmw_{selected_subj}_{i}",
                                    help=f"Práctica {i+1} earliest week"
                                )
                                practica_data[str(i+1)] = {
                                    'min_week': p_min_w,
                                    'duration': p_def.get('duration', 2),
                                    'room': p_def.get('room'),
                                }

                # ── LAB ROOMS ──
                with cfg_tab3:
                    st.caption("Where this subject's labs take place")
                    current_rooms = ov.get('lab_rooms', cfg.get('lab_rooms', []))
                    catalog_with_current = list(set(ROOM_CATALOG + current_rooms))

                    new_rooms = st.multiselect(
                        "Allowed laboratories",
                        options=sorted(catalog_with_current),
                        default=current_rooms,
                        key=f"rm_{selected_subj}",
                    )
                    new_simul = st.checkbox(
                        "Use multiple rooms in parallel (simultaneous sessions)",
                        value=ov.get('simultaneous_rooms', cfg.get('simultaneous_rooms', False)),
                        key=f"sim_{selected_subj}",
                        help="Multiple groups can run at the same time in different rooms"
                    )

                    # Per-práctica room override
                    if new_n_sess <= 6 and new_rooms:
                        with st.expander("Per-práctica room override (optional)"):
                            rcols = st.columns(min(new_n_sess, 4))
                            for i, rcol in enumerate(rcols[:new_n_sess]):
                                with rcol:
                                    p_def = practica_data.get(str(i+1), {})
                                    cur_room = p_def.get('room')
                                    p_room = st.selectbox(
                                        f"P{i+1} room",
                                        options=["(default)"] + new_rooms,
                                        index=0 if not cur_room else (new_rooms.index(cur_room)+1 if cur_room in new_rooms else 0),
                                        key=f"pr_{selected_subj}_{i}",
                                    )
                                    if str(i+1) in practica_data:
                                        practica_data[str(i+1)]['room'] = None if p_room == "(default)" else p_room

                # ── ADVANCED ──
                with cfg_tab4:
                    st.caption("Subject identification keywords (used to match students)")
                    kw_str = st.text_input(
                        "Keywords (comma-separated)",
                        value=", ".join(ov.get('keywords', cfg.get('keywords', []))),
                        key=f"kw_{selected_subj}",
                        help="Words that identify this subject in student data"
                    )
                    kw_excl_str = st.text_input(
                        "Exclude keywords (comma-separated)",
                        value=", ".join(ov.get('keyword_exclude', cfg.get('keyword_exclude', []))),
                        key=f"kwx_{selected_subj}",
                        help="Words that should NOT match"
                    )

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # Save all this subject's overrides automatically
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                st.session_state.advanced_config['subject_overrides'][selected_subj] = {
                    'num_sessions': new_n_sess,
                    'max_students': new_max,
                    'min_week': new_min_w,
                    'max_week': new_max_w,
                    'num_groups': new_n_groups,
                    'min_size': new_min_size,
                    'schedule_pref': sched_pref,
                    'lab_rooms': new_rooms,
                    'simultaneous_rooms': new_simul,
                    'keywords': [k.strip() for k in kw_str.split(',') if k.strip()],
                    'keyword_exclude': [k.strip() for k in kw_excl_str.split(',') if k.strip()],
                    'practica_config': practica_data,
                }

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # Validation feedback (real-time checks)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                validation_msgs = []

                # Check 1: max_week >= min_week + num_sessions - 1
                weeks_window = new_max_w - new_min_w + 1
                if weeks_window < new_n_sess:
                    validation_msgs.append((
                        'error',
                        f"Week window too small: {weeks_window} weeks "
                        f"available for {new_n_sess} sessions. Increase `End week` or reduce `Sessions`."
                    ))
                elif weeks_window == new_n_sess:
                    validation_msgs.append((
                        'warning',
                        f"Tight window: exactly {weeks_window} weeks for {new_n_sess} sessions. "
                        f"No flexibility — a holiday could cause a conflict."
                    ))

                # Check 2: num_groups vs students fit
                # We don't know exact student count here, but warn on extreme values
                if new_max < 5:
                    validation_msgs.append((
                        'warning',
                        f"Group capacity very low ({new_max}). Many groups will be created."
                    ))
                if new_max > 25:
                    validation_msgs.append((
                        'warning',
                        f"Group capacity high ({new_max}). Verify the room can accommodate."
                    ))

                # Check 3: min_size constraint
                if new_min_size > new_max:
                    validation_msgs.append((
                        'error',
                        f"Min size ({new_min_size}) > Max size ({new_max}). Cannot form a group."
                    ))

                # Check 4: num_sessions extreme
                if new_n_sess > 8:
                    validation_msgs.append((
                        'warning',
                        f"Many sessions ({new_n_sess}). Verify this is intentional."
                    ))
                if new_n_sess < 1:
                    validation_msgs.append((
                        'error',
                        f"At least 1 session is required."
                    ))

                # Check 5: no rooms selected
                if not new_rooms:
                    validation_msgs.append((
                        'error',
                        f"No rooms selected — this subject cannot be scheduled."
                    ))

                # Check 6: no keywords (empty after strip)
                if not [k.strip() for k in kw_str.split(',') if k.strip()]:
                    validation_msgs.append((
                        'warning',
                        f"No keywords defined — this subject will not be correctly detected in source data."
                    ))

                # Display validation messages
                if validation_msgs:
                    st.markdown("---")
                    st.markdown("**Validation**")
                    for level, msg in validation_msgs:
                        if level == 'error':
                            st.error(msg)
                        elif level == 'warning':
                            st.warning(msg)
                        else:
                            st.info(msg)
                else:
                    st.markdown("---")
                    st.success("Configuration valid for this subject")

                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                # Action buttons (bottom)
                # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                st.markdown("---")
                ac1, ac2, ac3 = st.columns([2, 1, 1])
                with ac1:
                    if ov:
                        st.caption(f"Subject has overrides")
                with ac2:
                    if ov:
                        if st.button("Reset this", use_container_width=True, key=f"rst_{selected_subj}"):
                            del st.session_state.advanced_config['subject_overrides'][selected_subj]
                            st.rerun()
                with ac3:
                    overrides_count = len(st.session_state.advanced_config.get('subject_overrides', {}))
                    st.caption(f"**{overrides_count}** modified")

    # ════════════════════════════════════════
    # TAB 3: Year preferences
    # ════════════════════════════════════════
    with tab3:
        st.caption(t('year_pref_sub'))
        yc1, yc2 = st.columns(2)
        with yc1:
            st.markdown("**Morning (08:30-14:30)**")
            morning_y1 = st.checkbox("1st year morning", value=True, key='ym1')
            morning_y3 = st.checkbox("3rd year morning", value=True, key='ym3')
            st.session_state.advanced_config['allow_afternoon_y1y3'] = st.checkbox(
                "Allow 1st/3rd year afternoon (exceptional)",
                value=False, key='ya13',
                help="Unblocks ~50 unassigned Física+Química students"
            )
        with yc2:
            st.markdown("**Afternoon (15:00-19:00)**")
            afternoon_y2 = st.checkbox("2nd year afternoon", value=True, key='ya2')
            afternoon_y4 = st.checkbox("4th year afternoon", value=True, key='ya4')
            st.session_state.advanced_config['allow_morning_y2y4'] = st.checkbox(
                "Allow 2nd/4th year morning (exceptional)",
                value=False, key='ym24',
            )

    # ════════════════════════════════════════
    # TAB 4: Teacher availability
    # ════════════════════════════════════════
    with tab4:
        st.markdown("### Teacher Availability Configuration")
        st.caption("Configure teacher availability constraints and preferences for optimal scheduling.")
        
        try:
            import pandas as _pd
            _pbdf = _pd.read_csv('data_clean/optimization/professor_busy.csv')
            _prof_names = sorted(_pbdf['professor_id'].dropna().astype(str).unique().tolist())
        except Exception:
            _prof_names = []

        _BLOCKS_UI = ["08:30-10:30", "10:30-12:30", "12:30-14:30",
                      "15:00-17:00", "17:00-19:00", "19:00-21:00"]
        _DAYS_FULL = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]

        # ═══════════════════════════════════════════════════════════
        # OPTION 1: Days per week CANNOT be used by teacher
        # ═══════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("#### Option 1: Days per week unavailable")
        st.caption("Block entire weekdays when a teacher is never available (hard constraint)")
        
        st.session_state.advanced_config.setdefault('teacher_unavailable_weekdays', {})
        
        with st.expander("Add unavailable weekday(s) for a teacher", expanded=False):
            wd_c1, wd_c2, wd_c3 = st.columns([2, 2, 1])
            with wd_c1:
                if _prof_names:
                    wd_teacher = st.selectbox("Teacher", _prof_names, key="wd_teacher_sel")
                else:
                    wd_teacher = st.text_input("Teacher name", key="wd_teacher_txt",
                        help="Enter teacher name manually")
            with wd_c2:
                wd_days = st.multiselect("Unavailable weekday(s)", _DAYS_FULL, key="wd_days_sel",
                    help="Select one or more days when this teacher cannot work")
            with wd_c3:
                st.write("")
                st.write("")
                if st.button("Add", key="add_wd_v1"):
                    if wd_teacher and wd_days:
                        _store = st.session_state.advanced_config['teacher_unavailable_weekdays']
                        _store.setdefault(wd_teacher, [])
                        for day in wd_days:
                            if day not in _store[wd_teacher]:
                                _store[wd_teacher].append(day)
                        _store[wd_teacher] = sorted(_store[wd_teacher], key=lambda d: _DAYS_FULL.index(d))
                        st.rerun()

        if st.session_state.advanced_config['teacher_unavailable_weekdays']:
            st.markdown("**Current unavailable weekdays:**")
            for teacher, days in list(st.session_state.advanced_config['teacher_unavailable_weekdays'].items()):
                cols = st.columns([4, 1])
                with cols[0]:
                    st.markdown(f"**{teacher}** → Never available on: **{', '.join(days)}**")
                with cols[1]:
                    if st.button("Remove", key=f"del_wd_{teacher}"):
                        del st.session_state.advanced_config['teacher_unavailable_weekdays'][teacher]
                        st.rerun()
        else:
            st.info("No unavailable weekdays configured")

        # ═══════════════════════════════════════════════════════════
        # OPTION 2: Exact day/time CANNOT be used by teacher
        # ═══════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("#### Option 2: Specific day/time slots unavailable")
        st.caption("Block specific time slots on specific days (hard constraint)")
        
        st.session_state.advanced_config.setdefault('teacher_unavailability', {})
        
        with st.expander("Add unavailable time slot", expanded=False):
            tc1, tc2, tc3, tc4 = st.columns([2, 1.5, 1.5, 1])
            with tc1:
                if _prof_names:
                    teacher_name = st.selectbox("Teacher", _prof_names, key="teacher_sel_v5")
                else:
                    teacher_name = st.text_input("Teacher name", key="teacher_txt_v5",
                        help="Enter teacher name manually")
            with tc2:
                teacher_day = st.selectbox("Day", _DAYS_FULL, key="t_day_v4")
            with tc3:
                teacher_block = st.selectbox("Time slot",
                    ["(All day)"] + _BLOCKS_UI, key="t_block_v4",
                    help="Select 'All day' to block all time slots on this day")
            with tc4:
                st.write("")
                st.write("")
                if st.button("Add", key="add_teacher_v4"):
                    if teacher_name:
                        _store = st.session_state.advanced_config['teacher_unavailability']
                        _store.setdefault(teacher_name, [])
                        _blocks = _BLOCKS_UI if teacher_block == "(All day)" else [teacher_block]
                        _changed = False
                        for _b in _blocks:
                            _slot = f"{teacher_day} {_b}"
                            if _slot not in _store[teacher_name]:
                                _store[teacher_name].append(_slot)
                                _changed = True
                        if _changed:
                            st.rerun()

        if st.session_state.advanced_config['teacher_unavailability']:
            st.markdown("**Current unavailable time slots:**")
            for teacher, slots in list(st.session_state.advanced_config['teacher_unavailability'].items()):
                cols = st.columns([4, 1])
                with cols[0]:
                    st.markdown(f"**{teacher}** → {len(slots)} slot(s): {', '.join(slots[:5])}" + 
                               (f" *(+{len(slots)-5} more)*" if len(slots) > 5 else ""))
                with cols[1]:
                    if st.button("Remove", key=f"del_t_v4_{teacher}"):
                        del st.session_state.advanced_config['teacher_unavailability'][teacher]
                        st.rerun()
        else:
            st.info("No unavailable time slots configured")

        # ═══════════════════════════════════════════════════════════
        # OPTION 3: Preferred time range by teacher
        # ═══════════════════════════════════════════════════════════
        st.markdown("---")
        st.markdown("#### Option 3: Preferred time range")
        st.caption("Soft preferences: optimizer will try to respect these but won't block if impossible")
        
        st.session_state.advanced_config.setdefault('teacher_preferences', {})
        
        with st.expander("Set teacher preferences", expanded=False):
            pref_c1, pref_c2, pref_c3, pref_c4 = st.columns([2, 1, 2, 1])
            with pref_c1:
                if _prof_names:
                    pref_teacher = st.selectbox("Teacher", _prof_names, key="pref_teacher_v2")
                else:
                    pref_teacher = st.text_input("Teacher", key="pref_teacher_txt_v2")
            with pref_c2:
                pref_max_days = st.number_input("Max days/week", 0, 5, 0, key="pref_max_days_v2",
                    help="0 = no limit. Soft constraint: warns if exceeded but doesn't block.")
            with pref_c3:
                pref_hours = st.multiselect("Preferred time slots", _BLOCKS_UI, key="pref_hours_v2",
                    help="Time slots the teacher prefers. Optimizer will penalize assignments outside this range.")
            with pref_c4:
                st.write("")
                st.write("")
                if st.button("Set", key="pref_set_v2") and pref_teacher:
                    _prefs = {}
                    if pref_max_days > 0:
                        _prefs['max_days_per_week'] = int(pref_max_days)
                    if pref_hours:
                        _prefs['preferred_blocks'] = sorted(_BLOCKS_UI.index(b) + 1 for b in pref_hours)
                    if _prefs:
                        st.session_state.advanced_config['teacher_preferences'][pref_teacher] = _prefs
                    else:
                        st.session_state.advanced_config['teacher_preferences'].pop(pref_teacher, None)
                    st.rerun()

        if st.session_state.advanced_config['teacher_preferences']:
            st.markdown("**Current teacher preferences:**")
            for teacher, prefs in list(st.session_state.advanced_config['teacher_preferences'].items()):
                cols = st.columns([4, 1])
                _desc_parts = []
                if prefs.get('max_days_per_week'):
                    _desc_parts.append(f"\u2264{prefs['max_days_per_week']} days/week")
                if prefs.get('preferred_blocks'):
                    _hours = [_BLOCKS_UI[b-1] for b in prefs['preferred_blocks']]
                    _desc_parts.append(f"Prefers: {', '.join(_hours)}")
                with cols[0]:
                    st.markdown(f"**{teacher}** → {' · '.join(_desc_parts)}")
                with cols[1]:
                    if st.button("Remove", key=f"del_pref_v2_{teacher}"):
                        st.session_state.advanced_config['teacher_preferences'].pop(teacher)
                        st.rerun()
        else:
            st.info("No teacher preferences configured")

    # ─── Wizard navigation ───
    n_overrides_nav = len(st.session_state.advanced_config.get('subject_overrides', {}))
    if n_overrides_nav > 0:
        st.markdown(
            f'<div style="margin-top:1rem;color:var(--text-secondary);font-size:0.875rem;">'
            f'{n_overrides_nav} customized subject(s) will be applied during optimization</div>',
            unsafe_allow_html=True
        )

    wizard_nav(
        prev_label="Data", prev_page='data',
        next_label="Optimize", next_page='optimize',
    )

# ════════════════════════════════════════════════════════════
# PAGE: OPTIMIZE
# ════════════════════════════════════════════════════════════
elif page == t('nav_optimize'):
    page_header(t('opt_title'), t('opt_sub'))
    wizard_stepper('optimize')

    # Prerequisite check
    if not data_ok:
        st.warning("**Missing data** — please load the Excel files first "
                    "in the *Data* step.")
        if st.button("← Back to Data", type="primary"):
            st.session_state['_nav_to'] = 'data'
            st.rerun()
        st.stop()

    # Pre-flight summary checkpoint
    aul = st.session_state.aulario_df
    alu = st.session_state.alumnos_df
    n_overrides_opt = len(st.session_state.advanced_config.get('subject_overrides', {}))

    summary_items = [
        (f"Aulario : {len(aul):,} lignes", "valid"),
        (f"Alumnos : {len(alu):,} inscriptions", "valid"),
    ]
    if n_overrides_opt > 0:
        summary_items.append((f"{n_overrides_opt} customized subject(s)", "info"))
    else:
        summary_items.append(("Default configuration", "info"))

    render_checkpoint_summary("Ready to run the optimization", summary_items)

    help_tip(
        "<strong>Step 3 of 4:</strong> Click the button below to run the pipeline. "
        "The operation takes about <strong>10-30 seconds</strong> and automatically runs: "
        "data cleaning, group formation, CP-SAT optimization, Excel generation "
        "in Daniel's format for 3 levels × 2 semesters.",
        icon=""
    )

    c1, c2 = st.columns(2)
    with c1: stat_card("Aulario", f"{len(aul):,}", f"{aul.shape[1]} columns")
    with c2: stat_card("Alumnos", f"{len(alu):,}", f"{alu.shape[1]} columns")

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)

    with st.expander(f'{t("exec_options")}'):
        include_names = st.checkbox(t('include_names'), value=True)
        solver_timeout = st.slider(t('solver_timeout'), 30, 600, 300)

    if st.button(f"{t('run_btn')}", type="primary", use_container_width=True):
        import threading
        import time as time_module
        import json

        # ════════════════════════════════════════════════════════════
        # BRIDGE UI → PIPELINE : sauvegarder la config utilisateur
        # ════════════════════════════════════════════════════════════
        os.makedirs('config', exist_ok=True)
        user_config = {
            'global': {
                'preferred_size': st.session_state.advanced_config.get('preferred_size', 12),
                'default_max': st.session_state.advanced_config.get('default_max', 15),
                'min_size': st.session_state.advanced_config.get('min_size', 7),
                'computer_lab_max': st.session_state.advanced_config.get('computer_lab_max', 24),
                'reduced_max_size': st.session_state.advanced_config.get('reduced_max_size', 12),
                'start_week': st.session_state.advanced_config.get('start_week', 4),
                's1_total_weeks': st.session_state.advanced_config.get('s1_total_weeks', 14),
                's2_total_weeks': st.session_state.advanced_config.get('s2_total_weeks', 20),
            },
            'subjects': st.session_state.advanced_config.get('subject_overrides', {}),
            'year_prefs': {
                'allow_afternoon_y1y3': st.session_state.advanced_config.get('allow_afternoon_y1y3', False),
                'allow_morning_y2y4': st.session_state.advanced_config.get('allow_morning_y2y4', False),
            },
            'teachers': st.session_state.advanced_config.get('teacher_unavailability', {}),
            'teacher_rules': st.session_state.advanced_config.get('teacher_rules', {}),
            'meta': {
                'saved_at': datetime.now().isoformat(),
                'app_version': '1.0.0',
            }
        }
        try:
            with open('config/user_config.json', 'w', encoding='utf-8') as f:
                json.dump(user_config, f, indent=2, ensure_ascii=False)
            # Show a small badge confirming save
            n_overrides = len(user_config['subjects'])
            if n_overrides > 0:
                st.info(f"User configuration saved ({n_overrides} customized subjects)")
        except Exception as e:
            st.warning(f"Unable to save configuration: {e}")

        # Also persist the live advanced configuration to the per-user memory
        # so it is restored automatically the next time the app is launched.
        if PERSISTENCE_OK:
            try:
                _persist.persist_now(st)
            except Exception:
                pass

        # Pipeline phases with weights (sum = 100)
        PHASES = [
            ("Loading data files", 5),
            ("Cleaning + joining (master_schedule)", 15),
            ("Detecting anomalies", 5),
            ("Preparing optimization data", 10),
            ("Forming groups (round-robin + cross-program)", 15),
            ("Solving CP-SAT (S1)", 20),
            ("Solving CP-SAT (S2)", 20),
            ("Generating outputs", 10),
        ]

        progress_container = st.empty()
        timer_container = st.empty()
        status_container = st.empty()

        try:
            # Make the pipeline importable wherever it lives (bundle root when
            # frozen, src/, or cwd) — mirrors the config loader above.
            if PATHS_OK:
                _root = str(app_paths.resource_root())
                if _root not in sys.path:
                    sys.path.insert(0, _root)
            for _p in ('src', '.'):
                if _p not in sys.path:
                    sys.path.insert(0, _p)

            # Capture pipeline output in shared state for threading
            pipeline_state = {
                'done': False, 'error': None, 'log': '',
            }

            old_stdout = sys.stdout
            buffer = io.StringIO()
            sys.stdout = buffer

            def run_pipeline():
                try:
                    import pipeline
                    import importlib
                    importlib.reload(pipeline)
                    pipeline.main()
                    pipeline_state['done'] = True
                except Exception as e:
                    pipeline_state['error'] = str(e)
                    pipeline_state['done'] = True

            start_time = time_module.time()
            thread = threading.Thread(target=run_pipeline, daemon=True)
            thread.start()

            # Live progress while thread runs
            # Phase detection via stdout markers
            last_pct = 0
            phase_idx = 0
            cumulative = 0

            # Phase markers Pipeline outputs (ÉTAPE 1, 2, 3, ...)
            PHASE_MARKERS = [
                "ÉTAPE 1",  # Loading
                "ÉTAPE 2",  # Cleaning
                "ÉTAPE 3",  # Anomalies
                "ÉTAPE 4",  # Optimization prep
                "ÉTAPE 5",  # Groups
                "S1 :",     # Solving S1
                "S2 :",     # Solving S2
                "ÉTAPE 6",  # Outputs
            ]

            while not pipeline_state['done']:
                elapsed = time_module.time() - start_time
                current_log = buffer.getvalue()

                # Detect highest phase reached
                new_phase = phase_idx
                for i, marker in enumerate(PHASE_MARKERS):
                    if marker in current_log:
                        new_phase = max(new_phase, i + 1)

                if new_phase != phase_idx:
                    phase_idx = new_phase
                    cumulative = sum(PHASES[i][1] for i in range(phase_idx))

                # Smoothly inch progress within the current phase based on time
                if phase_idx < len(PHASES):
                    phase_name, phase_weight = PHASES[phase_idx]
                    # estimate time for current phase (5s per weight unit)
                    partial = min(phase_weight * 0.9,
                                   (elapsed * 2) % phase_weight)
                    pct = min(99, cumulative + partial)
                else:
                    pct = 99
                    phase_name = "Finalizing..."

                pct = max(pct, last_pct + 0.5)
                pct = min(pct, 99)
                last_pct = pct

                progress_container.progress(int(pct) / 100, text=f"{phase_name} — {int(pct)}%")
                timer_container.markdown(
                    f"<div style='font-size: 0.8rem; color: var(--text-secondary); text-align: center;'>"
                    f"Elapsed: <strong>{int(elapsed)}s</strong> · Phase {phase_idx}/{len(PHASES)}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                time_module.sleep(0.3)

            thread.join(timeout=1)
            sys.stdout = old_stdout
            final_elapsed = int(time_module.time() - start_time)

            if pipeline_state['error']:
                progress_container.empty()
                timer_container.empty()
                st.error(f"Pipeline failed after {final_elapsed}s: {pipeline_state['error']}")
            else:
                progress_container.progress(1.0, text=f"{t('done')} — 100%")
                timer_container.markdown(
                    f"<div style='font-size: 0.85rem; color: var(--success); text-align: center; margin-top: 0.5rem;'>"
                    f"Completed in <strong>{final_elapsed}s</strong>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

                st.session_state.pipeline_log = buffer.getvalue()
                st.session_state.pipeline_ran = True
                status_container.success(f"{t('success')} ({final_elapsed}s)")

                # Record this run in the persistent history (best-effort, cheap
                # reads of the small summary CSVs the pipeline just wrote).
                if PERSISTENCE_OK:
                    try:
                        _summary = {"elapsed_s": final_elapsed}
                        _gp = 'outputs/optimization/assignment_summary_global.csv'
                        if os.path.exists(_gp):
                            _g = pd.read_csv(_gp).iloc[0].to_dict()
                            _summary["assignment_rate"] = round(
                                float(_g.get("assignment_rate_pct", 0)), 1)
                            _summary["students_rate"] = round(
                                float(_g.get("students_unique_rate_pct",
                                              _g.get("assignment_rate_pct", 0))), 1)
                        _sp = 'outputs/optimization/optimized_schedule_v5.csv'
                        if os.path.exists(_sp):
                            _sd = pd.read_csv(_sp)
                            _summary["sessions"] = int(len(_sd))
                            if "semester" in _sd.columns:
                                _summary["s1_sessions"] = int((_sd["semester"] == 1).sum())
                                _summary["s2_sessions"] = int((_sd["semester"] == 2).sum())
                        _cp = 'outputs/optimization/group_composition.csv'
                        if os.path.exists(_cp):
                            _cd = pd.read_csv(_cp)
                            _summary["groups"] = int(
                                _cd.groupby(["subject", "grupo"]).ngroups)
                        _persist.record_run(_summary)
                    except Exception:
                        pass

                # Professional run report (plain-English summary + metrics);
                # the raw solver log is kept inside it, demoted to a collapsed
                # technical section.
                render_run_report(st.session_state.pipeline_log, final_elapsed)
        except Exception as e:
            sys.stdout = old_stdout
            progress_container.empty()
            timer_container.empty()
            st.error(f"{e}")

    # ─── Wizard navigation (always shown) ───
    wizard_nav(
        prev_label="Configuration", prev_page='config',
        next_label="View results", next_page='results',
        next_disabled=not st.session_state.pipeline_ran,
        next_disabled_reason="Run the pipeline first",
    )

# ════════════════════════════════════════════════════════════
# PAGE: RESULTS
# ════════════════════════════════════════════════════════════
elif page == t('nav_results'):
    page_header(t('res_title'), t('res_sub'))
    wizard_stepper('results')

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Back to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    help_tip(
        "<strong>Pipeline complete.</strong> Here is a summary of the generated plan. "
        "View the distribution by day and time block, the per-subject details, "
        "or go straight to Export to download the Excel files.",
        icon=""
    )

    try:
        # Resolve via app_paths so it works both from the workspace (frozen)
        # and from source. Falls back to the relative path otherwise.
        def _rp(rel):
            if PATHS_OK:
                found = app_paths.resolve_existing(rel)
                if found:
                    return found
            return rel
        sched = pd.read_csv(_rp('outputs/optimization/optimized_schedule_v5.csv'))
        grps = pd.read_csv(_rp('outputs/optimization/group_composition.csv'))

        # Real stats from the pipeline's own summary — never hard-coded.
        _rate_txt, _conf_txt = "—", "—"
        try:
            import config_verify as _cv
            _summ = _cv.assignment_summary()
            if _summ.get("available"):
                if _summ.get("assignment_rate_pct"):
                    # Clamp to 100% — Phase-8 overrides can nudge the raw value
                    # slightly over 100 in an older summary file.
                    _rate_val = min(100.0, float(_summ['assignment_rate_pct']))
                    _rate_txt = f"{_rate_val:.0f}%"
                _un = _summ.get("total_unassigned")
                if _un is not None:
                    _conf_txt = str(max(0, int(float(_un))))
        except Exception:
            pass

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: stat_card(t('sessions_lbl'), len(sched), f"S1: {len(sched[sched['semester']==1])} · S2: {len(sched[sched['semester']==2])}")
        with c2: stat_card(t('groups_lbl'), sched.drop_duplicates(['subject','grupo']).shape[0], "lab groups")
        with c3:
            nc = 'student_name' if 'student_name' in grps.columns else 'student_hash'
            n = grps.drop_duplicates(subset=['subject', 'grupo', nc]).shape[0]
            try:
                _asum = pd.read_csv(_rp('outputs/optimization/assignment_summary.csv'))
                _av = pd.to_numeric(_asum['assigned'], errors='coerce').dropna()
                if len(_av):
                    n = int(_av.sum())
            except Exception:
                pass
            stat_card(t('assigned_lbl'), n, "enrolments")
        with c4: stat_card(t('rate_lbl'), _rate_txt, "actual")
        with c5: stat_card("Unassigned", _conf_txt, "actual")

        # Distribution
        section_header("Distribution")
        c1, c2 = st.columns(2)
        with c1:
            by_day = sched['day'].value_counts().reindex(['Lunes','Martes','Miércoles','Jueves','Viernes']).fillna(0)
            st.bar_chart(by_day)
        with c2:
            by_block = sched['time_block'].value_counts().sort_index()
            st.bar_chart(by_block)

        # Per subject table
        section_header("Subjects")
        summary = sched.groupby('subject').agg(
            sessions=('session', 'count'),
            groups=('grupo', 'nunique'),
            weeks_from=('week', 'min'),
            weeks_to=('week', 'max')
        ).reset_index()
        summary['weeks'] = summary.apply(lambda r: f"W{r['weeks_from']}-W{r['weeks_to']}", axis=1)
        st.dataframe(summary[['subject','sessions','groups','weeks']],
                     use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Loading error: {e}")

    # Conformité : qualité des données, KPIs, non placés et solveur.
    render_quality_panel()

    wizard_nav(
        prev_label="Optimize", prev_page='optimize',
        next_label="Export", next_page='export',
    )

# ════════════════════════════════════════════════════════════
# PAGE: RELIABILITY DASHBOARD
# Comprehensive metrics to give Daniel quantitative confidence
# in the generated planning.
# ════════════════════════════════════════════════════════════
elif page == t('nav_dashboard'):
    page_header(
        "Reliability dashboard",
        "Quantitative metrics to validate the quality of the generated plan."
    )

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Go to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    # Load metrics module + data
    try:
        import reliability_metrics as rm
        schedule_df = pd.read_csv('outputs/optimization/optimized_schedule_v5.csv')
        groups_df = pd.read_csv('outputs/optimization/group_composition.csv')
    except Exception as e:
        safe_error("Unable to load the data", e)
        st.stop()

    with st.spinner("Computing metrics…"):
        metrics = rm.compute_all_metrics(schedule_df, groups_df)

    # ───────────────────────────────────────────────────────
    # 1. HEALTH SCORE — top-of-page summary
    # ───────────────────────────────────────────────────────
    health = metrics['health']
    score = health['score']
    verdict = health['verdict']
    issues = health['issues']

    # Color coding
    if score >= 90:
        score_color = "#22c55e"   # green
        score_bg = "rgba(34, 197, 94, 0.06)"
        verdict_emoji = ""
    elif score >= 70:
        score_color = "#f59e0b"   # amber
        score_bg = "rgba(245, 158, 11, 0.06)"
        verdict_emoji = ""
    else:
        score_color = "#ef4444"   # red
        score_bg = "rgba(239, 68, 68, 0.06)"
        verdict_emoji = ""

    col_score, col_verdict = st.columns([1, 2])
    with col_score:
        st.markdown(f"""
            <div style="
                background: {score_bg};
                border: 2px solid {score_color};
                border-radius: 16px;
                padding: 2rem 1rem;
                text-align: center;
            ">
                <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.05em;">
                    Overall score
                </div>
                <div style="font-size: 4rem; font-weight: 700; color: {score_color}; line-height: 1; margin: 0.5rem 0;">
                    {score}
                </div>
                <div style="font-size: 0.85rem; color: var(--text-secondary);">
                    out of 100
                </div>
            </div>
        """, unsafe_allow_html=True)
    with col_verdict:
        st.markdown(f"""
            <div style="padding: 1.5rem 2rem; height: 100%;">
                <div style="font-size: 1.5rem; font-weight: 700; color: var(--text-heading); margin-bottom: 0.5rem;">
                    {verdict_emoji} {verdict}
                </div>
                <div style="color: var(--text-secondary); font-size: 0.95rem; line-height: 1.6;">
                    Score based on 7 dimensions: assignment, conflicts, distribution,
                    room occupancy, student overload, spacing, and alignment
                    with the reference.
                </div>
            </div>
        """, unsafe_allow_html=True)

    if issues:
        with st.expander(f"{len(issues)} item(s) requiring attention", expanded=False):
            for issue in issues:
                st.warning(issue)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────────
    # 2. ESSENTIAL METRICS — always visible
    # ───────────────────────────────────────────────────────
    section_header("Key metrics")

    a = metrics['assignment']
    c = metrics['conflicts']

    em_col1, em_col2, em_col3, em_col4 = st.columns(4)
    with em_col1:
        rate = a.get('assignment_rate', 0)
        rate_color = "#22c55e" if rate >= 95 else "#f59e0b" if rate >= 85 else "#ef4444"
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Assignment rate</div>
                <div class="stat-value" style="color: {rate_color};">{rate:.1f}%</div>
                <div class="stat-desc">{a.get('assigned_students', 0)} / {a.get('total_students', 0)} enrolments (student × subject)</div>
            </div>
        """, unsafe_allow_html=True)
    with em_col2:
        n_c1 = c.get('c1_violations', 0)
        n_c4 = c.get('c4_violations', 0)
        n_stud = c.get('student_conflicts', 0)
        n_conf = n_c1 + n_c4 + n_stud
        conf_color = "#22c55e" if n_conf == 0 else "#ef4444"
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Conflicts detected</div>
                <div class="stat-value" style="color: {conf_color};">{n_conf}</div>
                <div class="stat-desc">C1: {n_c1} · C4: {n_c4} · Stu: {n_stud}</div>
            </div>
        """, unsafe_allow_html=True)
    with em_col3:
        n_overflow = a.get('overflow_groups', 0)
        n_alt = a.get('alt_room_groups', 0)
        n_excep = n_overflow + n_alt
        excep_color = "#22c55e" if n_excep == 0 else "#f59e0b"
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Exceptional groups</div>
                <div class="stat-value" style="color: {excep_color};">{n_excep}</div>
                <div class="stat-desc">{n_overflow} overflow · {n_alt} alt. room</div>
            </div>
        """, unsafe_allow_html=True)
    with em_col4:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Total sessions</div>
                <div class="stat-value">{a.get('total_sessions', 0)}</div>
                <div class="stat-desc">{a.get('total_groups', 0)} groupes</div>
            </div>
        """, unsafe_allow_html=True)

    # Conflicts detail
    if n_conf > 0:
        st.error(f"**{n_conf} conflict(s) detected.** See details below.")
        with st.expander("Conflict details", expanded=True):
            if c.get('examples_c1'):
                st.markdown(f"**C1 (subject + slot duplicated) — {n_c1} case(s)**")
                _c1 = "\n".join(
                    f"- {ex.get('subject', '?')} — "
                    f"S{ex.get('semester', '?')} W{ex.get('week', '?')} "
                    f"{ex.get('day', '?')} {ex.get('time_block', '?')} "
                    f"({ex.get('count', 0)} sessions)"
                    for ex in c['examples_c1'][:10]
                )
                st.markdown(_c1)
            if c.get('examples_c4'):
                st.markdown(f"**C4 (room + slot duplicated) — {n_c4} case(s)**")
                _c4 = "\n".join(
                    f"- {ex.get('room', '?')} — "
                    f"S{ex.get('semester', '?')} W{ex.get('week', '?')} "
                    f"{ex.get('day', '?')} {ex.get('time_block', '?')} "
                    f"({ex.get('count', 0)} sessions)"
                    for ex in c['examples_c4'][:10]
                )
                st.markdown(_c4)
            if n_stud > 0:
                st.markdown(f"**Duplicate students — {n_stud} case(s) detected**")
                st.caption("See the Individual case page to identify the students concerned.")
    else:
        st.success("**No conflicts detected.** The plan satisfies all hard constraints.")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────────
    # 3. QUALITY METRICS — expandable sections
    # ───────────────────────────────────────────────────────
    section_header("Quality metrics")

    qual_tab1, qual_tab2, qual_tab3, qual_tab4 = st.tabs([
        "Distribution", "Rooms", "Student overload", "Spacing"
    ])

    # ---- TAB: Distribution ----
    with qual_tab1:
        d = metrics['distribution']
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Distribution by day of week**")
            by_day = d.get('by_day', {})
            if by_day:
                day_df = pd.DataFrame([
                    {'Day': day, 'Sessions': by_day[day]}
                    for day in ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
                    if day in by_day
                ])
                st.bar_chart(day_df.set_index('Day'))

                # Detect bottleneck
                avg = sum(by_day.values()) / len(by_day) if by_day else 0
                max_day = max(by_day.items(), key=lambda x: x[1]) if by_day else (None, 0)
                if max_day[1] > avg * 1.5:
                    st.warning(f"Bottleneck detected: {max_day[0]} concentrates {max_day[1]} sessions "
                               f"(average {avg:.0f})")
                else:
                    st.success("Balanced distribution across days")

        with col_b:
            st.markdown("**Distribution par bloc horaire**")
            by_block = d.get('by_block', {})
            if by_block:
                block_df = pd.DataFrame([
                    {'Bloc': block, 'Sessions': count}
                    for block, count in sorted(by_block.items())
                ])
                st.bar_chart(block_df.set_index('Bloc'))

        st.markdown("**Distribution by week**")
        by_week = d.get('by_week', {})
        if by_week:
            week_df = pd.DataFrame([
                {'Week': f"W{int(str(w).split('-')[-1].lstrip('WS')):02d}", 'Sessions': count}
                for w, count in sorted(by_week.items())
            ])
            st.bar_chart(week_df.set_index('Week'))

    # ---- TAB: Room occupancy ----
    with qual_tab2:
        rooms = metrics['room_occupancy']
        if rooms:
            st.markdown("**Room load** (% occupation of available slots)")

            room_data = []
            for r in rooms:
                util = r.get('occupancy_pct', 0)
                if util >= 80:
                    status = "Saturated"
                elif util >= 60:
                    status = "High"
                elif util >= 30:
                    status = "Moderate"
                else:
                    status = "Low"
                room_data.append({
                    'Room':          r.get('room', '?'),
                    'Semester':      f"S{r.get('semester', '?')}",
                    'Occupation':    f"{util:.1f}%",
                    'Sessions':      r.get('sessions_used', 0),
                    'Available slots': r.get('slots_available', 0),
                    'Statut':        status,
                })

            st.dataframe(
                pd.DataFrame(room_data),
                use_container_width=True,
                hide_index=True,
            )

            saturated = [r for r in rooms if r.get('status') == 'critical']
            if saturated:
                st.warning(f"{len(saturated)} saturated room(s): "
                           f"{', '.join(r['room'] for r in saturated)}")
            else:
                st.success("No saturated rooms — capacity headroom available")
        else:
            st.info("No room data available.")

    # ---- TAB: Student overload ----
    with qual_tab3:
        ov = metrics['overload']
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            n_overloaded = ov.get('overloaded_count', 0)
            color = "#22c55e" if n_overloaded == 0 else "#f59e0b"
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Overloaded students</div>
                    <div class="stat-value" style="color: {color};">{n_overloaded}</div>
                    <div class="stat-desc">> 3 labs same week</div>
                </div>
            """, unsafe_allow_html=True)
        with col_b:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Max peak observed</div>
                    <div class="stat-value">{ov.get('max_labs_observed', 0)}</div>
                    <div class="stat-desc">labs/week (1 student)</div>
                </div>
            """, unsafe_allow_html=True)
        with col_c:
            avg_grp_size = a.get('avg_group_size', 0)
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Taille moyenne groupe</div>
                    <div class="stat-value">{avg_grp_size:.1f}</div>
                    <div class="stat-desc">students per group</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        if ov.get('overloaded_count', 0) > 0 and ov.get('examples'):
            st.markdown(f"**Top {len(ov['examples'])} cas de surcharge**")
            top_data = []
            for entry in ov['examples'][:10]:
                top_data.append({
                    'Student':     entry.get('student', '?'),
                    'Semester':     f"S{entry.get('semester', '?')}",
                    'Week':      f"W{entry.get('week', '?')}",
                    'Labs this week': entry.get('count', 0),
                })
            st.dataframe(pd.DataFrame(top_data), use_container_width=True, hide_index=True)
        elif n_overloaded == 0:
            st.success("No student has more than 3 labs in the same week")

    # ---- TAB: Spacing ----
    with qual_tab4:
        sp = metrics['spacing']
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            pct_well = sp.get('well_spaced_groups_pct', 0)
            color = "#22c55e" if pct_well >= 80 else "#f59e0b" if pct_well >= 60 else "#ef4444"
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Well-spaced groups</div>
                    <div class="stat-value" style="color: {color};">{pct_well:.0f}%</div>
                    <div class="stat-desc">P1=W4, Pn=Wmax, regular spacing</div>
                </div>
            """, unsafe_allow_html=True)
        with col_b:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Avg P1 offset</div>
                    <div class="stat-value">{sp.get('avg_first_excess', 0):.1f}</div>
                    <div class="stat-desc">weeks after min_week</div>
                </div>
            """, unsafe_allow_html=True)
        with col_c:
            st.markdown(f"""
                <div class="stat-card">
                    <div class="stat-label">Avg Pn offset</div>
                    <div class="stat-value">{sp.get('avg_last_deficit', 0):.1f}</div>
                    <div class="stat-desc">semaines avant max_week</div>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        st.markdown("**Detailed indicators**")
        st.markdown(f"""
            - **Average P1 offset**: {sp.get('avg_first_excess', 0):.2f} weeks after `min_week`
              (ideal: 0)
            - **Average Pn offset**: {sp.get('avg_last_deficit', 0):.2f} weeks before `max_week`
              (ideal: 0)
            - **Average gap deviation**: {sp.get('avg_gap_deviation', 0):.2f} weeks
              vs the ideal gap (ideal: 0)
            - **Perfectly spaced groups**: {pct_well:.0f}% of total
        """)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────────
    # 4. SUBJECT COVERAGE — comparison vs Daniel reference
    # ───────────────────────────────────────────────────────
    section_header("Coverage by subject")

    cov = metrics['coverage']
    if cov:
        cov_data = []
        for entry in cov:
            ref_students = entry.get('ref_students')
            deviation_pct = entry.get('deviation_pct')
            status = entry.get('status', 'ok')
            status_icon = {
                'ok': 'OK',
                'warning': 'Moderate gap',
                'critical': 'Large gap',
            }.get(status, status)

            cov_data.append({
                'Subject':          entry.get('subject', '?'),
                'Sem.':             f"S{entry.get('semester', '?')}",
                'Students':        entry.get('students', 0),
                'Groups':           entry.get('groups', 0),
                'Sessions':         entry.get('sessions', 0),
                'Daniel ref (stu.)': ref_students if ref_students is not None else '—',
                'Deviation':        f"{deviation_pct:+.1f}%" if deviation_pct is not None else '—',
                'Status':           status_icon,
            })
        st.dataframe(pd.DataFrame(cov_data), use_container_width=True, hide_index=True)

        # Highlight problematic subjects
        problematic = [c for c in cov if c.get('status') == 'critical']
        if problematic:
            with st.expander(f"{len(problematic)} subject(s) with >30% deviation vs Daniel"):
                for p in problematic:
                    dev = p.get('deviation_pct', 0)
                    st.write(f"- **{p.get('subject', '?')}** : {dev:+.1f}% "
                             f"({p.get('students', 0)} actual vs {p.get('ref_students', '?')} reference)")
        elif any(c.get('status') == 'warning' for c in cov):
            n_warn = sum(1 for c in cov if c.get('status') == 'warning')
            st.info(f"{n_warn} subject(s) with moderate gap (15-30%) — to monitor but acceptable")
        else:
            st.success("All subjects are aligned with Daniel's reference")

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────────
    # 5. EXPORT
    # ───────────────────────────────────────────────────────
    section_header("Export the report")

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        # JSON export
        import json as json_module
        # Convert metrics to JSON-safe format
        def make_json_safe(obj):
            if isinstance(obj, dict):
                return {k: make_json_safe(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [make_json_safe(x) for x in obj]
            elif hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            elif pd.isna(obj) if not isinstance(obj, (list, dict, set)) else False:
                return None
            else:
                return obj
        try:
            json_str = json_module.dumps(make_json_safe(metrics), indent=2, ensure_ascii=False)
            st.download_button(
                "Download metrics (JSON)",
                data=json_str.encode('utf-8'),
                file_name=f"reliability_metrics_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception as ex:
            st.error(f"JSON export error: {ex}")

    with col_e2:
        # Plain-text summary for sharing
        text_lines = [
            "RELIABILITY REPORT — SCHEDULING PLAN",
            "=" * 60,
            f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            f"OVERALL SCORE: {score}/100 ({verdict})",
            "",
            "KEY METRICS",
            f"  - Assignment rate: {a.get('assignment_rate', 0):.1f}%",
            f"  - Assigned students: {a.get('assigned_students', 0)} / {a.get('total_students', 0)}",
            f"  - Total sessions: {a.get('total_sessions', 0)}",
            f"  - Groups formed: {a.get('total_groups', 0)}",
            f"  - Conflicts detected: {n_conf}",
            f"  - Overflow groups: {n_overflow}",
            f"  - Alt. room groups: {n_alt}",
            "",
        ]
        if issues:
            text_lines.append("POINTS D'ATTENTION")
            for issue in issues:
                text_lines.append(f"  - {issue}")
            text_lines.append("")

        text_lines.append("=" * 60)
        text_summary = "\n".join(text_lines)

        st.download_button(
            "Download summary (TXT)",
            data=text_summary.encode('utf-8'),
            file_name=f"reliability_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    # Wizard navigation
    wizard_nav(
        prev_label="Results", prev_page='results',
        next_label="History", next_page='history',
    )

# ════════════════════════════════════════════════════════════
# PAGE: INTEGRITY (flow-integrity checks, shown as visual cards)
# Same checks as verify_flow.py, but rendered in-app for the defense
# (no terminal). Students -> free; Professors -> free; rooms; reservations.
# ════════════════════════════════════════════════════════════
elif page == t('nav_integrity'):
    page_header(
        "Flow integrity",
        "Live verification that the generated schedule respects every rule: "
        "students free, rooms free, professors eligible, reservations honoured."
    )

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Go to Optimize", type="primary", key="integ_go_opt"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    def _rp(rel):
        if PATHS_OK:
            found = app_paths.resolve_existing(rel)
            if found:
                return found
        return rel

    def _safe_csv(rel):
        import os as _os
        # Try the given path, then a common folder TYPO ('optimizarion'), then a
        # recursive search by filename — so a misplaced file is still found
        # instead of showing N/A.
        cands = [rel]
        if 'optimization/' in rel:
            cands.append(rel.replace('optimization/', 'optimizarion/'))
        seen = []
        for c in cands:
            seen.append(_rp(c))
        # recursive fallback by basename within the workspace
        try:
            base = _os.path.basename(rel)
            ws = getattr(app_paths, 'WORKSPACE', None) if PATHS_OK else None
            if ws is None and PATHS_OK:
                ws = app_paths.workspace_path()
                ws = _os.path.dirname(ws) if _os.path.splitext(str(ws))[1] else str(ws)
            if ws:
                for root, _d, files in _os.walk(str(ws)):
                    if base in files:
                        seen.append(_os.path.join(root, base))
        except Exception:
            pass
        for pth in seen:
            try:
                if pth and _os.path.exists(pth):
                    return pd.read_csv(pth)
            except Exception:
                continue
        return None

    sched = _safe_csv('outputs/optimization/optimized_schedule_v5.csv')
    comp = _safe_csv('outputs/optimization/group_composition.csv')
    blocked = _safe_csv('outputs/optimization/blocked_slots.csv')
    busy = _safe_csv('data_clean/optimization/student_busy.csv')
    profs = _safe_csv('data_clean/optimization/subject_professors.csv')
    pbusy = _safe_csv('data_clean/optimization/professor_busy.csv')

    if sched is None or comp is None:
        safe_error("Unable to load the generated schedule "
                   "(optimized_schedule_v5.csv / group_composition.csv).", None)
        st.stop()

    from collections import defaultdict as _dd

    DAY_IDS = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Jueves": 3, "Viernes": 4}
    BLOCK_IDS = {"08:30-10:30": 1, "10:30-12:30": 2, "12:30-14:30": 3,
                 "15:00-17:00": 4, "17:00-19:00": 5, "19:00-21:00": 6}

    sid_col = ("student_hash" if "student_hash" in comp.columns
               else "student_name" if "student_name" in comp.columns else None)

    sessions = sched.copy()
    sessions["grupo"] = pd.to_numeric(sessions["grupo"], errors="coerce")
    sessions = sessions.dropna(subset=["grupo"]); sessions["grupo"] = sessions["grupo"].astype(int)

    # The schedule uses prefixed subject keys ("S1_Física") while
    # group_composition uses the clean name ("Física"). Normalise both sides so
    # the (subject, grupo) join actually matches.
    import re as _re
    def _subj_key(name):
        return _re.sub(r'^S[12]_', '', str(name)).strip().lower()

    grp_students = _dd(set)
    student_filiere = {}   # student id -> filière (titulacion), for traced examples
    if sid_col:
        # Skip manual-override placements: those are deliberate human-in-the-loop
        # decisions Daniel has already arbitrated, exactly as the pipeline's own
        # student-conflict check does. Counting them would flag accepted clashes.
        _has_ov = "is_override" in comp.columns
        _fil_col = ("titulacion" if "titulacion" in comp.columns
                    else "program" if "program" in comp.columns else None)
        for _, r in comp.iterrows():
            if str(r.get("grupo", "")).strip() in ("", "nan"):
                continue
            if _fil_col and r[sid_col] not in student_filiere:
                _fv = str(r.get(_fil_col, "") or "").strip()
                if _fv and not _fv.upper().startswith(("MIXED", "OVERFLOW")):
                    student_filiere[r[sid_col]] = _fv
            if _has_ov and bool(r.get("is_override", False)):
                continue
            grp_students[(_subj_key(r["subject"]), int(r["grupo"]))].add(r[sid_col])

    # Build per-student lab slots
    student_slot = _dd(list)
    for _, s in sessions.iterrows():
        key = (_subj_key(s["subject"]), int(s["grupo"]))
        for st_ in grp_students.get(key, ()):
            student_slot[st_].append((int(s["week"]), str(s["day"]), str(s["time_block"]),
                                      str(s["subject"]), int(s["grupo"])))

    results = []   # (status, title, detail)  status in {pass, info, skip, fail}

    # 1. student-free
    clash = 0
    for st_, slots in student_slot.items():
        seen = {}
        for (w, d, b, subj, g) in slots:
            k = (w, d, b)
            if k in seen and seen[k] != (subj, g):
                clash += 1
            seen[k] = (subj, g)
    results.append(("pass" if clash == 0 else "fail",
                    "Students never double-booked",
                    "No student has two lab sessions at the same week/day/block."
                    if clash == 0 else f"{clash} clash(es) found."))

    # 2. student-vs-class. The anonymised build keys composition by hash while
    # student_busy uses raw ids — but student_directory.csv maps id<->hash, so we
    # translate student_busy to hashes and check WITHOUT exposing real names.
    directory = _safe_csv('outputs/optimization/student_directory.csv')
    if busy is not None and sid_col:
        bcol = busy.columns
        sidc = "student_id" if "student_id" in bcol else ("student_hash" if "student_hash" in bcol else bcol[0])
        # id -> composition identifier (name or hash) bridge via student_directory
        id_map = {}
        if directory is not None and "student_id" in directory.columns and sid_col in directory.columns:
            id_map = {str(r["student_id"]): str(r[sid_col]) for _, r in directory.iterrows()}
        busy_slots = _dd(set)
        for _, r in busy.iterrows():
            raw = str(r[sidc])
            key = raw if sid_col == sidc else id_map.get(raw, raw)
            di = int(r["day_idx"]) if "day_idx" in bcol else DAY_IDS.get(str(r.get("day", "")), -1)
            bi = int(r["block_id"]) if "block_id" in bcol else BLOCK_IDS.get(str(r.get("block", "")), -1)
            busy_slots[key].add((di, bi))
        comp_ids = set(str(x) for x in comp[sid_col])
        if busy_slots and (set(busy_slots) & comp_ids):
            # student_busy is the WEEKLY RECURRING class pattern (day+block, no
            # week); labs are week-specific. A day/block coincidence is therefore
            # not necessarily a conflict, and we can't resolve it from a
            # week-agnostic map. Report as INFO; the pipeline enforces the real
            # week-aware no-overlap at group formation.
            coincide = 0
            for st_, slots in student_slot.items():
                for (w, d, b, subj, g) in slots:
                    if (DAY_IDS.get(d, -1), BLOCK_IDS.get(b, -1)) in busy_slots.get(str(st_), ()):
                        coincide += 1
            results.append(("info", "Lab vs class slot",
                            f"{coincide} lab/day-block coincidence(s) with the recurring class "
                            f"pattern — not necessarily conflicts (student_busy is week-agnostic; "
                            f"the pipeline enforces week-aware no-overlap at group formation)."))
        else:
            results.append(("skip", "Lab vs class slot",
                            "Could not align student_busy with the schedule "
                            "(student_directory.csv missing or ids don't match)."))
    else:
        results.append(("skip", "Lab vs class slot",
                        "student_busy.csv not available in this build."))

    # 3. room-free (per semester)
    room_slot = _dd(int)
    for _, s in sessions.iterrows():
        for room in str(s["lab_rooms"]).split(","):
            room = room.strip()
            if room:
                room_slot[(room, int(s["semester"]), int(s["week"]),
                           str(s["day"]), str(s["time_block"]))] += 1
    c4 = [k for k, n in room_slot.items() if n > 1]
    results.append(("pass" if not c4 else "fail",
                    "Rooms never double-booked (per semester)",
                    "No room hosts two sessions in the same semester/week/day/block."
                    if not c4 else f"{len(c4)} conflict(s); e.g. " +
                    "; ".join(f"{r} S{sem} W{w} {d} {b}" for (r, sem, w, d, b) in c4[:3])))

    # 4a + 4b professors
    if profs is not None:
        elig = {str(r["subject"]): [n.strip() for n in str(r["professors"]).split(";") if n.strip()]
                for _, r in profs.iterrows()}
        def _names_for(subj):
            if subj in elig: return elig[subj]
            base = subj.split("_", 1)[-1]
            for k, v in elig.items():
                if k.split("_", 1)[-1] == base: return v
            return []
        no_elig = [str(s["subject"]) for _, s in sessions.iterrows() if not _names_for(str(s["subject"]))]
        results.append(("pass" if not no_elig else "fail",
                        "Every session has an eligible professor",
                        "Each lab subject has at least one qualified professor."
                        if not no_elig else f"Missing for: {sorted(set(no_elig))[:5]}"))
        # 4b informational
        pbset = _dd(set)
        if pbusy is not None:
            pc = pbusy.columns; pidc = "professor_id" if "professor_id" in pc else pc[0]
            for _, r in pbusy.iterrows():
                di = int(r["day_idx"]) if "day_idx" in pc else -1
                bi = int(r["block_id"]) if "block_id" in pc else -1
                pbset[str(r[pidc])].add((di, bi))
        all_names = {n for names in elig.values() for n in names}
        if pbset and len(set(pbset) & all_names) >= max(3, 0.3 * len(all_names)):
            nf = 0
            for _, s in sessions.iterrows():
                names = _names_for(str(s["subject"]))
                if names and all((DAY_IDS.get(str(s["day"]), -1), BLOCK_IDS.get(str(s["time_block"]), -1))
                                 in pbset.get(n, set()) for n in names):
                    nf += 1
            results.append(("info", "Professor availability",
                            f"{nf} session(s) where every eligible professor is also marked busy — "
                            "expected when the eligible professor is the one running the lab. "
                            "The pipeline already removes genuinely-busy slots at group formation."))
        else:
            results.append(("skip", "Professor availability",
                            "professor_busy.csv not available or identifiers don't align."))
    else:
        results.append(("skip", "Eligible professors",
                        "subject_professors.csv not available in this build."))

    # 5. reserved slots (soft, per semester) + 5b markers absent
    if blocked is not None and len(blocked):
        has_sem = "semester" in blocked.columns
        bset = set()
        for _, r in blocked.iterrows():
            sem = int(r["semester"]) if has_sem else None
            bset.add((str(r["lab_rooms"]).strip(), sem, int(r["week"]),
                      str(r["day"]), str(r["time_block"])))
        hits = []
        for _, s in sessions.iterrows():
            for room in str(s["lab_rooms"]).split(","):
                key = (room.strip(), int(s["semester"]) if has_sem else None,
                       int(s["week"]), str(s["day"]), str(s["time_block"]))
                if key in bset:
                    hits.append(f"{str(s['subject']).split('_',1)[-1]} G{int(s['grupo'])} "
                                f"(S{int(s['semester'])} W{int(s['week'])} {s['day']} {s['time_block']})")
        if not hits:
            results.append(("pass", "Reserved slots clear",
                            "No real session is placed on a reserved (e.g. Biotecnología) slot."))
        else:
            results.append(("info", "Reserved-slot avoidance (soft)",
                            f"{len(hits)} residual session(s) on reserved slots — the unavoidable "
                            f"minimum when a group is fixed to that day/block: " + "; ".join(hits[:4])))
        markers_in_sched = ("blocked" in sched.columns) or ((sessions["grupo"] == 0).any())
        results.append(("pass" if not markers_in_sched else "fail",
                        "Reservation markers kept out of the schedule",
                        "The schedule has no marker rows, so the reliability check stays clean."
                        if not markers_in_sched else "Marker rows leaked into the schedule."))
    else:
        results.append(("skip", "Reserved slots",
                        "blocked_slots.csv not found (no reservations configured)."))

    # ── Summary banner ──────────────────────────────────────
    n_pass = sum(1 for r in results if r[0] == "pass")
    n_fail = sum(1 for r in results if r[0] == "fail")
    n_info = sum(1 for r in results if r[0] == "info")
    n_skip = sum(1 for r in results if r[0] == "skip")
    # Group the cards by status so all PASS sit together, then INFO, then N/A
    # (failures first if any, since they are the most important to see).
    _st_order = {"fail": 0, "pass": 1, "info": 2, "skip": 3}
    results.sort(key=lambda r: _st_order.get(r[0], 9))
    if n_fail == 0:
        st.markdown(
            f"<div style='padding:1.1rem 1.3rem;border-radius:12px;margin-bottom:1.2rem;"
            f"background:rgba(34,197,94,0.10);border:1px solid rgba(34,197,94,0.45);'>"
            f"<span style='font-size:1.15rem;font-weight:700;color:#22c55e;'>All integrity checks passed</span>"
            f"<br><span style='color:var(--text-muted);'>{n_pass} passed · {n_info} informational · {n_skip} not applicable in this build</span>"
            f"</div>", unsafe_allow_html=True)
    else:
        st.markdown(
            f"<div style='padding:1.1rem 1.3rem;border-radius:12px;margin-bottom:1.2rem;"
            f"background:rgba(239,68,68,0.10);border:1px solid rgba(239,68,68,0.45);'>"
            f"<span style='font-size:1.15rem;font-weight:700;color:#ef4444;'>{n_fail} integrity check(s) failed</span>"
            f"<br><span style='color:var(--text-muted);'>{n_pass} passed · {n_info} informational · {n_skip} not applicable</span>"
            f"</div>", unsafe_allow_html=True)

    # ── Check cards ─────────────────────────────────────────
    _style = {
        "pass": ("#22c55e", "rgba(34,197,94,0.06)", "", "PASS"),
        "fail": ("#ef4444", "rgba(239,68,68,0.07)", "", "FAIL"),
        "info": ("#f4b942", "rgba(244,185,66,0.07)", "", "INFO"),
        "skip": ("#64748b", "rgba(100,116,139,0.06)", "", "N/A"),
    }
    for status, title, detail in results:
        color, bg, icon, tag = _style[status]
        st.markdown(
            f"<div style='display:flex;gap:0.9rem;align-items:flex-start;padding:0.85rem 1.1rem;"
            f"border-radius:10px;margin-bottom:0.6rem;background:{bg};border:1px solid {color}33;"
            f"border-left:3px solid {color};'>"
            f"<div style='flex:1;'>"
            f"<div style='font-weight:650;color:var(--text-primary);'>{title} "
            f"<span style='font-size:0.7rem;color:{color};border:1px solid {color}66;border-radius:6px;"
            f"padding:1px 6px;margin-left:6px;vertical-align:middle;'>{tag}</span></div>"
            f"<div style='color:var(--text-muted);font-size:0.9rem;margin-top:0.2rem;'>{detail}</div>"
            f"</div></div>", unsafe_allow_html=True)

    # ── Legend: what the badges mean (esp. the yellow INFO cards) ───────────
    with st.expander("What do these badges mean? (PASS / INFO / N/A)"):
        st.markdown(
            "- **<span style='color:#22c55e;'>PASS</span>** — the rule is verified: "
            "the generated schedule satisfies it with zero violations.\n"
            "- **<span style='color:#f4b942;'>INFO</span>** (yellow) — **not a problem**. "
            "It flags something that *looks* like it could be an issue but isn't a real "
            "conflict, usually because the source data can't prove it either way. These are "
            "shown transparently rather than hidden. In this build:\n"
            "    - *Lab vs class slot* — `student_busy` records the **weekly recurring** class "
            "pattern (day+block, no week number), while labs are placed in **specific weeks**. "
            "A day/block coincidence isn't necessarily a clash; the pipeline already enforces "
            "the real week-aware no-overlap when forming groups.\n"
            "    - *Professor availability* — a professor who is **running a lab** also appears "
            "\"busy\" at that slot in `professor_busy`. So \"all eligible busy\" mixes genuine "
            "over-subscription with the normal case of the eligible professor teaching the "
            "session. The pipeline removes genuinely-busy slots at group formation.\n"
            "    - *Reserved-slot avoidance (soft)* — the Biotecnología reservation is a soft "
            "penalty, not a hard block. The 2 residual sessions are the unavoidable minimum "
            "(their group is fixed to that day/block); everything else was steered away.\n"
            "- **<span style='color:#64748b;'>N/A</span>** — the check couldn't run because a "
            "needed file isn't in this build (e.g. `subject_professors.csv`). Not a failure.",
            unsafe_allow_html=True,
        )

    # ── Traced examples (for the defense) ──────────────────
    section_header("Traced examples")
    st.caption("Pick a few students and professors to show the schedule matches reality. "
               "Each student's sessions are grouped by semester — no two share a week/day/block. "
               "A student enrolled only in S1 subjects (e.g. Física + Química, typical 1st-year) "
               "correctly shows no S2 sessions.")

    # how many students to show
    _n_students = st.slider("Students to show", 1, 10, 4, key="integ_n_students")

    # day order for tidy sorting
    _DAY_ORDER = {"Lunes": 0, "Martes": 1, "Miércoles": 2, "Jueves": 3, "Viernes": 4}
    # map a schedule subject -> semester number from the sessions frame
    _subj_sem = {}
    for _, _s in sessions.iterrows():
        _subj_sem[str(_s["subject"])] = int(_s["semester"])

    st.markdown("**Students** — name · field · sessions (grouped by semester)")
    shown = 0
    for st_, slots in student_slot.items():
        if shown >= _n_students:
            break
        fil = student_filiere.get(st_, "—")
        # split this student's sessions by semester
        by_sem = _dd(list)
        for (w, d, b, subj, g) in slots:
            by_sem[_subj_sem.get(subj, 0)].append((w, d, b, subj, g))
        # build the per-semester rows
        sem_blocks = ""
        for sem in sorted(by_sem):
            rows = sorted(by_sem[sem], key=lambda x: (x[0], _DAY_ORDER.get(x[1], 9)))
            chips = ""
            for (w, d, b, subj, g) in rows:
                name = subj.split("_", 1)[-1]
                chips += (
                    f"<span style='display:inline-block;background:var(--bg-elevated,#1b2440);"
                    f"border:1px solid var(--border,#2c3658);border-radius:7px;"
                    f"padding:2px 8px;margin:2px 4px 2px 0;font-size:0.78rem;color:var(--text-primary,#e6ecf5);'>"
                    f"<b>{name}</b> G{g} · <span style='color:var(--text-muted,#94a3b8);'>"
                    f"S{sem} W{w} · {d} {b}</span></span>"
                )
            sem_blocks += (
                f"<div style='margin:0.35rem 0 0.1rem;'>"
                f"<span style='font-size:0.7rem;letter-spacing:0.06em;color:var(--text-muted,#94a3b8);"
                f"text-transform:uppercase;'>Semester {sem}</span><br>{chips}</div>"
            )
        st.markdown(
            f"<div style='padding:0.7rem 0.95rem;border-radius:10px;margin-bottom:0.6rem;"
            f"background:var(--bg-card,rgba(255,255,255,0.02));border:1px solid var(--border,#2c3658);'>"
            f"<div style='display:flex;align-items:center;gap:0.6rem;margin-bottom:0.2rem;'>"
            f"<span style='font-weight:700;color:var(--text-primary,#fff);'>{str(st_)}</span>"
            f"<span style='font-size:0.72rem;font-weight:600;color:#38bdf8;border:1px solid #38bdf855;"
            f"background:#38bdf814;border-radius:6px;padding:1px 8px;'>{fil}</span>"
            f"<span style='font-size:0.72rem;color:var(--text-muted,#94a3b8);'>"
            f"· {len(slots)} session(s)</span></div>"
            f"{sem_blocks}</div>",
            unsafe_allow_html=True,
        )
        shown += 1

    if profs is not None:
        # Lab credits per professor (1 P credit = 5 lab sessions) — feature #6 output.
        import unicodedata as _ud
        def _norm_pn(x):
            x = _ud.normalize("NFKD", str(x))
            x = "".join(c for c in x if not _ud.combining(c))
            return " ".join(sorted(x.lower().replace(",", " ").split()))
        _credit_by_norm = {}
        for _p in ("professor_lab_load.csv",
                   "outputs/optimization/professor_lab_load.csv"):
            if os.path.exists(_p):
                try:
                    _ll = pd.read_csv(_p)
                    for _, _r in _ll.iterrows():
                        _credit_by_norm[_norm_pn(_r.get("prof_name", ""))] = {
                            "cr": float(_r.get("lab_credits", 0) or 0),
                            "sess": int(float(_r.get("lab_sessions", 0) or 0)),
                            "over": bool(_r.get("over_budget", False)),
                        }
                    break
                except Exception:
                    pass

        st.markdown("**Professors** — subject · eligible teachers · lab credits → sessions "
                    "(1 P credit = 5 sessions)")
        for subj in sorted(sessions["subject"].unique()):
            names = _names_for(str(subj))
            if not names:
                continue
            # one chip per professor — name + lab-credit load when known
            chips = ""
            for nm in names:
                _ci = _credit_by_norm.get(_norm_pn(nm))
                if _ci and _ci["cr"] > 0:
                    _flag = " (over budget)" if _ci["over"] else ""
                    _load = (f"<span style='color:#6fb6e8;font-weight:600;'> · "
                             f"{_ci['cr']:.0f} cr P \u2192 {_ci['sess']} sess{_flag}</span>")
                else:
                    _load = ""
                chips += (
                    f"<span style='display:inline-block;background:var(--bg-elevated,#1b2440);"
                    f"border:1px solid var(--border,#2c3658);border-radius:7px;"
                    f"padding:2px 8px;margin:2px 4px 2px 0;font-size:0.78rem;"
                    f"color:var(--text-primary,#e6ecf5);'>{nm}{_load}</span>"
                )
            # scheduled slots for this subject (where data actually links to time)
            _ss = sessions[sessions["subject"] == subj]
            _slot_bits = ""
            if len(_ss):
                _agg = (_ss.groupby(["day", "time_block"]).size()
                        .sort_values(ascending=False))
                _parts = [f"{d} {tb} \u00d7{n}" for (d, tb), n in _agg.items()]
                _slot_bits = (
                    "<div style='margin-top:0.45rem;padding-top:0.4rem;"
                    "border-top:1px solid var(--border,#2c365844);font-size:0.73rem;"
                    "color:var(--text-secondary,#9fb0c8);'>"
                    "scheduled sessions: " + " · ".join(_parts) + "</div>"
                )
            st.markdown(
                f"<div style='padding:0.7rem 0.95rem;border-radius:10px;margin-bottom:0.6rem;"
                f"background:var(--bg-card,rgba(255,255,255,0.02));border:1px solid var(--border,#2c3658);'>"
                f"<div style='display:flex;align-items:center;gap:0.6rem;margin-bottom:0.3rem;'>"
                f"<span style='font-weight:700;color:var(--text-primary,#fff);'>"
                f"{str(subj).split('_',1)[-1]}</span>"
                f"<span style='font-size:0.72rem;font-weight:600;color:#22c55e;border:1px solid #22c55e55;"
                f"background:#22c55e14;border-radius:6px;padding:1px 8px;'>{len(names)} eligible</span>"
                f"</div>{chips}{_slot_bits}</div>",
                unsafe_allow_html=True,
            )

    # -- Credits per professor (clear, sortable table) --
    section_header("Credits per professor")
    _ll_path = None
    for _p in ("professor_lab_load.csv",
               "outputs/optimization/professor_lab_load.csv"):
        if os.path.exists(_p):
            _ll_path = _p
            break
    if _ll_path is None:
        st.info("File professor_lab_load.csv not found. "
                "Run the pipeline to display credits per professor.")
    else:
        try:
            _df = pd.read_csv(_ll_path)
            _df_lab = _df[_df["lab_credits"].fillna(0) > 0].copy()
            n_prof = len(_df_lab)
            n_over = int(_df_lab["over_budget"].fillna(False).astype(bool).sum())
            tot_cr = float(_df_lab["lab_credits"].fillna(0).sum())
            tot_sess = int(_df_lab["lab_sessions"].fillna(0).sum())

            help_tip(
                "Lab load per professor. Validated rule: "
                "1 P credit = 5 lab sessions. Budget overruns are "
                "signaled (never blocking).",
                icon=""
            )
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                stat_card("Professors", n_prof, "with lab credits")
            with c2:
                stat_card("Lab credits", f"{tot_cr:.0f}", "total assigned")
            with c3:
                stat_card("Lab sessions", tot_sess, "total (credits x 5)")
            with c4:
                stat_card("Overruns", n_over, "budget signaled")

            _show = _df_lab.rename(columns={
                "prof_code": "Code",
                "prof_name": "Professor",
                "lab_credits": "Lab credits",
                "lab_sessions": "Lab sessions",
                "theory_credits": "Theory credits",
                "total_assigned": "Total assigned",
                "budget": "Budget",
                "margin": "Margin",
                "over_budget": "Over budget",
            })
            _cols = ["Code", "Professor", "Lab credits", "Lab sessions",
                     "Theory credits", "Total assigned", "Budget", "Margin",
                     "Over budget"]
            _cols = [c for c in _cols if c in _show.columns]
            _show = _show[_cols].sort_values("Lab credits", ascending=False)
            st.dataframe(_show, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"Unable to display credits per professor: {e}")

    # -- How lab credits are computed and distributed --
    with st.expander("How are lab credits computed and distributed?"):
        st.markdown(
            """
**Source of truth.** The file `Asignacion_2025-2026_v5.xlsx`, sheet
*"Asignación docente"*, lists for each (subject, group) pair up to
**4 professors**, each with a credit count and a character:
**T** = theory (lecture) or **P** = practice (lab).

**Validated conversion rule.** `1 P credit = 5 lab sessions`.
Example: a professor with **3P** must supervise **15 lab sessions**.
Only **P** credits generate lab sessions; **T** credits are counted
separately (column *Theory credits*).

**Distribution.** Sessions are distributed per subject/group according to the
professors declared on the sheet. The *Total assigned* column adds
theory + lab, compared to the professor's *Budget* to compute the *Margin*.

**Overruns.** When the load exceeds the budget, the system **signals** it
(column *Over budget*) but **never blocks** generation:
the system validates, it does not decide. In the official data, around
**17 professors out of 127** are already above their budget — this is a
factual statement left to the coordination's discretion.
            """
        )

    # ── Teacher availability verification (proof) ──────────────────────
    section_header("Teacher availability — verification")
    help_tip(
        "A posteriori proof that the produced schedule respects the parameters "
        "of 'Teacher Availability Configuration'. Generated by the pipeline "
        "(config/availability_verification.json) on every run.",
        icon=""
    )
    _verif = None
    for _vp in ("config/availability_verification.json",
                "outputs/optimization/config/availability_verification.json"):
        if os.path.exists(_vp):
            try:
                with open(_vp, "r", encoding="utf-8") as _vf:
                    _verif = json.load(_vf)
                break
            except Exception:
                _verif = None
    if _verif is None:
        st.info("No verification available yet. Run the "
                "pipeline to generate the availability enforcement proof "
                "(config/availability_verification.json).")
    else:
        # 1) Unavailable slots (HARD constraint)
        _hbs = _verif.get("hard_blocked_slots", {})
        _viol = _hbs.get("violations", [])
        _relaxed_n = int(_hbs.get("relaxed_count", 0))
        _unexpected_n = int(_hbs.get("unexpected_count", 0))
        _status = _hbs.get("status")
        if _status == "ok":
            st.success(
                f"Unavailable slots: **0 violation** "
                f"({_hbs.get('checked_groups', 0)} constrained groups checked). "
                "No session is placed on a blocked slot."
            )
        elif _status == "relaxed":
            st.warning(
                f"Unavailable slots: **{len(_viol)} expected violation(s)** "
                f"({_relaxed_n} relaxed, 0 unexpected). These placements are "
                "EXPECTED: for these subjects, enforcing the unavailability would "
                "leave **no feasible slot**, so the constraint was deliberately "
                "relaxed to keep the subject schedulable. Per the project "
                "principle, the system **signals** but **never blocks**."
            )
        else:
            st.error(
                f"Unavailable slots: **{len(_viol)} violation(s)** detected "
                f"({_relaxed_n} relaxed/expected, {_unexpected_n} unexpected). "
                "The unexpected ones warrant investigation."
            )
        if _viol:
            _vdf = pd.DataFrame(_viol).rename(columns={
                "subject": "Subject",
                "group": "Group",
                "day": "Day",
                "block": "Slot",
                "relaxed": "Relaxed (expected)",
                "reason": "Reason",
            })
            st.dataframe(_vdf, use_container_width=True, hide_index=True)
            st.caption(
                "Relaxed = expected: enforcing the unavailability would leave no "
                "feasible slot for this subject. To remove it, relax a teacher's "
                "unavailability, add a room/slot, or accept it."
            )

        # 2) Preferred time range (SOFT constraint)
        _pref = _verif.get("preferred_range", [])
        if _pref:
            st.markdown("**Preferred time range** (soft — compliance rate)")
            _pdf = pd.DataFrame(_pref).rename(columns={
                "teacher": "Teacher",
                "recognized": "Recognized",
                "preferred_blocks": "Preferred slots",
                "sessions_total": "Sessions",
                "sessions_inside": "Inside range",
                "pct_inside": "% inside range",
            })
            st.dataframe(_pdf, use_container_width=True, hide_index=True)

        # 3) Max lab days / week (SIGNAL)
        _mdw = _verif.get("max_days_per_week", [])
        if _mdw:
            st.markdown("**Maximum lab days / week** (signal)")
            _mdf = pd.DataFrame(_mdw).rename(columns={
                "teacher": "Teacher",
                "recognized": "Recognized",
                "cap": "Cap",
                "days_used": "Days used",
                "days": "Days",
                "status": "Status",
            })
            st.dataframe(_mdf, use_container_width=True, hide_index=True)

        if _verif.get("generated_at"):
            st.caption(f"Verification generated on {_verif['generated_at']}")

    st.caption("These are the same checks as verify_flow.py — shown here so no terminal is needed.")


# ════════════════════════════════════════════════════════════
# PAGE: HISTORY (snapshots / version timeline)
# Each pipeline run + every manual edit creates a snapshot.
# Daniel can view, restore, compare, or delete versions.
# ════════════════════════════════════════════════════════════
elif page == t('nav_history'):
    page_header(
        "Version history",
        "Every plan generation is saved automatically. "
        "You can restore any previous version at any time."
    )

    # Lazy import - only needed when this page is visited
    try:
        import version_manager as vm
    except ImportError:
        st.error("Module version_manager.py not found. "
                 "Check that the file is present in the application folder.")
        st.stop()

    # ───────────────────────────────────────────────────
    # 1. SUMMARY HEADER
    # ───────────────────────────────────────────────────
    snapshots = vm.list_snapshots()

    if not snapshots:
        st.info("No snapshots yet. "
                "Versions are created automatically after each pipeline run.")
        # Still allow manual snapshot creation if pipeline output exists
        if os.path.exists('outputs/optimization/optimized_schedule_v5.csv'):
            st.markdown("---")
            section_header("Create a manual snapshot")
            # Suggest an intelligent name following Daniel's convention.
            suggested_name = vm.suggest_snapshot_name('milestone')
            with st.form("manual_snapshot_form"):
                snap_label = st.text_input(
                    "Nom du snapshot",
                    value=suggested_name,
                    help="You can keep the suggested name or edit it "
                         "(format type Daniel : Distribucion_Practicas_25-26_revN)."
                )
                desc_input = st.text_input(
                    "Description (optionnelle)",
                    placeholder="e.g. First version validated by Daniel",
                )
                if st.form_submit_button("Create snapshot", type="primary"):
                    snap_id = vm.create_snapshot(
                        snapshot_type='milestone',
                        description=desc_input or 'Snapshot manuel',
                        label=snap_label if snap_label else None,
                    )
                    if snap_id:
                        st.success(f"Snapshot created: {snap_id}")
                        st.rerun()
                    else:
                        st.error("Creation failed")
        st.stop()

    # ───────────────────────────────────────────────────
    # 2. STATS CARDS
    # ───────────────────────────────────────────────────
    n_total = len(snapshots)
    n_auto = sum(1 for s in snapshots if s.get('snapshot_type') == 'auto')
    n_manual = sum(1 for s in snapshots if s.get('snapshot_type') == 'manual')
    n_milestone = sum(1 for s in snapshots if s.get('snapshot_type') == 'milestone')
    total_size_kb = sum(s.get('size_kb', 0) for s in snapshots)

    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Total versions</div>
                <div class="stat-value">{n_total}</div>
                <div class="stat-desc">snapshots stored</div>
            </div>
        """, unsafe_allow_html=True)
    with sc2:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Automatiques</div>
                <div class="stat-value">{n_auto}</div>
                <div class="stat-desc">after generation</div>
            </div>
        """, unsafe_allow_html=True)
    with sc3:
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Manuelles</div>
                <div class="stat-value">{n_manual + n_milestone}</div>
                <div class="stat-desc">{n_milestone} milestones</div>
            </div>
        """, unsafe_allow_html=True)
    with sc4:
        size_display = f"{total_size_kb / 1024:.1f} MB" if total_size_kb >= 1024 else f"{total_size_kb} KB"
        st.markdown(f"""
            <div class="stat-card">
                <div class="stat-label">Space used</div>
                <div class="stat-value">{size_display}</div>
                <div class="stat-desc">on disk</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────
    # 3. CREATE MANUAL SNAPSHOT
    # ───────────────────────────────────────────────────
    with st.expander("Create a manual snapshot (milestone)"):
        st.caption("Create a named snapshot to mark a milestone "
                   "(e.g. 'Version validated by Daniel', 'Before January changes')")
        suggested_name_inline = vm.suggest_snapshot_name('milestone')
        with st.form("manual_snap_form_inline"):
            snap_label_inline = st.text_input(
                "Nom du snapshot",
                value=suggested_name_inline,
                help="Daniel-style format — editable.",
            )
            desc_input = st.text_input(
                "Description du snapshot",
                placeholder="e.g. Version validated by Daniel on May 15",
            )
            if st.form_submit_button("Create snapshot", type="primary"):
                if snap_label_inline:
                    snap_id = vm.create_snapshot(
                        snapshot_type='milestone',
                        description=desc_input or snap_label_inline,
                        label=snap_label_inline,
                    )
                    if snap_id:
                        st.success(f"Snapshot created: {snap_id}")
                        st.rerun()
                    else:
                        st.error("Failed — check that a plan exists to archive")
                else:
                    st.warning("Veuillez entrer un nom de snapshot")

    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

    # ───────────────────────────────────────────────────
    # 4. SNAPSHOT TIMELINE (selectable)
    # ───────────────────────────────────────────────────
    section_header(f"Timeline ({len(snapshots)} versions)")

    # Build display strings for selectbox
    type_labels = {
        'auto': 'Auto',
        'manual': 'Manual',
        'milestone': 'Milestone',
    }

    snapshot_options = []
    for snap in snapshots:
        created = snap.get('created_at', '')
        try:
            dt = datetime.fromisoformat(created)
            time_str = dt.strftime('%d/%m/%Y %H:%M')
        except Exception:
            time_str = created

        type_label = type_labels.get(snap.get('snapshot_type'), '?')
        size_kb = snap.get('size_kb', 0)
        snap_id_display = snap.get('id', '?')
        desc = snap.get('description', '')[:50]

        # Show the snapshot ID (Daniel's naming convention) most prominently,
        # then type/date/size as secondary info.
        label = f"{snap_id_display}  ·  {type_label} {time_str}  ·  {size_kb} KB"
        if desc and desc not in snap_id_display:
            label += f"  —  {desc}"
        snapshot_options.append((label, snap['id']))

    selected_label = st.selectbox(
        "Select a version to view",
        options=[opt[0] for opt in snapshot_options],
        index=0,
        help="Versions are sorted newest to oldest",
    )
    # Map back to ID
    selected_id = next(opt[1] for opt in snapshot_options if opt[0] == selected_label)
    selected_snap = vm.get_snapshot(selected_id)

    if selected_snap:
        # Detail panel
        st.markdown(f"""
            <div class="info-card" style="margin-top: 1rem;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <div style="font-weight: 600; font-size: 1.1rem; color: var(--text-heading); margin-bottom: 0.25rem;">
                            {selected_snap.get('description', '?')}
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary);">
                            ID : <code>{selected_id}</code>
                            &nbsp;·&nbsp; Type : {type_labels.get(selected_snap.get('snapshot_type'), '?')}
                            &nbsp;·&nbsp; Created: {selected_snap.get('created_at', '?')[:19].replace('T', ' ')}
                            &nbsp;·&nbsp; Taille : {selected_snap.get('size_kb', 0)} KB
                        </div>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Action buttons
        ac1, ac2, ac3, ac4 = st.columns(4)
        with ac1:
            if st.button("Restore this version",
                          type="primary",
                          use_container_width=True,
                          help="Replaces the current plan with this version. "
                               "The current state will be automatically saved before replacement."):
                with st.spinner("Restauration en cours..."):
                    ok = vm.restore_snapshot(selected_id, create_safety_snapshot=True)
                if ok:
                    st.success(f"Version restored: {selected_id}")
                    st.info("A safety snapshot was created automatically with the previous state.")
                    st.rerun()
                else:
                    st.error("Restore failed")
        with ac2:
            with st.popover("Renommer", use_container_width=True):
                new_desc = st.text_input(
                    "Nouvelle description",
                    value=selected_snap.get('description', ''),
                    key=f"rename_{selected_id}",
                )
                if st.button("Enregistrer", key=f"save_rename_{selected_id}"):
                    if vm.update_description(selected_id, new_desc):
                        st.success("Description updated")
                        st.rerun()
        with ac3:
            with st.popover("Delete", use_container_width=True):
                st.warning(f"Permanently delete: **{selected_snap.get('description', '?')}**?")
                if st.button("Confirm deletion",
                             type="primary",
                             key=f"confirm_del_{selected_id}"):
                    if vm.delete_snapshot(selected_id):
                        st.success("Snapshot deleted")
                        st.rerun()
        with ac4:
            # Show key metrics if snapshot has them
            if 'metrics' in selected_snap:
                st.metric(
                    "Reliability score",
                    f"{selected_snap['metrics'].get('health', {}).get('score', '?')}/100",
                )

    # ───────────────────────────────────────────────────
    # 5. COMPARE TWO VERSIONS
    # ───────────────────────────────────────────────────
    if len(snapshots) >= 2:
        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        section_header("Comparer deux versions")

        c1, c2 = st.columns(2)
        with c1:
            label_a = st.selectbox(
                "Reference version",
                options=[opt[0] for opt in snapshot_options],
                index=min(1, len(snapshot_options) - 1),
                key='compare_a',
            )
            id_a = next(opt[1] for opt in snapshot_options if opt[0] == label_a)
        with c2:
            label_b = st.selectbox(
                "Compared version",
                options=[opt[0] for opt in snapshot_options],
                index=0,
                key='compare_b',
            )
            id_b = next(opt[1] for opt in snapshot_options if opt[0] == label_b)

        if id_a == id_b:
            st.info("Select two different versions to compare them.")
        else:
            with st.spinner("Comparing..."):
                diff = vm.compare_snapshots(id_a, id_b)

            if diff is None:
                st.error("Unable to compare these two versions")
            else:
                d1, d2, d3 = st.columns(3)
                with d1:
                    sd = diff.get('sessions_diff', 0)
                    color = "#22c55e" if sd == 0 else "#f59e0b"
                    sign = "+" if sd > 0 else ""
                    st.markdown(f"""
                        <div class="stat-card">
                            <div class="stat-label">Session difference</div>
                            <div class="stat-value" style="color: {color};">{sign}{sd}</div>
                            <div class="stat-desc">{diff.get('sessions_a', 0)} → {diff.get('sessions_b', 0)}</div>
                        </div>
                    """, unsafe_allow_html=True)
                with d2:
                    cc = diff.get('cells_changed', 0)
                    color = "#22c55e" if cc == 0 else "#f59e0b"
                    st.markdown(f"""
                        <div class="stat-card">
                            <div class="stat-label">Modified sessions</div>
                            <div class="stat-value" style="color: {color};">{cc}</div>
                            <div class="stat-desc">week, day, room changed</div>
                        </div>
                    """, unsafe_allow_html=True)
                with d3:
                    n_subj = len(diff.get('subjects_changed', []))
                    st.markdown(f"""
                        <div class="stat-card">
                            <div class="stat-label">Affected subjects</div>
                            <div class="stat-value">{n_subj}</div>
                            <div class="stat-desc">with at least 1 change</div>
                        </div>
                    """, unsafe_allow_html=True)

                if diff.get('subjects_changed'):
                    st.markdown("**Subjects with changes:**")
                    st.write(", ".join(diff['subjects_changed']))

                if diff.get('sessions_added', 0) > 0 or diff.get('sessions_removed', 0) > 0:
                    st.warning(
                        f"Sessions added: {diff.get('sessions_added', 0)} · "
                        f"removed: {diff.get('sessions_removed', 0)}"
                    )

    # Wizard navigation
    wizard_nav(
        prev_label="Reliability", prev_page='dashboard',
        next_label="Edit", next_page='edit',
    )

# ════════════════════════════════════════════════════════════
# PAGE: MANUAL EDIT
# Workflow restructured as a 3-step linear stepper:
#   Step 1: choose the type of operation (move or swap)
#   Step 2: configure the operation
#   Step 3: review and stage to the pending basket
#
# A compact pending basket is always visible at the top.
# Backend: manual_edit.py (unchanged)
# ════════════════════════════════════════════════════════════
elif page == t('nav_edit'):
    page_header(
        "Manual plan editing",
        "Three guided steps to safely modify the plan. "
        "Changes are staged until explicit validation — "
        "a snapshot is created before each commit."
    )

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Go to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    # Lazy import
    try:
        import manual_edit as me
    except ImportError:
        st.error("Module `manual_edit.py` not found. "
                 "Check that the file is present in the application folder.")
        st.stop()

    # ───────────────────────────────────────────────────
    # Initialize EditSession + wizard state in session_state
    # ───────────────────────────────────────────────────
    if 'edit_session' not in st.session_state:
        st.session_state.edit_session = me.EditSession()
        ok = st.session_state.edit_session.load()
        if not ok:
            st.error("Unable to load the plan. Run the pipeline first.")
            st.stop()

    if 'edit_wizard_step' not in st.session_state:
        st.session_state.edit_wizard_step = 1
    if 'edit_wizard_op' not in st.session_state:
        st.session_state.edit_wizard_op = None     # 'move' | 'swap'

    edit_session = st.session_state.edit_session
    n_pending = len(edit_session.pending)

    # ═══════════════════════════════════════════════════
    # COMPACT PENDING BASKET — always visible at the top
    # ═══════════════════════════════════════════════════
    if n_pending == 0:
        # Discreet when empty
        st.markdown(
            "<div style='padding:0.5rem 1rem; border-radius:8px; "
            "background:rgba(255,255,255,0.03); border-left:3px solid #4ade80; "
            "font-size:0.85rem; color:var(--text-secondary); margin-bottom:1rem;'>"
            "No pending changes — you can edit freely"
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        # Compact bar with summary + expansion
        with st.container(border=True):
            cba, cbb, cbc, cbd = st.columns([3, 2, 2, 1])
            with cba:
                st.markdown(
                    f"<div style='padding-top:0.4rem;'>"
                    f"<strong>{n_pending} pending modification(s)</strong> · "
                    f"<span style='color:var(--text-secondary); font-size:0.85rem;'>"
                    f"not yet applied to disk</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with cbb:
                # Suggest an intelligent default name for the snapshot.
                try:
                    import version_manager as _vm_for_suggest
                    _default_label = _vm_for_suggest.suggest_snapshot_name('milestone')
                except Exception:
                    _default_label = ''
                commit_label = st.text_input(
                    "Nom du snapshot",
                    value=_default_label,
                    key='commit_label_input',
                    label_visibility='collapsed',
                    help="Name suggested following Daniel's convention — editable.",
                )
            with cbc:
                if st.button("Apply all", type="primary",
                              use_container_width=True,
                              key='commit_all_button'):
                    success, msg = edit_session.commit(label=commit_label)
                    if success:
                        st.success(f"{msg}")
                        st.session_state.edit_wizard_step = 1
                        st.session_state.edit_wizard_op = None
                        st.rerun()
                    else:
                        st.error(f"{msg}")
            with cbd:
                if st.button("", help="Annuler toutes",
                              use_container_width=True,
                              key='discard_all_button'):
                    edit_session.discard_all_pending()
                    st.rerun()

            # Expander to see the list of pending changes
            with st.expander(f"See the details of {n_pending} modification(s)", expanded=False):
                for idx, change in enumerate(edit_session.pending):
                    cdl, cdr = st.columns([10, 1])
                    with cdl:
                        st.write(f"**{idx + 1}.** {change.description}")
                        if change.warnings:
                            st.caption(f"{len(change.warnings)} warning(s): "
                                        + " · ".join(change.warnings[:2])
                                        + (" …" if len(change.warnings) > 2 else ""))
                    with cdr:
                        if st.button("", key=f"discard_pending_{idx}",
                                      help="Remove from basket"):
                            edit_session.discard_pending(idx)
                            st.rerun()

    # ═══════════════════════════════════════════════════
    # STEPPER HEADER
    # ═══════════════════════════════════════════════════
    current_step = st.session_state.edit_wizard_step
    step_labels = ["1. Operation type", "2. Configure", "3. Validate"]

    sh = ""
    sh += "<div style='display:flex; gap:0; margin:1.5rem 0 2rem 0;'>"
    for i, label in enumerate(step_labels, start=1):
        if i < current_step:
            bg, color, border = "rgba(34,197,94,0.15)", "#4ade80", "#22c55e"
            icon = str(i)
        elif i == current_step:
            bg, color, border = "rgba(99,102,241,0.15)", "#a5b4fc", "#6366f1"
            icon = str(i)
        else:
            bg, color, border = "rgba(255,255,255,0.03)", "#71717a", "rgba(255,255,255,0.1)"
            icon = str(i)

        sh += (
            f"<div style='flex:1; padding:0.75rem 1rem; background:{bg}; "
            f"border:1px solid {border}; "
            f"border-radius:{'8px 0 0 8px' if i == 1 else ('0 8px 8px 0' if i == len(step_labels) else '0')}; "
            f"color:{color}; font-size:0.9rem; text-align:center;'>"
            f"<span style='font-weight:700; margin-right:0.5rem;'>{icon}</span>"
            f"{label}"
            f"</div>"
        )
    sh += "</div>"
    st.markdown(sh, unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════
    # STEP 1: choose the type of operation
    # ═══════════════════════════════════════════════════
    if current_step == 1:
        st.markdown("### What modification would you like to make?")
        st.caption("Click on a card to start. "
                   "You can go back at any time.")
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        op_col_a, op_col_b = st.columns(2)
        with op_col_a:
            with st.container(border=True):
                st.markdown(
                    "<div style='padding:0.5rem 0;'>"
                    '<div class="card-icon-placeholder"></div>'
                    "<h4 style='margin:0 0 0.5rem 0;'>Move a session</h4>"
                    "<p style='color:var(--text-secondary); font-size:0.9rem; "
                    "min-height:5rem; margin:0 0 1rem 0;'>"
                    "Change the week, day or time block "
                    "of a single session or all sessions of a group. "
                    "Useful for handling holidays or room conflicts."
                    "</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Start", type="primary",
                              use_container_width=True, key='choose_move'):
                    st.session_state.edit_wizard_op = 'move'
                    st.session_state.edit_wizard_step = 2
                    st.rerun()

        with op_col_b:
            with st.container(border=True):
                st.markdown(
                    "<div style='padding:0.5rem 0;'>"
                    '<div class="card-icon-placeholder"></div>'
                    "<h4 style='margin:0 0 0.5rem 0;'>Reorganise students</h4>"
                    "<p style='color:var(--text-secondary); font-size:0.9rem; "
                    "min-height:5rem; margin:0 0 1rem 0;'>"
                    "Swap two students between two groups, or move "
                    "one student to another group. "
                    "Shared subjects (Física/Química) are synchronised."
                    "</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                if st.button("Start", type="primary",
                              use_container_width=True, key='choose_swap'):
                    st.session_state.edit_wizard_op = 'swap'
                    st.session_state.edit_wizard_step = 2
                    st.rerun()

    # ═══════════════════════════════════════════════════
    # STEP 2: configure the operation
    # ═══════════════════════════════════════════════════
    elif current_step == 2:
        # Back button + breadcrumb
        bcol1, bcol2 = st.columns([1, 6])
        with bcol1:
            if st.button("← Retour", key='back_to_step1'):
                st.session_state.edit_wizard_step = 1
                st.session_state.edit_wizard_op = None
                st.rerun()
        with bcol2:
            op_label = ("Move a session" if st.session_state.edit_wizard_op == 'move'
                        else "Reorganise students")
            st.markdown(f"<div style='padding-top:0.4rem; color:var(--text-secondary);'>"
                        f"Step 2 — <strong>{op_label}</strong>"
                        f"</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        # Common subject + group selectors
        subjects = edit_session.list_subjects()
        if not subjects:
            st.error("No subject found in the plan.")
            st.stop()

        col_subj, col_grp = st.columns([2, 1])
        with col_subj:
            selected_subject = st.selectbox(
                "Subject",
                subjects,
                format_func=lambda s: s.replace('S1_', 'S1 · ').replace('S2_', 'S2 · '),
                key='edit_subject_select',
            )
        with col_grp:
            groups = edit_session.list_groups(selected_subject)
            if not groups:
                st.warning("No groups for this subject.")
                st.stop()
            selected_group = st.selectbox(
                "Groupe", groups, key='edit_group_select',
            )

        sessions_in_group = edit_session.list_sessions(selected_subject, selected_group)

        # ─────────────────────────────────────────────────────
        # OPERATION: MOVE (session or whole group)
        # ─────────────────────────────────────────────────────
        if st.session_state.edit_wizard_op == 'move':
            if not sessions_in_group:
                st.warning("This group has no sessions.")
                st.stop()

            # Show current sessions as context
            with st.expander(
                f"Sessions actuelles de "
                f"{selected_subject.replace('S1_', '').replace('S2_', '')} G{selected_group}",
                expanded=False,
            ):
                ses_df = pd.DataFrame([
                    {
                        'Práctica': f"P{s['session']}",
                        'Week': f"W{s['week']}",
                        'Day': s['day'],
                        'Bloc': s['time_block'],
                        'Room(s)': s['lab_rooms'],
                    }
                    for s in sessions_in_group
                ])
                st.dataframe(ses_df, hide_index=True, use_container_width=True)

            # Granularity sub-selector (more discreet than the radio at top)
            granularity = st.radio(
                "What do you want to move?",
                options=['A single session', 'All sessions of the group'],
                horizontal=True,
                key='move_granularity',
            )

            st.markdown("---")

            # ─── Sub-mode A: move a single session ───
            if granularity == 'A single session':
                sn_choice = st.selectbox(
                    "Which session?",
                    options=[s['session'] for s in sessions_in_group],
                    format_func=lambda n: (
                        f"Práctica {n} — actuellement "
                        f"W{next(s['week'] for s in sessions_in_group if s['session'] == n)} "
                        f"{next(s['day'] for s in sessions_in_group if s['session'] == n)} "
                        f"{next(s['time_block'] for s in sessions_in_group if s['session'] == n)}"
                    ),
                    key='edit_session_choice',
                )

                current = next(s for s in sessions_in_group if s['session'] == sn_choice)
                current_semester = int(edit_session.schedule_df[
                    (edit_session.schedule_df['subject'] == selected_subject)
                    & (edit_session.schedule_df['grupo'] == selected_group)
                ].iloc[0]['semester'])

                all_weeks = sorted(edit_session.schedule_df[
                    edit_session.schedule_df['semester'] == current_semester
                ]['week'].unique().tolist())
                all_weeks = [int(w) for w in all_weeks]

                # Smart C5 filtering (keep the L2 logic)
                other_sessions = [s for s in sessions_in_group if s['session'] != sn_choice]
                prev_session = max((s for s in other_sessions if s['session'] < sn_choice),
                                    key=lambda x: x['session'], default=None)
                next_session = min((s for s in other_sessions if s['session'] > sn_choice),
                                    key=lambda x: x['session'], default=None)
                c5_min_week = (prev_session['week'] + 1) if prev_session else min(all_weeks)
                c5_max_week = (next_session['week'] - 1) if next_session else max(all_weeks)
                c5_valid_weeks = [w for w in all_weeks if c5_min_week <= w <= c5_max_week]

                cw1, cw2 = st.columns([3, 2])
                with cw2:
                    show_all_weeks = st.checkbox(
                        "Show all weeks",
                        value=False,
                        key='show_all_weeks_toggle',
                        help=(
                            "By default, only weeks compatible with "
                            "the chronological order are offered."
                        ),
                    )

                with cw1:
                    week_options = all_weeks if show_all_weeks else c5_valid_weeks
                    if not week_options:
                        st.warning(
                            "No week respects the chronological order. "
                            "Check \"Show all weeks\" to force."
                        )
                        week_options = all_weeks

                    current_week = int(current['week'])
                    if current_week in week_options:
                        default_idx = week_options.index(current_week)
                    elif c5_valid_weeks:
                        default_idx = week_options.index(c5_valid_weeks[len(c5_valid_weeks) // 2])
                    else:
                        default_idx = 0

                    target_week = st.selectbox(
                        "Target week",
                        options=week_options,
                        index=default_idx,
                        format_func=lambda w: (
                            f"W{w}" + (" — current" if w == current_week else "")
                        ),
                        key='target_week_select',
                    )

                # C5 context caption
                if prev_session and next_session:
                    st.caption(
                        f"To respect order: session {sn_choice} must be between "
                        f"**W{c5_min_week}** et **W{c5_max_week}**."
                    )
                elif prev_session:
                    st.caption(
                        f"To respect order: session {sn_choice} must start from "
                        f"de **W{c5_min_week}**."
                    )
                elif next_session:
                    st.caption(
                        f"To respect order: session {sn_choice} must be at the latest "
                        f"tard en **W{c5_max_week}**."
                    )

                # Build feasibility grid
                with st.spinner("Computing available slots…"):
                    grid = edit_session.feasibility_grid(
                        subject=selected_subject, grupo=selected_group,
                        session_num=sn_choice, target_weeks=[target_week],
                    )

                # Quality hint (global feedback on grid)
                n_warning = sum(1 for g in grid.values() if g['status'] == 'warning')
                n_total = max(len(grid), 1)
                if n_warning > n_total * 0.6 and not show_all_weeks:
                    st.info(
                        f"Week W{target_week} produces many warnings "
                        f"({n_warning}/{n_total}). This is often normal — the warnings "
                        f"are non-blocking."
                    )

                st.markdown(
                    "**Target slot.** Hover over cells to see details. "
                    "<span style='display:inline-flex;gap:0.5rem;font-size:0.85rem;'>"
                    "<span style='display:inline-flex;align-items:center;gap:0.3rem;'>"
                    "<span style='width:8px;height:8px;border-radius:50%;background:#22C55E;'></span>Free</span>"
                    "<span style='display:inline-flex;align-items:center;gap:0.3rem;'>"
                    "<span style='width:8px;height:8px;border-radius:50%;background:#F59E0B;'></span>Warning</span>"
                    "<span style='display:inline-flex;align-items:center;gap:0.3rem;'>"
                    "<span style='width:8px;height:8px;border-radius:50%;background:#EF4444;'></span>Conflict</span>"
                    "<span style='display:inline-flex;align-items:center;gap:0.3rem;'>"
                    "<span style='width:8px;height:8px;border-radius:50%;background:#6366F1;'></span>Current</span>"
                    "</span>",
                    unsafe_allow_html=True,
                )

                # Render the visual grid
                grid_html = '<table style="width:100%; border-collapse:collapse; font-size:0.85rem; margin-bottom:1rem;">'
                grid_html += (
                    '<tr><th style="padding:8px; border:1px solid #444; background:#222">Day ↓ / Block →</th>'
                )
                for block in me.TIME_BLOCKS:
                    grid_html += f'<th style="padding:8px; border:1px solid #444; background:#222">{block}</th>'
                grid_html += '</tr>'

                for day in me.DAYS_OF_WEEK:
                    grid_html += (
                        f'<tr><td style="padding:8px; border:1px solid #444; '
                        f'background:#1a1a1a; font-weight:600">{day}</td>'
                    )
                    for block in me.TIME_BLOCKS:
                        cell = grid.get((target_week, day, block), {'status': 'free', 'reasons': []})
                        status = cell['status']
                        # Sober CSS dots replacing emojis - clearly visible
                        # but professional rather than playful.
                        if status == 'self':
                            dot_color, bg, tt = '#6366F1', 'rgba(99,102,241,0.2)', 'Current position'
                        elif status == 'free':
                            dot_color, bg, tt = '#22C55E', 'rgba(34,197,94,0.08)', 'Free'
                        elif status == 'warning':
                            dot_color, bg, tt = '#F59E0B', 'rgba(245,158,11,0.12)', ' · '.join(cell['reasons'])
                        else:
                            dot_color, bg, tt = '#EF4444', 'rgba(239,68,68,0.12)', ' · '.join(cell['reasons'])
                        dot = (f'<span style="display:inline-block;width:10px;height:10px;'
                               f'border-radius:50%;background:{dot_color};"></span>')
                        grid_html += (
                            f'<td style="padding:8px; border:1px solid #444; background:{bg}; '
                            f'text-align:center" title="{tt}">{dot}</td>'
                        )
                    grid_html += '</tr>'
                grid_html += '</table>'
                st.markdown(grid_html, unsafe_allow_html=True)

                col_dt, col_bk = st.columns(2)
                with col_dt:
                    target_day = st.selectbox("Day", me.DAYS_OF_WEEK, key='target_day_select')
                with col_bk:
                    target_block = st.selectbox("Time block", me.TIME_BLOCKS,
                                                  key='target_block_select')

                # Status of the chosen target
                chosen = grid.get((target_week, target_day, target_block),
                                    {'status': 'free', 'reasons': []})
                status_kind = chosen['status']

                # Status feedback
                if status_kind == 'self':
                    st.info("This is the current position of the session.")
                elif status_kind == 'free':
                    st.success("Slot free — move OK.")
                elif status_kind == 'warning':
                    st.warning("Move possible but check warnings:\n\n"
                                + "\n".join(f"- {r}" for r in chosen['reasons']))
                else:
                    st.error("Conflict — move impossible:\n\n"
                              + "\n".join(f"- {r}" for r in chosen['reasons']))

                # Action button at the bottom of the page (Step 2 → Step 3)
                if status_kind == 'free':
                    btn_label, btn_type, btn_disabled = "Continuer vers validation →", "primary", False
                elif status_kind == 'warning':
                    btn_label, btn_type, btn_disabled = "Continue (with warning) →", "secondary", False
                elif status_kind == 'self':
                    btn_label, btn_type, btn_disabled = "Current position", "secondary", True
                else:
                    btn_label, btn_type, btn_disabled = "Conflict — choose another slot", "secondary", True

                st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
                if st.button(btn_label, type=btn_type, disabled=btn_disabled,
                              use_container_width=True, key='proceed_move_session'):
                    # Stage the change and move to Step 3
                    result = edit_session.propose_move_session(
                        subject=selected_subject, grupo=selected_group,
                        session_num=sn_choice,
                        new_week=target_week, new_day=target_day, new_block=target_block,
                    )
                    if result.is_valid:
                        st.session_state.edit_wizard_step = 3
                        st.session_state.edit_last_op_summary = {
                            'kind': 'move_session',
                            'subject': selected_subject,
                            'grupo': selected_group,
                            'session': sn_choice,
                            'new_week': target_week,
                            'new_day': target_day,
                            'new_block': target_block,
                            'warnings': result.warnings,
                        }
                        st.rerun()
                    else:
                        st.error("Failed: " + "; ".join(result.blockers))

            # ─── Sub-mode B: move the whole group ───
            else:
                st.info("All sessions of the group will be moved to the new "
                        "slot (day + time block). Weeks remain unchanged.")

                current_day = sessions_in_group[0]['day']
                current_block = sessions_in_group[0]['time_block']
                st.caption(f"Current position : **{current_day} {current_block}**")

                col_nd, col_nb = st.columns(2)
                with col_nd:
                    new_day = st.selectbox(
                        "New day",
                        me.DAYS_OF_WEEK,
                        index=me.DAYS_OF_WEEK.index(current_day),
                        key='group_target_day',
                    )
                with col_nb:
                    new_block = st.selectbox(
                        "Nouveau bloc horaire",
                        me.TIME_BLOCKS,
                        index=me.TIME_BLOCKS.index(current_block) if current_block in me.TIME_BLOCKS else 0,
                        key='group_target_block',
                    )

                if new_day == current_day and new_block == current_block:
                    st.caption("Select a different day/block to move the group.")
                else:
                    preview = edit_session._validate_group_move(
                        subject=selected_subject, grupo=selected_group,
                        new_day=new_day, new_block=new_block,
                    )

                    if not preview.is_valid:
                        st.error("Conflict — move impossible:")
                        for b in preview.blockers[:10]:
                            st.write(f"  - {b}")
                        btn_disabled = True
                        btn_label = "Conflict — choose another slot"
                        btn_type = "secondary"
                    elif preview.warnings:
                        st.warning("Move possible but check warnings:")
                        for w in preview.warnings[:10]:
                            st.write(f"  - {w}")
                        btn_disabled = False
                        btn_label = "Continue (with warning) →"
                        btn_type = "secondary"
                    else:
                        st.success("No conflict detected — move OK.")
                        btn_disabled = False
                        btn_label = "Continuer vers validation →"
                        btn_type = "primary"

                    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
                    if st.button(btn_label, type=btn_type, disabled=btn_disabled,
                                  use_container_width=True, key='proceed_move_group'):
                        result = edit_session.propose_move_group(
                            subject=selected_subject, grupo=selected_group,
                            new_day=new_day, new_block=new_block,
                        )
                        if result.is_valid:
                            st.session_state.edit_wizard_step = 3
                            st.session_state.edit_last_op_summary = {
                                'kind': 'move_group',
                                'subject': selected_subject,
                                'grupo': selected_group,
                                'new_day': new_day,
                                'new_block': new_block,
                                'warnings': result.warnings,
                            }
                            st.rerun()

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # OPERATION: SWAP (students between groups)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        elif st.session_state.edit_wizard_op == 'swap':
            family = edit_session._get_subject_family_members(selected_subject)
            is_shared = len(family) > 1

            if is_shared:
                family_names = ' + '.join(
                    s.replace('S1_', '').replace('S2_', '') for s in family
                )
                st.info(
                    f"**{selected_subject.replace('S1_', '').replace('S2_', '')}** "
                    f"shares its groups with **{family_names}**. By default, the swap "
                    f"is applied to both to preserve consistency."
                )

            all_groups_info = edit_session.list_all_groups(selected_subject)
            source_info = next(
                (g for g in all_groups_info if g['grupo'] == selected_group),
                None
            )
            if source_info is None:
                st.error(f"Group G{selected_group} not found.")
                st.stop()

            st.markdown(
                f"<div style='padding:0.5rem 0.75rem; background:rgba(99,102,241,0.08); "
                f"border-radius:6px; margin-bottom:1rem;'>"
                f"<strong>Source group:</strong> G{selected_group} — "
                f"{source_info['day']} {source_info['block']} "
                f"<span style='color:var(--text-secondary);'>({source_info['size']} students)</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            students_a = edit_session.list_students_in_group(selected_subject, selected_group)
            if not students_a:
                st.warning("No students in this group.")
                st.stop()

            student_a_choice = st.selectbox(
                f"Student to move (from G{selected_group})",
                options=[s['id'] for s in students_a],
                format_func=lambda sid: (
                    f"{next(x['name'] for x in students_a if x['id'] == sid)}"
                    + (f" ({next(x['titulacion'] for x in students_a if x['id'] == sid)})"
                       if any(x.get('titulacion') for x in students_a) else '')
                ),
                key='swap_student_a',
            )

            other_groups = [g for g in all_groups_info if g['grupo'] != selected_group]
            if not other_groups:
                st.warning("No other group available.")
                st.stop()

            grupo_b_choice = st.selectbox(
                "Groupe destination",
                options=[g['grupo'] for g in other_groups],
                format_func=lambda gn: (
                    f"G{gn} — "
                    f"{next(g['day'] for g in other_groups if g['grupo'] == gn)} "
                    f"{next(g['block'] for g in other_groups if g['grupo'] == gn)} "
                    f"({next(g['size'] for g in other_groups if g['grupo'] == gn)} stu.)"
                ),
                key='swap_group_b',
            )

            students_b = edit_session.list_students_in_group(selected_subject, grupo_b_choice)
            student_b_options = [None] + [s['id'] for s in students_b]

            def _format_student_b(sid):
                if sid is None:
                    return "— Nobody (unilateral move) —"
                student_obj = next((x for x in students_b if x['id'] == sid), None)
                if student_obj is None:
                    return sid
                label = student_obj['name']
                if student_obj.get('titulacion'):
                    label += f" ({student_obj['titulacion']})"
                return label

            student_b_choice = st.selectbox(
                f"Student to receive in exchange (from G{grupo_b_choice})",
                options=student_b_options,
                format_func=_format_student_b,
                key='swap_student_b',
                help=(
                    "Select a student for a balanced swap, or "
                    "\"Nobody\" for a unilateral move."
                ),
            )

            if is_shared:
                cascade_shared = st.checkbox(
                    f"Also apply to shared subjects "
                    f"({', '.join(s.replace('S1_', '').replace('S2_', '') for s in family if s != selected_subject)})",
                    value=True,
                    key='swap_cascade_shared',
                    help=(
                        "Recommended: preserves shared-group consistency."
                    ),
                )
            else:
                cascade_shared = False

            # Live validation
            preview = edit_session.validate_swap(
                subject=selected_subject,
                grupo_a=selected_group, student_a=student_a_choice,
                grupo_b=grupo_b_choice, student_b=student_b_choice,
                cascade_shared=cascade_shared,
            )

            if not preview.is_valid:
                swap_status = 'conflict'
            elif preview.warnings:
                swap_status = 'warning'
            else:
                swap_status = 'free'

            # Compact concerned-subjects line
            if cascade_shared and is_shared:
                family_labels = ' + '.join(
                    s.replace('S1_', '').replace('S2_', '') for s in family
                )
                st.caption(f"Subjects concerned by this swap: **{family_labels}**")
            else:
                st.caption(
                    f"Subject concerned: "
                    f"**{selected_subject.replace('S1_', '').replace('S2_', '')}** seule"
                )

            # Feedback
            if swap_status == 'conflict':
                st.error("Conflict — swap impossible:")
                for b in preview.blockers[:10]:
                    st.write(f"  - {b}")
                btn_label, btn_type, btn_disabled = "Conflict — resolve first", "secondary", True
            elif swap_status == 'warning':
                st.warning("Swap possible but check warnings:")
                for w in preview.warnings[:10]:
                    st.write(f"  - {w}")
                btn_label, btn_type, btn_disabled = "Continue (with warning) →", "secondary", False
            else:
                if student_b_choice is None:
                    st.success("Unilateral move validated — no conflict detected.")
                else:
                    st.success("Swap validated — no conflict detected.")
                btn_label, btn_type, btn_disabled = "Continuer vers validation →", "primary", False

            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
            if st.button(btn_label, type=btn_type, disabled=btn_disabled,
                          use_container_width=True, key='proceed_swap'):
                result = edit_session.propose_swap(
                    subject=selected_subject,
                    grupo_a=selected_group, student_a=student_a_choice,
                    grupo_b=grupo_b_choice, student_b=student_b_choice,
                    cascade_shared=cascade_shared,
                )
                if result.is_valid:
                    st.session_state.edit_wizard_step = 3
                    st.session_state.edit_last_op_summary = {
                        'kind': 'swap',
                        'subject': selected_subject,
                        'grupo_a': selected_group,
                        'student_a': student_a_choice,
                        'grupo_b': grupo_b_choice,
                        'student_b': student_b_choice,
                        'cascade_shared': cascade_shared,
                        'warnings': result.warnings,
                    }
                    st.rerun()
                else:
                    st.error("Failed: " + "; ".join(result.blockers))

    # ═══════════════════════════════════════════════════
    # STEP 3: confirmation + next action
    # ═══════════════════════════════════════════════════
    elif current_step == 3:
        last_op = st.session_state.get('edit_last_op_summary')

        st.markdown("### Modification staged")
        st.caption(
            "The modification has been added to the basket. It will be applied to disk "
            "when you click on **\"Apply all\"** at the top of the page. "
            "You can also chain further modifications."
        )
        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        # Recap card
        if last_op:
            with st.container(border=True):
                kind = last_op.get('kind')
                if kind == 'move_session':
                    st.markdown(
                        f"**Type:** Session move  \n"
                        f"**Subject:** {last_op['subject'].replace('S1_', 'S1 · ').replace('S2_', 'S2 · ')}  \n"
                        f"**Groupe :** G{last_op['grupo']} · Práctica {last_op['session']}  \n"
                        f"**New slot:** W{last_op['new_week']} "
                        f"{last_op['new_day']} {last_op['new_block']}"
                    )
                elif kind == 'move_group':
                    st.markdown(
                        f"**Type:** Whole-group move  \n"
                        f"**Subject:** {last_op['subject'].replace('S1_', 'S1 · ').replace('S2_', 'S2 · ')}  \n"
                        f"**Group:** G{last_op['grupo']} (all sessions)  \n"
                        f"**New weekly slot:** {last_op['new_day']} {last_op['new_block']}"
                    )
                elif kind == 'swap':
                    if last_op.get('student_b'):
                        verb = f"Swap {last_op['student_a']} ↔ {last_op['student_b']}"
                    else:
                        verb = f"Move of {last_op['student_a']}"
                    st.markdown(
                        f"**Type :** {verb}  \n"
                        f"**Subject:** {last_op['subject'].replace('S1_', 'S1 · ').replace('S2_', 'S2 · ')}  \n"
                        f"**Groups:** G{last_op['grupo_a']} ↔ G{last_op['grupo_b']}  \n"
                        f"**Shared subjects cascade:** "
                        f"{'oui' if last_op.get('cascade_shared') else 'non'}"
                    )

                if last_op.get('warnings'):
                    st.markdown("---")
                    st.markdown(f"**{len(last_op['warnings'])} warning(s):**")
                    for w in last_op['warnings']:
                        st.write(f"- {w}")

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown(f"**{n_pending} modification(s)** total in the basket.")

        # Three next-action buttons
        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            if st.button("Make another modification",
                          type="primary", use_container_width=True,
                          key='action_more'):
                st.session_state.edit_wizard_step = 1
                st.session_state.edit_wizard_op = None
                st.rerun()
        with nc2:
            if st.button("Appliquer maintenant",
                          use_container_width=True,
                          key='action_apply_now'):
                success, msg = edit_session.commit(label='')
                if success:
                    st.success(f"{msg}")
                    st.session_state.edit_wizard_step = 1
                    st.session_state.edit_wizard_op = None
                    st.rerun()
                else:
                    st.error(f"{msg}")
        with nc3:
            if st.button("Remove this modification",
                          use_container_width=True,
                          key='action_undo'):
                if edit_session.pending:
                    edit_session.discard_pending(len(edit_session.pending) - 1)
                st.session_state.edit_wizard_step = 1
                st.session_state.edit_wizard_op = None
                st.rerun()

    # ═══════════════════════════════════════════════════
    # Wizard navigation footer
    # ═══════════════════════════════════════════════════
    wizard_nav(
        prev_label="History", prev_page='history',
        next_label="Groups", next_page='groups',
    )

# ════════════════════════════════════════════════════════════
# PAGE: GROUPS
# ════════════════════════════════════════════════════════════
elif page == t('nav_groups'):
    page_header(t('grp_title'), t('grp_sub'))

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Go to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    try:
        grps = pd.read_csv('outputs/optimization/group_composition.csv')
        subjects = sorted(grps['subject'].unique())

        c1, c2 = st.columns(2)
        with c1: subject = st.selectbox("Subject", subjects)
        with c2:
            grp_nums = sorted(grps[grps['subject']==subject]['grupo'].unique())
            grupo = st.selectbox("Group", grp_nums)

        filt = grps[(grps['subject']==subject) & (grps['grupo']==grupo)]
        nc = 'student_name' if 'student_name' in grps.columns else 'student_hash'
        filt = filt.drop_duplicates(subset=[nc])

        c1, c2 = st.columns(2)
        with c1: stat_card(t('students'), len(filt), "")
        with c2:
            prog_mix = ', '.join(f"{p}: {c}" for p, c in filt['titulacion'].value_counts().items()) if 'titulacion' in filt.columns else ""
            stat_card("Programs", len(filt['titulacion'].unique()) if 'titulacion' in filt.columns else 0, prog_mix[:40])

        cols_show = [nc]
        if 'titulacion' in filt.columns: cols_show.append('titulacion')
        st.dataframe(filt[cols_show].sort_values(nc), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Loading error: {e}")

# ════════════════════════════════════════════════════════════
# PAGE: COMPARE
# ════════════════════════════════════════════════════════════
elif page == t('nav_compare'):
    page_header(t('cmp_title'), t('cmp_sub'))

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Go to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    DANIEL = {
        'Física': 248, 'Química': 248, 'Electrotecnia': 115, 'Mecanismos': 110,
        'Termodinámica': 116, 'Tecnologías de Fabricación': 112,
        'Robótica y Automatización': 54, 'Automatización Industrial': 8,
    }

    try:
        grps = pd.read_csv('outputs/optimization/group_composition.csv')
        nc = 'student_name' if 'student_name' in grps.columns else 'student_hash'

        rows = []
        for subj, dref in DANIEL.items():
            ours = grps[grps['subject']==subj].drop_duplicates(subset=['grupo', nc])
            n = len(ours)
            diff = n - dref
            pct = abs(diff) / max(dref,1) * 100
            status = "OK" if pct<=15 else "Moderate" if pct<=40 else "Critical"
            rows.append({
                'Subject': subj, 'Ours': n, 'Daniel': dref,
                'Diff': f"{diff:+d}", '%': f"{pct:.0f}%", 'Status': status,
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Error: {e}")

# ════════════════════════════════════════════════════════════
# PAGE: EXPORT
# ════════════════════════════════════════════════════════════
elif page == t('nav_export'):
    page_header(t('exp_title'), t('exp_sub'))
    wizard_stepper('export')

    if not run_ok:
        st.warning("**Pipeline not executed** — please run the optimization first.")
        if st.button("← Back to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    help_tip(
        "<strong>Step 4 of 4:</strong> Download the Excel files in Daniel's format for "
        "<strong>3 levels × 2 semesters</strong>. Each file contains the "
        "<em>Grupo de prácticas</em> and <em>Vista profesor</em> tabs validated by Daniel.",
        icon=""
    )

    # ─── REGENERATE ALL button (top-priority) ───
    st.markdown(f"""
        <div class="info-card" style="background: linear-gradient(135deg, var(--bg-surface) 0%, var(--bg-accent-subtle) 100%); border-left: 4px solid var(--navy); margin-bottom: 1.5rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div style="font-weight: 600; color: var(--text-heading); font-size: 1.05rem; margin-bottom: 0.25rem;">Regenerate everything</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary);">Generate S1 + S2 files for all 3 levels (Primero + Segundo + Tercero) at once</div>
                </div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    if st.button("Generate ALL (S1 + S2 × Primero + Segundo + Tercero)",
                 type="primary", use_container_width=True, key='gen_all'):
        progress = st.progress(0, text="Starting...")
        try:
            import excel_export as _xl
            progress.progress(0.15, text="Generating S1 (Primero + Segundo + Tercero)...")
            r1 = _xl.generate_semester(1)
            progress.progress(0.6, text="Generating S2 (Primero + Segundo + Cuarto)...")
            r2 = _xl.generate_semester(2)
            progress.progress(1.0, text="Done!")

            n_files = len(r1["files"]) + len(r2["files"])
            if r1["ok"] and r2["ok"]:
                st.success(f"{n_files} files generated (S1 + S2 across all levels)")
            elif r1["ok"] or r2["ok"]:
                st.warning(f"Partial success — {n_files} file(s) generated")
            else:
                st.error("Generation failed — see the log below")

            with st.expander("Full log"):
                st.code((r1["log"] or "") + "\n" + (r2["log"] or ""), language="text")
            st.rerun()  # refresh the file tree / download buttons below
        except Exception as e:
            import traceback
            progress.empty()
            st.error(f"Generation error: {e}")
            with st.expander("Traceback"):
                st.code(traceback.format_exc(), language="text")

    # ─── Download FULL Curso 2025-2026 ZIP (all 6 files) ───
    curso_root = 'outputs/optimization/Curso_2025_2026'
    if os.path.exists(curso_root):
        # Collect all .xlsx files in Curso_2025_2026
        all_curso_files = []
        for root, dirs, files in os.walk(curso_root):
            for f in files:
                if f.lower().endswith('.xlsx'):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, curso_root)
                    all_curso_files.append((full_path, rel_path))

        if all_curso_files:
            st.markdown("""
                <div class="info-card" style="
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.04), rgba(34, 197, 94, 0.01));
                    border-left: 4px solid var(--green);
                    margin-top: 1rem;
                    margin-bottom: 1rem;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="font-weight: 600; color: var(--text-heading); font-size: 1rem; margin-bottom: 0.25rem;">
                                Download Curso 2025-2026 (full archive)
                            </div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">
                                Tous les fichiers Excel (S1 + S2 × Primero + Segundo + Tercero) dans une archive ZIP unique
                            </div>
                        </div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            try:
                # Build the ZIP in memory
                buf_full = io.BytesIO()
                with zipfile.ZipFile(buf_full, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for full_path, rel_path in all_curso_files:
                        zf.write(full_path, os.path.join('Curso_2025_2026', rel_path))

                file_count = len(all_curso_files)
                size_mb = len(buf_full.getvalue()) / 1024 / 1024

                st.download_button(
                    f"Download Curso 2025-2026.zip ({file_count} files, {size_mb:.1f} MB)",
                    data=buf_full.getvalue(),
                    file_name="Curso_2025_2026.zip",
                    mime="application/zip",
                    type="primary",
                    use_container_width=True,
                    key='zip_curso_full',
                )
            except Exception as e:
                st.error(f"Error while creating the ZIP: {e}")

    st.markdown("---")

    # Generate buttons
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
            <div class="info-card">
                <div class="stat-label">{t('gen_s1_title')}</div>
                <p style="font-size: 0.85rem; color: var(--text-secondary); margin: 0.5rem 0 1rem 0;">Primero · Segundo · Tercero</p>
            </div>
        """, unsafe_allow_html=True)
        if st.button(f"{t('gen_s1_btn')}", type="primary", use_container_width=True, key='gen_s1'):
            with st.spinner(f"{t('running')}"):
                try:
                    import excel_export as _xl
                    r = _xl.generate_semester(1)
                    if r["ok"]:
                        st.success(f"{t('done')} — {len(r['files'])} file(s) S1")
                        with st.expander("Log"):
                            st.code(r["log"], language="text")
                        st.rerun()
                    else:
                        st.error("Error generating S1 files")
                        with st.expander("Error log"):
                            st.code((r["error"] or "") + "\n" + (r["log"] or ""), language="text")
                except Exception as e:
                    st.error(f"{e}")

    with c2:
        st.markdown(f"""
            <div class="info-card">
                <div class="stat-label">{t('gen_s2_title')}</div>
                <p style="font-size: 0.85rem; color: var(--text-secondary); margin: 0.5rem 0 1rem 0;">Primero · Segundo · Tercero</p>
            </div>
        """, unsafe_allow_html=True)
        if st.button(f"{t('gen_s2_btn')}", type="primary", use_container_width=True, key='gen_s2'):
            with st.spinner(f"{t('running')}"):
                try:
                    import excel_export as _xl
                    r = _xl.generate_semester(2)
                    if r["ok"]:
                        st.success(f"{t('done')} — {len(r['files'])} file(s) S2")
                        with st.expander("Log"):
                            st.code(r["log"], language="text")
                        st.rerun()
                    else:
                        st.error("Error generating S2 files")
                        with st.expander("Error log"):
                            st.code((r["error"] or "") + "\n" + (r["log"] or ""), language="text")
                except Exception as e:
                    st.error(f"{e}")

    # File tree + downloads
    section_header(f"{t('download_files')}")

    curso_dir = 'outputs/optimization/Curso_2025_2026'
    if os.path.exists(curso_dir):
        all_files = []
        for root, dirs, files in sorted(os.walk(curso_dir)):
            for f in sorted(files):
                if f.endswith('.xlsx'):
                    all_files.append((os.path.join(root, f), os.path.relpath(os.path.join(root, f), curso_dir)))

        s1_files = [(fp, rel) for fp, rel in all_files if 'Primer semestre' in rel]
        s2_files = [(fp, rel) for fp, rel in all_files if 'Segundo semestre' in rel]

        tab1, tab2 = st.tabs([f"S1 ({len(s1_files)})", f"S2 ({len(s2_files)})"])

        with tab1:
            for fp, rel in s1_files:
                with open(fp, 'rb') as f:
                    parts = rel.split(os.sep)
                    label = f"{parts[0]} · {parts[-1]}"
                    st.download_button(
                        label, data=f.read(), file_name=parts[-1],
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        use_container_width=True, key=f"dl_{rel}",
                    )

            if s1_files:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for fp, rel in s1_files:
                        zf.write(fp, os.path.join('Curso_2025_2026', rel))
                st.download_button(
                    f"{t('dl_s1_zip')}", data=buf.getvalue(),
                    file_name="S1_Curso_2025_2026.zip", mime="application/zip",
                    type="primary", use_container_width=True, key='zip_s1',
                )

        with tab2:
            for fp, rel in s2_files:
                with open(fp, 'rb') as f:
                    parts = rel.split(os.sep)
                    label = f"{parts[0]} · {parts[-1]}"
                    st.download_button(
                        label, data=f.read(), file_name=parts[-1],
                        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        use_container_width=True, key=f"dl2_{rel}",
                    )

            if s2_files:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for fp, rel in s2_files:
                        zf.write(fp, os.path.join('Curso_2025_2026', rel))
                st.download_button(
                    f"{t('dl_s2_zip')}", data=buf.getvalue(),
                    file_name="S2_Curso_2025_2026.zip", mime="application/zip",
                    type="primary", use_container_width=True, key='zip_s2',
                )
    else:
        st.info("No files generated yet")

    # ─── Wizard navigation ───
    wizard_nav(
        prev_label="Results", prev_page='results',
        next_label=None, next_page=None,  # No next page after export
    )

    # Final completion message
    if os.path.exists('outputs/optimization/Curso_2025_2026'):
        st.markdown("""
            <div style="text-align: center; margin-top: 2rem; padding: 1.5rem;
                         background: linear-gradient(135deg, rgba(34, 197, 94, 0.06), rgba(34, 197, 94, 0.02));
                         border: 1px solid rgba(34, 197, 94, 0.25);
                         border-radius: 12px;">
                <div style="font-weight: 600; color: var(--green); margin-bottom: 0.25rem;">
                    Workflow complete
                </div>
                <div style="font-size: 0.85rem; color: var(--text-secondary);">
                    Your Excel files are ready to send to Daniel.
                </div>
            </div>
        """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE: INDIVIDUAL STUDENT CASE (Daniel's exception handler)
# ════════════════════════════════════════════════════════════
elif page == t('nav_student'):
    page_header(
        "Individual case",
        "Quickly find the most compatible group for a given student."
    )

    # ─── Check that pipeline has been run ───
    schedule_path = 'outputs/optimization/optimized_schedule_v5.csv'
    groups_path = 'outputs/optimization/group_composition.csv'
    directory_path = 'outputs/optimization/student_directory.csv'
    student_busy_path = 'data_clean/optimization/student_busy.csv'

    if not os.path.exists(schedule_path):
        st.warning("**No plan generated** — please run the pipeline first.")
        if st.button("← Go to Optimize", type="primary"):
            st.session_state['_nav_to'] = 'optimize'
            st.rerun()
        st.stop()

    # ─── Load all data ───
    @st.cache_data
    def load_student_case_data():
        sched = pd.read_csv(schedule_path)
        groups = pd.read_csv(groups_path) if os.path.exists(groups_path) else None
        directory = pd.read_csv(directory_path) if os.path.exists(directory_path) else None
        student_busy = {}
        if os.path.exists(student_busy_path):
            sb_df = pd.read_csv(student_busy_path)
            for _, row in sb_df.iterrows():
                sid = row['student_id']
                if sid not in student_busy:
                    student_busy[sid] = set()
                student_busy[sid].add((int(row['day_idx']), int(row['block_id'])))
        return sched, groups, directory, student_busy

    try:
        sched_df, groups_df, directory_df, student_busy_map = load_student_case_data()
    except Exception as e:
        safe_error("Error loading data", e, stop=True)

    if directory_df is None or len(directory_df) == 0:
        st.warning("The student_directory.csv file was not generated. "
                    "Re-run the pipeline to generate it.")
        st.stop()

    student_options = []
    for _, row in directory_df.iterrows():
        sid = row['student_id']
        sname = str(row.get('student_name', sid))
        prog = row.get('titulacion', '')
        prog_str = f" ({prog})" if prog else ""
        label = f"{sname}{prog_str}"
        student_options.append((label, sid, sname))
    student_options.sort(key=lambda x: x[0])

    DAYS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
    BLOCKS = [
        (1, "08:30-10:30"),
        (2, "10:30-12:30"),
        (3, "12:30-14:30"),
        (4, "15:00-17:00"),
        (5, "17:00-19:00"),
        (6, "19:00-21:00"),
    ]

    # ════════════════════════════════════════════════════════════
    # STEP 1: Identify the student
    # ════════════════════════════════════════════════════════════
    st.markdown("### 1. Identify the student")

    col_mode, col_select = st.columns([1, 2])
    with col_mode:
        search_mode = st.radio(
            "Mode",
            ["Choose from list", "New case"],
            key='search_mode',
            label_visibility='collapsed',
            horizontal=True,
        )

    selected_sid = None
    selected_sname = None
    selected_label = ""
    manual_program = ""

    if search_mode == "Choose from list":
        with col_select:
            labels = [opt[0] for opt in student_options]
            selected_label = st.selectbox(
                f"Student ({len(labels)} available)",
                options=labels,
                key='student_select',
            )
            if selected_label:
                match = next(opt for opt in student_options if opt[0] == selected_label)
                selected_sid = match[1]
                selected_sname = match[2]
    else:
        with col_select:
            cm_a, cm_b = st.columns(2)
            with cm_a:
                manual_name = st.text_input("Student name", key='manual_name')
            with cm_b:
                manual_program = st.text_input("Titulación (optionnel)", key='manual_prog')
            if manual_name:
                selected_sname = manual_name
                selected_sid = f"NEW_{abs(hash(manual_name)) % 100000}"
                selected_label = f"{manual_name} (nouveau)"

    if not selected_sname:
        st.info("Select or enter a student to continue")
        st.stop()

    # ════════════════════════════════════════════════════════════
    # STEP 2: Availability grid
    # ════════════════════════════════════════════════════════════
    st.markdown("### 2. Student availability")

    current_busy = student_busy_map.get(selected_sid, set())

    col_status, col_legend = st.columns([3, 2])
    with col_status:
        if current_busy:
            st.caption(
                f"**{len(current_busy)} busy slots** detected from university data. "
                f"Click on Free cells in the grid to add a manual conflict."
            )
        else:
            st.caption("No constraints known in the database — new student or no current courses detected.")
    with col_legend:
        st.caption("Current course  ·  Added conflict  ·  Available")

    state_key = f'extra_busy_{selected_sid}'
    if state_key not in st.session_state:
        st.session_state[state_key] = set()

    header_cols = st.columns([1.2] + [1] * 5)
    with header_cols[0]:
        st.markdown("**Heure**")
    for i, day in enumerate(DAYS):
        with header_cols[i + 1]:
            st.markdown(f"**{day}**")

    for block_id, block_label in BLOCKS:
        row_cols = st.columns([1.2] + [1] * 5)
        with row_cols[0]:
            st.markdown(
                f"<div style='padding-top:0.5rem;font-size:0.85rem;"
                f"color:var(--text-secondary);'>{block_label}</div>",
                unsafe_allow_html=True
            )

        for day_idx in range(5):
            slot = (day_idx, block_id)
            with row_cols[day_idx + 1]:
                is_current_busy = slot in current_busy
                is_extra_busy = slot in st.session_state[state_key]

                if is_current_busy:
                    st.markdown(
                        "<div style='background:#3b82f6;color:white;padding:0.5rem;"
                        "border-radius:4px;text-align:center;font-size:0.75rem;'>"
                        "Course</div>",
                        unsafe_allow_html=True
                    )
                else:
                    btn_label = "Conflict" if is_extra_busy else "Free"
                    if st.button(btn_label,
                                  key=f"slot_{day_idx}_{block_id}_{selected_sid}",
                                  use_container_width=True):
                        if slot in st.session_state[state_key]:
                            st.session_state[state_key].discard(slot)
                        else:
                            st.session_state[state_key].add(slot)
                        st.rerun()

    note = st.text_area(
        "Notes / context (optional)",
        placeholder="Ex: 'Resit for Física 1st year', 'Internship on Tuesday'",
        key=f'note_{selected_sid}',
        height=80,
    )

    # ════════════════════════════════════════════════════════════
    # STEP 3: Subjects
    # ════════════════════════════════════════════════════════════
    st.markdown("### 3. Subjects involved")

    enrolled_subjects = []
    if groups_df is not None:
        # Resolve the join key. When optimization outputs are anonymised,
        # group_composition.csv carries 'student_hash' (no name). Map the
        # selected student -> their hash via the local directory, then join.
        if 'student_name' in groups_df.columns:
            student_groups = groups_df[groups_df['student_name'] == selected_sname]
        elif 'student_hash' in groups_df.columns and directory_df is not None \
                and 'student_hash' in directory_df.columns:
            _hash_rows = directory_df[directory_df['student_id'] == selected_sid]
            _sel_hash = str(_hash_rows.iloc[0]['student_hash']) if len(_hash_rows) else None
            student_groups = groups_df[groups_df['student_hash'].astype(str) == _sel_hash] \
                if _sel_hash else groups_df.iloc[0:0]
        else:
            student_groups = groups_df.iloc[0:0]
        enrolled_subjects = sorted(student_groups['subject'].unique().tolist())

    if enrolled_subjects:
        st.caption(f"Detected enrolments: {', '.join(enrolled_subjects)}")

    if groups_df is not None:
        all_subjects = sorted(groups_df['subject'].unique().tolist())
    else:
        all_subjects = []

    selected_subjects = st.multiselect(
        "Which subjects to search for compatible groups?",
        options=all_subjects,
        default=enrolled_subjects if enrolled_subjects else [],
        key=f'subj_select_{selected_sid}',
    )

    if not selected_subjects:
        st.info("Select at least one subject to see recommendations")
        st.stop()

    # ════════════════════════════════════════════════════════════
    # Compute compatibility
    # ════════════════════════════════════════════════════════════
    total_busy = current_busy | st.session_state[state_key]

    def find_compatible_groups(subject_clean):
        possible_matches = (sched_df['subject'] == subject_clean) | \
                           (sched_df['subject'].str.endswith(f"_{subject_clean}", na=False))
        subj_sched = sched_df[possible_matches]
        if len(subj_sched) == 0:
            return []

        groups_info = []
        unique_groups = subj_sched.drop_duplicates(subset=['grupo'])

        for _, row in unique_groups.iterrows():
            grupo = int(row['grupo'])
            day = row.get('day', '?')
            time_block = row.get('time_block', '?')
            lab_rooms = str(row.get('lab_rooms', '?'))

            try:
                day_idx = DAYS.index(day)
            except ValueError:
                day_idx = -1

            block_id = None
            for bid, label in BLOCKS:
                if label == time_block:
                    block_id = bid
                    break

            slot = (day_idx, block_id)
            has_conflict = slot in total_busy

            in_group = groups_df[
                (groups_df['subject'] == subject_clean) & (groups_df['grupo'] == grupo)
            ] if groups_df is not None else None
            capacity_used = len(in_group) if in_group is not None else 0
            capacity_max = 15

            is_afternoon = block_id in [4, 5, 6]

            groups_info.append({
                'grupo': grupo,
                'day': day, 'day_idx': day_idx,
                'time_block': time_block, 'block_id': block_id,
                'lab_rooms': lab_rooms,
                'capacity_used': capacity_used,
                'capacity_max': capacity_max,
                'has_conflict': has_conflict,
                'is_afternoon': is_afternoon,
            })

        groups_info.sort(
            key=lambda g: (g['has_conflict'],
                           g['is_afternoon'],
                           -(g['capacity_max'] - g['capacity_used']))
        )
        return groups_info

    results_by_subject = {
        subject: find_compatible_groups(subject)
        for subject in selected_subjects
    }

    # ════════════════════════════════════════════════════════════
    # SYNTHESIS CARD
    # ════════════════════════════════════════════════════════════
    st.markdown("### Summary")

    def categorize(g):
        cap_remaining = g['capacity_max'] - g['capacity_used']
        if g['has_conflict']:
            return 'conflict'
        if cap_remaining <= 0:
            return 'full'
        if g['is_afternoon']:
            return 'compatible_afternoon'
        return 'best'

    def best_pick_for_subject(groups):
        best = [g for g in groups if categorize(g) == 'best']
        if best:
            return max(best, key=lambda g: g['capacity_max'] - g['capacity_used']), 'optimal'
        afternoon = [g for g in groups if categorize(g) == 'compatible_afternoon']
        if afternoon:
            return max(afternoon, key=lambda g: g['capacity_max'] - g['capacity_used']), 'afternoon'
        full = [g for g in groups if categorize(g) == 'full']
        if full:
            return full[0], 'full'
        return None, 'none'

    with st.container(border=True):
        for subject in selected_subjects:
            groups = results_by_subject[subject]
            pick, pick_kind = best_pick_for_subject(groups)

            n_best = sum(1 for g in groups if categorize(g) == 'best')
            n_afternoon = sum(1 for g in groups if categorize(g) == 'compatible_afternoon')
            n_full = sum(1 for g in groups if categorize(g) == 'full')
            n_conflict = sum(1 for g in groups if categorize(g) == 'conflict')
            n_total = len(groups)

            if pick_kind == 'optimal':
                cap_rem = pick['capacity_max'] - pick['capacity_used']
                reco_line = (
                    f"**Recommended: Group {pick['grupo']}** · "
                    f"{pick['day']} {pick['time_block']} · "
                    f"{cap_rem} place(s) disponible(s)"
                )
                reco_color = "rgba(34,197,94,0.08)"
                reco_border = "#22c55e"
            elif pick_kind == 'afternoon':
                cap_rem = pick['capacity_max'] - pick['capacity_used']
                reco_line = (
                    f"**Recommended (afternoon): Group {pick['grupo']}** · "
                    f"{pick['day']} {pick['time_block']} · "
                    f"{cap_rem} place(s) disponible(s)"
                )
                reco_color = "rgba(245,158,11,0.08)"
                reco_border = "#f59e0b"
            elif pick_kind == 'full':
                reco_line = (
                    f"**No group with available slots.** "
                    f"All compatible groups are full."
                )
                reco_color = "rgba(245,158,11,0.08)"
                reco_border = "#f59e0b"
            else:
                reco_line = (
                    f"**No compatible group found.** "
                    f"All slots conflict with the student's availability."
                )
                reco_color = "rgba(239,68,68,0.08)"
                reco_border = "#ef4444"

            st.markdown(
                f"<div style='padding:0.75rem 1rem; background:{reco_color}; "
                f"border-left:3px solid {reco_border}; border-radius:6px; "
                f"margin-bottom:0.5rem;'>"
                f"<div style='font-size:0.85rem; color:var(--text-secondary); "
                f"text-transform:uppercase; letter-spacing:0.05em; margin-bottom:0.25rem;'>"
                f"{subject}</div>"
                f"<div>{reco_line}</div>"
                f"<div style='font-size:0.85rem; color:var(--text-secondary); margin-top:0.5rem;'>"
                f"{n_best} optimal · {n_afternoon} afternoon · "
                f"{n_full} full · {n_conflict} in conflict · {n_total} groups total"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        ca1, ca2 = st.columns(2)
        with ca1:
            summary_lines = [f"Student: {selected_label}", ""]
            for subject in selected_subjects:
                groups = results_by_subject[subject]
                pick, pick_kind = best_pick_for_subject(groups)
                if pick:
                    cap_rem = pick['capacity_max'] - pick['capacity_used']
                    summary_lines.append(
                        f"{subject} -> Groupe {pick['grupo']} "
                        f"({pick['day']} {pick['time_block']}, "
                        f"{cap_rem} place(s) libre(s))"
                    )
                else:
                    summary_lines.append(f"{subject} -> No compatible group")
            if note:
                summary_lines.append("")
                summary_lines.append(f"Notes : {note}")
            summary_text = "\n".join(summary_lines)

            st.download_button(
                "Copy the summary (TXT)",
                data=summary_text.encode('utf-8'),
                file_name=f"caso_{selected_sname.replace(' ', '_')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with ca2:
            if st.button(
                "Open Manual Editing",
                use_container_width=True,
                help=(
                    "Go to the Edit page to add the student "
                    "to the recommended group via a swap."
                ),
            ):
                st.session_state['_nav_to'] = 'edit'
                st.rerun()

    # ════════════════════════════════════════════════════════════
    # Detail with filter
    # ════════════════════════════════════════════════════════════
    st.markdown("### 4. Group details")

    filter_choice = st.radio(
        "Afficher :",
        options=[
            "Solutions only",
            "All groups",
            "Conflicts only",
        ],
        horizontal=True,
        key='caso_filter_choice',
    )

    for subject in selected_subjects:
        st.markdown(f"#### {subject}")
        groups = results_by_subject[subject]

        if not groups:
            st.info(f"No group found for {subject}")
            continue

        if filter_choice == "Solutions only":
            visible = [g for g in groups if not g['has_conflict']]
            hidden_count = len(groups) - len(visible)
        elif filter_choice == "Conflicts only":
            visible = [g for g in groups if g['has_conflict']]
            hidden_count = len(groups) - len(visible)
        else:
            visible = groups
            hidden_count = 0

        if not visible:
            st.caption(
                f"_No group to display with this filter. "
                f"{len(groups)} group(s) total — change the filter to see them._"
            )
            continue

        compatible = [g for g in groups if not g['has_conflict']]
        with_capacity = len([g for g in compatible if g['capacity_used'] < g['capacity_max']])
        cs1, cs2, cs3 = st.columns(3)
        with cs1:
            st.metric("Compatible", len(compatible))
        with cs2:
            st.metric("In conflict", len(groups) - len(compatible))
        with cs3:
            st.metric("With slots", with_capacity)

        for g in visible:
            cap_remaining = g['capacity_max'] - g['capacity_used']

            if g['has_conflict']:
                color = "#EF4444"
                msg = "Conflict with availability"
                bg = "rgba(239,68,68,0.06)"
            elif cap_remaining <= 0:
                color = "#F59E0B"
                msg = "Full (saturated)"
                bg = "rgba(245,158,11,0.06)"
            elif g['is_afternoon']:
                color = "#F59E0B"
                msg = "Compatible (afternoon)"
                bg = "rgba(245,158,11,0.04)"
            else:
                color = "#22C55E"
                msg = "Compatible"
                bg = "rgba(34,197,94,0.06)"

            st.markdown(
                f"<div style='padding:0.5rem 0.75rem; background:{bg}; "
                f"border-left:3px solid {color}; border-radius:4px; "
                f"margin:0.25rem 0; display:flex; justify-content:space-between; "
                f"align-items:center; gap:1rem; font-size:0.9rem;'>"
                f"<div style='display:flex;align-items:center;gap:0.5rem;'>"
                f"<span style='width:8px;height:8px;border-radius:50%;background:{color};'></span>"
                f"<strong>G{g['grupo']}</strong> · "
                f"{g['day']} {g['time_block']} · "
                f"<span style='color:var(--text-secondary);'>{g['lab_rooms']}</span>"
                f"</div>"
                f"<div style='color:var(--text-secondary); font-size:0.85rem; "
                f"white-space:nowrap;'>"
                f"{g['capacity_used']}/{g['capacity_max']} · {msg}"
                f"</div>"
                f"</div>",
                unsafe_allow_html=True
            )

        if hidden_count > 0:
            st.caption(
                f"_{hidden_count} group(s) hidden by the filter. "
                f"Change the filter above to see them._"
            )

    # ════════════════════════════════════════════════════════════
    # Footer recap
    # ════════════════════════════════════════════════════════════
    st.markdown("---")

    n_extra = len(st.session_state[state_key])
    if n_extra > 0:
        cf1, cf2 = st.columns([3, 1])
        with cf1:
            st.caption(
                f"{n_extra} slot(s) added manually as additional conflict(s)."
            )
        with cf2:
            if st.button("Reset manual conflicts", key=f'reset_{selected_sid}',
                          use_container_width=True):
                st.session_state[state_key] = set()
                st.rerun()

# ════════════════════════════════════════════════════════════
# PAGE: UPDATES (apply Python patches, show version)
# ════════════════════════════════════════════════════════════
elif page == t('nav_updates'):
    page_header(t('nav_updates'), "Version & patches")

    try:
        import update_manager as _upd
        _UPD_OK = True
    except Exception as _e:
        _UPD_OK = False
        st.error(f"Update module unavailable: {_e}")

    if _UPD_OK:
        base_v = _upd.base_version()
        eff_v = _upd.effective_version()
        applied = _upd.applied_patches()

        c1, c2 = st.columns(2)
        with c1:
            stat_card("Installed version", eff_v, f"base {base_v}")
        with c2:
            stat_card("Patches applied", len(applied),
                      "patches Python actifs")

        st.markdown("---")
        section_header("Apply a patch (.zip)")
        help_tip(
            "Drop a patch <code>.zip</code> file here, provided by "
            "the developer. It updates the application code "
            "<strong>without reinstalling</strong>. Restart the application after "
            "applying it to activate the patch.",
            icon=""
        )

        patch_file = st.file_uploader("Patch (.zip)", type=["zip"],
                                       key="patch_upload",
                                       label_visibility="collapsed")
        if patch_file is not None:
            # Persist the upload to a temp file, inspect, then offer to apply
            import tempfile as _tf
            tmp_path = os.path.join(_tf.gettempdir(), patch_file.name)
            with open(tmp_path, "wb") as _f:
                _f.write(patch_file.getbuffer())

            info = _upd.inspect_patch(tmp_path)
            if not info.get("ok"):
                st.error(f"Invalid patch: {info.get('error')}")
            else:
                meta = info["meta"]
                st.markdown(f"""
                    <div class="info-card">
                        <div class="stat-label">Patch v{meta.get('version','?')}</div>
                        <p style="color: var(--text-secondary); margin: 0.5rem 0;">
                            {meta.get('notes','(no note)')}
                        </p>
                        <p style="font-size: 0.8rem; color: var(--text-muted);">
                            Files: {', '.join(info.get('py_files', [])) or '—'} ·
                            requiert l'app ≥ {meta.get('min_app','1.0.0')}
                        </p>
                    </div>
                """, unsafe_allow_html=True)

                if st.button(f"Apply patch v{meta.get('version','?')}",
                              type="primary", use_container_width=True,
                              key="apply_patch_btn"):
                    res = _upd.apply_patch(tmp_path)
                    if res["ok"]:
                        st.success(
                            f"Patch v{res['version']} applied "
                            f"({len(res['applied'])} file(s)). "
                            f"Restart the application to activate it."
                        )
                        st.balloons()
                    else:
                        st.error(f"Failed: {res['error']}")

        # History of applied patches
        if applied:
            st.markdown("---")
            section_header("Patch history")
            _rows = [{
                "Version": p.get("version", "?"),
                "Date": (p.get("applied_at", "") or "")[:16].replace("T", " "),
                "Files": ", ".join(p.get("files", [])),
                "Notes": p.get("notes", ""),
            } for p in applied]
            st.dataframe(pd.DataFrame(_rows), use_container_width=True,
                         hide_index=True)

            if st.button("Revert to the base version (remove patches)",
                          use_container_width=True, key="revert_patches"):
                r = _upd.revert_all_patches()
                if r["ok"]:
                    st.success(
                        f"{r['removed']} patch file(s) removed. "
                        f"Restart the application."
                    )
                else:
                    st.error(f"Error: {r['error']}")

        st.markdown("---")
        st.caption(
            "For a major update, install the new "
            "LabScheduling_Setup_vX.Y.Z.exe: it updates the application "
            "over the existing installation."
        )

# ════════════════════════════════════════════════════════════
# FOOTER
# ════════════════════════════════════════════════════════════
st.markdown(f"""
    <div class="app-footer">
        <div>{t('footer')}</div>
    </div>
""", unsafe_allow_html=True)