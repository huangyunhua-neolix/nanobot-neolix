"""M2 §3.7 path-escape defense — symlink + `..` rejects.

These tests exercise the open-with-O_NOFOLLOW + resolve-against-root
defense in the create / edit / patch / delete pipelines.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from nanobot.agent.tools.skill_manage import SkillManageTool


def _tool(tmp_workspace: Path) -> SkillManageTool:
    config = type(
        "_Cfg", (), {
            "skill_manage": type(
                "_SM", (), {
                    "max_mutations_per_turn": 1000,
                    "max_body_bytes": 65536,
                    "max_agent_skills": 200,
                    "max_description_len": 280,
                },
            )(),
        },
    )()
    return SkillManageTool(
        workspace=tmp_workspace,
        telemetry=None,
        provenance_tag="agent",
        config=config,
        runtime_state=None,
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only path-escape test")
@pytest.mark.asyncio
async def test_skill_md_symlink_to_outside_workspace(
    tmp_workspace: Path, tmp_path: Path
) -> None:
    """A symlinked SKILL.md pointing outside the workspace MUST be rejected."""
    skill_dir = tmp_workspace / "skills" / "agent" / "evil"
    skill_dir.mkdir(parents=True)
    target = tmp_path / "external_target.md"
    target.write_text("---\norigin: agent\n---\nstolen\n", encoding="utf-8")
    os.symlink(target, skill_dir / "SKILL.md")
    tool = _tool(tmp_workspace)
    r = await tool.execute(verb="edit", name="evil", body="hijack")
    assert r["ok"] is False
    assert r["error_code"] == "path_escape"


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only path-escape test")
@pytest.mark.asyncio
async def test_lock_file_symlink_rejected(
    tmp_workspace: Path, tmp_path: Path
) -> None:
    """A symlinked <name>/.lock pointing outside MUST be rejected by
    fd_file_lock (O_NOFOLLOW + is_symlink precheck)."""
    skill_dir = tmp_workspace / "skills" / "agent" / "evil2"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\norigin: agent\n---\nbody\n", encoding="utf-8"
    )
    external = tmp_path / "fake.lock"
    external.write_bytes(b"")
    os.symlink(external, skill_dir / ".lock")
    tool = _tool(tmp_workspace)
    r = await tool.execute(verb="edit", name="evil2", body="x")
    assert r["ok"] is False
    assert r["error_code"] == "path_escape"


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only path-escape test")
@pytest.mark.asyncio
async def test_create_lock_symlink_rejected(
    tmp_workspace: Path, tmp_path: Path
) -> None:
    """A symlinked <skills/agent>/.create.lock MUST be rejected on create."""
    agent_root = tmp_workspace / "skills" / "agent"
    agent_root.mkdir(parents=True)
    external = tmp_path / "fake_create.lock"
    external.write_bytes(b"")
    os.symlink(external, agent_root / ".create.lock")
    tool = _tool(tmp_workspace)
    r = await tool.execute(verb="create", name="ok", body="hi")
    assert r["ok"] is False
    assert r["error_code"] == "path_escape"


@pytest.mark.asyncio
async def test_name_dot_dot_blocked(tmp_workspace: Path) -> None:
    """`..` MUST be rejected at the name-validator layer; never reaches paths."""
    tool = _tool(tmp_workspace)
    r = await tool.execute(verb="create", name="..", body="x")
    assert r["ok"] is False
    assert r["error_code"] == "invalid_name"
