from datetime import datetime, timezone

from nanobot.evolve.gates.human_review import HumanReviewGate
from nanobot.evolve.schemas import Baseline, Candidate, SkillFrontmatter


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


def _candidate(**metrics: int) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content="candidate",
        frontmatter=_frontmatter(),
        body_md="candidate",
        cache_key_hash="cache",
        size_metrics={"lines": 1, **metrics},
        content_hash="candhash",
        parent_baseline_hash="basehash",
        gepa_iteration=1,
    )


def test_human_review_gate_passes_complete_review_bundle() -> None:
    result = HumanReviewGate().evaluate(
        _candidate(
            review_manifest=1,
            review_report=1,
            review_diff=1,
            review_pr_body=1,
            review_optimizer_input=1,
            review_optimizer_output=1,
            review_requires_human_approval=1,
        ),
        _baseline(),
    )

    assert result.gate_name == "5-human-review"
    assert result.verdict == "pass"
    assert result.metrics["review_artifacts_present"] == 6.0
    assert result.evidence is not None
    assert result.evidence["requires_human_approval"] == "true"


def test_human_review_gate_fails_missing_review_bundle_item() -> None:
    result = HumanReviewGate().evaluate(
        _candidate(
            review_manifest=1,
            review_report=1,
            review_diff=0,
            review_pr_body=1,
            review_optimizer_input=1,
            review_optimizer_output=1,
            review_requires_human_approval=1,
        ),
        _baseline(),
    )

    assert result.verdict == "fail"
    assert result.failure_reason == "human-review-artifacts-incomplete: review_diff"
