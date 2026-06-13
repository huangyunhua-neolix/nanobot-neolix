"""Tests for the Curator telemetry snapshot adapter."""

from pathlib import Path

from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.curator.telemetry import TelemetrySnapshotResult, load_telemetry_snapshot


def test_load_telemetry_snapshot_returns_empty_for_missing_file(tmp_path: Path) -> None:
    telemetry = SkillTelemetry(tmp_path)

    result = load_telemetry_snapshot(telemetry)

    assert isinstance(result, TelemetrySnapshotResult)
    assert result.snapshot["entries"] == {}
    assert result.warnings == []


def test_snapshot_includes_dirty_in_memory_entries_without_flush(tmp_path: Path) -> None:
    telemetry = SkillTelemetry(tmp_path)
    telemetry.reconcile(
        [
            {
                "name": "dirty-skill",
                "effective_origin": "agent",
                "shadowed_origins": [],
                "path": str(tmp_path / "skills" / "agent" / "dirty-skill" / "SKILL.md"),
            }
        ]
    )
    telemetry.bump("dirty-skill", "view")

    result = load_telemetry_snapshot(telemetry)

    assert result.snapshot["entries"]["dirty-skill"]["views"] == 1


def test_snapshot_preserves_unknown_origin(tmp_path: Path) -> None:
    """Unknown-origin entries (created via bump before reconcile) are preserved."""
    telemetry = SkillTelemetry(tmp_path)
    # bump a name that has never been reconciled → SkillTelemetry gives it "unknown" origin
    telemetry.bump("mystery", "view")

    result = load_telemetry_snapshot(telemetry)

    assert result.snapshot["entries"]["mystery"]["origin"] == "unknown"


def test_oserror_from_snapshot_returns_empty_and_warning(tmp_path: Path) -> None:
    """OSError from telemetry.snapshot() returns empty snapshot + warning."""

    class _BrokenTelemetry:
        def snapshot(self):
            raise OSError("disk exploded")

    result = load_telemetry_snapshot(_BrokenTelemetry())

    assert result.snapshot["entries"] == {}
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "telemetry_snapshot_failed"
    assert "disk exploded" in result.warnings[0].message
