from typing import Literal

from pydantic import Field, model_validator

from nanobot.evolve._base import EvolveBase


class OptimizerInput(EvolveBase):
    schema_version: Literal["1"] = "1"
    run_id: str
    skill_name: str
    baseline_hash: str
    baseline_skill_md_redacted: str
    eval_records_path: str
    output_dir: str
    max_candidates: int = Field(ge=1)
    timeout_seconds: int = Field(ge=1)
    seed: int


class OptimizerCandidate(EvolveBase):
    skill_name: str
    skill_md_content: str
    score: float = Field(ge=0.0, le=1.0)
    iteration: int = Field(ge=1)
    rationale: str = Field(max_length=2000)


class OptimizerError(EvolveBase):
    code: Literal["no_improvement", "invalid_input", "optimizer_failed"]
    message: str = Field(max_length=500)


class OptimizerResult(EvolveBase):
    schema_version: Literal["1"] = "1"
    candidates: list[OptimizerCandidate] = Field(default_factory=list)
    error: OptimizerError | None = None
    optimizer_name: str
    optimizer_version: str | None = None
    seed: int | None = None

    @model_validator(mode="after")
    def _validate_result_shape(self) -> "OptimizerResult":
        if self.error is None:
            if not self.candidates:
                raise ValueError("success result requires at least one candidate")
            return self
        if self.error.code == "no_improvement":
            if self.candidates:
                raise ValueError("no_improvement result must not include candidates")
            return self
        raise ValueError("invalid_input and optimizer_failed are adapter errors")
