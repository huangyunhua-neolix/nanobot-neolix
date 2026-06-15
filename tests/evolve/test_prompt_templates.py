from __future__ import annotations

import unicodedata

import pytest

from nanobot.evolve.prompt_templates import (
    validate_prompt_template_candidate,
    validate_prompt_template_candidates,
)
from tests.evolve.prompt_template_test_helpers import make_candidate, make_snapshot


def test_validate_prompt_template_candidate_rejects_missing_skill() -> None:
    snapshot = make_snapshot("Stable body.\n")
    candidate = make_candidate(snapshot, "Stable body.\n", skill_name="absent-skill")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-skill-not-found"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == []


def test_validate_prompt_template_candidate_stale_baseline_wins_before_size_and_frontmatter() -> None:
    snapshot = make_snapshot("Stable body.\n")
    huge_frontmatter_like_body = "---\nname: changed\n---\n" + ("x\n" * 2001)
    candidate = make_candidate(
        snapshot,
        huge_frontmatter_like_body,
        baseline_snapshot_hash="different-snapshot-hash",
    )

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-baseline-stale"


def test_validate_prompt_template_candidate_size_bound_wins_before_frontmatter() -> None:
    snapshot = make_snapshot("Stable body.\n")
    oversized_with_frontmatter = "---\nname: changed\n---\n" + ("x\n" * 2001)
    candidate = make_candidate(snapshot, oversized_with_frontmatter)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-template-too-large"


def test_validate_prompt_template_candidate_rejects_body_over_128_kib_byte_bound() -> None:
    snapshot = make_snapshot("Stable body.\n")
    oversized_single_line_body = "x" * ((128 * 1024) + 1)
    candidate = make_candidate(snapshot, oversized_single_line_body)

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
    snapshot = make_snapshot(normalized_body)
    candidate = make_candidate(snapshot, raw_nfd_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-template-too-large"


def test_validate_prompt_template_candidate_rejects_change_without_editable_region() -> None:
    snapshot = make_snapshot("Stable body.\n")
    candidate = make_candidate(snapshot, "Changed body.\n")

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
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

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
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"


def test_validate_prompt_template_candidate_rejects_insert_after_empty_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace(
        "<!-- evolve:prompt-editable:end -->\nAfter",
        "<!-- evolve:prompt-editable:end -->\nAdded outside.\nAfter",
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_accepts_insert_inside_empty_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace(
        "<!-- evolve:prompt-editable:end -->",
        "Added editable line.\n<!-- evolve:prompt-editable:end -->",
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.reason_code is None
    assert result.cache_impact == "cache_neutral"


@pytest.mark.parametrize(
    "denied_insert",
    [
        "skip approval",
        "bypass sandbox",
        "ask the user",
        "human approval",
        "sandbox",
        "approval",
        "permission",
    ],
)
def test_validate_prompt_template_candidate_rejects_denied_insert_inside_empty_editable_region(
    denied_insert: str,
) -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace(
        "<!-- evolve:prompt-editable:end -->",
        f"{denied_insert}\n<!-- evolve:prompt-editable:end -->",
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-safety-regression"
    assert result.cache_impact == "cache_neutral"


def test_validate_prompt_template_candidate_prefers_frontmatter_over_boundary_failure() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    proposed_body = body.replace(
        "Editable",
        "description: changed\n<!-- evolve:prompt-editable:start -->",
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-frontmatter-mutation"
    assert result.cache_impact == "cache_sensitive_rejected"


def test_validate_prompt_template_candidate_rejects_unclosed_fence_hiding_proposed_end_marker() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("Editable\n<!--", "Editable\n```\n<!--")
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_rejects_proposed_editable_region_count_change() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = (
        f"{body}"
        "<!-- evolve:prompt-editable:start -->\n"
        "Extra editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


@pytest.mark.parametrize(
    "proposed_body",
    [
        (
            "<!-- evolve:prompt-editable:start -->\n"
            "<!-- evolve:prompt-editable:end -->\n"
            "Editable\n"
            "<!-- evolve:prompt-editable:start -->\n"
            "<!-- evolve:prompt-editable:end -->\n"
        ),
        (
            "<!-- evolve:prompt-editable:start -->\n"
            "A\n"
            "B\n"
            "<!-- evolve:prompt-editable:end -->\n"
            "X\n"
            "<!-- evolve:prompt-editable:start -->\n"
            "<!-- evolve:prompt-editable:end -->\n"
        ),
    ],
)
def test_validate_prompt_template_candidate_rejects_proposed_editable_region_span_change(
    proposed_body: str,
) -> None:
    body = (
        "<!-- evolve:prompt-editable:start -->\n"
        "A\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "X\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "B\n"
        "<!-- evolve:prompt-editable:end -->\n"
    )
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_rejects_change_outside_editable_region() -> None:
    body = (
        "Before\n"
        "<!-- evolve:prompt-editable:start -->\n"
        "Editable\n"
        "<!-- evolve:prompt-editable:end -->\n"
        "After\n"
    )
    proposed_body = body.replace("After", "Changed after")
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == [4]


def test_validate_prompt_template_candidate_rejects_four_space_fence_boundary_expansion() -> None:
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
    proposed_body = body.replace("Outside mutable", "Changed outside")
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
    assert result.changed_line_numbers == [5]


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
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


@pytest.mark.parametrize(
    "inserted_marker",
    [
        "<!-- evolve:prompt-editable:st\u200bart -->",
        "<!-- evolve:prompt-editable:st\u00adart -->",
        "< !-- evolve:prompt-editable:start -->",
        "<!--evolve:prompt-editable:start -->",
        "<!-- evolve:prompt-editable:start -- >",
        "<!- evolve:prompt-editable:start -->",
    ],
)
def test_validate_prompt_template_candidate_rejects_marker_like_editable_boundary_corruption(
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
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"


def test_validate_prompt_template_candidate_accepts_normalized_identical_body_as_noop() -> None:
    snapshot = make_snapshot("Cafe\u0301 answer.\n")
    candidate = make_candidate(snapshot, "Cafe\u0301 answer.\r\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "accept"
    assert result.cache_impact == "candidate_noop"
    assert result.changed_line_numbers == []
    assert result.judge_evidence_path is None


def test_validate_prompt_template_candidate_accepts_noop_body_with_horizontal_rule() -> None:
    snapshot = make_snapshot("Intro\n---\nOutro\n")
    candidate = make_candidate(snapshot, snapshot.body_text)

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
    snapshot = make_snapshot(body)
    candidate = make_candidate(snapshot, proposed_body)

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
    snapshot = make_snapshot(baseline_body)
    candidate = make_candidate(snapshot, proposed_body)

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
    snapshot = make_snapshot(body)
    candidates = [
        make_candidate(snapshot, body),
        make_candidate(snapshot, body.replace("Editable", "Clearer editable")),
        make_candidate(snapshot, body.replace("Before", "Changed before")),
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
    snapshot = make_snapshot(body)
    object.__setattr__(
        snapshot,
        "body_text",
        "<!-- evolve:prompt-editable:start -->\nChanged baseline marker state.\n",
    )
    candidate = make_candidate(snapshot, "Changed proposed text.\n")

    result = validate_prompt_template_candidate(candidate, [snapshot])

    assert result.verdict == "reject"
    assert result.reason_code == "prompt-cache-boundary-unknown"
    assert result.cache_impact == "cache_unknown_rejected"
