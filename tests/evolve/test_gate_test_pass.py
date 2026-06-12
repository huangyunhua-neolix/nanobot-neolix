"""Tests for nanobot.evolve.gates.test_pass.TestPassGate (spec §6.1, t-08).

Covers:
- name property
- precondition violations (§6.1.2 / decision #120)
- pass case (counts above both floors)
- tier-A fail case (counts below 80% floor)
- tier-C fail case (counts below 100% floor)
- metrics dict contract keys (§6.1.4)
- integer cross-multiplication boundary (decision #115)
"""

from typing import TYPE_CHECKING

import pytest

from nanobot.evolve.exceptions import GateInternalError
from nanobot.evolve.gates import GateResult
from nanobot.evolve.gates.test_pass import TestPassGate

if TYPE_CHECKING:  # pragma: no cover - typing only
    from nanobot.evolve.harness import Baseline, Candidate  # noqa: F401


class _FakeCandidate:
    """Duck for Candidate — t-11 will land the real Pydantic model."""

    def __init__(self, size_metrics: dict[str, int]) -> None:
        self.content_hash = "cand-hash"
        self.cache_key_hash = "cand-cache-key"
        self.size_metrics = size_metrics


class _FakeBaseline:
    """Duck for Baseline — t-11 will land the real Pydantic model."""

    def __init__(self) -> None:
        self.content_hash = "base-hash"
        self.cache_key_hash = "base-cache-key"


def _make_candidate(
    *,
    tier_c_pass: int,
    tier_c_total: int,
    tier_a_pass: int,
    tier_a_total: int,
) -> _FakeCandidate:
    return _FakeCandidate(
        {
            "tier_c_pass": tier_c_pass,
            "tier_c_total": tier_c_total,
            "tier_a_pass": tier_a_pass,
            "tier_a_total": tier_a_total,
        }
    )


def test_gate_name():
    gate = TestPassGate()
    assert gate.name == "1-test-pass"


def test_gate_is_deterministic():
    assert TestPassGate.NONDETERMINISTIC is False


def test_pass_verdict():
    """Spec DoD: 5/5 tier-C, 20/25 tier-A → pass."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=20, tier_a_total=25
    )
    result = gate.evaluate(cand, _FakeBaseline())
    assert isinstance(result, GateResult)
    assert result.verdict == "pass"
    assert result.failure_reason is None
    assert result.gate_name == "1-test-pass"
    assert result.candidate_hash == "cand-hash"
    assert result.baseline_hash == "base-hash"


def test_tier_a_fail_verdict():
    """Spec DoD: 5/5 tier-C, 17/25 tier-A → fail with tier-a-rate-floor reason."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=17, tier_a_total=25
    )
    result = gate.evaluate(cand, _FakeBaseline())
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("tier-a-rate-floor")


def test_tier_c_fail_verdict():
    """Tier C below 100% floor — fail with tier-c-rate-floor reason. Path 1 wins."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=4, tier_c_total=5, tier_a_pass=25, tier_a_total=25
    )
    result = gate.evaluate(cand, _FakeBaseline())
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("tier-c-rate-floor")


def test_tier_c_fail_takes_precedence_over_tier_a():
    """When both tiers below floor, the tier-c reason is reported (path 1 first)."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=4, tier_c_total=5, tier_a_pass=10, tier_a_total=25
    )
    result = gate.evaluate(cand, _FakeBaseline())
    assert result.verdict == "fail"
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("tier-c-rate-floor")


def test_precondition_tier_c_empty():
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=0, tier_c_total=0, tier_a_pass=20, tier_a_total=25
    )
    with pytest.raises(GateInternalError) as exc:
        gate.evaluate(cand, _FakeBaseline())
    assert "tier-c-empty" in str(exc.value)


def test_precondition_tier_a_empty():
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=0, tier_a_total=0
    )
    with pytest.raises(GateInternalError) as exc:
        gate.evaluate(cand, _FakeBaseline())
    assert "tier-a-empty" in str(exc.value)


def test_precondition_tier_c_below_floor():
    """DoD: len(tier_c) < 5 raises GateInternalError."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=4, tier_c_total=4, tier_a_pass=20, tier_a_total=25
    )
    with pytest.raises(GateInternalError) as exc:
        gate.evaluate(cand, _FakeBaseline())
    assert "tier-c-below-floor" in str(exc.value)


def test_metrics_contract_keys():
    """Spec §6.1.4: metrics MUST include the six contract keys."""
    gate = TestPassGate()
    cand = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=20, tier_a_total=25
    )
    result = gate.evaluate(cand, _FakeBaseline())
    required = {
        "tier_c_pass_count",
        "tier_c_total",
        "tier_c_rate",
        "tier_a_pass_count",
        "tier_a_total",
        "tier_a_rate",
    }
    assert required.issubset(set(result.metrics.keys()))
    assert result.metrics["tier_c_rate"] == pytest.approx(1.0)
    assert result.metrics["tier_a_rate"] == pytest.approx(20 / 25)


def test_integer_cross_multiplication_boundary():
    """Decision #115: bps comparison uses integer arithmetic — no FP wobble.

    20/25 = 0.80 exactly meets the 80 bps floor → pass (not fail).
    19/25 = 0.76 is below → fail.
    """
    gate = TestPassGate()
    on_boundary = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=20, tier_a_total=25
    )
    just_below = _make_candidate(
        tier_c_pass=5, tier_c_total=5, tier_a_pass=19, tier_a_total=25
    )
    assert gate.evaluate(on_boundary, _FakeBaseline()).verdict == "pass"
    assert gate.evaluate(just_below, _FakeBaseline()).verdict == "fail"
