"""OfflineHarness skeleton — spec §3.2 / §3.7 / §6.0 / §6.4.2 / §6.5.

This is the M4 offline-evolution skeleton: data models for Skill content,
Candidate / Baseline, the per-run manifest, and the harness that walks the
ordered ``GATES`` registry with short-circuit semantics. Later milestones
will layer judges, GEPA selection, and PR application on top.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib.metadata
import json
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import ValidationError

from nanobot.evolve.deploy import assemble_pr_body
from nanobot.evolve.exceptions import ConfigError
from nanobot.evolve.gates import GATES, Gate, GateResult
from nanobot.evolve.gates.semantic_fidelity import SemanticFidelityGate
from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool
from nanobot.evolve.optimizer.adapter import OptimizerAdapter
from nanobot.evolve.optimizer.schemas import OptimizerCandidate, OptimizerInput, OptimizerResult
from nanobot.evolve.privacy.redact import redact
from nanobot.evolve.report import render_run_report
from nanobot.evolve.schemas import (
    Baseline,
    Candidate,
    DiffStats,
    JudgeRunSummary,
    JudgeSummary,
    ReviewReadiness,
    RunManifest,
    SkillContent,
    SkillFrontmatter,
    ToolContractSnapshot,
    ToolMetadataCandidate,
    ToolMetadataValidationResult,
    ValidationFailure,
    dump_manifest,
    load_manifest,
)
from nanobot.evolve.tool_metadata import (
    build_tool_metadata_judge_record,
    capture_loaded_tool_contract_snapshot,
    render_tool_metadata_review,
    validate_tool_metadata_candidate,
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
_SAFE_REASON_MAX_CHARS = 300
_PR_BODY_FORBIDDEN_REASON_CHARS = frozenset(
    {"\n", "\r", "\u2028", "\u2029", "\u0085", "\x00"}
)
_REVIEW_ARTIFACT_PATHS: dict[str, str] = {
    "manifest": "manifest.json",
    "report": "report.md",
    "diff": "diff.patch",
    "pr_body": "pr_body.md",
    "optimizer_input": "optimizer/optimizer_input.json",
    "optimizer_output": "optimizer/optimizer_output.json",
}
_TOOL_METADATA_ARTIFACT_PATHS: dict[str, str] = {
    "tool_contract_snapshot": "tool_contract_snapshot.json",
    "tool_metadata_candidates": "tool_metadata_candidates.jsonl",
    "tool_metadata_review": "tool_metadata_review.md",
}
_TOOL_METADATA_JUDGE_EVIDENCE_PATH = "tool_metadata_judge_evidence.jsonl"


def _review_artifact_plan() -> dict[str, str]:
    return dict(_REVIEW_ARTIFACT_PATHS)


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


def _normalize_lf(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _count_eval_bundle_records(bundle_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw in bundle_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        tier = str(row["tier"])
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _diff_stats_from_patch(patch: str) -> DiffStats:
    files_changed = 0
    insertions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return DiffStats(files_changed=files_changed, insertions=insertions, deletions=deletions)


def _judge_summary_from_gate_results(gate_results: list[GateResult]) -> JudgeRunSummary | None:
    semantic_results = [r for r in gate_results if r.gate_name == "4-semantic-fidelity"]
    if not semantic_results:
        return None
    aggregates = sorted(float(r.metrics.get("semantic_aggregate", 0.0)) for r in semantic_results)
    min_axis = min(
        min(
            float(r.metrics.get("semantic_process", 0.0)),
            float(r.metrics.get("semantic_output", 0.0)),
            float(r.metrics.get("semantic_token", 0.0)),
        )
        for r in semantic_results
    )
    modes = {(r.evidence or {}).get("judge_mode", "local_fallback") for r in semantic_results}
    mode = modes.pop() if len(modes) == 1 else "mixed"
    calibrated = any((r.evidence or {}).get("calibrated") == "true" for r in semantic_results)
    mid = len(aggregates) // 2
    median = (
        aggregates[mid]
        if len(aggregates) % 2 == 1
        else (aggregates[mid - 1] + aggregates[mid]) / 2.0
    )
    return JudgeRunSummary(
        judge_mode=mode,  # type: ignore[arg-type]
        calibrated=calibrated,
        provider_identity=None,
        evidence_count=len(semantic_results),
        median_aggregate=median,
        min_axis_score=min_axis,
        disagreement_max=None,
    )


def _safe_single_line_reason(text: str, *, max_chars: int = _SAFE_REASON_MAX_CHARS) -> str:
    """Return a redacted, bounded one-line reason safe for markdown fields."""
    redacted = redact(text).text
    sanitized = "".join(
        " "
        if ch in _PR_BODY_FORBIDDEN_REASON_CHARS or ord(ch) < 0x20 or ord(ch) == 0x7F
        else ch
        for ch in redacted
    )
    sanitized = re.sub(r"\s+", " ", sanitized).replace("```", "'''").strip()
    if len(sanitized) <= max_chars:
        return sanitized
    return sanitized[: max_chars - 1].rstrip() + "…"


def _validation_failure_reason(exc: ValidationError) -> str:
    return _safe_single_line_reason(f"frontmatter-invalid: {exc}")


def _tool_metadata_artifact_plan() -> dict[str, str]:
    return dict(_TOOL_METADATA_ARTIFACT_PATHS)


def _metadata_rejection_reason(result: ToolMetadataValidationResult) -> str:
    reason_code = result.reason_code or "tool-metadata-rejected"
    reason = result.reason or reason_code
    return _safe_single_line_reason(reason)


def _tool_metadata_candidate_hash(candidate: ToolMetadataCandidate) -> str:
    """Return validation-failure hash in the tool metadata namespace."""
    return f"tool-metadata:{candidate.baseline_schema_hash}"


def _review_validation_results(
    results: list[ToolMetadataValidationResult],
) -> list[ToolMetadataValidationResult]:
    """Return validation results with review-friendly rejection reasons."""
    return [
        result.model_copy(
            update={
                "reason": _safe_single_line_reason(
                    f"{result.reason_code}: {result.reason}"
                    if result.verdict == "reject" and result.reason_code and result.reason
                    else result.reason or "<none>"
                )
            }
        )
        for result in results
    ]


def _redacted_tool_metadata_candidate(candidate: ToolMetadataCandidate) -> ToolMetadataCandidate:
    """Return a metadata candidate safe for shareable JSON artifacts."""
    return ToolMetadataCandidate.model_validate_json(
        redact(candidate.model_dump_json(by_alias=True)).text
    )


def _redacted_tool_contract_snapshot(snapshot: ToolContractSnapshot) -> ToolContractSnapshot:
    """Return a tool contract snapshot safe for shareable JSON artifacts."""
    return ToolContractSnapshot.model_validate_json(
        redact(snapshot.model_dump_json(by_alias=True)).text
    )


def _matching_tool_snapshot(
    candidate: ToolMetadataCandidate,
    snapshot: list[ToolContractSnapshot],
) -> ToolContractSnapshot | None:
    """Return the baseline snapshot matching a metadata candidate contract."""
    return next(
        (
            item
            for item in snapshot
            if item.tool_name == candidate.tool_name
            and item.schema_hash == candidate.baseline_schema_hash
        ),
        None,
    )


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

    def _gates_for_run(self, run_dir: Path) -> list[Gate]:
        gates: list[Gate] = []
        for gate in self._gates:
            if isinstance(gate, SemanticFidelityGate):
                gates.append(SemanticFidelityGate(evidence_dir=run_dir))
            else:
                gates.append(gate)
        return gates

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
            repeat = 5 if tier == "C" else 1
            for index in range(1, repeat + 1):
                record = {
                    "recordId": f"{skill_name}-{tier}-{index}",
                    "tier": tier,
                    "promptRedacted": redact(
                        f"Evaluate {skill_name} tier {tier} prompt {index}."
                    ).text,
                    "expectedRedacted": redact(
                        f"Expected {skill_name} tier {tier} answer {index}."
                    ).text,
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
        eval_counts: dict[str, int] | None = None,
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
        eval_counts = eval_counts or {"A": 1, "C": 5}
        tier_c_total = eval_counts.get("C", 0)
        tier_a_total = eval_counts.get("A", 0)
        size_metrics = {
            "lines": len(skill_md_content.splitlines()),
            "tier_c_pass": tier_c_total,
            "tier_c_total": tier_c_total,
            "tier_a_pass": tier_a_total,
            "tier_a_total": tier_a_total,
        }
        return Candidate(
            skill_name=optimizer_candidate.skill_name,
            skill_md_content=skill_md_content,
            frontmatter=frontmatter,
            body_md=body,
            cache_key_hash=_sha256_text(frontmatter.description),
            size_metrics=size_metrics,
            content_hash=_sha256_text(skill_md_content),
            parent_baseline_hash=baseline.content_hash,
            gepa_iteration=optimizer_candidate.iteration,
            gepa_seed=optimizer_result.seed,
            review_readiness=ReviewReadiness(
                artifact_paths=_review_artifact_plan(),
                requires_human_approval=True,
            ),
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

    def _build_diff_patch(self, baseline: Baseline, promoted: Candidate | None) -> str:
        """Return a deterministic unified diff for the promoted candidate."""
        if promoted is None:
            return ""
        skill_path = f"skills/agent/{baseline.skill_name}/SKILL.md"
        diff_lines = difflib.unified_diff(
            _normalize_lf(baseline.skill_md_content).splitlines(),
            _normalize_lf(promoted.skill_md_content).splitlines(),
            fromfile=f"a/{skill_path}",
            tofile=f"b/{skill_path}",
            lineterm="",
        )
        patch = "\n".join(diff_lines)
        return patch + ("\n" if patch else "")

    def _empty_judge_summary(self, record_count: int) -> JudgeSummary:
        """Return a zeroed deterministic judge summary for offline runs."""
        return JudgeSummary(
            record_count=record_count,
            median_aggregate=0.0,
            median_process=0.0,
            median_output=0.0,
            median_token=0.0,
            consensus_split_count=0,
        )

    def _capture_tool_contract_snapshot(self) -> list[ToolContractSnapshot]:
        """Capture tool contracts using the same loader path as runtime startup."""
        return capture_loaded_tool_contract_snapshot(workspace=str(self._workspace))

    def _write_tool_metadata_judge_evidence(
        self,
        run_dir: Path,
        snapshot: list[ToolContractSnapshot],
        candidates: list[ToolMetadataCandidate],
        validation_results: list[ToolMetadataValidationResult],
    ) -> list[ToolMetadataValidationResult]:
        """Write deterministic judge evidence for accepted metadata candidates."""
        evidence_path = run_dir / _TOOL_METADATA_JUDGE_EVIDENCE_PATH
        # One local judge keeps JudgePool's odd-size quorum invariant without tuning.
        judge_pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
        updated_results = list(validation_results)
        lines: list[str] = []
        for index, (candidate, result) in enumerate(zip(candidates, validation_results)):
            if result.verdict != "accept":
                continue
            baseline = _matching_tool_snapshot(candidate, snapshot)
            if baseline is None:
                continue
            evidence = judge_pool.score_with_evidence(
                build_tool_metadata_judge_record(candidate, baseline)
            )
            lines.append(evidence.model_dump_json(by_alias=True))
            updated_results[index] = result.model_copy(
                update={"judge_evidence_path": _TOOL_METADATA_JUDGE_EVIDENCE_PATH}
            )

        if lines:
            evidence_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return updated_results

    def _write_tool_metadata_artifacts(
        self,
        run_dir: Path,
        snapshot: list[ToolContractSnapshot],
        candidates: list[ToolMetadataCandidate],
        validation_results: list[ToolMetadataValidationResult],
    ) -> dict[str, str]:
        """Write metadata artifacts after optional judge evidence has been written."""
        if not snapshot and not candidates:
            return {}

        artifact_paths = _tool_metadata_artifact_plan()
        if (run_dir / _TOOL_METADATA_JUDGE_EVIDENCE_PATH).is_file():
            artifact_paths["tool_metadata_judge_evidence"] = _TOOL_METADATA_JUDGE_EVIDENCE_PATH
        safe_snapshot = [_redacted_tool_contract_snapshot(item) for item in snapshot]
        safe_candidates = [_redacted_tool_metadata_candidate(candidate) for candidate in candidates]
        (run_dir / artifact_paths["tool_contract_snapshot"]).write_text(
            json.dumps(
                [item.model_dump(mode="json", by_alias=True) for item in safe_snapshot],
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (run_dir / artifact_paths["tool_metadata_candidates"]).write_text(
            "".join(
                candidate.model_dump_json(by_alias=True) + "\n"
                for candidate in safe_candidates
            ),
            encoding="utf-8",
        )
        (run_dir / artifact_paths["tool_metadata_review"]).write_text(
            render_tool_metadata_review(
                snapshot, candidates, _review_validation_results(validation_results)
            ),
            encoding="utf-8",
        )
        return artifact_paths

    def _nanobot_version(self) -> str:
        """Return the installed nanobot-ai version, or 0.0.0 in editable test runs."""
        try:
            return importlib.metadata.version("nanobot-ai")
        except importlib.metadata.PackageNotFoundError:
            return "0.0.0"

    def run(
        self,
        *,
        skill_name: str,
        optimizer_command: list[str],
        tiers: list[str],
        max_candidates: int = 8,
        optimizer_timeout_seconds: int = 600,
    ) -> RunManifest:
        """Execute the external optimizer and write deterministic offline artifacts."""
        started_at = datetime.now(timezone.utc)
        run_id = self._generate_run_id(skill_name)
        run_dir = self._workspace / "evals" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        previous_gates = self._gates
        self._gates = self._gates_for_run(run_dir)
        optimizer_dir = run_dir / "optimizer"

        try:
            return self._run(
                skill_name=skill_name,
                optimizer_command=optimizer_command,
                tiers=tiers,
                max_candidates=max_candidates,
                optimizer_timeout_seconds=optimizer_timeout_seconds,
                started_at=started_at,
                run_id=run_id,
                run_dir=run_dir,
                optimizer_dir=optimizer_dir,
            )
        finally:
            self._gates = previous_gates

    def _run(
        self,
        *,
        skill_name: str,
        optimizer_command: list[str],
        tiers: list[str],
        max_candidates: int,
        optimizer_timeout_seconds: int,
        started_at: datetime,
        run_id: str,
        run_dir: Path,
        optimizer_dir: Path,
    ) -> RunManifest:
        baseline = self._load_baseline_skill(skill_name)
        tool_contract_snapshot = self._capture_tool_contract_snapshot()
        eval_bundle = self._load_eval_records(skill_name, tiers, run_id)
        record_count_per_tier = _count_eval_bundle_records(eval_bundle)
        optimizer_input = OptimizerInput(
            run_id=run_id,
            skill_name=skill_name,
            baseline_hash=baseline.content_hash,
            baseline_skill_md_redacted=redact(baseline.skill_md_content).text,
            eval_records_path=str(eval_bundle),
            output_dir=str(optimizer_dir),
            max_candidates=max_candidates,
            timeout_seconds=optimizer_timeout_seconds,
            seed=123456789,
            tool_contract_snapshot=tool_contract_snapshot,
        )

        subprocess_start = time.perf_counter()
        optimizer_result = OptimizerAdapter(optimizer_command=optimizer_command).run(
            optimizer_input
        )
        subprocess_runtime_ms = int((time.perf_counter() - subprocess_start) * 1000)

        validation_failures: list[ValidationFailure] = []
        valid_candidates: list[Candidate] = []
        seen_hashes: set[str] = set()
        tool_metadata_validation_results: list[ToolMetadataValidationResult] = []
        for index, metadata_candidate in enumerate(optimizer_result.tool_metadata_candidates):
            validation_result = validate_tool_metadata_candidate(
                metadata_candidate, tool_contract_snapshot
            )
            tool_metadata_validation_results.append(validation_result)
            if validation_result.verdict == "reject":
                validation_failures.append(
                    ValidationFailure(
                        candidate_index=index,
                        candidate_hash=_tool_metadata_candidate_hash(metadata_candidate),
                        reason_code=validation_result.reason_code or "tool-metadata-rejected",
                        reason=_metadata_rejection_reason(validation_result),
                    )
                )

        tool_metadata_validation_results = self._write_tool_metadata_judge_evidence(
            run_dir,
            tool_contract_snapshot,
            optimizer_result.tool_metadata_candidates,
            tool_metadata_validation_results,
        )

        if not (optimizer_result.error and optimizer_result.error.code == "no_improvement"):
            for index, optimizer_candidate in enumerate(
                self._rank_candidates(optimizer_result)[:max_candidates]
            ):
                try:
                    candidate = self._candidate_from_optimizer(
                        optimizer_candidate,
                        baseline,
                        run_id,
                        optimizer_result,
                        record_count_per_tier,
                    )
                except ValidationError as exc:
                    validation_failures.append(
                        ValidationFailure(
                            candidate_index=index,
                            candidate_hash="<invalid>",
                            reason_code="frontmatter-invalid",
                            reason=_validation_failure_reason(exc),
                        )
                    )
                    continue

                reason = self._validate_candidate(candidate, baseline, seen_hashes=seen_hashes)
                if reason is not None:
                    validation_failures.append(
                        ValidationFailure(
                            candidate_index=index,
                            candidate_hash=candidate.content_hash,
                            reason_code=reason,
                            reason=reason,
                        )
                    )
                    continue
                seen_hashes.add(candidate.content_hash)
                valid_candidates.append(candidate)

        gate_traces: dict[str, list[GateResult]] = {}
        promoted: Candidate | None = None
        for candidate in valid_candidates:
            trace = self._run_gates(candidate, baseline)
            gate_traces[candidate.content_hash] = trace
            if all(result.verdict == "pass" for result in trace):
                promoted = candidate
                break

        metadata_rejections_exist = any(
            result.verdict == "reject" for result in tool_metadata_validation_results
        )
        if optimizer_result.error and optimizer_result.error.code == "no_improvement":
            if metadata_rejections_exist and not valid_candidates:
                final_status = "rejected_by_validation"
            else:
                final_status = "no_improvement"
        elif not valid_candidates and validation_failures:
            final_status = "rejected_by_validation"
        else:
            final_status = self._compute_final_status(
                promoted, valid_candidates, baseline, gate_traces=gate_traces
            )

        candidates_dir = run_dir / "candidates"
        for candidate in valid_candidates:
            candidates_dir.mkdir(parents=True, exist_ok=True)
            (candidates_dir / f"{candidate.content_hash}.SKILL.md").write_text(
                candidate.skill_md_content, encoding="utf-8"
            )

        tool_metadata_artifact_paths = self._write_tool_metadata_artifacts(
            run_dir,
            tool_contract_snapshot,
            optimizer_result.tool_metadata_candidates,
            tool_metadata_validation_results,
        )
        artifact_paths = {
            **_review_artifact_plan(),
            "eval_bundle": "optimizer/eval_bundle.ndjson",
            "optimizer_stderr": "optimizer/stderr.txt",
            "optimizer_stdout": "optimizer/stdout.txt",
            **tool_metadata_artifact_paths,
        }
        gate_verdicts = [
            result
            for candidate in valid_candidates
            for result in gate_traces.get(candidate.content_hash, [])
        ]
        diff_patch = self._build_diff_patch(baseline, promoted)
        diff_stats = _diff_stats_from_patch(diff_patch)
        judge_run_summary = _judge_summary_from_gate_results(gate_verdicts)
        judge_evidence_paths = (
            {"semantic_fidelity": "judge_evidence.jsonl"}
            if (run_dir / "judge_evidence.jsonl").is_file()
            else {}
        )
        finished_at = datetime.now(timezone.utc)
        manifest = RunManifest(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            nanobot_version=self._nanobot_version(),
            evolve_extra_version={"optimizer": optimizer_result.optimizer_name},
            skill_name=skill_name,
            baseline_hash=baseline.content_hash,
            candidate_hashes=[candidate.content_hash for candidate in valid_candidates],
            promoted_candidate_hash=promoted.content_hash if promoted is not None else None,
            gate_verdicts=gate_verdicts,
            judge_summary=self._empty_judge_summary(sum(record_count_per_tier.values())),
            final_status=final_status,
            tiers_used=tiers,  # type: ignore[arg-type]
            record_count_per_tier=record_count_per_tier,
            judge_pool_health={},
            optimizer_name=optimizer_result.optimizer_name,
            optimizer_version=optimizer_result.optimizer_version,
            optimizer_seed=optimizer_result.seed,
            validation_failures=validation_failures,
            subprocess_runtime_ms=subprocess_runtime_ms,
            artifact_paths=artifact_paths,
            diff_stats=diff_stats,
            requires_human_approval=promoted is not None,
            judge_run_summary=judge_run_summary,
            judge_evidence_paths=judge_evidence_paths,
            tool_metadata_artifact_paths=tool_metadata_artifact_paths,
        )

        (run_dir / "diff.patch").write_text(diff_patch, encoding="utf-8")
        (run_dir / "pr_body.md").write_text(
            assemble_pr_body(manifest, gate_verdicts), encoding="utf-8"
        )
        (run_dir / "report.md").write_text(
            render_run_report(manifest, gate_traces, optimizer_result, validation_failures),
            encoding="utf-8",
        )
        dump_manifest(run_dir / "manifest.json", manifest)
        return manifest

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
                    reason = _safe_single_line_reason(
                        f"gate-internal-error: {type(exc).__name__}: {exc}", max_chars=240
                    )
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
            if result.failure_reason is not None:
                result = result.model_copy(
                    update={"failure_reason": _safe_single_line_reason(result.failure_reason)}
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
