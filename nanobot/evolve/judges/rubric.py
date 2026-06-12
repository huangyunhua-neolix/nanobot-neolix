from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, computed_field, field_validator, model_validator

from nanobot.evolve._base import EvolveBase
from nanobot.evolve.schemas import RubricScore, RubricWeights, assert_odd_pool_size


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


class JudgePool(EvolveBase):
    model_config = ConfigDict(**{**EvolveBase.model_config, "frozen": True})
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
