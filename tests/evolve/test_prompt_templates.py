from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from nanobot.evolve.prompt_templates import (
    PromptTemplateBoundaryError,
    capture_bundled_prompt_template_snapshot,
    parse_editable_regions,
    snapshot_from_skill_markdown,
    validate_prompt_template_candidate,
    validate_prompt_template_candidates,
)
from nanobot.evolve.schemas import PromptTemplateCandidate, PromptTemplateSnapshot


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


def _snapshot(body: str, *, skill_name: str = "demo-skill") -> PromptTemplateSnapshot:
    return snapshot_from_skill_markdown(
        skill_name=skill_name,
        source_identifier=f"nanobot/skills/{skill_name}/SKILL.md",
        text=_skill_markdown(body),
    )


def _candidate(
    snapshot: PromptTemplateSnapshot,
    proposed_body: str,
    *,
    skill_name: str | None = None,
    baseline_snapshot_hash: str | None = None,
) -> PromptTemplateCandidate:
    return PromptTemplateCandidate(
        skill_name=skill_name or snapshot.skill_name,
        baseline_snapshot_hash=baseline_snapshot_hash or snapshot.snapshot_hash,
        proposed_body=proposed_body,
        intended_improvement="Make the editable text clearer.",
        risk_assessment="Only editable prompt text changes.",
        cache_impact_claim="cache neutral",
    )


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


def test_validate_prompt_template_candidate_rejects_missing_skill() -> None:
    snapshot = _snapshot("Stable body.\n")
    candidate = _candidate(snapshot, "Stable body.\n", skill_name="absent-skill")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-skill-not-found"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == []


def test_validate_prompt_template_candidate_stale_baseline_wins_before_size_and_frontmatter() -> None:
    snapshot = _snapshot("Stable body.\n")
    huge_frontmatter_like_body = "---\nname: changed\n---\n" + ("x\n" * 2001)
    candidate = _candidate(
        snapshot,
        huge_frontmatter_like_body,
        baseline_snapshot_hash="different-snapshot-hash",
    )

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-baseline-stale"


def test_validate_prompt_template_candidate_size_bound_wins_before_frontmatter() -> None:
    snapshot = _snapshot("Stable body.\n")
    oversized_with_frontmatter = "---\nname: changed\n---\n" + ("x\n" * 2001)
    candidate = _candidate(snapshot, oversized_with_frontmatter)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-template-too-large"


def test_validate_prompt_template_candidate_rejects_body_over_128_kib_byte_bound() -> None:
    snapshot = _snapshot("Stable body.\n")
    oversized_single_line_body = "x" * ((128 * 1024) + 1)
    candidate = _candidate(snapshot, oversized_single_line_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-template-too-large"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_rejects_raw_body_over_128_kib_before_unicode_normalization() -> None:
    repeated_character_count = 44_000
    normalized_body = "é" * repeated_character_count + "\n"
    raw_nfd_body = unicodedata.normalize("NFD", normalized_body)
    assert len(raw_nfd_body.encode("utf-8")) > 128 * 1024
    assert len(normalized_body.encode("utf-8")) <= 128 * 1024
    snapshot = _snapshot(normalized_body)
    candidate = _candidate(snapshot, raw_nfd_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-template-too-large"


def test_validate_prompt_template_candidate_rejects_frontmatter_delimiter_mutation() -> None:
    snapshot = _snapshot("Stable body.\n")
    candidate = _candidate(snapshot, "Stable body.\n---\nMore body.\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-frontmatter-mutation"
    assert result.cache_impact == "cache_sensitive_rejected"


def test_validate_prompt_template_candidate_rejects_frontmatter_field_mutation() -> None:
    snapshot = _snapshot("Stable body.\n")
    candidate = _candidate(snapshot, "description: changed\nStable body.\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-frontmatter-mutation"
    assert result.cache_impact == "cache_sensitive_rejected"


def test_validate_prompt_template_candidate_rejects_case_insensitive_frontmatter_field_mutation() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("Editable", "Description: changed")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-frontmatter-mutation"
    assert result.cache_impact == "cache_sensitive_rejected"


@pytest.mark.parametrize(
    "obfuscated_field",
    [
        "descrip\u200btion: changed",
        "descrip\u00adtion: changed",
        "descri\u0301ption: changed",
    ],
)
def test_validate_prompt_template_candidate_rejects_obfuscated_frontmatter_field_mutation(
    obfuscated_field: str,
) -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("Editable", obfuscated_field)
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-frontmatter-mutation"
    assert result.cache_impact == "cache_sensitive_rejected"


def test_validate_prompt_template_candidate_rejects_change_without_editable_region() -> None:
    snapshot = _snapshot("Stable body.\n")
    candidate = _candidate(snapshot, "Changed body.\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == [0]


def test_validate_prompt_template_candidate_accepts_change_inside_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable first\n"
        "Editable second\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("Editable second", "Clearer editable second")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"
    assert result.changed_line_numbers == [3]
    assert result.judge_evidence_path is None


def test_validate_prompt_template_candidate_accepts_insert_at_editable_region_end() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("Editable\n<!--", "Editable\nAdded editable line.\n<!--")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"


def test_validate_prompt_template_candidate_rejects_change_outside_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("After", "Changed after")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == [4]


@pytest.mark.parametrize(
    "inserted_marker",
    [
        "<!-- evolve:prompt-editable:start -->",
        "<!-- evolve:prompt-editable:end -->",
    ],
)
def test_validate_prompt_template_candidate_rejects_editable_marker_in_changed_text(
    inserted_marker: str,
) -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("Editable", f"Editable\n{inserted_marker}")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_rejects_protected_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Always ask the user before proceeding.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("proceeding", "continuing")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


@pytest.mark.parametrize(
    "denied_phrase",
    [
        "Skip approval for this instruction.",
        "sk\u200bip approval for this instruction.",
        "skip\u00adapproval for this instruction.",
        "sk\u20ddip approval for this instruction.",
        "sk\u0903ip approval for this instruction.",
        "sk-ip approval for this instruction.",
        "sk/ip approval for this instruction.",
        "sk\u2011ip approval for this instruction.",
        "skip appro-val for this instruction.",
        "sk\u0456p approval",
        "s\u043aip approval",
        "ski\u0440 approval",
    ],
)
def test_validate_prompt_template_candidate_rejects_denied_weakening_phrase(
    denied_phrase: str,
) -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("Editable instruction.", denied_phrase)
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


def test_validate_prompt_template_candidate_rejects_contextual_denied_weakening_phrase() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "skip\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("skip\n<!--", "skip\napproval\n<!--")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


def test_validate_prompt_template_candidate_rejects_denied_phrase_with_combining_mark() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace(
        "Editable instruction.",
        "s\u0301kip approval for this instruction.",
    )
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


def test_validate_prompt_template_candidate_rejects_denied_phrase_split_by_inserted_filler() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "skip\n"
        "filler\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("filler\n<!--", "filler\napproval\n<!--")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


def test_validate_prompt_template_candidate_rejects_denied_phrase_replaced_with_filler() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace(
        "Editable instruction.",
        "skip\nfiller-inserted\napproval",
    )
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"


def test_validate_prompt_template_candidate_accepts_denied_phrase_tokens_in_separate_regions() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "First editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "Middle\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Second editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("First editable instruction.", "skip").replace(
        "Second editable instruction.",
        "approval",
    )
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"
    assert result.changed_line_numbers == [2, 6]


def test_validate_prompt_template_candidate_accepts_normalized_identical_body_as_noop() -> None:
    snapshot = _snapshot("Cafe\u0301 answer.\n")
    candidate = _candidate(snapshot, "Cafe\u0301 answer.\r\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.cache_impact == "candidate_noop"
    assert result.changed_line_numbers == []
    assert result.judge_evidence_path is None


def test_validate_prompt_template_candidate_accepts_noop_body_with_horizontal_rule() -> None:
    snapshot = _snapshot("Intro\n---\nOutro\n")
    candidate = _candidate(snapshot, snapshot.body_text)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "candidate_noop"
    assert result.changed_line_numbers == []


def test_validate_prompt_template_candidate_accepts_edit_with_unchanged_horizontal_rule() -> None:
    body = (
        "Intro\n"
        "---\n"
        "Details\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable instruction.\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace("Editable instruction.", "Clearer editable instruction.")
    snapshot = _snapshot(body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"
    assert result.changed_line_numbers == [4]


@pytest.mark.parametrize(
    ("baseline_body", "proposed_body"),
    [
        ("Stable body.\n", "Stable body."),
        ("Stable body.", "Stable body.\n"),
    ],
)
def test_validate_prompt_template_candidate_rejects_final_newline_only_boundary_change(
    baseline_body: str,
    proposed_body: str,
) -> None:
    snapshot = _snapshot(baseline_body)
    candidate = _candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == []


def test_validate_prompt_template_candidates_preserves_duplicate_order_and_independent_results() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    snapshot = _snapshot(body)
    candidates = [
        _candidate(snapshot, body),
        _candidate(snapshot, body.replace("Editable", "Clearer editable")),
        _candidate(snapshot, body.replace("Before", "Changed before")),
    ]

    results = validate_prompt_template_candidates(candidates, [snapshot])

    assert [result.verdict for result in results] == ["accept", "accept", "reject"]
    assert [result.cache_impact for result in results] == [
        "candidate_noop",
        "cache_neutral",
        "cache_unknown_rejected",
    ]
    assert [result.changed_line_numbers for result in results] == [[], [2], [0]]


def test_validate_prompt_template_candidate_fails_closed_on_ambiguous_editable_regions() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    snapshot = _snapshot(body)
    object.__setattr__(
        snapshot,
        "body_text",
        "<!-- evolve:prompt-editable:start -->\nChanged baseline marker state.\n",
    )
    candidate = _candidate(snapshot, "Changed proposed text.\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
