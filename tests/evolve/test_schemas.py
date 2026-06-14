import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from nanobot.evolve.gates import GateResult
from nanobot.evolve.harness import RunManifest as HarnessRunManifest
from nanobot.evolve.harness import load_manifest as harness_load_manifest
from nanobot.evolve.optimizer.schemas import OptimizerError, OptimizerInput, OptimizerResult
from nanobot.evolve.schemas import (
    Candidate,
    DiffStats,
    JudgeEvidence,
    JudgeProviderIdentity,
    JudgeRunSummary,
    JudgeSummary,
    ReviewReadiness,
    RubricScore,
    RubricWeights,
    RunManifest,
    SkillFrontmatter,
    ToolContractSnapshot,
    ToolMetadataCandidate,
    ToolMetadataValidationResult,
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


def _judge_provider_identity() -> JudgeProviderIdentity:
    return JudgeProviderIdentity(
        provider_name="anthropic",
        base_url="https://api.example.invalid",
        api_version="2026-06-14",
        model_id="claude-sonnet-4-6",
        prompt_template_version="semantic-judge-v2",
        rubric_version="rubric-v2",
    )


def test_judge_provider_identity_serializes_full_calibration_surface() -> None:
    identity = _judge_provider_identity()

    dumped = identity.model_dump(by_alias=True)
    assert dumped == {
        "providerName": "anthropic",
        "baseUrl": "https://api.example.invalid",
        "apiVersion": "2026-06-14",
        "modelId": "claude-sonnet-4-6",
        "promptTemplateVersion": "semantic-judge-v2",
        "rubricVersion": "rubric-v2",
        "scoreSchemaVersion": "2",
    }
    assert JudgeProviderIdentity.model_validate(dumped) == identity


def test_judge_evidence_serializes_aux_provider_and_score() -> None:
    evidence = JudgeEvidence(
        record_id="record-1",
        judge_mode="aux_llm",
        provider_identity=_judge_provider_identity(),
        score=RubricScore(process=0.9, output=0.8, token=0.7, aggregate=0.82),
        confidence=0.75,
        reasoning_redacted="Candidate preserves the redacted intent.",
        disagreement={"output": 0.1},
        calibrated=True,
    )

    dumped = evidence.model_dump(by_alias=True)
    assert dumped == {
        "recordId": "record-1",
        "judgeMode": "aux_llm",
        "providerIdentity": _judge_provider_identity().model_dump(by_alias=True),
        "score": {"process": 0.9, "output": 0.8, "token": 0.7, "aggregate": 0.82},
        "confidence": 0.75,
        "reasoningRedacted": "Candidate preserves the redacted intent.",
        "disagreement": {"output": 0.1},
        "calibrated": True,
    }
    assert JudgeEvidence.model_validate(dumped) == evidence


def test_judge_evidence_defaults_to_local_uncalibrated_metadata() -> None:
    evidence = JudgeEvidence(
        record_id="record-1",
        judge_mode="local_fallback",
        score=RubricScore(process=0.9, output=0.8, token=0.7, aggregate=0.82),
    )

    assert evidence.provider_identity is None
    assert evidence.confidence is None
    assert evidence.reasoning_redacted is None
    assert evidence.disagreement == {}
    assert evidence.calibrated is False


def test_judge_run_summary_validates_bounds_and_round_trips() -> None:
    summary = JudgeRunSummary(
        judge_mode="aux_llm",
        calibrated=True,
        provider_identity=_judge_provider_identity(),
        evidence_count=3,
        median_aggregate=0.8,
        min_axis_score=0.6,
        disagreement_max=0.2,
    )

    dumped = summary.model_dump(by_alias=True)
    assert JudgeRunSummary.model_validate(dumped) == summary
    with pytest.raises(ValidationError):
        JudgeRunSummary(
            judge_mode="aux_llm",
            calibrated=True,
            evidence_count=-1,
            median_aggregate=0.8,
            min_axis_score=0.6,
        )
    with pytest.raises(ValidationError):
        JudgeRunSummary(
            judge_mode="aux_llm",
            calibrated=True,
            evidence_count=1,
            median_aggregate=0.8,
            min_axis_score=0.6,
            disagreement_max=1.1,
        )


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


def _judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=2,
        median_aggregate=0.0,
        median_process=0.0,
        median_output=0.0,
        median_token=0.0,
        consensus_split_count=0,
    )


def _frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="Demo skill",
        origin="agent",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _candidate_payload() -> dict[str, object]:
    return {
        "skill_name": "demo-skill",
        "skill_md_content": "---\nname: demo-skill\n---\nUse concise answers.\n",
        "frontmatter": _frontmatter(),
        "body_md": "Use concise answers.\n",
        "cache_key_hash": "cachehash",
        "size_metrics": {"lines": 4},
        "content_hash": "candhash",
        "parent_baseline_hash": "basehash",
        "gepa_iteration": 1,
    }


def _manifest_payload() -> dict[str, object]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "run_id": "run-1",
        "started_at": now,
        "finished_at": now,
        "nanobot_version": "0.0.0",
        "evolve_extra_version": {"optimizer": "fake"},
        "skill_name": "demo-skill",
        "baseline_hash": "basehash",
        "candidate_hashes": ["candhash"],
        "promoted_candidate_hash": "candhash",
        "gate_verdicts": [],
        "judge_summary": _judge_summary(),
        "final_status": "promoted_to_pr",
        "tiers_used": ["A", "C"],
        "record_count_per_tier": {"A": 1, "C": 5},
        "judge_pool_health": {},
    }


def test_diff_stats_model_accepts_patch_counts() -> None:
    stats = DiffStats(files_changed=1, insertions=3, deletions=2)

    assert stats.files_changed == 1
    assert stats.insertions == 3
    assert stats.deletions == 2


def test_review_readiness_defaults_and_serialization() -> None:
    readiness = ReviewReadiness()

    assert readiness.artifact_paths == {}
    assert readiness.requires_human_approval is True
    assert readiness.model_dump(by_alias=True) == {
        "artifactPaths": {},
        "requiresHumanApproval": True,
    }


def test_candidate_review_readiness_defaults_to_none_for_manifest_compatibility() -> None:
    candidate = Candidate(**_candidate_payload())

    assert candidate.review_readiness is None
    assert candidate.model_dump(by_alias=True)["reviewReadiness"] is None


def test_candidate_accepts_review_readiness_model() -> None:
    candidate = Candidate(
        **_candidate_payload(),
        review_readiness=ReviewReadiness(
            artifact_paths={"manifest": "manifest.json"},
            requires_human_approval=True,
        ),
    )

    assert candidate.review_readiness is not None
    assert candidate.review_readiness.artifact_paths["manifest"] == "manifest.json"


def test_manifest_defaults_m5_completion_fields_for_m5_1_compatibility() -> None:
    manifest = RunManifest(**_manifest_payload())

    assert manifest.diff_stats is None
    assert manifest.requires_human_approval is False


def test_manifest_defaults_m6_judge_fields_for_m5_compatibility() -> None:
    manifest = RunManifest(**_manifest_payload())

    assert manifest.judge_run_summary is None
    assert manifest.judge_evidence_paths == {}


def test_manifest_accepts_m6_judge_summary_and_evidence_paths() -> None:
    manifest = RunManifest(
        **_manifest_payload(),
        judge_run_summary=JudgeRunSummary(
            judge_mode="local_fallback",
            calibrated=False,
            evidence_count=1,
            median_aggregate=0.82,
            min_axis_score=0.7,
        ),
        judge_evidence_paths={"semantic_fidelity": "judge_evidence.jsonl"},
    )

    assert manifest.judge_run_summary is not None
    assert manifest.judge_run_summary.judge_mode == "local_fallback"
    assert manifest.judge_evidence_paths == {"semantic_fidelity": "judge_evidence.jsonl"}


def test_manifest_accepts_diff_stats_and_human_review_flag() -> None:
    manifest = RunManifest(
        **_manifest_payload(),
        diff_stats=DiffStats(files_changed=1, insertions=3, deletions=2),
        requires_human_approval=True,
    )

    assert manifest.diff_stats is not None
    assert manifest.diff_stats.insertions == 3
    assert manifest.requires_human_approval is True


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
    assert manifest.judge_run_summary is None
    assert manifest.judge_evidence_paths == {}


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


# ---------------------------------------------------------------------------
# M7 Tool Metadata Schemas
# ---------------------------------------------------------------------------


def test_tool_contract_snapshot_serializes_hash_surface() -> None:
    snapshot = ToolContractSnapshot(
        tool_name="read_file",
        description_text="Read a workspace file.",
        parameters_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace path"}
            },
            "required": ["path"],
        },
        source_kind="builtin",
        schema_hash="a" * 64,
    )

    dumped = snapshot.model_dump(by_alias=True)

    assert dumped == {
        "toolName": "read_file",
        "descriptionText": "Read a workspace file.",
        "parametersSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace path"}
            },
            "required": ["path"],
        },
        "sourceKind": "builtin",
        "schemaHash": "a" * 64,
    }
    assert ToolContractSnapshot.model_validate(dumped) == snapshot


def test_tool_contract_snapshot_rejects_empty_schema_hash() -> None:
    with pytest.raises(ValidationError):
        ToolContractSnapshot(
            tool_name="read_file",
            description_text="Read a workspace file.",
            parameters_schema={},
            source_kind="builtin",
            schema_hash="",
        )


def test_tool_metadata_candidate_uses_proposed_schema_as_single_source() -> None:
    candidate = ToolMetadataCandidate(
        tool_name="read_file",
        baseline_schema_hash="a" * 64,
        proposed_schema={
            "name": "read_file",
            "description": "Read one explicitly requested workspace file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Explicit workspace file path",
                    }
                },
                "required": ["path"],
            },
        },
        intended_improvement="Clarifies that the path must be explicit.",
        risk_assessment="No permission or schema expansion.",
    )

    dumped = candidate.model_dump(by_alias=True)

    assert dumped["toolName"] == "read_file"
    assert dumped["baselineSchemaHash"] == "a" * 64
    assert "candidateDescription" not in dumped
    assert "candidateParameterNotes" not in dumped
    assert ToolMetadataCandidate.model_validate(dumped) == candidate


def test_tool_metadata_candidate_rejects_empty_baseline_schema_hash() -> None:
    with pytest.raises(ValidationError):
        ToolMetadataCandidate(
            tool_name="read_file",
            baseline_schema_hash="",
            proposed_schema={"type": "object"},
            intended_improvement="Clarifies scope.",
            risk_assessment="No permission or schema expansion.",
        )


def test_tool_metadata_candidate_rejects_blank_intended_improvement() -> None:
    with pytest.raises(ValidationError):
        ToolMetadataCandidate(
            tool_name="read_file",
            baseline_schema_hash="a" * 64,
            proposed_schema={"type": "object"},
            intended_improvement="",
            risk_assessment="No permission or schema expansion.",
        )


def test_tool_metadata_candidate_rejects_blank_risk_assessment() -> None:
    with pytest.raises(ValidationError):
        ToolMetadataCandidate(
            tool_name="read_file",
            baseline_schema_hash="a" * 64,
            proposed_schema={"type": "object"},
            intended_improvement="Clarifies scope.",
            risk_assessment="",
        )


def test_tool_metadata_validation_result_round_trips_rejection() -> None:
    result = ToolMetadataValidationResult(
        tool_name="read_file",
        baseline_schema_hash="a" * 64,
        verdict="reject",
        reason_code="tool-permission-expansion",
        reason="tool-permission-expansion: changed text contains 'without permission'",
        changed_paths=["$.description"],
        judge_evidence_path=None,
    )

    dumped = result.model_dump(by_alias=True)

    assert dumped == {
        "toolName": "read_file",
        "baselineSchemaHash": "a" * 64,
        "verdict": "reject",
        "reasonCode": "tool-permission-expansion",
        "reason": "tool-permission-expansion: changed text contains 'without permission'",
        "changedPaths": ["$.description"],
        "judgeEvidencePath": None,
    }
    assert ToolMetadataValidationResult.model_validate(dumped) == result


def test_tool_metadata_validation_result_rejects_verdict_reject_without_reason_code() -> None:
    with pytest.raises(ValidationError):
        ToolMetadataValidationResult(
            tool_name="read_file",
            baseline_schema_hash="a" * 64,
            verdict="reject",
            reason_code=None,
        )


def test_tool_metadata_validation_result_rejects_empty_baseline_schema_hash() -> None:
    with pytest.raises(ValidationError):
        ToolMetadataValidationResult(
            tool_name="read_file",
            baseline_schema_hash="",
            verdict="accept",
        )


def test_tool_metadata_validation_result_accepts_verdict_with_evidence() -> None:
    result = ToolMetadataValidationResult(
        tool_name="read_file",
        baseline_schema_hash="a" * 64,
        verdict="accept",
        reason_code=None,
        reason=None,
        changed_paths=["$.description", "$.parameters.path.description"],
        judge_evidence_path="path/to/evidence.jsonl",
    )

    assert result.verdict == "accept"
    assert result.judge_evidence_path == "path/to/evidence.jsonl"
    assert len(result.changed_paths) == 2

    dumped = result.model_dump(by_alias=True)
    assert dumped["judgeEvidencePath"] == "path/to/evidence.jsonl"
    assert dumped["changedPaths"] == ["$.description", "$.parameters.path.description"]
    assert ToolMetadataValidationResult.model_validate(dumped) == result


def test_run_manifest_defaults_m7_tool_metadata_fields_for_m6_compatibility() -> None:
    manifest = RunManifest(**_manifest_payload())

    assert manifest.tool_metadata_artifact_paths == {}


def test_run_manifest_accepts_tool_metadata_artifact_paths() -> None:
    manifest = RunManifest(
        **_manifest_payload(),
        tool_metadata_artifact_paths={
            "tool_contract_snapshot": "tool_contract_snapshot.json",
            "tool_metadata_candidates": "tool_metadata_candidates.jsonl",
            "tool_metadata_review": "tool_metadata_review.md",
        },
    )

    assert manifest.tool_metadata_artifact_paths == {
        "tool_contract_snapshot": "tool_contract_snapshot.json",
        "tool_metadata_candidates": "tool_metadata_candidates.jsonl",
        "tool_metadata_review": "tool_metadata_review.md",
    }


# ---------------------------------------------------------------------------
# M7 Optimizer Contract Fields
# ---------------------------------------------------------------------------


def test_optimizer_input_accepts_tool_contract_snapshot_context() -> None:
    snapshot = ToolContractSnapshot(
        tool_name="read_file",
        description_text="Read a workspace file.",
        parameters_schema={"type": "object", "properties": {}},
        source_kind="builtin",
        schema_hash="a" * 64,
    )

    payload = OptimizerInput(
        run_id="run-1",
        skill_name="demo-skill",
        baseline_hash="basehash",
        baseline_skill_md_redacted="redacted",
        eval_records_path="optimizer/eval_bundle.ndjson",
        output_dir="optimizer",
        max_candidates=8,
        timeout_seconds=600,
        seed=123,
        tool_contract_snapshot=[snapshot],
    )

    dumped = payload.model_dump(by_alias=True)

    assert dumped["toolContractSnapshot"][0]["toolName"] == "read_file"
    assert OptimizerInput.model_validate(dumped).tool_contract_snapshot == [snapshot]


def test_optimizer_result_accepts_optional_tool_metadata_candidates() -> None:
    candidate = ToolMetadataCandidate(
        tool_name="read_file",
        baseline_schema_hash="a" * 64,
        proposed_schema={
            "name": "read_file",
            "description": "Read one explicitly requested workspace file.",
            "parameters": {"type": "object", "properties": {}},
        },
        intended_improvement="Clarifies scope.",
        risk_assessment="No permission or schema expansion.",
    )

    error = OptimizerError(code="no_improvement", message="No skill improvement.")

    result = OptimizerResult(
        optimizer_name="external-wrapper",
        candidates=[],
        error=error,
        tool_metadata_candidates=[candidate],
    )

    dumped = result.model_dump(by_alias=True)

    assert dumped["toolMetadataCandidates"][0]["toolName"] == "read_file"
    assert OptimizerResult.model_validate(dumped).tool_metadata_candidates == [candidate]
