import json
from datetime import datetime, timezone
from pathlib import Path

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


def test_semantic_fidelity_gate_records_local_fallback_evidence_path(tmp_path: Path) -> None:
    result = SemanticFidelityGate(evidence_dir=tmp_path).evaluate(
        _candidate("Use concise answers. Include one concrete example."),
        _baseline(),
    )

    assert result.verdict == "pass"
    assert result.evidence is not None
    assert result.evidence["judge_mode"] == "local_fallback"
    assert result.evidence["calibrated"] == "false"
    assert result.evidence["judge_evidence_path"] == "judge_evidence.jsonl"

    evidence_path = tmp_path / "judge_evidence.jsonl"
    rows = [json.loads(line) for line in evidence_path.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["judgeMode"] == "local_fallback"
    assert rows[0]["score"]["aggregate"] >= 0.8


def test_semantic_fidelity_gate_external_required_fails_without_provider() -> None:
    result = SemanticFidelityGate(require_external=True).evaluate(
        _candidate("Use concise answers. Include one concrete example."),
        _baseline(),
    )

    assert result.verdict == "fail"
    assert result.failure_reason == "judge-provider-missing"
    assert result.metrics["semantic_aggregate"] == 0.0


def test_semantic_fidelity_gate_fails_empty_candidate() -> None:
    result = SemanticFidelityGate().evaluate(_candidate(""), _baseline())

    assert result.verdict == "fail"
    assert result.failure_reason == "semantic-fidelity-below-threshold"
    assert result.metrics["semantic_aggregate"] == 0.0
