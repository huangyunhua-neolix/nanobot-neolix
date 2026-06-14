"""OfflineHarness skeleton — spec §3.2 / §3.7 / §6.0 / §6.4.2 / §6.5.

This is the M4 offline-evolution skeleton: data models for Skill content,
Candidate / Baseline, the per-run manifest, and the harness that walks the
ordered ``GATES`` registry with short-circuit semantics. Later milestones
will layer judges, GEPA selection, and PR application on top.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from nanobot.evolve.exceptions import ConfigError
from nanobot.evolve.gates import GATES, Gate, GateResult
from nanobot.evolve.optimizer.schemas import OptimizerCandidate, OptimizerResult
from nanobot.evolve.privacy.redact import redact
from nanobot.evolve.schemas import (
    Baseline,
    Candidate,
    JudgeSummary,
    RunManifest,
    SkillContent,
    SkillFrontmatter,
    ValidationFailure,
    dump_manifest,
    load_manifest,
)

__all__ = [
    "Baseline",
    "Candidate",
    "JudgeSummary",
    "OfflineHarness",
    "RunManifest",
    "SkillContent",
    "SkillFrontmatter",
    "ValidationFailure",
    "dump_manifest",
    "load_manifest",
]


_FRONTMATTER_RE = re.compile(r"\A---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_PATH_CLAIM_RE = re.compile(
    r"/(?:Users|home|root|Volumes)/|/(?:private/)?var/folders/|[A-Za-z]:[/\\]Users[/\\]",
    re.IGNORECASE,
)
_RUN_ID_SUFFIX_LIMIT = 10_000


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        return {}, raw

    values: dict[str, str] = {}
    for line in match.group("frontmatter").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values, match.group("body")


def _render_skill(frontmatter: SkillFrontmatter, body: str) -> str:
    values = frontmatter.model_dump(mode="json", exclude_none=True)
    lines = ["---"]
    for key in sorted(values):
        lines.append(f"{key}: {values[key]}")
    lines.append("---")
    lines.append(body.rstrip() + "\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Harness (§6.0 / §6.4.2 / §6.5)
# ---------------------------------------------------------------------------


class OfflineHarness:
    """Skeleton harness — owns gate iteration and final-status arbitration.

    M4 round 4 lands only ``_run_gates`` + ``_compute_final_status``; the
    end-to-end ``run()`` orchestrator is t-14 / t-15 territory.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        gates: Optional[list[Gate]] = None,
        gate_timeout_seconds: float = 300.0,
    ) -> None:
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
        self._gate_timeout_seconds = gate_timeout_seconds

    # --- run preparation -------------------------------------------------

    def _generate_run_id(self, skill_name: str, *, timestamp: str | None = None) -> str:
        """Return the first unused run id for ``skill_name`` at ``timestamp``."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        runs_dir = self._workspace / "evals" / "runs"
        prefix = f"{timestamp}-{skill_name}-"
        used_suffixes: set[int] = set()
        if runs_dir.is_dir():
            for path in runs_dir.iterdir():
                if not path.is_dir() or not path.name.startswith(prefix):
                    continue
                suffix = path.name.removeprefix(prefix)
                if len(suffix) == 4 and suffix.isdigit():
                    used_suffixes.add(int(suffix))

        for suffix in range(1, _RUN_ID_SUFFIX_LIMIT):
            if suffix not in used_suffixes:
                return f"{prefix}{suffix:04d}"
        raise FileExistsError(f"no available run-id suffix for {prefix}")

    def _load_baseline_skill(self, skill_name: str) -> Baseline:
        """Load the workspace skill file as a baseline model."""
        skill_path = self._workspace / "skills" / "agent" / skill_name / "SKILL.md"
        raw = skill_path.read_text(encoding="utf-8")
        frontmatter_values, body = _parse_frontmatter(raw)
        frontmatter = SkillFrontmatter.model_validate(frontmatter_values)
        return Baseline(
            skill_name=skill_name,
            skill_md_content=raw,
            frontmatter=frontmatter,
            body_md=body,
            cache_key_hash=_sha256_text(frontmatter.description),
            size_metrics={"lines": len(raw.splitlines())},
            content_hash=_sha256_text(raw),
            loaded_from=str(skill_path),
            loaded_at=datetime.now(timezone.utc),
        )

    def _load_eval_records(self, skill_name: str, tiers: list[str], run_id: str) -> Path:
        """Write a minimal redacted optimizer eval bundle for ``tiers``."""
        bundle_path = self._workspace / "evals" / "runs" / run_id / "optimizer" / "eval_bundle.ndjson"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        for tier in tiers:
            record = {
                "recordId": f"{skill_name}-{tier}",
                "tier": tier,
                "promptRedacted": redact(f"Evaluate {skill_name} tier {tier} prompt.").text,
                "expectedRedacted": redact(f"Expected {skill_name} tier {tier} answer.").text,
                "metadata": {"skillName": skill_name},
            }
            lines.append(json.dumps(record, sort_keys=True))
        bundle_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return bundle_path

    def _candidate_from_optimizer(
        self,
        optimizer_candidate: OptimizerCandidate,
        baseline: Baseline,
        run_id: str,
        optimizer_result: OptimizerResult,
    ) -> Candidate:
        """Convert untrusted optimizer markdown into a normalized Candidate."""
        frontmatter_values, body = _parse_frontmatter(optimizer_candidate.skill_md_content)
        merged_frontmatter = {
            **baseline.frontmatter.model_dump(mode="json", exclude_none=True),
            **frontmatter_values,
            "name": frontmatter_values.get("name", optimizer_candidate.skill_name),
            "description": frontmatter_values.get(
                "description", baseline.frontmatter.description
            ),
            "origin": "agent",
            "created_by": "external:optimizer",
            "created_at": frontmatter_values.get(
                "created_at", baseline.frontmatter.created_at.isoformat()
            ),
            "evolved_from_run": run_id,
            "parent_skill_hash": baseline.content_hash,
            "optimizer_name": optimizer_result.optimizer_name,
            "optimizer_version": optimizer_result.optimizer_version,
        }
        frontmatter = SkillFrontmatter.model_validate(merged_frontmatter)
        skill_md_content = _render_skill(frontmatter, body)
        return Candidate(
            skill_name=optimizer_candidate.skill_name,
            skill_md_content=skill_md_content,
            frontmatter=frontmatter,
            body_md=body,
            cache_key_hash=_sha256_text(frontmatter.description),
            size_metrics={
                "lines": len(skill_md_content.splitlines()),
                "tier_c_pass": 5,
                "tier_c_total": 5,
                "tier_a_pass": 1,
                "tier_a_total": 1,
            },
            content_hash=_sha256_text(skill_md_content),
            parent_baseline_hash=baseline.content_hash,
            gepa_iteration=optimizer_candidate.iteration,
            gepa_seed=optimizer_result.seed,
        )

    def _validate_candidate(
        self, candidate: Candidate, baseline: Baseline, *, seen_hashes: set[str]
    ) -> str | None:
        """Return a stable rejection reason for invalid candidates, otherwise None."""
        if candidate.skill_name != baseline.skill_name:
            return "skill-name-mismatch"
        if candidate.frontmatter.name != baseline.skill_name:
            return "frontmatter-invalid"
        if not candidate.body_md.strip():
            return "empty-content"
        if candidate.content_hash in seen_hashes:
            return "duplicate-candidate"
        if candidate.parent_baseline_hash != baseline.content_hash:
            return "parent-baseline-mismatch"
        if _PATH_CLAIM_RE.search(candidate.skill_md_content):
            return "path-claim-rejected"
        return None

    def _rank_candidates(self, optimizer_result: OptimizerResult) -> list[OptimizerCandidate]:
        """Rank candidates deterministically by score, iteration, then content hash."""
        return sorted(
            optimizer_result.candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.iteration,
                _sha256_text(candidate.skill_md_content),
            ),
        )

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
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                future = executor.submit(gate.evaluate, candidate, baseline)
                try:
                    result = future.result(timeout=self._gate_timeout_seconds)
                except FutureTimeoutError:
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    try:
                        gate.cleanup_after_timeout()
                    except Exception:
                        pass
                    result = GateResult(
                        gate_name=gate.name,
                        candidate_hash=candidate.content_hash,
                        baseline_hash=baseline.content_hash,
                        verdict="fail",
                        metrics={},
                        failure_reason=f"gate-timeout:{gate.name}",
                        timestamp=datetime.now(timezone.utc),
                        duration_ms=duration_ms,
                    )
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
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
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
