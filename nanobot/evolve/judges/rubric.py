from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import Field, computed_field, field_validator, model_validator

from nanobot.evolve._base import EvolveBase, FrozenEvolveBase
from nanobot.evolve.schemas import RubricScore, RubricWeights, assert_odd_pool_size

if TYPE_CHECKING:
    from nanobot.evolve.judges.calibration import CalibrationRecord


class JudgeConfig(EvolveBase):
    model: str


class JudgeResult(EvolveBase):
    eval_record_id: str
    judge_model: str
    score: RubricScore
    reasoning: str
    timestamp: datetime
    prompt_template_version: str


class JudgeConsensus(EvolveBase):
    eval_record_id: str
    judges: list[JudgeResult]
    median_score: RubricScore
    inter_judge_variance: dict[str, float]
    consensus_verdict: Literal["agree", "split", "single"]


class JudgePool(FrozenEvolveBase):
    judges: list[JudgeConfig] = Field(..., min_length=1)
    weights: RubricWeights = Field(default_factory=RubricWeights)
    require_consensus: bool = False
    min_quorum: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _validate_quorum_bounds(self) -> "JudgePool":
        if self.min_quorum is not None and self.min_quorum > len(self.judges):
            raise ValueError(
                f"JudgePool.min_quorum={self.min_quorum} exceeds len(judges)={len(self.judges)}"
            )
        return self

    @field_validator("judges")
    @classmethod
    def _odd_pool_only(cls, v: list[JudgeConfig]) -> list[JudgeConfig]:
        assert_odd_pool_size(len(v), context="JudgePool.judges")
        return v

    @computed_field  # type: ignore[misc]
    @property
    def effective_min_quorum(self) -> int:
        if self.min_quorum is not None:
            return self.min_quorum
        return (len(self.judges) // 2) + 1

    def score(self, record: "CalibrationRecord") -> RubricScore:
        """Return a deterministic local rubric score for offline gate checks.

        Provider-backed judges can replace this path in a later milestone. This
        default scorer is intentionally simple and dependency-free so calibration
        and gate 4 have a concrete public entry point now.
        """
        candidate_body = str(record.input_payload.get("candidateBody", "")).strip()
        baseline_body = str(record.input_payload.get("baselineBody", "")).strip()
        expected = str(record.input_payload.get("expectedRedacted", "")).strip()
        if not candidate_body:
            return RubricScore(process=0.0, output=0.0, token=0.0, aggregate=0.0)

        process = 1.0 if "TODO" not in candidate_body and "TBD" not in candidate_body else 0.5
        output = 1.0
        expected_terms = {
            token.strip(".,:;!?()[]{}").lower()
            for token in expected.split()
            if len(token.strip(".,:;!?()[]{}")) >= 5
        }
        candidate_terms = {
            token.strip(".,:;!?()[]{}").lower()
            for token in candidate_body.split()
            if len(token.strip(".,:;!?()[]{}")) >= 5
        }
        if (
            expected
            and expected.lower() not in candidate_body.lower()
            and expected_terms.isdisjoint(candidate_terms)
        ):
            output = 0.8
        if baseline_body and candidate_body == baseline_body:
            output = min(output, 0.7)
        token = 0.9 if len(candidate_body) >= len(baseline_body) else 0.8
        aggregate = (
            process * self.weights.process
            + output * self.weights.output
            + token * self.weights.token
        )
        return RubricScore(
            process=round(process, 6),
            output=round(output, 6),
            token=round(token, 6),
            aggregate=round(aggregate, 6),
        )
