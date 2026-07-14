"""
diagnostics.py — Audit d'anomalies métier + moteur de remèdes proposés.

OBJECTIF (cf. demande de Mendrika) :
    Un statut solveur "OPTIMAL" ne garantit PAS que la solution respecte toutes
    les règles métier. Le pré-traitement (form_groups, 8 phases avec filets de
    secours) peut ABSORBER une infaisabilité en DÉFORMANT la solution : groupes
    minuscules, groupes à 1 étudiant, séances hors-période (1ère année
    l'après-midi), matières sur-souscrites. Ces anomalies sont FAISABLES pour le
    solveur mais INCORRECTES pour l'établissement.

    Ce module SCANNE la solution produite (outputs Excel/CSV) pour détecter ces
    anomalies, les compte par NIVEAU × SEMESTRE × MATIÈRE, et propose pour
    chacune un REMÈDE CHIFFRÉ (texte) que l'utilisateur peut décider d'appliquer
    ou d'ajuster. Rien n'est appliqué automatiquement.

    Tout est VÉRIFIABLE : les mêmes chiffres alimentent l'UI et la feuille Excel
    « Diagnostic & Remèdes ».

Ce module est PUR (pas de Streamlit, pas d'effet de bord), donc testable.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constantes métier (miroir de pipeline.py — gardées ici pour découplage/test)
# ---------------------------------------------------------------------------

# Blocs du matin / après-midi identifiés par leur LABEL horaire (colonne
# time_block du planning). Les blocs 1-3 sont le matin, 4-6 l'après-midi/soir.
MORNING_LABELS = {"08:30-10:30", "10:30-12:30", "12:30-14:30"}
AFTERNOON_LABELS = {"15:00-17:00", "17:00-19:00", "19:00-21:00"}

# Politique année → période (cf. pipeline.ALLOW_AFTERNOON_Y1Y3 / ALLOW_MORNING_Y2Y4).
# 1ère et 3ème année : le matin. 2ème et 4ème année : l'après-midi.
MORNING_YEARS = {1, 3}
AFTERNOON_YEARS = {2, 4}

DEFAULT_MIN_GROUP_SIZE = 7

# Sévérités (ordre d'affichage / de tri).
SEV_CRITICAL = "critique"
SEV_WARNING = "avertissement"
SEV_INFO = "info"
_SEV_RANK = {SEV_CRITICAL: 0, SEV_WARNING: 1, SEV_INFO: 2}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _period_of(time_block_label: str) -> Optional[str]:
    """Retourne 'morning' | 'afternoon' | None pour un label horaire."""
    lbl = str(time_block_label).strip()
    if lbl in MORNING_LABELS:
        return "morning"
    if lbl in AFTERNOON_LABELS:
        return "afternoon"
    return None


def _level_label(curso_num: Any) -> str:
    """1 -> 'Primero', 2 -> 'Segundo', ... (fallback: valeur brute)."""
    names = {1: "Primero", 2: "Segundo", 3: "Tercero", 4: "Cuarto"}
    try:
        return names.get(int(curso_num), f"Año {curso_num}")
    except Exception:
        return str(curso_num)


def _sem_label(semester: Any) -> str:
    try:
        return f"S{int(str(semester).replace('S', ''))}"
    except Exception:
        return str(semester)


def _dedup_groups(schedule_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Réduit le planning (1 ligne / séance) à 1 ligne / groupe unique.

    Un groupe est identifié par (semester, subject, grupo). On conserve les
    attributs stables du groupe : curso_num, nb_students, et l'ensemble des
    time_blocks/périodes utilisés par ses séances.
    """
    by_group: Dict[tuple, Dict[str, Any]] = {}
    for r in schedule_rows:
        key = (str(r.get("semester")), str(r.get("subject")), str(r.get("grupo")))
        g = by_group.get(key)
        if g is None:
            g = {
                "semester": r.get("semester"),
                "subject": r.get("subject"),
                "grupo": r.get("grupo"),
                "curso_num": r.get("curso_num"),
                "nb_students": r.get("nb_students"),
                "time_blocks": set(),
                "periods": set(),
                "n_sessions": 0,
            }
            by_group[key] = g
        g["n_sessions"] += 1
        tb = r.get("time_block")
        if tb is not None and str(tb).strip():
            g["time_blocks"].add(str(tb).strip())
            p = _period_of(tb)
            if p:
                g["periods"].add(p)
        # nb_students peut varier légèrement selon la séance : on garde le max
        try:
            if r.get("nb_students") is not None:
                g["nb_students"] = max(int(g["nb_students"] or 0),
                                       int(r["nb_students"]))
        except Exception:
            pass
    return list(by_group.values())


# ---------------------------------------------------------------------------
# Détecteurs d'anomalies
# ---------------------------------------------------------------------------

def detect_tiny_groups(groups: List[Dict[str, Any]],
                       min_group_size: int = DEFAULT_MIN_GROUP_SIZE
                       ) -> List[Dict[str, Any]]:
    """Groupes en dessous de la taille minimale (dont groupes à 1 étudiant).

    Symptôme classique d'une infaisabilité absorbée par les phases de secours
    (P6 crée des groupes solo quand un étudiant ne rentre nulle part).
    """
    out: List[Dict[str, Any]] = []
    for g in groups:
        try:
            n = int(g.get("nb_students") or 0)
        except Exception:
            n = 0
        if n <= 0:
            continue
        if n < min_group_size:
            solo = (n == 1)
            out.append({
                "type": "tiny_group",
                "severity": SEV_CRITICAL if solo else SEV_WARNING,
                "level": _level_label(g.get("curso_num")),
                "curso_num": g.get("curso_num"),
                "semester": _sem_label(g.get("semester")),
                "subject": g.get("subject"),
                "grupo": g.get("grupo"),
                "nb_students": n,
                "min_group_size": min_group_size,
                "detail": (
                    f"Group {g.get('grupo')} of \u201c{g.get('subject')}\u201d: "
                    f"{n} student(s) < minimum {min_group_size}"
                    + (" (SOLO GROUP)" if solo else "")
                ),
            })
    return out


def detect_wrong_period(groups: List[Dict[str, Any]],
                        allow_afternoon_y1y3: bool = False,
                        allow_morning_y2y4: bool = False
                        ) -> List[Dict[str, Any]]:
    """Séances placées dans la mauvaise période pour le niveau.

    1ère/3ème année attendues le matin ; 2ème/4ème l'après-midi. Sauf si les
    dérogations correspondantes sont activées dans la config.
    """
    out: List[Dict[str, Any]] = []
    for g in groups:
        try:
            curso = int(g.get("curso_num"))
        except Exception:
            continue
        periods = g.get("periods") or set()
        bad_blocks: List[str] = []
        if curso in MORNING_YEARS and not allow_afternoon_y1y3:
            if "afternoon" in periods:
                bad_blocks = sorted(
                    b for b in (g.get("time_blocks") or set())
                    if _period_of(b) == "afternoon")
                expected = "morning"
        elif curso in AFTERNOON_YEARS and not allow_morning_y2y4:
            if "morning" in periods:
                bad_blocks = sorted(
                    b for b in (g.get("time_blocks") or set())
                    if _period_of(b) == "morning")
                expected = "afternoon"
        if bad_blocks:
            out.append({
                "type": "wrong_period",
                "severity": SEV_CRITICAL,
                "level": _level_label(curso),
                "curso_num": curso,
                "semester": _sem_label(g.get("semester")),
                "subject": g.get("subject"),
                "grupo": g.get("grupo"),
                "bad_blocks": bad_blocks,
                "expected_period": expected,
                "detail": (
                    f"Group {g.get('grupo')} of \u201c{g.get('subject')}\u201d "
                    f"({_level_label(curso)}) placed on {', '.join(bad_blocks)} "
                    f"whereas the {expected} is expected"
                ),
            })
    return out


# ---------------------------------------------------------------------------
# Moteur de remèdes proposés (texte chiffré ; jamais appliqué automatiquement)
# ---------------------------------------------------------------------------

def propose_remedy(anomaly: Dict[str, Any]) -> Dict[str, Any]:
    """Associe à une anomalie un remède PROPOSÉ (action + paramètre chiffré).

    Retourne {action, target, param, text}. Le champ `text` est prêt à afficher
    ou à écrire dans l'Excel. Rien n'est appliqué : l'utilisateur décide.
    """
    kind = anomaly.get("type")
    if kind == "tiny_group":
        n = anomaly.get("nb_students", 0)
        need = anomaly.get("min_group_size", DEFAULT_MIN_GROUP_SIZE) - n
        return {
            "action": "merge_or_relax_min",
            "target": f"{anomaly.get('subject')} / grupo {anomaly.get('grupo')}",
            "param": need,
            "text": (
                f"Merge this group with another group of the same subject "
                f"(+{need} student(s) to reach the minimum), OR lower "
                f"MIN_GROUP_SIZE if {n} student(s) is acceptable for this case, "
                f"OR open an additional slot to redistribute."
            ),
        }
    if kind == "wrong_period":
        expected = anomaly.get("expected_period")
        return {
            "action": "move_to_expected_period",
            "target": f"{anomaly.get('subject')} / grupo {anomaly.get('grupo')}",
            "param": expected,
            "text": (
                f"Move these sessions to a {expected} slot (Plan editing "
                f"\u2192 Move a session), OR enable the matching override in "
                f"Configuration \u2192 Time preference per year level if the "
                f"{expected} is truly impossible."
            ),
        }
    if kind == "bottleneck":
        excess = anomaly.get("excess", anomaly.get("overflow", 0))
        return {
            "action": "add_capacity_or_widen_window",
            "target": str(anomaly.get("ident", anomaly.get("resource", ""))),
            "param": excess,
            "text": (
                f"Excess of {excess} session(s) on this slot. Widen the "
                f"[min_week, max_week] window by +{excess} week(s), OR open an "
                f"additional room/slot, OR reduce the number of parallel groups "
                f"on this slot."
            ),
        }
    if kind == "oversubscription":
        gap = anomaly.get("gap", 0)
        crit = anomaly.get("single_prof")
        return {
            "action": "add_professor_or_reduce_groups",
            "target": str(anomaly.get("subject", "")),
            "param": gap,
            "text": (
                f"{gap} group(s) beyond the credit budget."
                + (" SINGLE PROFESSOR (critical): " if crit else " ")
                + "Allocate additional P credits to an eligible professor, "
                "OR reduce the number of groups scheduled for this subject."
            ),
        }
    if kind == "credit_overload":
        delta = anomaly.get("delta", 0)
        return {
            "action": "rebalance_professor_load",
            "target": str(anomaly.get("professor", "")),
            "param": delta,
            "text": (
                f"Professor over budget by +{delta} session(s) vs credits. "
                f"Reassign {delta} session(s) to an eligible colleague of the "
                f"same subject, OR adjust the P credits in the Teaching "
                f"assignment (Asignaci\u00f3n docente)."
            ),
        }
    return {"action": "review", "target": "", "param": None,
            "text": "Manual review recommended."}


# ---------------------------------------------------------------------------
# Agrégat : audit complet + réconciliation par niveau × semestre × matière
# ---------------------------------------------------------------------------

def audit_schedule(schedule_rows: List[Dict[str, Any]],
                   min_group_size: int = DEFAULT_MIN_GROUP_SIZE,
                   allow_afternoon_y1y3: bool = False,
                   allow_morning_y2y4: bool = False,
                   extra_anomalies: Optional[List[Dict[str, Any]]] = None
                   ) -> Dict[str, Any]:
    """Audit complet de la solution : anomalies + remèdes + agrégats.

    Args:
        schedule_rows: lignes du planning (optimized_schedule_v5.csv en dicts).
        min_group_size: seuil de taille minimale de groupe.
        allow_afternoon_y1y3 / allow_morning_y2y4: dérogations actives (config).
        extra_anomalies: anomalies déjà détectées ailleurs (sur-souscription,
            goulots, surcharges profs) à intégrer au rapport unifié.

    Returns:
        dict {anomalies, by_type, by_level_semester, n_total, n_critical}.
        Chaque anomalie porte son remède proposé sous la clé `remedy`.
    """
    groups = _dedup_groups(schedule_rows)

    anomalies: List[Dict[str, Any]] = []
    anomalies += detect_tiny_groups(groups, min_group_size)
    anomalies += detect_wrong_period(groups, allow_afternoon_y1y3,
                                     allow_morning_y2y4)
    if extra_anomalies:
        anomalies += list(extra_anomalies)

    # Attache un remède proposé à chaque anomalie.
    for a in anomalies:
        a["remedy"] = propose_remedy(a)

    # Tri : sévérité puis niveau/semestre/matière.
    anomalies.sort(key=lambda a: (
        _SEV_RANK.get(a.get("severity", SEV_INFO), 3),
        str(a.get("level", "")), str(a.get("semester", "")),
        str(a.get("subject", "")),
    ))

    # Agrégats par type.
    by_type: Dict[str, int] = defaultdict(int)
    for a in anomalies:
        by_type[a.get("type", "?")] += 1

    # Réconciliation par niveau × semestre.
    by_level_semester: Dict[str, Dict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    for a in anomalies:
        key = f"{a.get('level', '?')} · {a.get('semester', '?')}"
        by_level_semester[key][a.get("type", "?")] += 1
        by_level_semester[key]["total"] += 1

    n_critical = sum(1 for a in anomalies
                     if a.get("severity") == SEV_CRITICAL)

    return {
        "anomalies": anomalies,
        "by_type": dict(by_type),
        "by_level_semester": {k: dict(v) for k, v in by_level_semester.items()},
        "n_total": len(anomalies),
        "n_critical": n_critical,
        "n_groups_analyzed": len(groups),
        "healthy": len(anomalies) == 0,
    }
