# M8 Prompt / Template Evolution Safety Substrate Spec

## Status

Draft approved for bundled-skills prompt/template artifact-only M8 scope.

## Goal

Add a cache-safe prompt/template evolution lane for bundled skills that can produce deterministic, reviewable prompt/template candidate artifacts without modifying live skill files or runtime prompt cache behavior.

## Non-goals

M8 does not edit bundled skill source files, hot-reload prompts, mutate system prompts, apply candidates to stable prompt cache segments, change tool permissions, alter sandbox behavior, change runtime skill loading, or use judge metrics as optimizer fitness. Prompt/template candidates remain PR-only review artifacts.

## Background

M1-M7 established offline skill evolution, semantic judge evidence, and a metadata-only tool evolution substrate. M7 intentionally used an artifact-first review path because tool contract changes can affect safety boundaries even when they look descriptive. Prompt/template evolution has similar risk: wording changes can invalidate cache assumptions, weaken safety instructions, or silently change how bundled skills invoke tools.

The M8 first version narrows scope to bundled skills only. It reuses the M7 pattern: capture a deterministic baseline snapshot, allow the optimizer to emit inert candidates, validate them deterministically, write redacted review artifacts, and surface review state in reports and PR checklist text. It does not materialize patched skill files or apply changes.

## Scope

### In scope

- Capture deterministic snapshots for bundled skill prompt/template text at offline run start.
- Pass the snapshot to the optimizer as context.
- Accept optional optimizer output for prompt/template candidates.
- Validate that candidates target existing bundled skills and match current baseline hashes.
- Validate that candidates do not change frontmatter identity, cache-sensitive regions, tool permission wording, sandbox wording, or human-review requirements.
- Produce JSON and Markdown artifacts for human review.
- Produce explicit cache-impact artifacts that describe whether each candidate is cache-neutral, cache-sensitive, or rejected.
- Surface prompt/template artifact paths in run reports and PR checklist text without adding new top-level PR body sections.

### Out of scope

- Editing bundled skill files.
- Generating patch files that can be applied automatically.
- Shadow materialization of full candidate skill files.
- Runtime hot replacement of prompts or templates.
- System prompt evolution outside bundled skill bodies.
- Evolution of M6/M7 judge prompts, optimizer prompts, or harness-internal templates.
- Changes to tool registry, MCP discovery, sandbox policy, permission prompts, or runtime skill loading.

## Architecture

M8 adds a prompt/template artifact lane to the existing offline evolution flow.

### Prompt/template snapshot

A snapshot captures bundled skill prompt/template baselines once at run start. All candidates in the run compare against that snapshot. If the skill changes between runs, old candidates fail stale-baseline validation in the later run.

Snapshot extraction is deterministic:

1. Load bundled skills through the same read-only skill-loading path already used by the offline harness.
2. Include only bundled skills, not user-installed or runtime-generated skills.
3. For each bundled skill, capture:
   - `skill_name`
   - `source_kind`, fixed to `bundled` for M8 first version
   - `source_identifier`, a redaction-safe stable identifier for the bundled skill path or loader location
   - `frontmatter_hash`, computed from cache-relevant frontmatter fields
   - `body_hash`, computed from the full body text
   - `cache_sensitive_hash`, computed from cache-sensitive segments
   - `template_hash`, computed from the canonical review body used for candidate comparison
   - `body_line_count`
4. Sort snapshots by `(source_kind, skill_name)`.
5. Compute `snapshot_hash` from canonical JSON containing only stable review fields, serialized with sorted keys and compact separators.

Snapshots must be byte-stable for the same bundled skill contents. Snapshot generation is read-only.

### Cache-sensitive segments

M8 treats cache-sensitive segments as protected. A segment is cache-sensitive when it is one of these:

- Frontmatter fields that participate in skill identity or cache keys.
- Explicit stable-cache markers if present in the skill body.
- Safety/tool-permission instructions that must remain stable for review and runtime behavior.
- Prompt sections referenced by existing cache-key computation.

The first M8 implementation must not infer broad edits as safe. If segment classification is ambiguous, the candidate is rejected with `prompt-cache-boundary-unknown` rather than accepted.

### Prompt/template candidate

The optimizer may emit prompt/template candidates as inert artifacts, not patches. The candidate model contains:

- `skill_name`
- `baseline_snapshot_hash`
- `proposed_body`
- `intended_improvement`
- `risk_assessment`
- `cache_impact_claim`

`proposed_body` is the single source of truth for the candidate text. The optimizer must not provide independent diff summaries as authoritative data; Markdown review rendering derives diffs from the baseline body and `proposed_body`.

A candidate may change only non-cache-sensitive body text. It must preserve frontmatter, skill identity, required review instructions, safety instructions, and tool permission instructions.

### Validation and rejection codes

M8 validates prompt/template candidates deterministically before semantic judging:

1. `prompt-skill-not-found`: target bundled skill is absent from the snapshot.
2. `prompt-baseline-stale`: candidate baseline hash does not match the current snapshot.
3. `prompt-frontmatter-mutation`: candidate attempts to change frontmatter or skill identity.
4. `prompt-cache-boundary-unknown`: validator cannot prove the changed region is outside cache-sensitive segments.
5. `prompt-cache-sensitive-mutation`: candidate changes cache-sensitive text.
6. `prompt-safety-regression`: candidate weakens safety, permission, sandbox, review, or narrow-tool instructions.
7. `prompt-template-too-large`: candidate exceeds configured size or line-count bounds for review artifacts.

The safety regression check is conservative. It scans changed text and nearby context after whitespace normalization. It rejects wording that removes or weakens instructions requiring permission checks, sandbox respect, human approval, review-only artifacts, narrow tool preference, or non-application of candidates.

Only candidates that pass deterministic validation can receive semantic judge evidence. Judge evidence is local review support only and must not feed optimizer input, optimizer output, or optimizer fitness.

### Cache-impact artifact

M8 writes a cache-impact artifact for every run with snapshots or prompt/template candidates. It contains one row per candidate and summary counts:

- `cache_neutral`: changed regions are outside protected segments.
- `cache_sensitive`: changed regions touch protected segments and are rejected.
- `cache_unknown`: validator cannot classify the region and rejects.
- `candidate_absent`: no prompt/template candidates were emitted.

The report and PR body must surface the cache-impact summary so reviewers can see whether prompt evolution would invalidate stable prompt assumptions before any manual follow-up.

### Review artifacts

When snapshots or candidates exist, the harness writes:

- `prompt_template_snapshot.json`
- `prompt_template_candidates.jsonl`
- `prompt_template_review.md`
- `prompt_template_cache_impact.json`
- Optional `prompt_template_judge_evidence.jsonl` for accepted candidates

Shareable JSON artifacts are redacted before writing. Markdown review rendering redacts, bounds, and escapes free text. Artifacts must use deterministic ordering and stable relative paths.

### Report and PR surfaces

`render_run_report()` adds a prompt/template review section when prompt/template artifact paths exist. The section lists artifact paths and the cache-impact summary.

`assemble_pr_body()` adds prompt/template review checklist items inside the existing human-review checklist. It must not add a new top-level PR body section or change the existing section invariant.

Checklist items require reviewers to confirm:

- Prompt/template diff artifacts were inspected.
- No bundled skill source file changed automatically.
- Cache-sensitive segments were not modified by accepted candidates.
- Safety/tool/sandbox/review wording was not weakened.

## Data flow

1. `OfflineHarness.run()` starts and captures bundled skill prompt/template snapshots.
2. The snapshot is included in optimizer input.
3. The optimizer may emit `promptTemplateCandidates`.
4. The harness validates every candidate deterministically.
5. Accepted candidates may receive deterministic local judge evidence.
6. The harness writes redacted JSON, Markdown, cache-impact, and optional judge-evidence artifacts.
7. The manifest records prompt/template artifact paths.
8. Reports and PR body checklist text surface review state.
9. No skill source file or runtime prompt cache is modified.

## Safety invariants

- Bundled skill source files are read-only during M8 runs.
- Runtime prompt cache is not mutated.
- Candidates are artifacts only.
- Cache-sensitive text cannot be accepted.
- Stale-baseline candidates cannot be accepted.
- Missing-skill candidates cannot be accepted.
- Safety/tool/sandbox/review wording regressions cannot be accepted.
- Judge evidence cannot influence optimizer fitness.
- Report and PR outputs must make manual review mandatory.

## Testing requirements

Focused M8 tests must cover:

- Snapshot determinism and hash stability.
- Snapshot extraction does not mutate loaded skill data.
- Optimizer input includes `promptTemplateSnapshot`.
- Optimizer output accepts optional `promptTemplateCandidates` while preserving old JSON compatibility.
- Validation rejects missing skill, stale baseline, frontmatter mutation, cache-sensitive mutation, unknown cache boundary, safety regression, and oversized candidates.
- Accepted candidates generate JSON/Markdown/cache-impact artifacts.
- Rejected candidates render clear reason codes and do not receive judge evidence.
- Artifacts are redacted, bounded, and deterministic.
- Report and PR body surfaces include prompt/template review state without changing PR body section count.
- A harness run with prompt/template candidates does not modify bundled skill source files.
- Full `tests/evolve` and `ruff check nanobot/evolve tests/evolve` pass.

## Acceptance criteria

M8 is complete when:

- Bundled skill prompt/template snapshots are captured deterministically.
- Optimizer contracts include optional prompt/template snapshot and candidate fields.
- Candidate validation enforces cache and safety boundaries before judging.
- Review artifacts and cache-impact artifacts are written for human review.
- Reports and PR body checklist text surface prompt/template review state.
- No runtime prompt/template application path exists.
- No bundled skill file changes during a run.
- The roadmap links this spec, its implementation plan, and its retro.

## Follow-ups

- M8.x may add shadow candidate materialization, but only with explicit proposed-vs-applied audit trails and no automatic source overwrite.
- M8.x may extend the surface to harness-internal judge or optimizer prompts after bundled skill prompt safety is proven.
- M9 may consume M8 artifacts as part of runtime/offline integration, but runtime must still only propose offline jobs and must not apply prompt candidates.
- M10 should consider extracting shared artifact-lane helpers from M7/M8 to reduce harness and metadata module size.
