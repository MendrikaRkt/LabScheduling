"""ConfigLoader: loads config.yaml and turns it into business objects.

This is the ONLY place that knows the YAML format. The rest of the application
manipulates typed objects (Subject, AppSettings) and does not depend on the
file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Tuple

import yaml

from domain.entities.subject import Subject
from domain.value_objects import Period, TimeBlock, WeekWindow

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "config", "config.yaml",
)


@dataclass
class SolverSettings:
    random_seed: int = 42
    relative_gap: float = 0.02
    time_limit_seconds: int = 300
    num_workers: int = 8
    log_progress: bool = False


@dataclass
class FridaySettings:
    soft_cap: int = 125
    base_penalty: int = 8
    overcap_weight: int = 10


@dataclass
class GroupSizeSettings:
    preferred: int = 12
    max: int = 15
    min: int = 7
    recovery_min: int = 7
    max_extra_groups: int = 3
    computer_lab_max: int = 24
    reduced_max: int = 12


@dataclass
class AppSettings:
    """Typed global configuration of the application."""
    sessions_per_credit: int = 5
    solver: SolverSettings = field(default_factory=SolverSettings)
    friday: FridaySettings = field(default_factory=FridaySettings)
    group_sizes: GroupSizeSettings = field(default_factory=GroupSizeSettings)
    objective_weights: Dict[str, int] = field(default_factory=dict)
    parity_enabled: bool = True
    parity_penalty_weight: int = 50
    semester_1_weeks: int = 14
    semester_2_weeks: int = 20
    days: List[str] = field(default_factory=list)
    time_blocks: List[TimeBlock] = field(default_factory=list)
    holidays: Dict[int, Dict[Tuple[int, int], str]] = field(default_factory=dict)
    subject_blocked_slots: Dict[Tuple[int, str], Dict[Tuple[int, int, int], str]] = \
        field(default_factory=dict)
    known_programs: frozenset = frozenset()
    include_real_names: bool = True
    paths: Dict[str, str] = field(default_factory=dict)
    subjects: Dict[str, Subject] = field(default_factory=dict)

    @property
    def friday_idx(self) -> int:
        return 4

    def semester_weeks(self, semester: int) -> int:
        return self.semester_1_weeks if semester == 1 else self.semester_2_weeks


class ConfigLoader:
    """Loads and parses the YAML configuration file."""

    def __init__(self, path: str = DEFAULT_CONFIG_PATH):
        self.path = path

    def load(self) -> AppSettings:
        with open(self.path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        return self._build(raw)

    # -- helpers ------------------------------------------------------------
    def _build(self, raw: dict) -> AppSettings:
        settings = AppSettings()

        settings.sessions_per_credit = raw.get("credit_system", {}).get(
            "sessions_per_credit", 5)

        s = raw.get("solver", {})
        settings.solver = SolverSettings(
            random_seed=s.get("random_seed", 42),
            relative_gap=s.get("relative_gap", 0.02),
            time_limit_seconds=s.get("time_limit_seconds", 300),
            num_workers=s.get("num_workers", 8),
            log_progress=s.get("log_progress", False),
        )

        f = raw.get("friday_policy", {})
        settings.friday = FridaySettings(
            soft_cap=f.get("soft_cap", 125),
            base_penalty=f.get("base_penalty", 8),
            overcap_weight=f.get("overcap_weight", 10),
        )

        g = raw.get("group_sizes", {})
        settings.group_sizes = GroupSizeSettings(
            preferred=g.get("preferred", 12), max=g.get("max", 15),
            min=g.get("min", 7), recovery_min=g.get("recovery_min", 7),
            max_extra_groups=g.get("max_extra_groups", 3),
            computer_lab_max=g.get("computer_lab_max", 24),
            reduced_max=g.get("reduced_max", 12),
        )

        settings.objective_weights = dict(raw.get("objective_weights", {}))

        p = raw.get("parity", {})
        settings.parity_enabled = p.get("enabled", True)
        settings.parity_penalty_weight = p.get("penalty_weight", 50)

        cal = raw.get("calendar", {})
        settings.semester_1_weeks = cal.get("semester_1_weeks", 14)
        settings.semester_2_weeks = cal.get("semester_2_weeks", 20)
        settings.days = list(cal.get("days", []))
        settings.time_blocks = [
            TimeBlock(id=b["id"], label=b["label"], start=b["start"],
                    end=b["end"], period=Period(b["period"]))
            for b in cal.get("time_blocks", [])
        ]

        # holidays: semester -> {(week, day_idx): label}
        holidays: Dict[int, Dict[Tuple[int, int], str]] = {}
        for sem, entries in (raw.get("holidays", {}) or {}).items():
            holidays[int(sem)] = {(int(w), int(d)): label for w, d, label in entries}
        settings.holidays = holidays

        # subject_blocked_slots
        blocked: Dict[Tuple[int, str], Dict[Tuple[int, int, int], str]] = {}
        sbs = raw.get("subject_blocked_slots", {}) or {}
        label = sbs.get("blocked_label", "Festivo / No disponible")
        for key, spec in (sbs.get("slots", {}) or {}).items():
            sem_str, subj = key.split("|", 1)
            slots = {}
            for w in spec.get("weeks", []):
                for d in spec.get("days", []):
                    for b in spec.get("blocks", []):
                        slots[(w, d, b)] = label
            blocked[(int(sem_str), subj)] = slots
        settings.subject_blocked_slots = blocked

        settings.known_programs = frozenset(raw.get("known_programs", []))
        settings.include_real_names = raw.get("include_real_names", True)
        settings.paths = dict(raw.get("paths", {}))

        # subjects -> Subject entities
        subjects = {}
        for code, cfg in (raw.get("subjects", {}) or {}).items():
            subjects[code] = Subject(
                code=code,
                curso_num=cfg["curso_num"],
                semester=cfg["semester"],
                num_sessions=cfg["num_sessions"],
                window=WeekWindow(cfg["min_week"], cfg["max_week"]),
                max_students=cfg["max_students"],
                lab_rooms=list(cfg.get("lab_rooms", [])),
                keywords=list(cfg.get("keywords", [])),
                keyword_exclude=list(cfg.get("keyword_exclude", [])),
                group_by_program=cfg.get("group_by_program", False),
                shared_group=cfg.get("shared_group"),
                simultaneous_rooms=cfg.get("simultaneous_rooms", False),
                intro_session_paired=cfg.get("intro_session_paired", False),
            )
        settings.subjects = subjects
        return settings


@lru_cache(maxsize=1)
def get_settings(path: str = DEFAULT_CONFIG_PATH) -> AppSettings:
    """Cached access to the configuration (application singleton)."""
    return ConfigLoader(path).load()
