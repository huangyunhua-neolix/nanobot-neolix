"""Tests for the /curator built-in command."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, cmd_curator, register_builtin_commands
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.config.schema import CuratorConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeSkills:
    def list_skills_with_shadows(self) -> list[dict[str, Any]]:
        return []

    def get_skill_metadata(self, name: str) -> dict[str, Any] | None:
        return None


class _FakeTelemetry:
    def snapshot(self) -> dict[str, Any]:
        return {"schema_version": 1, "updated_at": "", "entries": {}}


def _make_loop(*, curator_config: CuratorConfig | None = None) -> Any:
    """Build a minimal fake loop accepted by cmd_curator."""
    loop = SimpleNamespace(
        workspace=MagicMock(),  # Path-like; str() is called on it
        context=SimpleNamespace(skills=_FakeSkills()),
        telemetry=_FakeTelemetry(),
        curator_config=curator_config or CuratorConfig(),
    )
    # Make str(loop.workspace) return something sensible
    loop.workspace.__str__ = lambda self: "/fake/workspace"
    return loop


def _ctx(raw: str, args: str = "", loop: Any = None) -> CommandContext:
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    return CommandContext(
        msg=msg, session=None, key=msg.session_key, raw=raw, args=args, loop=loop or _make_loop()
    )


# ---------------------------------------------------------------------------
# Arg-parsing: default (dry-run)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_default_is_dry_run() -> None:
    """No args → dry-run text report returned."""
    out = await cmd_curator(_ctx("/curator", args=""))
    assert "Curator report" in out.content
    assert "dry-run" in out.content


@pytest.mark.asyncio
async def test_curator_explicit_dry_run_flag() -> None:
    """--dry-run is equivalent to default."""
    out = await cmd_curator(_ctx("/curator --dry-run", args="--dry-run"))
    assert "Curator report" in out.content
    assert "dry-run" in out.content


# ---------------------------------------------------------------------------
# Arg-parsing: --apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_apply_flag_forced_dry_run() -> None:
    """--apply with default config (forced_dry_run_until='auto') is refused.

    The default CuratorConfig has forced_dry_run_until='auto', which is always
    active, so --apply must be blocked and the report must say so.
    """
    out = await cmd_curator(_ctx("/curator --apply", args="--apply"))
    assert "Apply refused" in out.content
    assert "forced dry-run" in out.content.lower()
    assert "Curator report" in out.content


# ---------------------------------------------------------------------------
# Arg-parsing: --json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_json_flag_wraps_in_fenced_block() -> None:
    """--json wraps the JSON report in a fenced ```json block."""
    out = await cmd_curator(_ctx("/curator --json", args="--json"))
    assert out.content.startswith("```json\n")
    assert out.content.rstrip().endswith("```")
    # Should contain parseable JSON with mode field
    import json
    inner = out.content.strip().removeprefix("```json").removesuffix("```").strip()
    data = json.loads(inner)
    assert "mode" in data


@pytest.mark.asyncio
async def test_curator_json_sets_render_metadata() -> None:
    """--json output has render_as=text so markdown renderer won't re-escape."""
    out = await cmd_curator(_ctx("/curator --json", args="--json"))
    assert out.metadata.get("render_as") == "text"


# ---------------------------------------------------------------------------
# Arg-parsing: --include-protected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_include_protected_flag_accepted() -> None:
    """--include-protected is accepted without error."""
    out = await cmd_curator(_ctx("/curator --include-protected", args="--include-protected"))
    assert "Curator report" in out.content


# ---------------------------------------------------------------------------
# Arg-parsing: unknown flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_unknown_flag_returns_usage() -> None:
    """Unknown flag returns a usage message containing 'unknown flag: <flag>'."""
    out = await cmd_curator(_ctx("/curator --bogus", args="--bogus"))
    assert "unknown flag: --bogus" in out.content


# ---------------------------------------------------------------------------
# Arg-parsing: mutual exclusion of --dry-run and --apply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_curator_dry_run_and_apply_conflict() -> None:
    """--dry-run and --apply together are mutually exclusive regardless of order."""
    out = await cmd_curator(_ctx("/curator --dry-run --apply", args="--dry-run --apply"))
    assert "--dry-run" in out.content and "--apply" in out.content
    assert "mutually exclusive" in out.content.lower() or "cannot" in out.content.lower()


@pytest.mark.asyncio
async def test_curator_apply_and_dry_run_conflict_reversed() -> None:
    """Order does not matter for the mutual-exclusion check."""
    out = await cmd_curator(_ctx("/curator --apply --dry-run", args="--apply --dry-run"))
    assert "--dry-run" in out.content and "--apply" in out.content
    assert "mutually exclusive" in out.content.lower()


# ---------------------------------------------------------------------------
# Router registration: exact and prefix
# ---------------------------------------------------------------------------


def test_curator_exact_registration() -> None:
    """'/curator' (exact) is dispatchable."""
    router = CommandRouter()
    register_builtin_commands(router)
    assert router.is_dispatchable_command("/curator")


def test_curator_prefix_registration() -> None:
    """'/curator --apply' (prefix) is dispatchable."""
    router = CommandRouter()
    register_builtin_commands(router)
    assert router.is_dispatchable_command("/curator --apply")


@pytest.mark.asyncio
async def test_curator_dispatches_via_router() -> None:
    """Router dispatches /curator and returns an OutboundMessage."""
    router = CommandRouter()
    register_builtin_commands(router)
    out = await router.dispatch(_ctx("/curator", args=""))
    assert out is not None
    assert "Curator report" in out.content


# ---------------------------------------------------------------------------
# Command palette entry
# ---------------------------------------------------------------------------


def test_curator_in_command_palette() -> None:
    """BUILTIN_COMMAND_SPECS must contain the /curator entry."""
    specs = {spec.command: spec for spec in BUILTIN_COMMAND_SPECS}
    assert "/curator" in specs
    spec = specs["/curator"]
    assert spec.title == "Review skills"
    assert spec.description == "Review skill telemetry and propose safe cleanup actions."
    assert spec.icon == "scissors"
    assert "--dry-run" in spec.arg_hint
