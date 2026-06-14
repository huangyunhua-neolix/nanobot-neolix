from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.gates import Gate, GateResult

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate

_REQUIRED_REVIEW_FLAGS: tuple[str, ...] = (
    "review_manifest",
    "review_report",
    "review_diff",
    "review_pr_body",
    "review_optimizer_input",
    "review_optimizer_output",
)


class HumanReviewGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "5-human-review"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = time.monotonic()
        missing = [
            name for name in _REQUIRED_REVIEW_FLAGS if candidate.size_metrics.get(name, 0) < 1
        ]
        requires_approval = candidate.size_metrics.get("review_requires_human_approval", 0) >= 1
        if not requires_approval:
            missing.append("review_requires_human_approval")
        passed = not missing
        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict="pass" if passed else "fail",
            metrics={
                "review_artifacts_present": float(
                    sum(
                        1
                        for name in _REQUIRED_REVIEW_FLAGS
                        if candidate.size_metrics.get(name, 0) >= 1
                    )
                ),
                "review_artifacts_required": float(len(_REQUIRED_REVIEW_FLAGS)),
                "requires_human_approval": 1.0 if requires_approval else 0.0,
            },
            evidence={"requires_human_approval": "true" if requires_approval else "false"},
            failure_reason=(
                None if passed else f"human-review-artifacts-incomplete: {', '.join(missing)}"
            ),
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
