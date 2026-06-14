from __future__ import annotations

import json
from pathlib import Path

import pytest

from nanobot.evolve.harness import OfflineHarness, _parse_frontmatter, _render_skill
from nanobot.evolve.optimizer.schemas import OptimizerCandidate, OptimizerResult


def _write_skill(workspace: Path, name: str, body: str = "Use concise answers.") -> Path:
    skill_dir = workspace / "skills" / "agent" / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(_skill_markdown(name, body), encoding="utf-8")
    return path


def _skill_markdown(name: str, body: str = "Use concise answers.") -> str:
    return (
        "---\n"
        f"name: {name}\n"
        "description: Demo skill\n"
        "origin: agent\n"
        "created_by: tests\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "---\n"
        f"{body}\n"
    )


def _optimizer_result(candidate: OptimizerCandidate) -> OptimizerResult:
    return OptimizerResult(
        optimizer_name="external-wrapper",
        optimizer_version="0.1.0",
        seed=123,
        error=None,
        candidates=[candidate],
    )


def _optimizer_candidate(markdown: str, *, skill_name: str = "demo-skill") -> OptimizerCandidate:
    return OptimizerCandidate(
        skill_name=skill_name,
        skill_md_content=markdown,
        score=0.9,
        iteration=2,
        rationale="better",
    )


def test_generate_run_id_scans_existing_suffixes(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path)
    existing = tmp_path / "evals" / "runs" / "20260614T120000Z-demo-skill-0001"
    existing.mkdir(parents=True)

    run_id = harness._generate_run_id("demo-skill", timestamp="20260614T120000Z")

    assert run_id == "20260614T120000Z-demo-skill-0002"


def test_generate_run_id_raises_when_suffixes_exhausted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = OfflineHarness(workspace=tmp_path)
    existing = tmp_path / "evals" / "runs" / "20260614T120000Z-demo-skill-0001"
    existing.mkdir(parents=True)
    monkeypatch.setattr("nanobot.evolve.harness._RUN_ID_SUFFIX_LIMIT", 2)

    with pytest.raises(FileExistsError, match="no available run-id suffix"):
        harness._generate_run_id("demo-skill", timestamp="20260614T120000Z")


def test_load_baseline_skill_parses_frontmatter_and_hashes(tmp_path: Path) -> None:
    raw = _skill_markdown("demo-skill")
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)

    baseline = harness._load_baseline_skill("demo-skill")

    assert baseline.skill_name == "demo-skill"
    assert baseline.frontmatter.name == "demo-skill"
    assert baseline.content_hash == "9cb272a6b6ecb80dd92c8a2a5db7565ee74d8fc7a4d4572337e8b2d0cdd0f1d5"
    assert baseline.cache_key_hash == "cb1b3a49f70a3bf5ced215c8f87875a9219ee622b6c7ef6ca4656003e9941e7e"
    assert baseline.size_metrics["lines"] == len(raw.splitlines())
    assert baseline.loaded_from.endswith("skills/agent/demo-skill/SKILL.md")


def test_load_eval_records_writes_redacted_bundle(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path)

    bundle = harness._load_eval_records("demo-skill", ["C", "A"], "run-1")

    assert bundle == tmp_path / "evals" / "runs" / "run-1" / "optimizer" / "eval_bundle.ndjson"
    assert bundle.exists()
    lines = bundle.read_text(encoding="utf-8").splitlines()
    assert lines == [
        '{"expectedRedacted": "Expected demo-skill tier C answer.", "metadata": {"skillName": "demo-skill"}, "promptRedacted": "Evaluate demo-skill tier C prompt.", "recordId": "demo-skill-C", "tier": "C"}',
        '{"expectedRedacted": "Expected demo-skill tier A answer.", "metadata": {"skillName": "demo-skill"}, "promptRedacted": "Evaluate demo-skill tier A prompt.", "recordId": "demo-skill-A", "tier": "A"}',
    ]
    assert [list(json.loads(line).keys()) for line in lines] == [
        ["expectedRedacted", "metadata", "promptRedacted", "recordId", "tier"],
        ["expectedRedacted", "metadata", "promptRedacted", "recordId", "tier"],
    ]


def test_candidate_from_optimizer_injects_provenance(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate(
        "---\nname: demo-skill\ncreated_by: malicious\n---\nUse clearer answers.\n"
    )
    optimizer_result = _optimizer_result(candidate_input)

    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)

    assert candidate.frontmatter.created_by == "external:optimizer"
    assert candidate.frontmatter.evolved_from_run == "run-1"
    assert candidate.frontmatter.parent_skill_hash == baseline.content_hash
    assert candidate.frontmatter.optimizer_name == "external-wrapper"
    assert candidate.frontmatter.optimizer_version == "0.1.0"
    assert candidate.frontmatter.evolved_at is None
    assert candidate.parent_baseline_hash == baseline.content_hash
    assert candidate.gepa_iteration == 2
    assert candidate.gepa_seed == 123


def test_candidate_from_optimizer_defaults_missing_frontmatter_name(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate(
        "---\ndescription: Updated skill\n---\nUse clearer answers.\n"
    )
    optimizer_result = _optimizer_result(candidate_input)

    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)

    assert candidate.frontmatter.name == "demo-skill"


def test_candidate_from_optimizer_preserves_frontmatter_name_mismatch(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate(
        "---\nname: wrong-skill\ndescription: Updated skill\n---\nUse clearer answers.\n"
    )
    optimizer_result = _optimizer_result(candidate_input)

    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)
    reason = harness._validate_candidate(candidate, baseline, seen_hashes=set())

    assert candidate.frontmatter.name == "wrong-skill"
    assert reason == "frontmatter-invalid"


def test_validate_candidate_rejects_mismatched_skill(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    other = baseline.model_copy(update={"skill_name": "other-skill"})

    reason = harness._validate_candidate(other, baseline, seen_hashes=set())

    assert reason == "skill-name-mismatch"


def test_validate_candidate_rejects_empty_content(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate("---\nname: demo-skill\n---\n   \n")
    optimizer_result = _optimizer_result(candidate_input)
    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)

    reason = harness._validate_candidate(candidate, baseline, seen_hashes=set())

    assert reason == "empty-content"


def test_validate_candidate_rejects_duplicate_body(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate = baseline.model_copy(update={"parent_baseline_hash": baseline.content_hash})

    reason = harness._validate_candidate(candidate, baseline, seen_hashes={candidate.content_hash})

    assert reason == "duplicate-candidate"


def test_validate_candidate_rejects_parent_baseline_mismatch(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate(_skill_markdown("demo-skill", "Use clearer answers."))
    optimizer_result = _optimizer_result(candidate_input)
    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)
    candidate = candidate.model_copy(update={"parent_baseline_hash": "wrong-parent"})

    reason = harness._validate_candidate(candidate, baseline, seen_hashes=set())

    assert reason == "parent-baseline-mismatch"


@pytest.mark.parametrize(
    "path_claim",
    [
        "/var/folders/zz/abc123/T/nanobot",
        "/root/.nanobot/config.json",
        "/Volumes/PrivateDrive/notes.txt",
        r"C:\Users\Alice\.nanobot\config.json",
        "C:/Users/Alice/.nanobot/config.json",
    ],
)
def test_validate_candidate_rejects_private_path_claims(tmp_path: Path, path_claim: str) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")
    candidate_input = _optimizer_candidate(_skill_markdown("demo-skill", f"Do not mention {path_claim}"))
    optimizer_result = _optimizer_result(candidate_input)
    candidate = harness._candidate_from_optimizer(candidate_input, baseline, "run-1", optimizer_result)

    reason = harness._validate_candidate(candidate, baseline, seen_hashes=set())

    assert reason == "path-claim-rejected"


def test_parse_frontmatter_returns_values_and_body() -> None:
    values, body = _parse_frontmatter(
        "---\nname: demo-skill\ndescription: Demo skill\n# ignored\n---\nUse concise answers.\n"
    )

    assert values == {"name": "demo-skill", "description": "Demo skill"}
    assert body == "Use concise answers.\n"


def test_render_skill_sorts_frontmatter_keys(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    harness = OfflineHarness(workspace=tmp_path)
    baseline = harness._load_baseline_skill("demo-skill")

    rendered = _render_skill(baseline.frontmatter, "Use concise answers.\n")

    assert rendered == (
        "---\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "created_by: tests\n"
        "description: Demo skill\n"
        "name: demo-skill\n"
        "origin: agent\n"
        "---\n"
        "Use concise answers.\n"
    )


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
