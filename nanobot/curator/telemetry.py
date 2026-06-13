"""Telemetry snapshot adapter for Curator.

Curator reads telemetry exclusively through this adapter.
It never reads or writes raw `.telemetry.json` files directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nanobot.agent.skills_telemetry import TelemetrySnapshot
from nanobot.curator.models import CuratorWarning


@dataclass(frozen=True)
class TelemetrySnapshotResult:
    snapshot: TelemetrySnapshot
    warnings: list[CuratorWarning] = field(default_factory=list)


def load_telemetry_snapshot(telemetry: Any) -> TelemetrySnapshotResult:
    """Return Curator's read-only view of skill telemetry.

    Calls `telemetry.snapshot()` only. On OSError, returns an empty snapshot
    and a warning with code `telemetry_snapshot_failed`.
    """
    try:
        snapshot = telemetry.snapshot()
    except OSError as exc:
        return TelemetrySnapshotResult(
            snapshot={"schema_version": 1, "updated_at": "", "entries": {}},
            warnings=[
                CuratorWarning(
                    code="telemetry_snapshot_failed",
                    message=f"telemetry snapshot unavailable: {exc}",
                )
            ],
        )
    return TelemetrySnapshotResult(snapshot=snapshot, warnings=[])
