"""Tests for telemetry construction & wiring at AgentLoop startup (M1 Task C3+)."""

from pathlib import Path
from unittest.mock import MagicMock

from nanobot.agent.loop import AgentLoop
from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.bus.queue import MessageBus


def _make_loop_with_real_deps(tmp_path: Path) -> AgentLoop:
    """Construct AgentLoop with REAL ContextBuilder/SubagentManager (no patches).

    Uses a plain (un-spec'd) MagicMock provider; AgentLoop.__init__ only calls
    provider.get_default_model() during construction, which MagicMock supports
    natively.
    """
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    return AgentLoop(bus=bus, provider=provider, workspace=tmp_path)


def test_agent_loop_constructs_telemetry_and_passes_down(tmp_path: Path) -> None:
    loop = _make_loop_with_real_deps(tmp_path)
    assert isinstance(loop.telemetry, SkillTelemetry)
    # The same SkillTelemetry instance must be threaded into both downstream owners.
    assert loop.context.skills.telemetry is loop.telemetry
    assert loop.subagents.telemetry is loop.telemetry
