from __future__ import annotations

from pathlib import Path

from nanobot.evolve.harness import OfflineHarness
from nanobot.evolve.optimizer.schemas import OptimizerCandidate, OptimizerResult


def _write_skill(workspace: Path, name: str, body: str = "Use concise answers.") -> Path:
    skill_dir = workspace / "skills" / "agent" / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(
        "---\n"
        f"name: {name}\n"
        "description: Demo skill\n"
        "origin: agent\n"
        "created_by: tests\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "---\n"
        f"{body}\n",
        encoding="utf-8",
    )
    return path


def test_generate_run_id_scans_existing_suffixes(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path)
    existing = tmp_path / "evals" / "runs" / "20260614T120000Z-demo-skill-0001"
    existing.mkdir(parents=True)

    run_id = harness._generate_run_id("demo-skill", timestamp="20260614T120000Z")

    assert run_id == "20260614T120000Z-demo-skill-0002"


def test_load_baseline_skill_parses_frontmatter_and_hashes(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)

    baseline = harness._load_baseline_skill("demo-skill")

    assert baseline.skill_name == "demo-skill"
    assert baseline.frontmatter.name == "demo-skill"
    assert baseline.content_hash
    assert baseline.cache_key_hash
    assert baseline.loaded_from.endswith("skills/agent/demo-skill/SKILL.md")


def test_load_eval_records_writes_redacted_bundle(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path)

    bundle = harness._load_eval_records("demo-skill", ["A", "C"], "run-1")

    assert bundle == tmp_path / "evals" / "runs" / "run-1" / "optimizer" / "eval_bundle.ndjson"
    assert bundle.exists()
    assert "promptRedacted" in bundle.read_text(encoding="utf-8")


def test_candidate_from_optimizer_injects_provenance(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    optimizer_result = OptimizerResult(
        optimizer_name="external-wrapper",
        optimizer_version="0.1.0",
        seed=123,
        error=None,
        candidates=[
            OptimizerCandidate(
                skill_name="demo-skill",
                skill_md_content="---\nname: demo-skill\ncreated_by: malicious\n---\nUse clearer answers.\n",
                score=0.9,
                iteration=2,
                rationale="better",
            )
        ],
    )

    candidate = harness._candidate_from_optimizer(
        optimizer_result.candidates[0], baseline, "run-1", optimizer_result
    )

    assert candidate.frontmatter.created_by == "external:optimizer"
    assert candidate.frontmatter.evolved_from_run == "run-1"
    assert candidate.frontmatter.parent_skill_hash == baseline.content_hash
    assert candidate.frontmatter.optimizer_name == "external-wrapper"
    assert candidate.frontmatter.optimizer_version == "0.1.0"
    assert candidate.parent_baseline_hash == baseline.content_hash
    assert candidate.gepa_iteration == 2
    assert candidate.gepa_seed == 123


def test_validate_candidate_rejects_mismatched_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    other = baseline.model_copy(update={"skill_name": "other-skill"})

    reason = harness._validate_candidate(other, baseline, seen_hashes=set())

    assert reason == "skill-name-mismatch"


def test_validate_candidate_rejects_duplicate_body(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate = baseline.model_copy(update={"parent_baseline_hash": baseline.content_hash})

    reason = harness._validate_candidate(candidate, baseline, seen_hashes={candidate.content_hash})

    assert reason == "duplicate-candidate"


def test_rank_candidates_uses_score_iteration_hash(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path)
    result = OptimizerResult(
        optimizer_name="external-wrapper",
        error=None,
        candidates=[
            OptimizerCandidate(skill_name="demo-skill", skill_md_content="b", score=0.5, iteration=2, rationale="b"),
            OptimizerCandidate(skill_name="demo-skill", skill_md_content="a", score=0.9, iteration=2, rationale="a"),
            OptimizerCandidate(skill_name="demo-skill", skill_md_content="c", score=0.9, iteration=1, rationale="c"),
        ],
    )

    ranked = harness._rank_candidates(result)

    assert [c.skill_md_content for c in ranked] == ["c", "a", "b"]
