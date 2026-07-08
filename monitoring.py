"""monitoring.py — Page « Monitoring » (tour de contrôle) de LabScheduling.

Objectif (demande explicite) : centraliser, en UNE page, la vérification et le
suivi de tout le pipeline d'optimisation afin de pouvoir le mettre à l'échelle,
le contrôler et le maintenir dans la durée — en particulier vis-à-vis des
incohérences, de l'infaisabilité et de l'analyse de scénarios.

La page agrège, de façon défensive :
  • Contraintes & variables du modèle (estimées depuis le planning) ;
  • Entrées appliquées (config/user_config.json) et poids (cache LPA) ;
  • Détection d'un étudiant dupliqué entre groupes ;
  • Vérification que les labos planifiés respectent les contraintes (C1/C4/C5,
    double réservation étudiant) ;
  • Vérification des emplois du temps (étudiants ET professeurs : pas de
    double réservation) ;
  • Créneaux libres / occupés (salles, professeurs, étudiants) ;
  • Labos existants, considérations initiales, inscriptions/planification,
    fréquence, nombre de TP ;
  • Point de départ des erreurs / anomalies rencontrées, infaisabilité ;
  • Différents scénarios (historique des runs solveur).

Philosophie du projet (préservée partout) :
    « L'affectation est une donnée ; le système la valide, il ne la décide pas. »
Les collecteurs sont PURS (aucun appel Streamlit), DÉFENSIFS (ne lèvent jamais
d'exception sur des données indéterminées) et renvoient des dict/list simples,
donc unitairement testables. Seul ``render`` dessine l'interface Streamlit.
"""

from __future__ import annotations

import os
import json
from collections import defaultdict

import pandas as pd

# Convention métier : 1 crédit P = 5 séances (centralisée dans lab_constants).
try:
    from lab_constants import CREDIT_TO_SESSIONS, SESSIONS_PER_GROUP
except Exception:  # pragma: no cover - repli si l'import échoue
    CREDIT_TO_SESSIONS = 5
    SESSIONS_PER_GROUP = 5

# Chemins par défaut des sorties du pipeline (relatifs à la racine de travail).
DEFAULT_SCHEDULE_PATH = "outputs/optimization/optimized_schedule_v5.csv"
DEFAULT_GROUPS_PATH = "outputs/optimization/group_composition.csv"
DEFAULT_CONFIG_PATH = "config/user_config.json"
DEFAULT_SOLVER_STATS_PATH = "reports/solver_stats.json"
DEFAULT_REPORTS_DIR = "reports"


# =============================================================================
# Utilitaires d'E/S — toujours défensifs
# =============================================================================

def _read_json(path):
    """Lit un JSON et renvoie l'objet, ou None si absent / illisible / vide."""
    try:
        if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
            return None
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _read_csv(path):
    """Lit un CSV et renvoie un DataFrame, ou None si absent / illisible."""
    try:
        if not path or not os.path.exists(path):
            return None
        return pd.read_csv(path)
    except Exception:
        return None


def _safe_int(x):
    """Conversion best-effort en int (None en cas d'échec)."""
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


# =============================================================================
# 1) Entrées appliquées & poids
# =============================================================================

def load_inputs(path=DEFAULT_CONFIG_PATH):
    """Renvoie les paramètres utilisateur réellement appliqués (config saved).

    Structure renvoyée (toujours présente, ``available`` indique la validité) :
        {available, global, subjects, year_prefs, teachers, teacher_rules, meta}
    Dégrade proprement quand le fichier est vide ou absent.
    """
    cfg = _read_json(path)
    if not isinstance(cfg, dict) or not cfg:
        return {
            "available": False, "global": {}, "subjects": {},
            "year_prefs": {}, "teachers": {}, "teacher_rules": {}, "meta": {},
        }
    return {
        "available": True,
        "global": cfg.get("global", {}) or {},
        "subjects": cfg.get("subjects", {}) or {},
        "year_prefs": cfg.get("year_prefs", {}) or {},
        "teachers": cfg.get("teachers", {}) or {},
        "teacher_rules": cfg.get("teacher_rules", {}) or {},
        "meta": cfg.get("meta", {}) or {},
    }


def load_weights():
    """Renvoie les poids de pratiques et les cibles « attendues » par professeur.

    Lit le cache committé via lab_professor_assignment.load_weights_cache().
    Structure : {available, convention, generated_from, n_subjects,
                 expected_rows: [{subject, professor, groups, expected}], ...}.
    """
    out = {
        "available": False, "convention": "", "generated_from": "",
        "n_subjects": 0, "expected_rows": [], "theory": {},
    }
    try:
        import lab_professor_assignment as lpa
        cache = lpa.load_weights_cache()
    except Exception:
        cache = None
    if not isinstance(cache, dict):
        return out
    out["available"] = True
    out["convention"] = cache.get("convention", "1 crédit P = 5 séances")
    out["generated_from"] = cache.get("generated_from", "")
    expected = cache.get("expected", {}) or {}
    out["n_subjects"] = len(expected)
    rows = []
    for subject, lst in expected.items():
        for entry in lst:
            try:
                prof, groups, sessions = entry[0], entry[1], entry[2]
            except (IndexError, TypeError):
                continue
            rows.append({
                "subject": subject, "professor": prof,
                "groups": _safe_int(groups) or 0,
                "expected": _safe_int(sessions) or 0,
            })
    out["expected_rows"] = rows
    out["theory"] = cache.get("theory", {}) or {}
    return out


# =============================================================================
# 2) Modèle : variables & contraintes (estimées depuis le planning)
# =============================================================================

def estimate_model_size(schedule_df):
    """Estime la taille du modèle CP-SAT à partir du PLANNING produit.

    Le modèle CP-SAT réel est construit en mémoire dans pipeline.main() et n'est
    pas réutilisable ici ; on en fournit donc une ESTIMATION fidèle, dérivée du
    planning :
      • variables ≈ nombre de séances (1 variable « semaine » entière / séance) ;
      • familles de contraintes :
          - C1 : (matière, sem, jour, bloc) à ≥ 2 séances (matière non dédoublée),
          - C4 : (salle, sem, jour, bloc) à ≥ 2 séances (salle non dédoublée),
          - C5 : Σ (séances-1) par (matière, groupe) (ordre chronologique).
    Renvoie un dict ; ``note`` rappelle qu'il s'agit d'une estimation.
    """
    base = {
        "n_sessions": 0, "est_variables": 0,
        "c1_families": 0, "c4_families": 0, "c5_constraints": 0,
        "total_constraints_est": 0,
        "note": ("Estimation dérivée du planning produit ; le modèle CP-SAT réel "
                 "est construit dans pipeline.main()."),
    }
    if schedule_df is None or len(schedule_df) == 0:
        return base
    df = schedule_df
    n = int(len(df))
    base["n_sessions"] = n
    base["est_variables"] = n

    cols = set(df.columns)
    # C1 : matière en double sur un même créneau
    if {"subject", "semester", "day", "time_block"}.issubset(cols):
        g1 = df.groupby(["subject", "semester", "day", "time_block"]).size()
        base["c1_families"] = int((g1 >= 2).sum())
    # C4 : salle en double (après éclatement multi-salles)
    if {"lab_rooms", "semester", "day", "time_block"}.issubset(cols):
        rows = []
        for _, r in df.iterrows():
            for room in str(r.get("lab_rooms", "")).split(","):
                room = room.strip()
                if room and room.lower() != "nan":
                    rows.append((room, r.get("semester"), r.get("day"),
                                 r.get("time_block")))
        if rows:
            ex = pd.DataFrame(rows, columns=["room", "semester", "day", "time_block"])
            g4 = ex.groupby(["room", "semester", "day", "time_block"]).size()
            base["c4_families"] = int((g4 >= 2).sum())
    # C5 : ordre chronologique par (matière, groupe)
    if {"subject", "grupo"}.issubset(cols):
        c5 = 0
        for _key, grp in df.groupby(["subject", "grupo"]):
            k = int(len(grp))
            if k >= 2:
                c5 += k - 1
        base["c5_constraints"] = c5
    base["total_constraints_est"] = (
        base["c1_families"] + base["c4_families"] + base["c5_constraints"]
    )
    return base


# =============================================================================
# 3) Vérification des contraintes sur le planning produit
# =============================================================================

def collect_constraint_checks(schedule_df, groups_df):
    """Re-vérifie C1/C4/C5 et les conflits étudiants sur le planning produit.

    Réutilise reliability_metrics.detect_conflicts (source de vérité unique).
    Renvoie le dict de conflits enrichi d'un résumé « checks » lisible.
    """
    conflicts = {
        "c1_violations": 0, "c4_violations": 0, "c5_violations": 0,
        "student_conflicts": 0,
        "examples_c1": [], "examples_c4": [], "examples_c5": [],
    }
    try:
        import reliability_metrics as rm
        if schedule_df is not None and len(schedule_df) > 0:
            conflicts = rm.detect_conflicts(
                schedule_df,
                groups_df if groups_df is not None else pd.DataFrame())
    except Exception:
        pass

    checks = [
        {"code": "C1", "label": "Matière unique par créneau",
         "violations": int(conflicts.get("c1_violations", 0))},
        {"code": "C4", "label": "Salle unique par créneau",
         "violations": int(conflicts.get("c4_violations", 0))},
        {"code": "C5", "label": "Séances en ordre chronologique",
         "violations": int(conflicts.get("c5_violations", 0))},
        {"code": "STU", "label": "Étudiant jamais en double réservation",
         "violations": int(conflicts.get("student_conflicts", 0))},
    ]
    for c in checks:
        c["passed"] = c["violations"] == 0
    conflicts["checks"] = checks
    conflicts["all_passed"] = all(c["passed"] for c in checks)
    return conflicts


# =============================================================================
# 4) Étudiant dupliqué entre groupes (même matière)
# =============================================================================

def detect_student_group_duplicates(groups_df):
    """Détecte un étudiant inscrit dans PLUSIEURS groupes de la MÊME matière.

    Renvoie {count, examples:[{student, subject, groups:[...]}]}. Les placements
    marqués « is_override » (arbitrés manuellement) sont ignorés : ce sont des
    décisions assumées, pas des anomalies.
    """
    out = {"count": 0, "examples": []}
    if groups_df is None or len(groups_df) == 0:
        return out
    cols = set(groups_df.columns)
    if not {"subject", "grupo"}.issubset(cols):
        return out
    sid = "student_name" if "student_name" in cols else (
        "student_hash" if "student_hash" in cols else None)
    if sid is None:
        return out

    df = groups_df
    if "is_override" in cols:
        try:
            df = df[~df["is_override"].astype(bool)]
        except Exception:
            df = groups_df

    seen = defaultdict(set)  # (student, subject) -> set(groups)
    for _, r in df.iterrows():
        gi = _safe_int(r.get("grupo"))
        if gi is None:
            continue
        seen[(r.get(sid), r.get("subject"))].add(gi)

    dups = [(stu, subj, sorted(g)) for (stu, subj), g in seen.items() if len(g) > 1]
    out["count"] = len(dups)
    for stu, subj, g in dups[:20]:
        out["examples"].append({"student": str(stu), "subject": str(subj),
                                 "groups": g})
    return out


# =============================================================================
# 5) Conformité crédits (NB : sessions planifiées ≤ crédits attribués)
# =============================================================================

def collect_credit_compliance(schedule_df):
    """Compare, par (matière, professeur), les séances PLANIFIÉES aux séances
    ATTENDUES (= crédits P × 5), de façon strictement cohérente avec la
    « Teacher View ».

    NB métier : les séances attribuées à un professeur ne doivent PAS excéder
    ses crédits. On classe chaque ligne en :
        'over'  : planned > expected  (dépassement → à corriger) ;
        'under' : planned < expected  (sous le plafond → conforme) ;
        'ok'    : planned == expected (aligné).
    Renvoie {available, rows, n_ok, n_under, n_over, over_examples}.
    """
    out = {"available": False, "rows": [], "n_ok": 0, "n_under": 0,
           "n_over": 0, "over_examples": []}
    if schedule_df is None or len(schedule_df) == 0:
        return out
    if not {"subject", "grupo"}.issubset(set(schedule_df.columns)):
        return out
    try:
        import lab_professor_assignment as lpa
    except Exception:
        return out

    # 1) matière planifiée -> groupes réellement planifiés (clé canonique)
    subject_to_groups = {}
    canon_to_label = {}
    for s in schedule_df["subject"].dropna().unique():
        label = lpa._strip_semester_prefix(s) if hasattr(lpa, "_strip_semester_prefix") else s
        key = lpa.canonical_subject_key(label)
        canon_to_label.setdefault(key, label)
        grps = []
        for g in schedule_df[schedule_df["subject"] == s]["grupo"].dropna().unique():
            gi = _safe_int(g)
            if gi is not None:
                grps.append(gi)
        if grps:
            subject_to_groups.setdefault(key, set()).update(grps)
    subject_to_groups = {k: sorted(v) for k, v in subject_to_groups.items()}
    if not subject_to_groups:
        return out

    try:
        sgmap = lpa.assign_schedule_groups(None, subject_to_groups) or {}
        exp_df = lpa.expected_sessions(None)
    except Exception:
        return out

    expected_map = {}
    try:
        for _, r in exp_df.iterrows():
            expected_map[(r["subject_clean"], r["prof_name"])] = float(r["sessions_expected"])
    except Exception:
        expected_map = {}

    # 2) séances planifiées par (matière canonique, professeur)
    planned = defaultdict(int)
    # groupe -> prof par matière
    for s in schedule_df["subject"].dropna().unique():
        label = lpa._strip_semester_prefix(s) if hasattr(lpa, "_strip_semester_prefix") else s
        key = lpa.canonical_subject_key(label)
        sub = schedule_df[schedule_df["subject"] == s]
        for _, row in sub.iterrows():
            gi = _safe_int(row.get("grupo"))
            if gi is None:
                continue
            prof = sgmap.get((key, gi))
            if prof:
                planned[(key, prof)] += 1

    out["available"] = bool(planned)
    for (key, prof), n_planned in sorted(planned.items()):
        expected = expected_map.get((key, prof))
        label = canon_to_label.get(key, key)
        if expected is None:
            status = "no_target"
            delta = 0
        else:
            delta = int(round(n_planned - expected))
            if delta == 0:
                status = "ok"
                out["n_ok"] += 1
            elif delta < 0:
                status = "under"
                out["n_under"] += 1
            else:
                status = "over"
                out["n_over"] += 1
        row = {
            "subject": label, "professor": prof,
            "expected": int(expected) if expected is not None else None,
            "planned": int(n_planned), "delta": delta, "status": status,
        }
        out["rows"].append(row)
        if status == "over":
            out["over_examples"].append(row)
    return out


def collect_oversubscription(schedule_df):
    """Détecte les matières sur-souscrites (groupes planifiés > budget de crédits P).
    
    Croise les groupes réellement planifiés (schedule_df) avec le budget officiel
    (expected_sessions) pour identifier les matières dont le volume dépasse la
    capacité provisionnée. Marque les cas critiques (prof unique) et calcule
    l'écart capacitaire.
    
    Contexte : Les conflits horaires professeurs (collect_professor_conflicts) et
    dépassements de crédits (collect_credit_compliance) sont souvent la CONSÉQUENCE
    de la sur-souscription — ce collecteur identifie la cause racine.
    
    Returns:
        dict avec:
            count: nombre de matières sur-souscrites
            total_gap_groups: écart cumulé en groupes
            single_prof_count: nombre de matières à prof unique sur-souscrites
            items: [{subject, budget_groups, planned_groups, gap, n_professors,
                     professors, single_prof}, ...]
    """
    out = {"count": 0, "total_gap_groups": 0, "single_prof_count": 0, "items": []}
    if schedule_df is None or len(schedule_df) == 0:
        return out
    if "subject" not in schedule_df.columns or "grupo" not in schedule_df.columns:
        return out
    
    try:
        import lab_professor_assignment as lpa
    except Exception:
        return out
    
    # 1) Budget par matière (somme des groupes attendus par prof)
    try:
        exp_df = lpa.expected_sessions(None)
    except Exception:
        return out
    if exp_df is None or len(exp_df) == 0:
        return out
    
    budget_by_subject = {}
    for subj, grp in exp_df.groupby("subject_clean"):
        budget_by_subject[subj] = {
            "groups": int(grp["groups"].sum()),
            "professors": grp["prof_name"].tolist(),
        }
    
    # 2) Groupes planifiés par matière (canonique)
    planned_by_subject = {}
    for s in schedule_df["subject"].dropna().unique():
        label = lpa._strip_semester_prefix(s) if hasattr(lpa, "_strip_semester_prefix") else s
        key = lpa.canonical_subject_key(label)
        sub = schedule_df[schedule_df["subject"] == s]
        n_groups = sub["grupo"].nunique()
        if key not in planned_by_subject:
            planned_by_subject[key] = {"groups": 0, "label": label}
        planned_by_subject[key]["groups"] += n_groups
    
    # 3) Nombre de profs par matière (depuis weights)
    try:
        weights = lpa.subject_professor_weights(None)
    except Exception:
        weights = {}
    n_profs = {k: len(v) for k, v in weights.items()}
    
    # 4) Comparaison budget vs planifié
    all_subjects = set(list(budget_by_subject.keys()) + list(planned_by_subject.keys()))
    for subj in all_subjects:
        budget_info = budget_by_subject.get(subj, {"groups": 0, "professors": []})
        planned_info = planned_by_subject.get(subj, {"groups": 0, "label": subj})
        
        budget_g = budget_info["groups"]
        planned_g = planned_info["groups"]
        gap = planned_g - budget_g
        
        if gap <= 0:
            continue  # pas de sur-souscription
        
        profs = budget_info["professors"]
        np = n_profs.get(subj, len(profs))
        single = (np == 1)
        
        out["count"] += 1
        out["total_gap_groups"] += gap
        if single:
            out["single_prof_count"] += 1
        
        out["items"].append({
            "subject": planned_info.get("label", subj),
            "budget_groups": budget_g,
            "planned_groups": planned_g,
            "gap": gap,
            "n_professors": np,
            "professors": profs,
            "single_prof": single,
        })
    
    # Tri par gap décroissant
    out["items"] = sorted(out["items"], key=lambda x: -x["gap"])
    return out


# =============================================================================
# 6) Emplois du temps : double réservation des professeurs
# =============================================================================

def collect_professor_conflicts(schedule_df):
    """Vérifie qu'un professeur n'est jamais affecté à 2 séances simultanées.

    Affecte d'abord un professeur responsable à chaque séance (cohérent avec la
    Teacher View) puis recherche, par (sem, semaine, jour, bloc), un professeur
    présent sur ≥ 2 séances. Renvoie {count, examples:[...]}.
    """
    out = {"count": 0, "examples": []}
    if schedule_df is None or len(schedule_df) == 0:
        return out
    needed = {"subject", "grupo", "semester", "week", "day", "time_block"}
    if not needed.issubset(set(schedule_df.columns)):
        return out

    df = schedule_df.copy()
    # Récupère / calcule la colonne professeur
    if "professor" not in df.columns:
        try:
            import lab_professor_assignment as lpa
            df["professor"] = lpa.assign_professors_to_schedule_df(df)
        except Exception:
            df["professor"] = ""

    slot_profs = defaultdict(lambda: defaultdict(set))  # prof -> slot -> {(subj,grupo)}
    for _, r in df.iterrows():
        prof = str(r.get("professor", "") or "").strip()
        if not prof:
            continue
        # un libellé multi-professeurs ("A; B") n'est pas un conflit individuel
        if ";" in prof:
            continue
        slot = (_safe_int(r.get("semester")), _safe_int(r.get("week")),
                r.get("day"), r.get("time_block"))
        gi = _safe_int(r.get("grupo"))
        slot_profs[prof][slot].add((r.get("subject"), gi))

    for prof, slots in slot_profs.items():
        for slot, sg in slots.items():
            if len(sg) > 1:
                out["count"] += 1
                if len(out["examples"]) < 20:
                    out["examples"].append({
                        "professor": prof,
                        "semester": slot[0], "week": slot[1],
                        "day": slot[2], "time_block": slot[3],
                        "sessions": [f"{s} G{g}" for s, g in sorted(
                            sg, key=lambda x: (str(x[0]), x[1] or 0))],
                    })
    return out


# =============================================================================
# 7) Créneaux libres / occupés (salles, professeurs, étudiants)
# =============================================================================

def collect_free_busy(schedule_df, groups_df):
    """Synthèse occupation / disponibilité pour salles, professeurs, étudiants.

    • Salles      : reliability_metrics.compute_room_occupancy (occupation %, statut) ;
    • Professeurs : nombre de séances par professeur (charge) ;
    • Étudiants   : reliability_metrics.compute_student_overload (surcharge / semaine).
    """
    out = {"rooms": [], "professors": [], "students": {}}
    if schedule_df is None or len(schedule_df) == 0:
        return out

    # --- Salles ---
    try:
        import reliability_metrics as rm
        out["rooms"] = rm.compute_room_occupancy(schedule_df)
    except Exception:
        out["rooms"] = []

    # --- Professeurs (charge en séances) ---
    df = schedule_df
    if "professor" not in df.columns:
        try:
            import lab_professor_assignment as lpa
            df = schedule_df.copy()
            df["professor"] = lpa.assign_professors_to_schedule_df(df)
        except Exception:
            df = schedule_df
    if "professor" in df.columns:
        load = defaultdict(int)
        for p in df["professor"].tolist():
            p = str(p or "").strip()
            if p:
                load[p] += 1
        out["professors"] = [
            {"professor": p, "sessions": n}
            for p, n in sorted(load.items(), key=lambda kv: -kv[1])
        ]

    # --- Étudiants (surcharge hebdomadaire) ---
    try:
        import reliability_metrics as rm
        if groups_df is not None and len(groups_df) > 0:
            out["students"] = rm.compute_student_overload(schedule_df, groups_df)
    except Exception:
        out["students"] = {}
    return out


# =============================================================================
# 8) Labos existants / fréquence / nombre de TP / inscriptions
# =============================================================================

def collect_existing_labs(schedule_df):
    """Synthèse des labos planifiés : nb matières (TP), groupes, séances, et un
    détail par matière (groupes, séances, fréquence = séances/groupe).
    """
    out = {"n_subjects": 0, "n_groups": 0, "n_sessions": 0, "per_subject": []}
    if schedule_df is None or len(schedule_df) == 0:
        return out
    cols = set(schedule_df.columns)
    out["n_sessions"] = int(len(schedule_df))
    if "subject" in cols:
        out["n_subjects"] = int(schedule_df["subject"].nunique())
    if {"subject", "grupo"}.issubset(cols):
        out["n_groups"] = int(
            schedule_df.groupby(["subject", "grupo"]).ngroups)
        for subj, grp in schedule_df.groupby("subject"):
            n_groups = int(grp["grupo"].nunique())
            n_sessions = int(len(grp))
            out["per_subject"].append({
                "subject": str(subj),
                "groups": n_groups,
                "sessions": n_sessions,
                "sessions_per_group": round(n_sessions / n_groups, 2) if n_groups else 0,
            })
        out["per_subject"].sort(key=lambda x: x["subject"])
    return out


def collect_frequency(schedule_df):
    """Distribution des séances (jour / bloc / semaine) + score d'équilibre."""
    try:
        import reliability_metrics as rm
        if schedule_df is not None and len(schedule_df) > 0:
            return rm.compute_distribution_metrics(schedule_df)
    except Exception:
        pass
    return {"by_day": {}, "by_block": {}, "by_week": {},
            "peak_day": None, "peak_week": None, "balance_score": 0}


def collect_enrollment(groups_df):
    """Inscriptions / planification : nb étudiants uniques, nb inscriptions
    (étudiant × matière), répartition par programme, nb d'overrides manuels.
    """
    out = {"n_students": 0, "n_enrolments": 0, "by_program": {}, "n_overrides": 0}
    if groups_df is None or len(groups_df) == 0:
        return out
    cols = set(groups_df.columns)
    sid = "student_name" if "student_name" in cols else (
        "student_hash" if "student_hash" in cols else None)
    out["n_enrolments"] = int(len(groups_df))
    if sid:
        out["n_students"] = int(groups_df[sid].nunique())
    if "program" in cols:
        try:
            out["by_program"] = groups_df["program"].value_counts().to_dict()
        except Exception:
            out["by_program"] = {}
    if "is_override" in cols:
        try:
            out["n_overrides"] = int(groups_df["is_override"].astype(bool).sum())
        except Exception:
            out["n_overrides"] = 0
    return out


# =============================================================================
# 9) Scénarios (runs solveur) & infaisabilité / point de départ des erreurs
# =============================================================================

def load_solver_runs(path=DEFAULT_SOLVER_STATS_PATH):
    """Renvoie la liste des runs solveur enregistrés (ou [] si absent)."""
    data = _read_json(path)
    return data if isinstance(data, list) else []


def summarize_solver_runs(runs):
    """Synthèse des runs solveur (= scénarios) : comptes par statut, totaux,
    objectif/temps moyens, runs infaisables isolés.
    """
    out = {
        "n_runs": 0, "by_status": {}, "total_sessions": 0,
        "total_wall_time_s": 0.0, "infeasible_runs": [], "runs": [],
    }
    if not isinstance(runs, list) or not runs:
        return out
    out["n_runs"] = len(runs)
    out["runs"] = runs
    for r in runs:
        status = str(r.get("status", "?"))
        out["by_status"][status] = out["by_status"].get(status, 0) + 1
        out["total_sessions"] += _safe_int(r.get("n_sessions")) or 0
        try:
            out["total_wall_time_s"] += float(r.get("wall_time_s", 0) or 0)
        except (TypeError, ValueError):
            pass
        if status == "INFEASIBLE":
            out["infeasible_runs"].append(r)
    out["total_wall_time_s"] = round(out["total_wall_time_s"], 2)
    return out


def collect_infeasibility(reports_dir=DEFAULT_REPORTS_DIR,
                          solver_stats_path=DEFAULT_SOLVER_STATS_PATH):
    """« Point de départ des erreurs » : agrège les diagnostics d'infaisabilité.

    Combine :
      • les fichiers reports/infeasibility_S*.txt (goulots physiques détectés
        par pipeline.diagnose_infeasibility) ;
      • les runs solveur au statut INFEASIBLE.
    Renvoie {files:[{name, semester, preview, n_lines}], infeasible_runs:[...]}.
    """
    out = {"files": [], "infeasible_runs": []}
    try:
        if reports_dir and os.path.isdir(reports_dir):
            for fname in sorted(os.listdir(reports_dir)):
                if fname.startswith("infeasibility_") and fname.endswith(".txt"):
                    fpath = os.path.join(reports_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read()
                    except Exception:
                        content = ""
                    sem = ""
                    base = fname[len("infeasibility_"):-len(".txt")]
                    if base.upper().startswith("S"):
                        sem = base
                    out["files"].append({
                        "name": fname, "semester": sem,
                        "preview": content[:1500],
                        "n_lines": content.count("\n") + 1 if content else 0,
                    })
    except Exception:
        pass
    out["infeasible_runs"] = summarize_solver_runs(
        load_solver_runs(solver_stats_path)).get("infeasible_runs", [])
    return out


# =============================================================================
# Agrégateur — tour de contrôle (résumé d'anomalies)
# =============================================================================

def build_report(schedule_df, groups_df, config_path=DEFAULT_CONFIG_PATH,
                 solver_stats_path=DEFAULT_SOLVER_STATS_PATH,
                 reports_dir=DEFAULT_REPORTS_DIR):
    """Construit le rapport complet de monitoring + un résumé d'anomalies.

    ``anomalies`` est la synthèse « tour de contrôle » : une liste de
    {severity, category, message} (severity ∈ {error, warning, info}).
    """
    report = {
        "inputs": load_inputs(config_path),
        "weights": load_weights(),
        "model_size": estimate_model_size(schedule_df),
        "constraints": collect_constraint_checks(schedule_df, groups_df),
        "student_duplicates": detect_student_group_duplicates(groups_df),
        "credit_compliance": collect_credit_compliance(schedule_df),
        "oversubscription": collect_oversubscription(schedule_df),
        "professor_conflicts": collect_professor_conflicts(schedule_df),
        "free_busy": collect_free_busy(schedule_df, groups_df),
        "existing_labs": collect_existing_labs(schedule_df),
        "frequency": collect_frequency(schedule_df),
        "enrollment": collect_enrollment(groups_df),
        "solver": summarize_solver_runs(load_solver_runs(solver_stats_path)),
        "infeasibility": collect_infeasibility(reports_dir, solver_stats_path),
    }

    anomalies = []

    def add(sev, cat, msg):
        anomalies.append({"severity": sev, "category": cat, "message": msg})

    c = report["constraints"]
    if c.get("c1_violations"):
        add("error", "Contraintes", f"{c['c1_violations']} violation(s) C1 (matière en double)")
    if c.get("c4_violations"):
        add("error", "Contraintes", f"{c['c4_violations']} violation(s) C4 (salle en double)")
    if c.get("c5_violations"):
        add("error", "Contraintes", f"{c['c5_violations']} violation(s) C5 (ordre chronologique)")
    if c.get("student_conflicts"):
        add("error", "Emplois du temps",
            f"{c['student_conflicts']} étudiant(s) en double réservation")

    if report["professor_conflicts"].get("count"):
        add("error", "Emplois du temps",
            f"{report['professor_conflicts']['count']} conflit(s) horaire professeur")

    if report["student_duplicates"].get("count"):
        add("warning", "Inscriptions",
            f"{report['student_duplicates']['count']} étudiant(s) dupliqué(s) entre groupes")

    cc = report["credit_compliance"]
    if cc.get("n_over"):
        add("error", "Crédits",
            f"{cc['n_over']} professeur(s) dépassant leurs crédits (séances > attendues)")

    os = report["oversubscription"]
    if os.get("count"):
        msg = f"{os['count']} matière(s) sur-souscrite(s) (groupes planifiés > budget)"
        if os.get("single_prof_count"):
            msg += f" — dont {os['single_prof_count']} à prof unique (critique)"
        add("warning", "Capacité", msg)

    rooms_crit = [r for r in report["free_busy"].get("rooms", [])
                  if r.get("status") == "critical"]
    if rooms_crit:
        add("warning", "Salles", f"{len(rooms_crit)} salle(s) en sur-occupation (> 90%)")

    if report["infeasibility"].get("files") or report["infeasibility"].get("infeasible_runs"):
        n = len(report["infeasibility"].get("files", [])) + \
            len(report["infeasibility"].get("infeasible_runs", []))
        add("error", "Infaisabilité",
            f"{n} diagnostic(s) d'infaisabilité détecté(s) — voir le point de départ des erreurs")

    if not report["inputs"].get("available"):
        add("info", "Entrées",
            "Aucune configuration utilisateur enregistrée (paramètres par défaut appliqués)")

    report["anomalies"] = anomalies
    report["n_errors"] = sum(1 for a in anomalies if a["severity"] == "error")
    report["n_warnings"] = sum(1 for a in anomalies if a["severity"] == "warning")
    report["n_infos"] = sum(1 for a in anomalies if a["severity"] == "info")
    return report


# =============================================================================
# Rendu Streamlit
# =============================================================================

def render(st, helpers=None, t=None):
    """Dessine la page Monitoring dans Streamlit.

    helpers : dict optionnel {page_header, section_header, stat_card, safe_error}.
              Des replis simples sont fournis si absents.
    t       : fonction de traduction optionnelle (non requise ; la page est en
              anglais comme le reste de l'application).
    """
    helpers = helpers or {}
    page_header = helpers.get("page_header") or (lambda title, sub="": st.title(title))
    section_header = helpers.get("section_header") or (lambda title: st.subheader(title))
    stat_card = helpers.get("stat_card") or (
        lambda label, value, desc="": st.metric(label, value, desc))
    safe_error = helpers.get("safe_error") or (
        lambda msg, exc=None, **k: st.error(f"{msg}: {exc}" if exc else msg))

    page_header(
        "Monitoring — control tower",
        "Centralized verification of the optimization pipeline: constraints, "
        "inputs, weights, conflicts, free/busy slots, infeasibility and scenarios."
    )

    # ---- Chargement défensif des sorties du pipeline ----
    schedule_df = _read_csv(DEFAULT_SCHEDULE_PATH)
    groups_df = _read_csv(DEFAULT_GROUPS_PATH)

    if schedule_df is None or len(schedule_df) == 0:
        st.warning("**Pipeline not executed yet** — run the optimization to "
                   "populate the monitoring dashboard.")
        try:
            if st.button("← Go to Optimize", type="primary"):
                st.session_state["_nav_to"] = "optimize"
                st.rerun()
        except Exception:
            pass
        # On affiche tout de même les entrées/poids/scénarios disponibles.
        _render_inputs_weights(st, section_header, stat_card)
        _render_scenarios(st, section_header, stat_card)
        _render_infeasibility(st, section_header)
        return

    try:
        with st.spinner("Collecting monitoring data…"):
            report = build_report(schedule_df, groups_df)
    except Exception as e:
        safe_error("Unable to build the monitoring report", e)
        return

    _render_overview(st, section_header, stat_card, report)
    _render_model(st, section_header, stat_card, report)
    _render_constraints(st, section_header, report)
    _render_emploi_du_temps(st, section_header, report)
    _render_credit_compliance(st, section_header, stat_card, report)
    _render_oversubscription(st, section_header, stat_card, report)
    _render_free_busy(st, section_header, report)
    _render_existing_labs(st, section_header, stat_card, report)
    _render_frequency(st, section_header, report)
    _render_enrollment(st, section_header, stat_card, report)
    _render_inputs_weights(st, section_header, stat_card)
    _render_scenarios(st, section_header, stat_card)
    _render_infeasibility(st, section_header)


# ---- sous-rendus (gardent render() lisible) --------------------------------

def _badge_html(text, kind):
    colors = {"error": "#ef4444", "warning": "#f59e0b",
              "info": "#3b82f6", "ok": "#22c55e"}
    c = colors.get(kind, "#64748b")
    return (f"<span style='display:inline-block;padding:2px 10px;border-radius:10px;"
            f"background:{c}1a;color:{c};font-size:0.8rem;font-weight:600;"
            f"margin:2px 4px 2px 0'>{text}</span>")


def _render_overview(st, section_header, stat_card, report):
    section_header("Control-tower overview")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Errors", report.get("n_errors", 0), "blocking anomalies")
    with c2:
        stat_card("Warnings", report.get("n_warnings", 0), "to review")
    with c3:
        stat_card("Sessions", report["existing_labs"].get("n_sessions", 0),
                  "scheduled labs")
    with c4:
        stat_card("Subjects (TP)", report["existing_labs"].get("n_subjects", 0),
                  "practical courses")

    anomalies = report.get("anomalies", [])
    if not anomalies:
        st.success("No anomaly detected — the plan passes every monitoring check.")
        return
    order = {"error": 0, "warning": 1, "info": 2}
    for a in sorted(anomalies, key=lambda x: order.get(x["severity"], 9)):
        line = f"**[{a['category']}]** {a['message']}"
        if a["severity"] == "error":
            st.error(line)
        elif a["severity"] == "warning":
            st.warning(line)
        else:
            st.info(line)


def _render_model(st, section_header, stat_card, report):
    section_header("Model — variables & constraints (estimated)")
    m = report["model_size"]
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        stat_card("Variables (est.)", m.get("est_variables", 0), "≈ 1 / session")
    with c2:
        stat_card("C1 families", m.get("c1_families", 0), "subject / slot")
    with c3:
        stat_card("C4 families", m.get("c4_families", 0), "room / slot")
    with c4:
        stat_card("C5 constraints", m.get("c5_constraints", 0), "chronological order")
    st.caption(m.get("note", ""))


def _render_constraints(st, section_header, report):
    section_header("Constraint verification (post-solve)")
    c = report["constraints"]
    rows = []
    for chk in c.get("checks", []):
        rows.append({
            "Constraint": f"{chk['code']} — {chk['label']}",
            "Status": "OK" if chk["passed"] else "VIOLATION",
            "Violations": chk["violations"],
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if c.get("all_passed"):
        st.success("All constraints satisfied on the produced schedule.")
    else:
        for key, title in (("examples_c1", "C1"), ("examples_c4", "C4"),
                           ("examples_c5", "C5")):
            ex = c.get(key) or []
            if ex:
                with st.expander(f"{title} — example violations ({len(ex)})"):
                    st.dataframe(pd.DataFrame(ex), use_container_width=True,
                                 hide_index=True)


def _render_emploi_du_temps(st, section_header, report):
    section_header("Timetables — students & professors")
    c = report["constraints"]
    pc = report["professor_conflicts"]
    dup = report["student_duplicates"]
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Student double-bookings", c.get("student_conflicts", 0))
    with col2:
        st.metric("Professor conflicts", pc.get("count", 0))
    with col3:
        st.metric("Students duplicated across groups", dup.get("count", 0))

    if pc.get("examples"):
        with st.expander(f"Professor schedule conflicts ({pc['count']})"):
            st.dataframe(pd.DataFrame(pc["examples"]),
                         use_container_width=True, hide_index=True)
    if dup.get("examples"):
        with st.expander(f"Students in several groups of the same subject ({dup['count']})"):
            rows = [{"Student": e["student"], "Subject": e["subject"],
                     "Groups": ", ".join(f"G{g}" for g in e["groups"])}
                    for e in dup["examples"]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_credit_compliance(st, section_header, stat_card, report):
    section_header("Credit compliance (planned ≤ assigned credits)")
    cc = report["credit_compliance"]
    if not cc.get("available"):
        st.info("Credit source unavailable — per-professor compliance cannot be computed.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Within ceiling", cc.get("n_ok", 0) + cc.get("n_under", 0),
                  "planned ≤ expected (compliant)")
    with c2:
        stat_card("Over budget", cc.get("n_over", 0),
                  "planned > expected (to review)")
    with c3:
        stat_card("Exact match", cc.get("n_ok", 0), "planned = expected")
    st.caption("NB: sessions assigned to a professor must not exceed their P "
               "credits (1 credit = 5 sessions). Over-budget rows are flagged "
               "in red in the Teacher View Excel sheet as well.")
    if cc.get("over_examples"):
        with st.expander(f"Professors over budget ({cc['n_over']})", expanded=True):
            rows = [{"Professor": r["professor"], "Subject": r["subject"],
                     "Expected": r["expected"], "Planned": r["planned"],
                     "Δ": f"+{r['delta']}"} for r in cc["over_examples"]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    if cc.get("rows"):
        with st.expander("Full per-professor breakdown"):
            rows = [{"Professor": r["professor"], "Subject": r["subject"],
                     "Expected": r["expected"], "Planned": r["planned"],
                     "Δ": r["delta"], "Status": r["status"]}
                    for r in cc["rows"]]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_oversubscription(st, section_header, stat_card, report):
    """Affiche les matières sur-souscrites (groupes planifiés > budget crédits P).
    
    Aide à diagnostiquer la CAUSE RACINE des conflits professeurs et dépassements
    de crédits : quand la demande étudiante dépasse la capacité provisionnée,
    les professeurs sont mécaniquement sur-sollicités.
    """
    section_header("Over-subscription (root cause of conflicts & credit overruns)")
    os = report["oversubscription"]
    
    if not os.get("count"):
        st.success("✓ No over-subscribed courses — all scheduled groups fit within P credit budget.")
        st.caption("Over-subscription occurs when enrollment demand generates more lab groups "
                   "than provisioned P credits can support. When absent, professor conflicts "
                   "and credit overruns (if any) stem from other causes (e.g., scheduling constraints).")
        return
    
    # Métriques principales
    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Over-subscribed courses", os.get("count", 0),
                  "groups planned > budget")
    with c2:
        stat_card("Single-prof critical", os.get("single_prof_count", 0),
                  "unavoidable without hiring/provisioning")
    with c3:
        stat_card("Total capacity gap", os.get("total_gap_groups", 0),
                  "extra groups beyond budget")
    
    st.warning(
        f"**{os['count']} courses are over-subscribed**: student enrollment has generated "
        f"more groups than the P credit budget supports. This is the **root cause** of "
        f"professor conflicts and credit overruns detected elsewhere in this report."
    )
    
    st.caption(
        "**Context:** The solver prioritizes placing all enrolled students (pedagogical objective). "
        "Professor assignment is computed *post-hoc* proportionally to P credits. When scheduled "
        "groups exceed budget, professors are mechanically over-allocated → conflicts + overruns."
    )
    
    # Tableau détaillé
    with st.expander(f"Detailed breakdown — {os['count']} over-subscribed courses", expanded=True):
        rows = []
        for item in os.get("items", []):
            profs_str = ", ".join(item.get("professors", [])[:3])
            if len(item.get("professors", [])) > 3:
                profs_str += f" (+{len(item['professors']) - 3})"
            
            flag = "⚠️ SINGLE PROF" if item.get("single_prof") else ""
            rows.append({
                "Course": item["subject"],
                "Budget (groups)": item["budget_groups"],
                "Scheduled (groups)": item["planned_groups"],
                "Gap": f"+{item['gap']}",
                "# Professors": item["n_professors"],
                "Professors": profs_str,
                "Critical": flag,
            })
        
        df_os = pd.DataFrame(rows)
        st.dataframe(df_os, use_container_width=True, hide_index=True)
    
    # Guidance actionnable
    st.info(
        "**Next steps:**\n"
        f"- **Priority:** {os.get('single_prof_count', 0)} single-professor courses require "
        "capacity intervention (hire additional faculty or provision extra P credits).\n"
        f"- **Distributable:** {os['count'] - os.get('single_prof_count', 0)} multi-professor "
        "courses may benefit from load rebalancing or additional provisioning.\n"
        "- **Administrative action:** Use this table to request budget allocation for the identified gap."
    )


def _render_free_busy(st, section_header, report):
    section_header("Free / busy slots (rooms · professors · students)")
    fb = report["free_busy"]

    rooms = fb.get("rooms", [])
    if rooms:
        st.markdown("**Rooms — occupancy**")
        rows = [{"Room": r["room"], "Semester": r["semester"],
                 "Used": r["sessions_used"], "Available": r["slots_available"],
                 "Occupancy %": r["occupancy_pct"], "Status": r["status"]}
                for r in rooms]
        df_rooms = pd.DataFrame(rows)
        st.dataframe(df_rooms, use_container_width=True, hide_index=True)
        try:
            chart = df_rooms.set_index("Room")["Occupancy %"]
            st.bar_chart(chart)
        except Exception:
            pass

    profs = fb.get("professors", [])
    if profs:
        st.markdown("**Professors — teaching load (busy sessions)**")
        df_p = pd.DataFrame(profs).rename(columns={"professor": "Professor",
                                                    "sessions": "Sessions"})
        st.dataframe(df_p, use_container_width=True, hide_index=True)

    students = fb.get("students", {})
    if students:
        st.markdown("**Students — weekly load**")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Overloaded students", students.get("overloaded_count", 0),
                      help="> 3 labs in the same week")
        with c2:
            st.metric("Max labs observed / week", students.get("max_labs_observed", 0))
        if students.get("examples"):
            with st.expander("Overloaded student examples"):
                st.dataframe(pd.DataFrame(students["examples"]),
                             use_container_width=True, hide_index=True)


def _render_existing_labs(st, section_header, stat_card, report):
    section_header("Existing labs — number of practical courses & frequency")
    el = report["existing_labs"]
    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Practical courses", el.get("n_subjects", 0), "distinct subjects")
    with c2:
        stat_card("Groups", el.get("n_groups", 0), "subject × group")
    with c3:
        stat_card("Sessions", el.get("n_sessions", 0), "total scheduled")
    if el.get("per_subject"):
        rows = [{"Subject": r["subject"], "Groups": r["groups"],
                 "Sessions": r["sessions"],
                 "Sessions / group": r["sessions_per_group"]}
                for r in el["per_subject"]]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_frequency(st, section_header, report):
    section_header("Frequency — distribution of sessions")
    fr = report["frequency"]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Peak day", str(fr.get("peak_day") or "—"))
    with c2:
        st.metric("Peak week", str(fr.get("peak_week") or "—"))
    with c3:
        st.metric("Balance score", f"{fr.get('balance_score', 0)}/100")
    by_day = fr.get("by_day", {})
    if by_day:
        try:
            st.markdown("**Sessions per day**")
            st.bar_chart(pd.Series(by_day))
        except Exception:
            pass
    by_week = fr.get("by_week", {})
    if by_week:
        try:
            st.markdown("**Sessions per week**")
            st.bar_chart(pd.Series(by_week))
        except Exception:
            pass


def _render_enrollment(st, section_header, stat_card, report):
    section_header("Enrollment & planning")
    en = report["enrollment"]
    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Students", en.get("n_students", 0), "unique")
    with c2:
        stat_card("Enrolments", en.get("n_enrolments", 0), "student × subject")
    with c3:
        stat_card("Manual overrides", en.get("n_overrides", 0), "arbitrated placements")
    by_prog = en.get("by_program", {})
    if by_prog:
        try:
            st.markdown("**Enrolments per program**")
            st.bar_chart(pd.Series(by_prog))
        except Exception:
            pass


def _render_inputs_weights(st, section_header, stat_card):
    section_header("Applied inputs & weights")
    inputs = load_inputs()
    if inputs.get("available"):
        g = inputs.get("global", {})
        st.markdown("**Applied parameters (initial considerations)**")
        rows = [{"Parameter": k, "Value": v} for k, v in g.items()]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        yp = inputs.get("year_prefs", {})
        if yp:
            st.caption("Year preferences: " + ", ".join(
                f"{k} = {v}" for k, v in yp.items()))
        n_overrides = len(inputs.get("subjects", {}) or {})
        n_teachers = len(inputs.get("teachers", {}) or {})
        n_rules = len(inputs.get("teacher_rules", {}) or {})
        c1, c2, c3 = st.columns(3)
        with c1:
            stat_card("Subject overrides", n_overrides, "customized subjects")
        with c2:
            stat_card("Teacher constraints", n_teachers, "unavailabilities")
        with c3:
            stat_card("Teacher rules", n_rules, "custom rules")
        meta = inputs.get("meta", {})
        if meta.get("saved_at"):
            st.caption(f"Configuration saved at {meta.get('saved_at')} "
                       f"(app {meta.get('app_version', '?')}).")
    else:
        st.info("No user configuration saved — default parameters are applied.")

    weights = load_weights()
    if weights.get("available"):
        st.markdown("**Professor weights & expected sessions (source-derived)**")
        st.caption(f"Convention: {weights.get('convention')}. "
                   f"{weights.get('n_subjects', 0)} subject(s) with P credits.")
        rows = weights.get("expected_rows", [])
        if rows:
            df = pd.DataFrame(rows).rename(columns={
                "subject": "Subject", "professor": "Professor",
                "groups": "Groups", "expected": "Expected sessions"})
            with st.expander(f"Expected sessions per professor ({len(rows)} rows)"):
                st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Weights cache unavailable — per-professor targets cannot be shown.")


def _render_scenarios(st, section_header, stat_card):
    section_header("Scenarios — solver runs")
    summary = summarize_solver_runs(load_solver_runs())
    if not summary.get("n_runs"):
        st.info("No solver run recorded yet. Run the optimization to populate scenarios.")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        stat_card("Runs", summary["n_runs"], "recorded scenarios")
    with c2:
        stat_card("Total sessions", summary["total_sessions"], "across runs")
    with c3:
        stat_card("Total solve time", f"{summary['total_wall_time_s']}s", "wall clock")
    if summary.get("by_status"):
        st.markdown(" ".join(
            _badge_html(f"{k}: {v}",
                        "ok" if k in ("OPTIMAL", "FEASIBLE") else
                        "error" if k == "INFEASIBLE" else "warning")
            for k, v in summary["by_status"].items()), unsafe_allow_html=True)
    runs = summary.get("runs", [])
    if runs:
        try:
            df = pd.DataFrame(runs)
            st.dataframe(df, use_container_width=True, hide_index=True)
        except Exception:
            pass


def _render_infeasibility(st, section_header):
    section_header("Starting point of errors — infeasibility diagnostics")
    inf = collect_infeasibility()
    files = inf.get("files", [])
    runs = inf.get("infeasible_runs", [])
    if not files and not runs:
        st.success("No infeasibility diagnostic recorded — every scenario solved.")
        return
    if runs:
        st.error(f"{len(runs)} solver run(s) returned INFEASIBLE.")
        try:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
        except Exception:
            pass
    for f in files:
        with st.expander(f"{f['name']} — diagnostic ({f['n_lines']} lines)"):
            st.text(f.get("preview", ""))
