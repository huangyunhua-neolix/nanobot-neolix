from datetime import datetime, timezone

from nanobot.evolve.gates.human_review import HumanReviewGate
from nanobot.evolve.schemas import Baseline, Candidate, ReviewReadiness, SkillFrontmatter


def _frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="Demo skill",
        origin="agent",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _baseline() -> Baseline:
    return Baseline(
        skill_name="demo-skill",
        skill_md_content="base",
        frontmatter=_frontmatter(),
        body_md="base",
        cache_key_hash="cache",
        size_metrics={"lines": 1},
        content_hash="basehash",
        loaded_from="tests",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _artifact_paths(**overrides: str) -> dict[str, str]:
    paths = {
        "manifest": "manifest.json",
        "report": "report.md",
        "diff": "diff.patch",
        "pr_body": "pr_body.md",
        "optimizer_input": "optimizer/optimizer_input.json",
        "optimizer_output": "optimizer/optimizer_output.json",
    }
    paths.update(overrides)
    return paths


def _readiness(
    *,
    artifact_paths: dict[str, str] | None = None,
    requires_human_approval: bool = True,
) -> ReviewReadiness:
    return ReviewReadiness(
        artifact_paths=_artifact_paths() if artifact_paths is None else artifact_paths,
        requires_human_approval=requires_human_approval,
    )


def _candidate(review_readiness: ReviewReadiness | None = None) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content="candidate",
        frontmatter=_frontmatter(),
        body_md="candidate",
        cache_key_hash="cache",
        size_metrics={"lines": 1},
        content_hash="candhash",
        parent_baseline_hash="basehash",
        gepa_iteration=1,
        review_readiness=review_readiness,
    )


def test_human_review_gate_passes_complete_review_readiness() -> None:
    result = HumanReviewGate().evaluate(_candidate(_readiness()), _baseline())

    assert result.gate_name == "5-human-review"
    assert result.verdict == "pass"
    assert result.metrics["review_artifacts_present"] == 6.0
    assert result.metrics["review_artifacts_required"] == 6.0
    assert result.metrics["review_checks_present"] == 7.0
    assert result.metrics["review_checks_required"] == 7.0
    assert result.metrics["requires_human_approval"] == 1.0
    assert result.evidence is not None
    assert result.evidence["approval_status"] == "external-human-approval-required-not-granted"


def test_human_review_gate_fails_when_readiness_missing() -> None:
    result = HumanReviewGate().evaluate(_candidate(), _baseline())

    assert result.verdict == "fail"
    assert result.metrics["review_artifacts_present"] == 0.0
    assert result.metrics["review_artifacts_required"] == 6.0
    assert result.metrics["review_checks_present"] == 0.0
    assert result.metrics["review_checks_required"] == 7.0
    assert result.metrics["requires_human_approval"] == 0.0
    assert result.failure_reason is not None
    assert "readiness-missing" in result.failure_reason
    assert "requires_human_approval" in result.failure_reason


def test_human_review_gate_fails_missing_review_artifact_key() -> None:
    paths = _artifact_paths()
    del paths["diff"]

    result = HumanReviewGate().evaluate(_candidate(_readiness(artifact_paths=paths)), _baseline())

    assert result.verdict == "fail"
    assert result.metrics["review_artifacts_present"] == 5.0
    assert result.metrics["review_artifacts_required"] == 6.0
    assert result.metrics["review_checks_present"] == 6.0
    assert result.metrics["review_checks_required"] == 7.0
    assert result.metrics["requires_human_approval"] == 1.0
    assert result.failure_reason == "human-review-readiness-incomplete: missing artifacts: diff"


def test_human_review_gate_fails_without_human_approval_requirement() -> None:
    result = HumanReviewGate().evaluate(
        _candidate(_readiness(requires_human_approval=False)),
        _baseline(),
    )

    assert result.verdict == "fail"
    assert result.metrics["review_artifacts_present"] == 6.0
    assert result.metrics["review_artifacts_required"] == 6.0
    assert result.metrics["review_checks_present"] == 6.0
    assert result.metrics["review_checks_required"] == 7.0
    assert result.metrics["requires_human_approval"] == 0.0
    assert result.failure_reason == (
        "human-review-readiness-incomplete: missing approval requirement: "
        "requires_human_approval"
    )
