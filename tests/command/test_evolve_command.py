from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from nanobot.bus.events import InboundMessage
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, cmd_evolve, register_builtin_commands
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.config.schema import EvolutionConfig
from nanobot.evolve.proposals import maybe_create_dream_proposal


def _make_loop(*, evolution_config: EvolutionConfig | None = None) -> Any:
    workspace = MagicMock()
    workspace.__str__ = lambda self: "/fake/workspace"
    return SimpleNamespace(
        workspace=workspace,
        evolution_config=evolution_config or EvolutionConfig(),
        _schedule_background=lambda coro: None,
        bus=SimpleNamespace(publish_outbound=lambda msg: None),
    )


def _ctx(raw: str, args: str = "", loop: Any = None) -> CommandContext:
    msg = InboundMessage(channel="cli", sender_id="u1", chat_id="direct", content=raw)
    return CommandContext(
        msg=msg,
        session=None,
        key=msg.session_key,
        raw=raw,
        args=args,
        loop=loop or _make_loop(),
    )


@pytest.mark.asyncio
async def test_evolve_usage_for_unknown_action() -> None:
    out = await cmd_evolve(_ctx("/evolve bogus", args="bogus"))

    assert "Usage:" in out.content
    assert "list" in out.content
    assert out.metadata.get("render_as") == "text"


def test_evolve_registered_in_router_and_palette() -> None:
    router = CommandRouter()
    register_builtin_commands(router)

    assert router.is_dispatchable_command("/evolve")
    assert router.is_dispatchable_command("/evolve list")
    specs = {spec.command: spec for spec in BUILTIN_COMMAND_SPECS}
    assert "/evolve" in specs


@pytest.mark.asyncio
async def test_evolve_list_formats_store(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubStore:
        def __init__(self, workspace):
            pass

        def list(self):
            return []

    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)

    out = await cmd_evolve(_ctx("/evolve list", args="list"))

    assert "Evolution proposals" in out.content
    assert "No evolution proposals" in out.content


@pytest.mark.asyncio
async def test_evolve_create_requires_skill_and_rationale() -> None:
    out = await cmd_evolve(_ctx("/evolve create", args="create"))

    assert "Usage:" in out.content
    assert "create <skill> <rationale>" in out.content


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_evolve_create_rejects_path_like_skill_name() -> None:
    out = await cmd_evolve(_ctx("/evolve create ../secret make better", args="create ../secret make better"))

    assert "skill_name" in out.content


async def test_evolve_create_writes_manual_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubProposal:
        proposal_id = "evolve-1"
        skill_name = "demo-skill"
        source = "manual"
        status = "proposed"
        created_at = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)
        trigger_ref = None
        run_id = None
        manifest_path = None
        rationale_redacted = "make better"
        error_redacted = None

    class StubStore:
        def __init__(self, workspace):
            pass

    def fake_create_manual_proposal(store, *, skill_name, rationale):
        assert skill_name == "demo-skill"
        assert rationale == "make better"
        return StubProposal()

    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)
    monkeypatch.setattr(
        "nanobot.evolve.proposals.create_manual_proposal",
        fake_create_manual_proposal,
    )

    out = await cmd_evolve(
        _ctx("/evolve create demo-skill make better", args="create demo-skill make better")
    )

    assert "evolve-1" in out.content
    assert "demo-skill" in out.content


@pytest.mark.asyncio
async def test_evolve_show_formats_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubStore:
        def __init__(self, workspace):
            pass

        def get(self, proposal_id):
            assert proposal_id == "evolve-1"
            return SimpleNamespace(
                proposal_id="evolve-1",
                skill_name="demo-skill",
                source="manual",
                status="proposed",
                created_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
                trigger_ref=None,
                run_id=None,
                manifest_path=None,
                rationale_redacted="make better",
                error_redacted=None,
            )

    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)

    out = await cmd_evolve(_ctx("/evolve show evolve-1", args="show evolve-1"))

    assert "Proposal" in out.content
    assert "evolve-1" in out.content


@pytest.mark.asyncio
async def test_evolve_disabled_config_returns_message() -> None:
    out = await cmd_evolve(
        _ctx(
            "/evolve list",
            args="list",
            loop=_make_loop(evolution_config=EvolutionConfig(enabled=False)),
        )
    )

    assert "disabled by config" in out.content


@pytest.mark.asyncio
async def test_evolve_create_respects_manual_trigger_config() -> None:
    out = await cmd_evolve(
        _ctx(
            "/evolve create demo-skill make better",
            args="create demo-skill make better",
            loop=_make_loop(evolution_config=EvolutionConfig(proposal_triggers=["curator", "dream"])),
        )
    )

    assert "Manual evolution proposals are disabled" in out.content


@pytest.mark.asyncio
async def test_evolve_run_executes_background_success(monkeypatch: pytest.MonkeyPatch) -> None:
    published = []

    class StubStore:
        def __init__(self, workspace):
            pass

    class StubResult:
        proposal = SimpleNamespace(
            proposal_id="evolve-1",
            skill_name="demo-skill",
            status="completed",
            run_id="run-1",
            manifest_path="evals/runs/run-1/manifest.json",
        )
        manifest = SimpleNamespace(final_status="no_improvement")

    class StubRunner:
        def __init__(self, store):
            pass

        def run(self, proposal_id, **kwargs):
            assert proposal_id == "evolve-1"
            return StubResult()

    class Bus:
        async def publish_outbound(self, msg):
            published.append(msg)

    class Loop:
        workspace = Path("/tmp/workspace")
        evolution_config = EvolutionConfig()
        bus = Bus()

        def _schedule_background(self, coro):
            self.coro = coro

    loop = Loop()
    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)
    monkeypatch.setattr("nanobot.evolve.proposals.ProposalRunner", StubRunner)

    out = await cmd_evolve(_ctx("/evolve run evolve-1", args="run evolve-1", loop=loop))
    await loop.coro

    assert "Evolution run started" in out.content
    assert "Evolution run" in published[0].content
    assert "run-1" in published[0].content


@pytest.mark.asyncio
async def test_evolve_run_redacts_background_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    published = []

    class StubStore:
        def __init__(self, workspace):
            pass

    class StubRunner:
        def __init__(self, store):
            pass

        def run(self, proposal_id, **kwargs):
            raise RuntimeError("failed for alice@example.com")

    class Bus:
        async def publish_outbound(self, msg):
            published.append(msg)

    class Loop:
        workspace = Path("/tmp/workspace")
        evolution_config = EvolutionConfig()
        bus = Bus()

        def _schedule_background(self, coro):
            self.coro = coro

    loop = Loop()
    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)
    monkeypatch.setattr("nanobot.evolve.proposals.ProposalRunner", StubRunner)

    out = await cmd_evolve(_ctx("/evolve run evolve-1", args="run evolve-1", loop=loop))
    await loop.coro

    assert "Evolution run started" in out.content
    assert "alice@example.com" not in published[0].content
    assert "[REDACTED:EMAIL]" in published[0].content


@pytest.mark.asyncio
async def test_dream_completion_can_create_evolution_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = []

    class StubStore:
        def __init__(self, workspace):
            pass

    def fake_create_dream_proposal(store, *, skill_name, rationale, trigger_ref=None):
        created.append((skill_name, rationale, trigger_ref))

    monkeypatch.setattr("nanobot.evolve.proposals.ProposalStore", StubStore)
    monkeypatch.setattr(
        "nanobot.evolve.proposals.create_dream_proposal",
        fake_create_dream_proposal,
    )

    loop = SimpleNamespace(
        workspace=Path("/tmp/workspace"),
        evolution_config=EvolutionConfig(),
    )

    maybe_create_dream_proposal(
        loop,
        completed=True,
        processed_entries=12,
    )

    assert created == [
        (
            "dream-memory",
            "Dream completed after processing 12 history entries.",
            "dream:cursor:12",
        )
    ]


@pytest.mark.parametrize(
    "loop,completed",
    [
        (SimpleNamespace(workspace=Path("/tmp/workspace"), evolution_config=EvolutionConfig()), False),
        (SimpleNamespace(workspace=Path("/tmp/workspace"), evolution_config=None), True),
        (
            SimpleNamespace(
                workspace=Path("/tmp/workspace"),
                evolution_config=EvolutionConfig(enabled=False),
            ),
            True,
        ),
        (
            SimpleNamespace(
                workspace=Path("/tmp/workspace"),
                evolution_config=EvolutionConfig(proposal_triggers=["manual", "curator"]),
            ),
            True,
        ),
    ],
)
def test_dream_proposal_negative_paths_do_not_create(
    monkeypatch: pytest.MonkeyPatch,
    loop,
    completed: bool,
) -> None:
    def fail_create(*args, **kwargs):
        raise AssertionError("should not create dream proposal")

    monkeypatch.setattr("nanobot.evolve.proposals.create_dream_proposal", fail_create)

    assert maybe_create_dream_proposal(loop, completed=completed, processed_entries=12) is None
