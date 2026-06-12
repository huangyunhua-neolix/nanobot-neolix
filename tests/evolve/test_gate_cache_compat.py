"""Tests for CacheCompatGate (gate 3 — "3-cache-compat")."""

from __future__ import annotations

from dataclasses import dataclass

from nanobot.evolve.gates.cache_compat import CacheCompatGate


@dataclass
class _FakeCandidate:
    content_hash: str
    cache_key_hash: str


@dataclass
class _FakeBaseline:
    content_hash: str
    cache_key_hash: str


def test_gate_name_is_three_cache_compat() -> None:
    assert CacheCompatGate().name == "3-cache-compat"


def test_gate_is_deterministic() -> None:
    assert CacheCompatGate.NONDETERMINISTIC is False


def test_equal_cache_keys_produce_pass_with_evidence() -> None:
    candidate = _FakeCandidate(content_hash="cand-aaa", cache_key_hash="key-xyz")
    baseline = _FakeBaseline(content_hash="base-bbb", cache_key_hash="key-xyz")

    result = CacheCompatGate().evaluate(candidate, baseline)  # type: ignore[arg-type]

    assert result.gate_name == "3-cache-compat"
    assert result.verdict == "pass"
    assert result.failure_reason is None
    assert result.metrics == {"byte_diff_present": 0.0}
    assert result.evidence is not None
    assert result.evidence["candidate_cache_key"] == "key-xyz"
    assert result.evidence["baseline_cache_key"] == "key-xyz"
    assert result.candidate_hash == "cand-aaa"
    assert result.baseline_hash == "base-bbb"
    assert result.timestamp is not None
    assert result.duration_ms >= 0


def test_different_cache_keys_produce_fail_with_evidence() -> None:
    candidate = _FakeCandidate(content_hash="cand-aaa", cache_key_hash="key-new")
    baseline = _FakeBaseline(content_hash="base-bbb", cache_key_hash="key-old")

    result = CacheCompatGate().evaluate(candidate, baseline)  # type: ignore[arg-type]

    assert result.verdict == "fail"
    assert result.metrics == {"byte_diff_present": 1.0}
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("cache-key-mismatch")
    assert "candidate=key-new" in result.failure_reason
    assert "baseline=key-old" in result.failure_reason
    # Decision #116: evidence MUST be populated on fail path too.
    assert result.evidence is not None
    assert result.evidence["candidate_cache_key"] == "key-new"
    assert result.evidence["baseline_cache_key"] == "key-old"
    assert result.gate_name == "3-cache-compat"
    assert result.candidate_hash == "cand-aaa"
    assert result.baseline_hash == "base-bbb"
    assert result.timestamp is not None
    assert result.duration_ms >= 0
