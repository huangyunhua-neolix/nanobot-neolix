"""M2 §4.2 — ToolContext.provenance_tag default + assignability."""
from __future__ import annotations


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
