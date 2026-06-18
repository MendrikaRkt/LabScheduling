"""Configuration pytest : rend les modules du dépôt importables et fournit des
fixtures de données synthétiques (aucune dépendance aux gros fichiers Excel/CSV
de production, pour que la CI reste rapide et reproductible)."""

import os
import sys

import pandas as pd
import pytest

# Racine du dépôt sur le sys.path (les modules sont à la racine).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def synthetic_master_df():
    """Un master_schedule minimal mais valide (colonnes attendues présentes)."""
    return pd.DataFrame(
        {
            "AlumnoID": [1, 2, 3, 4, 5, 6],
            "subject": ["Mat A"] * 3 + ["Mat B"] * 3,
            "day": ["Lunes", "Lunes", "Martes", "Viernes", "Viernes", "Viernes"],
            "slot_hora_inicio": ["08:30"] * 6,
            "semester": [1, 1, 1, 2, 2, 2],
        }
    )


@pytest.fixture
def synthetic_subject_students():
    return {
        "Mat A": [1, 2, 3, 10],   # 10 = inscrit mais NON placé (fuite volontaire)
        "Mat B": [4, 5, 6],
    }


@pytest.fixture
def synthetic_groups():
    """Groupes formés correspondant aux étudiants ci-dessus."""
    return [
        {
            "subject": "Mat A", "grupo": 1, "semester": 1,
            "day": "Lunes", "day_idx": 0, "block_id": "b1",
            "nb_students": 3, "num_sessions": 3,
            "min_week": 1, "max_week": 12,
            "lab_rooms": "Lab Alpha",
            "student_ids": [1, 2, 3],
            "_overflow": False,
        },
        {
            "subject": "Mat B", "grupo": 1, "semester": 2,
            "day": "Viernes", "day_idx": 4, "block_id": "b1",
            "nb_students": 3, "num_sessions": 2,
            "min_week": 1, "max_week": 18,
            "lab_rooms": "Lab Beta",
            "student_ids": [4, 5, 6],
            "_overflow": True, "_recovered": True,
        },
    ]


@pytest.fixture
def synthetic_results_df():
    return pd.DataFrame(
        [
            {"semester": 1, "subject": "Mat A", "grupo": 1, "session": 1,
             "week": 2, "day": "Lunes", "time_block": "08:30",
             "nb_students": 3, "lab_rooms": "Lab Alpha"},
            {"semester": 1, "subject": "Mat A", "grupo": 1, "session": 2,
             "week": 6, "day": "Lunes", "time_block": "08:30",
             "nb_students": 3, "lab_rooms": "Lab Alpha"},
            {"semester": 2, "subject": "Mat B", "grupo": 1, "session": 1,
             "week": 3, "day": "Viernes", "time_block": "08:30",
             "nb_students": 3, "lab_rooms": "Lab Beta"},
        ]
    )
