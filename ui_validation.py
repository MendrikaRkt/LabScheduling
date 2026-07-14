# -*- coding: utf-8 -*-
"""
ui_validation.py — Validation préventive des paramètres de configuration.

Ce module centralise, sous forme de fonctions PURES et testables (aucune
dépendance Streamlit), toutes les règles de validation appliquées aux
paramètres saisis par l'utilisateur dans l'interface de configuration
AVANT le lancement du solveur.

Objectif métier
---------------
Le système sait déjà détecter les anomalies *après coup* (``diagnostics.py``,
``schedule_validation.py``). Ce module ajoute le garde-fou *en amont* : il
empêche l'utilisateur de lancer une optimisation avec des paramètres qui
violent les contraintes nécessaires à un résultat conforme (p. ex.
``taille min > taille max``, fenêtre de semaines insuffisante pour le nombre
de séances, aucune salle sélectionnée, etc.).

Les seuils métier sont réutilisés depuis ``diagnostics.py`` et
``schedule_validation.py`` afin d'éviter toute divergence de constantes.

Chaque règle produit une :class:`Issue` avec un niveau :
- ``error``   : configuration bloquante — le bouton « Lancer » doit être désactivé.
- ``warning`` : configuration acceptée mais risquée — on prévient l'utilisateur.
- ``info``    : information contextuelle.

Toutes les chaînes destinées à l'utilisateur sont en français, conformément
aux exigences du projet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Réutilisation des constantes métier existantes (source unique de vérité) ──
try:  # pragma: no cover - chemins d'import défensifs
    from diagnostics import (
        DEFAULT_MIN_GROUP_SIZE,
        MORNING_YEARS,
        AFTERNOON_YEARS,
    )
except Exception:  # pragma: no cover
    DEFAULT_MIN_GROUP_SIZE = 7
    MORNING_YEARS = {1, 3}
    AFTERNOON_YEARS = {2, 4}

try:  # pragma: no cover
    from schedule_validation import GROUP_MIN, GROUP_PREFERRED, GROUP_MAX
except Exception:  # pragma: no cover
    GROUP_MIN, GROUP_PREFERRED, GROUP_MAX = 7, 12, 15


# Niveaux de sévérité (ordre de priorité : error > warning > info)
LEVEL_ERROR = "error"
LEVEL_WARNING = "warning"
LEVEL_INFO = "info"
_LEVEL_RANK = {LEVEL_ERROR: 0, LEVEL_WARNING: 1, LEVEL_INFO: 2}

# Bornes « raisonnables » utilisées pour les indications (hints) affichées à
# l'utilisateur. Elles décrivent des plages recommandées, pas des limites dures.
ABSOLUTE_MIN_GROUP = 2
ABSOLUTE_MAX_GROUP = 35
MIN_SESSIONS = 1
MAX_SESSIONS_SOFT = 8


@dataclass
class Issue:
    """Un problème de validation détecté sur un paramètre.

    Attributes
    ----------
    level:
        Niveau de sévérité : ``error``, ``warning`` ou ``info``.
    code:
        Identifiant stable de la règle (utile pour les tests et le suivi).
    message:
        Message clair en français décrivant le problème.
    hint:
        Indication sur les valeurs acceptables (facultatif).
    scope:
        Contexte du problème : ``"global"`` ou le code de la matière concernée.
    """

    level: str
    code: str
    message: str
    hint: str = ""
    scope: str = "global"

    @property
    def is_blocking(self) -> bool:
        return self.level == LEVEL_ERROR


@dataclass
class ValidationReport:
    """Agrégat de toutes les :class:`Issue` détectées sur une configuration."""

    issues: List[Issue] = field(default_factory=list)

    # -- Filtres par niveau ------------------------------------------------
    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == LEVEL_ERROR]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.level == LEVEL_WARNING]

    @property
    def infos(self) -> List[Issue]:
        return [i for i in self.issues if i.level == LEVEL_INFO]

    # -- Verdicts ----------------------------------------------------------
    @property
    def is_blocking(self) -> bool:
        """Vrai si au moins une erreur bloquante est présente."""
        return len(self.errors) > 0

    @property
    def is_clean(self) -> bool:
        """Vrai si aucune erreur ni avertissement."""
        return not self.errors and not self.warnings

    def sorted_issues(self) -> List[Issue]:
        """Retourne les problèmes triés par sévérité décroissante."""
        return sorted(self.issues, key=lambda i: _LEVEL_RANK.get(i.level, 9))

    def summary(self) -> Dict[str, int]:
        return {
            "errors": len(self.errors),
            "warnings": len(self.warnings),
            "infos": len(self.infos),
            "total": len(self.issues),
        }


# ──────────────────────────────────────────────────────────────────────────
# Helpers internes
# ──────────────────────────────────────────────────────────────────────────

def _to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """Convertit prudemment une valeur en entier, sinon retourne ``default``."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────────────────
# Règles : paramètres globaux
# ──────────────────────────────────────────────────────────────────────────

def validate_global_params(cfg: Dict[str, Any]) -> List[Issue]:
    """Valide les paramètres globaux de génération (onglet « Paramètres globaux »).

    Parameters
    ----------
    cfg:
        Dictionnaire des paramètres globaux (``st.session_state.advanced_config``).

    Returns
    -------
    list of Issue
    """
    issues: List[Issue] = []

    min_size = _to_int(cfg.get("min_size"), DEFAULT_MIN_GROUP_SIZE)
    preferred = _to_int(cfg.get("preferred_size"), GROUP_PREFERRED)
    default_max = _to_int(cfg.get("default_max"), GROUP_MAX)
    computer_max = _to_int(cfg.get("computer_lab_max"), 24)
    reduced_max = _to_int(cfg.get("reduced_max_size"), 12)
    start_week = _to_int(cfg.get("start_week"), 4)
    s1_weeks = _to_int(cfg.get("s1_total_weeks"), 14)
    s2_weeks = _to_int(cfg.get("s2_total_weeks"), 20)

    # R1 — cohérence min <= max (bloquant)
    if min_size is not None and default_max is not None and min_size > default_max:
        issues.append(Issue(
            LEVEL_ERROR, "G_MIN_GT_MAX",
            f"The minimum size ({min_size}) is larger than the maximum "
            f"size ({default_max}): no group can be formed.",
            hint=f"The min size must be ≤ the max size ({default_max}).",
        ))

    # R2 — cohérence taille préférée entre min et max (bloquant si > max)
    if preferred is not None and default_max is not None and preferred > default_max:
        issues.append(Issue(
            LEVEL_ERROR, "G_PREF_GT_MAX",
            f"The preferred size ({preferred}) exceeds the maximum size "
            f"({default_max}).",
            hint=f"The preferred size must be between the min size "
                 f"and the max size ({default_max}).",
        ))
    if (preferred is not None and min_size is not None
            and preferred < min_size):
        issues.append(Issue(
            LEVEL_WARNING, "G_PREF_LT_MIN",
            f"The preferred size ({preferred}) is smaller than the minimum "
            f"size ({min_size}): groups below the minimum may be "
            f"merged.",
            hint=f"Recommended: min ({min_size}) ≤ preferred ≤ max.",
        ))

    # R3 — taille minimale sous le seuil métier recommandé (avertissement)
    if min_size is not None and min_size < GROUP_MIN:
        issues.append(Issue(
            LEVEL_WARNING, "G_MIN_BELOW_POLICY",
            f"The minimum size ({min_size}) is below the recommended "
            f"business threshold ({GROUP_MIN}). Very small (or even "
            f"single-student) groups could be created.",
            hint=f"The coordinator's recommended threshold is {GROUP_MIN} "
                 f"students minimum.",
        ))

    # R4 — capacité salle informatique cohérente avec le max standard
    if (computer_max is not None and default_max is not None
            and computer_max < default_max):
        issues.append(Issue(
            LEVEL_WARNING, "G_COMPUTER_LT_MAX",
            f"The computer-room capacity ({computer_max}) is "
            f"below the standard max size ({default_max}).",
            hint="Computer rooms usually hold more "
                 "students than standard labs.",
        ))

    # R5 — max réduit cohérent
    if (reduced_max is not None and default_max is not None
            and reduced_max > default_max):
        issues.append(Issue(
            LEVEL_WARNING, "G_REDUCED_GT_MAX",
            f"The special/reduced maximum ({reduced_max}) exceeds the "
            f"standard maximum ({default_max}).",
            hint=f"The reduced maximum should be ≤ {default_max}.",
        ))

    # R6 — semaine de départ dans les bornes du semestre (bloquant)
    if start_week is not None and start_week < 1:
        issues.append(Issue(
            LEVEL_ERROR, "G_START_WEEK_LT_1",
            f"The first week ({start_week}) must be ≥ 1.",
            hint="Typical value: 3 or 4.",
        ))
    if (start_week is not None and s1_weeks is not None
            and start_week >= s1_weeks):
        issues.append(Issue(
            LEVEL_ERROR, "G_START_WEEK_GE_S1",
            f"The first week ({start_week}) is on or after "
            f"the last week of S1 ({s1_weeks}): no week is "
            f"available to schedule in S1.",
            hint=f"The first week must be < {s1_weeks}.",
        ))

    # R7 — durée des semestres cohérente (avertissement)
    if (s1_weeks is not None and s2_weeks is not None
            and s2_weeks < s1_weeks):
        issues.append(Issue(
            LEVEL_WARNING, "G_S2_LT_S1",
            f"The number of S2 weeks ({s2_weeks}) is smaller than "
            f"S1 ({s1_weeks}), which is unusual.",
            hint="Check the academic calendar.",
        ))

    return issues


# ──────────────────────────────────────────────────────────────────────────
# Règles : surcharges par matière
# ──────────────────────────────────────────────────────────────────────────

def validate_subject_override(code: str,
                              ov: Dict[str, Any],
                              semester: Optional[int] = None,
                              curso_num: Optional[int] = None,
                              year_prefs: Optional[Dict[str, Any]] = None
                              ) -> List[Issue]:
    """Valide la surcharge d'une matière (onglet « Configuration par matière »).

    Parameters
    ----------
    code:
        Code / nom de la matière (sert de ``scope``).
    ov:
        Dictionnaire de surcharge de la matière.
    semester:
        Semestre (1 ou 2) pour l'affichage éventuel.
    curso_num:
        Année (1..4) de la matière, pour vérifier la cohérence horaire.
    year_prefs:
        Préférences horaires globales (``allow_afternoon_y1y3`` /
        ``allow_morning_y2y4``) qui assouplissent la règle année → période.
    """
    issues: List[Issue] = []
    year_prefs = year_prefs or {}

    n_sess = _to_int(ov.get("num_sessions"), 1)
    max_students = _to_int(ov.get("max_students"), GROUP_MAX)
    min_size = _to_int(ov.get("min_size"), DEFAULT_MIN_GROUP_SIZE)
    min_week = _to_int(ov.get("min_week"), 1)
    max_week = _to_int(ov.get("max_week"), 1)
    rooms = ov.get("lab_rooms") or []
    keywords = ov.get("keywords") or []
    schedule_pref = ov.get("schedule_pref")

    # S1 — fenêtre de semaines suffisante pour le nombre de séances (bloquant)
    if min_week is not None and max_week is not None and n_sess is not None:
        window = max_week - min_week + 1
        if window < n_sess:
            issues.append(Issue(
                LEVEL_ERROR, "S_WINDOW_TOO_SMALL",
                f"[{code}] Window too short: {window} week(s) "
                f"available for {n_sess} session(s). Increase the "
                f"\"End week\" or reduce the number of sessions.",
                hint=f"At least {n_sess} weeks are needed "
                     f"(currently from W{min_week} to W{max_week}).",
                scope=code,
            ))
        elif window == n_sess:
            issues.append(Issue(
                LEVEL_WARNING, "S_WINDOW_TIGHT",
                f"[{code}] Tight window: exactly {window} weeks for "
                f"{n_sess} sessions. No margin — a public holiday could "
                f"cause a conflict.",
                hint="Ideally allow 1 to 2 weeks of margin.",
                scope=code,
            ))

    # S2 — cohérence min_size / max_students (bloquant)
    if (min_size is not None and max_students is not None
            and min_size > max_students):
        issues.append(Issue(
            LEVEL_ERROR, "S_MIN_GT_MAX",
            f"[{code}] The min size ({min_size}) exceeds the max size "
            f"({max_students}): a group cannot be formed.",
            hint=f"The min size must be ≤ {max_students}.",
            scope=code,
        ))

    # S3 — nombre de séances valide (bloquant si < 1)
    if n_sess is not None and n_sess < MIN_SESSIONS:
        issues.append(Issue(
            LEVEL_ERROR, "S_NO_SESSION",
            f"[{code}] At least {MIN_SESSIONS} session is required.",
            hint=f"Recommended number of sessions: {MIN_SESSIONS} to "
                 f"{MAX_SESSIONS_SOFT}.",
            scope=code,
        ))
    elif n_sess is not None and n_sess > MAX_SESSIONS_SOFT:
        issues.append(Issue(
            LEVEL_WARNING, "S_MANY_SESSIONS",
            f"[{code}] High number of sessions ({n_sess}). Make sure "
            f"this is intentional.",
            hint=f"Usual value: {MIN_SESSIONS} to {MAX_SESSIONS_SOFT}.",
            scope=code,
        ))

    # S4 — capacité extrême (avertissement)
    if max_students is not None and max_students < 5:
        issues.append(Issue(
            LEVEL_WARNING, "S_CAPACITY_LOW",
            f"[{code}] Very low group capacity ({max_students}): many "
            f"groups will be created.",
            hint=f"Recommended range: {GROUP_MIN} to {GROUP_MAX}.",
            scope=code,
        ))
    if max_students is not None and max_students > 25:
        issues.append(Issue(
            LEVEL_WARNING, "S_CAPACITY_HIGH",
            f"[{code}] High group capacity ({max_students}): check "
            f"that the room can hold it.",
            hint=f"Recommended range: {GROUP_MIN} to {GROUP_MAX}.",
            scope=code,
        ))

    # S5 — aucune salle sélectionnée (bloquant)
    if not rooms:
        issues.append(Issue(
            LEVEL_ERROR, "S_NO_ROOM",
            f"[{code}] No room selected: this subject cannot "
            f"be scheduled.",
            hint="Select at least one laboratory in the "
                 "\"Lab rooms\" tab.",
            scope=code,
        ))

    # S6 — aucun mot-clé (avertissement)
    if not keywords:
        issues.append(Issue(
            LEVEL_WARNING, "S_NO_KEYWORD",
            f"[{code}] No keyword defined: this subject may not "
            f"be detected in the source data.",
            hint="Add keywords in the \"Advanced\" tab.",
            scope=code,
        ))

    # S7 — cohérence année → période horaire (avertissement)
    if curso_num is not None and schedule_pref in ("morning", "afternoon"):
        allow_pm_13 = bool(year_prefs.get("allow_afternoon_y1y3", False))
        allow_am_24 = bool(year_prefs.get("allow_morning_y2y4", False))
        if (curso_num in MORNING_YEARS and schedule_pref == "afternoon"
                and not allow_pm_13):
            issues.append(Issue(
                LEVEL_WARNING, "S_PERIOD_MISMATCH",
                f"[{code}] Year {curso_num} (morning expected) configured for "
                f"the afternoon. This contradicts the year → period rule.",
                hint="Enable \"allow afternoon for years 1/3\" "
                     "if intended, otherwise switch back to \"morning\".",
                scope=code,
            ))
        elif (curso_num in AFTERNOON_YEARS and schedule_pref == "morning"
              and not allow_am_24):
            issues.append(Issue(
                LEVEL_WARNING, "S_PERIOD_MISMATCH",
                f"[{code}] Year {curso_num} (afternoon expected) configured "
                f"for the morning. This contradicts the year → period rule.",
                hint="Enable \"allow morning for years 2/4\" if "
                     "intended, otherwise switch back to \"afternoon\".",
                scope=code,
            ))

    return issues


# ──────────────────────────────────────────────────────────────────────────
# Agrégation
# ──────────────────────────────────────────────────────────────────────────

def validate_all(advanced_config: Dict[str, Any]) -> ValidationReport:
    """Valide l'intégralité de la configuration avant lancement du solveur.

    Combine la validation des paramètres globaux et de toutes les surcharges
    de matières présentes dans ``advanced_config``.

    Parameters
    ----------
    advanced_config:
        Le dictionnaire ``st.session_state.advanced_config``.

    Returns
    -------
    ValidationReport
    """
    report = ValidationReport()
    if not isinstance(advanced_config, dict):
        return report

    report.issues.extend(validate_global_params(advanced_config))

    year_prefs = {
        "allow_afternoon_y1y3": advanced_config.get("allow_afternoon_y1y3", False),
        "allow_morning_y2y4": advanced_config.get("allow_morning_y2y4", False),
    }

    overrides = advanced_config.get("subject_overrides") or {}
    for code, ov in overrides.items():
        if not isinstance(ov, dict):
            continue
        report.issues.extend(
            validate_subject_override(
                code, ov,
                semester=ov.get("semester"),
                curso_num=ov.get("curso_num"),
                year_prefs=year_prefs,
            )
        )

    return report


__all__ = [
    "Issue",
    "ValidationReport",
    "validate_global_params",
    "validate_subject_override",
    "validate_all",
    "LEVEL_ERROR",
    "LEVEL_WARNING",
    "LEVEL_INFO",
]
