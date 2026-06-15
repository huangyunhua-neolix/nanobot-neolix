# M8 Prompt / Template Evolution Safety Substrate Spec

## Status

Draft under review; revised after scope, coherence, feasibility, safety, and testing review findings.

## Goal

Add a cache-safe prompt/template evolution lane for bundled skills that can produce deterministic, reviewable prompt/template candidate artifacts without modifying live skill files or runtime prompt cache behavior.

## Non-goals

M8 does not edit bundled skill source files during offline runs, hot-reload prompts, mutate system prompts, apply candidates to stable prompt cache inputs, change tool permissions, alter sandbox behavior, change runtime skill loading, or use judge metrics as optimizer fitness. Prompt/template candidates remain PR-only review artifacts.

## Background

M1-M7 established offline skill evolution, semantic judge evidence, and a metadata-only tool evolution substrate. M7 intentionally used an artifact-first review path because tool contract changes can affect safety boundaries even when they look descriptive. Prompt/template evolution has similar risk: wording changes can invalidate cache assumptions, weaken safety instructions, or silently change how bundled skills invoke tools.

M8 first version covers bundled skills only. It reuses the M7 artifact-first pattern, but it must not copy M7's helper logic into a second divergent implementation. M8 includes a small shared artifact-lane extraction before adding prompt/template-specific snapshot, validation, and rendering code.

## Scope

### In scope

- Extract shared M7/M8 artifact-lane scaffolding for deterministic artifact path planning, JSONL writing, redacted JSON artifact writing, and manifest path recording.
- Enumerate bundled skill files from `nanobot/skills/*/SKILL.md` through a new read-only bundled-skill snapshot loader.
- Capture deterministic snapshots for bundled skill frontmatter and body text at offline run start.
- Pass the prompt/template snapshot to the optimizer as context.
- Accept optional optimizer output for prompt/template candidates.
- Validate that candidates target existing bundled skills and match current baseline hashes.
- Validate that candidates do not include or mutate frontmatter.
- Validate that candidates change only explicitly editable body regions.
- Produce JSON and Markdown artifacts for human review.
- Report cache impact explicitly in the Markdown review artifact, run report, and PR checklist text.
- Surface prompt/template artifact paths in run reports and PR checklist text without adding new top-level PR body sections.

### Out of scope

- Editing bundled skill files during an offline run.
- Generating patch files that can be applied automatically.
- Shadow materialization of full candidate skill files.
- Runtime hot replacement of prompts or templates.
- System prompt evolution outside bundled skill bodies.
- Evolution of M6/M7 judge prompts, optimizer prompts, or harness-internal templates.
- Adding editable markers to bundled skill source files as part of this milestone.
- Changes to tool registry, MCP discovery, sandbox policy, permission prompts, or runtime skill loading.

## Definitions

### Bundled skill

A bundled skill is a tracked repository skill at `nanobot/skills/<skill_name>/SKILL.md`. M8 does not use the offline harness's current single-skill workspace loader, because that loader reads `workspace/skills/agent/<skill_name>/SKILL.md` and does not enumerate bundled repository skills.

M8 introduces a read-only bundled-skill enumerator that walks `nanobot/skills/*/SKILL.md`, parses each file into frontmatter and body, and returns deterministic records sorted by skill name. User-installed skills, runtime-generated skills, and workspace `skills/agent` fixtures are outside the bundled-skill snapshot.

### Editable body region

A body line is editable only when it is inside explicit baseline markers:

```markdown
<!-- evolve:prompt-editable:start -->
...
<!-- evolve:prompt-editable:end -->
```

M8 does not add these markers to bundled skills. If a bundled skill has no editable region markers, non-empty prompt/template changes for that skill must be rejected with `prompt-cache-boundary-unknown`. This fail-closed behavior is intentional: M8 establishes the safety substrate before any broad prompt mutation surface exists.

Editable-region parsing is strict:

- Markers must be balanced and non-overlapping.
- Nested editable regions are invalid.
- Markers inside fenced code blocks do not count.
- Any parse exception or ambiguous marker state is `prompt-cache-boundary-unknown`.
- Changed lines that cannot be mapped to an editable baseline region are `prompt-cache-boundary-unknown`.

### Cache-sensitive surface

The current evolve cache compatibility gate uses the skill frontmatter `description` as the cache key input. There is no existing body-level cache segmentation subsystem and no existing stable-cache marker syntax in bundled skill bodies.

Therefore M8 V1 defines cache-sensitive surface as the full frontmatter block. Because candidates contain only `proposed_body`, any candidate that includes a frontmatter delimiter (`---`) or attempts to provide frontmatter fields is rejected with `prompt-frontmatter-mutation`. Accepted prompt/template candidates are cache-neutral by construction because they cannot alter frontmatter or cache-key input.

If future work adds body-level cache markers, that belongs in M8.x and must update this spec before implementation.

## Architecture

M8 adds a prompt/template artifact lane to the existing offline evolution flow.

### Shared artifact-lane scaffolding

Before implementing prompt/template-specific logic, M8 extracts shared helpers from the M7 lane where doing so reduces duplication without changing behavior:

- Stable artifact path mapping.
- JSONL writing with deterministic ordering.
- Redacted JSON artifact writing.
- Manifest artifact-path registration.
- Markdown-safe review text helpers for redaction, bounding, and escaping.

The extraction must preserve M7 behavior and tests. M8 then instantiates the same artifact-lane primitives for prompt/template artifacts. This prevents M7 and M8 from shipping two diverging artifact pipelines.

### Prompt/template snapshot

A snapshot captures bundled skill prompt/template baselines once at run start. All candidates in the run compare against that snapshot. If the skill changes between runs, old candidates fail stale-baseline validation in the later run.

Each snapshot record contains:

- `skill_name`
- `source_kind`, fixed to `bundled`
- `source_identifier`, the redaction-safe relative path `nanobot/skills/<skill_name>/SKILL.md`
- `frontmatter_hash`, computed from the full parsed frontmatter mapping converted to JSON-safe primitives and serialized with `sort_keys=True`, `ensure_ascii=False`, and compact separators `(',', ':')`. Non-JSON-native frontmatter values are converted to strings before hashing.
- `body_hash`, computed from the exact body text after frontmatter parsing, UTF-8 BOM removal, line-ending normalization to `\n`, trailing-newline preservation, and Unicode NFC normalization.
- `cache_key_hash`, computed with the same current evolve rule as the cache gate: hash of frontmatter `description`
- `editable_region_count`
- `body_line_count`
- `snapshot_hash`, computed from canonical JSON containing `skill_name`, `source_kind`, `source_identifier`, `frontmatter_hash`, `body_hash`, `cache_key_hash`, `editable_region_count`, and `body_line_count`

`body_hash` and `cache_key_hash` are review fields. `snapshot_hash` is the single baseline hash used for staleness validation.

Snapshots must be byte-stable for the same bundled skill contents. Snapshot generation is read-only and must not mutate parsed frontmatter or body data.

### Prompt/template candidate

The optimizer may emit prompt/template candidates as inert artifacts, not patches. The candidate model contains:

- `skill_name`
- `baseline_snapshot_hash`
- `proposed_body`
- `intended_improvement`
- `risk_assessment`
- `cache_impact_claim`

`cache_impact_claim` is explanatory text only; validation derives cache impact from the baseline snapshot and `proposed_body`. `proposed_body` is the single source of truth for the candidate text. Optimizer-provided diff summaries are not part of the M8 schema; if a future optimizer emits extra summary fields, they must be ignored for validation and review truth.

A candidate may change only body text inside explicit editable regions. It must not include frontmatter delimiters or frontmatter fields.

### Validation and rejection codes

M8 validates prompt/template candidates deterministically before semantic judging:

1. `prompt-skill-not-found`: target bundled skill is absent from the snapshot.
2. `prompt-baseline-stale`: candidate baseline hash does not match the current snapshot.
3. `prompt-frontmatter-mutation`: candidate includes frontmatter delimiters or attempts to provide frontmatter fields.
4. `prompt-cache-boundary-unknown`: validator cannot prove every changed line maps to an explicit editable baseline region, or editable-region parsing fails.
5. `prompt-safety-regression`: changed lines touch protected wording patterns or reject-only semantic review detects weakening of protected safety wording.
6. `prompt-template-too-large`: `proposed_body` exceeds 128 KiB or 2,000 lines. These are hard upper bounds and configuration cannot raise them. The current bundled skills are expected to be below the 128 KiB baseline; if a bundled skill already exceeds the bound, M8 must either lower that skill's candidate surface to no-op review or update this spec before implementation.

M8 does not include `prompt-cache-sensitive-mutation` in V1 because the only current cache-sensitive surface is frontmatter, and frontmatter attempts are covered by `prompt-frontmatter-mutation`.

Validation precedence is deterministic:

1. Missing skill.
2. Stale baseline.
3. Size bound.
4. Frontmatter mutation.
5. Editable-region parse failure or changed line outside editable regions.
6. Safety regression.
7. Accept.

Exceptions are mapped by the stage that raised them. Missing skill, stale baseline, and size-bound checks run before parsing. Frontmatter delimiter detection is a plain text scan; if it matches, the result is `prompt-frontmatter-mutation`. Exceptions during editable-region parsing, diff mapping, protected-wording classification, or safety classification become `prompt-cache-boundary-unknown`. Parser bugs fail closed.

### Safety regression checks

M8 does not rely on a keyword-only allow/pass detector. Safety handling has two layers:

1. Positive editable-region allowlist: accepted candidates can only change text inside explicit editable regions. Protected safety/tool/sandbox/review instructions must not be placed inside editable regions. If protected wording appears inside an editable region, implementation must treat the entire region as protected and reject changes touching it.
2. Reject-only safety review: changed hunks are checked by deterministic protected-wording patterns, deterministic deny patterns, and optional M6 semantic judge evidence. This review can reject a candidate but can never override another rejection or turn an unsafe candidate into an accepted candidate.

Protected wording recognition is deterministic. The validator scans editable-region baseline text and changed hunks after casefolding and whitespace normalization. If any baseline editable region contains one of the protected phrases below, edits touching that region are `prompt-safety-regression`:

- Permission or approval requirements: `permission`, `approval`, `confirm`, `ask the user`, `human approval`.
- Sandbox or execution safety requirements: `sandbox`, `safe execution`, `do not execute`, `never execute`, `untrusted code`.
- Human review and PR-only artifact requirements: `human review`, `review artifact`, `pr-only`, `pull request`, `do not apply`, `manual review`.
- Narrow-tool preference over broad shell/process execution: `narrow tool`, `structured tool`, `prefer read`, `prefer search`, `avoid shell`, `avoid exec`.
- Non-application of candidates to live files or runtime prompts: `do not modify`, `no runtime`, `not applied`, `do not write`, `live prompt`.

Changed hunks are also rejected if they introduce denied weakening phrases such as `skip approval`, `without asking`, `ignore sandbox`, `bypass review`, `apply automatically`, `use shell instead`, or `hide from user`. Future changes to these phrase sets must add regression tests.

A candidate that removes, contradicts, or weakens these categories is `prompt-safety-regression`.

### Judge and optimizer isolation

Only candidates that pass deterministic validation can receive semantic judge evidence. Judge evidence is local review support only.

The optimizer input and optimizer output artifacts must not contain judge evidence paths, judge scores, judge summaries, or previous prompt/template judge artifacts. The optimizer adapter must read only the current optimizer input path and must not be passed prompt/template judge evidence paths. A future run must not add prior judge evidence into optimizer context by reading review artifacts.

### Cache-impact reporting

M8 reports cache impact in `prompt_template_review.md`, `report.md`, and PR checklist text. It does not write a separate cache-impact JSON artifact in V1 because the summary is derived from validation results.

The review summary includes deterministic counts:

- `cache_neutral`: accepted candidates that changed only explicit editable body regions.
- `cache_sensitive_rejected`: candidates rejected by `prompt-frontmatter-mutation`.
- `cache_unknown_rejected`: candidates rejected by `prompt-cache-boundary-unknown`.
- `candidate_absent`: no prompt/template candidates were emitted.
- `candidate_noop`: candidates whose normalized body is identical to the baseline body.

Whitespace-only diffs are classified as no-op. A no-op candidate is accepted only if the normalized body is byte-equal to the normalized baseline body after line-ending and Unicode normalization; it is rendered with `cache_impact=noop` and does not receive judge evidence.

### Review artifacts

When snapshots or candidates exist, the harness writes:

- `prompt_template_snapshot.json`
- `prompt_template_candidates.jsonl`
- `prompt_template_review.md`
- Optional `prompt_template_judge_evidence.jsonl` for accepted candidates

Manifest artifact path keys are stable and must be exactly:

- `prompt_template_snapshot`
- `prompt_template_candidates`
- `prompt_template_review`
- `prompt_template_judge_evidence`

Shareable JSON artifacts are redacted before writing using the same redaction pipeline used by M7 artifacts. Markdown review rendering must:

- Render candidate-controlled text only inside fenced code blocks.
- Escape or replace fence delimiters so candidate text cannot break out of the code fence.
- Strip or neutralize HTML comments, raw HTML blocks, Markdown links/images, and checklist-looking lines from candidate-controlled prose outside code blocks.
- Bound candidate-controlled text snippets to fixed limits.
- Never render optimizer-controlled text as PR checklist items or headings.

Artifact writes must use temp-file plus atomic rename. The manifest must not record an artifact path until the artifact write succeeds. A failed artifact write aborts the run rather than leaving a partial artifact referenced by the manifest.

### Manifest, report, and PR surfaces

`RunManifest` gains `prompt_template_artifact_paths: dict[str, str]` with `default_factory=dict`, mirroring the M7 `tool_metadata_artifact_paths` compatibility pattern.

`render_run_report()` adds a prompt/template review section when prompt/template artifact paths exist. The section lists artifact paths and cache-impact counts.

`assemble_pr_body()` adds fixed prompt/template review checklist items inside the existing human-review checklist. It must not add a new top-level PR body section or change the existing section invariant. Checklist text is a compile-time template and must not include optimizer-controlled candidate text.

Checklist items require reviewers to confirm:

- Prompt/template diff artifacts were inspected.
- No bundled skill source file changed automatically.
- Cache-sensitive frontmatter was not modified by accepted candidates.
- Safety/tool/sandbox/review wording was not weakened.

Tests must assert the exact checklist item count and the total PR body section count.

## Data flow

1. `OfflineHarness.run()` starts and captures bundled skill prompt/template snapshots with the new bundled-skill enumerator.
2. The snapshot is included in optimizer input as `promptTemplateSnapshot`.
3. The optimizer may emit `promptTemplateCandidates`.
4. The harness validates every candidate deterministically.
5. Accepted candidates may receive deterministic local judge evidence.
6. The harness writes redacted JSON, Markdown, and optional judge-evidence artifacts.
7. The manifest records prompt/template artifact paths only after successful artifact writes.
8. Reports and PR body checklist text surface review state and cache-impact counts.
9. No skill source file or runtime prompt cache is modified.

## Safety invariants

- Bundled skill source files are read-only during M8 runs.
- Runtime prompt cache input is not mutated.
- Candidates are artifacts only.
- Frontmatter cannot be changed by a candidate.
- Non-editable body regions cannot be changed by an accepted candidate.
- Stale-baseline candidates cannot be accepted.
- Missing-skill candidates cannot be accepted.
- Safety/tool/sandbox/review wording regressions cannot be accepted.
- Judge evidence cannot influence optimizer input, optimizer output, or optimizer fitness.
- Report and PR outputs must make manual review mandatory.

## Testing requirements

Focused M8 tests must cover:

- Shared artifact-lane extraction preserves M7 tool metadata artifact outputs.
- Bundled-skill snapshot enumeration reads `nanobot/skills/*/SKILL.md`, excludes workspace/user skills, and is deterministic.
- Snapshot hashing is stable across dict key order, locale, UTF-8 BOM presence, Unicode NFC/NFD forms, trailing-newline variants, and CRLF/LF line endings.
- Snapshot extraction does not mutate parsed skill data.
- Optimizer input includes `promptTemplateSnapshot`.
- Optimizer output accepts optional `promptTemplateCandidates` while preserving old JSON compatibility.
- One negative validation test per rejection code: `prompt-skill-not-found`, `prompt-baseline-stale`, `prompt-frontmatter-mutation`, `prompt-cache-boundary-unknown`, `prompt-safety-regression`, and `prompt-template-too-large`.
- Each rejection test asserts the exact reason code appears in JSON and Markdown artifacts, the JSON artifact remains well-formed, and the manifest records only successfully written artifact paths.
- Ambiguous editable-region parsing rejects fail-closed with `prompt-cache-boundary-unknown`.
- Candidate text outside explicit editable regions is rejected.
- Candidate text inside explicit editable regions can be accepted when all other checks pass.
- Optimizer-provided diff summaries are ignored; review diffs are derived from baseline body and `proposed_body`.
- Accepted candidates generate JSON/Markdown artifacts and optional judge evidence.
- Rejected candidates do not receive judge evidence.
- Judge evidence does not appear in optimizer input, optimizer output, or later optimizer context; include a two-run regression where the first run writes judge evidence and the second run's optimizer input remains evidence-free.
- Artifact redaction covers secret-shaped strings in `proposed_body`, `intended_improvement`, and `risk_assessment`, including Anthropic/OpenAI/GitHub/AWS-like keys, bearer tokens, emails, and absolute home paths.
- Markdown review rendering keeps candidate-controlled text inside escaped, bounded code fences and cannot render candidate-controlled checklist items.
- Report and PR body surfaces include prompt/template review state without changing the numeric PR body section count.
- PR checklist tests assert the exact fixed prompt/template checklist item count.
- A harness run with accepted prompt/template candidates does not modify bundled skill source file content or mtimes.
- A harness run with rejected prompt/template candidates does not modify bundled skill source file content or mtimes.
- Duplicate candidates for the same skill have deterministic ordering and independent validation results.
- Empty bundled-skill enumeration produces a well-formed empty snapshot and no prompt/template candidate artifacts.
- Whitespace-only diffs are classified as no-op accepted, rendered with `cache_impact=noop`, and do not receive judge evidence.
- Full `tests/evolve` and `ruff check nanobot/evolve tests/evolve` pass.

## Acceptance criteria

M8 is complete when:

- M7/M8 shared artifact-lane helpers exist and M7 behavior remains unchanged.
- Bundled skill prompt/template snapshots are captured deterministically from `nanobot/skills/*/SKILL.md`.
- Optimizer contracts include optional prompt/template snapshot and candidate fields.
- Candidate validation enforces frontmatter, editable-region, size, stale-baseline, and safety boundaries before judging.
- Review artifacts are written for human review with cache-impact counts.
- Reports and PR body checklist text surface prompt/template review state.
- No runtime prompt/template application path exists.
- No bundled skill file content or mtime changes during accepted or rejected runs.
- The roadmap links this spec, its implementation plan, and its retro.

## Follow-ups

- M8.x may add editable markers to selected bundled skills in a separate source-editing PR after the substrate exists.
- M8.x may add shadow candidate materialization, but only with explicit proposed-vs-applied audit trails and no automatic source overwrite.
- M8.x may extend the surface to harness-internal judge or optimizer prompts after bundled skill prompt safety is proven.
- M9 may consume M8 artifacts as part of runtime/offline integration, but runtime must still only propose offline jobs and must not apply prompt candidates.
- M10 may further split shared artifact-lane helpers if M8 extraction exposes broader maintainability debt.
