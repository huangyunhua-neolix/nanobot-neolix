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
    review_readiness: "ReviewReadiness | None" = None


class JudgeSummary(EvolveBase):
    record_count: int
    median_aggregate: float
    median_process: float
    median_output: float
    median_token: float
    consensus_split_count: int


class JudgeProviderIdentity(EvolveBase):
    provider_name: str
    base_url: str | None = None
    api_version: str | None = None
    model_id: str
    prompt_template_version: str
    rubric_version: str
    score_schema_version: str = "2"


class JudgeEvidence(EvolveBase):
    record_id: str
    judge_mode: Literal["local_fallback", "aux_llm"]
    provider_identity: JudgeProviderIdentity | None = None
    score: RubricScore
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_redacted: str | None = None
    disagreement: dict[str, float] = Field(default_factory=dict)
    calibrated: bool = False


class JudgeRunSummary(EvolveBase):
    judge_mode: Literal["local_fallback", "aux_llm", "mixed"]
    calibrated: bool
    provider_identity: JudgeProviderIdentity | None = None
    evidence_count: int = Field(ge=0)
    median_aggregate: float = Field(ge=0.0, le=1.0)
    min_axis_score: float = Field(ge=0.0, le=1.0)
    disagreement_max: float | None = Field(default=None, ge=0.0, le=1.0)


class ToolContractSnapshot(EvolveBase):
    tool_name: str
    description_text: str = ""
    parameters_schema: dict[str, object] = Field(default_factory=dict)
    source_kind: Literal["builtin", "mcp", "unknown"]
    schema_hash: str = Field(min_length=1)


class ToolMetadataCandidate(EvolveBase):
    tool_name: str
    baseline_schema_hash: str = Field(min_length=1)
    proposed_schema: dict[str, object]
    intended_improvement: str = Field(min_length=1, max_length=2000)
    risk_assessment: str = Field(min_length=1, max_length=2000)


class ToolMetadataValidationResult(EvolveBase):
    tool_name: str
    baseline_schema_hash: str = Field(min_length=1)
    verdict: Literal["accept", "reject"]
    reason_code: str | None = None
    reason: str | None = None
    changed_paths: list[str] = Field(default_factory=list)
    judge_evidence_path: str | None = None

    @model_validator(mode="after")
    def _reject_requires_reason_code(self) -> "ToolMetadataValidationResult":
        if self.verdict == "reject" and self.reason_code is None:
            raise ValueError(
                "ToolMetadataValidationResult with verdict='reject' requires reason_code to be non-None"
            )
        return self


class PromptTemplateSnapshot(EvolveBase):
    skill_name: str
    source_kind: Literal["bundled"] = "bundled"
    source_identifier: str
    frontmatter_hash: str = Field(min_length=1)
    body_hash: str = Field(min_length=1)
    cache_key_hash: str = Field(min_length=1)
    editable_region_count: int = Field(ge=0)
    body_line_count: int = Field(ge=0)
    snapshot_hash: str = Field(min_length=1)
    body_text: str


class PromptTemplateCandidate(EvolveBase):
    skill_name: str
    baseline_snapshot_hash: str = Field(min_length=1)
    proposed_body: str
    intended_improvement: str = Field(min_length=1, max_length=2000)
    risk_assessment: str = Field(min_length=1, max_length=2000)
    cache_impact_claim: str = Field(min_length=1, max_length=2000)


class PromptTemplateValidationResult(EvolveBase):
    skill_name: str
    baseline_snapshot_hash: str = Field(min_length=1)
    verdict: Literal["accept", "reject"]
    cache_impact: Literal[
        "cache_neutral",
        "cache_sensitive_rejected",
        "cache_unknown_rejected",
        "candidate_noop",
    ]
    reason_code: str | None = None
    reason: str | None = None
    changed_line_numbers: list[int] = Field(default_factory=list)
    judge_evidence_path: str | None = None

    @model_validator(mode="after")
    def _reject_requires_reason_code(self) -> "PromptTemplateValidationResult":
        if self.verdict == "reject" and self.reason_code is None:
            raise ValueError(
                "PromptTemplateValidationResult with verdict='reject' requires reason_code to be non-None"
            )
        return self


class PromptTemplateCacheImpactCounts(EvolveBase):
    cache_neutral: int = Field(default=0, ge=0)
    cache_sensitive_rejected: int = Field(default=0, ge=0)
    cache_unknown_rejected: int = Field(default=0, ge=0)
    candidate_absent: int = Field(default=0, ge=0)
    candidate_noop: int = Field(default=0, ge=0)


class ValidationFailure(EvolveBase):
    candidate_index: int = Field(ge=0)
    candidate_hash: str
    reason_code: str
    reason: str


class EvolutionProposalContext(EvolveBase):
    proposal_id: str = Field(min_length=1, max_length=500)
    source: Literal["manual", "curator", "dream"]


class DiffStats(EvolveBase):
    files_changed: int = Field(default=0, ge=0)
    insertions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)


class ReviewReadiness(EvolveBase):
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    requires_human_approval: bool = True


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
    diff_stats: DiffStats | None = None
    requires_human_approval: bool = False
    judge_run_summary: JudgeRunSummary | None = None
    judge_evidence_paths: dict[str, str] = Field(default_factory=dict)
    tool_metadata_artifact_paths: dict[str, str] = Field(default_factory=dict)
    prompt_template_artifact_paths: dict[str, str] = Field(default_factory=dict)
    evolution_proposal: EvolutionProposalContext | None = None


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
    data = manifest.model_dump(mode="json", by_alias=True)
    if data.get("evolutionProposal") is None:
        data.pop("evolutionProposal", None)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
