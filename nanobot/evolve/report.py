from __future__ import annotations

from nanobot.evolve.gates import GateResult
from nanobot.evolve.optimizer.schemas import OptimizerResult
from nanobot.evolve.privacy.redact import redact
from nanobot.evolve.schemas import RunManifest, ValidationFailure

_MAX_SAFE_TEXT_CHARS = 300


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
        "## Validation failures",
    ]
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
