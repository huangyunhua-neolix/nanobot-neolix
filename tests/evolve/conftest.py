"""Shared fake Candidate/Baseline fixtures for evolve gate tests.

Defined here so all gate test files share ONE shape. When t-11 lands the real
Pydantic Candidate/Baseline, this is the single place to update.

Per-file fakes in ``test_gate_test_pass.py`` / ``test_gate_skill_size.py`` /
``test_gate_cache_compat.py`` are intentionally left in place during the M4
skeleton round (cross-task ownership). Later rounds may migrate them onto
these fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest


@dataclass
class FakeCandidate:
    content_hash: str = "cand-hash"
    cache_key_hash: str = "cand-cache-key"
    # ``float`` matches the eventual Pydantic ``dict[str, float]`` schema for
    # ``size_metrics`` (the per-file ``int``-typed fake in ``test_gate_test_pass``
    # is the divergent shape; this is the canonical one).
    size_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class FakeBaseline:
    content_hash: str = "base-hash"
    cache_key_hash: str = "base-cache-key"
    size_metrics: dict[str, float] = field(default_factory=dict)


@pytest.fixture
def shared_passing_candidate() -> FakeCandidate:
    """A candidate that satisfies all three M4 gates by default.

    Padded above the tier-C 1.00 and tier-A 0.80 pass-rate floors so a future
    floor tightening surfaces in the gate-specific tests rather than flipping
    this fixture to fail and breaking the e2e smoke as a false positive.
    Current values: tier-C = 10/10 (1.00), tier-A = 24/25 (0.96).
    """
    return FakeCandidate(
        content_hash="cand-shared",
        cache_key_hash="key-shared",
        size_metrics={
            # Gate 1 (test_pass) — padded above tier-c (1.00) and tier-a (0.80) floors.
            "tier_c_pass": 10.0,
            "tier_c_total": 10.0,
            "tier_a_pass": 24.0,
            "tier_a_total": 25.0,
            # Gate 2 (skill_size) — within both 400 hard cap and 150 delta cap.
            "lines": 300.0,
        },
    )


@pytest.fixture
def shared_baseline() -> FakeBaseline:
    return FakeBaseline(
        content_hash="base-shared",
        cache_key_hash="key-shared",  # matches candidate → gate 3 passes
        size_metrics={"lines": 280.0},
    )
