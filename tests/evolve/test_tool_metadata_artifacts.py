from __future__ import annotations

from nanobot.evolve.tool_metadata_artifacts import matching_tool_snapshot
from tests.evolve.test_tool_metadata import _candidate_for_tool, _fake_read_tool, _snapshot_for_tool


def test_matching_tool_snapshot_requires_tool_name_and_schema_hash_match() -> None:
    tool = _fake_read_tool()
    snapshot = _snapshot_for_tool(tool)
    candidate = _candidate_for_tool(tool=tool)

    assert matching_tool_snapshot(candidate, [snapshot]) == snapshot

    wrong_tool = candidate.model_copy(update={"tool_name": "other_tool"})
    wrong_hash = candidate.model_copy(update={"baseline_schema_hash": "wrong-hash"})

    assert matching_tool_snapshot(wrong_tool, [snapshot]) is None
    assert matching_tool_snapshot(wrong_hash, [snapshot]) is None
    assert matching_tool_snapshot(candidate, []) is None
