from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Literal, Optional

from nanobot.evolve._base import EvolveBase

if TYPE_CHECKING:
    from nanobot.evolve.harness import Baseline, Candidate


class GateResult(EvolveBase):
    gate_name: str
    candidate_hash: str
    baseline_hash: str
    verdict: Literal["pass", "fail"]
    metrics: dict[str, float]
    evidence: Optional[dict[str, str]] = None
    failure_reason: Optional[str] = None
    timestamp: datetime
    duration_ms: int


class Gate(ABC):
    NONDETERMINISTIC: ClassVar[bool] = False
    _subclasses: ClassVar[list[type["Gate"]]] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        Gate._subclasses.append(cls)

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult: ...


GATES: list[Gate] = []  # populated by import side-effect from concrete gate modules
# Note: concrete imports added at the bottom AFTER gates land (t-08..t-10).
