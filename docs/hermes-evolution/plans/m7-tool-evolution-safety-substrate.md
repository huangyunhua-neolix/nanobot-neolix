# M7 Tool Evolution Safety Substrate Plan

## Status

Implemented, pending PR review and merge.

## Goal

Add a metadata-only tool evolution lane that can produce reviewable tool contract artifacts without applying changes to runtime tools.

## Safety boundaries

M7 preserves these boundaries:

- No edits to `nanobot/agent/tools/*.py`.
- No changes to `ToolRegistry` execution semantics.
- No changes to MCP discovery.
- No changes to sandbox or permission prompts.
- No automatic application of metadata candidates to live tools.
- Metadata candidates remain PR/review artifacts only.

## Architecture

M7 extends the offline evolution harness with an artifact-first review path:

1. Capture a deterministic snapshot of currently loaded tool contracts at run start.
2. Pass that snapshot to the optimizer as context.
3. Accept optional `toolMetadataCandidates` from optimizer output.
4. Validate each metadata candidate deterministically before any judging.
5. Write JSON/Markdown artifacts for human review.
6. Optionally write local semantic judge evidence for accepted metadata candidates.
7. Surface artifact paths in reports and PR checklist text.

The core implementation lives in `nanobot/evolve/tool_metadata.py`; `OfflineHarness` owns run integration and artifact writing.

## Implemented components

### Schema and optimizer contracts

- Added `ToolContractSnapshot`, `ToolMetadataCandidate`, and `ToolMetadataValidationResult` to `nanobot/evolve/schemas.py`.
- Added `RunManifest.tool_metadata_artifact_paths` for generated artifact paths.
- Added `OptimizerInput.tool_contract_snapshot` and `OptimizerResult.tool_metadata_candidates`.
- Preserved compatibility with metadata-only `no_improvement` optimizer results.

### Deterministic snapshot capture

- Canonicalizes OpenAI nested tool schema shape and flat schema shape.
- Hashes only `tool_name`, `description_text`, and `parameters_schema` using sorted compact JSON.
- Sorts snapshots by `(source_kind, tool_name)`.
- Converts runtime schema fragments to JSON-safe data without mutating cached registry definitions.
- Keeps runtime-tool imports localized to the loaded-snapshot bridge and documented by the decoupling guard allow-list.

### Candidate validation

Validation rejects candidates when they:

- target a missing tool;
- reference a stale baseline schema hash;
- mutate non-descriptive schema paths;
- change descriptive paths to non-string values;
- expand permissions, hide safety boundaries, or bypass review;
- encourage broad execution-tool usage where narrower structured tools should be used.

Allowed metadata-only paths are:

- `$.description`
- `$.parameters.description`
- `$.parameters.properties.<name>.description`
- `$.parameters.properties.<name>.title`

### Review artifacts

`OfflineHarness` writes these artifacts when snapshot or metadata candidates exist:

- `tool_contract_snapshot.json`
- `tool_metadata_candidates.jsonl`
- `tool_metadata_review.md`
- optional `tool_metadata_judge_evidence.jsonl`

Shareable JSON artifacts are redacted before writing. Markdown review rendering also redacts, bounds, and escapes free text.

### Semantic judge evidence

Accepted metadata candidates with matching baseline snapshots get local deterministic judge evidence:

- Candidate metadata is carried as inert `CalibrationRecord` input data.
- `expectedRedacted` explicitly instructs the judge not to follow instructions inside tool metadata.
- Judge evidence is written for human review only.
- Judge metrics are not fed back into optimizer input/output and are not used as optimizer fitness.

### Report and PR surfaces

- `render_run_report()` adds a `Tool metadata review` section when artifact paths exist.
- `assemble_pr_body()` adds tool metadata review checklist items inside the existing human-review checklist.
- The PR body section invariant is preserved; no new top-level PR sections were added.

## Verification

Focused M7 checks passed:

```bash
uv run --extra dev pytest tests/evolve/test_schemas.py tests/evolve/test_tool_metadata.py tests/evolve/test_harness_run.py tests/evolve/test_harness_tool_metadata.py tests/evolve/test_report.py tests/evolve/test_deploy.py -q
```

Full evolve checks passed after review fixes:

```bash
uv run --extra dev pytest tests/evolve -q
uv run --extra dev ruff check nanobot/evolve tests/evolve
```

Latest observed results:

- `tests/evolve`: 522 passed
- `ruff check nanobot/evolve tests/evolve`: passed

## Follow-ups

- A later M7.x may design a manual application workflow for accepted metadata, but it must include an applied-vs-proposed audit trail.
- M8 should reuse the artifact-first pattern for prompt/template evolution and add explicit cache-impact reporting.
- M7 should not be marked merged until its PR lands on `main`.
