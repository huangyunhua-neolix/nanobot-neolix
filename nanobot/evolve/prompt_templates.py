from __future__ import annotations

from nanobot.evolve.prompt_template_boundaries import (
    EditableRegion,
    PromptTemplateBoundaryError,
    parse_editable_regions,
)
from nanobot.evolve.prompt_template_boundaries import (
    changed_baseline_line_numbers as _changed_baseline_line_numbers,
)
from nanobot.evolve.prompt_template_boundaries import (
    changed_proposed_line_numbers as _changed_proposed_line_numbers,
)
from nanobot.evolve.prompt_template_boundaries import (
    changed_text_contexts as _changed_text_contexts,
)
from nanobot.evolve.prompt_template_boundaries import (
    has_region_span_bypass as _has_region_span_bypass,
)
from nanobot.evolve.prompt_template_boundaries import (
    line_allowed_by_regions as _line_allowed_by_regions,
)
from nanobot.evolve.prompt_template_boundaries import (
    proposed_changed_text as _proposed_changed_text,
)
from nanobot.evolve.prompt_template_boundaries import (
    proposed_region_texts as _proposed_region_texts,
)
from nanobot.evolve.prompt_template_boundaries import region_text as _region_text
from nanobot.evolve.prompt_template_boundaries import (
    regions_touched_by_lines as _regions_touched_by_lines,
)
from nanobot.evolve.prompt_template_safety import (
    DENIED_WEAKENING_PHRASES as _DENIED_WEAKENING_PHRASES,
)
from nanobot.evolve.prompt_template_safety import (
    PROPOSED_PROTECTED_SAFETY_PHRASES as _PROPOSED_PROTECTED_SAFETY_PHRASES,
)
from nanobot.evolve.prompt_template_safety import (
    PROTECTED_SAFETY_PHRASES as _PROTECTED_SAFETY_PHRASES,
)
from nanobot.evolve.prompt_template_safety import (
    contains_marker_like_editable_boundary as _contains_marker_like_editable_boundary,
)
from nanobot.evolve.prompt_template_safety import (
    contains_non_ascii_letter_or_symbol as _contains_non_ascii_letter_or_symbol,
)
from nanobot.evolve.prompt_template_safety import contains_phrase as _contains_phrase
from nanobot.evolve.prompt_template_safety import (
    contains_phrase_tokens_in_order as _contains_phrase_tokens_in_order,
)
from nanobot.evolve.prompt_template_safety import (
    contains_weakening_pattern as _contains_weakening_pattern,
)
from nanobot.evolve.prompt_template_safety import (
    has_frontmatter_mutation as _has_frontmatter_mutation,
)
from nanobot.evolve.prompt_template_snapshots import (
    capture_bundled_prompt_template_snapshot,
    snapshot_from_skill_markdown,
)
from nanobot.evolve.prompt_template_snapshots import line_count as _line_count
from nanobot.evolve.prompt_template_snapshots import normalize_body_text as _normalize_body_text
from nanobot.evolve.schemas import (
    PromptTemplateCandidate,
    PromptTemplateSnapshot,
    PromptTemplateValidationResult,
)

__all__ = [
    "EditableRegion",
    "PromptTemplateBoundaryError",
    "capture_bundled_prompt_template_snapshot",
    "parse_editable_regions",
    "snapshot_from_skill_markdown",
    "validate_prompt_template_candidate",
    "validate_prompt_template_candidates",
]

_MAX_PROMPT_TEMPLATE_BODY_BYTES = 128 * 1024
_MAX_PROMPT_TEMPLATE_BODY_LINES = 2_000


def _body_too_large(body: str) -> bool:
    return (
        len(body.encode("utf-8")) > _MAX_PROMPT_TEMPLATE_BODY_BYTES
        or _line_count(body) > _MAX_PROMPT_TEMPLATE_BODY_LINES
    )


def _reject_prompt_result(
    *,
    candidate: PromptTemplateCandidate,
    reason_code: str,
    reason: str,
    cache_impact: str,
    changed_line_numbers: list[int] | None = None,
) -> PromptTemplateValidationResult:
    return PromptTemplateValidationResult(
        skill_name=candidate.skill_name,
        baseline_snapshot_hash=candidate.baseline_snapshot_hash,
        verdict="reject",
        cache_impact=cache_impact,
        reason_code=reason_code,
        reason=reason,
        changed_line_numbers=sorted(set(changed_line_numbers or [])),
        judge_evidence_path=None,
    )


def _accept_prompt_result(
    *,
    candidate: PromptTemplateCandidate,
    cache_impact: str,
    changed_line_numbers: list[int] | None = None,
) -> PromptTemplateValidationResult:
    return PromptTemplateValidationResult(
        skill_name=candidate.skill_name,
        baseline_snapshot_hash=candidate.baseline_snapshot_hash,
        verdict="accept",
        cache_impact=cache_impact,
        changed_line_numbers=sorted(set(changed_line_numbers or [])),
        judge_evidence_path=None,
    )


def validate_prompt_template_candidate(
    candidate: PromptTemplateCandidate,
    snapshot: list[PromptTemplateSnapshot],
) -> PromptTemplateValidationResult:
    baseline = next((item for item in snapshot if item.skill_name == candidate.skill_name), None)
    if baseline is None:
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-skill-not-found",
            reason="No prompt template snapshot exists for the candidate skill.",
            cache_impact="cache_unknown_rejected",
        )
    if baseline.snapshot_hash != candidate.baseline_snapshot_hash:
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-baseline-stale",
            reason="Candidate baseline snapshot hash does not match the current snapshot.",
            cache_impact="cache_unknown_rejected",
        )

    if _body_too_large(candidate.proposed_body):
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-template-too-large",
            reason="Proposed prompt template body exceeds the hard size bounds.",
            cache_impact="cache_unknown_rejected",
        )
    proposed_body = _normalize_body_text(candidate.proposed_body)
    baseline_body = baseline.body_text
    if proposed_body == baseline_body:
        return _accept_prompt_result(
            candidate=candidate,
            cache_impact="candidate_noop",
        )

    proposed_changed_text = _proposed_changed_text(proposed_body, baseline_body)
    if _has_frontmatter_mutation(proposed_changed_text):
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-frontmatter-mutation",
            reason="Proposed prompt template body includes frontmatter-like content.",
            cache_impact="cache_sensitive_rejected",
        )

    try:
        editable_regions = parse_editable_regions(baseline_body)
        proposed_regions = parse_editable_regions(proposed_body)
        if len(proposed_regions) != len(editable_regions):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes editable region markers.",
                cache_impact="cache_unknown_rejected",
            )

        proposed_changed_line_numbers = _changed_proposed_line_numbers(baseline_body, proposed_body)

        if _contains_marker_like_editable_boundary(proposed_changed_text):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes editable region markers.",
                cache_impact="cache_unknown_rejected",
            )

        changed_line_numbers = _changed_baseline_line_numbers(
            baseline_body,
            proposed_body,
            editable_regions,
        )
        if not changed_line_numbers:
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes could not be mapped to baseline lines.",
                cache_impact="cache_unknown_rejected",
            )
        if any(not _line_allowed_by_regions(line_number, editable_regions) for line_number in changed_line_numbers):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes a line outside explicit editable regions.",
                cache_impact="cache_unknown_rejected",
                changed_line_numbers=changed_line_numbers,
            )
        if any(not _line_allowed_by_regions(line_number, proposed_regions) for line_number in proposed_changed_line_numbers):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template places changed text outside explicit editable regions.",
                cache_impact="cache_unknown_rejected",
                changed_line_numbers=changed_line_numbers,
            )
        if _has_region_span_bypass(editable_regions, proposed_regions, baseline_body, proposed_body):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes editable region spans.",
                cache_impact="cache_unknown_rejected",
                changed_line_numbers=changed_line_numbers,
            )
        touched_regions = _regions_touched_by_lines(changed_line_numbers, editable_regions)
        if any(
            _contains_phrase(
                _region_text(baseline_body, region),
                _PROTECTED_SAFETY_PHRASES,
                map_confusables=True,
            )
            or _contains_phrase_tokens_in_order(
                _region_text(baseline_body, region),
                _PROTECTED_SAFETY_PHRASES,
                map_confusables=True,
            )
            for region in touched_regions
        ):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-safety-regression",
                reason="Proposed prompt template changes an editable region containing protected safety language.",
                cache_impact="cache_neutral",
                changed_line_numbers=changed_line_numbers,
            )
        proposed_region_texts = _proposed_region_texts(
            baseline_body=baseline_body,
            proposed_body=proposed_body,
            regions=touched_regions,
        )
        all_proposed_region_texts = _proposed_region_texts(
            baseline_body=baseline_body,
            proposed_body=proposed_body,
            regions=editable_regions,
        )
        joined_all_proposed_regions = "\n".join(all_proposed_region_texts)
        proposed_safety_texts = [
            *proposed_region_texts,
            *_changed_text_contexts(proposed_body, proposed_changed_line_numbers),
        ]
        if any(_has_frontmatter_mutation(text) for text in proposed_region_texts):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-frontmatter-mutation",
                reason="Proposed prompt template body includes frontmatter-like content.",
                cache_impact="cache_sensitive_rejected",
                changed_line_numbers=changed_line_numbers,
            )
        if (
            _contains_non_ascii_letter_or_symbol(proposed_changed_text)
            or _contains_weakening_pattern(joined_all_proposed_regions)
            or _contains_phrase(joined_all_proposed_regions, _DENIED_WEAKENING_PHRASES, map_confusables=True)
            or _contains_phrase_tokens_in_order(
                joined_all_proposed_regions,
                _DENIED_WEAKENING_PHRASES,
                map_confusables=True,
            )
            or any(
                _contains_non_ascii_letter_or_symbol(text)
                or _contains_phrase(text, _PROPOSED_PROTECTED_SAFETY_PHRASES, map_confusables=True)
                or _contains_phrase_tokens_in_order(
                    text,
                    _PROPOSED_PROTECTED_SAFETY_PHRASES,
                    map_confusables=True,
                )
                or _contains_weakening_pattern(text)
                or _contains_phrase(text, _DENIED_WEAKENING_PHRASES, map_confusables=True)
                or _contains_phrase_tokens_in_order(
                    text,
                    _DENIED_WEAKENING_PHRASES,
                    map_confusables=True,
                )
                for text in proposed_safety_texts
            )
        ):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-safety-regression",
                reason="Proposed prompt template introduces denied safety-weakening language.",
                cache_impact="cache_neutral",
                changed_line_numbers=changed_line_numbers,
            )
    except Exception:
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-cache-boundary-unknown",
            reason="Prompt template editable-boundary validation failed closed.",
            cache_impact="cache_unknown_rejected",
        )

    return _accept_prompt_result(
        candidate=candidate,
        cache_impact="cache_neutral",
        changed_line_numbers=changed_line_numbers,
    )


def validate_prompt_template_candidates(
    candidates: list[PromptTemplateCandidate],
    snapshot: list[PromptTemplateSnapshot],
) -> list[PromptTemplateValidationResult]:
    return [validate_prompt_template_candidate(candidate, snapshot) for candidate in candidates]
