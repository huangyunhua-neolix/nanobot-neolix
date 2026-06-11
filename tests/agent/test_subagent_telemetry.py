"""Tests for SubagentManager telemetry propagation (M1 Task C2)."""

from pathlib import Path

from nanobot.agent.skills_telemetry import SkillTelemetry


def test_subagent_manager_holds_telemetry(tmp_path: Path) -> None:
    from nanobot.agent.subagent import SubagentManager
    telem = SkillTelemetry(tmp_path)
    mgr = SubagentManager(
        provider=object(),
        workspace=tmp_path,
        bus=None,
        max_tool_result_chars=10_000,
        model="m",
        telemetry=telem,
    )
    assert mgr.telemetry is telem


def test_subagent_build_prompt_uses_shared_telemetry(tmp_path: Path) -> None:
    """Constructed SkillsLoader inside _build_subagent_prompt MUST share telemetry."""
    from nanobot.agent.subagent import SubagentManager
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndescription: f\n---\nbody"
    )
    telem = SkillTelemetry(tmp_path)
    mgr = SubagentManager(
        provider=object(),
        workspace=tmp_path,
        bus=None,
        max_tool_result_chars=10_000,
        model="m",
        telemetry=telem,
    )
    mgr._build_subagent_prompt(workspace=tmp_path)
    snap = telem.snapshot()
    # foo was bumped via build_skills_summary inside subagent prompt construction.
    # Other packaged builtin skills may also have entries; that's OK.
    assert snap["entries"]["foo"]["views"] == 1
