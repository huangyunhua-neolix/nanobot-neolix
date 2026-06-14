import json

from nanobot.curator.models import (
    ApplyStatus,
    Confidence,
    CuratorAction,
    CuratorProposal,
    CuratorReport,
    CuratorWarning,
    ProposalReason,
    ReportMode,
)
from nanobot.curator.report import format_json_report, format_text_report


def _report(mode: ReportMode = ReportMode.DRY_RUN) -> CuratorReport:
    return CuratorReport(
        mode=mode,
        skills_scanned=12,
        protected=4,
        proposals=[
            CuratorProposal(
                name="old-debug-helper",
                origin="agent",
                action=CuratorAction.DELETE_CANDIDATE,
                confidence=Confidence.HIGH,
                reasons=[
                    ProposalReason(code="zero_uses_after_views", params={"views": 30, "uses": 0}),
                    ProposalReason(code="stale_since_last_use", params={"days": 45}),
                ],
                protected=False,
                apply_status=ApplyStatus.ELIGIBLE,
            )
        ],
        warnings=[CuratorWarning(code="aux_skipped", message="auxiliary model not configured")],
    )


def test_text_report_is_stable_and_template_based() -> None:
    text = format_text_report(_report())

    assert text == "\n".join(
        [
            "Curator report (dry-run)",
            "Skills scanned: 12",
            "Protected: 4",
            "Proposals: 1",
            "",
            "- delete_candidate old-debug-helper",
            "  origin: agent",
            "  confidence: high",
            "  reason: zero_uses_after_views views=30 uses=0",
            "  reason: stale_since_last_use days=45",
            "  apply: eligible with /curator --apply",
            "",
            "Warnings:",
            "- aux_skipped: auxiliary model not configured",
        ]
    )


def test_apply_mode_header() -> None:
    text = format_text_report(_report(ReportMode.APPLY))

    assert text.startswith("Curator report (apply)")


def test_clean_scan_no_trailing_blank_line_and_no_warnings_section() -> None:
    report = CuratorReport(
        mode=ReportMode.DRY_RUN,
        skills_scanned=0,
        protected=0,
        proposals=[],
        warnings=[],
    )
    text = format_text_report(report)

    assert text == "\n".join(
        [
            "Curator report (dry-run)",
            "Skills scanned: 0",
            "Protected: 0",
            "Proposals: 0",
        ]
    )


def test_forced_dry_run_report_includes_refusal() -> None:
    text = format_text_report(
        _report(ReportMode.FORCED_DRY_RUN),
        forced_until="2026-06-20T00:00:00Z",
    )

    assert text == "\n".join(
        [
            "Apply refused: curator is in forced dry-run window until 2026-06-20T00:00:00Z.",
            "Curator report (dry-run)",
            "Skills scanned: 12",
            "Protected: 4",
            "Proposals: 1",
            "",
            "- delete_candidate old-debug-helper",
            "  origin: agent",
            "  confidence: high",
            "  reason: zero_uses_after_views views=30 uses=0",
            "  reason: stale_since_last_use days=45",
            "  apply: eligible with /curator --apply",
            "",
            "Warnings:",
            "- aux_skipped: auxiliary model not configured",
        ]
    )


def test_json_report_is_pretty_and_deterministic() -> None:
    text = format_json_report(_report())
    data = json.loads(text)

    assert data["mode"] == "dry_run"
    assert data["proposals"][0]["apply_status"] == "eligible"
    assert data["proposals"][0]["name"] == "old-debug-helper"
    assert text.endswith("\n")
