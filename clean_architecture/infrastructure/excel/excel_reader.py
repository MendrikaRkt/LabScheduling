"""excel_reader.py - Reading of data sources (Excel / CSV).

Centralizes ALL knowledge of the external file formats:
  - Asignacion_2025-2026_v5.xlsx -> official P credits per professor
    (single source of truth for the professor assignment)
  - master_schedule.csv -> individual enrolments and timetables
  - informeDetalle      -> official timetable (SpreadsheetML)

The rest of the application receives domain entities (Professor) and is
completely unaware of the Excel column structure.

Structure of the "Asignacion docente" sheet:
  - Col 9  : Asignatura (subject name)
  - Col 37 : Curso (year of study)
  - Col 38 : Semestre (1 or 2)
  - Col 45 : Creditos T (theory)
  - Col 46 : Creditos P (practice)
  - Col 49-60 : Prof 1..4 (abbreviations) + credits + type
  - Col 64 : responsible professor email
  - Col 65 : Resp Texto (full name of the responsible professor)
  - Col 68-79 : Prof 1..4 "bis" with FULL NAMES + credits + type
                (used here because readable, unlike the abbreviations)

Business rule: 1 P credit = 5 laboratory sessions (configurable).
Up to 4 professors can share the same subject/theory group.

CREDIT POLICY: only PRACTICE (P) credits are counted. Theory (T) credits are
completely ignored. Rows tagged "TP" hold a professor who delivers both theory
and practice; only the practice component is extracted (see read_assignments).
"""
from __future__ import annotations

import logging
import os
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import pandas as pd

from domain.entities.professor import Professor
from domain.rules import DEFAULT_SESSIONS_PER_CREDIT, credits_to_sessions
from domain.value_objects import Credits, CreditType

logger = logging.getLogger(__name__)

# -- Column indices of the "Asignacion docente" sheet -------------------------
COL_ASIGNATURA = 9
COL_CURSO = 37
COL_SEMESTRE = 38
COL_CREDITOS_T = 45
COL_CREDITOS_P = 46
COL_RESP_EMAIL = 64
COL_RESP_TEXTO = 65

# Professor blocks with FULL NAMES ("bis" columns):
# (name, credits, type) -> up to 4 blocks per row (up to 4 professors).
PROF_BLOCKS_FULLNAME = [(68, 69, 70), (71, 72, 73), (74, 75, 76), (77, 78, 79)]
# Historical blocks with abbreviations (49-60), kept as a fallback.
PROF_BLOCKS_ABBREV = [(49, 50, 51), (52, 53, 54), (55, 56, 57), (58, 59, 60)]


def _normalize(text: str) -> str:
    """Normalize a label: lowercase, no accents, compacted spaces."""
    if text is None:
        return ""
    s = str(text).strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(s.split())


@dataclass
class SubjectMatcher:
    """Links an Excel label (Spanish) to an internal subject code from config.

    The matching relies on the `keywords` / `keyword_exclude` defined in
    `config.yaml` for each subject. The `semester` disambiguates homonymous
    subjects (e.g. Fisica I in S1 vs Fisica II in S2).
    """

    # code -> {"keywords": [...], "keyword_exclude": [...], "semester": int}
    rules: Dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings) -> "SubjectMatcher":
        """Builds the matcher from the configured subjects."""
        rules: Dict[str, dict] = {}
        for code, subj in settings.subjects.items():
            rules[code] = {
                "keywords": [_normalize(k) for k in getattr(subj, "keywords", [])],
                "keyword_exclude": [
                    _normalize(k) for k in getattr(subj, "keyword_exclude", [])
                ],
                "semester": getattr(subj, "semester", None),
            }
        return cls(rules=rules)

    def match(self, asignatura: str, semester: Optional[int] = None) -> Optional[str]:
        """Returns the internal subject code or None if there is no match.

        The match whose keyword is the longest (the most specific) is kept, so
        that a generic keyword does not win over a specific one.
        """
        name = _normalize(asignatura)
        if not name:
            return None
        best_code: Optional[str] = None
        best_len = -1
        for code, rule in self.rules.items():
            if semester is not None and rule.get("semester") not in (None, semester):
                continue
            if any(ex and ex in name for ex in rule["keyword_exclude"]):
                continue
            for kw in rule["keywords"]:
                if kw and kw in name and len(kw) > best_len:
                    best_code, best_len = code, len(kw)
        return best_code

    def __call__(self, asignatura: str, semester: Optional[int] = None) -> Optional[str]:
        return self.match(asignatura, semester)


@dataclass
class ProfessorAssignment:
    """An elementary professor x subject assignment (from one Excel row)."""
    professor: str
    subject_code: str
    subject_label: str
    curso: Optional[int]
    semester: Optional[int]
    practice_credits: float
    expected_sessions: int
    email: str = ""


class ExcelReader:
    """Reader of the source files, returning business objects."""

    # -- master schedule ---------------------------------------------------
    CSV_READ_OPTIONS = (
        ("utf-8-sig", ","), ("utf-8", ","), ("latin-1", ","),
        ("utf-8-sig", ";"), ("latin-1", ";"),
    )

    def __init__(self, sessions_per_credit: int = DEFAULT_SESSIONS_PER_CREDIT):
        if sessions_per_credit <= 0:
            raise ValueError("sessions_per_credit must be > 0")
        self.sessions_per_credit = sessions_per_credit

    def read_master_schedule(self, path: str) -> pd.DataFrame:
        """Loads master_schedule.csv trying several encodings/separators."""
        last_err = None
        for enc, sep in self.CSV_READ_OPTIONS:
            try:
                df = pd.read_csv(path, encoding=enc, sep=sep)
                if df.shape[1] > 1:
                    return df
            except Exception as e:  # noqa: BLE001
                last_err = e
        raise IOError(f"Unable to read {path}: {last_err}")

    # -- detailed assignments (source of truth) -----------------------------
    def read_assignments(self, path: str,
                         sheet_name: str = "Asignacion docente",
                         subject_matcher: Optional[Callable] = None,
                         use_fullnames: bool = True) -> List[ProfessorAssignment]:
        """Reads every practice assignment (type P) of the workbook.

        Args:
            path: path of the Asignacion_2025-2026_v5.xlsx workbook.
            sheet_name: teaching assignment sheet.
            subject_matcher: callable(label, semester) -> code | None.
                If None, the raw label is kept as the code.
            use_fullnames: True to use the "bis" columns (full names),
                False for the abbreviations (49-60).

        Returns:
            List of ProfessorAssignment (one per professor x subject pair found,
            P credits > 0). Several professors (up to 4) per row are handled.

        Credit policy:
            - type "P"  -> P credits = listed value (pure practice)
            - type "TP" -> practice part = credits x P-ratio of the row
                           (the professor delivers theory + practice; we isolate
                           the P component to preserve the row's total P credits)
            - type "T" / anything else -> IGNORED (theory only, no practice)
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        blocks = PROF_BLOCKS_FULLNAME if use_fullnames else PROF_BLOCKS_ABBREV

        assignments: List[ProfessorAssignment] = []
        for _, row in df.iterrows():
            asignatura = self._cell(row, COL_ASIGNATURA)
            if not asignatura:
                continue
            semester = self._int(row, COL_SEMESTRE)
            curso = self._int(row, COL_CURSO)
            email = self._cell(row, COL_RESP_EMAIL)

            code = (subject_matcher(asignatura, semester)
                    if subject_matcher else asignatura)
            if code is None:
                continue  # subject outside the labs scope

            # Row T/P credits (mixed) -> ratio used to split the 'TP' rows.
            row_t = self._num(row, COL_CREDITOS_T)
            row_p = self._num(row, COL_CREDITOS_P)
            p_ratio = (row_p / (row_t + row_p)) if (row_t + row_p) > 0 else 0.0

            for name_col, cred_col, type_col in blocks:
                name = self._cell(row, name_col)
                ctype = self._cell(row, type_col).upper()
                cred = self._num(row, cred_col)
                if not name or cred <= 0:
                    continue
                # Determine the professor's PRACTICE credits:
                #   - 'P'  -> credits = listed value (pure practice)
                #   - 'TP' -> practice part = credits x row P-ratio (the
                #             professor delivers theory + practice; we isolate
                #             the P component to preserve the row's P credits)
                #   - 'T' / others -> ignored (no practice)
                if ctype == "P":
                    p_credits = cred
                elif ctype == "TP":
                    p_credits = round(cred * p_ratio, 3)
                else:
                    continue
                if p_credits <= 0:
                    continue
                assignments.append(ProfessorAssignment(
                    professor=name,
                    subject_code=code,
                    subject_label=asignatura,
                    curso=curso,
                    semester=semester,
                    practice_credits=p_credits,
                    expected_sessions=credits_to_sessions(
                        p_credits, self.sessions_per_credit),
                    email=email,
                ))
        logger.info("P assignments read: %d (sheet '%s')",
                    len(assignments), sheet_name)
        return assignments

    # -- professor credits (aggregated entities) ----------------------------
    def read_professor_credits(self, path: str,
                            sheet_name: str = "Asignacion docente",
                            subject_matcher: Optional[Callable] = None,
                            use_fullnames: bool = True) -> List[Professor]:
        """Aggregates the assignments into Professor entities (P credits per subject).

        Returns:
            List of Professor (one per name, P credits accumulated per subject).
        """
        assignments = self.read_assignments(
            path, sheet_name, subject_matcher, use_fullnames)
        professors: Dict[str, Professor] = {}
        for a in assignments:
            prof = professors.setdefault(
                a.professor, Professor(name=a.professor, email=a.email))
            if not prof.email and a.email:
                prof.email = a.email
            prof.add_credits(a.subject_code,
                            Credits(a.practice_credits, CreditType.PRACTICE))
        logger.info("Professors (with P credits): %d", len(professors))
        return list(professors.values())

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _cell(row, idx) -> str:
        try:
            val = row.iloc[idx]
        except (IndexError, KeyError):
            return ""
        if pd.isna(val):
            return ""
        return str(val).strip()

    @staticmethod
    def _num(row, idx) -> float:
        try:
            val = row.iloc[idx]
        except (IndexError, KeyError):
            return 0.0
        if pd.isna(val):
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    @classmethod
    def _int(cls, row, idx) -> Optional[int]:
        val = cls._num(row, idx)
        return int(val) if val else None
