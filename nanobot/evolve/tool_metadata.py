"""Deterministic tool contract snapshots for M7 metadata-only tool evolution."""

import hashlib
import json
from copy import deepcopy
from typing import Any

from nanobot.evolve.schemas import ToolContractSnapshot


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


def capture_tool_contract_snapshot(registry: Any) -> list[ToolContractSnapshot]:
    """Capture snapshot of tool contracts from registry.

    Iterate registry.get_definitions(), canonicalize each schema, extract
    tool metadata, and compute schema hashes. Sort results by (source_kind, tool_name).

    Args:
        registry: Object with get_definitions() method (typically ToolRegistry).

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
        source_kind = "mcp" if tool_name.startswith("mcp_") else "builtin"

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
            source_kind=source_kind,  # type: ignore[arg-type]
            schema_hash=hash_value,
        )
        snapshots.append(snapshot)

    # Sort by (source_kind, tool_name)
    snapshots.sort(key=lambda s: (s.source_kind, s.tool_name))

    return snapshots
