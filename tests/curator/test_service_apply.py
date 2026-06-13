"""Tests for CuratorService dry-run and forced dry-run orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

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
    """When forced dry-run is inactive, apply=True yields APPLY mode."""
    service = _make_service(forced_dry_run_until="2000-01-01T00:00:00Z")
    assert service.forced_dry_run_active() is False

    report = service.run(apply=True, include_protected=False)
    assert report.mode == ReportMode.APPLY
    # ELIGIBLE status is preserved (no actual delete is performed here)
    assert report.proposals[0].apply_status == ApplyStatus.ELIGIBLE


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
