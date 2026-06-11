"""M2 §6.1 / plan task t-12 — Dream → SkillManageTool wiring end-to-end.

These tests pin the three production callers that hand a ``MemoryStore``
instance to the Dream tool registry:

* ``nanobot/agent/context.py`` — ``ContextBuilder.__init__`` constructs the
  ``MemoryStore`` and forwards ``telemetry`` to it.
* ``nanobot/cli/commands.py`` — the cron Dream job calls
  ``store.build_dream_tools()`` on ``agent.context.memory``.
* ``nanobot/command/builtin.py`` — the manual ``/dream`` slash command calls
  ``store.build_dream_tools()`` on ``loop.context.memory``.

A wiring regression in any of those paths would result in either
``MemoryStore.telemetry is None`` or ``SkillManageTool`` not being
registered with ``provenance_tag="dream"``, so newly created skills would
land with the wrong ``created_by`` frontmatter (or the cap-bumps would be
silently dropped).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.agent.tools.skill_manage import SkillManageTool
from nanobot.agent.tools.skill_manage_ops import _parse_skill

# ---------------------------------------------------------------------------
# 1. Functional end-to-end: Dream-tier create writes ``created_by: dream``
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dream_skill_create_records_dream_provenance(tmp_path: Path) -> None:
    """Simulate Dream issuing a ``skill_manage create`` and verify the
    SKILL.md frontmatter records ``created_by: dream``.

    The orchestrator that triggers this is the Dream cron path, but the
    LLM-side mock is irrelevant: we exercise ``build_dream_tools()``
    directly to demonstrate the tool that the Dream runner would receive
    is the one that stamps ``dream`` provenance.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    telemetry = SkillTelemetry(workspace)
    store = MemoryStore(workspace, telemetry=telemetry)

    tools = store.build_dream_tools()
    skill_tool = tools.get("skill_manage")
    assert isinstance(skill_tool, SkillManageTool)
    assert skill_tool._provenance_tag_ == "dream"
    assert skill_tool._telemetry_ is telemetry

    result = await skill_tool.execute(
        verb="create",
        name="dreamt-up",
        description="learnt during dream",
        body="# Dreamt skill\n\nDo the thing.\n",
    )
    assert result["ok"] is True, result

    skill_md = workspace / "skills" / "agent" / "dreamt-up" / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    # Use the same parser the production code uses (skill_manage_ops._parse_skill)
    # so YAML quoting, trailing whitespace, or key ordering changes don't silently
    # break this contract — we want to assert the *parsed value*, not its rendering.
    frontmatter, _body = _parse_skill(text)
    assert frontmatter["created_by"] == "dream"


@pytest.mark.asyncio
async def test_context_builder_threads_telemetry_into_memory_store(
    tmp_path: Path,
) -> None:
    """ContextBuilder must forward its ``telemetry`` to the MemoryStore so
    that ``build_dream_tools()`` inherits the same SkillTelemetry instance
    rather than silently using ``None``.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    telemetry = SkillTelemetry(workspace)
    builder = ContextBuilder(workspace, telemetry=telemetry)

    assert builder.memory.telemetry is telemetry

    tools = builder.memory.build_dream_tools()
    skill_tool = tools.get("skill_manage")
    assert skill_tool is not None
    assert skill_tool._telemetry_ is telemetry
    assert skill_tool._provenance_tag_ == "dream"


def test_memory_store_telemetry_defaults_to_none(tmp_path: Path) -> None:
    """Back-compat: ``MemoryStore`` may be constructed without ``telemetry``
    (e.g. WebUI-only paths that never run Dream). ``build_dream_tools()``
    must still succeed and register a ``SkillManageTool(telemetry=None)``;
    SkillManageTool already tolerates a None telemetry per its WebUI bypass.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = MemoryStore(workspace)
    assert store.telemetry is None

    tools = store.build_dream_tools()
    skill_tool = tools.get("skill_manage")
    assert skill_tool is not None
    assert skill_tool._telemetry_ is None
    assert skill_tool._provenance_tag_ == "dream"


# ---------------------------------------------------------------------------
# 2. Inspection-based: pin the three production caller sites to telemetry
# ---------------------------------------------------------------------------

# Repo root (resolved via this file's location) so the assertions are
# independent of whatever pytest's CWD happens to be.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_text(rel: str) -> str:
    return (_REPO_ROOT / rel).read_text(encoding="utf-8")


def _find_store_attr_chains(rel: str) -> list[str]:
    """Parse ``rel`` and return ``ast.unparse`` of every ``store = <Attribute>``
    assignment found anywhere in the module (including nested closures).

    Substring matching on raw source produces confusing failures on innocuous
    refactors (whitespace, comments, line wrapping); structural AST inspection
    pins the *shape* of the assignment instead.
    """
    tree = ast.parse(_read_text(rel))
    chains: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == "store"):
            continue
        if not isinstance(node.value, ast.Attribute):
            continue
        chains.append(ast.unparse(node.value))
    return chains


def test_context_py_constructs_memory_store_with_telemetry() -> None:
    """``nanobot/agent/context.py`` must construct ``MemoryStore`` with the
    ``telemetry=`` kwarg. Plain ``MemoryStore(workspace)`` without
    ``telemetry`` would silently break the Dream provenance chain.
    """
    text = _read_text("nanobot/agent/context.py")
    # Tolerate spacing / wrapping but require the kwarg explicitly.
    assert re.search(
        r"MemoryStore\([^)]*\btelemetry\s*=", text,
    ), "ContextBuilder must call MemoryStore(..., telemetry=...)"
    # Guard against a regression that drops the kwarg back to bare-positional.
    assert "MemoryStore(workspace)\n" not in text, (
        "Found bare MemoryStore(workspace) — telemetry kwarg was lost"
    )


def test_cli_commands_dream_path_uses_context_memory() -> None:
    """The CLI cron Dream job sources its store from ``agent.context.memory``
    so the telemetry threaded into ContextBuilder reaches build_dream_tools().

    Verified structurally via AST: we look for an ``Assign`` node whose target
    is ``store`` and whose value is the attribute chain ``agent.context.memory``.
    This survives whitespace / comment / wrapping changes but still pins the
    head of the chain (``agent``) and the intermediate node (``context``).
    """
    rel = "nanobot/cli/commands.py"
    chains = _find_store_attr_chains(rel)
    assert "agent.context.memory" in chains, (
        f"Dream CLI job must contain `store = agent.context.memory` "
        f"(carrying telemetry); found store-assignments: {chains!r}"
    )
    # Also confirm build_dream_tools() is invoked on a `store.` somewhere
    # in the module (structural rather than textual).
    tree = ast.parse(_read_text(rel))
    assert any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "build_dream_tools"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "store"
        for n in ast.walk(tree)
    ), "Dream CLI job must call store.build_dream_tools()"


def test_builtin_dream_command_uses_context_memory() -> None:
    """The manual `/dream` command's store must come from
    ``loop.context.memory`` so the AgentLoop's telemetry instance is used.

    Verified structurally via AST (see ``_find_store_attr_chains``).
    """
    rel = "nanobot/command/builtin.py"
    chains = _find_store_attr_chains(rel)
    assert "loop.context.memory" in chains, (
        f"/dream builtin command must contain `store = loop.context.memory` "
        f"(carrying telemetry); found store-assignments: {chains!r}"
    )
    tree = ast.parse(_read_text(rel))
    assert any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "build_dream_tools"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "store"
        for n in ast.walk(tree)
    ), "/dream builtin command must call store.build_dream_tools()"


def test_agent_loop_passes_telemetry_to_context_builder() -> None:
    """Source-of-truth check: AgentLoop owns the SkillTelemetry instance and
    passes it into ContextBuilder. This is the head of the chain that all
    three production callers depend on.
    """
    text = _read_text("nanobot/agent/loop.py")
    assert re.search(
        r"ContextBuilder\([^)]*telemetry\s*=\s*self\.telemetry",
        text,
        re.DOTALL,
    ), "AgentLoop must construct ContextBuilder(..., telemetry=self.telemetry)"
