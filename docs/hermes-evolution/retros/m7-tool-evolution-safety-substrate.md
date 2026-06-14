# M7 Tool Evolution Safety Substrate Retro

## Status

Implemented, pending PR review and merge.

## What landed

M7 adds a metadata-only tool evolution lane to the offline harness. Each run captures a deterministic `ToolRegistry.get_definitions()` snapshot, passes sanitized tool contract context to the optimizer, validates optional metadata candidates against the current contract hash, and writes review artifacts:

- `tool_contract_snapshot.json`
- `tool_metadata_candidates.jsonl`
- `tool_metadata_review.md`
- optional `tool_metadata_judge_evidence.jsonl`

The implementation rejects missing tools, stale contract hashes, schema structure mutations, permission-expanding wording, and broad-tool regressions before any semantic judging.

## Safety boundaries preserved

M7 does not edit `nanobot/agent/tools/*.py`, change `ToolRegistry` execution, change MCP discovery, change permission prompts, change sandbox policy, or modify stable prompt cache sections. Accepted metadata remains proposed-only and requires human review before any later application workflow.

## Follow-ups

A later M7.x can design a manual application workflow, but it must include an applied-vs-proposed audit trail that records what wording was applied, by whom, and in which PR. M8 should reuse the artifact-first review pattern for prompt/template evolution while adding explicit cache impact reporting.
