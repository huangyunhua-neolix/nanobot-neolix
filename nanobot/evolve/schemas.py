import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, model_validator

from nanobot.evolve._base import EvolveBase, FrozenEvolveBase
from nanobot.evolve.gates import GateResult


class RubricScore(EvolveBase):
    process: float = Field(ge=0.0, le=1.0)
    output: float = Field(ge=0.0, le=1.0)
    token: float = Field(ge=0.0, le=1.0)
    aggregate: float = Field(ge=0.0, le=1.0)


class RubricWeights(EvolveBase):
    process: float = Field(default=0.4, ge=0.0, le=1.0)
    output: float = Field(default=0.4, ge=0.0, le=1.0)
    token: float = Field(default=0.2, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "RubricWeights":
        s = self.process + self.output + self.token
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"RubricWeights must sum to 1.0 (got {s:.6f}); "
                f"process={self.process}, output={self.output}, token={self.token}"
            )
        return self


class SkillFrontmatter(EvolveBase):
    name: str
    description: str
    origin: Literal["bundled", "user", "agent"]
    created_by: str
    created_at: datetime
    evolved_from_run: Optional[str] = None
    evolved_at: Optional[datetime] = None
    parent_skill_hash: Optional[str] = None
    optimizer_name: Optional[str] = None
    optimizer_version: Optional[str] = None


class SkillContent(EvolveBase):
    skill_name: str
    skill_md_content: str
    frontmatter: SkillFrontmatter
    body_md: str
    cache_key_hash: str
    size_metrics: dict[str, int]
    content_hash: str


class Baseline(SkillContent):
    loaded_from: str
    loaded_at: datetime


class Candidate(SkillContent):
    parent_baseline_hash: str
    gepa_iteration: int
    gepa_seed: Optional[int] = None


class JudgeSummary(EvolveBase):
    record_count: int
    median_aggregate: float
    median_process: float
    median_output: float
    median_token: float
    consensus_split_count: int


class ValidationFailure(EvolveBase):
    candidate_index: int = Field(ge=0)
    candidate_hash: str
    reason_code: str
    reason: str


class RunManifest(FrozenEvolveBase):
    run_id: str
    started_at: datetime
    finished_at: datetime
    nanobot_version: str
    evolve_extra_version: dict[str, str]
    skill_name: str
    baseline_hash: str
    candidate_hashes: list[str]
    promoted_candidate_hash: Optional[str]
    gate_verdicts: list[GateResult]
    judge_summary: JudgeSummary
    final_status: Literal[
        "promoted_to_pr",
        "rejected_by_gate",
        "rejected_by_validation",
        "no_improvement",
        "harness_error",
    ]
    tiers_used: list[Literal["A", "B", "C", "D"]]
    record_count_per_tier: dict[str, int]
    judge_pool_health: dict[str, str]
    optimizer_name: str | None = None
    optimizer_version: str | None = None
    optimizer_seed: int | None = None
    validation_failures: list[ValidationFailure] = Field(default_factory=list)
    subprocess_runtime_ms: int | None = None
    artifact_paths: dict[str, str] = Field(default_factory=dict)


def assert_odd_pool_size(n: int, *, context: str) -> None:
    if n < 1 or n % 2 == 0:
        raise ValueError(
            f"{context}: judge pool size must be odd and >= 1 (got {n})"
        )


def load_manifest(path: Path) -> RunManifest:
    """Load and validate a RunManifest from JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest JSON at {path}: {exc}") from exc
    return RunManifest.model_validate(raw)


def dump_manifest(path: Path, manifest: RunManifest) -> None:
    """Write a RunManifest JSON file using the model's alias contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )
