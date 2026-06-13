import pytest
from pydantic import ValidationError

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


def test_reason_has_closed_code_and_params() -> None:
    reason = ProposalReason(code="zero_uses_after_views", params={"views": 30, "uses": 0})

    assert reason.code == "zero_uses_after_views"
    assert reason.params == {"views": 30, "uses": 0}


def test_reason_rejects_freeform_snippet_fields() -> None:
    with pytest_raises_validation_error():
        ProposalReason(
            code="zero_uses_after_views",
            params={"views": 30},
            body_excerpt="secret text",
        )


def test_report_model_uses_spec_enum_values() -> None:
    proposal = CuratorProposal(
        name="old-debug-helper",
        origin="agent",
        action=CuratorAction.DELETE_CANDIDATE,
        confidence=Confidence.HIGH,
        reasons=[ProposalReason(code="zero_uses_after_views", params={"views": 30})],
        protected=False,
        apply_status=ApplyStatus.ELIGIBLE,
    )
    report = CuratorReport(
        mode=ReportMode.DRY_RUN,
        skills_scanned=1,
        protected=0,
        proposals=[proposal],
        warnings=[CuratorWarning(code="sample_warning", message="safe summary")],
    )

    assert report.model_dump(mode="json") == {
        "mode": "dry_run",
        "skills_scanned": 1,
        "protected": 0,
        "proposals": [
            {
                "name": "old-debug-helper",
                "origin": "agent",
                "action": "delete_candidate",
                "confidence": "high",
                "reasons": [
                    {"code": "zero_uses_after_views", "params": {"views": 30}}
                ],
                "protected": False,
                "apply_status": "eligible",
                "aux_verdict": None,
            }
        ],
        "warnings": [{"code": "sample_warning", "message": "safe summary"}],
    }


def pytest_raises_validation_error():
    return pytest.raises(ValidationError)
