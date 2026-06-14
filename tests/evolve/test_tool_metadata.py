"""Tests for deterministic tool contract snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from nanobot.agent.tools.registry import ToolRegistry
from nanobot.evolve.schemas import ToolContractSnapshot
from nanobot.evolve.tool_metadata import (
    canonical_tool_schema,
    capture_tool_contract_snapshot,
    schema_hash,
)


@dataclass
class FakeTool:
    """Fake tool for testing snapshot capture."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_schema(self) -> dict[str, Any]:
        """Return OpenAI function schema shape."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class FlatSchemaTool:
    """Fake tool that returns flat schema shape (non-OpenAI)."""

    name: str
    description: str
    parameters: dict[str, Any]

    def to_schema(self) -> dict[str, Any]:
        """Return flat schema shape."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class TestCanonicalToolSchema:
    """Test schema canonicalization logic."""

    def test_openai_nested_schema_extracts_function(self) -> None:
        """OpenAI nested schema with 'function' key returns deep copy of function."""
        schema = {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {"type": "object"},
            },
        }
        result = canonical_tool_schema(schema)
        assert result == {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object"},
        }

    def test_flat_schema_returns_deep_copy(self) -> None:
        """Flat schema (no 'function' key) returns deep copy of input."""
        schema = {
            "name": "read_file",
            "description": "Read a file",
            "parameters": {"type": "object"},
        }
        result = canonical_tool_schema(schema)
        assert result == schema
        # Verify it's a deep copy
        assert result is not schema

    def test_function_key_not_dict_returns_deep_copy_of_schema(self) -> None:
        """If 'function' key exists but is not dict, return deep copy of schema."""
        schema = {
            "type": "function",
            "function": "not_a_dict",
            "name": "read_file",
            "description": "Read a file",
        }
        result = canonical_tool_schema(schema)
        assert result == schema
        assert result is not schema

    def test_deep_copy_modifications_dont_affect_original(self) -> None:
        """Modifications to result don't affect original schema."""
        schema = {
            "function": {
                "name": "read_file",
                "parameters": {"type": "object", "properties": {}},
            }
        }
        result = canonical_tool_schema(schema)
        result["name"] = "modified"
        result["parameters"]["properties"]["foo"] = "bar"
        assert schema["function"]["name"] == "read_file"
        assert "foo" not in schema["function"]["parameters"]["properties"]


class TestSchemaHash:
    """Test schema hash computation."""

    def test_hash_is_stable(self) -> None:
        """Same inputs produce same hash."""
        hash1 = schema_hash(
            tool_name="read_file",
            description_text="Read file from disk",
            parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        hash2 = schema_hash(
            tool_name="read_file",
            description_text="Read file from disk",
            parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        assert hash1 == hash2

    def test_hash_differs_with_different_tool_name(self) -> None:
        """Different tool names produce different hashes."""
        params = {"type": "object"}
        desc = "Read file from disk"
        hash1 = schema_hash(tool_name="read_file", description_text=desc, parameters_schema=params)
        hash2 = schema_hash(tool_name="write_file", description_text=desc, parameters_schema=params)
        assert hash1 != hash2

    def test_hash_differs_with_different_description(self) -> None:
        """Different descriptions produce different hashes."""
        tool_name = "read_file"
        params = {"type": "object"}
        hash1 = schema_hash(tool_name=tool_name, description_text="Read file", parameters_schema=params)
        hash2 = schema_hash(tool_name=tool_name, description_text="Read file from disk", parameters_schema=params)
        assert hash1 != hash2

    def test_hash_differs_with_different_parameters(self) -> None:
        """Different parameter schemas produce different hashes."""
        tool_name = "read_file"
        desc = "Read file from disk"
        hash1 = schema_hash(
            tool_name=tool_name,
            description_text=desc,
            parameters_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        hash2 = schema_hash(
            tool_name=tool_name,
            description_text=desc,
            parameters_schema={"type": "object", "properties": {"path": {"type": "integer"}}},
        )
        assert hash1 != hash2

    def test_hash_stable_despite_dict_key_order(self) -> None:
        """Hash is stable regardless of dict key insertion order."""
        tool_name = "read_file"
        desc = "Read file from disk"
        # Same content, different insertion order
        params1 = {"type": "object", "properties": {"a": {}, "b": {}}}
        params2 = {"properties": {"b": {}, "a": {}}, "type": "object"}
        hash1 = schema_hash(tool_name=tool_name, description_text=desc, parameters_schema=params1)
        hash2 = schema_hash(tool_name=tool_name, description_text=desc, parameters_schema=params2)
        assert hash1 == hash2

    def test_hash_is_sha256_hex(self) -> None:
        """Hash is a valid SHA256 hex string."""
        h = schema_hash(
            tool_name="test",
            description_text="test",
            parameters_schema={},
        )
        assert len(h) == 64  # SHA256 hex is 64 chars
        assert all(c in "0123456789abcdef" for c in h)


class TestCaptureToolContractSnapshot:
    """Test snapshot capture from ToolRegistry."""

    def test_empty_registry_returns_empty_list(self) -> None:
        """Empty registry produces empty snapshot list."""
        registry = ToolRegistry()
        snapshots = capture_tool_contract_snapshot(registry)
        assert snapshots == []

    def test_builtin_tool_snapshot(self) -> None:
        """Builtin tool (non-mcp_ prefix) produces correct snapshot."""
        registry = ToolRegistry()
        tool = FakeTool(
            name="read_file",
            description="Read a file from disk",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.tool_name == "read_file"
        assert snap.description_text == "Read a file from disk"
        assert snap.parameters_schema == {"type": "object", "properties": {"path": {"type": "string"}}}
        assert snap.source_kind == "builtin"
        assert len(snap.schema_hash) == 64

    def test_mcp_tool_snapshot(self) -> None:
        """MCP tool (mcp_ prefix) produces correct snapshot with mcp source_kind."""
        registry = ToolRegistry()
        tool = FakeTool(
            name="mcp_filesystem",
            description="MCP filesystem access",
            parameters={"type": "object"},
        )
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.tool_name == "mcp_filesystem"
        assert snap.source_kind == "mcp"

    def test_flat_schema_tool_snapshot(self) -> None:
        """Flat schema tool is canonicalized and snapshotted correctly."""
        registry = ToolRegistry()
        tool = FlatSchemaTool(
            name="flat_tool",
            description="A flat tool",
            parameters={"type": "object"},
        )
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        snap = snapshots[0]
        assert snap.tool_name == "flat_tool"
        assert snap.description_text == "A flat tool"

    def test_missing_name_field_defaults_to_empty_string(self) -> None:
        """Tool with missing name field uses empty string."""
        registry = ToolRegistry()

        @dataclass
        class NoNameTool:
            name: str = "no_name_tool"
            description: str = "No name"
            parameters: dict[str, Any] = None

            def __post_init__(self) -> None:
                if self.parameters is None:
                    self.parameters = {}

            def to_schema(self) -> dict[str, Any]:
                return {
                    "function": {
                        "description": "No name",
                        "parameters": {},
                    }
                }

        tool = NoNameTool()
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        assert snapshots[0].tool_name == ""

    def test_missing_description_defaults_to_empty_string(self) -> None:
        """Tool with missing description uses empty string."""
        registry = ToolRegistry()

        @dataclass
        class NoDescTool:
            name: str = "no_desc_tool"
            description: str = "test"
            parameters: dict[str, Any] = None

            def __post_init__(self) -> None:
                if self.parameters is None:
                    self.parameters = {}

            def to_schema(self) -> dict[str, Any]:
                return {
                    "function": {
                        "name": "test",
                        "parameters": {},
                    }
                }

        tool = NoDescTool()
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        assert snapshots[0].description_text == ""

    def test_missing_parameters_defaults_to_empty_dict(self) -> None:
        """Tool with missing parameters uses empty dict."""
        registry = ToolRegistry()

        @dataclass
        class NoParamsTool:
            name: str = "no_params_tool"
            description: str = "test"
            parameters: dict[str, Any] = None

            def __post_init__(self) -> None:
                if self.parameters is None:
                    self.parameters = {}

            def to_schema(self) -> dict[str, Any]:
                return {
                    "function": {
                        "name": "test",
                        "description": "test",
                    }
                }

        tool = NoParamsTool()
        registry.register(tool)  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        assert snapshots[0].parameters_schema == {}

    def test_snapshots_ordered_by_source_kind_then_name(self) -> None:
        """Snapshots sorted by (source_kind, tool_name)."""
        registry = ToolRegistry()

        # Register in non-alphabetical order
        registry.register(FakeTool(name="zebra", description="", parameters={}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="mcp_zulu", description="", parameters={}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="alpha", description="", parameters={}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="mcp_alpha", description="", parameters={}))  # type: ignore[arg-type]

        snapshots = capture_tool_contract_snapshot(registry)

        # Should be: builtin alpha, builtin zebra, mcp_alpha, mcp_zulu
        assert len(snapshots) == 4
        assert snapshots[0].tool_name == "alpha"
        assert snapshots[0].source_kind == "builtin"
        assert snapshots[1].tool_name == "zebra"
        assert snapshots[1].source_kind == "builtin"
        assert snapshots[2].tool_name == "mcp_alpha"
        assert snapshots[2].source_kind == "mcp"
        assert snapshots[3].tool_name == "mcp_zulu"
        assert snapshots[3].source_kind == "mcp"

    def test_snapshot_ordering_with_mixed_builtin_mcp(self) -> None:
        """Mixed builtin and mcp tools sorted correctly."""
        registry = ToolRegistry()
        registry.register(FakeTool(name="write_file", description="", parameters={}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="mcp_network", description="", parameters={}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="read_file", description="", parameters={}))  # type: ignore[arg-type]

        snapshots = capture_tool_contract_snapshot(registry)

        assert snapshots[0].tool_name == "read_file"
        assert snapshots[0].source_kind == "builtin"
        assert snapshots[1].tool_name == "write_file"
        assert snapshots[1].source_kind == "builtin"
        assert snapshots[2].tool_name == "mcp_network"
        assert snapshots[2].source_kind == "mcp"

    def test_byte_stable_output_for_same_registry(self) -> None:
        """Same registry contents produce byte-stable snapshots."""
        registry = ToolRegistry()
        registry.register(FakeTool(name="tool_a", description="desc a", parameters={"type": "object"}))  # type: ignore[arg-type]
        registry.register(FakeTool(name="tool_b", description="desc b", parameters={"prop": "val"}))  # type: ignore[arg-type]

        snapshots1 = capture_tool_contract_snapshot(registry)
        snapshots2 = capture_tool_contract_snapshot(registry)

        # All fields should match exactly
        assert len(snapshots1) == len(snapshots2)
        for s1, s2 in zip(snapshots1, snapshots2):
            assert s1.tool_name == s2.tool_name
            assert s1.description_text == s2.description_text
            assert s1.parameters_schema == s2.parameters_schema
            assert s1.source_kind == s2.source_kind
            assert s1.schema_hash == s2.schema_hash

    def test_snapshots_are_tool_contract_snapshot_instances(self) -> None:
        """Returned snapshots are ToolContractSnapshot instances."""
        registry = ToolRegistry()
        registry.register(FakeTool(name="test", description="test", parameters={}))  # type: ignore[arg-type]
        snapshots = capture_tool_contract_snapshot(registry)

        assert len(snapshots) == 1
        assert isinstance(snapshots[0], ToolContractSnapshot)
