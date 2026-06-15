from __future__ import annotations

import re
import unicodedata

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
PROTECTED_SAFETY_PHRASES = (
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
PROPOSED_PROTECTED_SAFETY_PHRASES = PROTECTED_SAFETY_PHRASES
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
DENIED_WEAKENING_PHRASES = (
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



def normalize_safety_text(text: str, *, map_confusables: bool = False) -> str:
    decomposed = unicodedata.normalize("NFKD", text).casefold()
    if map_confusables:
        decomposed = decomposed.translate(_SAFETY_CONFUSABLE_TRANSLATION)
    stripped_characters: list[str] = []
    for character in decomposed:
        category = unicodedata.category(character)
        if character == "­" or category == "Cf" or category.startswith("M"):
            continue
        if category == "Cc":
            if character.isspace():
                stripped_characters.append(" ")
            continue
        stripped_characters.append(character)
    normalized = unicodedata.normalize("NFKC", "".join(stripped_characters))
    return " ".join(normalized.split())


def alnum_compact_safety_text(text: str, *, map_confusables: bool = False) -> str:
    normalized = normalize_safety_text(text, map_confusables=map_confusables)
    return "".join(character for character in normalized if character.isalnum())


def contains_non_ascii_letter_or_symbol(text: str) -> bool:
    return any(
        ord(character) > 127 and unicodedata.category(character)[0] in {"L", "S"}
        for character in text
    )


def contains_phrase(
    text: str,
    phrases: tuple[str, ...],
    *,
    map_confusables: bool = False,
) -> bool:
    normalized = normalize_safety_text(text, map_confusables=map_confusables)
    compact_normalized = "".join(normalized.split())
    alnum_compact_normalized = alnum_compact_safety_text(
        text,
        map_confusables=map_confusables,
    )
    return any(
        normalized_phrase in normalized
        or "".join(normalized_phrase.split()) in compact_normalized
        or alnum_compact_safety_text(
            normalized_phrase,
            map_confusables=map_confusables,
        )
        in alnum_compact_normalized
        for phrase in phrases
        if (normalized_phrase := normalize_safety_text(phrase, map_confusables=map_confusables))
    )


def contains_marker_like_editable_boundary(text: str) -> bool:
    compact = alnum_compact_safety_text(text)
    return any(
        token in compact
        for token in (
            "evolveprompteditablestart",
            "evolveprompteditableend",
            "prompteditablestart",
            "prompteditableend",
        )
    )


def normalize_field_name(field_name: str) -> str:
    normalized = normalize_safety_text(field_name, map_confusables=True).strip()
    while normalized[:1] in {"-", "?"}:
        normalized = normalized[1:].strip()
    return normalized.strip("'\"")


def has_frontmatter_mutation(body: str) -> bool:
    pending_yaml_key: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        normalized_delimiter_line = normalize_safety_text(stripped)
        if re.match(r"^(?:---|\.\.\.)(?:\s|#|$)", normalized_delimiter_line):
            return True
        if pending_yaml_key is not None and stripped.startswith(":"):
            return is_safety_control_field(pending_yaml_key, stripped[1:])
        pending_yaml_key = None
        field_name, separator, field_value = stripped.partition(":")
        if not separator:
            normalized_standalone_key = re.sub(r"[\s-]+", "_", normalize_field_name(stripped))
            if any(token in normalized_standalone_key for token in _SAFETY_CONTROL_FIELD_KEY_TOKENS):
                pending_yaml_key = normalized_standalone_key
            continue
        normalized_field_name = normalize_field_name(field_name)
        normalized_key = re.sub(r"[\s-]+", "_", normalized_field_name)
        if (
            normalized_field_name in _FRONTMATTER_FIELD_NAMES
            or normalized_key in _SAFETY_CONTROL_FIELD_NAMES
            or is_safety_control_field(normalized_key, field_value)
            or contains_non_ascii_letter_or_symbol(field_name)
        ):
            return True
    return False


def is_safety_control_field(normalized_key: str, field_value: str) -> bool:
    key_has_safety_control = any(
        token in normalized_key for token in _SAFETY_CONTROL_FIELD_KEY_TOKENS
    )
    if not key_has_safety_control:
        return False
    normalized_value = normalize_safety_text(field_value, map_confusables=True)
    if not normalized_value:
        return True
    normalized_value_key = re.sub(r"[\s-]+", "_", normalized_value)
    return any(
        token in normalized_value or token in normalized_value_key
        for token in _SAFETY_CONTROL_FIELD_VALUE_TOKENS
    )


def contains_weakening_pattern(text: str) -> bool:
    normalized = normalized_weakening_text(text)
    return contains_tool_enablement(normalized) or contains_safety_control_weakening(normalized)


def normalized_weakening_text(text: str) -> str:
    return (
        normalize_safety_text(text, map_confusables=True)
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


def contains_tool_enablement(normalized: str) -> bool:
    tokens = re.findall(r"[a-z0-9]+", normalized)
    token_set = set(tokens)
    compact_normalized = alnum_compact_safety_text(normalized)
    tool_subject_tokens = {
        "bash",
        "shell",
        "sh",
        "zsh",
        "terminal",
        "subprocess",
        "subprocesses",
        "exec",
    }
    tool_predicate_tokens = {
        "use",
        "run",
        "execute",
        "call",
        "invoke",
        "invocation",
        "open",
        "spawn",
        "launch",
        "enable",
        "enabled",
        "allow",
        "allowed",
        "prefer",
        "directly",
        "instead",
        "commands",
        "tool",
        "calls",
    }
    process_predicate_tokens = {
        "run",
        "execute",
        "call",
        "invoke",
        "invocation",
        "open",
        "spawn",
        "launch",
        "enable",
        "enabled",
        "allow",
        "allowed",
        "directly",
        "commands",
        "tool",
        "calls",
    }
    subject_found = (
        bool(token_set & tool_subject_tokens)
        or "/bin/sh" in normalized
        or "binsh" in compact_normalized
        or "commandline" in compact_normalized
    )
    predicate_found = bool(token_set & tool_predicate_tokens) or any(
        phrase in normalized for phrase in ("may be used", "can be used")
    )
    process_enablement_found = "process" in token_set and (
        bool(token_set & process_predicate_tokens)
        or "may be used" in normalized
        or "can be used" in normalized
    )
    return (subject_found and predicate_found) or process_enablement_found


def contains_safety_control_weakening(normalized: str) -> bool:
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


def contains_phrase_tokens_in_order(
    text: str,
    phrases: tuple[str, ...],
    *,
    map_confusables: bool = False,
) -> bool:
    tokens = re.findall(r"\w+", normalize_safety_text(text, map_confusables=map_confusables))
    if not tokens:
        return False
    for phrase in phrases:
        phrase_tokens = re.findall(
            r"\w+",
            normalize_safety_text(phrase, map_confusables=map_confusables),
        )
        if phrase_tokens and tokens_appear_in_order(tokens, phrase_tokens):
            return True
    return False


def tokens_appear_in_order(tokens: list[str], phrase_tokens: list[str]) -> bool:
    phrase_index = 0
    for token in tokens:
        if phrase_index >= len(phrase_tokens):
            return True
        if token != phrase_tokens[phrase_index]:
            continue
        phrase_index += 1
    return phrase_index == len(phrase_tokens)
