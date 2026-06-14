import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from nanobot.evolve.gates import GateResult
from nanobot.evolve.harness import RunManifest as HarnessRunManifest
from nanobot.evolve.harness import load_manifest as harness_load_manifest
from nanobot.evolve.schemas import (
    JudgeSummary,
    RubricScore,
    RubricWeights,
    RunManifest,
    ValidationFailure,
    assert_odd_pool_size,
    dump_manifest,
    load_manifest,
)


def test_rubric_weights_defaults_sum_to_one():
    w = RubricWeights()
    assert w.process == 0.4
    assert w.output == 0.4
    assert w.token == 0.2
    assert abs((w.process + w.output + w.token) - 1.0) < 1e-9


def test_rubric_weights_bad_sum_raises_with_sum_in_message():
    with pytest.raises(ValidationError) as exc_info:
        RubricWeights(process=0.5, output=0.5, token=0.5)
    assert "1.500000" in str(exc_info.value)


def test_assert_odd_pool_size_even_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        assert_odd_pool_size(2, context="x")


def test_assert_odd_pool_size_zero_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        assert_odd_pool_size(0, context="x")


def test_assert_odd_pool_size_odd_returns_none():
    assert assert_odd_pool_size(3, context="x") is None


def test_rubric_score_valid_construction():
    score = RubricScore(process=0.5, output=0.7, token=0.3, aggregate=0.5)
    dumped = score.model_dump()
    assert dumped == {"process": 0.5, "output": 0.7, "token": 0.3, "aggregate": 0.5}
    round_trip = RubricScore(**dumped)
    assert round_trip == score


def test_rubric_score_field_out_of_range_rejected():
    with pytest.raises(ValidationError):
        RubricScore(process=1.5, output=0.5, token=0.3, aggregate=0.5)


def test_rubric_score_aggregate_out_of_range_rejected():
    with pytest.raises(ValidationError):
        RubricScore(process=0.5, output=0.5, token=0.3, aggregate=-0.1)


def test_rubric_weights_negative_weight_rejected():
    with pytest.raises(ValidationError):
        RubricWeights(process=-0.1, output=0.6, token=0.5)


def test_rubric_weights_tolerance_edge_inside():
    # sum equals 1.0 - 5e-7 (within 1e-6 tolerance) -> accepted
    w = RubricWeights(process=0.4, output=0.4, token=0.2 - 5e-7)
    assert abs((w.process + w.output + w.token) - 1.0) <= 1e-6


def test_rubric_weights_tolerance_edge_outside():
    # sum equals 1.0 - 5e-6 (outside 1e-6 tolerance) -> ValidationError
    with pytest.raises(ValidationError):
        RubricWeights(process=0.4, output=0.4, token=0.2 - 5e-6)


def test_assert_odd_pool_size_one_returns_none():
    assert assert_odd_pool_size(1, context="x") is None


def test_assert_odd_pool_size_negative_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        assert_odd_pool_size(-1, context="x")


# ---------------------------------------------------------------------------
# M5 shared schema / harness compatibility
# ---------------------------------------------------------------------------


def _judge_summary_for_m5_schema_tests() -> JudgeSummary:
    return JudgeSummary(
        record_count=0,
        median_aggregate=0.0,
        median_process=0.0,
        median_output=0.0,
        median_token=0.0,
        consensus_split_count=0,
    )


def test_harness_reexports_run_manifest_for_m5_compatibility() -> None:
    assert HarnessRunManifest is RunManifest
    assert harness_load_manifest is load_manifest


def test_validation_failure_shape_uses_safe_fields() -> None:
    failure = ValidationFailure(
        candidate_index=1,
        candidate_hash="abc123",
        reason_code="frontmatter-invalid",
        reason="frontmatter-invalid",
    )

    assert failure.model_dump(by_alias=True) == {
        "candidateIndex": 1,
        "candidateHash": "abc123",
        "reasonCode": "frontmatter-invalid",
        "reason": "frontmatter-invalid",
    }


def test_run_manifest_m5_fields_have_defaults_for_m4_compatibility(tmp_path: Path) -> None:
    raw = {
        "runId": "run-xyz",
        "startedAt": "2026-01-01T00:00:00Z",
        "finishedAt": "2026-01-01T00:05:00Z",
        "nanobotVersion": "0.0.0",
        "evolveExtraVersion": {"dspy": "2.4.0"},
        "skillName": "demo-skill",
        "baselineHash": "basehash00112233",
        "candidateHashes": ["candhash44556677"],
        "promotedCandidateHash": None,
        "gateVerdicts": [],
        "judgeSummary": _judge_summary_for_m5_schema_tests().model_dump(by_alias=True),
        "finalStatus": "no_improvement",
        "tiersUsed": ["A", "C"],
        "recordCountPerTier": {"A": 0, "C": 0},
        "judgePoolHealth": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    manifest = load_manifest(path)

    assert manifest.optimizer_name is None
    assert manifest.validation_failures == []
    assert manifest.artifact_paths == {}


def test_run_manifest_accepts_rejected_by_validation_and_artifact_paths(tmp_path: Path) -> None:
    manifest = RunManifest(
        run_id="run-xyz",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        nanobot_version="0.0.0",
        evolve_extra_version={"optimizer": "external"},
        skill_name="demo-skill",
        baseline_hash="basehash00112233",
        candidate_hashes=[],
        promoted_candidate_hash=None,
        gate_verdicts=[
            GateResult(
                gate_name="1-test-pass",
                candidate_hash="candhash",
                baseline_hash="basehash00112233",
                verdict="fail",
                metrics={},
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                duration_ms=1,
            )
        ],
        judge_summary=_judge_summary_for_m5_schema_tests(),
        final_status="rejected_by_validation",
        tiers_used=["A", "C"],
        record_count_per_tier={"A": 0, "C": 0},
        judge_pool_health={},
        optimizer_name="external-wrapper",
        optimizer_seed=None,
        validation_failures=[
            ValidationFailure(
                candidate_index=0,
                candidate_hash="candhash",
                reason_code="empty-content",
                reason="empty-content",
            )
        ],
        artifact_paths={"report": "report.md", "optimizer_input": "optimizer/optimizer_input.json"},
    )
    path = tmp_path / "manifest.json"

    dump_manifest(path, manifest)
    loaded = load_manifest(path)

    assert loaded.final_status == "rejected_by_validation"
    assert loaded.validation_failures[0].candidate_index == 0
    assert loaded.artifact_paths["optimizer_input"] == "optimizer/optimizer_input.json"
