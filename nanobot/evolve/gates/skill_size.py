"""Gate 2 — skill size cap (`2-size-cap`), spec §6.2.

Deterministic gate enforcing two size budgets on a candidate skill:

  1. **Hard cap** — `candidate.size_metrics["lines"] > SKILL_LINE_HARD_CAP` (400) → fail.
  2. **Delta cap** — `candidate - baseline > SKILL_LINE_DELTA_CAP` (150) → fail.

Hard-cap exceedance has priority over delta-cap exceedance in `failure_reason`.

Line counting normalizes CRLF / CR line endings to LF before splitting, so the
metric is platform-independent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import perf_counter
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.exceptions import GateInternalError
from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates._constants import SKILL_LINE_DELTA_CAP, SKILL_LINE_HARD_CAP

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate


__all__ = ["SkillSizeGate", "count_lines"]


def count_lines(content: str) -> int:
    """Return the number of lines in *content*, CRLF/CR-normalized to LF.

    `count_lines("a\\r\\nb\\r\\nc")` returns 3.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return len(normalized.splitlines())


class SkillSizeGate(Gate):
    """Deterministic size-cap gate (spec §6.2)."""

    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "2-size-cap"

    def evaluate(self, candidate: Candidate, baseline: Baseline) -> GateResult:
        start = perf_counter()

        sm_c = candidate.size_metrics
        sm_b = baseline.size_metrics
        if "lines" not in sm_c:
            raise GateInternalError(
                "malformed-candidate: size_metrics missing required key 'lines'"
            )
        if "lines" not in sm_b:
            raise GateInternalError(
                "malformed-baseline: size_metrics missing required key 'lines'"
            )
        cl = int(sm_c["lines"])
        bl = int(sm_b["lines"])
        delta = cl - bl

        verdict: str = "pass"
        failure_reason: str | None = None

        # Path 1: hard-cap exceedance has priority.
        if cl > SKILL_LINE_HARD_CAP:
            verdict = "fail"
            failure_reason = f"hard-cap-exceeded: {cl} > {SKILL_LINE_HARD_CAP} lines"
        # Path 2: delta-cap exceedance (only if hard cap passed).
        elif delta > SKILL_LINE_DELTA_CAP:
            verdict = "fail"
            failure_reason = (
                f"delta-cap-exceeded: +{delta} > +{SKILL_LINE_DELTA_CAP} lines "
                f"({cl} vs {bl} baseline)"
            )

        duration_ms = int((perf_counter() - start) * 1000)

        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict=verdict,  # type: ignore[arg-type]
            metrics={
                "candidate_lines": float(cl),
                "baseline_lines": float(bl),
                "delta_lines": float(delta),
                "hard_cap": float(SKILL_LINE_HARD_CAP),
                "delta_cap": float(SKILL_LINE_DELTA_CAP),
            },
            failure_reason=failure_reason,
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
