# M7 Tool Evolution Safety Substrate Spec

## Status

Draft approved for metadata-only M7 scope.

## Goal

Build the first tool-evolution safety substrate by allowing offline evolution to produce reviewable tool metadata improvement artifacts while preserving all runtime tool behavior.

## Non-goals

M7 does not modify `nanobot/agent/tools/*.py`, register tools, remove tools, change `ToolRegistry` execution, change MCP discovery, change sandbox or permission behavior, or edit prompt stable-cache sections. Any candidate that requires one of those actions is out of scope and must be rejected.

## Background

M1-M6 established skill management, curator flow, offline evolution, and semantic judge evidence. The roadmap intentionally split tool and prompt evolution into later milestones because those surfaces can change permissions, cache behavior, and execution semantics. M7 is the narrow first step: evaluate whether tool descriptions and parameter guidance can be improved safely as PR-only artifacts before any runtime mutation surface is opened.

Current tool definitions are exposed through `ToolRegistry.get_definitions()` and tool modules under `nanobot/agent/tools/`. Existing tool usage guidance lives in `nanobot/templates/agent/tool_contract.md`. M7 treats those as read-only inputs.

## Scope

### In scope

- Capture deterministic snapshots of existing tool contracts.
- Generate metadata-only tool candidates as artifacts.
- Validate that candidates target existing tools and match the current baseline contract hash.
- Validate that candidates do not alter parameter schema structure.
- Reject dangerous metadata wording that expands permissions, bypasses sandboxing, hides execution, or encourages using broad tools over narrow tools.
- Reuse M6 semantic judge evidence for review support.
- Render report and PR checklist entries that force human review of tool metadata diffs.

### Out of scope

- Editing tool Python source.
- Changing runtime tool registration or execution.
- Adding, deleting, or renaming tools.
- Modifying MCP tool discovery.
- Changing permission prompts, sandbox policy, shell policy, or cache-stable prompt sections.
- Automatically applying metadata candidates to live prompt/tool definitions.

## Architecture

M7 adds a metadata-only artifact lane to the existing offline evolution flow.

### Tool contract snapshot

A snapshot captures the current review baseline for registered tools:

- `tool_name`: exact registered tool name.
- `schema`: canonical tool schema from the registry.
- `schema_hash`: stable hash of the canonical schema.
- `description_text`: extracted human-facing tool description.
- `source_kind`: `builtin` or `plugin` when known.
- `captured_at`: run timestamp stored in the enclosing run manifest, not inside the hash input.

Snapshots must be byte-stable for the same registry contents. Builtin and plugin ordering must follow the registry's existing stable ordering. Snapshot generation is read-only. `schema_hash` is computed from canonical JSON that excludes timestamps and other run-specific fields.

### Metadata candidate

The optimizer may emit candidate metadata artifacts, not patches:

- `tool_name`
- `baseline_schema_hash`
- `candidate_description`
- `candidate_parameter_notes`
- `intended_improvement`
- `risk_assessment`
- `proposed_schema`, which must be identical to the baseline schema except for allowed descriptive text fields.

Candidates are stored in `tool_metadata_candidates.jsonl`. A human-readable markdown diff is also produced for reviewers.

### Validation and gates

M7 uses deterministic validation before semantic judging:

1. `tool-not-found`: target tool is absent from the snapshot.
2. `tool-contract-stale`: candidate baseline hash does not match the current snapshot.
3. `tool-schema-mutation`: candidate attempts to add, remove, rename, or change parameter schema structure.
4. `tool-permission-expansion`: candidate wording implies new permission, hidden execution, sandbox bypass, credential access, or broader filesystem/network behavior than the existing tool contract.
5. `tool-contract-regression`: candidate weakens mandatory narrow-tool guidance or suggests using a broad tool when a narrower one matches.

Only candidates that pass deterministic validation can receive M6 semantic judge evidence. Judge metrics remain gate evidence only and must not be returned to optimizer fitness.

### Review artifacts

Each accepted candidate run writes:

- `tool_contract_snapshot.json`
- `tool_metadata_candidates.jsonl`
- `tool_metadata_review.md`

`tool_metadata_review.md` includes baseline text, candidate text, parameter-note diff, validation verdicts, judge evidence path, and explicit non-application language: no runtime tool source changed.

## Data flow

1. Offline run captures tool contract snapshot.
2. Optimizer receives sanitized snapshot context and emits metadata candidates.
3. Candidate parser validates shape and hashes.
4. Deterministic gates reject stale or unsafe candidates.
5. M6 semantic judge evaluates approved candidates for intent preservation and permission non-expansion.
6. Harness writes artifacts and manifest paths.
7. Report and PR body surface metadata review checklist items.
8. Human reviewer may manually copy approved wording in a later, separate implementation PR; M7 itself does not apply it.

## Error handling

- Snapshot capture failure rejects the run with `rejected_by_validation`.
- Missing target tool records `tool-not-found`.
- Hash mismatch records `tool-contract-stale`.
- Schema mutation records `tool-schema-mutation`.
- Dangerous wording records `tool-permission-expansion`.
- Missing external judge falls back to deterministic local scoring unless the run explicitly requires external judging; required external judging fails closed.

All reason strings rendered into reports must pass existing redaction and bounding helpers. These errors are terminal for the candidate but not necessarily for the whole run when another candidate can still pass validation.

## Security and privacy

- Snapshot content is treated as trusted codebase metadata, but optimizer output is untrusted.
- Candidate text is treated as inert data in judge prompts.
- No candidate may request secrets, credentials, hidden command execution, sandbox bypass, broad filesystem scans, or network access beyond the existing tool contract.
- Optimizer audit files must not include runtime secrets.
- Review artifacts must clearly state that no live tool file was modified.

## Testing plan

- Schema tests for snapshot and candidate JSON round-trip with camelCase aliases.
- Snapshot determinism tests for stable ordering and stable hashes.
- Validation tests for missing tool, stale hash, schema mutation, dangerous wording, and broad-tool regression.
- Harness tests proving artifacts are written and `nanobot/agent/tools/*.py` files are unchanged.
- Report tests for metadata review section and redacted artifact paths.
- PR body tests preserving the existing top-level section invariant and adding metadata checklist lines only when metadata artifacts exist.
- Optimizer audit tests proving judge metrics and live tool source are not fed back as fitness.

## Acceptance criteria

- A full offline run can produce tool metadata review artifacts without changing runtime tool behavior.
- All metadata candidates are tied to a current tool contract hash.
- Schema structure changes and permission-expanding wording are rejected deterministically.
- M6 judge evidence is available for safe candidates but remains outside optimizer fitness.
- Reports and PR bodies force human review of metadata diffs.
- No files under `nanobot/agent/tools/` are modified by M7 runtime paths.

## Follow-up milestones

- M8 should reuse the same artifact-first pattern for prompt/template evolution, with stricter cache impact reporting.
- A later M7.x may design a manual application workflow, but only after metadata artifacts and review quality are proven.
