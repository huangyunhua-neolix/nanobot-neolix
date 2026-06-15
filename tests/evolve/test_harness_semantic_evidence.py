"""Semantic evidence ownership tests for OfflineHarness.

These tests cover harness-level ownership of judge_evidence.jsonl: pre-run
removal of optimizer-spoofed targets, post-run publication of trusted rows,
tamper-after-gate scenarios, and fail-closed behavior on directory targets.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

import pytest

from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates.semantic_fidelity import SemanticEvidenceRecorder, SemanticFidelityGate
from nanobot.evolve.harness import OfflineHarness
from tests.evolve.test_harness_run import _write_optimizer_script, _write_skill


class _PassingSemanticGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "4-semantic-fidelity"

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        return self._result(candidate, baseline, "pass", 0.95)

    def _result(self, candidate, baseline, verdict: str, aggregate: float):  # type: ignore[no-untyped-def]
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict=verdict,
            metrics={
                "semantic_process": aggregate,
                "semantic_output": aggregate,
                "semantic_token": aggregate,
                "semantic_aggregate": aggregate,
            },
            evidence={
                "judge_model": "local/deterministic",
                "judge_mode": "local_fallback",
                "calibrated": "false",
                "judge_evidence_path": "judge_evidence.jsonl",
            },
            failure_reason=None if verdict == "pass" else "semantic-fidelity-below-threshold",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            duration_ms=1,
        )


class _FirstCandidateFailingSemanticGate(_PassingSemanticGate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self) -> None:
        self._call_count = 0

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        self._call_count += 1
        if self._call_count == 1:
            return self._result(candidate, baseline, "fail", 0.0)
        return self._result(candidate, baseline, "pass", 0.95)


def test_harness_ignores_optimizer_spoofed_semantic_judge_evidence_without_candidate(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_spoofed_no_candidate.py"
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
Path('../judge_evidence.jsonl').write_text('optimizer-controlled evidence\\n')
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'semantic-spoofed-no-candidate-wrapper',
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
    assert not (run_dir / "judge_evidence.jsonl").exists()
    assert manifest.judge_evidence_paths == {}
    assert "semantic_fidelity" not in manifest.artifact_paths
    manifest_json = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_json["judgeEvidencePaths"] == {}
    assert "semantic_fidelity" not in manifest_json["artifactPaths"]


def test_harness_replaces_optimizer_spoofed_semantic_judge_evidence_for_valid_candidate(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_spoofed_valid_candidate.py"
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
Path('../judge_evidence.jsonl').write_text('optimizer-controlled evidence\\n')
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'semantic-spoofed-valid-candidate-wrapper',
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

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    evidence_path = run_dir / "judge_evidence.jsonl"
    evidence_text = evidence_path.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in evidence_text.splitlines()]
    assert "optimizer-controlled evidence" not in evidence_text
    assert len(rows) == 1
    assert rows[0]["recordId"].startswith("semantic:")
    assert manifest.judge_evidence_paths == {"semantic_fidelity": "judge_evidence.jsonl"}
    manifest_json = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_json["judgeEvidencePaths"] == {"semantic_fidelity": "judge_evidence.jsonl"}


def test_harness_replaces_semantic_evidence_recreated_after_optimizer_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_spoofed_after_cleanup.py"
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
    'optimizerName': 'semantic-spoofed-after-cleanup-wrapper',
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

    original_validate_candidate = OfflineHarness._validate_candidate

    def recreate_spoofed_evidence(self: OfflineHarness, candidate, baseline, *, seen_hashes):  # type: ignore[no-untyped-def]
        runs_dir = self._workspace / "evals" / "runs"
        run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
        assert len(run_dirs) == 1
        (run_dirs[0] / "judge_evidence.jsonl").write_text(
            "optimizer-controlled evidence after cleanup\n",
            encoding="utf-8",
        )
        return original_validate_candidate(
            self,
            candidate,
            baseline,
            seen_hashes=seen_hashes,
        )

    monkeypatch.setattr(OfflineHarness, "_validate_candidate", recreate_spoofed_evidence)
    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    evidence_path = run_dir / "judge_evidence.jsonl"
    evidence_text = evidence_path.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in evidence_text.splitlines()]
    assert "optimizer-controlled evidence" not in evidence_text
    assert len(rows) == 1
    assert rows[0]["recordId"].startswith("semantic:")
    assert manifest.judge_evidence_paths == {"semantic_fidelity": "judge_evidence.jsonl"}


def test_harness_rewrites_semantic_evidence_tampered_after_gate_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_spoofed_after_gate.py"
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
    'optimizerName': 'semantic-spoofed-after-gate-wrapper',
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

    original_run_gates = OfflineHarness._run_gates

    def tamper_after_gate_write(self: OfflineHarness, candidate, baseline):  # type: ignore[no-untyped-def]
        trace = original_run_gates(self, candidate, baseline)
        runs_dir = self._workspace / "evals" / "runs"
        run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
        assert len(run_dirs) == 1
        evidence_path = run_dirs[0] / "judge_evidence.jsonl"
        with evidence_path.open("a", encoding="utf-8") as evidence_file:
            evidence_file.write(
                json.dumps(
                    {
                        "recordId": "semantic:optimizer-spoof",
                        "judgeMode": "local_fallback",
                        "score": {
                            "process": 1.0,
                            "output": 1.0,
                            "token": 1.0,
                            "aggregate": 1.0,
                        },
                        "calibrated": False,
                    }
                )
                + "\n"
            )
        return trace

    monkeypatch.setattr(OfflineHarness, "_run_gates", tamper_after_gate_write)
    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    evidence_path = run_dir / "judge_evidence.jsonl"
    evidence_text = evidence_path.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in evidence_text.splitlines()]
    assert "optimizer-spoof" not in evidence_text
    assert len(rows) == 1
    assert rows[0]["recordId"].startswith("semantic:")
    assert manifest.judge_evidence_paths == {"semantic_fidelity": "judge_evidence.jsonl"}


def test_harness_publishes_trusted_semantic_evidence_for_gate_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "trusted_semantic_gate_results.py"
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
    'optimizerName': 'trusted-semantic-gate-results-wrapper',
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

    original_run_gates = OfflineHarness._run_gates

    def append_gate_result_spoof(self: OfflineHarness, candidate, baseline):  # type: ignore[no-untyped-def]
        trace = original_run_gates(self, candidate, baseline)
        runs_dir = self._workspace / "evals" / "runs"
        run_dirs = [path for path in runs_dir.iterdir() if path.is_dir()]
        assert len(run_dirs) == 1
        evidence_path = run_dirs[0] / "judge_evidence.jsonl"
        with evidence_path.open("a", encoding="utf-8") as evidence_file:
            evidence_file.write(
                json.dumps(
                    {
                        "recordId": f"semantic:{candidate.content_hash}:spoof",
                        "judgeMode": "local_fallback",
                        "score": {
                            "process": 1.0,
                            "output": 1.0,
                            "token": 1.0,
                            "aggregate": 1.0,
                        },
                        "calibrated": False,
                    }
                )
                + "\n"
            )
        return trace

    monkeypatch.setattr(OfflineHarness, "_run_gates", append_gate_result_spoof)
    manifest = OfflineHarness(workspace=tmp_path, gates=[_PassingSemanticGate()]).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    evidence_text = (run_dir / "judge_evidence.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in evidence_text.splitlines()]
    assert "spoof" not in evidence_text
    assert [row["recordId"] for row in rows] == [
        f"semantic:{manifest.gate_verdicts[0].candidate_hash}"
    ]
    assert manifest.judge_evidence_paths == {"semantic_fidelity": "judge_evidence.jsonl"}


def test_harness_preserves_multiple_trusted_semantic_evidence_rows(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "multiple_semantic_candidates.py"
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
    'optimizerName': 'multiple-semantic-candidates-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [
        {
            'skillName': payload['skillName'],
            'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse verbose answers. Remove required detail.\\n',
            'score': 0.95,
            'iteration': 1,
            'rationale': 'semantic gate should reject this candidate'
        },
        {
            'skillName': payload['skillName'],
            'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
            'score': 0.9,
            'iteration': 2,
            'rationale': 'valid candidate should pass'
        }
    ]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(
        workspace=tmp_path,
        gates=[_FirstCandidateFailingSemanticGate()],
    ).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    rows = [
        json.loads(line)
        for line in (run_dir / "judge_evidence.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    semantic_results = [
        result for result in manifest.gate_verdicts if result.gate_name == "4-semantic-fidelity"
    ]
    assert manifest.final_status == "promoted_to_pr"
    assert len(semantic_results) == 2
    assert len(rows) == 2
    assert [row["recordId"] for row in rows] == [
        f"semantic:{result.candidate_hash}" for result in semantic_results
    ]


def test_harness_fails_closed_when_semantic_evidence_target_becomes_directory_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_directory_before_publish.py"
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
    'optimizerName': 'semantic-directory-before-publish-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'valid candidate should pass'
    }]
}))
""".lstrip(),
    )

    original_build_diff_patch = OfflineHarness._build_diff_patch

    def replace_evidence_target_before_publish(self, baseline, promoted):  # type: ignore[no-untyped-def]
        run_dirs = [
            path for path in (self._workspace / "evals" / "runs").iterdir() if path.is_dir()
        ]
        assert len(run_dirs) == 1
        # Check that at least one gate has buffered evidence rows in its writer.
        evidence_gates = [
            gate
            for gate in self._gates
            if isinstance(gate, SemanticEvidenceRecorder | SemanticFidelityGate)
        ]
        assert any(gate._writer is not None and gate._writer._rows for gate in evidence_gates)
        evidence_path = run_dirs[0] / "judge_evidence.jsonl"
        evidence_path.mkdir()
        return original_build_diff_patch(self, baseline, promoted)

    monkeypatch.setattr(
        OfflineHarness,
        "_build_diff_patch",
        replace_evidence_target_before_publish,
    )
    with pytest.raises(OSError, match="semantic judge evidence path"):
        OfflineHarness(workspace=tmp_path).run(
            skill_name="demo-skill",
            optimizer_command=[sys.executable, str(script)],
            tiers=["A", "C"],
        )

    run_dirs = [path for path in (tmp_path / "evals" / "runs").iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert (run_dir / "judge_evidence.jsonl").is_dir()
    assert not (run_dir / "manifest.json").exists()
    assert not any(
        json.loads(line)["recordId"].startswith("semantic:")
        for evidence_path in run_dir.rglob("*.jsonl")
        if evidence_path.is_file()
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    )


def test_harness_fails_closed_on_optimizer_spoofed_semantic_judge_evidence_directory(
    tmp_path: Path,
) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "semantic_spoofed_directory.py"
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
Path('../judge_evidence.jsonl').mkdir()
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'semantic-spoofed-directory-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': {'code': 'no_improvement', 'message': 'No skill candidate improved.'},
    'candidates': []
}))
""".lstrip(),
    )

    with pytest.raises(IsADirectoryError, match="semantic fidelity judge evidence path"):
        OfflineHarness(workspace=tmp_path).run(
            skill_name="demo-skill",
            optimizer_command=[sys.executable, str(script)],
            tiers=["A", "C"],
        )
