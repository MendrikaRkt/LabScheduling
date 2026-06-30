"""Constraint entity: declarative representation of a solver constraint."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConstraintKind(str, Enum):
    """Categories of constraints known to the optimization engine."""
    NO_SAME_SUBJECT_SLOT = "C1"     # no 2 sessions same subject/slot/week
    NO_SAME_ROOM_SLOT = "C4"        # no 2 sessions same room/slot/week
    CHRONOLOGICAL_ORDER = "C5"      # ordering of sessions within a group
    RESERVATION = "RESV"            # reserved slot (soft penalty)
    PARITY = "PARITY"               # even/odd alternation (soft)
    FRIDAY_CAP = "FRIDAY"           # Friday anti-bottleneck (soft)


class ConstraintHardness(str, Enum):
    HARD = "hard"     # must be satisfied
    SOFT = "soft"     # penalized in the objective


@dataclass(frozen=True)
class Constraint:
    """Description of a constraint (metadata for auditing/diagnostics).

    Concrete constraints are posted on the CP-SAT model by the
    ConstraintManager; this entity is used to describe, count and audit them
    independently of the solver.
    """
    kind: ConstraintKind
    hardness: ConstraintHardness
    weight: int = 0          # weight in the objective if SOFT
    description: str = ""

    @property
    def is_soft(self) -> bool:
        return self.hardness == ConstraintHardness.SOFT
