"""Tests for SkillSizeGate (`2-size-cap`), spec §6.2 / plan §t-09 DoD."""

from __future__ import annotations

from dataclasses import dataclass, field

from nanobot.evolve.gates.skill_size import SkillSizeGate, count_lines


@dataclass
class _FakeCandidate:
    content_hash: str = "cand-hash"
    size_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class _FakeBaseline:
    content_hash: str = "base-hash"
    size_metrics: dict[str, float] = field(default_factory=dict)


def _make_pair(candidate_lines: int, baseline_lines: int) -> tuple[_FakeCandidate, _FakeBaseline]:
    return (
        _FakeCandidate(size_metrics={"lines": float(candidate_lines)}),
        _FakeBaseline(size_metrics={"lines": float(baseline_lines)}),
    )


def test_name_is_two_size_cap():
    assert SkillSizeGate().name == "2-size-cap"


def test_count_lines_crlf_normalization():
    assert count_lines("a\r\nb\r\nc") == 3


def test_count_lines_cr_only_normalization():
    # Classic-Mac line endings collapse to LF too.
    assert count_lines("a\rb\rc") == 3


def test_count_lines_mixed_and_empty():
    assert count_lines("") == 0
    assert count_lines("only-one-line") == 1
    assert count_lines("a\nb\nc\n") == 3


def test_hard_cap_exceeded_fails():
    cand, base = _make_pair(480, 300)
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("hard-cap-exceeded")
    assert "480" in result.failure_reason
    assert "400" in result.failure_reason


def test_delta_cap_exceeded_fails():
    cand, base = _make_pair(380, 180)  # delta = 200 > 150
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("delta-cap-exceeded")
    assert "+200" in result.failure_reason
    assert "380" in result.failure_reason
    assert "180" in result.failure_reason


def test_pass_when_both_caps_honored():
    cand, base = _make_pair(380, 300)  # delta = 80, cl = 380
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "pass"
    assert result.failure_reason is None


def test_hard_cap_boundary_equals_400_pass():
    cand, base = _make_pair(400, 300)  # cl == 400, not > 400; delta == 100, not > 150
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "pass"
    assert result.failure_reason is None


def test_hard_cap_boundary_401_fail():
    cand, base = _make_pair(401, 300)  # cl == 401 > 400
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("hard-cap-exceeded")


def test_delta_cap_boundary_equals_150_pass():
    cand, base = _make_pair(350, 200)  # delta == 150, not > 150
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "pass"
    assert result.failure_reason is None


def test_delta_cap_boundary_151_fail():
    cand, base = _make_pair(351, 200)  # delta == 151 > 150, cl == 351 < 400
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("delta-cap-exceeded")


def test_hard_cap_priority_over_delta_cap():
    # Both caps exceeded — must report hard-cap (path 1 priority).
    cand, base = _make_pair(500, 100)  # cl > 400 AND delta = 400 > 150
    result = SkillSizeGate().evaluate(cand, base)
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("hard-cap-exceeded")


def test_metrics_content_and_types():
    cand, base = _make_pair(380, 300)
    result = SkillSizeGate().evaluate(cand, base)
    m = result.metrics
    assert set(m.keys()) == {
        "candidate_lines",
        "baseline_lines",
        "delta_lines",
        "hard_cap",
        "delta_cap",
    }
    for v in m.values():
        assert isinstance(v, float)
    assert m["candidate_lines"] == 380.0
    assert m["baseline_lines"] == 300.0
    assert m["delta_lines"] == 80.0
    assert m["hard_cap"] == 400.0
    assert m["delta_cap"] == 150.0


def test_result_echoes_hashes_and_gate_name():
    cand, base = _make_pair(380, 300)
    cand.content_hash = "cand-xyz"
    base.content_hash = "base-abc"
    result = SkillSizeGate().evaluate(cand, base)
    assert result.gate_name == "2-size-cap"
    assert result.candidate_hash == "cand-xyz"
    assert result.baseline_hash == "base-abc"
    assert result.duration_ms >= 0


def test_gate_is_deterministic():
    assert SkillSizeGate.NONDETERMINISTIC is False
