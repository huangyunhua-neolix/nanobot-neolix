"""Tests for ``nanobot.evolve.harness`` — t-11 skeleton.

Covers spec §3.2 (data models), §3.7 (RunManifest frozen + extra=forbid),
§6.0 point 3 (Exception→fail mapping; BaseException propagation),
§6.4.2 (first-fail short-circuit), §6.5 (_compute_final_status decision tree).
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError

from nanobot.evolve.exceptions import ConfigError
from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.harness import (
    Baseline,
    Candidate,
    JudgeSummary,
    OfflineHarness,
    RunManifest,
    SkillFrontmatter,
    dump_manifest,
    load_manifest,
)

# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------


def _make_frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="demo",
        origin="bundled",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_baseline() -> Baseline:
    return Baseline(
        skill_name="demo-skill",
        skill_md_content="# demo",
        frontmatter=_make_frontmatter(),
        body_md="body",
        cache_key_hash="cache-base",
        size_metrics={"lines": 100},
        content_hash="base-hash",
        loaded_from="bundled:demo-skill",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _make_candidate(content_hash: str = "cand-hash") -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content="# demo v2",
        frontmatter=_make_frontmatter(),
        body_md="body v2",
        cache_key_hash="cache-base",  # same as baseline so cache_compat would pass
        size_metrics={"lines": 110},
        content_hash=content_hash,
        parent_baseline_hash="base-hash",
        gepa_iteration=1,
    )


def _make_judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=10,
        median_aggregate=0.8,
        median_process=0.8,
        median_output=0.8,
        median_token=0.8,
        consensus_split_count=0,
    )


# ---------------------------------------------------------------------------
# Stub Gates
# ---------------------------------------------------------------------------


def _ok_result(gate_name: str, candidate: Candidate, baseline: Baseline) -> GateResult:
    return GateResult(
        gate_name=gate_name,
        candidate_hash=candidate.content_hash,
        baseline_hash=baseline.content_hash,
        verdict="pass",
        metrics={},
        timestamp=datetime.now(timezone.utc),
        duration_ms=0,
    )


def _fail_result(gate_name: str, candidate: Candidate, baseline: Baseline) -> GateResult:
    return GateResult(
        gate_name=gate_name,
        candidate_hash=candidate.content_hash,
        baseline_hash=baseline.content_hash,
        verdict="fail",
        metrics={},
        failure_reason="stub-fail",
        timestamp=datetime.now(timezone.utc),
        duration_ms=0,
    )


class _PassGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self, gate_name: str, counter: list[str]) -> None:
        self._name = gate_name
        self._counter = counter

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        self._counter.append(self._name)
        return _ok_result(self._name, candidate, baseline)


class _FailGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self, gate_name: str, counter: list[str]) -> None:
        self._name = gate_name
        self._counter = counter

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        self._counter.append(self._name)
        return _fail_result(self._name, candidate, baseline)


class _RaiseGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self, gate_name: str, exc: BaseException) -> None:
        self._name = gate_name
        self._exc = exc

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        raise self._exc


class _SlowCleanupGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    def __init__(self) -> None:
        self.cleaned = False

    @property
    def name(self) -> str:
        return "1-slow"

    def evaluate(self, candidate, baseline):  # type: ignore[override]
        time.sleep(2)
        return _ok_result(self.name, candidate, baseline)

    def cleanup_after_timeout(self) -> None:
        self.cleaned = True


# ---------------------------------------------------------------------------
# Constructor / workspace validation
# ---------------------------------------------------------------------------


def test_workspace_not_dir_raises_config_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(ConfigError):
        OfflineHarness(workspace=missing)


def test_workspace_dir_accepted(tmp_path: Path) -> None:
    # Constructor with a valid workspace must not raise.
    OfflineHarness(workspace=tmp_path)


# ---------------------------------------------------------------------------
# _run_gates short-circuit + ordering
# ---------------------------------------------------------------------------


def test_run_gates_short_circuits_on_first_fail(tmp_path: Path) -> None:
    invoked: list[str] = []
    gates = [
        _FailGate("1-fail", invoked),
        _PassGate("2-skipped", invoked),
        _PassGate("3-skipped", invoked),
    ]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    trace = harness._run_gates(_make_candidate(), _make_baseline())
    assert len(trace) == 1
    assert trace[0].verdict == "fail"
    assert invoked == ["1-fail"], "gates after a fail must NOT be invoked"


def test_run_gates_returns_all_pass_traces_when_all_pass(tmp_path: Path) -> None:
    invoked: list[str] = []
    gates = [
        _PassGate("1-ok", invoked),
        _PassGate("2-ok", invoked),
        _PassGate("3-ok", invoked),
    ]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    trace = harness._run_gates(_make_candidate(), _make_baseline())
    assert len(trace) == 3
    assert [r.verdict for r in trace] == ["pass", "pass", "pass"]
    assert invoked == ["1-ok", "2-ok", "3-ok"]


# ---------------------------------------------------------------------------
# Exception handling — §6.0 point 3 / decision #109
# ---------------------------------------------------------------------------


def test_run_gates_catches_gate_exception_as_verdict_fail(tmp_path: Path) -> None:
    gates = [_RaiseGate("1-explodes", ValueError("boom"))]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    trace = harness._run_gates(_make_candidate(), _make_baseline())
    assert len(trace) == 1
    assert trace[0].verdict == "fail"
    assert trace[0].failure_reason is not None
    assert "gate-internal-error" in trace[0].failure_reason
    assert "ValueError" in trace[0].failure_reason
    assert "boom" in trace[0].failure_reason


def test_run_gates_writes_error_traceback_file(tmp_path: Path) -> None:
    gates = [_RaiseGate("1-explodes", RuntimeError("kaboom"))]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    candidate = _make_candidate(content_hash="abcdef0123456789")
    harness._run_gates(candidate, _make_baseline())
    err_path = tmp_path / "gates" / "abcdef012345" / "1-explodes.error.txt"
    assert err_path.exists()
    contents = err_path.read_text()
    assert "RuntimeError" in contents
    assert "kaboom" in contents


def test_run_gates_propagates_keyboard_interrupt(tmp_path: Path) -> None:
    gates = [_RaiseGate("1-kbi", KeyboardInterrupt())]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    with pytest.raises(KeyboardInterrupt):
        harness._run_gates(_make_candidate(), _make_baseline())


def test_run_gates_propagates_system_exit(tmp_path: Path) -> None:
    gates = [_RaiseGate("1-sysexit", SystemExit(2))]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    with pytest.raises(SystemExit) as exc_info:
        harness._run_gates(_make_candidate(), _make_baseline())
    # Pin the exit CODE, not just the type — a regression that collapsed
    # SystemExit(2) into bare SystemExit() must not slip through.
    assert exc_info.value.code == 2


def test_run_gates_propagates_cancelled_error(tmp_path: Path) -> None:
    # asyncio.CancelledError derives from BaseException on Python 3.8+; the
    # harness's ``except Exception`` clause MUST let it escape so a cancelled
    # outer task is not silently downgraded into a verdict='fail' trace.
    gates = [_RaiseGate("1-cancel", asyncio.CancelledError())]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    with pytest.raises(asyncio.CancelledError):
        harness._run_gates(_make_candidate(), _make_baseline())


def test_run_gates_synthetic_fail_short_circuits(tmp_path: Path) -> None:
    # A gate-internal-error must short-circuit subsequent gates identically to
    # an explicit verdict='fail'. Guards against a refactor that moves the
    # ``if result.verdict == 'fail': break`` inside the try block.
    invoked: list[str] = []
    gates = [
        _RaiseGate("1-boom", ValueError("boom")),
        _PassGate("2-should-skip", invoked),
    ]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    trace = harness._run_gates(_make_candidate(), _make_baseline())
    assert invoked == [], "gate after a synthetic fail must NOT be invoked"
    assert len(trace) == 1
    assert trace[0].verdict == "fail"
    assert trace[0].failure_reason is not None
    assert "gate-internal-error" in trace[0].failure_reason


def test_run_gates_timeout_returns_synthetic_failure_and_cleans_up(tmp_path: Path) -> None:
    gate = _SlowCleanupGate()
    harness = OfflineHarness(workspace=tmp_path, gates=[gate], gate_timeout_seconds=0.1)

    trace = harness._run_gates(_make_candidate(), _make_baseline())

    assert len(trace) == 1
    assert trace[0].verdict == "fail"
    assert trace[0].failure_reason == "gate-timeout:1-slow"
    assert gate.cleaned is True


def test_run_gates_error_file_path_uses_unknown_when_hash_empty(tmp_path: Path) -> None:
    # The _write_gate_error fallback branch ``hash_prefix = ... or "unknown"``
    # is exercised when content_hash is empty — without this test, the
    # fallback has zero coverage and a regression replacing it (e.g. with a
    # bare ``[:12]``) would create a directory named "" instead.
    gates = [_RaiseGate("1-explodes", RuntimeError("oops"))]
    harness = OfflineHarness(workspace=tmp_path, gates=gates)
    candidate = _make_candidate(content_hash="")
    harness._run_gates(candidate, _make_baseline())
    err_path = tmp_path / "gates" / "unknown" / "1-explodes.error.txt"
    assert err_path.exists()
    contents = err_path.read_text()
    assert "RuntimeError" in contents
    assert "oops" in contents


def test_run_gates_continues_when_error_file_write_fails(tmp_path: Path) -> None:
    # _write_gate_error wraps its IO in try/except so a missing or read-only
    # workspace cannot mask the synthetic fail GateResult — the primary
    # signal. Exercise this by removing the workspace mid-flight (tmp_path
    # itself stays around for pytest teardown bookkeeping; we recreate it
    # under a sub-dir so we can rmtree just the harness's view).
    workspace = tmp_path / "ws"
    workspace.mkdir()
    harness = OfflineHarness(workspace=workspace, gates=[_RaiseGate("1-boom", ValueError("x"))])
    # Make the gates dir un-writable on POSIX so the mkdir inside
    # _write_gate_error fails. (chmod 0o400 = read-only for owner.)
    gates_dir = workspace / "gates"
    gates_dir.mkdir()
    original_mode = gates_dir.stat().st_mode
    if sys.platform == "win32":
        # On Windows chmod-based read-only is unreliable; rmtree the gates
        # dir AND the workspace so the err_dir.mkdir(parents=True) fails.
        shutil.rmtree(workspace)
    else:
        gates_dir.chmod(0o400)
    try:
        trace = harness._run_gates(_make_candidate(), _make_baseline())
    finally:
        # Restore perms so pytest tmp_path cleanup can rm the tree.
        if sys.platform != "win32" and gates_dir.exists():
            gates_dir.chmod(original_mode)
    # The synthetic fail GateResult is still produced; no second exception
    # escaped through _write_gate_error.
    assert len(trace) == 1
    assert trace[0].verdict == "fail"
    assert trace[0].failure_reason is not None
    assert "gate-internal-error" in trace[0].failure_reason


# ---------------------------------------------------------------------------
# _compute_final_status — §6.5
# ---------------------------------------------------------------------------


def test_compute_final_status_promoted_to_pr(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path, gates=[])
    cand = _make_candidate()
    baseline = _make_baseline()
    assert harness._compute_final_status(cand, [cand], baseline) == "promoted_to_pr"


def test_compute_final_status_rejected_by_gate(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path, gates=[])
    cand = _make_candidate()
    baseline = _make_baseline()
    fail_trace = [_fail_result("1-fail", cand, baseline)]
    status = harness._compute_final_status(
        None, [cand], baseline, gate_traces={cand.content_hash: fail_trace}
    )
    assert status == "rejected_by_gate"


def test_compute_final_status_no_improvement(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path, gates=[])
    cand = _make_candidate()
    baseline = _make_baseline()
    pass_trace = [_ok_result("1-ok", cand, baseline)]
    status = harness._compute_final_status(
        None, [cand], baseline, gate_traces={cand.content_hash: pass_trace}
    )
    assert status == "no_improvement"


def test_compute_final_status_no_traces_is_no_improvement(tmp_path: Path) -> None:
    harness = OfflineHarness(workspace=tmp_path, gates=[])
    cand = _make_candidate()
    baseline = _make_baseline()
    assert harness._compute_final_status(None, [cand], baseline) == "no_improvement"


def test_compute_final_status_promoted_precedes_fail_trace(tmp_path: Path) -> None:
    # A non-None ``promoted`` MUST short-circuit BEFORE the fail-trace check.
    # A regression flipping the order would mis-classify a promoted candidate
    # as ``rejected_by_gate`` whenever its trace also contains a fail (e.g.
    # an earlier GEPA iteration's candidate failed before the promoted one).
    harness = OfflineHarness(workspace=tmp_path, gates=[])
    cand = _make_candidate()
    baseline = _make_baseline()
    fail_trace = [_fail_result("1-fail", cand, baseline)]
    status = harness._compute_final_status(
        cand, [cand], baseline, gate_traces={cand.content_hash: fail_trace}
    )
    assert status == "promoted_to_pr"


# ---------------------------------------------------------------------------
# RunManifest — §3.7 (frozen + extra=forbid)
# ---------------------------------------------------------------------------


def _make_run_manifest(**overrides: object) -> RunManifest:
    # Defaults model a fully promotable manifest (promoted_candidate_hash set,
    # final_status="promoted_to_pr") so manifest serialization tests get a
    # well-formed, round-trip-safe fixture without boilerplate. Pass explicit
    # overrides to test other status paths.
    fields: dict[str, object] = {
        "run_id": "run-abc",
        "started_at": datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 6, 13, 12, 5, tzinfo=timezone.utc),
        "nanobot_version": "0.0.0",
        "evolve_extra_version": {"dspy": "not-installed"},
        "skill_name": "demo-skill",
        "baseline_hash": "basehash00112233",
        "candidate_hashes": ["deadbeefcafebabe"],
        "promoted_candidate_hash": "deadbeefcafebabe",
        "gate_verdicts": [],
        "judge_summary": _make_judge_summary(),
        "final_status": "promoted_to_pr",
        "tiers_used": ["A", "C"],
        "record_count_per_tier": {"A": 1, "C": 1},
        "judge_pool_health": {"pool": "ok"},
    }
    fields.update(overrides)
    return RunManifest(**fields)  # type: ignore[arg-type]


def test_run_manifest_is_frozen() -> None:
    manifest = _make_run_manifest()
    with pytest.raises(ValidationError):
        manifest.run_id = "mutated"  # type: ignore[misc]


def test_run_manifest_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        _make_run_manifest(unexpected_field="boom")


# ---------------------------------------------------------------------------
# Candidate validation sanity
# ---------------------------------------------------------------------------


def test_candidate_pydantic_validation_required_fields() -> None:
    with pytest.raises(ValidationError):
        Candidate(
            skill_name="demo-skill",
            skill_md_content="# demo",
            frontmatter=_make_frontmatter(),
            body_md="body",
            # cache_key_hash intentionally omitted
            size_metrics={"lines": 100},
            content_hash="cand-hash",
            parent_baseline_hash="base-hash",
            gepa_iteration=1,
        )


# ---------------------------------------------------------------------------
# dump_manifest / load_manifest helpers
# ---------------------------------------------------------------------------


def test_dump_and_load_manifest_round_trip(tmp_path: Path) -> None:
    manifest = _make_run_manifest()
    path = tmp_path / "manifest.json"

    dump_manifest(path, manifest)
    loaded = load_manifest(path)

    assert loaded == manifest
    assert json.loads(path.read_text(encoding="utf-8"))["runId"] == "run-abc"


def test_load_manifest_invalid_json_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid manifest JSON"):
        load_manifest(path)


def test_load_manifest_validation_error_propagates(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"runId": "missing-fields"}', encoding="utf-8")

    with pytest.raises(ValidationError, match="validation error"):
        load_manifest(path)


def test_dump_manifest_creates_parent_directories(tmp_path: Path) -> None:
    manifest = _make_run_manifest()
    path = tmp_path / "nested" / "dir" / "manifest.json"

    dump_manifest(path, manifest)

    assert path.is_file()
    assert load_manifest(path) == manifest
