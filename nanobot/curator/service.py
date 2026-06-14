"""CuratorService: orchestrates dry-run and forced dry-run report generation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol

from nanobot.agent.tools.skill_manage_ops import do_delete
from nanobot.config.schema import CuratorConfig
from nanobot.curator.models import (
    ApplyStatus,
    Confidence,
    CuratorAction,
    CuratorProposal,
    CuratorReport,
    CuratorWarning,
    ReportMode,
)
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
        delete_operation: Callable used in apply mode to remove a skill.  Defaults
            to the M2 ``do_delete`` implementation from ``skill_manage_ops``.
        provenance_tag: String tag forwarded to the delete operation as an audit
            trail identifier.  Defaults to ``"curator"``.
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
        provenance_tag: str = "curator",
    ) -> None:
        self._workspace = workspace
        self._skills = skills
        self._telemetry = telemetry
        self._config = config
        self._now_fn: Callable[[], datetime] = now_fn or (
            lambda: datetime.now(timezone.utc)
        )
        self._delete_operation: Callable[..., dict[str, Any]] = delete_operation or do_delete
        self._provenance_tag: str = provenance_tag

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

    def forced_dry_run_active(self, now: datetime | None = None) -> bool:
        """Return True when the forced dry-run window is currently active.

        The window is active when ``resolve_forced_dry_run_until()`` returns a
        timestamp that is *in the future* relative to ``now``.  ``"auto"``
        always resolves to a future timestamp (now + 7 days) and is therefore
        always active.

        Args:
            now: The reference datetime to compare against.  Defaults to
                ``self._now_fn()`` when not provided, keeping callers (tests,
                external code) that omit the argument working correctly.
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
        reference = now if now is not None else self._now_fn()
        return reference < until_dt

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
        if apply and self.forced_dry_run_active(now):
            mode = ReportMode.FORCED_DRY_RUN
            for idx, proposal in enumerate(proposals):
                if proposal.apply_status == ApplyStatus.ELIGIBLE:
                    # Pydantic models are normally immutable; use model_copy to override.
                    proposals[idx] = proposal.model_copy(
                        update={"apply_status": ApplyStatus.REFUSED_FORCED_DRY_RUN}
                    )
        elif apply:
            mode = ReportMode.APPLY
            apply_warnings = self._apply_proposals(proposals)
            warnings.extend(apply_warnings)
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

    # ------------------------------------------------------------------
    # Apply helpers
    # ------------------------------------------------------------------

    def _apply_proposals(
        self,
        proposals: list[CuratorProposal],
    ) -> list[CuratorWarning]:
        """Attempt to apply each proposal in-place; return accumulated warnings.

        Replaces list entries in-place by index using ``model_copy`` (Pydantic
        models are immutable; the list itself is mutated, not the model objects).
        Safe-delete safety checks are enforced per proposal before calling the
        delete operation.  If the delete operation raises an exception, the
        proposal is mapped to ``ApplyStatus.FAILED``, a warning is appended, and
        processing continues with the remaining proposals.
        """
        warnings: list[CuratorWarning] = []
        for idx, proposal in enumerate(proposals):
            new_status: ApplyStatus | None = None

            if proposal.action == CuratorAction.DELETE_CANDIDATE:
                # Safety gate: protected origin
                if proposal.protected:
                    new_status = ApplyStatus.SKIPPED_PROTECTED
                elif proposal.origin == "unknown":
                    new_status = ApplyStatus.SKIPPED_UNKNOWN_ORIGIN
                elif proposal.origin != "agent":
                    # Covers non-agent origins including tier_locked TOCTOU rejection from M2 delete path.
                    new_status = ApplyStatus.SKIPPED_NON_AGENT
                elif (
                    proposal.confidence != Confidence.HIGH
                    or self._config.apply_delete_mode != "auto_high"
                ):
                    new_status = ApplyStatus.SKIPPED_LOW_CONFIDENCE
                else:
                    # All safety checks passed — call delete operation
                    try:
                        result = self._delete_operation(
                            workspace=self._workspace,
                            telemetry=self._telemetry,
                            provenance_tag=self._provenance_tag,
                            name=proposal.name,
                        )
                        new_status, warning = self._map_delete_result(result, proposal.name)
                        if warning is not None:
                            warnings.append(warning)
                    except Exception as exc:  # noqa: BLE001
                        new_status = ApplyStatus.FAILED
                        warnings.append(
                            CuratorWarning(
                                code="delete_failed",
                                message=(
                                    f"delete raised for skill '{proposal.name}': "
                                    f"{type(exc).__name__}"
                                ),
                            )
                        )
            elif proposal.action in {CuratorAction.MERGE_CANDIDATE, CuratorAction.PATCH_CANDIDATE}:
                new_status = ApplyStatus.SKIPPED_UNSUPPORTED_ACTION
            # CuratorAction.KEEP and CuratorAction.PROTECT: leave apply_status unchanged (NOT_APPLICABLE)

            if new_status is not None and new_status != proposal.apply_status:
                proposals[idx] = proposal.model_copy(update={"apply_status": new_status})

        return warnings

    def _map_delete_result(
        self,
        result: dict[str, Any],
        name: str,
    ) -> tuple[ApplyStatus, CuratorWarning | None]:
        """Map a do_delete result dict to an ApplyStatus and optional warning."""
        if result.get("ok") is True:
            return ApplyStatus.DELETED, None

        error_code = str(result.get("error_code", ""))
        if error_code == "not_found":
            return ApplyStatus.SKIPPED_MISSING, None
        if error_code == "tier_locked":
            return ApplyStatus.SKIPPED_NON_AGENT, None

        # Any other error: FAILED + warning
        warning = CuratorWarning(
            code="delete_failed",
            message=f"delete failed for skill '{name}': error_code={error_code}",
        )
        return ApplyStatus.FAILED, warning


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
