from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_noop_optimizer_writes_no_improvement_result(tmp_path: Path) -> None:
    input_path = tmp_path / "optimizer_input.json"
    output_path = tmp_path / "optimizer_output.json"
    input_path.write_text(
        json.dumps(
            {
                "schemaVersion": "1",
                "runId": "run-1",
                "skillName": "demo-skill",
                "baselineHash": "abc123",
                "baselineSkillMdRedacted": "---\nname: demo-skill\n---\nbody",
                "evalRecordsPath": str(tmp_path / "eval.ndjson"),
                "outputDir": str(tmp_path),
                "maxCandidates": 8,
                "timeoutSeconds": 5,
                "seed": 123,
                "toolContractSnapshot": [],
                "promptTemplateSnapshot": [],
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "nanobot.evolve.noop_optimizer",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert completed.returncode == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == "1"
    assert data["optimizerName"] == "nanobot-noop-optimizer"
    assert data["candidates"] == []
    assert data["toolMetadataCandidates"] == []
    assert data["promptTemplateCandidates"] == []
    assert data["error"] == {
        "code": "no_improvement",
        "message": "No optimizer configured; deterministic no-op fallback used.",
    }
    assert data["seed"] == 123


def test_noop_optimizer_rejects_invalid_input(tmp_path: Path) -> None:
    input_path = tmp_path / "bad.json"
    output_path = tmp_path / "out.json"
    input_path.write_text("{}", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "nanobot.evolve.noop_optimizer",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
        ],
        check=False,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert completed.returncode == 2
    assert not output_path.exists()
