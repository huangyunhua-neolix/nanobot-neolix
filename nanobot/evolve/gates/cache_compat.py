"""CacheCompatGate — deterministic gate 3 ("3-cache-compat").

Verifies that a candidate revision preserves the cache-key hash of the
baseline. Equal cache-key hashes mean downstream caches remain valid; a
mismatch forces invalidation and is treated as a regression.

Evidence (both candidate and baseline cache-key hashes) is populated on
both pass and fail verdicts per decision #116 so reviewers can audit
without re-running the gate.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.exceptions import GateInternalError
from nanobot.evolve.gates import Gate, GateResult

if TYPE_CHECKING:
    from nanobot.evolve.harness import Baseline, Candidate


class CacheCompatGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "3-cache-compat"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = time.monotonic()
        candidate_key = candidate.cache_key_hash
        baseline_key = baseline.cache_key_hash
        if not candidate_key:
            raise GateInternalError(
                "malformed-candidate: cache_key_hash is empty or None"
            )
        if not baseline_key:
            raise GateInternalError(
                "malformed-baseline: cache_key_hash is empty or None"
            )
        equal = candidate_key == baseline_key

        evidence: dict[str, str] = {
            "candidate_cache_key": candidate_key,
            "baseline_cache_key": baseline_key,
        }
        metrics: dict[str, float] = {"byte_diff_present": 0.0 if equal else 1.0}

        if equal:
            verdict: str = "pass"
            failure_reason: str | None = None
        else:
            verdict = "fail"
            failure_reason = (
                f"cache-key-mismatch: candidate={candidate_key} != baseline={baseline_key}"
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict=verdict,  # type: ignore[arg-type]
            metrics=metrics,
            evidence=evidence,
            failure_reason=failure_reason,
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
