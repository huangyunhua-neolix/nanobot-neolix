"""M2 (#67 W1): per-turn rate-cap counter must reset at the TOP of every
iteration in `AgentRunner._run_core`.

The runner reads/increments
``runtime_state._runtime_vars["skill_manage.mutations_this_turn"]`` to enforce
``skill_manage.max_mutations_per_turn``.  If the reset were placed OUTSIDE
the for-loop, mutations would leak across iterations and the spec would
break.  This test pre-seeds a non-zero value, drives the runner for 3
iterations, and asserts the counter reads 0 at the top of every iteration.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from nanobot.agent.hook import AgentHook, AgentHookContext
from nanobot.agent.runner import AgentRunner, AgentRunSpec
from nanobot.config.schema import AgentDefaults
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest

_MAX_TOOL_RESULT_CHARS = AgentDefaults().max_tool_result_chars
_RATE_CAP_KEY = "skill_manage.mutations_this_turn"


class _RecordingHook(AgentHook):
    """Records the rate-cap counter as observed at the top of each iteration,
    then bumps it to a non-zero value to prove the next iteration resets it.
    """

    def __init__(self, runtime_state: SimpleNamespace) -> None:
        super().__init__()
        self._runtime_state = runtime_state
        self.observed_at_iter_start: list[int] = []

    async def before_iteration(self, context: AgentHookContext) -> None:
        # `before_iteration` runs AFTER the reset line at the top of the
        # for-loop body, so a correctly-implemented reset means we always
        # observe 0 here, even if the previous iteration left a stale value.
        self.observed_at_iter_start.append(
            self._runtime_state._runtime_vars[_RATE_CAP_KEY]
        )
        # Simulate skill_manage performing a mutation this turn so that
        # if the reset were missing, the next iteration would see a non-zero
        # leaked value.
        self._runtime_state._runtime_vars[_RATE_CAP_KEY] += 7


@pytest.mark.asyncio
async def test_per_iteration_reset() -> None:
    runtime_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 3})

    provider = MagicMock(spec=LLMProvider)
    # Each call returns a tool-call response so the runner advances another
    # iteration without ever finalising; we cap iterations at 3 below.
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(
        content="thinking",
        tool_calls=[ToolCallRequest(id="c", name="list_dir", arguments={"path": "."})],
        usage={},
    ))

    tools = MagicMock()
    tools.get_definitions.return_value = []
    tools.execute = AsyncMock(return_value="ok")

    hook = _RecordingHook(runtime_state)

    runner = AgentRunner(provider)
    await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        model="test-model",
        max_iterations=3,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        hook=hook,
        runtime_state=runtime_state,  # the field under test
    ))

    # Three iterations were run; at the top of EACH the counter must be 0.
    assert hook.observed_at_iter_start == [0, 0, 0], (
        "skill_manage.mutations_this_turn must be reset to 0 at the TOP of "
        "each iteration; observed: " + repr(hook.observed_at_iter_start)
    )


@pytest.mark.asyncio
async def test_runtime_state_none_is_back_compat_noop() -> None:
    """When runtime_state is None (default for non-agent harnesses), the
    runner must NOT crash trying to reset a counter on a missing state."""
    provider = MagicMock(spec=LLMProvider)
    provider.chat_with_retry = AsyncMock(return_value=LLMResponse(
        content="done",
        tool_calls=[],
        usage={},
    ))
    tools = MagicMock()
    tools.get_definitions.return_value = []

    runner = AgentRunner(provider)
    result = await runner.run(AgentRunSpec(
        initial_messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        model="test-model",
        max_iterations=2,
        max_tool_result_chars=_MAX_TOOL_RESULT_CHARS,
        # runtime_state intentionally omitted → defaults to None
    ))
    assert result.final_content == "done"


# --- t-08 addition: rate-limited dispatcher path -----------------------------


from pathlib import Path  # noqa: E402

from nanobot.agent.tools.skill_manage import SkillManageTool  # noqa: E402


@pytest.mark.asyncio
async def test_create_rate_limited_after_5_in_one_iteration(
    tmp_path: Path,
) -> None:
    """6th create within a single iteration → `rate_limited` reject."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime_state = SimpleNamespace(_runtime_vars={"skill_manage.mutations_this_turn": 0})
    config = type(
        "_Cfg", (), {
            "skill_manage": type(
                "_SM", (), {
                    "max_mutations_per_turn": 5,
                    "max_body_bytes": 65536,
                    "max_agent_skills": 200,
                    "max_description_len": 280,
                },
            )(),
        },
    )()
    tool = SkillManageTool(
        workspace=workspace,
        telemetry=None,
        provenance_tag="agent",
        config=config,
        runtime_state=runtime_state,
    )
    accepted = 0
    rejected: list[dict] = []
    for i in range(6):
        r = await tool.execute(verb="create", name=f"s{i}", body="x")
        if r["ok"]:
            accepted += 1
        else:
            rejected.append(r)
    assert accepted == 5
    assert len(rejected) == 1
    assert rejected[0]["error_code"] == "rate_limited"
    # Counter MUST NOT have been incremented past max on the rejected call.
    assert runtime_state._runtime_vars["skill_manage.mutations_this_turn"] == 5
