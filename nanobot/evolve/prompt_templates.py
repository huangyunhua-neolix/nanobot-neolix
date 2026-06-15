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
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
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
_SAFETY_CONTROL_FIELD_NAMES = frozenset(
    {
        "approval",
        "human_approval",
        "requires_human_approval",
        "review",
        "human_review",
        "sandbox",
        "tool_safety",
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
_PROPOSED_PROTECTED_SAFETY_PHRASES = _PROTECTED_SAFETY_PHRASES
_PROTECTED_WEAKENING_SUBJECTS = (
    "approval",
    "human approval",
    "review",
    "human review",
    "sandbox",
    "sandbox protections",
    "permission",
    "permission checks",
    "prompt",
    "prompted",
    "ask the user",
    "asking the user",
    "user",
    "users",
    "asked",
    "tool safety",
    "tool safety controls",
    "bash",
    "shell",
    "sh",
    "zsh",
    "terminal",
    "command line",
    "subprocess",
    "process",
    "exec",
)
_WEAKENING_PREDICATES = (
    "does not need to",
    "do not need to",
    "do not require",
    "need not",
    "not required",
    "not happen",
    "not enforced",
    "not asked",
    "not prompted",
    "not necessary",
    "unnecessary",
    "optional",
    "not needed",
    "needed",
    "not mandatory",
    "mandatory",
    "may be omitted",
    "can be omitted",
    "omitted",
    "may be skipped",
    "can be skipped",
    "may be bypassed",
    "can be bypassed",
    "may be ignored",
    "can be ignored",
    "no need for",
    "may be waived",
    "waived",
    "discretionary",
    "may be used",
    "use",
    "commands",
    "tool",
    "calls",
    "instead",
    "rather than",
    "directly",
    "prefer",
    "allowed",
    "bypass",
    "via",
)
_SAFETY_CONTROL_FIELD_KEY_TOKENS = (
    "approval",
    "permission",
    "permissions",
    "review",
    "sandbox",
    "sandboxing",
    "safety",
    "safe_execution",
    "tool",
    "tools",
    "allowed_tools",
    "allowedtools",
    "allowed_tool",
    "allow_tools",
    "allowtools",
    "allow_tool",
    "available_tools",
    "availabletools",
    "available_tool",
    "tool_safety",
    "shell",
    "bash",
    "sh",
    "zsh",
    "terminal",
    "command_line",
    "subprocess",
    "process",
)
_SAFETY_CONTROL_FIELD_VALUE_TOKENS = (
    "false",
    "disabled",
    "optional",
    "not required",
    "not_required",
    "unnecessary",
    "none",
    "allow",
    "no",
    "off",
    "yes",
    "enabled",
    "bash",
    "shell",
    "true",
)
_DENIED_WEAKENING_PHRASES = (
    "skip approval",
    "without asking",
    "ignore sandbox",
    "bypass review",
    "apply automatically",
    "use shell instead",
    "hide from user",
    "do not ask the user",
    "proceed without approval",
    "skip human review",
    "no human approval required",
    "disable sandbox",
    "execute untrusted code",
    "human approval is not required",
    "approval is not required",
    "human review is not required",
    "sandbox can be ignored",
    "sandbox is optional",
    "approval can be skipped",
    "review can be bypassed",
    "do not request approval from the user",
    "bypass sandbox",
    "ignore human review",
    "avoid review",
    "approval is optional",
    "no approval needed",
    "never ask the user",
    "skip permission checks",
    "no permission needed",
    "use bash instead",
    "run shell instead",
    "approval not required",
    "human approval not required",
    "human review not required",
    "review not required",
    "no human review required",
    "no sandbox required",
    "sandbox optional",
    "approval unnecessary",
    "review unnecessary",
)
# Local skeleton mapping for safety phrase matching only; this is not a full
# Unicode confusables implementation.
_SAFETY_CONFUSABLE_TRANSLATION = str.maketrans(
    {
        "ɑ": "a",
        "а": "a",
        "α": "a",
        "𝛂": "a",
        "𝛼": "a",
        "𝜶": "a",
        "𝝰": "a",
        "𝞪": "a",
        "ꭤ": "a",
        "Ь": "b",
        "Ƅ": "b",
        "β": "b",
        "ϐ": "b",
        "Ꮟ": "b",
        "ƅ": "b",
        "ϲ": "c",
        "с": "c",
        "ᴄ": "c",
        "ⅽ": "c",
        "ԁ": "d",
        "ժ": "d",
        "ⅾ": "d",
        "е": "e",
        "℮": "e",
        "ε": "e",
        "ҽ": "e",
        "𝛆": "e",
        "𝜀": "e",
        "𝜺": "e",
        "𝝐": "e",
        "𝝴": "e",
        "𝞊": "e",
        "𝞮": "e",
        "ғ": "f",
        "բ": "f",
        "ց": "g",
        "һ": "h",
        "հ": "h",
        "Ꮒ": "h",
        "ᥙ": "h",
        "ı": "i",
        "ɩ": "i",
        "ɪ": "i",
        "і": "i",
        "ι": "i",
        "Ꭵ": "i",
        "ⅰ": "i",
        "ᴋ": "k",
        "к": "k",
        "κ": "k",
        "Ꮶ": "k",
        "ⅼ": "l",
        "ʟ": "l",
        "ӏ": "l",
        "ℓ": "l",
        "ո": "n",
        "п": "n",
        "ᴏ": "o",
        "о": "o",
        "ο": "o",
        "σ": "o",
        "օ": "o",
        "ס": "o",
        "º": "o",
        "ⅿ": "m",
        "м": "m",
        "ᴘ": "p",
        "р": "p",
        "ρ": "p",
        "ϱ": "p",
        "⍴": "p",
        "զ": "p",
        "г": "r",
        "ᴦ": "r",
        "ѕ": "s",
        "ꜱ": "s",
        "ꮪ": "s",
        "τ": "t",
        "т": "t",
        "ᴛ": "t",
        "ս": "u",
        "υ": "y",
        "ν": "v",
        "ѵ": "v",
        "ᴠ": "v",
        "ԝ": "w",
        "ա": "w",
        "х": "x",
        "χ": "x",
        "ҳ": "x",
        "×": "x",
        "у": "y",
        "ү": "y",
        "γ": "y",
        "ʏ": "y",
    }
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
    pending_yaml_key: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        normalized_delimiter_line = _normalize_safety_text(stripped)
        if re.match(r"^(?:---|\.\.\.)(?:\s|#|$)", normalized_delimiter_line):
            return True
        if pending_yaml_key is not None and stripped.startswith(":"):
            return _is_safety_control_field(pending_yaml_key, stripped[1:])
        pending_yaml_key = None
        field_name, separator, field_value = stripped.partition(":")
        if not separator:
            normalized_standalone_key = re.sub(r"[\s-]+", "_", _normalize_field_name(stripped))
            if any(token in normalized_standalone_key for token in _SAFETY_CONTROL_FIELD_KEY_TOKENS):
                pending_yaml_key = normalized_standalone_key
            continue
        normalized_field_name = _normalize_field_name(field_name)
        normalized_key = re.sub(r"[\s-]+", "_", normalized_field_name)
        if (
            normalized_field_name in _FRONTMATTER_FIELD_NAMES
            or normalized_key in _SAFETY_CONTROL_FIELD_NAMES
            or _is_safety_control_field(normalized_key, field_value)
            or _contains_non_ascii_letter_or_symbol(field_name)
        ):
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
            if _insertion_in_empty_region(baseline_start, editable_regions):
                changed_lines.add(baseline_start)
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


def _line_allowed_by_regions(line_number: int, regions: list[EditableRegion]) -> bool:
    return any(
        region.start_line <= line_number <= region.end_line
        or (region.start_line > region.end_line and line_number == region.start_line)
        for region in regions
    )


def _insertion_in_empty_region(baseline_start: int, regions: list[EditableRegion]) -> bool:
    return any(
        region.start_line > region.end_line and baseline_start == region.start_line
        for region in regions
    )


def _regions_touched_by_lines(
    changed_line_numbers: list[int], regions: list[EditableRegion]
) -> list[EditableRegion]:
    return [
        region
        for region in regions
        if any(_line_allowed_by_regions(line_number, [region]) for line_number in changed_line_numbers)
    ]


def _has_region_span_bypass(
    baseline_regions: list[EditableRegion],
    proposed_regions: list[EditableRegion],
    baseline_body: str,
    proposed_body: str,
) -> bool:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    for baseline_region, proposed_region in zip(baseline_regions, proposed_regions, strict=True):
        proposed_region_text = _region_text(proposed_body, proposed_region).splitlines()
        for baseline_line in _region_text(baseline_body, baseline_region).splitlines():
            if not baseline_line or baseline_line in proposed_region_text:
                continue
            baseline_outside_count = _line_count_outside_region(
                baseline_lines,
                baseline_region,
                baseline_line,
            )
            proposed_outside_count = _line_count_outside_region(
                proposed_lines,
                proposed_region,
                baseline_line,
            )
            if proposed_outside_count > baseline_outside_count:
                return True
    return False


def _line_count_outside_region(lines: list[str], region: EditableRegion, target_line: str) -> int:
    region_lines = set(_region_line_numbers(region, len(lines)))
    return sum(
        1
        for line_number, line in enumerate(lines)
        if line == target_line and line_number not in region_lines
    )


def _region_line_numbers(region: EditableRegion, line_count: int) -> list[int]:
    if region.end_line < region.start_line:
        return []
    return list(range(region.start_line, min(region.end_line + 1, line_count)))


def _normalize_safety_text(text: str, *, map_confusables: bool = False) -> str:
    decomposed = unicodedata.normalize("NFKD", text).casefold()
    if map_confusables:
        decomposed = decomposed.translate(_SAFETY_CONFUSABLE_TRANSLATION)
    stripped_characters: list[str] = []
    for character in decomposed:
        category = unicodedata.category(character)
        if character == "\u00ad" or category == "Cf" or category.startswith("M"):
            continue
        if category == "Cc":
            if character.isspace():
                stripped_characters.append(" ")
            continue
        stripped_characters.append(character)
    normalized = unicodedata.normalize("NFKC", "".join(stripped_characters))
    return " ".join(normalized.split())


def _alnum_compact_safety_text(text: str, *, map_confusables: bool = False) -> str:
    normalized = _normalize_safety_text(text, map_confusables=map_confusables)
    return "".join(character for character in normalized if character.isalnum())


def _contains_non_ascii_letter_or_symbol(text: str) -> bool:
    return any(
        ord(character) > 127 and unicodedata.category(character)[0] in {"L", "S"}
        for character in text
    )


def _contains_phrase(
    text: str,
    phrases: tuple[str, ...],
    *,
    map_confusables: bool = False,
) -> bool:
    normalized = _normalize_safety_text(text, map_confusables=map_confusables)
    compact_normalized = "".join(normalized.split())
    alnum_compact_normalized = _alnum_compact_safety_text(
        text,
        map_confusables=map_confusables,
    )
    return any(
        normalized_phrase in normalized
        or "".join(normalized_phrase.split()) in compact_normalized
        or _alnum_compact_safety_text(
            normalized_phrase,
            map_confusables=map_confusables,
        )
        in alnum_compact_normalized
        for phrase in phrases
        if (normalized_phrase := _normalize_safety_text(phrase, map_confusables=map_confusables))
    )


def _contains_marker_like_editable_boundary(text: str) -> bool:
    compact = _alnum_compact_safety_text(text)
    return any(
        token in compact
        for token in (
            "evolveprompteditablestart",
            "evolveprompteditableend",
            "prompteditablestart",
            "prompteditableend",
        )
    )


def _normalize_field_name(field_name: str) -> str:
    normalized = _normalize_safety_text(field_name, map_confusables=True).strip()
    while normalized[:1] in {"-", "?"}:
        normalized = normalized[1:].strip()
    return normalized.strip("'\"")


def _is_safety_control_field(normalized_key: str, field_value: str) -> bool:
    key_has_safety_control = any(
        token in normalized_key for token in _SAFETY_CONTROL_FIELD_KEY_TOKENS
    )
    if not key_has_safety_control:
        return False
    normalized_value = _normalize_safety_text(field_value, map_confusables=True)
    if not normalized_value:
        return True
    normalized_value_key = re.sub(r"[\s-]+", "_", normalized_value)
    return any(
        token in normalized_value or token in normalized_value_key
        for token in _SAFETY_CONTROL_FIELD_VALUE_TOKENS
    )


def _contains_weakening_pattern(text: str) -> bool:
    normalized = _normalized_weakening_text(text)
    return _contains_tool_enablement(normalized) or _contains_safety_control_weakening(normalized)


def _normalized_weakening_text(text: str) -> str:
    return (
        _normalize_safety_text(text, map_confusables=True)
        .replace("’", "'")
        .replace("`", "'")
        .replace("´", "'")
        .replace(" isn't ", " is not ")
        .replace(" aren't ", " are not ")
        .replace(" doesn't ", " does not ")
        .replace(" don't ", " do not ")
        .replace(" needn't ", " need not ")
        .replace(" should not be ", " not ")
        .replace(" must not be ", " not ")
        .replace(" will not be ", " not ")
    )


def _contains_tool_enablement(normalized: str) -> bool:
    tool_subjects = (
        "bash",
        "shell",
        " sh",
        "/bin/sh",
        "zsh",
        "terminal",
        "command line",
        "subprocess",
        "process",
        "exec",
    )
    tool_predicates = (
        "use",
        "run",
        "execute",
        "call",
        "invoke",
        "open",
        "spawn",
        "launch",
        "prefer",
        "may be used",
        "can be used",
        "directly",
        "instead",
        "commands",
        "tool",
        "calls",
    )
    return any(subject in normalized for subject in tool_subjects) and any(
        predicate in normalized for predicate in tool_predicates
    )


def _contains_safety_control_weakening(normalized: str) -> bool:
    safety_subjects = (
        "approval",
        "human approval",
        "review",
        "human review",
        "sandbox",
        "sandbox protections",
        "permission",
        "permission checks",
        "tool safety",
        "tool safety controls",
    )
    user_prompt_subjects = (
        "ask the user",
        "asking the user",
        "user",
        "users",
        "asked",
        "prompt",
        "prompted",
    )
    safety_predicates = (
        "does not need to",
        "do not need to",
        "do not require",
        "need not",
        "not required",
        "not happen",
        "not enforced",
        "not asked",
        "not prompted",
        "not necessary",
        "unnecessary",
        "optional",
        "not needed",
        "needed",
        "not mandatory",
        "mandatory",
        "may be omitted",
        "can be omitted",
        "omitted",
        "may be skipped",
        "can be skipped",
        "may be bypassed",
        "can be bypassed",
        "may be ignored",
        "can be ignored",
        "no need for",
        "may be waived",
        "waived",
        "discretionary",
        "disable",
        "disabled",
        "removed",
        "can be removed",
        "bypass",
        "bypassed",
        "allowed",
        "without",
    )
    user_prompt_predicates = (
        "do not ask",
        "do not prompt",
        "does not need to be asked",
        "never ask",
        "never be asked",
        "should never be asked",
        "must never be asked",
        "should not need to be asked",
        "not asked",
        "not prompted",
        "need not be asked",
        "not required",
        "optional",
        "without asking",
    )
    return (
        any(subject in normalized for subject in safety_subjects)
        and any(predicate in normalized for predicate in safety_predicates)
    ) or (
        any(subject in normalized for subject in user_prompt_subjects)
        and any(predicate in normalized for predicate in user_prompt_predicates)
    )


def _contains_phrase_tokens_in_order(
    text: str,
    phrases: tuple[str, ...],
    *,
    map_confusables: bool = False,
) -> bool:
    tokens = re.findall(r"\w+", _normalize_safety_text(text, map_confusables=map_confusables))
    if not tokens:
        return False
    for phrase in phrases:
        phrase_tokens = re.findall(
            r"\w+",
            _normalize_safety_text(phrase, map_confusables=map_confusables),
        )
        if phrase_tokens and _tokens_appear_in_order(tokens, phrase_tokens):
            return True
    return False


def _tokens_appear_in_order(tokens: list[str], phrase_tokens: list[str]) -> bool:
    phrase_index = 0
    for token in tokens:
        if phrase_index >= len(phrase_tokens):
            return True
        if token != phrase_tokens[phrase_index]:
            continue
        phrase_index += 1
    return phrase_index == len(phrase_tokens)


def _region_text(body: str, region: EditableRegion) -> str:
    lines = body.splitlines()
    if region.end_line < region.start_line:
        return ""
    return "\n".join(lines[region.start_line : region.end_line + 1])


def _proposed_region_texts(
    *,
    baseline_body: str,
    proposed_body: str,
    regions: list[EditableRegion],
) -> list[str]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    region_indices = range(len(regions))
    proposed_region_lines: dict[int, list[str]] = {index: [] for index in region_indices}
    for tag, baseline_start, baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            line_pairs = zip(
                range(baseline_start, baseline_end),
                proposed_lines[proposed_start:proposed_end],
                strict=True,
            )
            for baseline_line_number, line in line_pairs:
                for index, region in enumerate(regions):
                    if region.start_line <= baseline_line_number <= region.end_line:
                        proposed_region_lines[index].append(line)
            continue
        anchored_regions = {
            index
            for index, region in enumerate(regions)
            if baseline_start <= region.end_line and baseline_end > region.start_line
        }
        if not anchored_regions and baseline_start == baseline_end:
            anchor_lines = _insertion_anchor_lines(baseline_start, len(baseline_lines))
            anchored_regions = {
                index
                for index, region in enumerate(regions)
                if any(_line_allowed_by_regions(line_number, [region]) for line_number in anchor_lines)
                or _insertion_in_empty_region(baseline_start, [region])
            }
        for index in anchored_regions:
            proposed_region_lines[index].extend(proposed_lines[proposed_start:proposed_end])
    return [
        "\n".join(proposed_region_lines[index])
        for index in region_indices
        if proposed_region_lines[index]
    ]


def _proposed_changed_text(proposed_body: str, baseline_body: str) -> str:
    proposed_lines = proposed_body.splitlines()
    changed_lines = _changed_proposed_line_numbers(baseline_body, proposed_body)
    return "\n".join(proposed_lines[line_number] for line_number in changed_lines)


def _changed_text_contexts(proposed_body: str, changed_line_numbers: list[int]) -> list[str]:
    proposed_lines = proposed_body.splitlines()
    return [
        "\n".join(
            proposed_lines[context_line_number]
            for context_line_number in range(line_number - 2, line_number + 3)
            if 0 <= context_line_number < len(proposed_lines)
            and proposed_lines[context_line_number].strip() not in {_EDITABLE_START, _EDITABLE_END}
        )
        for line_number in changed_line_numbers
    ]


def _changed_proposed_line_numbers(baseline_body: str, proposed_body: str) -> list[int]:
    baseline_lines = baseline_body.splitlines()
    proposed_lines = proposed_body.splitlines()
    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=proposed_lines,
        autojunk=False,
    )
    changed_lines: set[int] = set()
    for tag, _baseline_start, _baseline_end, proposed_start, proposed_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed_lines.update(range(proposed_start, proposed_end))
    return sorted(changed_lines)


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
            if (
                marker[0] == fence_marker
                and len(marker) >= fence_length
                and line[fence_match.end() :].strip(" \t") == ""
            ):
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
        proposed_safety_texts = [
            *proposed_region_texts,
            "\n".join(all_proposed_region_texts),
            *_changed_text_contexts(proposed_body, proposed_changed_line_numbers),
        ]
        if _contains_non_ascii_letter_or_symbol(proposed_changed_text) or any(
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
