"""OfflineHarness skeleton — spec §3.2 / §3.7 / §6.0 / §6.4.2 / §6.5.

This is the M4 offline-evolution skeleton: data models for Skill content,
Candidate / Baseline, the per-run manifest, and the harness that walks the
ordered ``GATES`` registry with short-circuit semantics. Later milestones
will layer judges, GEPA selection, and PR application on top.
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from nanobot.evolve._base import EvolveBase, FrozenEvolveBase
from nanobot.evolve.exceptions import ConfigError
from nanobot.evolve.gates import GATES, Gate, GateResult

# ---------------------------------------------------------------------------
# Pydantic data models (§3.2 / §3.7)
# ---------------------------------------------------------------------------


class SkillFrontmatter(EvolveBase):
    name: str
    description: str
    origin: Literal["bundled", "user", "agent"]
    created_by: str
    created_at: datetime
    evolved_from_run: Optional[str] = None
    evolved_at: Optional[datetime] = None
    parent_skill_hash: Optional[str] = None


class SkillContent(EvolveBase):
    skill_name: str
    skill_md_content: str
    frontmatter: SkillFrontmatter
    body_md: str
    cache_key_hash: str
    size_metrics: dict[str, int]
    content_hash: str


class Baseline(SkillContent):
    loaded_from: str
    loaded_at: datetime


class Candidate(SkillContent):
    parent_baseline_hash: str
    gepa_iteration: int
    gepa_seed: Optional[int] = None


class JudgeSummary(EvolveBase):
    record_count: int
    median_aggregate: float
    median_process: float
    median_output: float
    median_token: float
    consensus_split_count: int


class RunManifest(FrozenEvolveBase):
    # FrozenEvolveBase carries the immutable-once-written contract (§3.7) while
    # propagating EvolveBase's camelCase alias contract — see `_base.py` for the
    # rationale on centralising this overlay.

    run_id: str
    started_at: datetime
    finished_at: datetime
    nanobot_version: str
    evolve_extra_version: dict[str, str]
    skill_name: str
    baseline_hash: str
    candidate_hashes: list[str]
    promoted_candidate_hash: Optional[str]
    gate_verdicts: list[GateResult]
    judge_summary: JudgeSummary
    final_status: Literal[
        "promoted_to_pr", "rejected_by_gate", "no_improvement", "harness_error"
    ]
    tiers_used: list[Literal["A", "B", "C", "D"]]
    record_count_per_tier: dict[str, int]
    judge_pool_health: dict[str, str]


def load_manifest(path: Path) -> RunManifest:
    """Load and validate a RunManifest from JSON."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid manifest JSON at {path}: {exc}") from exc
    return RunManifest.model_validate(raw)


def dump_manifest(path: Path, manifest: RunManifest) -> None:
    """Write a RunManifest JSON file using the model's alias contract."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        manifest.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Harness (§6.0 / §6.4.2 / §6.5)
# ---------------------------------------------------------------------------


class OfflineHarness:
    """Skeleton harness — owns gate iteration and final-status arbitration.

    M4 round 4 lands only ``_run_gates`` + ``_compute_final_status``; the
    end-to-end ``run()`` orchestrator is t-14 / t-15 territory.
    """

    def __init__(self, *, workspace: Path, gates: Optional[list[Gate]] = None) -> None:
        """Construct an OfflineHarness over ``workspace``.

        ``gates`` is an optional dependency-injection seam — tests substitute
        stub gate lists here instead of mutating the module-level ``GATES``
        registry. Note: only the *list* is shallow-copied; the Gate instances
        themselves are shared by reference. Per §6.4.1 determinism intent,
        injected Gate instances MUST be stateless across ``_run_gates``
        invocations, otherwise mutable per-run state on a stub will leak
        between sibling harnesses that share the same gate list.
        """
        if not workspace.is_dir():
            raise ConfigError(f"workspace not a directory: {workspace}")
        self._workspace = workspace
        self._gates: list[Gate] = list(gates) if gates is not None else list(GATES)

    # --- gate execution --------------------------------------------------

    def _run_gates(self, candidate: Candidate, baseline: Baseline) -> list[GateResult]:
        """Iterate ``self._gates`` in order; short-circuit on first fail.

        Per spec §6.0 point 3 / decision #109: ``Exception`` subclasses raised
        from ``gate.evaluate(...)`` are converted into a synthetic GateResult
        with ``verdict='fail'`` + ``failure_reason='gate-internal-error: ...'``.

        ``KeyboardInterrupt`` / ``SystemExit`` / ``asyncio.CancelledError``
        derive from ``BaseException`` (not ``Exception``) and propagate
        transparently — never swallowed into a verdict.
        """
        trace: list[GateResult] = []
        for gate in self._gates:
            t0 = time.perf_counter()
            try:
                result = gate.evaluate(candidate, baseline)
            except Exception as exc:  # NOT BaseException — see docstring.
                duration_ms = int((time.perf_counter() - t0) * 1000)
                reason = f"gate-internal-error: {type(exc).__name__}: {str(exc)[:200]}"
                self._write_gate_error(gate, candidate, exc)
                result = GateResult(
                    gate_name=gate.name,
                    candidate_hash=candidate.content_hash,
                    baseline_hash=baseline.content_hash,
                    verdict="fail",
                    metrics={},
                    failure_reason=reason,
                    timestamp=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                )
            trace.append(result)
            if result.verdict == "fail":
                break  # §6.4.2 — first fail short-circuits the gate chain.
        return trace

    def _write_gate_error(self, gate: Gate, candidate: Candidate, exc: BaseException) -> None:
        """Best-effort traceback dump per §6.0 point 5 / decision #109.

        Path: ``<workspace>/gates/<candidate-hash-prefix>/<gate.name>.error.txt``.
        Skeleton: swallow write failures — the synthetic GateResult is the
        primary signal; a missing error file must never mask the failure path.
        """
        try:
            hash_prefix = candidate.content_hash[:12] or "unknown"
            err_dir = self._workspace / "gates" / hash_prefix
            err_dir.mkdir(parents=True, exist_ok=True)
            err_path = err_dir / f"{gate.name}.error.txt"
            err_path.write_text(
                "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            )
        except Exception:
            # Diagnostic IO failure must not derail the main control flow.
            pass

    # --- final status arbitration (§6.5) --------------------------------

    def _compute_final_status(
        self,
        promoted: Optional[Candidate],
        all_candidates: list[Candidate],
        baseline: Baseline,
        *,
        gate_traces: Optional[dict[str, list[GateResult]]] = None,
    ) -> Literal["promoted_to_pr", "rejected_by_gate", "no_improvement"]:
        """§6.5 decision tree (skeleton).

        - ``promoted`` is not None → ``"promoted_to_pr"``.
        - Otherwise, if any candidate has a recorded fail trace in
          ``gate_traces`` → ``"rejected_by_gate"``.
        - Else → ``"no_improvement"``.

        ``gate_traces`` is keyed by ``candidate.content_hash`` → list of
        GateResults. ``baseline`` is part of the signature per the plan even
        though this skeleton does not yet diff candidate vs. baseline scores.
        """
        del baseline  # unused in the skeleton; documents the §6.5 signature.
        if promoted is not None:
            return "promoted_to_pr"
        if gate_traces:
            for cand in all_candidates:
                trace = gate_traces.get(cand.content_hash, [])
                if any(r.verdict == "fail" for r in trace):
                    return "rejected_by_gate"
        return "no_improvement"
