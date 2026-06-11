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
