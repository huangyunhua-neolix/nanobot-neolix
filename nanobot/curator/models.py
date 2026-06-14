"""Curator report and proposal models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CuratorAction(StrEnum):
    KEEP = "keep"
    PROTECT = "protect"
    DELETE_CANDIDATE = "delete_candidate"
    MERGE_CANDIDATE = "merge_candidate"
    PATCH_CANDIDATE = "patch_candidate"


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ApplyStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    NOT_APPLICABLE = "not_applicable"
    ELIGIBLE = "eligible"
    DELETED = "deleted"
    SKIPPED_PROTECTED = "skipped_protected"
    SKIPPED_NON_AGENT = "skipped_non_agent"
    SKIPPED_UNKNOWN_ORIGIN = "skipped_unknown_origin"
    SKIPPED_MISSING = "skipped_missing"
    SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"
    SKIPPED_UNSUPPORTED_ACTION = "skipped_unsupported_action"
    REFUSED_FORCED_DRY_RUN = "refused_forced_dry_run"
    FAILED = "failed"


class ReportMode(StrEnum):
    DRY_RUN = "dry_run"
    APPLY = "apply"
    FORCED_DRY_RUN = "forced_dry_run"


class AuxVerdict(StrEnum):
    SUPPORT = "support"
    CAUTION = "caution"
    REJECT = "reject"


ReasonCode = Literal[
    "protected_origin",
    "protected_unknown_origin",
    "protected_name",
    "protected_pattern",
    "protected_always_on",
    "recent_use",
    "too_fresh",
    "not_enough_views",
    "zero_uses_after_views",
    "stale_since_last_use",
    "stale_since_created",
    "patch_history_caps_confidence",
    "recent_patch_activity",
    "shadow_unmasking_caps_confidence",
    "merge_similarity",
    "patch_churn_low_use",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalReason(StrictModel):
    code: ReasonCode
    params: dict[str, int | float | str | bool] = Field(default_factory=dict)


class CuratorWarning(StrictModel):
    code: str
    message: str


class CuratorProposal(StrictModel):
    name: str
    origin: Literal["user", "agent", "builtin", "unknown"]
    action: CuratorAction
    confidence: Confidence
    reasons: list[ProposalReason] = Field(default_factory=list)
    protected: bool = False
    apply_status: ApplyStatus = ApplyStatus.NOT_REQUESTED
    aux_verdict: AuxVerdict | None = None


class CuratorReport(StrictModel):
    mode: ReportMode
    skills_scanned: int
    protected: int
    proposals: list[CuratorProposal] = Field(default_factory=list)
    warnings: list[CuratorWarning] = Field(default_factory=list)
