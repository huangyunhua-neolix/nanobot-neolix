from __future__ import annotations

import pytest
from pydantic import ValidationError

from nanobot.evolve.exceptions import OptimizerRunError
from nanobot.evolve.optimizer.schemas import (
    OptimizerCandidate,
    OptimizerError,
    OptimizerInput,
    OptimizerResult,
)


def test_optimizer_input_uses_camel_case_aliases() -> None:
    payload = OptimizerInput(
        run_id="20260614T120000Z-demo-skill-0001",
        skill_name="demo-skill",
        baseline_hash="abc123",
        baseline_skill_md_redacted="---\nname: demo-skill\n---\nbody",
        eval_records_path="/tmp/run/optimizer/eval_bundle.ndjson",
        output_dir="/tmp/run/optimizer",
        max_candidates=8,
        timeout_seconds=600,
        seed=123456789,
    ).model_dump(by_alias=True)

    assert payload["schemaVersion"] == "1"
    assert payload["runId"] == "20260614T120000Z-demo-skill-0001"
    assert payload["baselineSkillMdRedacted"].startswith("---")
    assert "baseline_skill_md_redacted" not in payload


def test_optimizer_result_success_requires_candidates() -> None:
    result = OptimizerResult(
        optimizer_name="external-wrapper",
        optimizer_version="0.1.0",
        seed=123,
        error=None,
        candidates=[
            OptimizerCandidate(
                skill_name="demo-skill",
                skill_md_content="---\nname: demo-skill\n---\nbody",
                score=0.8,
                iteration=1,
                rationale="clearer instructions",
            )
        ],
    )

    assert result.schema_version == "1"
    assert result.candidates[0].score == 0.8


def test_optimizer_result_rejects_empty_success() -> None:
    with pytest.raises(ValidationError, match="success result requires at least one candidate"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=None,
            candidates=[],
        )


def test_optimizer_result_accepts_no_improvement_only_without_candidates() -> None:
    result = OptimizerResult(
        optimizer_name="external-wrapper",
        error=OptimizerError(code="no_improvement", message="No candidate improved."),
        candidates=[],
    )

    assert result.error is not None
    assert result.error.code == "no_improvement"


def test_optimizer_result_rejects_no_improvement_with_candidates() -> None:
    with pytest.raises(ValidationError, match="no_improvement result must not include candidates"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=OptimizerError(code="no_improvement", message="No candidate improved."),
            candidates=[
                OptimizerCandidate(
                    skill_name="demo-skill",
                    skill_md_content="---\nname: demo-skill\n---\nbody",
                    score=0.8,
                    iteration=1,
                    rationale="candidate should not be present",
                )
            ],
        )


def test_optimizer_result_rejects_invalid_input_as_structured_result() -> None:
    with pytest.raises(ValidationError, match="invalid_input and optimizer_failed are adapter errors"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=OptimizerError(code="invalid_input", message="bad input"),
            candidates=[],
        )


def test_optimizer_run_error_structured_fields() -> None:
    err = OptimizerRunError("optimizer failed", run_dir="/tmp/run", exit_code=7)

    assert err.run_dir == "/tmp/run"
    assert err.exit_code == 7
    assert OptimizerRunError.MUST_PRECEDE == frozenset({"RuntimeError"})
