"""M2 §4.2 — ToolContext.provenance_tag default + assignability.

Extended in t-07 with:
* write-once binding test (`SkillManageTool.create` captures the tag at
  construction time, immune to later ctx mutations).
* `_validate_provenance_tag` accept / reject sweep.
"""
from __future__ import annotations

import pytest


def test_tool_context_default_provenance_tag():
    from nanobot.agent.tools.context import ToolContext

    ctx = ToolContext(config=None, workspace="/tmp/dummy")
    assert ctx.provenance_tag == "agent"


def test_tool_context_provenance_tag_assignable():
    from nanobot.agent.tools.context import ToolContext

    ctx = ToolContext(
        config=None,
        workspace="/tmp/dummy",
        provenance_tag="subagent:abcd1234",
    )
    assert ctx.provenance_tag == "subagent:abcd1234"
    ctx.provenance_tag = "dream"
    assert ctx.provenance_tag == "dream"


# --- t-07 additions -----------------------------------------------------------


def test_provenance_tag_write_once():
    """`SkillManageTool.create` captures `ctx.provenance_tag` ONCE.

    Subsequent mutations to `ctx.provenance_tag` must NOT bleed into the
    already-constructed tool instance.
    """
    from nanobot.agent.tools.context import ToolContext
    from nanobot.agent.tools.skill_manage import SkillManageTool

    ctx = ToolContext(
        config=None,
        workspace="/tmp/dummy",
        provenance_tag="subagent:abc1",
    )
    tool = SkillManageTool.create(ctx)
    assert tool._provenance_tag_ == "subagent:abc1"

    # Mutate after construction — original tool must NOT pick this up.
    ctx.provenance_tag = "agent"
    assert tool._provenance_tag_ == "subagent:abc1"

    # And a brand new tool from the same (mutated) ctx picks up the new tag,
    # confirming the capture was at construction time and not at execute time.
    tool2 = SkillManageTool.create(ctx)
    assert tool2._provenance_tag_ == "agent"


def test_validate_provenance_tag_accepts_agent_and_subagent():
    from nanobot.agent.tools.skill_manage import _validate_provenance_tag

    # Should not raise.
    _validate_provenance_tag("agent")
    _validate_provenance_tag("subagent:abc")
    _validate_provenance_tag("subagent:" + "x" * 64)
    _validate_provenance_tag("subagent:A_b-1")


def test_validate_provenance_tag_rejects_bad_ids():
    from nanobot.agent.tools.skill_manage import _validate_provenance_tag

    bad = [
        "subagent:",                  # empty id
        "subagent:" + "x" * 65,       # id too long
        "subagent:中文",              # non-ASCII id
        "subagent:a/b",               # disallowed punctuation
        "subagent:a b",               # whitespace in id
        "hub",                        # neither 'agent' nor 'subagent:<id>'
        "",                           # empty
        "agent  ",                    # trailing whitespace
        " agent",                     # leading whitespace
        "AGENT",                      # uppercase literal
        "user",                       # not allowed (no 'user' principal)
        "subagent:abc:def",           # ':' in id
    ]
    for tag in bad:
        with pytest.raises(ValueError):
            _validate_provenance_tag(tag)


# --- t-11 additions: subagent provenance tag wiring -------------------------


def test_subagent_provenance_tag(tmp_path):
    """SubagentManager._build_subagent_tool_context stamps the ctx with
    `subagent:<task_id>`; a SkillManageTool created from that ctx captures
    the tag write-once. Mutating the parent's ctx afterwards does NOT change
    the subagent tool's bound tag.
    """
    from unittest.mock import MagicMock

    from nanobot.agent.subagent import SubagentManager
    from nanobot.agent.tools.context import ToolContext
    from nanobot.agent.tools.skill_manage import SkillManageTool
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.base import LLMProvider

    provider = MagicMock(spec=LLMProvider)
    provider.get_default_model.return_value = "test"
    sm = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=MessageBus(),
        model="test",
        max_tool_result_chars=16_000,
    )

    task_id = "abcd1234"
    sub_ctx = sm._build_subagent_tool_context(task_id=task_id)
    assert sub_ctx.provenance_tag == f"subagent:{task_id}"

    skill_tool = SkillManageTool.create(sub_ctx)
    assert skill_tool._provenance_tag_ == f"subagent:{task_id}"

    # Mutating an UNRELATED parent ctx must not bleed in.
    parent_ctx = ToolContext(
        config=None,
        workspace=str(tmp_path),
        provenance_tag="agent",
    )
    parent_ctx.provenance_tag = "agent"
    assert skill_tool._provenance_tag_ == f"subagent:{task_id}"

    # Mutating the SAME ctx after construction also must not bleed (t-07
    # write-once contract).
    sub_ctx.provenance_tag = "agent"
    assert skill_tool._provenance_tag_ == f"subagent:{task_id}"

    # Two distinct task_ids produce two distinct tags on two distinct tools.
    other_ctx = sm._build_subagent_tool_context(task_id="zz999999")
    other_tool = SkillManageTool.create(other_ctx)
    assert other_tool._provenance_tag_ == "subagent:zz999999"
    assert skill_tool._provenance_tag_ == f"subagent:{task_id}"


def test_subagent_runtime_state_is_fresh_and_isolated(tmp_path):
    """Each call to `_make_subagent_runtime_state` returns a NEW instance
    with an empty `_runtime_vars`, and `_build_subagent_tool_context` wires
    it onto ctx so SkillManageTool's rate-cap path uses it (not the parent's
    counter).
    """
    from unittest.mock import MagicMock

    from nanobot.agent.subagent import SubagentManager, _SubagentRuntimeState
    from nanobot.agent.tools.skill_manage import SkillManageTool
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.base import LLMProvider

    provider = MagicMock(spec=LLMProvider)
    provider.get_default_model.return_value = "test"
    sm = SubagentManager(
        provider=provider,
        workspace=tmp_path,
        bus=MessageBus(),
        model="test",
        max_tool_result_chars=16_000,
    )

    rt1 = sm._make_subagent_runtime_state()
    rt2 = sm._make_subagent_runtime_state()
    assert isinstance(rt1, _SubagentRuntimeState)
    assert rt1 is not rt2
    assert rt1._runtime_vars == {}
    rt1._runtime_vars["x"] = 1
    assert rt2._runtime_vars == {}

    sub_ctx = sm._build_subagent_tool_context(task_id="task0001", runtime_state=rt1)
    skill_tool = SkillManageTool.create(sub_ctx)
    assert skill_tool._runtime_state_ is rt1
