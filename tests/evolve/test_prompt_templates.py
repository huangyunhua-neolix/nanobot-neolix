from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from nanobot.evolve.prompt_templates import (
    PromptTemplateBoundaryError,
    capture_bundled_prompt_template_snapshot,
    parse_editable_regions,
    snapshot_from_skill_markdown,
)


def _skill_markdown(body: str, *, description: str = "Demo skill") -> str:
    return (
        "---\n"
        "name: demo-skill\n"
        f"description: {description}\n"
        "origin: bundled\n"
        "created_by: tests\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "---\n"
        f"{body}"
    )


def _write_bundled_skill(root: Path, name: str, body: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(_skill_markdown(body), encoding="utf-8")
    return path


def test_snapshot_from_skill_markdown_hashes_are_stable_across_frontmatter_key_order() -> None:
    body = "Use concise answers.\n"
    first = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=_skill_markdown(body),
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
    with_bom = "\ufeff" + _skill_markdown(decomposed)

    snapshot = snapshot_from_skill_markdown(
        skill_name="demo-skill",
        source_identifier="nanobot/skills/demo-skill/SKILL.md",
        text=with_bom,
    )

    assert snapshot.body_text == composed
    assert snapshot.body_line_count == 1


def test_snapshot_from_skill_markdown_rejects_non_mapping_frontmatter() -> None:
    text = "---\n- not\n- a\n- mapping\n---\nBody\n"

    with pytest.raises(PromptTemplateBoundaryError, match="frontmatter"):
        snapshot_from_skill_markdown(
            skill_name="demo-skill",
            source_identifier="nanobot/skills/demo-skill/SKILL.md",
            text=text,
        )


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
    _write_bundled_skill(bundled_root, "zeta", "Z body.\n")
    _write_bundled_skill(bundled_root, "alpha", "A body.\n")
    workspace_skill = tmp_path / "skills" / "agent" / "ignored" / "SKILL.md"
    workspace_skill.parent.mkdir(parents=True)
    workspace_skill.write_text(_skill_markdown("Ignored.\n"), encoding="utf-8")

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
        text=_skill_markdown(body),
    )

    assert snapshot.editable_region_count == 1
    assert snapshot.body_line_count == 4


def test_parse_editable_regions_uses_content_lines_and_excludes_marker_lines() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable 1\n"
        "Editable 2\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )

    regions = parse_editable_regions(body)

    assert [(region.start_line, region.end_line) for region in regions] == [(2, 3)]


def test_parse_editable_regions_ignores_markers_inside_fenced_code() -> None:
    body = (
        "```markdown\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "ignored\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "```\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "real\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )

    regions = parse_editable_regions(body)

    assert [(region.start_line, region.end_line) for region in regions] == [(6, 6)]


def test_parse_editable_regions_ignores_markers_inside_indented_tilde_fences() -> None:
    body = (
        "  ~~~markdown\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "ignored\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "  ~~~\n"
    )

    assert parse_editable_regions(body) == []


def test_parse_editable_regions_ignores_backtick_fences_inside_tilde_fences() -> None:
    body = (
        "~~~markdown\n"
        "```\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "ignored\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "~~~\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "real\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )

    regions = parse_editable_regions(body)

    assert [(region.start_line, region.end_line) for region in regions] == [(7, 7)]


def test_parse_editable_regions_rejects_unbalanced_and_nested_markers() -> None:
    with pytest.raises(PromptTemplateBoundaryError, match="unbalanced"):
        parse_editable_regions("<!-- evolve:prompt-editable:start -->\ntext\n")

    nested = (
        "<!-- evolve:prompt-editable:start -->\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "text\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    with pytest.raises(PromptTemplateBoundaryError, match="nested"):
        parse_editable_regions(nested)

    with pytest.raises(PromptTemplateBoundaryError, match="unbalanced"):
        parse_editable_regions("text\n<!-- evolve:prompt-editable:end -->\n")
