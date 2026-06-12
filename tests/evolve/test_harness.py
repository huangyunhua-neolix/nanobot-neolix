"""Tests for ``nanobot.evolve.harness`` — t-11 skeleton.

Covers spec §3.2 (data models), §3.7 (RunManifest frozen + extra=forbid),
§6.0 point 3 (Exception→fail mapping; BaseException propagation),
§6.4.2 (first-fail short-circuit), §6.5 (_compute_final_status decision tree).
"""

from __future__ import annotations

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
    with pytest.raises(SystemExit):
        harness._run_gates(_make_candidate(), _make_baseline())


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


# ---------------------------------------------------------------------------
# RunManifest — §3.7 (frozen + extra=forbid)
# ---------------------------------------------------------------------------


def _make_run_manifest(**overrides) -> RunManifest:
    fields = dict(
        run_id="run-1",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        nanobot_version="0.0.0",
        evolve_extra_version={"dspy": "2.4.0"},
        skill_name="demo-skill",
        baseline_hash="base-hash",
        candidate_hashes=["cand-1"],
        promoted_candidate_hash=None,
        gate_verdicts=[],
        judge_summary=_make_judge_summary(),
        final_status="no_improvement",
        tiers_used=["A", "C"],
        record_count_per_tier={"A": 5, "C": 3},
        judge_pool_health={"pool-a": "ok"},
    )
    fields.update(overrides)
    return RunManifest(**fields)


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
