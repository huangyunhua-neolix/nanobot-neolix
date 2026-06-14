from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates._constants import RUBRIC_PASS_THRESHOLD
from nanobot.evolve.judges.calibration import CalibrationRecord
from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate


class SemanticFidelityGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = True

    @property
    def name(self) -> str:
        return "4-semantic-fidelity"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = time.monotonic()
        pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
        score = pool.score(
            CalibrationRecord(
                record_id=f"semantic:{candidate.content_hash}",
                human_scores={"process": 1.0, "output": 1.0, "token": 1.0},
                input_payload={
                    "baselineBody": baseline.body_md,
                    "candidateBody": candidate.body_md,
                    "expectedRedacted": baseline.body_md,
                },
            )
        )
        passed = score.aggregate >= RUBRIC_PASS_THRESHOLD
        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict="pass" if passed else "fail",
            metrics={
                "semantic_process": score.process,
                "semantic_output": score.output,
                "semantic_token": score.token,
                "semantic_aggregate": score.aggregate,
            },
            evidence={"judge_model": "local/deterministic"},
            failure_reason=None if passed else "semantic-fidelity-below-threshold",
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
