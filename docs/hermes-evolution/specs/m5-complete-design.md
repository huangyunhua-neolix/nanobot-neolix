# M5 Complete Design

## Status

Approved direction: complete M5 by adding the missing promotion gates and closing M5.1 stubs, while keeping the evolution surface limited to skills.

## Goal

Finish the M5 Darwinian Evolver milestone as a reviewable, PR-only offline skill-evolution pipeline with five gates:

1. test-pass gate,
2. skill-size gate,
3. cache-compat gate,
4. semantic-fidelity judge gate,
5. human-review readiness gate.

M5 is complete when `nanobot evolve run` can produce artifacts for a skill candidate, evaluate it through all five gates, and clearly require human approval before any live change is merged.

## Non-goals

- Do not evolve tool source code under `nanobot/agent/tools/`.
- Do not evolve system prompts or template files under `nanobot/templates/`.
- Do not push branches, open PRs, commit generated artifacts, or overwrite live skill files.
- Do not import GEPA, DSPy, Darwinian Evolver, or other optimizer packages in-process.
- Do not make nondeterministic judge scores part of optimizer fitness aggregation.

Tool and prompt evolution remain later independent milestones. M5 will document extension boundaries for those surfaces, but not implement automatic mutation for them.

## Architecture

### Gate 4: SemanticFidelityGate

Add `nanobot/evolve/gates/semantic_fidelity.py` and append it to `GATES` after cache compatibility.

The gate compares a candidate skill against its baseline and the run's evaluation records. It uses the existing judge/rubric path instead of adding a new provider abstraction. `JudgePool.score()` becomes the public scoring entry point used by calibration and semantic fidelity. The first implementation may use a deterministic local scoring path when no external judge provider is configured, but the gate contract must allow future LLM-backed judges.

The gate verdict is promotion-blocking. If semantic fidelity is below the configured threshold, the candidate is rejected. Judge metrics are recorded in the manifest/report, but are not returned to the optimizer or used as fitness.

### Gate 5: HumanReviewGate

Add `nanobot/evolve/gates/human_review.py` and append it to `GATES` after semantic fidelity.

The gate is a local PR-readiness gate, not a replacement for GitHub review. It verifies that a promoted candidate has complete review artifacts:

- `manifest.json`,
- `report.md`,
- `diff.patch`,
- `pr_body.md`,
- optimizer input/output audit files,
- explicit human-review checklist and required-approval wording in the PR body/report.

The gate passes only when the artifact bundle is ready for a human reviewer and the manifest records that human approval is still required. It must not call GitHub or inspect remote branch protection.

### Harness flow

`OfflineHarness.run()` keeps the existing M5.1 subprocess optimizer boundary and candidate validation. After a candidate passes gates 1-3, it runs gate 4 and gate 5 in order. Gate execution remains fail-fast and bounded by the existing per-gate timeout.

The harness should stop using placeholder M5.1 values where real data is available:

- `record_count_per_tier` comes from the generated eval bundle rather than a hardcoded one-record-per-tier assumption.
- test-pass gate metrics use real evaluated record counts when available.
- diff stats in `assemble_pr_body()` come from the generated `diff.patch` or equivalent patch stats stored in the manifest.

### Data model

Extend `RunManifest` only where necessary:

- artifact paths for gate 5 checks,
- diff stat fields or a small `DiffStats` model,
- semantic-fidelity summary if not already represented by gate evidence,
- `requires_human_approval: bool` for the PR-only human gate.

Keep manifest compatibility with older M5.1 manifests. Loading older manifests should not fail solely because new optional fields are absent.

### Reports and PR body

`report.md` and `pr_body.md` must make review state explicit:

- list all five gate results,
- include semantic-fidelity evidence,
- include diff stats,
- include a human-review checklist,
- state that no live skill file was changed,
- state that human approval is required before merge.

## Error handling

- Optimizer subprocess failures continue to raise existing typed optimizer errors.
- Candidate validation failures remain per-candidate and do not abort the whole run if other candidates remain.
- Gate 4 failures are normal gate failures, not exceptions, unless judge execution itself crashes.
- Gate 5 missing-artifact failures are normal gate failures with actionable evidence.
- Gate timeout behavior remains fail-closed.

## Security and privacy

- Keep optimizer input redacted.
- Treat optimizer output as untrusted until candidate validation completes.
- Do not expose unredacted eval records to PR body/report.
- Do not execute instructions from optimizer output or generated markdown.
- Do not call external network services from gate 5.
- Preserve PR-only behavior: generated artifacts are review inputs, not automatic deployment.

## Testing

Add/extend tests for:

- `JudgePool.score()` public entry point and calibration integration.
- Semantic gate pass/fail behavior.
- Human-review gate pass/fail behavior for complete and incomplete artifact bundles.
- `GATES` order includes five gates.
- Harness promotes only after all five gates pass.
- Harness rejects candidates that fail gate 4 or gate 5.
- Manifest compatibility for M5.1 manifests.
- Real diff stats appear in `pr_body.md`.
- Real eval record counts appear in manifest/report.
- `nanobot evolve run` still writes artifacts without mutating live skills.

Run targeted tests under `tests/evolve/` plus ruff for touched Python files.

## Documentation updates

Update:

- `docs/hermes-evolution/roadmap.md` to mark M5 complete under the skills-only definition.
- `docs/hermes-evolution/specs/m5-darwinian-evolver.md` or a follow-up M5 completion note to record the scope decision.
- `docs/hermes-evolution/specs/m4-carry-forward.md` to close entries addressed by gate 4/5, real diff stats, real judge scoring, and record counts.
- Add or update a retro for M5 completion.

## Open constraints resolved

- “Full M5” means five-gate skill evolution, not automatic mutation of tools or prompts.
- Tool and prompt evolution are intentionally moved out of M5 completion scope because they require separate safety, cache, and review designs.
- Human-review gate is local readiness verification; actual human review remains outside the CLI and repository automation.
