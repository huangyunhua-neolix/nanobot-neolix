from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Literal

from nanobot.evolve._base import EvolveBase

if TYPE_CHECKING:
    from nanobot.evolve.harness import Baseline, Candidate


__all__ = ["Gate", "GateResult", "GATES"]


class GateResult(EvolveBase):
    gate_name: str
    candidate_hash: str
    baseline_hash: str
    verdict: Literal["pass", "fail"]
    metrics: dict[str, float]
    evidence: dict[str, str] | None = None
    failure_reason: str | None = None
    timestamp: datetime
    duration_ms: int


class Gate(ABC):
    NONDETERMINISTIC: ClassVar[bool] = False

    # Declaration-time set of all Gate subclasses (including abstract test doubles);
    # consumed by the spec §6.4.1 contract test to enforce NONDETERMINISTIC declaration.
    # Do NOT iterate for evaluate() — use the GATES execution registry below instead.
    _subclasses: ClassVar[list[type["Gate"]]] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Dedup against repeat imports / importlib.reload / pytest re-collection so
        # the contract test's iteration over _subclasses doesn't observe duplicates.
        if cls not in Gate._subclasses:
            Gate._subclasses.append(cls)

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult: ...


# Ordered EXECUTION registry — concrete Gate INSTANCES only, appended at module
# bottom after gate-implementations land in t-08/09/10. Harness iterates THIS list
# for evaluate(). Order MUST match the "N-" name prefix (gate 1 first, etc.) —
# §6.4.1 contract test (t-07) enforces this.
GATES: list[Gate] = []

# Local imports kept at bottom to avoid a circular import: each gate module
# `from nanobot.evolve.gates import Gate, GateResult`, so this module must
# finish defining those names before importing the concrete subclasses.
from nanobot.evolve.gates.cache_compat import CacheCompatGate  # noqa: E402
from nanobot.evolve.gates.skill_size import SkillSizeGate  # noqa: E402
from nanobot.evolve.gates.test_pass import TestPassGate  # noqa: E402

GATES.append(TestPassGate())
GATES.append(SkillSizeGate())
GATES.append(CacheCompatGate())
