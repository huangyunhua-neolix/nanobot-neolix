"""CuratorService: orchestrates dry-run and forced dry-run report generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from nanobot.config.schema import CuratorConfig
from nanobot.curator.models import ApplyStatus, CuratorReport, CuratorWarning, ReportMode
from nanobot.curator.policy import generate_proposals
from nanobot.curator.telemetry import SnapshotProvider, load_telemetry_snapshot

_UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
_AUTO_WINDOW_DAYS = 7


class SkillsProvider(Protocol):
    """Minimal interface required by :class:`CuratorService`."""

    def list_skills_with_shadows(self) -> list[dict[str, Any]]: ...

    def get_skill_metadata(self, name: str) -> dict[str, Any] | None: ...


class CuratorService:
    """Orchestrate dry-run and forced dry-run curator report generation.

    Args:
        workspace: Path string for the agent workspace (informational; passed through).
        skills: Object exposing ``list_skills_with_shadows()`` and ``get_skill_metadata()``.
        telemetry: Object exposing ``snapshot()`` (a :class:`SnapshotProvider`).
        config: :class:`CuratorConfig` from the active agent configuration.
        now_fn: Callable returning the current UTC datetime.  Defaults to
            ``datetime.now(timezone.utc)``.  Injected for determinism in tests.
        delete_operation: Reserved; not used in dry-run mode.  Accepted for
            interface stability so callers can pre-wire apply logic.
        provenance_tag: Optional string tag attached to the service instance
            (e.g. session id); unused internally but visible for diagnostics.
    """

    def __init__(
        self,
        *,
        workspace: str,
        skills: SkillsProvider,
        telemetry: SnapshotProvider,
        config: CuratorConfig,
        now_fn: Callable[[], datetime] | None = None,
        delete_operation: Any = None,
        provenance_tag: str | None = None,
    ) -> None:
        self._workspace = workspace
        self._skills = skills
        self._telemetry = telemetry
        self._config = config
        self._now_fn: Callable[[], datetime] = now_fn or (
            lambda: datetime.now(timezone.utc)
        )
        self._delete_operation = delete_operation
        self._provenance_tag = provenance_tag

    # ------------------------------------------------------------------
    # Forced dry-run helpers
    # ------------------------------------------------------------------

    def resolve_forced_dry_run_until(self) -> str | None:
        """Return the resolved forced-dry-run timestamp string, or None.

        If ``config.forced_dry_run_until == "auto"``, returns now + 7 days
        formatted as ``YYYY-MM-DDTHH:MM:SSZ``.  If it is already a concrete
        timestamp, returns it unchanged.  Returns ``None`` when the field is
        empty string or any falsy value.
        """
        value = self._config.forced_dry_run_until
        if not value:
            return None
        if value == "auto":
            until_dt = self._now_fn() + timedelta(days=_AUTO_WINDOW_DAYS)
            return until_dt.strftime(_UTC_FMT)
        return value

    def forced_dry_run_active(self) -> bool:
        """Return True when the forced dry-run window is currently active.

        The window is active when ``resolve_forced_dry_run_until()`` returns a
        timestamp that is *in the future* relative to ``now_fn()``.  ``"auto"``
        always resolves to a future timestamp (now + 7 days) and is therefore
        always active.
        """
        resolved = self.resolve_forced_dry_run_until()
        if resolved is None:
            return False
        if self._config.forced_dry_run_until == "auto":
            return True
        try:
            until_dt = datetime.strptime(resolved, _UTC_FMT).replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        return self._now_fn() < until_dt

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run(self, *, apply: bool, include_protected: bool) -> CuratorReport:
        """Generate a curator report.

        Args:
            apply: When ``True``, the caller requested destructive apply
                actions.  If a forced dry-run window is active, apply is
                refused and proposals receive ``ApplyStatus.REFUSED_FORCED_DRY_RUN``.
            include_protected: When ``True``, PROTECT and KEEP proposals are
                included in the output.

        Returns:
            A :class:`CuratorReport` reflecting the current skill hygiene state.
        """
        now = self._now_fn()

        # --- Load telemetry (best-effort; warnings collected) ---
        telem_result = load_telemetry_snapshot(self._telemetry)
        warnings: list[CuratorWarning] = list(telem_result.warnings)
        telemetry_entries: dict[str, Any] = dict(telem_result.snapshot.get("entries", {}))

        # --- Load visible skills ---
        visible_skills = self._skills.list_skills_with_shadows()
        metadata_by_name: dict[str, dict[str, Any]] = {}
        for skill in visible_skills:
            name = str(skill["name"])
            meta = self._skills.get_skill_metadata(name)
            metadata_by_name[name] = meta or {}

        # --- Generate proposals ---
        proposals = generate_proposals(
            visible_skills=visible_skills,
            telemetry_entries=telemetry_entries,
            metadata_by_name=metadata_by_name,
            config=self._config,
            now=now,
            include_protected=include_protected,
        )

        # --- Determine mode and apply forced dry-run overrides ---
        if apply and self.forced_dry_run_active():
            mode = ReportMode.FORCED_DRY_RUN
            for proposal in proposals:
                if proposal.apply_status == ApplyStatus.ELIGIBLE:
                    # Pydantic models are normally immutable; use model_copy to override.
                    idx = proposals.index(proposal)
                    proposals[idx] = proposal.model_copy(
                        update={"apply_status": ApplyStatus.REFUSED_FORCED_DRY_RUN}
                    )
        elif apply:
            mode = ReportMode.APPLY
        else:
            mode = ReportMode.DRY_RUN

        # Count protected skills (proposals with protected=True OR not in output due to
        # include_protected=False).  We count across ALL visible_skills for the
        # skills_scanned total, but only track protected from proposals list
        # that have protected=True.  To get an accurate protected count we
        # re-run with include_protected=True if needed.
        if not include_protected:
            protected_count = _count_protected(
                visible_skills=visible_skills,
                telemetry_entries=telemetry_entries,
                metadata_by_name=metadata_by_name,
                config=self._config,
                now=now,
            )
        else:
            protected_count = sum(1 for p in proposals if p.protected)

        return CuratorReport(
            mode=mode,
            skills_scanned=len(visible_skills),
            protected=protected_count,
            proposals=proposals,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _count_protected(
    *,
    visible_skills: list[dict[str, Any]],
    telemetry_entries: dict[str, Any],
    metadata_by_name: dict[str, dict[str, Any]],
    config: CuratorConfig,
    now: datetime,
) -> int:
    """Return the number of skills that would be PROTECT proposals."""
    all_proposals = generate_proposals(
        visible_skills=visible_skills,
        telemetry_entries=telemetry_entries,
        metadata_by_name=metadata_by_name,
        config=config,
        now=now,
        include_protected=True,
    )
    return sum(1 for p in all_proposals if p.protected)
