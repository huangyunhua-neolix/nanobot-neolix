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


# --- t-09 additions: synchronicity + subagent-budget isolation ---------------

import ast  # noqa: E402
import asyncio  # noqa: E402
import inspect  # noqa: E402


def _make_tool(workspace: Path, runtime_state: SimpleNamespace) -> SkillManageTool:
    """Helper: build a SkillManageTool wired to the given workspace + state.

    Mirrors the construction used by `test_create_rate_limited_after_5_in_one_iteration`
    above, factored out so the t-09 tests can stay terse.
    """
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
    return SkillManageTool(
        workspace=workspace,
        telemetry=None,
        provenance_tag="agent",
        config=config,
        runtime_state=runtime_state,
    )


@pytest.mark.parametrize("sixth_verb", ["edit", "patch", "delete"])
@pytest.mark.asyncio
async def test_any_verb_rate_limited_after_5_creates(
    tmp_path: Path,
    sixth_verb: str,
) -> None:
    """5 successful creates + 6th call of ANY verb → `rate_limited`.

    The rate-cap gate runs BEFORE cheap-rejects (skill_manage.py §Step A,
    pre-validation, pre-existence-check), so the 6th verb does not need to
    name an existing skill — it just has to trip the gate.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 0})
    tool = _make_tool(workspace, runtime_state)

    for i in range(5):
        r = await tool.execute(verb="create", name=f"s{i}", body="x")
        assert r["ok"], f"create #{i} should succeed but got {r!r}"
    assert runtime_state._runtime_vars[_RATE_CAP_KEY] == 5

    # 6th call: pick verb-appropriate args. Even if the verb would otherwise
    # cheap-reject (e.g. delete on a non-existent name), the rate-cap gate
    # MUST fire first.
    if sixth_verb == "edit":
        sixth = await tool.execute(verb="edit", name="s0", body="y")
    elif sixth_verb == "patch":
        sixth = await tool.execute(
            verb="patch", name="s0", search="x", replace="z",
        )
    else:  # delete
        sixth = await tool.execute(verb="delete", name="s0")

    assert sixth["ok"] is False
    assert sixth["error_code"] == "rate_limited", (
        f"expected rate_limited as 6th verb={sixth_verb!r}, got {sixth!r}"
    )
    # Reject path must NOT have bumped the counter further.
    assert runtime_state._runtime_vars[_RATE_CAP_KEY] == 5


@pytest.mark.asyncio
async def test_reset_then_mixed_verbs_succeed(tmp_path: Path) -> None:
    """5 creates → manual reset → 5 mixed verbs (edit/patch/delete on existing
    skills) all succeed. Proves the gate is purely counter-based and does NOT
    track verb identity.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 0})
    tool = _make_tool(workspace, runtime_state)

    # Phase 1: saturate the counter with 5 creates.
    for i in range(5):
        r = await tool.execute(verb="create", name=f"s{i}", body="x")
        assert r["ok"], f"create #{i} unexpectedly rejected: {r!r}"
    assert runtime_state._runtime_vars[_RATE_CAP_KEY] == 5

    # Simulate AgentRunner._run_core's per-iteration reset (top of for-loop).
    runtime_state._runtime_vars[_RATE_CAP_KEY] = 0

    # Phase 2: 5 mixed-verb mutations on the existing skills, all should pass
    # both the rate-cap gate and verb pipelines.
    mixed: list[dict] = []
    mixed.append(await tool.execute(verb="edit", name="s0", body="yy"))
    mixed.append(
        await tool.execute(verb="patch", name="s1", search="x", replace="z")
    )
    mixed.append(await tool.execute(verb="delete", name="s2"))
    mixed.append(await tool.execute(verb="edit", name="s3", body="qq"))
    mixed.append(await tool.execute(verb="delete", name="s4"))

    for idx, r in enumerate(mixed):
        assert r["ok"], f"mixed-verb call #{idx} rejected: {r!r}"
    assert runtime_state._runtime_vars[_RATE_CAP_KEY] == 5


@pytest.mark.asyncio
async def test_concurrent_gather_at_counter_4_one_winner(tmp_path: Path) -> None:
    """Two parallel `asyncio.gather` tasks starting from counter=4 →
    exactly one `ok=True` and one `rate_limited`.

    This locks down the synchronicity invariant: the read+check+increment
    sequence inside `_increment_mutation_counter_or_reject` does NOT
    `await`, so a single-threaded asyncio loop cannot interleave them, and
    only one of the two tasks can observe `current=4` before incrementing.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    runtime_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 4})
    tool = _make_tool(workspace, runtime_state)

    # Two distinct names so the verb pipelines themselves cannot interfere
    # (each grabs a different name-lock); the only contended resource is the
    # rate-cap counter.
    call1 = tool.execute(verb="create", name="alpha", body="a")
    call2 = tool.execute(verb="create", name="beta", body="b")
    r1, r2 = await asyncio.gather(call1, call2)

    oks = [r for r in (r1, r2) if r["ok"]]
    rejects = [r for r in (r1, r2) if not r["ok"]]
    assert len(oks) == 1, f"expected exactly one winner, got {oks!r}"
    assert len(rejects) == 1, f"expected exactly one reject, got {rejects!r}"
    assert rejects[0]["error_code"] == "rate_limited"
    # Final counter == 5 (the lone successful increment).
    assert runtime_state._runtime_vars[_RATE_CAP_KEY] == 5


def test_increment_helper_has_no_await() -> None:
    """Static gate: `_increment_mutation_counter_or_reject` MUST be a
    plain synchronous function with NO `await` expressions. An accidental
    `await` (e.g. someone refactoring to use an async lock) would re-open
    the race window the helper is meant to close.
    """
    src = inspect.getsource(
        SkillManageTool._increment_mutation_counter_or_reject
    )
    tree = ast.parse(src.lstrip())  # lstrip to drop leading method indent
    awaits = [n for n in ast.walk(tree) if isinstance(n, ast.Await)]
    assert awaits == [], (
        "_increment_mutation_counter_or_reject must contain no `await` "
        f"expressions; found {len(awaits)}"
    )


@pytest.mark.asyncio
async def test_subagent_independent_quota(tmp_path: Path) -> None:
    """Subagent (and grandchild) get a FRESH per-turn quota — the parent's
    counter is not inherited or shared. Each tier runs the full 5-mutation
    budget independently; the parent's counter remains untouched.
    """
    # --- Parent: 4 mutations (under the cap) -------------------------------
    parent_ws = tmp_path / "parent_ws"
    parent_ws.mkdir()
    parent_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 0})
    parent_tool = _make_tool(parent_ws, parent_state)
    for i in range(4):
        r = await parent_tool.execute(verb="create", name=f"p{i}", body="x")
        assert r["ok"], f"parent create #{i} rejected: {r!r}"
    assert parent_state._runtime_vars[_RATE_CAP_KEY] == 4

    # --- Subagent spawn: a FRESH RuntimeState (NOT shared with parent). ----
    # In production this is the contract `subagent.py` (t-11) must honour;
    # here we exercise the RuntimeState contract directly.
    sub_ws = tmp_path / "sub_ws"
    sub_ws.mkdir()
    sub_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 0})
    assert sub_state is not parent_state
    assert sub_state._runtime_vars is not parent_state._runtime_vars

    sub_tool = _make_tool(sub_ws, sub_state)
    for i in range(5):
        r = await sub_tool.execute(verb="create", name=f"c{i}", body="x")
        assert r["ok"], f"subagent create #{i} rejected: {r!r}"
    assert sub_state._runtime_vars[_RATE_CAP_KEY] == 5

    # --- Grandchild spawn: another fresh RuntimeState. ---------------------
    grand_ws = tmp_path / "grand_ws"
    grand_ws.mkdir()
    grand_state = SimpleNamespace(_runtime_vars={_RATE_CAP_KEY: 0})
    grand_tool = _make_tool(grand_ws, grand_state)
    for i in range(5):
        r = await grand_tool.execute(verb="create", name=f"g{i}", body="x")
        assert r["ok"], f"grandchild create #{i} rejected: {r!r}"
    assert grand_state._runtime_vars[_RATE_CAP_KEY] == 5

    # Parent counter MUST NOT have moved while children mutated. Confirms
    # there is no aliasing of `_runtime_vars` across the tier boundary.
    assert parent_state._runtime_vars[_RATE_CAP_KEY] == 4


# --- t-11 addition: subagent independent quota via SkillManageTool ----------


@pytest.mark.asyncio
async def test_subagent_skill_manage_tool_independent_quota(
    tmp_path: Path,
) -> None:
    """Spec §5.2.1 (SkillManageTool layer): a spawned subagent's per-turn
    rate-cap counter is INDEPENDENT of its parent's. Five mutations on the
    subagent's state succeed, the 6th rate-limits, and the parent's counter
    is unchanged.

    Companion to `test_subagent_independent_quota` above: that one exercises
    the RuntimeState contract via `_make_tool`; this one constructs
    `SkillManageTool` directly with a `subagent:` provenance tag to lock
    down the tool-level wiring contract that t-11 depends on.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()

    parent_runtime_state = SimpleNamespace(
        _runtime_vars={"skill_manage.mutations_this_turn": 3},
    )
    sub_runtime_state = SimpleNamespace(
        _runtime_vars={"skill_manage.mutations_this_turn": 0},
    )

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

    sub_tool = SkillManageTool(
        workspace=workspace,
        telemetry=None,
        provenance_tag="subagent:abcd1234",
        config=config,
        runtime_state=sub_runtime_state,
    )

    accepted = 0
    rejected: list[dict] = []
    for i in range(6):
        r = await sub_tool.execute(verb="create", name=f"s{i}", body="x")
        if r["ok"]:
            accepted += 1
        else:
            rejected.append(r)

    # 5 succeed on the subagent; 6th rate-limits.
    assert accepted == 5
    assert len(rejected) == 1
    assert rejected[0]["error_code"] == "rate_limited"
    assert sub_runtime_state._runtime_vars["skill_manage.mutations_this_turn"] == 5

    # Parent's counter is untouched — the two RuntimeStates are isolated.
    assert parent_runtime_state._runtime_vars[
        "skill_manage.mutations_this_turn"
    ] == 3
