"""Tests for CuratorService dry-run and forced dry-run orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nanobot.agent.skills_telemetry import SCHEMA_VERSION, TelemetrySnapshot
from nanobot.config.schema import CuratorConfig
from nanobot.curator.models import (
    ApplyStatus,
    Confidence,
    CuratorAction,
    CuratorProposal,
    ReportMode,
)
from nanobot.curator.service import CuratorService

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 6, 13, 0, 0, 0, tzinfo=timezone.utc)
_STALE_CREATED = "2026-04-01T00:00:00Z"  # 73 days before _NOW — clearly stale


def _now_fn() -> datetime:
    return _NOW


def _stale_agent_telemetry_entry() -> dict:
    """Telemetry for a high-confidence delete candidate."""
    return {
        "origin": "agent",
        "shadowed": [],
        "views": 30,
        "uses": 0,
        "patches": 0,
        "entry_created_at": _STALE_CREATED,
        "last_view": "2026-04-10T00:00:00Z",
        "last_use": None,
    }


class _FakeSkills:
    """Minimal SkillsProvider stub returning a single stale agent skill."""

    def __init__(self, skill_name: str = "old-debug-helper") -> None:
        self._name = skill_name

    def list_skills_with_shadows(self) -> list[dict]:
        return [
            {
                "name": self._name,
                "effective_origin": "agent",
                "shadowed_origins": [],
                "path": f"/workspace/skills/agent/{self._name}/SKILL.md",
            }
        ]

    def get_skill_metadata(self, name: str) -> dict | None:
        return {}


class _FakeTelemetry:
    """Minimal SnapshotProvider stub returning a fixed TelemetrySnapshot."""

    def __init__(self, entries: dict | None = None) -> None:
        self._entries = entries or {}

    def snapshot(self) -> TelemetrySnapshot:
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": "2026-06-13T00:00:00Z",
            "entries": self._entries,
        }


def _make_service(
    *,
    forced_dry_run_until: str = "",
    now_fn=_now_fn,
    skill_name: str = "old-debug-helper",
) -> CuratorService:
    # Disable forced dry-run by default (empty string) via a past timestamp.
    if forced_dry_run_until == "":
        config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    else:
        config = CuratorConfig(forced_dry_run_until=forced_dry_run_until)

    telemetry_entries = {skill_name: _stale_agent_telemetry_entry()}
    return CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(skill_name),
        telemetry=_FakeTelemetry(telemetry_entries),
        config=config,
        now_fn=now_fn,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dry_run_does_not_delete_and_mode_is_dry_run() -> None:
    """Dry-run: report mode is DRY_RUN, ELIGIBLE proposal is preserved unchanged."""
    service = _make_service(forced_dry_run_until="2000-01-01T00:00:00Z")  # past → not active
    report = service.run(apply=False, include_protected=False)

    assert report.mode == ReportMode.DRY_RUN
    assert len(report.proposals) == 1
    proposal = report.proposals[0]
    # Proposal is ELIGIBLE but no file is touched in dry-run
    assert proposal.apply_status == ApplyStatus.ELIGIBLE
    # No warnings from healthy telemetry
    assert report.warnings == []
    assert report.skills_scanned == 1


def test_forced_dry_run_refuses_apply_and_sets_refused_status() -> None:
    """Forced dry-run: apply=True returns FORCED_DRY_RUN mode; proposal status is REFUSED."""
    future_until = "2099-12-31T23:59:59Z"
    service = _make_service(forced_dry_run_until=future_until)
    assert service.forced_dry_run_active() is True

    report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.FORCED_DRY_RUN
    assert len(report.proposals) == 1
    proposal = report.proposals[0]
    assert proposal.apply_status == ApplyStatus.REFUSED_FORCED_DRY_RUN
    assert report.skills_scanned == 1


def test_forced_dry_run_file_and_tombstone_not_touched(tmp_path: Path) -> None:
    """Forced dry-run must not call any delete_operation (file unchanged)."""
    calls: list[str] = []

    def _spy_delete(name: str) -> None:
        calls.append(name)

    future_until = "2099-12-31T23:59:59Z"
    config = CuratorConfig(forced_dry_run_until=future_until)
    telemetry_entries = {"old-debug-helper": _stale_agent_telemetry_entry()}
    service = CuratorService(
        workspace=str(tmp_path),
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry(telemetry_entries),
        config=config,
        now_fn=_now_fn,
        delete_operation=_spy_delete,
    )
    service.run(apply=True, include_protected=False)

    # delete_operation must NEVER be invoked during a forced dry-run
    assert calls == [], f"Unexpected delete calls: {calls}"


def test_forced_dry_run_until_auto_resolves_to_now_plus_7_days() -> None:
    """'auto' resolves to now + 7 days using the injected now_fn."""
    config = CuratorConfig(forced_dry_run_until="auto")
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry({"old-debug-helper": _stale_agent_telemetry_entry()}),
        config=config,
        now_fn=_now_fn,
    )
    resolved = service.resolve_forced_dry_run_until()
    assert resolved is not None

    expected_dt = datetime(2026, 6, 20, 0, 0, 0, tzinfo=timezone.utc)  # _NOW + 7 days
    parsed = datetime.strptime(resolved, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert parsed == expected_dt


def test_forced_dry_run_auto_is_always_active() -> None:
    """'auto' forced_dry_run_until is always considered active."""
    config = CuratorConfig(forced_dry_run_until="auto")
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry(),
        config=config,
        now_fn=_now_fn,
    )
    assert service.forced_dry_run_active() is True


def test_past_forced_dry_run_until_is_not_active() -> None:
    """A forced_dry_run_until in the past means the window is over."""
    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry(),
        config=config,
        now_fn=_now_fn,
    )
    assert service.forced_dry_run_active() is False


def test_apply_with_inactive_forced_dry_run_returns_apply_mode() -> None:
    """When forced dry-run is inactive, apply=True yields APPLY mode and calls delete."""
    calls: list[tuple[str, str]] = []

    def _spy_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        calls.append((name, provenance_tag))
        return {"ok": True, "verb": "delete", "name": name}

    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    telemetry_entries = {"old-debug-helper": _stale_agent_telemetry_entry()}
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry(telemetry_entries),
        config=config,
        now_fn=_now_fn,
        delete_operation=_spy_delete,
    )
    assert service.forced_dry_run_active() is False

    report = service.run(apply=True, include_protected=False)
    assert report.mode == ReportMode.APPLY
    # HIGH-confidence ELIGIBLE delete candidate is called and maps to DELETED
    assert len(calls) == 1
    skill_name, prov_tag = calls[0]
    assert skill_name == "old-debug-helper"
    assert prov_tag == "curator", f"Expected provenance_tag='curator', got {prov_tag!r}"
    assert report.proposals[0].apply_status == ApplyStatus.DELETED


def test_forced_dry_run_only_mutates_eligible_proposals() -> None:
    """Forced dry-run must flip ELIGIBLE → REFUSED_FORCED_DRY_RUN and leave all other statuses unchanged."""
    future_until = "2099-12-31T23:59:59Z"

    # Build a synthetic mixed-status proposal list with two ELIGIBLE proposals
    # and one proposal for each representative non-ELIGIBLE status.
    _mixed_proposals = [
        CuratorProposal(
            name="stale-alpha",
            origin="agent",
            action=CuratorAction.DELETE_CANDIDATE,
            confidence=Confidence.HIGH,
            apply_status=ApplyStatus.ELIGIBLE,
        ),
        CuratorProposal(
            name="stale-beta",
            origin="agent",
            action=CuratorAction.DELETE_CANDIDATE,
            confidence=Confidence.HIGH,
            apply_status=ApplyStatus.ELIGIBLE,
        ),
        CuratorProposal(
            name="medium-confidence",
            origin="agent",
            action=CuratorAction.DELETE_CANDIDATE,
            confidence=Confidence.MEDIUM,
            apply_status=ApplyStatus.NOT_REQUESTED,
        ),
        CuratorProposal(
            name="builtin-skill",
            origin="builtin",
            action=CuratorAction.KEEP,
            confidence=Confidence.LOW,
            apply_status=ApplyStatus.NOT_APPLICABLE,
            protected=True,
        ),
    ]

    config = CuratorConfig(forced_dry_run_until=future_until)
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(),
        telemetry=_FakeTelemetry({}),
        config=config,
        now_fn=_now_fn,
    )

    # Monkeypatch generate_proposals at the service-module level so run() sees
    # our synthetic list without requiring a real policy-matching skill set.
    with patch("nanobot.curator.service.generate_proposals", return_value=list(_mixed_proposals)):
        report = service.run(apply=True, include_protected=True)

    assert report.mode == ReportMode.FORCED_DRY_RUN

    by_name = {p.name: p for p in report.proposals}

    # Both ELIGIBLE proposals must be flipped.
    assert by_name["stale-alpha"].apply_status == ApplyStatus.REFUSED_FORCED_DRY_RUN
    assert by_name["stale-beta"].apply_status == ApplyStatus.REFUSED_FORCED_DRY_RUN

    # Non-ELIGIBLE statuses must be preserved exactly.
    assert by_name["medium-confidence"].apply_status == ApplyStatus.NOT_REQUESTED
    assert by_name["builtin-skill"].apply_status == ApplyStatus.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Task 7: safe delete apply path tests
# ---------------------------------------------------------------------------


def _make_apply_service(
    *,
    delete_operation,
    skill_name: str = "old-debug-helper",
    apply_delete_mode: str = "auto_high",
) -> CuratorService:
    """Build a CuratorService with forced dry-run disabled, wired to a custom delete_operation."""
    config = CuratorConfig(
        forced_dry_run_until="2000-01-01T00:00:00Z",
        apply_delete_mode=apply_delete_mode,  # type: ignore[arg-type]
    )
    telemetry_entries = {skill_name: _stale_agent_telemetry_entry()}
    return CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(skill_name),
        telemetry=_FakeTelemetry(telemetry_entries),
        config=config,
        now_fn=_now_fn,
        delete_operation=delete_operation,
    )


def test_apply_high_confidence_delete_calls_delete_op_and_maps_deleted() -> None:
    """HIGH confidence DELETE_CANDIDATE in apply mode calls injected delete op and maps to DELETED."""
    calls: list[str] = []

    def _spy_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        calls.append(name)
        return {"ok": True, "verb": "delete", "name": name}

    service = _make_apply_service(delete_operation=_spy_delete)
    report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.APPLY
    assert calls == ["old-debug-helper"], f"Expected delete call, got: {calls}"
    assert len(report.proposals) == 1
    assert report.proposals[0].apply_status == ApplyStatus.DELETED
    assert report.warnings == []


def test_apply_medium_confidence_delete_skips_without_calling_delete() -> None:
    """Medium/low confidence DELETE_CANDIDATE does not call delete and maps to SKIPPED_LOW_CONFIDENCE."""
    calls: list[str] = []

    def _spy_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        calls.append(name)
        return {"ok": True, "verb": "delete", "name": name}

    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills("medium-skill"),
        telemetry=_FakeTelemetry({}),
        config=config,
        now_fn=_now_fn,
        delete_operation=_spy_delete,
    )

    # Monkeypatch generate_proposals to yield a MEDIUM confidence proposal directly.
    medium_proposal = CuratorProposal(
        name="medium-skill",
        origin="agent",
        action=CuratorAction.DELETE_CANDIDATE,
        confidence=Confidence.MEDIUM,
        apply_status=ApplyStatus.NOT_REQUESTED,
    )
    with patch("nanobot.curator.service.generate_proposals", return_value=[medium_proposal]):
        report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.APPLY
    assert calls == [], f"delete must NOT be called for medium confidence, got: {calls}"
    assert report.proposals[0].apply_status == ApplyStatus.SKIPPED_LOW_CONFIDENCE


def test_apply_delete_result_not_found_maps_to_skipped_missing() -> None:
    """delete_operation returning not_found maps to SKIPPED_MISSING."""

    def _not_found_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        return {"ok": False, "verb": "delete", "name": name, "error_code": "not_found", "error_message": "gone"}

    service = _make_apply_service(delete_operation=_not_found_delete)
    report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.APPLY
    assert report.proposals[0].apply_status == ApplyStatus.SKIPPED_MISSING
    assert report.warnings == []


def test_apply_delete_result_lock_busy_maps_to_failed_and_appends_warning() -> None:
    """Failed delete (lock_busy) maps to FAILED, appends CuratorWarning, and continues."""
    calls: list[str] = []

    def _lock_busy_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        calls.append(name)
        return {"ok": False, "verb": "delete", "name": name, "error_code": "lock_busy", "error_message": "locked"}

    # Two skills: first fails, second should still be processed (DELETED).
    first_telem = _stale_agent_telemetry_entry()
    second_telem = _stale_agent_telemetry_entry()

    class _TwoSkills:
        def list_skills_with_shadows(self) -> list[dict]:
            return [
                {
                    "name": "skill-a",
                    "effective_origin": "agent",
                    "shadowed_origins": [],
                    "path": "/workspace/skills/agent/skill-a/SKILL.md",
                },
                {
                    "name": "skill-b",
                    "effective_origin": "agent",
                    "shadowed_origins": [],
                    "path": "/workspace/skills/agent/skill-b/SKILL.md",
                },
            ]

        def get_skill_metadata(self, name: str) -> dict | None:
            return {}

    success_calls: list[str] = []

    def _mixed_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        if name == "skill-a":
            return {"ok": False, "verb": "delete", "name": name, "error_code": "lock_busy", "error_message": "locked"}
        success_calls.append(name)
        return {"ok": True, "verb": "delete", "name": name}

    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    service = CuratorService(
        workspace="/workspace",
        skills=_TwoSkills(),
        telemetry=_FakeTelemetry({"skill-a": first_telem, "skill-b": second_telem}),
        config=config,
        now_fn=_now_fn,
        delete_operation=_mixed_delete,
    )
    report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.APPLY
    by_name = {p.name: p for p in report.proposals}
    assert by_name["skill-a"].apply_status == ApplyStatus.FAILED
    assert by_name["skill-b"].apply_status == ApplyStatus.DELETED

    # One warning for skill-a's failure; skill name and error_code in message, no skill body
    assert len(report.warnings) == 1
    w = report.warnings[0]
    assert w.code == "delete_failed"
    assert "skill-a" in w.message
    assert "lock_busy" in w.message
    # Ensure skill description/body is NOT leaked into the warning message
    assert "description" not in w.message.lower()


def test_apply_delete_raises_exception_maps_to_failed_and_continues() -> None:
    """If delete_operation raises, proposal maps to FAILED, warning appended, next proposal processed."""

    class _TwoSkills:
        def list_skills_with_shadows(self) -> list[dict]:
            return [
                {
                    "name": "skill-raises",
                    "effective_origin": "agent",
                    "shadowed_origins": [],
                    "path": "/workspace/skills/agent/skill-raises/SKILL.md",
                },
                {
                    "name": "skill-ok",
                    "effective_origin": "agent",
                    "shadowed_origins": [],
                    "path": "/workspace/skills/agent/skill-ok/SKILL.md",
                },
            ]

        def get_skill_metadata(self, name: str) -> dict | None:
            return {}

    def _raising_delete(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        if name == "skill-raises":
            raise RuntimeError("disk full")
        return {"ok": True, "verb": "delete", "name": name}

    stale = _stale_agent_telemetry_entry()
    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    service = CuratorService(
        workspace="/workspace",
        skills=_TwoSkills(),
        telemetry=_FakeTelemetry({"skill-raises": stale, "skill-ok": stale}),
        config=config,
        now_fn=_now_fn,
        delete_operation=_raising_delete,
    )
    report = service.run(apply=True, include_protected=False)

    assert report.mode == ReportMode.APPLY
    by_name = {p.name: p for p in report.proposals}
    assert by_name["skill-raises"].apply_status == ApplyStatus.FAILED
    assert by_name["skill-ok"].apply_status == ApplyStatus.DELETED

    # Warning for the raised exception includes skill name and exception class, not body
    assert len(report.warnings) == 1
    w = report.warnings[0]
    assert w.code == "delete_failed"
    assert "skill-raises" in w.message
    assert "RuntimeError" in w.message


# ---------------------------------------------------------------------------
# Safety-gate tests: delete must NOT be called for non-delete-candidate proposals
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Task 8: aux deliberation skip behavior
# ---------------------------------------------------------------------------


def test_dry_run_with_aux_deliberation_disabled_produces_no_aux_warnings() -> None:
    """CuratorConfig(aux_deliberation=False) produces a report with no aux-related warnings."""
    config = CuratorConfig(
        forced_dry_run_until="2000-01-01T00:00:00Z",
        aux_deliberation=False,
    )
    telemetry_entries = {"old-debug-helper": _stale_agent_telemetry_entry()}
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills("old-debug-helper"),
        telemetry=_FakeTelemetry(telemetry_entries),
        config=config,
        now_fn=_now_fn,
    )
    report = service.run(apply=False, include_protected=False)

    # Must be a plain dry-run with no provider ever called
    assert report.mode == ReportMode.DRY_RUN
    assert report.warnings == [], f"Expected no warnings, got: {report.warnings}"
    # Proposals exist but carry no aux verdict (feature disabled)
    for proposal in report.proposals:
        assert proposal.aux_verdict is None, (
            f"aux_verdict must be None when aux_deliberation=False, got {proposal.aux_verdict!r}"
        )


@pytest.mark.parametrize(
    "proposal_kwargs,expected_status",
    [
        (
            {
                "name": "protected-skill",
                "origin": "agent",
                "action": CuratorAction.DELETE_CANDIDATE,
                "confidence": Confidence.HIGH,
                "apply_status": ApplyStatus.ELIGIBLE,
                "protected": True,
            },
            ApplyStatus.SKIPPED_PROTECTED,
        ),
        (
            {
                "name": "unknown-origin-skill",
                "origin": "unknown",
                "action": CuratorAction.DELETE_CANDIDATE,
                "confidence": Confidence.HIGH,
                "apply_status": ApplyStatus.ELIGIBLE,
            },
            ApplyStatus.SKIPPED_UNKNOWN_ORIGIN,
        ),
        (
            {
                "name": "builtin-skill",
                "origin": "builtin",
                "action": CuratorAction.DELETE_CANDIDATE,
                "confidence": Confidence.HIGH,
                "apply_status": ApplyStatus.ELIGIBLE,
            },
            ApplyStatus.SKIPPED_NON_AGENT,
        ),
        (
            {
                "name": "merge-skill",
                "origin": "agent",
                "action": CuratorAction.MERGE_CANDIDATE,
                "confidence": Confidence.HIGH,
                "apply_status": ApplyStatus.ELIGIBLE,
            },
            ApplyStatus.SKIPPED_UNSUPPORTED_ACTION,
        ),
        (
            {
                "name": "patch-skill",
                "origin": "agent",
                "action": CuratorAction.PATCH_CANDIDATE,
                "confidence": Confidence.HIGH,
                "apply_status": ApplyStatus.ELIGIBLE,
            },
            ApplyStatus.SKIPPED_UNSUPPORTED_ACTION,
        ),
    ],
)
def test_safety_gates_skip_without_calling_delete(
    proposal_kwargs: dict, expected_status: ApplyStatus
) -> None:
    """Safety-gate proposals must not call the delete operation and map to the expected status."""
    delete_called: list[str] = []

    def _fail_if_called(*, workspace: str, telemetry: object, provenance_tag: str, name: str) -> dict:
        delete_called.append(name)
        return {"ok": True, "verb": "delete", "name": name}

    proposal = CuratorProposal(**proposal_kwargs)
    config = CuratorConfig(forced_dry_run_until="2000-01-01T00:00:00Z")
    service = CuratorService(
        workspace="/workspace",
        skills=_FakeSkills(proposal_kwargs["name"]),
        telemetry=_FakeTelemetry({}),
        config=config,
        now_fn=_now_fn,
        delete_operation=_fail_if_called,
    )

    with patch("nanobot.curator.service.generate_proposals", return_value=[proposal]):
        report = service.run(apply=True, include_protected=True)

    assert report.mode == ReportMode.APPLY
    assert delete_called == [], f"delete must NOT be called, got: {delete_called}"
    assert report.proposals[0].apply_status == expected_status
