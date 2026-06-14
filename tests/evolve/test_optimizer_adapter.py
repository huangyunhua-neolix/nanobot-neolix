from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from nanobot.evolve.exceptions import ConfigError, OptimizerRunError
from nanobot.evolve.optimizer.adapter import OptimizerAdapter
from nanobot.evolve.optimizer.schemas import (
    OptimizerCandidate,
    OptimizerError,
    OptimizerInput,
    OptimizerResult,
)


def _optimizer_input(tmp_path: Path) -> OptimizerInput:
    optimizer_dir = tmp_path / "run" / "optimizer"
    return OptimizerInput(
        run_id="20260614T120000Z-demo-skill-0001",
        skill_name="demo-skill",
        baseline_hash="basehash00112233",
        baseline_skill_md_redacted="---\nname: demo-skill\n---\nbody",
        eval_records_path=str(optimizer_dir / "eval_bundle.ndjson"),
        output_dir=str(optimizer_dir),
        max_candidates=8,
        timeout_seconds=5,
        seed=123456789,
    )


def _write_optimizer_script(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_optimizer_adapter_writes_input_and_parses_output(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import json
import sys
from pathlib import Path

input_path = Path(sys.argv[sys.argv.index("--input") + 1])
output_path = Path(sys.argv[sys.argv.index("--output") + 1])
payload = json.loads(input_path.read_text(encoding="utf-8"))
assert payload["runId"] == "20260614T120000Z-demo-skill-0001"
assert payload["skillName"] == "demo-skill"
output_path.write_text(json.dumps({
    "schemaVersion": "1",
    "candidates": [{
        "skillName": payload["skillName"],
        "skillMdContent": "---\\nname: demo-skill\\n---\\nbody",
        "score": 0.91,
        "iteration": 1,
        "rationale": "clearer instructions"
    }],
    "error": None,
    "optimizerName": "test-optimizer",
    "optimizerVersion": "0.1.0",
    "seed": payload["seed"]
}), encoding="utf-8")
""".lstrip(),
    )

    result = OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
        _optimizer_input(tmp_path)
    )

    optimizer_dir = tmp_path / "run" / "optimizer"
    written_input = json.loads((optimizer_dir / "optimizer_input.json").read_text(encoding="utf-8"))
    assert written_input["schemaVersion"] == "1"
    assert written_input["baselineSkillMdRedacted"].startswith("---")
    assert result.optimizer_name == "test-optimizer"
    assert result.candidates[0].score == 0.91
    assert (optimizer_dir / "stdout.txt").read_text(encoding="utf-8") == ""
    assert (optimizer_dir / "stderr.txt").read_text(encoding="utf-8") == ""


def test_optimizer_adapter_env_allowlist_excludes_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("NANOBOT_TOKEN", "secret-token")
    monkeypatch.setenv("LANG", "C.UTF-8")
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import json
import os
import sys
from pathlib import Path

output_path = Path(sys.argv[sys.argv.index("--output") + 1])
assert os.environ.get("LANG") == "C.UTF-8"
assert "ANTHROPIC_API_KEY" not in os.environ
assert "NANOBOT_TOKEN" not in os.environ
assert not any(key.endswith("_TOKEN") for key in os.environ)
output_path.write_text(json.dumps({
    "schemaVersion": "1",
    "candidates": [{
        "skillName": "demo-skill",
        "skillMdContent": "---\\nname: demo-skill\\n---\\nbody",
        "score": 0.8,
        "iteration": 1,
        "rationale": "safe env"
    }],
    "error": None,
    "optimizerName": "test-optimizer"
}), encoding="utf-8")
""".lstrip(),
    )

    result = OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
        _optimizer_input(tmp_path)
    )

    assert result.optimizer_name == "test-optimizer"


def test_optimizer_adapter_missing_executable_maps_to_config_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing-optimizer"

    with pytest.raises(ConfigError, match="optimizer command not found"):
        OptimizerAdapter(optimizer_command=[str(missing_path)]).run(_optimizer_input(tmp_path))


def test_optimizer_adapter_ambiguous_relative_path_maps_to_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ambiguous relative optimizer command"):
        OptimizerAdapter(optimizer_command=["tools/optimizer"]).run(_optimizer_input(tmp_path))


def test_optimizer_adapter_timeout_maps_to_optimizer_run_error(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import time

time.sleep(5)
""".lstrip(),
    )
    payload = _optimizer_input(tmp_path)
    payload.timeout_seconds = 1

    with pytest.raises(OptimizerRunError, match="timed out") as exc_info:
        OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(payload)

    assert exc_info.value.run_dir == str(tmp_path / "run" / "optimizer")
    assert exc_info.value.exit_code is None


def test_optimizer_adapter_nonzero_exit_maps_to_optimizer_run_error(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(script_path, "import sys\nsys.exit(7)\n")

    with pytest.raises(OptimizerRunError, match="optimizer command exited with 7") as exc_info:
        OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
            _optimizer_input(tmp_path)
        )

    assert exc_info.value.run_dir == str(tmp_path / "run" / "optimizer")
    assert exc_info.value.exit_code == 7


def test_optimizer_adapter_missing_output_maps_to_optimizer_run_error(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(script_path, "")

    with pytest.raises(OptimizerRunError, match="missing optimizer output") as exc_info:
        OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
            _optimizer_input(tmp_path)
        )

    assert exc_info.value.exit_code is None


def test_optimizer_adapter_invalid_output_json_maps_to_optimizer_run_error(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import sys
from pathlib import Path

output_path = Path(sys.argv[sys.argv.index("--output") + 1])
output_path.write_text("not json", encoding="utf-8")
""".lstrip(),
    )

    with pytest.raises(OptimizerRunError, match="invalid optimizer output JSON"):
        OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
            _optimizer_input(tmp_path)
        )


def test_optimizer_adapter_structured_optimizer_failed_output_maps_to_error(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import json
import sys
from pathlib import Path

output_path = Path(sys.argv[sys.argv.index("--output") + 1])
output_path.write_text(json.dumps({
    "schemaVersion": "1",
    "candidates": [],
    "error": {"code": "optimizer_failed", "message": "GEPA crashed"},
    "optimizerName": "test-optimizer"
}), encoding="utf-8")
""".lstrip(),
    )

    with pytest.raises(OptimizerRunError, match="optimizer_failed: GEPA crashed"):
        OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
            _optimizer_input(tmp_path)
        )


def test_optimizer_adapter_stdout_and_stderr_are_capped(tmp_path: Path) -> None:
    script_path = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script_path,
        """
import json
import sys
from pathlib import Path

sys.stdout.buffer.write(b"O" * (10 * 1024 * 1024 + 1))
sys.stdout.buffer.flush()
sys.stderr.buffer.write(b"E" * (10 * 1024 * 1024 + 1))
sys.stderr.buffer.flush()
output_path = Path(sys.argv[sys.argv.index("--output") + 1])
output_path.write_text(json.dumps({
    "schemaVersion": "1",
    "candidates": [{
        "skillName": "demo-skill",
        "skillMdContent": "---\\nname: demo-skill\\n---\\nbody",
        "score": 0.8,
        "iteration": 1,
        "rationale": "capped streams"
    }],
    "error": None,
    "optimizerName": "test-optimizer"
}), encoding="utf-8")
""".lstrip(),
    )

    OptimizerAdapter(optimizer_command=[sys.executable, str(script_path)]).run(
        _optimizer_input(tmp_path)
    )

    stdout = (tmp_path / "run" / "optimizer" / "stdout.txt").read_bytes()
    stderr = (tmp_path / "run" / "optimizer" / "stderr.txt").read_bytes()
    assert stdout == (b"O" * (10 * 1024 * 1024)) + b"<TRUNCATED>"
    assert stderr == (b"E" * (10 * 1024 * 1024)) + b"<TRUNCATED>"


def test_optimizer_input_uses_camel_case_aliases() -> None:
    payload = OptimizerInput(
        run_id="20260614T120000Z-demo-skill-0001",
        skill_name="demo-skill",
        baseline_hash="abc123",
        baseline_skill_md_redacted="---\nname: demo-skill\n---\nbody",
        eval_records_path="/tmp/run/optimizer/eval_bundle.ndjson",
        output_dir="/tmp/run/optimizer",
        max_candidates=8,
        timeout_seconds=600,
        seed=123456789,
    ).model_dump(by_alias=True)

    assert payload["schemaVersion"] == "1"
    assert payload["runId"] == "20260614T120000Z-demo-skill-0001"
    assert payload["baselineSkillMdRedacted"].startswith("---")
    assert "baseline_skill_md_redacted" not in payload


def test_optimizer_result_success_requires_candidates() -> None:
    result = OptimizerResult(
        optimizer_name="external-wrapper",
        optimizer_version="0.1.0",
        seed=123,
        error=None,
        candidates=[
            OptimizerCandidate(
                skill_name="demo-skill",
                skill_md_content="---\nname: demo-skill\n---\nbody",
                score=0.8,
                iteration=1,
                rationale="clearer instructions",
            )
        ],
    )

    assert result.schema_version == "1"
    assert result.candidates[0].score == 0.8


def test_optimizer_result_rejects_empty_success() -> None:
    with pytest.raises(ValidationError, match="success result requires at least one candidate"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=None,
            candidates=[],
        )


def test_optimizer_result_accepts_no_improvement_only_without_candidates() -> None:
    result = OptimizerResult(
        optimizer_name="external-wrapper",
        error=OptimizerError(code="no_improvement", message="No candidate improved."),
        candidates=[],
    )

    assert result.error is not None
    assert result.error.code == "no_improvement"


def test_optimizer_result_rejects_no_improvement_with_candidates() -> None:
    with pytest.raises(ValidationError, match="no_improvement result must not include candidates"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=OptimizerError(code="no_improvement", message="No candidate improved."),
            candidates=[
                OptimizerCandidate(
                    skill_name="demo-skill",
                    skill_md_content="---\nname: demo-skill\n---\nbody",
                    score=0.8,
                    iteration=1,
                    rationale="candidate should not be present",
                )
            ],
        )


def test_optimizer_result_rejects_invalid_input_as_structured_result() -> None:
    with pytest.raises(ValidationError, match="invalid_input and optimizer_failed are adapter errors"):
        OptimizerResult(
            optimizer_name="external-wrapper",
            error=OptimizerError(code="invalid_input", message="bad input"),
            candidates=[],
        )


def test_optimizer_run_error_structured_fields() -> None:
    err = OptimizerRunError("optimizer failed", run_dir="/tmp/run", exit_code=7)

    assert err.run_dir == "/tmp/run"
    assert err.exit_code == 7
    assert OptimizerRunError.MUST_PRECEDE == frozenset({"RuntimeError"})
