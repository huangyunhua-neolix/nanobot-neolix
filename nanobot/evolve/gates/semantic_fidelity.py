from __future__ import annotations

import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.artifacts import atomic_write_text
from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates._constants import RUBRIC_PASS_THRESHOLD

if TYPE_CHECKING:
    from nanobot.evolve.judges.auxiliary import AuxJudgeClient
    from nanobot.evolve.schemas import Baseline, Candidate, JudgeEvidence


class SemanticEvidenceRecorder(Gate):
    NONDETERMINISTIC: ClassVar[bool] = True

    def __init__(self, gate: Gate, *, evidence_dir: Path | None = None) -> None:
        self._gate = gate
        self._evidence_dir = evidence_dir
        self._evidence_rows: list[str] = []

    @property
    def name(self) -> str:
        return self._gate.name

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        result = self._gate.evaluate(candidate, baseline)
        if (
            result.gate_name == "4-semantic-fidelity"
            and result.evidence is not None
            and result.evidence.get("judge_evidence_path") == "judge_evidence.jsonl"
        ):
            self._record_result_evidence(result)
        return result

    def cleanup_after_timeout(self) -> None:
        self._gate.cleanup_after_timeout()

    def publish_evidence(self) -> str | None:
        if self._evidence_dir is None or not self._evidence_rows:
            return None
        path = self._evidence_dir / "judge_evidence.jsonl"
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(mode):
                raise OSError(f"semantic judge evidence path is not a regular file: {path}")
        atomic_write_text(path, "\n".join(self._evidence_rows) + "\n")
        return path.name

    def _record_result_evidence(self, result: GateResult) -> None:
        from nanobot.evolve.schemas import JudgeEvidence, RubricScore

        evidence = JudgeEvidence(
            record_id=f"semantic:{result.candidate_hash}",
            judge_mode=result.evidence.get("judge_mode", "local_fallback"),  # type: ignore[arg-type]
            score=RubricScore(
                process=float(result.metrics.get("semantic_process", 0.0)),
                output=float(result.metrics.get("semantic_output", 0.0)),
                token=float(result.metrics.get("semantic_token", 0.0)),
                aggregate=float(result.metrics.get("semantic_aggregate", 0.0)),
            ),
            calibrated=result.evidence.get("calibrated") == "true",
        )
        self._evidence_rows.append(evidence.model_dump_json(by_alias=True))


class SemanticFidelityGate(SemanticEvidenceRecorder):
    NONDETERMINISTIC: ClassVar[bool] = True

    def __init__(
        self,
        *,
        evidence_dir: Path | None = None,
        require_external: bool = False,
        aux_client: "AuxJudgeClient | None" = None,
    ) -> None:
        super().__init__(self, evidence_dir=evidence_dir)
        self._require_external = require_external
        self._aux_client = aux_client

    @property
    def name(self) -> str:
        return "4-semantic-fidelity"

    def cleanup_after_timeout(self) -> None:
        pass

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        from nanobot.evolve.judges.calibration import CalibrationRecord
        from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool

        start = time.monotonic()
        pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
        record = CalibrationRecord(
            record_id=f"semantic:{candidate.content_hash}",
            human_scores={"process": 1.0, "output": 1.0, "token": 1.0},
            input_payload={
                "baselineBody": baseline.body_md,
                "candidateBody": candidate.body_md,
                "expectedRedacted": baseline.body_md,
            },
        )
        try:
            judge_evidence = pool.score_with_evidence(
                record,
                aux_client=self._aux_client,
                require_external=self._require_external,
            )
        except ValueError as exc:
            return self._failure(candidate, baseline, start, str(exc))

        evidence_path = self._write_evidence(judge_evidence)
        score = judge_evidence.score
        passed = score.aggregate >= RUBRIC_PASS_THRESHOLD
        duration_ms = int((time.monotonic() - start) * 1000)
        gate_evidence = {
            "judge_model": judge_evidence.provider_identity.model_id
            if judge_evidence.provider_identity is not None
            else "local/deterministic",
            "judge_mode": judge_evidence.judge_mode,
            "calibrated": str(judge_evidence.calibrated).lower(),
        }
        if evidence_path is not None:
            gate_evidence["judge_evidence_path"] = evidence_path
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
            evidence=gate_evidence,
            failure_reason=None if passed else "semantic-fidelity-below-threshold",
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )

    def _failure(
        self,
        candidate: "Candidate",
        baseline: "Baseline",
        start: float,
        reason: str,
    ) -> GateResult:
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict="fail",
            metrics={
                "semantic_process": 0.0,
                "semantic_output": 0.0,
                "semantic_token": 0.0,
                "semantic_aggregate": 0.0,
            },
            evidence={"judge_mode": "none", "calibrated": "false"},
            failure_reason=reason,
            timestamp=datetime.now(timezone.utc),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    def _write_evidence(self, evidence: JudgeEvidence) -> str | None:
        if self._evidence_dir is None:
            return None
        self._evidence_rows.append(evidence.model_dump_json(by_alias=True))
        return "judge_evidence.jsonl"
