from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.gates import Gate, GateResult

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate

_REQUIRED_ARTIFACT_KEYS: tuple[str, ...] = (
    "manifest",
    "report",
    "diff",
    "pr_body",
    "optimizer_input",
    "optimizer_output",
)


def _failure_reason(missing_artifacts: list[str], missing_requirements: list[str]) -> str:
    parts: list[str] = []
    if missing_artifacts:
        parts.append(f"missing artifacts: {', '.join(missing_artifacts)}")
    approval_requirements = [
        requirement for requirement in missing_requirements if requirement != "readiness-missing"
    ]
    if approval_requirements:
        parts.append(f"missing approval requirement: {', '.join(approval_requirements)}")
    if "readiness-missing" in missing_requirements:
        parts.append("readiness-missing")
    return f"human-review-readiness-incomplete: {'; '.join(parts)}"


class HumanReviewGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "5-human-review"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = time.monotonic()
        readiness = candidate.review_readiness
        artifact_paths = readiness.artifact_paths if readiness is not None else {}
        present_artifacts = [
            key
            for key in _REQUIRED_ARTIFACT_KEYS
            if isinstance(artifact_paths.get(key), str) and artifact_paths[key].strip()
        ]
        missing_artifacts = [
            key for key in _REQUIRED_ARTIFACT_KEYS if key not in present_artifacts
        ]
        requires_approval = bool(
            readiness is not None and readiness.requires_human_approval is True
        )
        missing_requirements: list[str] = []
        if readiness is None:
            missing_requirements.append("readiness-missing")
        if not requires_approval:
            missing_requirements.append("requires_human_approval")

        passed = not missing_artifacts and not missing_requirements
        review_checks_present = len(present_artifacts) + (1 if requires_approval else 0)
        review_checks_required = len(_REQUIRED_ARTIFACT_KEYS) + 1
        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict="pass" if passed else "fail",
            metrics={
                "review_artifacts_present": float(len(present_artifacts)),
                "review_artifacts_required": float(len(_REQUIRED_ARTIFACT_KEYS)),
                "review_checks_present": float(review_checks_present),
                "review_checks_required": float(review_checks_required),
                "requires_human_approval": 1.0 if requires_approval else 0.0,
            },
            evidence={
                "required_artifact_keys": ",".join(_REQUIRED_ARTIFACT_KEYS),
                "approval_status": "external-human-approval-required-not-granted",
                "requires_human_approval": "true" if requires_approval else "false",
            },
            failure_reason=None if passed else _failure_reason(missing_artifacts, missing_requirements),
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
