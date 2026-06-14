from datetime import datetime, timezone

from nanobot.evolve.gates.semantic_fidelity import SemanticFidelityGate
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
        skill_md_content="---\nname: demo-skill\ndescription: Demo skill\n---\nUse concise answers.\n",
        frontmatter=_frontmatter(),
        body_md="Use concise answers.",
        cache_key_hash="cache",
        size_metrics={"lines": 5},
        content_hash="basehash",
        loaded_from="tests",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _candidate(body: str) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content=f"---\nname: demo-skill\ndescription: Demo skill\n---\n{body}\n",
        frontmatter=_frontmatter(),
        body_md=body,
        cache_key_hash="cache",
        size_metrics={"lines": 6},
        content_hash="candhash",
        parent_baseline_hash="basehash",
        gepa_iteration=1,
    )


def test_semantic_fidelity_gate_passes_candidate_above_threshold() -> None:
    result = SemanticFidelityGate().evaluate(
        _candidate("Use concise answers. Include one concrete example."),
        _baseline(),
    )

    assert result.gate_name == "4-semantic-fidelity"
    assert result.verdict == "pass"
    assert result.metrics["semantic_aggregate"] >= 0.8
    assert result.evidence is not None
    assert result.evidence["judge_model"] == "local/deterministic"


def test_semantic_fidelity_gate_fails_empty_candidate() -> None:
    result = SemanticFidelityGate().evaluate(_candidate(""), _baseline())

    assert result.verdict == "fail"
    assert result.failure_reason == "semantic-fidelity-below-threshold"
    assert result.metrics["semantic_aggregate"] == 0.0
