"""Gate 1 — ``1-test-pass`` (spec §6.1).

Deterministic pass-rate gate over Tier C (core golden) and Tier A (broad)
records. Per decision #115 the aggregation uses integer cross-multiplication
to avoid floating-point wobble at the bps thresholds.

M4 skeleton testability shim
----------------------------
This implementation does NOT yet drive the per-record subprocess loop (that
arrives with t-11's harness). For the skeleton, ``evaluate`` reads pre-loaded
counts from ``candidate.size_metrics`` (which is the dict-extension surface
defined in spec §3.2). Required keys::

    tier_c_pass, tier_c_total, tier_a_pass, tier_a_total

The harness (t-11) is the component that will populate these from the real
loader output before invoking the gate.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.exceptions import GateInternalError
from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates._constants import (
    TIER_A_PASS_RATE_FLOOR_BPS,
    TIER_C_PASS_RATE_FLOOR_BPS,
)

if TYPE_CHECKING:
    from nanobot.evolve.harness import Baseline, Candidate


__all__ = ["TestPassGate"]


_TIER_C_MIN_RECORDS = 5  # §1.1 invariant: ≥5 core golden records.


class TestPassGate(Gate):
    """Spec §6.1 gate. Deterministic verdict."""

    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "1-test-pass"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = datetime.now(timezone.utc)

        sm = candidate.size_metrics
        tier_c_pass = int(sm.get("tier_c_pass", 0))
        tier_c_total = int(sm.get("tier_c_total", 0))
        tier_a_pass = int(sm.get("tier_a_pass", 0))
        tier_a_total = int(sm.get("tier_a_total", 0))

        # Preconditions (§6.1.2 / decision #120).
        if tier_c_total == 0:
            raise GateInternalError("tier-c-empty: gate-1 requires ≥1 record")
        if tier_a_total == 0:
            raise GateInternalError("tier-a-empty: gate-1 requires ≥1 record")
        if tier_c_total < _TIER_C_MIN_RECORDS:
            raise GateInternalError(
                "tier-c-below-floor: §1.1 invariant requires ≥5 core golden"
            )

        metrics: dict[str, float] = {
            "tier_c_pass_count": float(tier_c_pass),
            "tier_c_total": float(tier_c_total),
            "tier_c_rate": tier_c_pass / tier_c_total,
            "tier_a_pass_count": float(tier_a_pass),
            "tier_a_total": float(tier_a_total),
            "tier_a_rate": tier_a_pass / tier_a_total,
        }

        verdict: str = "pass"
        failure_reason: str | None = None

        # Path 1 — Tier C floor (rate < 1.00). Integer cross-multiplication
        # per decision #115 avoids FP wobble at the bps boundary.
        if tier_c_pass * 100 < TIER_C_PASS_RATE_FLOOR_BPS * tier_c_total:
            verdict = "fail"
            failure_reason = (
                f"tier-c-rate-floor: {tier_c_pass}/{tier_c_total} "
                f"({tier_c_pass / tier_c_total:.2f}) < 1.0"
            )
        # Path 2 — only evaluated when Tier C passes.
        elif tier_a_pass * 100 < TIER_A_PASS_RATE_FLOOR_BPS * tier_a_total:
            verdict = "fail"
            failure_reason = (
                f"tier-a-rate-floor: {tier_a_pass}/{tier_a_total} "
                f"({tier_a_pass / tier_a_total:.2f}) < 0.80"
            )

        end = datetime.now(timezone.utc)
        duration_ms = int((end - start).total_seconds() * 1000)

        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict=verdict,  # type: ignore[arg-type]
            metrics=metrics,
            evidence=None,
            failure_reason=failure_reason,
            timestamp=end,
            duration_ms=duration_ms,
        )
