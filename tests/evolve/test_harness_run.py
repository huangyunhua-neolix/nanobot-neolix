from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import ClassVar

import pytest

from nanobot.evolve.gates import Gate
from nanobot.evolve.harness import OfflineHarness, _parse_frontmatter, _render_skill
from nanobot.evolve.optimizer.schemas import OptimizerCandidate, OptimizerResult


def _write_skill(workspace: Path, name: str, body: str = "Use concise answers.") -> Path:
    skill_dir = workspace / "skills" / "agent" / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(_skill_markdown(name, body), encoding="utf-8")
    return path


def _write_optimizer_script(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


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


class _ExplodingGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self, gate_name: str, message: str) -> None:
        self._name = gate_name
        self._message = message

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        raise RuntimeError(self._message)


def test_harness_run_promotes_candidate_and_writes_artifacts(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'transform-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'adds example instruction'
    }]
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
        max_candidates=8,
        optimizer_timeout_seconds=5,
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    assert manifest.final_status == "promoted_to_pr"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "report.md").exists()
    assert (run_dir / "diff.patch").exists()
    assert (run_dir / "pr_body.md").exists()
    assert (run_dir / "optimizer" / "optimizer_input.json").exists()
    assert (run_dir / "optimizer" / "optimizer_output.json").exists()
    assert (run_dir / "optimizer" / "stdout.txt").exists()
    assert (run_dir / "optimizer" / "stderr.txt").exists()
    assert (run_dir / "optimizer" / "eval_bundle.ndjson").exists()
    patch = (run_dir / "diff.patch").read_text(encoding="utf-8")
    assert "--- a/skills/agent/demo-skill/SKILL.md" in patch
    assert "+++ b/skills/agent/demo-skill/SKILL.md" in patch
    assert manifest.artifact_paths == {
        "diff": "diff.patch",
        "eval_bundle": "optimizer/eval_bundle.ndjson",
        "optimizer_input": "optimizer/optimizer_input.json",
        "optimizer_output": "optimizer/optimizer_output.json",
        "optimizer_stderr": "optimizer/stderr.txt",
        "optimizer_stdout": "optimizer/stdout.txt",
        "pr_body": "pr_body.md",
        "report": "report.md",
    }
    assert manifest.evolve_extra_version == {"optimizer": "transform-wrapper"}
    assert "Use concise answers." in (
        tmp_path / "skills" / "agent" / "demo-skill" / "SKILL.md"
    ).read_text(encoding="utf-8")


def test_harness_run_omitted_timeout_writes_default_600_seconds(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'timeout-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No candidate improved.'},
    'candidates': []
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    optimizer_input = json.loads(
        (tmp_path / "evals" / "runs" / manifest.run_id / "optimizer" / "optimizer_input.json")
        .read_text(encoding="utf-8")
    )
    assert optimizer_input["timeoutSeconds"] == 600


def test_harness_run_gate_exception_reason_is_pr_body_safe(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'gate-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Add a gate-safe example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'exercise rejected_by_gate path'
    }]
}))
""".lstrip(),
    )
    harness = OfflineHarness(
        workspace=tmp_path,
        gates=[_ExplodingGate("1-explodes", "bad line\n```secret```\x01still same failure")],
    )

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    assert manifest.final_status == "rejected_by_gate"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "pr_body.md").exists()
    assert (run_dir / "report.md").exists()
    reason = manifest.gate_verdicts[0].failure_reason
    assert reason is not None
    assert "bad line" in reason
    assert "still same failure" in reason
    assert "\n" not in reason
    assert "```" not in reason
    assert "\x01" not in reason
    pr_body = (run_dir / "pr_body.md").read_text(encoding="utf-8")
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "bad line" in pr_body
    assert "bad line" in report


def test_harness_run_all_invalid_candidates_is_rejected_by_validation(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "bad_candidate.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'bad-wrapper',
    'error': None,
    'candidates': [{
        'skillName': 'other-skill',
        'skillMdContent': '---\\nname: other-skill\\n---\\nBad.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'bad'
    }]
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.final_status == "rejected_by_validation"
    assert manifest.validation_failures[0].candidate_index == 0
    assert manifest.validation_failures[0].reason_code == "skill-name-mismatch"
    assert manifest.candidate_hashes == []
    assert manifest.promoted_candidate_hash is None


def test_harness_run_mixed_validation_promotes_valid_candidate(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "mixed_candidates.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'mixed-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [
        {
            'skillName': 'demo-skill',
            'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nValid lower score candidate.\\n',
            'score': 0.8,
            'iteration': 1,
            'rationale': 'valid candidate'
        },
        {
            'skillName': 'other-skill',
            'skillMdContent': '---\\nname: other-skill\\ndescription: Demo skill\\n---\\nInvalid higher score candidate.\\n',
            'score': 0.9,
            'iteration': 1,
            'rationale': 'ranked first but invalid'
        }
    ]
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.final_status == "promoted_to_pr"
    assert manifest.promoted_candidate_hash is not None
    assert manifest.validation_failures[0].candidate_index == 0
    assert manifest.validation_failures[0].reason_code == "skill-name-mismatch"


def test_harness_run_no_improvement_status(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "no_improvement.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'quiet-wrapper',
    'error': {'code': 'no_improvement', 'message': 'No candidate improved.'},
    'candidates': []
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.final_status == "no_improvement"
    assert manifest.candidate_hashes == []
    assert manifest.promoted_candidate_hash is None


def test_harness_run_records_malformed_frontmatter_validation_failure(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "malformed_frontmatter.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'bad-frontmatter-wrapper',
    'error': None,
    'candidates': [{
        'skillName': 'demo-skill',
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\ncreated_at: not-a-date\\n---\\nBad date.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'bad frontmatter'
    }]
}))
""".lstrip(),
    )
    harness = OfflineHarness(workspace=tmp_path)

    manifest = harness.run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.final_status == "rejected_by_validation"
    assert manifest.validation_failures[0].candidate_index == 0
    assert manifest.validation_failures[0].candidate_hash == "<invalid>"
    assert manifest.validation_failures[0].reason_code == "frontmatter-invalid"
    reason = manifest.validation_failures[0].reason
    assert reason.startswith("frontmatter-invalid: ")
    assert "created_at" in reason
    assert "not-a-date" in reason
    assert len(reason) <= 300


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
