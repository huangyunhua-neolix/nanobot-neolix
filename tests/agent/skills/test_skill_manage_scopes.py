"""Scope-expansion tests for SkillManageTool (M2 plan §t-13).

Verifies that ToolLoader auto-discovers SkillManageTool and registers it
under each of the three scopes documented in the plan:

* ``core``     — main agent loop (`AgentRunner`).
* ``subagent`` — `nanobot/agent/subagent.py:214` calls
  `ToolLoader().load(ctx, registry, scope="subagent")`.
* ``memory``   — Dream / memory consolidation registry (the Chinese-language
  spec colloquially calls this "dream scope", but the loader matches the
  literal `"memory"`; see ``filesystem.py`` and ``test_dream_tools.py``).
"""
from __future__ import annotations

import pytest

from nanobot.agent.tools.context import ToolContext
from nanobot.agent.tools.loader import ToolLoader
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.skill_manage import SkillManageTool
from nanobot.config.schema import Config


def _make_ctx(tmp_path) -> ToolContext:
    # SkillManageTool.enabled() requires ``workspace`` to be non-None.
    return ToolContext(config=Config().tools, workspace=str(tmp_path))


def test_skill_manage_declares_core_subagent_memory_scopes():
    # The class-level declaration is the source of truth the loader reads;
    # asserting it directly catches accidental scope removals in PRs that
    # never trigger the loader-driven tests below.
    scopes = SkillManageTool._scopes
    assert "core" in scopes
    assert "subagent" in scopes
    assert "memory" in scopes


@pytest.mark.parametrize("scope", ["core", "subagent", "memory"])
def test_loader_registers_skill_manage_in_scope(tmp_path, scope):
    loader = ToolLoader()
    registry = ToolRegistry()
    ctx = _make_ctx(tmp_path)

    loader.load(ctx, registry, scope=scope)

    assert "skill_manage" in registry.tool_names, (
        f"skill_manage missing from scope={scope!r}; "
        f"tools={sorted(registry.tool_names)}"
    )


def test_loader_skill_manage_excluded_from_unknown_scope(tmp_path):
    """Sanity: a scope literal not in `_scopes` must NOT register the tool."""
    loader = ToolLoader()
    registry = ToolRegistry()
    ctx = _make_ctx(tmp_path)

    loader.load(ctx, registry, scope="this-scope-does-not-exist")

    assert "skill_manage" not in registry.tool_names
