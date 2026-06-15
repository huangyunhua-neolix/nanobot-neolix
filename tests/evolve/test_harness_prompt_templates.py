from __future__ import annotations

import json
import sys
from pathlib import Path

from nanobot.evolve.harness import OfflineHarness
from tests.evolve.test_harness_run import _write_optimizer_script, _write_skill

_PROMPT_ARTIFACT_PATHS = {
    "prompt_template_snapshot": "prompt_template_snapshot.json",
    "prompt_template_candidates": "prompt_template_candidates.jsonl",
    "prompt_template_review": "prompt_template_review.md",
}


def _bundled_skill_state() -> dict[Path, tuple[bytes, int]]:
    root = Path(__file__).resolve().parents[2] / "nanobot" / "skills"
    return {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in sorted(root.glob("*/SKILL.md"))}


def test_harness_optimizer_input_includes_prompt_template_snapshot(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "prompt_snapshot.py"
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
assert 'promptTemplateSnapshot' in payload
assert isinstance(payload['promptTemplateSnapshot'], list)
assert payload['promptTemplateSnapshot']
assert all(item['sourceKind'] == 'bundled' for item in payload['promptTemplateSnapshot'])
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'prompt-snapshot-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': []
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    optimizer_input = json.loads((run_dir / "optimizer" / "optimizer_input.json").read_text())
    assert optimizer_input["promptTemplateSnapshot"]
    assert manifest.prompt_template_artifact_paths == _PROMPT_ARTIFACT_PATHS
    assert json.loads((run_dir / "prompt_template_snapshot.json").read_text(encoding="utf-8"))
    assert (run_dir / "prompt_template_candidates.jsonl").read_text(encoding="utf-8") == ""
    review = (run_dir / "prompt_template_review.md").read_text(encoding="utf-8")
    assert "No prompt/template candidates emitted." in review
    assert "candidate_absent" in review


def test_harness_writes_prompt_template_candidate_artifacts_for_no_improvement(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "prompt_candidate.py"
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
snapshot = payload['promptTemplateSnapshot'][0]
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'prompt-candidate-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': [],
    'promptTemplateCandidates': [{
        'skillName': snapshot['skillName'],
        'baselineSnapshotHash': snapshot['snapshotHash'],
        'proposedBody': snapshot['bodyText'],
        'intendedImprovement': 'No-op prompt review artifact.',
        'riskAssessment': 'No body change.',
        'cacheImpactClaim': 'No frontmatter changed.'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    assert manifest.final_status == "no_improvement"
    assert manifest.prompt_template_artifact_paths == _PROMPT_ARTIFACT_PATHS
    candidates_jsonl = (run_dir / "prompt_template_candidates.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in candidates_jsonl.splitlines()]
    assert rows[0]["intendedImprovement"] == "No-op prompt review artifact."
    review = (run_dir / "prompt_template_review.md").read_text(encoding="utf-8")
    assert "candidate_noop" in review
    assert "No-op prompt review artifact." in review
    manifest_json = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_json["promptTemplateArtifactPaths"] == _PROMPT_ARTIFACT_PATHS


def test_harness_rejected_prompt_template_candidate_records_validation_failure(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "prompt_rejected.py"
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
snapshot = payload['promptTemplateSnapshot'][0]
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'prompt-rejected-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': [],
    'promptTemplateCandidates': [{
        'skillName': snapshot['skillName'],
        'baselineSnapshotHash': snapshot['snapshotHash'],
        'proposedBody': '---\\ndescription: mutated\\n',
        'intendedImprovement': 'Mutate frontmatter.',
        'riskAssessment': 'Unsafe cache mutation.',
        'cacheImpactClaim': 'Claims safe.'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    assert manifest.final_status == "rejected_by_validation"
    assert manifest.validation_failures[0].candidate_hash.startswith("prompt-template:")
    assert manifest.validation_failures[0].reason_code == "prompt-frontmatter-mutation"
    review = (run_dir / "prompt_template_review.md").read_text(encoding="utf-8")
    assert "prompt-frontmatter-mutation" in review
    manifest_json = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_json["promptTemplateArtifactPaths"] == _PROMPT_ARTIFACT_PATHS


def test_harness_redacts_prompt_template_json_artifacts(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "prompt_secrets.py"
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
snapshot = payload['promptTemplateSnapshot'][0]
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'prompt-secrets-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': [],
    'promptTemplateCandidates': [{
        'skillName': snapshot['skillName'],
        'baselineSnapshotHash': snapshot['snapshotHash'],
        'proposedBody': 'Email alice@example.com and read /Users/alice/private/sk-ant-abcdefghijklmnopqrstuvwxyzABCDEF.\\n',
        'intendedImprovement': 'Contact alice@example.com.',
        'riskAssessment': 'Mentions /Users/alice/private.',
        'cacheImpactClaim': 'No frontmatter changed.'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    candidates_jsonl = (run_dir / "prompt_template_candidates.jsonl").read_text(encoding="utf-8")
    assert "alice@example.com" not in candidates_jsonl
    assert "/Users/" not in candidates_jsonl
    assert "sk-ant-" not in candidates_jsonl
    assert "[REDACTED:EMAIL]" in candidates_jsonl
    assert "[REDACTED:APIKEY:ANTHROPIC]" in candidates_jsonl


def test_harness_prompt_template_artifacts_do_not_mutate_bundled_skills(
    tmp_path: Path,
) -> None:
    before = _bundled_skill_state()
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "prompt_source.py"
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
snapshot = payload['promptTemplateSnapshot'][0]
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'prompt-source-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': [],
    'promptTemplateCandidates': [{
        'skillName': snapshot['skillName'],
        'baselineSnapshotHash': snapshot['snapshotHash'],
        'proposedBody': snapshot['bodyText'],
        'intendedImprovement': 'No-op candidate.',
        'riskAssessment': 'No source mutation.',
        'cacheImpactClaim': 'No frontmatter changed.'
    }]
}))
""".lstrip(),
    )

    OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert _bundled_skill_state() == before
