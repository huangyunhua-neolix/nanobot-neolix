from __future__ import annotations

from datetime import datetime, timezone

from nanobot.evolve.gates import GateResult
from nanobot.evolve.optimizer.schemas import OptimizerError, OptimizerResult
from nanobot.evolve.report import render_run_report
from nanobot.evolve.schemas import JudgeRunSummary, JudgeSummary, RunManifest, ValidationFailure


def _judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=2,
        median_aggregate=0.0,
        median_process=0.0,
        median_output=0.0,
        median_token=0.0,
        consensus_split_count=0,
    )


def _manifest(**overrides: object) -> RunManifest:
    fields: dict[str, object] = dict(
        run_id="20260614T120000Z-demo-skill-0001",
        started_at=datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 14, 12, 1, tzinfo=timezone.utc),
        nanobot_version="0.2.1",
        evolve_extra_version={"optimizer": "external"},
        skill_name="demo-skill",
        baseline_hash="basehash00112233",
        candidate_hashes=["candhash44556677"],
        promoted_candidate_hash="candhash44556677",
        gate_verdicts=[],
        judge_summary=_judge_summary(),
        final_status="promoted_to_pr",
        tiers_used=["A", "C"],
        record_count_per_tier={"A": 1, "C": 1},
        judge_pool_health={},
        optimizer_name="external-wrapper",
        optimizer_seed=123,
        artifact_paths={"diff": "diff.patch", "pr_body": "pr_body.md"},
    )
    fields.update(overrides)
    return RunManifest(**fields)  # type: ignore[arg-type]


def _optimizer_result() -> OptimizerResult:
    return OptimizerResult(
        optimizer_name="external-wrapper",
        error=OptimizerError(code="no_improvement", message="No improvement"),
        candidates=[],
    )


def _gate(
    name: str,
    verdict: str = "pass",
    *,
    candidate_hash: str = "candhash44556677",
    failure_reason: str | None = None,
) -> GateResult:
    return GateResult(
        gate_name=name,
        candidate_hash=candidate_hash,
        baseline_hash="basehash00112233",
        verdict=verdict,  # type: ignore[arg-type]
        metrics={"score": 1.0},
        failure_reason=failure_reason,
        timestamp=datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
        duration_ms=10,
    )


def test_render_run_report_has_stable_sections() -> None:
    report = render_run_report(
        _manifest(),
        {"candhash44556677": [_gate("1-test-pass"), _gate("2-size-cap")]},
        OptimizerResult(
            optimizer_name="external-wrapper",
            seed=123,
            error=OptimizerError(code="no_improvement", message="No improvement"),
            candidates=[],
        ),
        [],
    )

    headers = [line for line in report.splitlines() if line.startswith("## ")]
    assert headers == [
        "## Summary",
        "## Optimizer",
        "## Review state",
        "## Validation failures",
        "## Gates",
        "## Artifacts",
    ]
    assert "Run: `20260614T120000Z-demo-skill-0001`" in report
    assert "Status: `promoted_to_pr`" in report


def test_render_run_report_includes_semantic_judge_summary() -> None:
    report = render_run_report(
        _manifest(
            judge_run_summary=JudgeRunSummary(
                judge_mode="local_fallback",
                calibrated=False,
                evidence_count=1,
                median_aggregate=0.82,
                min_axis_score=0.71,
                disagreement_max=None,
            ),
            judge_evidence_paths={"semantic_fidelity": "judge_evidence.jsonl"},
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert report.index("## Review state") < report.index("## Semantic judge")
    assert report.index("## Semantic judge") < report.index("## Validation failures")
    assert "Mode: `local_fallback`" in report
    assert "Calibrated: `false`" in report
    assert "Evidence count: `1`" in report
    assert "Median aggregate: `0.82`" in report
    assert "Minimum axis score: `0.71`" in report
    assert "Disagreement max: `<none>`" in report
    assert "Evidence: `judge_evidence.jsonl`" in report
    assert "Judge metrics were not returned to the optimizer" in report


def test_render_run_report_redacts_semantic_judge_evidence_path() -> None:
    report = render_run_report(
        _manifest(
            judge_run_summary=JudgeRunSummary(
                judge_mode="local_fallback",
                calibrated=False,
                evidence_count=1,
                median_aggregate=0.7100000000000001,
                min_axis_score=0.8200000000000001,
                disagreement_max=None,
            ),
            judge_evidence_paths={
                "semantic_fidelity": (
                    "/Users/alice/private/sk-ant-1234567890abcdefghijklmnop/"
                    "judge_evidence.jsonl"
                )
            },
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert "Median aggregate: `0.71`" in report
    assert "Minimum axis score: `0.82`" in report
    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_includes_tool_metadata_review_artifacts() -> None:
    report = render_run_report(
        _manifest(
            tool_metadata_artifact_paths={
                "tool_contract_snapshot": "runs/1/tool_contract_snapshot.json",
                "tool_metadata_candidates": "runs/1/tool_metadata_candidates.jsonl",
                "tool_metadata_review": "runs/1/tool_metadata_review.md",
                "tool_metadata_judge_evidence": (
                    "runs/1/tool_metadata_judge_evidence.jsonl"
                ),
            }
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert report.index("## Review state") < report.index("## Tool metadata review")
    assert report.index("## Tool metadata review") < report.index("## Validation failures")
    assert (
        "No runtime tool source changed; artifacts require human review before "
        "any application."
    ) in report
    assert "Snapshot: `runs/1/tool_contract_snapshot.json`" in report
    assert "Candidates: `runs/1/tool_metadata_candidates.jsonl`" in report
    assert "Review: `runs/1/tool_metadata_review.md`" in report
    assert "Judge evidence: `runs/1/tool_metadata_judge_evidence.jsonl`" in report


def test_render_run_report_redacts_tool_metadata_artifact_paths() -> None:
    report = render_run_report(
        _manifest(
            tool_metadata_artifact_paths={
                "tool_contract_snapshot": (
                    "/Users/alice/private/sk-ant-1234567890abcdefghijklmnop/"
                    "tool_contract_snapshot.json"
                )
            }
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_lists_validation_failures_safely() -> None:
    failure = ValidationFailure(
        candidate_index=0,
        candidate_hash="candhash44556677",
        reason_code="frontmatter-invalid",
        reason=(
            "frontmatter-invalid in /Users/alice/private/skill.md with "
            "sk-ant-1234567890abcdefghijklmnop"
        ),
    )

    report = render_run_report(
        _manifest(final_status="rejected_by_validation", validation_failures=[failure]),
        {},
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=OptimizerError(code="no_improvement", message="No improvement"),
            candidates=[],
        ),
        [failure],
    )

    assert "frontmatter-invalid" in report
    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_bounds_validation_reason_after_redaction() -> None:
    raw_reason = " ".join(
        [
            "/Users/alice/private/project/sk-ant-1234567890abcdefghijklmnop"
            for _ in range(30)
        ]
    )
    failure = ValidationFailure(
        candidate_index=0,
        candidate_hash="candhash44556677",
        reason_code="frontmatter-invalid",
        reason=raw_reason,
    )

    report = render_run_report(
        _manifest(final_status="rejected_by_validation", validation_failures=[failure]),
        {},
        _optimizer_result(),
        [failure],
    )

    rendered_reason = report.split("frontmatter-invalid: ", maxsplit=1)[1].splitlines()[0]
    assert len(rendered_reason) <= 300
    assert "/Users/" not in rendered_reason
    assert "alice" not in rendered_reason
    assert "sk-ant-" not in rendered_reason


def test_render_run_report_redacts_gate_failure_reason() -> None:
    report = render_run_report(
        _manifest(final_status="rejected_by_gate"),
        {
            "candhash44556677": [
                _gate(
                    "1-test-pass",
                    verdict="fail",
                    failure_reason=(
                        "failed reading /Users/alice/private/trace.log with "
                        "sk-ant-1234567890abcdefghijklmnop"
                    ),
                )
            ]
        },
        _optimizer_result(),
        [],
    )

    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_redacts_artifact_path_values() -> None:
    report = render_run_report(
        _manifest(
            artifact_paths={
                "trace": "/Users/alice/private/sk-ant-1234567890abcdefghijklmnop/trace.log"
            }
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_includes_prompt_template_review_artifacts() -> None:
    report = render_run_report(
        _manifest(
            prompt_template_artifact_paths={
                "prompt_template_snapshot": "runs/1/prompt_template_snapshot.json",
                "prompt_template_candidates": "runs/1/prompt_template_candidates.jsonl",
                "prompt_template_review": "runs/1/prompt_template_review.md",
                "prompt_template_judge_evidence": "runs/1/prompt_template_judge_evidence.jsonl",
            }
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert report.index("## Review state") < report.index("## Prompt template review")
    assert report.index("## Prompt template review") < report.index("## Validation failures")
    assert "No bundled skill source changed" in report
    assert "Cache-sensitive frontmatter was not modified by accepted candidates." in report
    assert "Snapshot: `runs/1/prompt_template_snapshot.json`" in report
    assert "Candidates: `runs/1/prompt_template_candidates.jsonl`" in report
    assert "Review: `runs/1/prompt_template_review.md`" in report
    assert "Judge evidence: `runs/1/prompt_template_judge_evidence.jsonl`" in report


def test_render_run_report_redacts_prompt_template_artifact_paths() -> None:
    report = render_run_report(
        _manifest(
            prompt_template_artifact_paths={
                "prompt_template_snapshot": (
                    "/Users/alice/private/sk-ant-1234567890abcdefghijklmnop/"
                    "prompt_template_snapshot.json"
                )
            }
        ),
        {},
        _optimizer_result(),
        [],
    )

    assert "[REDACTED:APIKEY:ANTHROPIC]" in report
    assert "/Users/" not in report
    assert "alice" not in report
    assert "sk-ant-" not in report


def test_render_run_report_sorts_candidates_and_artifacts_and_none_promotion() -> None:
    report = render_run_report(
        _manifest(
            candidate_hashes=["zzzzzzzz9999", "aaaaaaaa1111"],
            promoted_candidate_hash=None,
            artifact_paths={"zeta": "zeta.log", "alpha": "alpha.log"},
        ),
        {
            "zzzzzzzz9999": [_gate("1-test-pass", candidate_hash="zzzzzzzz9999")],
            "aaaaaaaa1111": [_gate("1-test-pass", candidate_hash="aaaaaaaa1111")],
        },
        _optimizer_result(),
        [],
    )

    assert "Promoted candidate: `<none>`" in report
    assert report.index("Candidate `aaaaaaaa`:") < report.index("Candidate `zzzzzzzz`:")
    assert report.index("- alpha: `alpha.log`") < report.index("- zeta: `zeta.log`")
