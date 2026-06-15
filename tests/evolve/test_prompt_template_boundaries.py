from __future__ import annotations

import pytest

from nanobot.evolve.prompt_templates import PromptTemplateBoundaryError, parse_editable_regions


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


def test_parse_editable_regions_requires_strict_backtick_fence_closer() -> None:
    body = (
        "```markdown\n"
        "```not a closing fence\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "ignored\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "```\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "real\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )

    regions = parse_editable_regions(body)

    assert [(region.start_line, region.end_line) for region in regions] == [(7, 7)]


def test_parse_editable_regions_requires_strict_tilde_fence_closer() -> None:
    body = (
        "~~~markdown\n"
        "~~~not a closing fence\n"
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


def test_parse_editable_regions_treats_four_space_fence_as_literal_text() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "    ```\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "Outside mutable\n"
        "```\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )

    regions = parse_editable_regions(body)

    assert [(region.start_line, region.end_line) for region in regions] == [(2, 3)]


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


