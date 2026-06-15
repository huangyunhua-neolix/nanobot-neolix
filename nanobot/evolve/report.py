from __future__ import annotations

from nanobot.evolve.gates import GateResult
from nanobot.evolve.optimizer.schemas import OptimizerResult
from nanobot.evolve.privacy.redact import redact
from nanobot.evolve.schemas import RunManifest, ValidationFailure

_MAX_SAFE_TEXT_CHARS = 300
_TOOL_METADATA_ARTIFACT_LABELS = (
    ("Snapshot", "tool_contract_snapshot"),
    ("Candidates", "tool_metadata_candidates"),
    ("Review", "tool_metadata_review"),
    ("Judge evidence", "tool_metadata_judge_evidence"),
)
_PROMPT_TEMPLATE_ARTIFACT_LABELS = (
    ("Snapshot", "prompt_template_snapshot"),
    ("Candidates", "prompt_template_candidates"),
    ("Review", "prompt_template_review"),
    ("Judge evidence", "prompt_template_judge_evidence"),
)


def _redact_and_bound(text: str, max_chars: int = _MAX_SAFE_TEXT_CHARS) -> str:
    redacted = redact(text).text
    if len(redacted) <= max_chars:
        return redacted
    return redacted[: max_chars - 3] + "..."


def render_run_report(
    manifest: RunManifest,
    gate_results_by_candidate: dict[str, list[GateResult]],
    optimizer_result: OptimizerResult,
    validation_failures: list[ValidationFailure],
) -> str:
    lines: list[str] = [
        "## Summary",
        f"Run: `{manifest.run_id}`",
        f"Skill: `{manifest.skill_name}`",
        f"Status: `{manifest.final_status}`",
        f"Baseline: `{manifest.baseline_hash[:8]}`",
        f"Promoted candidate: `{manifest.promoted_candidate_hash or '<none>'}`",
        "",
        "## Optimizer",
        f"Name: `{optimizer_result.optimizer_name}`",
        f"Version: `{optimizer_result.optimizer_version or '<none>'}`",
        f"Seed: `{optimizer_result.seed if optimizer_result.seed is not None else '<none>'}`",
        "",
        "## Review state",
        f"Human approval required: `{str(manifest.requires_human_approval).lower()}`",
    ]
    if manifest.tool_metadata_artifact_paths:
        lines.extend(
            [
                "",
                "## Tool metadata review",
                (
                    "No runtime tool source changed; artifacts require human "
                    "review before any application."
                ),
            ]
        )
        for label, key in _TOOL_METADATA_ARTIFACT_LABELS:
            path = manifest.tool_metadata_artifact_paths.get(key, "<none>")
            lines.append(f"{label}: `{_redact_and_bound(path)}`")
    if manifest.prompt_template_artifact_paths:
        lines.extend(
            [
                "",
                "## Prompt template review",
                (
                    "No bundled skill source changed; prompt/template candidates "
                    "require human review before any application."
                ),
                "Cache-sensitive frontmatter was not modified by accepted candidates.",
            ]
        )
        for label, key in _PROMPT_TEMPLATE_ARTIFACT_LABELS:
            path = manifest.prompt_template_artifact_paths.get(key, "<none>")
            lines.append(f"{label}: `{_redact_and_bound(path)}`")
    if manifest.judge_run_summary is not None:
        summary = manifest.judge_run_summary
        evidence_path = manifest.judge_evidence_paths.get("semantic_fidelity", "<none>")
        disagreement = (
            summary.disagreement_max
            if summary.disagreement_max is not None
            else "<none>"
        )
        lines.extend(
            [
                "",
                "## Semantic judge",
                f"Mode: `{summary.judge_mode}`",
                f"Calibrated: `{str(summary.calibrated).lower()}`",
                f"Evidence count: `{summary.evidence_count}`",
                f"Median aggregate: `{summary.median_aggregate:.6g}`",
                f"Minimum axis score: `{summary.min_axis_score:.6g}`",
                f"Disagreement max: `{disagreement}`",
                f"Evidence: `{_redact_and_bound(evidence_path)}`",
                "Judge metrics were not returned to the optimizer and were not used as optimizer fitness.",
            ]
        )
    if manifest.diff_stats is not None:
        lines.extend(
            [
                "",
                "## Diff stats",
                f"Files changed: `{manifest.diff_stats.files_changed}`",
                f"Insertions: `{manifest.diff_stats.insertions}`",
                f"Deletions: `{manifest.diff_stats.deletions}`",
            ]
        )
    lines.extend([
        "",
        "## Validation failures",
    ])
    if not validation_failures:
        lines.append("None")
    else:
        for failure in validation_failures:
            reason = _redact_and_bound(failure.reason)
            lines.append(
                f"- candidate #{failure.candidate_index} `{failure.candidate_hash[:8]}` "
                f"{failure.reason_code}: {reason}"
            )
    lines.extend(["", "## Gates"])
    if not gate_results_by_candidate:
        lines.append("None")
    else:
        for candidate_hash in sorted(gate_results_by_candidate):
            lines.append(f"Candidate `{candidate_hash[:8]}`:")
            for result in gate_results_by_candidate[candidate_hash]:
                suffix = f" ({_redact_and_bound(result.failure_reason)})" if result.failure_reason else ""
                lines.append(f"- {result.gate_name}: {result.verdict}{suffix}")
    lines.extend(["", "## Artifacts"])
    if not manifest.artifact_paths:
        lines.append("None")
    else:
        for key in sorted(manifest.artifact_paths):
            path = _redact_and_bound(manifest.artifact_paths[key])
            lines.append(f"- {key}: `{path}`")
    return "\n".join(lines) + "\n"
