from __future__ import annotations

import difflib
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nanobot.evolve.schemas import (
    PromptTemplateCandidate,
    PromptTemplateSnapshot,
    PromptTemplateValidationResult,
)

_EDITABLE_START = "<!-- evolve:prompt-editable:start -->"
_EDITABLE_END = "<!-- evolve:prompt-editable:end -->"
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_MAX_PROMPT_TEMPLATE_BODY_BYTES = 128 * 1024
_MAX_PROMPT_TEMPLATE_BODY_LINES = 2_000
_FRONTMATTER_FIELD_NAMES = frozenset(
    {
        "name",
        "description",
        "origin",
        "created_by",
        "created_at",
        "evolved_from_run",
        "evolved_at",
        "parent_skill_hash",
        "optimizer_name",
        "optimizer_version",
    }
)
_PROTECTED_SAFETY_PHRASES = (
    "permission",
    "approval",
    "confirm",
    "ask the user",
    "human approval",
    "sandbox",
    "safe execution",
    "do not execute",
    "never execute",
    "untrusted code",
    "human review",
    "review artifact",
    "pr-only",
    "pull request",
    "do not apply",
    "manual review",
    "narrow tool",
    "structured tool",
    "prefer read",
    "prefer search",
    "avoid shell",
    "avoid exec",
    "do not modify",
    "no runtime",
    "not applied",
    "do not write",
    "live prompt",
)
_DENIED_WEAKENING_PHRASES = (
    "skip approval",
    "without asking",
    "ignore sandbox",
    "bypass review",
    "apply automatically",
    "use shell instead",
    "hide from user",
)
_DEFAULT_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parents[2] / "nanobot" / "skills"


class PromptTemplateBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class EditableRegion:
    start_line: int
    end_line: int


def _normalize_body_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text.removeprefix("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe(child) for child in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str]:
    normalized = _normalize_body_text(text)
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return {}, normalized
    frontmatter_text = normalized[4:end]
    body = normalized[end + 5 :]
    parsed = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(parsed, dict):
        raise PromptTemplateBoundaryError("frontmatter must be a YAML mapping")
    return parsed, body


def _line_count(text: str) -> int:
    if text == "":
        return 0
    return len(text.splitlines())


def _body_too_large(body: str) -> bool:
    return (
        len(body.encode("utf-8")) > _MAX_PROMPT_TEMPLATE_BODY_BYTES
        or _line_count(body) > _MAX_PROMPT_TEMPLATE_BODY_LINES
    )


def _has_frontmatter_mutation(body: str) -> bool:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped == "---":
            return True
        field_name, separator, _field_value = stripped.partition(":")
        if separator and field_name.strip().casefold() in _FRONTMATTER_FIELD_NAMES:
            return True
    return False


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


def _changed_baseline_line_numbers(
    baseline_body: str,
    proposed_body: str,
    editable_regions: list[EditableRegion] | None = None,
) -> list[int]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    changed_lines: set[int] = set()
    for tag, baseline_start, baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if baseline_start != baseline_end:
            changed_lines.update(range(baseline_start, baseline_end))
            continue
        anchor_lines = _insertion_anchor_lines(baseline_start, len(baseline_lines))
        if editable_regions is not None:
            editable_anchor_lines = [
                line_number
                for line_number in anchor_lines
                if _line_in_regions(line_number, editable_regions)
            ]
            if editable_anchor_lines:
                changed_lines.update(editable_anchor_lines)
                continue
        if anchor_lines:
            changed_lines.add(anchor_lines[0])
        elif proposed_start != proposed_end:
            changed_lines.add(0)
    return sorted(changed_lines)


def _insertion_anchor_lines(baseline_start: int, baseline_line_count: int) -> list[int]:
    anchor_lines: list[int] = []
    if baseline_start < baseline_line_count:
        anchor_lines.append(baseline_start)
    if baseline_start > 0:
        anchor_lines.append(baseline_start - 1)
    return anchor_lines


def _line_in_regions(line_number: int, regions: list[EditableRegion]) -> bool:
    return any(region.start_line <= line_number <= region.end_line for region in regions)


def _regions_touched_by_lines(
    changed_line_numbers: list[int], regions: list[EditableRegion]
) -> list[EditableRegion]:
    return [
        region
        for region in regions
        if any(region.start_line <= line_number <= region.end_line for line_number in changed_line_numbers)
    ]


def _normalize_safety_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    stripped = "".join(
        character
        for character in normalized
        if character != "\u00ad" and unicodedata.category(character) not in {"Cc", "Cf"}
    )
    return " ".join(stripped.split())


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = _normalize_safety_text(text)
    compact_normalized = "".join(normalized.split())
    return any(
        normalized_phrase in normalized
        or "".join(normalized_phrase.split()) in compact_normalized
        for phrase in phrases
        if (normalized_phrase := _normalize_safety_text(phrase))
    )


def _region_text(body: str, region: EditableRegion) -> str:
    lines = body.splitlines()
    if region.end_line < region.start_line:
        return ""
    return "\n".join(lines[region.start_line : region.end_line + 1])


def _proposed_changed_text(proposed_body: str, baseline_body: str) -> str:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    changed_chunks: list[str] = []
    for tag, _baseline_start, _baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_chunks.extend(proposed_lines[proposed_start:proposed_end])
    return "\n".join(changed_chunks)


def parse_editable_regions(body: str) -> list[EditableRegion]:
    lines = body.splitlines()
    fence_marker: str | None = None
    fence_length = 0
    active_start: int | None = None
    regions: list[EditableRegion] = []
    for index, line in enumerate(lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                fence_length = len(marker)
                continue
            if marker[0] == fence_marker and len(marker) >= fence_length:
                fence_marker = None
                fence_length = 0
                continue
        if fence_marker is not None:
            continue
        stripped = line.strip()
        if stripped == _EDITABLE_START:
            if active_start is not None:
                raise PromptTemplateBoundaryError("nested editable region marker")
            active_start = index + 1
            continue
        if stripped == _EDITABLE_END:
            if active_start is None:
                raise PromptTemplateBoundaryError("unbalanced editable region marker")
            regions.append(EditableRegion(start_line=active_start, end_line=index - 1))
            active_start = None
    if active_start is not None:
        raise PromptTemplateBoundaryError("unbalanced editable region marker")
    return regions


def snapshot_from_skill_markdown(
    *,
    skill_name: str,
    source_identifier: str,
    text: str,
) -> PromptTemplateSnapshot:
    frontmatter, body = _parse_skill_markdown(text)
    body = _normalize_body_text(body)
    regions = parse_editable_regions(body)
    frontmatter_hash = _hash_json(frontmatter)
    body_hash = _hash_text(body)
    cache_key_hash = _hash_text(str(frontmatter.get("description", "")))
    body_line_count = _line_count(body)
    snapshot_payload = {
        "skill_name": skill_name,
        "source_kind": "bundled",
        "source_identifier": source_identifier,
        "frontmatter_hash": frontmatter_hash,
        "body_hash": body_hash,
        "cache_key_hash": cache_key_hash,
        "editable_region_count": len(regions),
        "body_line_count": body_line_count,
    }
    snapshot_hash = _hash_json(snapshot_payload)
    return PromptTemplateSnapshot(
        skill_name=skill_name,
        source_kind="bundled",
        source_identifier=source_identifier,
        frontmatter_hash=frontmatter_hash,
        body_hash=body_hash,
        cache_key_hash=cache_key_hash,
        editable_region_count=len(regions),
        body_line_count=body_line_count,
        snapshot_hash=snapshot_hash,
        body_text=body,
    )


def capture_bundled_prompt_template_snapshot(
    bundled_skills_dir: Path = _DEFAULT_BUNDLED_SKILLS_DIR,
) -> list[PromptTemplateSnapshot]:
    if not bundled_skills_dir.exists():
        return []
    snapshots: list[PromptTemplateSnapshot] = []
    for path in sorted(bundled_skills_dir.glob("*/SKILL.md"), key=lambda item: item.parent.name):
        skill_name = path.parent.name
        source_identifier = f"nanobot/skills/{skill_name}/SKILL.md"
        snapshots.append(
            snapshot_from_skill_markdown(
                skill_name=skill_name,
                source_identifier=source_identifier,
                text=path.read_text(encoding="utf-8"),
            )
        )
    return snapshots


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

    proposed_body = _normalize_body_text(candidate.proposed_body)
    if _body_too_large(proposed_body):
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-template-too-large",
            reason="Proposed prompt template body exceeds the hard size bounds.",
            cache_impact="cache_unknown_rejected",
        )
    baseline_body = baseline.body_text
    if proposed_body == baseline_body:
        return _accept_prompt_result(
            candidate=candidate,
            cache_impact="candidate_noop",
        )
    if _has_frontmatter_mutation(_proposed_changed_text(proposed_body, baseline_body)):
        return _reject_prompt_result(
            candidate=candidate,
            reason_code="prompt-frontmatter-mutation",
            reason="Proposed prompt template body includes frontmatter-like content.",
            cache_impact="cache_sensitive_rejected",
        )

    try:
        editable_regions = parse_editable_regions(baseline_body)
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
        if any(not _line_in_regions(line_number, editable_regions) for line_number in changed_line_numbers):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-cache-boundary-unknown",
                reason="Proposed prompt template changes a line outside explicit editable regions.",
                cache_impact="cache_unknown_rejected",
                changed_line_numbers=changed_line_numbers,
            )
        touched_regions = _regions_touched_by_lines(changed_line_numbers, editable_regions)
        if any(
            _contains_phrase(_region_text(baseline_body, region), _PROTECTED_SAFETY_PHRASES)
            for region in touched_regions
        ):
            return _reject_prompt_result(
                candidate=candidate,
                reason_code="prompt-safety-regression",
                reason="Proposed prompt template changes an editable region containing protected safety language.",
                cache_impact="cache_neutral",
                changed_line_numbers=changed_line_numbers,
            )
        if _contains_phrase(
            _proposed_changed_text(proposed_body, baseline_body),
            _DENIED_WEAKENING_PHRASES,
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
