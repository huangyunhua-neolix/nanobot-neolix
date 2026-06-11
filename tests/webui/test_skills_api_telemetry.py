"""Regression test pinning the WebUI-must-not-bump-telemetry invariant (M1 Task C6)."""

from pathlib import Path


def test_webui_payload_does_not_create_or_modify_telemetry_file(tmp_path: Path) -> None:
    from nanobot.webui.skills_api import webui_skill_detail_payload, webui_skills_payload

    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")

    for _ in range(10):
        webui_skills_payload(tmp_path)
        webui_skill_detail_payload(tmp_path, "foo")

    # Telemetry file MUST NOT have been created by WebUI calls (telemetry=None)
    assert not (tmp_path / "skills" / ".telemetry.json").exists()
