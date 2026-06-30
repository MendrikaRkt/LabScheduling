# -*- coding: utf-8 -*-
"""
lab_constants.py
================

Constantes métier partagées par l'ensemble du pipeline de planification de
laboratoires (LabScheduling).

Ce module ne contient AUCUNE dépendance (pas d'import de pandas, de modules du
projet, etc.) afin d'éviter tout risque d'import circulaire : il peut être
importé librement par n'importe quel autre module du projet.

Historique
----------
Avant la centralisation, la constante ``CREDIT_TO_SESSIONS = 5`` était dupliquée
dans au moins quatre fichiers (``professor_credits.py``,
``lab_professor_assignment.py``, ``validation_credits.py`` et
``excel_generator_core.py``). Toute évolution de la convention « 1 crédit P =
N séances » imposait donc une modification synchronisée de plusieurs fichiers,
avec un risque d'incohérence. Cette constante (et la constante associée
``SESSIONS_PER_GROUP``) est désormais définie ici, en un seul endroit.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Convention pédagogique du coordinateur :
#   1 crédit de laboratoire (P) == 5 séances planifiées.
# Exemple de contrôle (« smoke test ») : une matière de 6 crédits P doit
# produire 6 * 5 = 30 séances.
# ---------------------------------------------------------------------------
CREDIT_TO_SESSIONS = 5

# Chaque groupe de pratiques correspond à 5 séances.
SESSIONS_PER_GROUP = 5

__all__ = ["CREDIT_TO_SESSIONS", "SESSIONS_PER_GROUP"]
