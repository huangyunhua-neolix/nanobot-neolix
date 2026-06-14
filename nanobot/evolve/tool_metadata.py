"""Deterministic tool contract snapshots for M7 metadata-only tool evolution."""

import hashlib
import json
import re
from copy import deepcopy
from typing import Any, Literal

from nanobot.agent.tools.registry import ToolRegistry
from nanobot.evolve.schemas import (
    ToolContractSnapshot,
    ToolMetadataCandidate,
    ToolMetadataValidationResult,
)


def canonical_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize tool schema to flat shape.

    If the schema has an OpenAI nested shape with dict 'function', return a
    deep copy of schema["function"]. Otherwise return a deep copy of the flat schema.

    Args:
        schema: Tool schema, either OpenAI nested or flat shape.

    Returns:
        Deep copy of the canonicalized schema dict.
    """
    fn = schema.get("function")
    if isinstance(fn, dict):
        return deepcopy(fn)
    return deepcopy(schema)


_DENIED_PERMISSION_PHRASES = (
    "bypass sandbox",
    "ignore sandbox",
    "without permission",
    "without user approval",
    "skip confirmation",
    "avoid approval",
    "disable safety",
    "ignore safety",
    "no need to ask",
    "hide from user",
    "silently execute",
    "without telling",
    "do not mention",
    "conceal",
    "stealth",
    "read secrets",
    "extract token",
    "steal token",
    "dump credentials",
    "read .env",
    "exfiltrate",
    "scan entire filesystem",
    "read all files",
    "crawl home directory",
    "access any website",
    "send to external",
    "upload to pastebin",
)

_BROAD_TOOL_REGRESSION_PATTERNS = (
    re.compile(
        r"\b(?:prefer|use)\s+(?:the\s+)?(?:exec|shell|process execution)\b"
        r".*\b(?:ordinary\s+)?(?:file reads|file read|reads|search|content search|file edits)\b"
    ),
    re.compile(
        r"\b(?:ordinary\s+)?(?:file reads|file read|reads|search|content search|file edits)\b"
        r".*\b(?:prefer|use)\s+(?:the\s+)?(?:exec|shell|process execution)\b"
    ),
    re.compile(r"\buse\s+(?:the\s+)?(?:exec|shell|process execution)\s+as\s+(?:a\s+)?universal\s+workaround\b"),
    re.compile(
        r"\btreat\s+(?:the\s+)?(?:exec|shell|process execution)\s+as\s+(?:a\s+)?universal\s+workaround\s+"
        r"for\s+files,\s+search,\s+web,\s+messages,\s+or\s+schedules\b"
    ),
    re.compile(
        r"\bprefer\s+(?:the\s+)?(?:broad\s+)?(?:exec|shell|process execution)\b"
        r".*\b(?:narrower(?:\s+structured)?|structured)\s+tool\s+exists\b"
    ),
    re.compile(
        r"\buse\s+(?:the\s+)?(?:exec|shell|process execution)\s+as\s+(?:a\s+)?replacement\s+for\s+"
        r"(?:narrower(?:\s+structured)?|structured)\s+tools?\b"
    ),
    re.compile(
        r"\buse\s+(?:the\s+)?(?:exec|shell|process execution)\s+instead\s+of\s+"
        r"(?:narrower(?:\s+structured)?|structured)\s+tools?\b"
    ),
)


def _compute_source_kind(tool_name: str) -> Literal["builtin", "mcp"]:
    """Compute source kind based on tool name prefix.

    Args:
        tool_name: Name of the tool.

    Returns:
        "mcp" if tool_name starts with "mcp_", otherwise "builtin".
    """
    return "mcp" if tool_name.startswith("mcp_") else "builtin"


def schema_hash(
    *,
    tool_name: str,
    description_text: str,
    parameters_schema: dict[str, Any],
) -> str:
    """Compute stable hash of tool contract.

    Hash canonical JSON containing only tool_name, description_text, and
    parameters_schema, serialized with sort_keys=True and compact separators.

    Args:
        tool_name: Name of the tool.
        description_text: Description of the tool.
        parameters_schema: JSON Schema for tool parameters.

    Returns:
        SHA256 hex digest.
    """
    snapshot_data = {
        "tool_name": tool_name,
        "description_text": description_text,
        "parameters_schema": parameters_schema,
    }
    json_str = json.dumps(snapshot_data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def _build_baseline_schema(snapshot: ToolContractSnapshot) -> dict[str, Any]:
    """Build flat baseline schema from a contract snapshot."""
    return {
        "name": snapshot.tool_name,
        "description": snapshot.description_text,
        "parameters": deepcopy(snapshot.parameters_schema),
    }


def _flatten_json_paths(value: Any, path: str = "$", *, include_containers: bool = True) -> dict[str, Any]:
    """Flatten JSON-like data into deterministic path-to-value mapping."""
    paths: dict[str, Any] = {}
    if include_containers or not isinstance(value, (dict, list)):
        paths[path] = value

    if isinstance(value, dict):
        for key in sorted(value):
            paths.update(_flatten_json_paths(value[key], f"{path}.{key}", include_containers=include_containers))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.update(_flatten_json_paths(item, f"{path}[{index}]", include_containers=include_containers))

    return paths


def _diff_json_paths(baseline_value: Any, proposed_value: Any, path: str) -> list[str]:
    """Return deterministic changed leaf or added/removed container paths."""
    if baseline_value == proposed_value:
        return []

    if isinstance(baseline_value, dict) and isinstance(proposed_value, dict):
        changed_paths: list[str] = []
        baseline_keys = set(baseline_value)
        proposed_keys = set(proposed_value)
        for key in sorted(baseline_keys - proposed_keys):
            changed_paths.append(f"{path}.{key}")
        for key in sorted(proposed_keys - baseline_keys):
            changed_paths.append(f"{path}.{key}")
        for key in sorted(baseline_keys & proposed_keys):
            changed_paths.extend(_diff_json_paths(baseline_value[key], proposed_value[key], f"{path}.{key}"))
        return changed_paths

    if isinstance(baseline_value, list) and isinstance(proposed_value, list):
        changed_paths = []
        shared_length = min(len(baseline_value), len(proposed_value))
        for index in range(shared_length):
            changed_paths.extend(
                _diff_json_paths(baseline_value[index], proposed_value[index], f"{path}[{index}]")
            )
        for index in range(shared_length, len(baseline_value)):
            changed_paths.append(f"{path}[{index}]")
        for index in range(shared_length, len(proposed_value)):
            changed_paths.append(f"{path}[{index}]")
        return changed_paths

    return [path]


def _changed_paths(baseline_schema: dict[str, Any], proposed_schema: dict[str, Any]) -> list[str]:
    """Return sorted JSON paths whose values changed between schemas."""
    return sorted(_diff_json_paths(baseline_schema, proposed_schema, "$"))


def _is_allowed_descriptive_path(path: str) -> bool:
    """Return whether path may change in a metadata-only candidate."""
    if path in {"$.description", "$.parameters.description"}:
        return True
    return bool(re.fullmatch(r"\$\.parameters\.properties\.[^.\[\]]+\.(?:description|title)", path))


def _normalize_text(value: str) -> str:
    """Normalize text for deterministic safety phrase checks."""
    return " ".join(value.split()).casefold()


def _has_permission_expansion(text: str) -> bool:
    """Return whether changed descriptive text contains denied safety phrases."""
    normalized_text = _normalize_text(text)
    return any(phrase in normalized_text for phrase in _DENIED_PERMISSION_PHRASES)


def _has_broad_tool_regression(text: str) -> bool:
    """Return whether changed descriptive text promotes broad exec usage."""
    normalized_text = _normalize_text(text)
    return any(pattern.search(normalized_text) for pattern in _BROAD_TOOL_REGRESSION_PATTERNS)


def _reject_result(
    *,
    candidate: ToolMetadataCandidate,
    reason_code: str,
    reason: str,
    changed_paths: list[str] | None = None,
) -> ToolMetadataValidationResult:
    """Build a deterministic rejection result."""
    return ToolMetadataValidationResult(
        tool_name=candidate.tool_name,
        baseline_schema_hash=candidate.baseline_schema_hash,
        verdict="reject",
        reason_code=reason_code,
        reason=reason,
        changed_paths=sorted(changed_paths or []),
    )


def validate_tool_metadata_candidate(
    candidate: ToolMetadataCandidate,
    snapshot: list[ToolContractSnapshot],
) -> ToolMetadataValidationResult:
    """Validate metadata-only schema changes against deterministic safety gates.

    Args:
        candidate: Proposed metadata candidate to validate.
        snapshot: Captured tool contract snapshots for the baseline registry.

    Returns:
        Validation result accepting descriptive-only safe changes or rejecting with
        a deterministic reason code.
    """
    matching_snapshot = next((item for item in snapshot if item.tool_name == candidate.tool_name), None)
    if matching_snapshot is None:
        return _reject_result(
            candidate=candidate,
            reason_code="tool-not-found",
            reason="Candidate target tool is absent from the contract snapshot.",
        )

    if matching_snapshot.schema_hash != candidate.baseline_schema_hash:
        return _reject_result(
            candidate=candidate,
            reason_code="tool-contract-stale",
            reason="Candidate baseline schema hash does not match the contract snapshot.",
        )

    baseline_schema = _build_baseline_schema(matching_snapshot)
    proposed_schema = canonical_tool_schema(candidate.model_dump()["proposed_schema"])
    changed_paths = _changed_paths(baseline_schema, proposed_schema)

    proposed_paths = _flatten_json_paths(proposed_schema)
    invalid_paths = [path for path in changed_paths if not _is_allowed_descriptive_path(path)]
    invalid_paths.extend(
        path
        for path in changed_paths
        if _is_allowed_descriptive_path(path) and not isinstance(proposed_paths.get(path), str)
    )
    if invalid_paths:
        return _reject_result(
            candidate=candidate,
            reason_code="tool-schema-mutation",
            reason="Candidate changes non-descriptive tool schema fields.",
            changed_paths=sorted(set(invalid_paths)),
        )

    changed_texts = [proposed_paths[path] for path in changed_paths]
    if any(_has_permission_expansion(text) for text in changed_texts):
        return _reject_result(
            candidate=candidate,
            reason_code="tool-permission-expansion",
            reason="Candidate descriptive text expands or hides permission and safety boundaries.",
            changed_paths=changed_paths,
        )

    if any(_has_broad_tool_regression(text) for text in changed_texts):
        return _reject_result(
            candidate=candidate,
            reason_code="tool-contract-regression",
            reason="Candidate descriptive text encourages broad execution tool usage over narrower tools.",
            changed_paths=changed_paths,
        )

    return ToolMetadataValidationResult(
        tool_name=candidate.tool_name,
        baseline_schema_hash=candidate.baseline_schema_hash,
        verdict="accept",
        changed_paths=sorted(changed_paths),
    )


def capture_tool_contract_snapshot(registry: ToolRegistry) -> list[ToolContractSnapshot]:
    """Capture snapshot of tool contracts from registry.

    Iterate registry.get_definitions(), canonicalize each schema, extract
    tool metadata, and compute schema hashes. Sort results by (source_kind, tool_name).

    Args:
        registry: ToolRegistry instance containing tool definitions.

    Returns:
        List of ToolContractSnapshot ordered by (source_kind, tool_name).
    """
    snapshots: list[ToolContractSnapshot] = []

    for schema_def in registry.get_definitions():
        # Canonicalize to flat shape
        flat_schema = canonical_tool_schema(schema_def)

        # Extract fields with fallbacks
        tool_name = flat_schema.get("name")
        if not isinstance(tool_name, str):
            tool_name = ""

        description_text = flat_schema.get("description")
        if not isinstance(description_text, str):
            description_text = ""

        parameters_schema = flat_schema.get("parameters")
        if not isinstance(parameters_schema, dict):
            parameters_schema = {}

        # Determine source kind
        source_kind = _compute_source_kind(tool_name)

        # Compute schema hash
        hash_value = schema_hash(
            tool_name=tool_name,
            description_text=description_text,
            parameters_schema=parameters_schema,
        )

        snapshot = ToolContractSnapshot(
            tool_name=tool_name,
            description_text=description_text,
            parameters_schema=parameters_schema,
            source_kind=source_kind,
            schema_hash=hash_value,
        )
        snapshots.append(snapshot)

    # Sort by (source_kind, tool_name)
    snapshots.sort(key=lambda s: (s.source_kind, s.tool_name))

    return snapshots
