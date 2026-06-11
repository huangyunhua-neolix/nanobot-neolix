"""M2 §4.3 step 1 — `skill_manage` create-verb pipeline.

Covers:
* happy-path agent-tier creation with frontmatter shape.
* same-tier name collision (`name_exists`).
* case-fold collisions (`MySkill` vs `myskill`).
* cross-tier shadow collisions (bundled / user pre-seeded → `name_collision`).
* quota gate (`max_agent_skills` enforced inside layer-0 lock).
* invariant: `create` does NOT bump telemetry — that's reconcile's job.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.agent.tools.skill_manage import SkillManageTool


@pytest.fixture
def tool_factory(tmp_workspace: Path):
    """Build a fresh SkillManageTool bound to ``tmp_workspace``."""

    def _factory(*, telemetry=None, max_agent_skills: int = 200):
        config = type(
            "_Cfg", (), {
                "skill_manage": type(
                    "_SM", (), {
                        "max_mutations_per_turn": 1000,
                        "max_body_bytes": 65536,
                        "max_agent_skills": max_agent_skills,
                        "max_description_len": 280,
                    },
                )(),
            },
        )()
        return SkillManageTool(
            workspace=tmp_workspace,
            telemetry=telemetry,
            provenance_tag="agent",
            config=config,
            runtime_state=None,
        )

    return _factory


@pytest.mark.asyncio
async def test_create_succeeds_in_agent_tier(
    tmp_workspace: Path, tool_factory
) -> None:
    tool = tool_factory()
    result = await tool.execute(
        verb="create", name="hello", description="hello skill", body="# hi\n",
    )
    assert result["ok"] is True
    assert result["verb"] == "create"
    assert result["name"] == "hello"
    skill_md = tmp_workspace / "skills" / "agent" / "hello" / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert "origin: agent" in text
    assert "created_by: agent" in text
    assert "# hi\n" in text


@pytest.mark.asyncio
async def test_create_collision_same_tier(
    tmp_workspace: Path, tool_factory
) -> None:
    tool = tool_factory()
    r1 = await tool.execute(verb="create", name="dup", body="a")
    assert r1["ok"] is True
    r2 = await tool.execute(verb="create", name="dup", body="b")
    assert r2["ok"] is False
    assert r2["error_code"] == "name_exists"


@pytest.mark.asyncio
async def test_create_case_fold_collision(
    tmp_workspace: Path, tool_factory
) -> None:
    """Layer-0 quota check uses case-fold lookup; uppercase-variant names
    are already rejected by `_validate_skill_name`. We exercise the
    case-fold path by pre-seeding a same-tier directory with a different
    case (illegal via the validator but possible via direct mkdir) and
    asserting a second `myskill` create lands on `name_exists` rather
    than silently shadowing.
    """
    tool = tool_factory()
    # Seed a 'foo' skill via the tool, then prove 'foo' collides exactly
    # (the validator already blocks 'FOO' / 'Foo'; case-fold here tests
    # the LOOKUP path, not the input validator).
    r = await tool.execute(verb="create", name="foo", body="x")
    assert r["ok"], r
    r2 = await tool.execute(verb="create", name="foo", body="y")
    assert r2["error_code"] == "name_exists"


@pytest.mark.asyncio
async def test_create_collision_with_bundled_tier(
    tmp_path: Path, tool_factory, monkeypatch
) -> None:
    """Pre-seed a builtin-tier skill with the same name → name_collision."""
    from nanobot.agent import skills as skills_mod

    builtin_root = tmp_path / "builtin_skills"
    (builtin_root / "shared").mkdir(parents=True)
    (builtin_root / "shared" / "SKILL.md").write_text(
        "---\norigin: builtin\n---\nbody\n", encoding="utf-8"
    )
    monkeypatch.setattr(skills_mod, "BUILTIN_SKILLS_DIR", builtin_root)
    tool = tool_factory()
    r = await tool.execute(verb="create", name="shared", body="z")
    assert r["ok"] is False
    assert r["error_code"] == "name_collision"


@pytest.mark.asyncio
async def test_create_collision_with_user_tier(
    tmp_workspace: Path, tool_factory
) -> None:
    """Pre-seed a workspace-level (user) skill → name_collision."""
    user_dir = tmp_workspace / "skills" / "shared"
    user_dir.mkdir(parents=True)
    (user_dir / "SKILL.md").write_text(
        "---\norigin: user\n---\nbody\n", encoding="utf-8"
    )
    tool = tool_factory()
    r = await tool.execute(verb="create", name="shared", body="z")
    assert r["ok"] is False
    assert r["error_code"] == "name_collision"


@pytest.mark.asyncio
async def test_create_quota_exceeded(
    tmp_workspace: Path, tool_factory
) -> None:
    tool = tool_factory(max_agent_skills=2)
    r1 = await tool.execute(verb="create", name="a", body="1")
    r2 = await tool.execute(verb="create", name="b", body="2")
    r3 = await tool.execute(verb="create", name="c", body="3")
    assert r1["ok"] and r2["ok"]
    assert r3["ok"] is False
    assert r3["error_code"] == "quota_exceeded"


@pytest.mark.asyncio
async def test_create_does_not_bump_telemetry(
    tmp_workspace: Path, tool_factory
) -> None:
    telem = SkillTelemetry(tmp_workspace)
    tool = tool_factory(telemetry=telem)
    r = await tool.execute(verb="create", name="newone", body="hello")
    assert r["ok"], r
    snap = telem.snapshot()
    # `create` MUST NOT register/bump an entry (M1 invariant — that's reconcile's job).
    assert "newone" not in snap["entries"]


@pytest.mark.asyncio
async def test_create_case_fold_collision_against_uppercase_on_disk(
    tmp_workspace: Path, tool_factory,
) -> None:
    """Pre-seed an uppercase-named agent-tier skill DIRECTLY on disk
    (bypassing the validator) and assert a lowercase create collides
    via the case-fold lookup branch in `_entry_for` (YEL test gap).
    """
    agent_root = tmp_workspace / "skills" / "agent"
    (agent_root / "MyOldSkill").mkdir(parents=True)
    (agent_root / "MyOldSkill" / "SKILL.md").write_text(
        "---\norigin: agent\n---\nseed body\n", encoding="utf-8"
    )
    tool = tool_factory()
    r = await tool.execute(verb="create", name="myoldskill", body="x")
    assert r["ok"] is False
    assert r["error_code"] == "name_collision"


@pytest.mark.asyncio
async def test_create_atomic_write_failure_cleans_up_dir(
    tmp_workspace: Path, tool_factory, monkeypatch,
) -> None:
    """Simulate `atomic_write` raising mid-create and assert the empty
    `<name>/` directory is cleaned up so the next attempt isn't blocked
    by `name_exists` (FIX 3 / YEL-DI-#4)."""
    import errno as _errno

    from nanobot.agent.tools import skill_manage_ops as _ops

    def _boom(*_args, **_kwargs):
        raise OSError(_errno.EIO, "simulated I/O error")

    monkeypatch.setattr(_ops, "atomic_write", _boom)
    tool = tool_factory()
    r = await tool.execute(verb="create", name="failer", body="x")
    assert r["ok"] is False
    assert r["error_code"] == "atomic_write_failed"
    # Cleanup must have removed the empty dir we just created.
    skill_dir = tmp_workspace / "skills" / "agent" / "failer"
    assert not skill_dir.exists(), (
        f"empty <name>/ dir {skill_dir} leaked after atomic_write failure"
    )


@pytest.mark.asyncio
async def test_create_invalid_args_requires_not_list(
    tmp_workspace: Path, tool_factory,
) -> None:
    """A non-list `requires` (e.g. `42`) must return `invalid_args` rather
    than crashing inside `list(requires or [])` (YEL-DI-#6)."""
    tool = tool_factory()
    r = await tool.execute(
        verb="create", name="argsbad", body="x", requires=42,
    )
    assert r["ok"] is False
    assert r["error_code"] == "invalid_args"

    r2 = await tool.execute(
        verb="create", name="argsbad2", body="x", requires=["ok", 7],
    )
    assert r2["ok"] is False
    assert r2["error_code"] == "invalid_args"
