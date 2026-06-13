"""Curator report formatting."""

from __future__ import annotations

import json

from nanobot.curator.models import ApplyStatus, CuratorReport, ProposalReason, ReportMode


def format_text_report(report: CuratorReport, *, forced_until: str | None = None) -> str:
    """Return a stable human-readable text representation of a CuratorReport."""
    lines: list[str] = []
    if report.mode == ReportMode.FORCED_DRY_RUN:
        until = forced_until or "unknown"
        lines.append(f"Apply refused: curator is in forced dry-run window until {until}.")
        header_mode = "dry-run"
    elif report.mode == ReportMode.APPLY:
        header_mode = "apply"
    else:
        header_mode = "dry-run"
    lines.extend(
        [
            f"Curator report ({header_mode})",
            f"Skills scanned: {report.skills_scanned}",
            f"Protected: {report.protected}",
            f"Proposals: {len(report.proposals)}",
        ]
    )
    if report.proposals:
        lines.append("")
    for proposal in report.proposals:
        lines.extend(
            [
                f"- {proposal.action.value} {proposal.name}",
                f"  origin: {proposal.origin}",
                f"  confidence: {proposal.confidence.value}",
            ]
        )
        for reason in proposal.reasons:
            lines.append(f"  reason: {_format_reason(reason)}")
        lines.append(f"  apply: {_format_apply(proposal.apply_status)}")
    if report.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in report.warnings:
            lines.append(f"- {warning.code}: {warning.message}")
    return "\n".join(lines)


def format_json_report(report: CuratorReport) -> str:
    """Return a pretty-printed JSON representation of a CuratorReport with a trailing newline."""
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"


def _format_reason(reason: ProposalReason) -> str:
    if not reason.params:
        return reason.code
    params = " ".join(f"{key}={value}" for key, value in reason.params.items())
    return f"{reason.code} {params}"


def _format_apply(status: ApplyStatus) -> str:
    if status == ApplyStatus.ELIGIBLE:
        return "eligible with /curator --apply"
    return status.value
