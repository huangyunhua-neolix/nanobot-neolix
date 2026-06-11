"""M2 §4.3 step 2/3 — `edit` and `patch` verb pipelines."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.agent.tools.skill_manage import SkillManageTool


@pytest.fixture
def tool_factory(tmp_workspace: Path):
    def _factory(*, telemetry=None):
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
            telemetry=telemetry,
            provenance_tag="agent",
            config=config,
            runtime_state=None,
        )

    return _factory


async def _create(tool, name: str, body: str = "original") -> None:
    r = await tool.execute(verb="create", name=name, body=body)
    assert r["ok"], r


@pytest.mark.asyncio
async def test_edit_replaces_body(tmp_workspace: Path, tool_factory) -> None:
    tool = tool_factory()
    await _create(tool, "thing", body="old body\n")
    r = await tool.execute(verb="edit", name="thing", body="brand new\n")
    assert r["ok"] is True
    skill_md = tmp_workspace / "skills" / "agent" / "thing" / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert "brand new" in text
    assert "old body" not in text
    assert "last_patched_at:" in text
    assert "patched_by: agent" in text


@pytest.mark.asyncio
async def test_patch_single_replace(tmp_workspace: Path, tool_factory) -> None:
    tool = tool_factory()
    await _create(tool, "thing", body="hello world\n")
    r = await tool.execute(
        verb="patch", name="thing", search="world", replace="moon"
    )
    assert r["ok"] is True
    text = (
        tmp_workspace / "skills" / "agent" / "thing" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "hello moon" in text


@pytest.mark.asyncio
async def test_patch_search_not_found(
    tmp_workspace: Path, tool_factory
) -> None:
    tool = tool_factory()
    await _create(tool, "thing", body="hello world\n")
    r = await tool.execute(
        verb="patch", name="thing", search="xyzzy", replace="?"
    )
    assert r["ok"] is False
    assert r["error_code"] == "search_not_found"


@pytest.mark.asyncio
async def test_patch_search_ambiguous(
    tmp_workspace: Path, tool_factory
) -> None:
    tool = tool_factory()
    await _create(tool, "thing", body="hi hi hi\n")
    r = await tool.execute(verb="patch", name="thing", search="hi", replace="x")
    assert r["ok"] is False
    assert r["error_code"] == "search_ambiguous"


@pytest.mark.asyncio
@pytest.mark.parametrize("tier_name,seed_dir", [
    ("user", "skills"),       # workspace/skills/<name>/
    ("builtin", "_builtin"),  # builtin (tested via monkeypatch below)
])
async def test_edit_tier_locked_for_non_agent(
    tmp_workspace: Path, tmp_path: Path, tool_factory, monkeypatch,
    tier_name: str, seed_dir: str,
) -> None:
    """Edit on a non-agent-tier shadow MUST reject with `tier_locked`."""
    from nanobot.agent import skills as skills_mod

    name = "shared-skill"
    if tier_name == "user":
        d = tmp_workspace / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            "---\norigin: user\n---\nuser-body\n", encoding="utf-8"
        )
    else:  # builtin
        builtin_root = tmp_path / "builtin_skills_for_test"
        (builtin_root / name).mkdir(parents=True)
        (builtin_root / name / "SKILL.md").write_text(
            "---\norigin: builtin\n---\nb\n", encoding="utf-8"
        )
        monkeypatch.setattr(skills_mod, "BUILTIN_SKILLS_DIR", builtin_root)

    tool = tool_factory()
    r = await tool.execute(verb="edit", name=name, body="hijack")
    assert r["ok"] is False
    assert r["error_code"] == "tier_locked"


@pytest.mark.asyncio
async def test_edit_bumps_telemetry_patch_kind(
    tmp_workspace: Path, tool_factory
) -> None:
    telem = SkillTelemetry(tmp_workspace)
    tool = tool_factory(telemetry=telem)
    await _create(tool, "tracked", body="x")
    # Reconcile so the telemetry has an entry to bump.
    telem.reconcile([{
        "name": "tracked",
        "effective_origin": "agent",
        "shadowed_origins": [],
        "path": str(tmp_workspace / "skills/agent/tracked/SKILL.md"),
    }])
    snap_before = telem.snapshot()
    patches_before = snap_before["entries"]["tracked"]["patches"]
    r = await tool.execute(verb="edit", name="tracked", body="y")
    assert r["ok"], r
    snap_after = telem.snapshot()
    assert snap_after["entries"]["tracked"]["patches"] == patches_before + 1
