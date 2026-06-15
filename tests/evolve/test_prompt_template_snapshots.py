from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from nanobot.evolve.prompt_templates import (
    PromptTemplateBoundaryError,
    capture_bundled_prompt_template_snapshot,
    snapshot_from_skill_markdown,
)
from tests.evolve.prompt_template_test_helpers import skill_markdown, write_bundled_skill


def test_snapshot_from_skill_markdown_hashes_are_stable_across_frontmatter_key_order() -> None:
    body = "Use concise answers.\n"
    first = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=skill_markdown(body),
    )
    reordered = (
        "---\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "created_by: tests\n"
        "origin: bundled\n"
        "description: Demo skill\n"
        "name: demo-skill\n"
        "---\n"
        f"{body}"
    )
    second = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=reordered,
    )

    assert second.frontmatter_hash == first.frontmatter_hash
    assert second.body_hash == first.body_hash
    assert second.cache_key_hash == first.cache_key_hash
    assert second.snapshot_hash == first.snapshot_hash


def test_snapshot_from_skill_markdown_normalizes_bom_crlf_and_unicode() -> None:
    decomposed = "Cafe\u0301 answer.\r\n"
    composed = unicodedata.normalize("NFC", decomposed).replace("\r\n", "\n")
    with_bom = "\ufeff" + skill_markdown(decomposed)

    snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=with_bom,
    )

    assert snapshot.body_text == composed
    assert snapshot.body_line_count == 1


def test_snapshot_from_skill_markdown_rejects_non_mapping_frontmatter() -> None:
    text = "---\n- not\n- a\n- mapping\n---\nBody\n"

    with pytest.raises(PromptTemplateBoundaryError, match="frontmatter must be a YAML mapping"):
        snapshot_from_skill_markdown(
            skill_name="demo-skill",
            source_identifier="nanobot/skills/demo-skill/SKILL.md",
            text=text,
        )


def test_snapshot_from_skill_markdown_uses_lenient_frontmatter_after_yaml_error() -> None:
    body = "Use concise answers.\n"
    invalid_yaml_text = "---\ndescription: Demo skill: invalid yaml\nname: demo-skill\n---\n"
    text = f"{invalid_yaml_text}{body}"

    snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=text,
    )

    valid_equivalent = (
        "---\n"
        'description: "Demo skill: invalid yaml"\n'
        "name: demo-skill\n"
        "---\n"
        f"{body}"
    )
    expected_snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=valid_equivalent,
    )

    assert snapshot.body_text == body
    assert snapshot.body_hash == expected_snapshot.body_hash
    assert snapshot.cache_key_hash == expected_snapshot.cache_key_hash
    assert snapshot.frontmatter_hash == expected_snapshot.frontmatter_hash


def test_snapshot_from_skill_markdown_treats_missing_closing_frontmatter_as_body() -> None:
    text = "---\ndescription: Demo skill\nBody\n"

    snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=text,
    )

    assert snapshot.body_text == text
    assert snapshot.cache_key_hash == snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text="Body\n",
    ).cache_key_hash


def test_capture_bundled_prompt_template_snapshot_enumerates_sorted_skills(tmp_path: Path) -> None:
    bundled_root = tmp_path / "nanobot" / "skills"
    write_bundled_skill(bundled_root, "zeta", "Z body.\n")
    write_bundled_skill(bundled_root, "alpha", "A body.\n")
    workspace_skill = tmp_path / "skills" / "agent" / "ignored" / "SKILL.md"
    workspace_skill.parent.mkdir(parents=True)
    workspace_skill.write_text(skill_markdown("Ignored.\n"), encoding="utf-8")

    snapshots = capture_bundled_prompt_template_snapshot(bundled_skills_dir=bundled_root)

    assert [item.skill_name for item in snapshots] == ["alpha", "zeta"]
    assert all(item.source_kind == "bundled" for item in snapshots)
    assert snapshots[0].source_identifier == "nanobot/skills/alpha/SKILL.md"


def test_capture_bundled_prompt_template_snapshot_empty_root_returns_empty_list(tmp_path: Path) -> None:
    snapshots = capture_bundled_prompt_template_snapshot(
        bundled_skills_dir=tmp_path / "nanobot" / "skills"
    )

    assert snapshots == []


def test_snapshot_counts_editable_regions() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )

    snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=skill_markdown(body),
    )

    assert snapshot.editable_region_count == 1
    assert snapshot.body_line_count == 4

