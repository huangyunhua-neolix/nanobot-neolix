# Finish M4 Offline Skeleton Design

## Context

M4 (`docs/hermes-evolution/specs/m4-offline-skeleton.md`) shipped an offline-evolution skeleton in PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6. The codebase now contains `nanobot/evolve/`, deterministic gates 1-3, redaction helpers, deploy helpers, manifest models, and `nanobot evolve` CLI wiring.

A follow-up review found that the milestone is not cleanly finished from a user/operator perspective:

- `nanobot evolve init`, `report`, and `apply` still raise `NotImplementedError` in `nanobot/cli/evolve.py`.
- Tier B/D dataset loading raises `NotImplementedError` from `nanobot/evolve/data/__init__.py::load_tier()`.
- The roadmap still describes M4 as in progress on `main`.
- There is no M4 retro explaining what landed versus what remains M5.

## Goal

Finish M4 as a coherent skeleton milestone without implementing M5.

The result should let an operator initialize an offline-evolution workspace, inspect/report an existing run manifest, and dry-run the PR-only apply surface locally. It should also make the documentation state match reality: M4 skeleton complete; M5 owns real Darwinian evolution.

## Non-goals

This work will not implement:

- The real GEPA optimization loop.
- Real LLM-backed `JudgePool.score` or calibration corpus.
- Gates 4-5.
- GitHub push or PR creation from `nanobot evolve apply`.
- Full §4.4 PR artifact bundle export (`--output-dir`, `--force`, atomic swap, fcntl locks, AST deploy-package guard).
- CI gate re-verification workflows.
- `record_self_eval()` write path or its 7-syscall durability contract.
- Tier B/D private-data loaders, redaction-to-loader integration, or SessionDB/self-eval enablement.
- M5 carry-forward entries whose close criteria explicitly depend on M5 design or production telemetry.

## Acceptance criteria

M4 is considered finished when all of these are true:

- `nanobot evolve init --workspace <dir>` creates the §4.1.1-compatible workspace skeleton and can be run twice without overwriting existing files or changing already-complete `.gitignore` mtime/content.
- `nanobot evolve report --manifest <path>` reads a valid `RunManifest` JSON file and prints the specified deterministic text format.
- `nanobot evolve apply --manifest <path>` performs a reduced-surface local PR preview for promotable manifests, refuses non-promotable manifests, and never pushes, commits, calls GitHub, spawns subprocesses, or mutates git state.
- `load_tier("B", ...)` and `load_tier("D", ...)` raise typed `ConfigError` refusals that name the M5/private-data boundary instead of `NotImplementedError`.
- `docs/hermes-evolution/roadmap.md` marks M4 skeleton complete and M5 as the next offline-evolution milestone.
- `docs/hermes-evolution/retros/m4-offline-skeleton.md` exists and names landed M4 scope, this finish pass, remaining M5 scope, and reviewed carry-forward entries.
- Focused tests pass: `pytest -x tests/evolve/` and `ruff check nanobot/evolve nanobot/cli/evolve.py tests/evolve`.

## Proposed approach

Use a narrow skeleton-completion pass.

### CLI behavior

`nanobot/cli/evolve.py` should keep the existing argparse command tree and exit-code mapping, but replace the current `NotImplementedError` handlers with useful skeleton behavior.

#### `nanobot evolve init`

- Resolve `--workspace` as follows:
  - if supplied, use `Path(args.workspace).expanduser()`;
  - if omitted, use `Path("~/.nanobot/evolve/default").expanduser()` to match the existing help text.
- Create the exact M4 §4.1.1 skeleton:
  - `<workspace>/evals/synthetic/.gitkeep`
  - `<workspace>/evals/golden/.gitkeep`
  - `<workspace>/evals/runs/`
  - `<workspace>/.gitignore` containing literal non-comment lines `evals/runs/`, `evals/self/`, and `evals/sessions/`
  - `<workspace>/evals/README.md`
- Do not create `datasets/`, top-level `runs/`, `candidates/`, `reports/`, or `evolve-config.json`; those were not in the M4 source-of-truth spec.
- Do not overwrite existing user files.
- If the workspace path exists and is not a directory, let the filesystem error surface to `EXIT_FS`.
- If only part of the skeleton exists, fill the missing pieces.
- `.gitignore` update must follow M4 §4.1.1 exact-line semantics: stripped, non-comment, exact literal match only; append only missing patterns; do not rewrite when all patterns already exist.
- Return `EXIT_OK` when the workspace exists or was created successfully.

Required `evals/README.md` headings:

```markdown
# nanobot evolve evals
## Tiers
## Record format
## Privacy
## M4/M5 boundary
```

#### `nanobot evolve report`

- Add `--manifest <path>` and change the existing positional `run_id` argument to optional (`nargs="?"`, default `None`). For this finish pass, `--manifest` is required for successful execution; if it is omitted, raise `ConfigError`. Positional `run_id` resolution can remain unimplemented until M5. Tests should call `--manifest` without a dummy positional.
- Read a `RunManifest` JSON file.
- Print this deterministic plain-text format, one field per line:

```text
Run: <run_id>
Skill: <skill_name>
Status: <final_status>
Promoted candidate: <promoted_candidate_hash-or-<none>>
Baseline: <baseline_hash>
Candidates: <comma-separated-candidate_hashes-or-<none>>
Gates:
- <gate_name>: <verdict>
Tiers: <tier>=<count>,...
Judge summary: records=<n>, aggregate=<median_aggregate>, process=<median_process>, output=<median_output>, token=<median_token>, splits=<consensus_split_count>
```

- Gate order must follow `manifest.gate_verdicts` order.
- Render missing `promoted_candidate_hash` and empty `candidate_hashes` as the literal `<none>`.
- Tier order must be alphabetical by tier key for stable tests.
- Error mapping:
  - missing manifest file: `FileNotFoundError` → `EXIT_FS` (`6`)
  - invalid JSON: `ConfigError` or bare `ValueError` → `EXIT_CONFIG` (`2`)
  - Pydantic validation error: wrapped as `ConfigError` by dispatch → `EXIT_CONFIG` (`2`)

#### `nanobot evolve apply`

- Add `--manifest <path>` and change the existing positional `run_id` argument to optional (`nargs="?"`, default `None`). For this finish pass, `--manifest` is required for successful execution; if it is omitted, raise `ConfigError`. Positional `run_id` resolution can remain unimplemented until M5. Tests should call `--manifest` without a dummy positional.
- Read a `RunManifest` JSON file.
- This is a **reduced-surface preflight subset** of M4 §4.4. It does not implement §4.4's bundle export, `--output-dir`, `--force`, atomic swap, lock, or deploy-package AST contract.
- Refuse every non-promotable manifest by raising `ApplyTerminalError` (`EXIT_APPLY_TERMINAL`, `8`):

| `final_status` | `promoted_candidate_hash` | Result |
|---|---|---|
| `promoted_to_pr` | non-empty | preview succeeds |
| `promoted_to_pr` | `None` | refuse with `ApplyTerminalError` |
| `rejected_by_gate` | any | refuse with `ApplyTerminalError` |
| `no_improvement` | any | refuse with `ApplyTerminalError` |
| `harness_error` | any | refuse with `ApplyTerminalError` |

- Generate local preflight output only:
  - derive `candidate_short_sha = manifest.promoted_candidate_hash[:8]`;
  - call `build_branch_name(manifest.run_id, manifest.skill_name, candidate_short_sha)`;
  - call `assemble_pr_body(manifest, manifest.gate_verdicts)`.
- Print deterministic plain text:

```text
Branch: <branch-name>
PR body:
<assembled-body>
```

- The CLI runtime must not push, mutate git state, call GitHub, spawn subprocesses, or create a PR.
- Return `EXIT_OK` for a valid preflight preview.
- Error mapping matches `report` for manifest load failures; terminal/refusal cases map to `EXIT_APPLY_TERMINAL` (`8`).

### Manifest helpers

Add these helpers to `nanobot/evolve/harness.py`:

- `load_manifest(path: Path) -> RunManifest`
- `dump_manifest(path: Path, manifest: RunManifest) -> None`

The helpers should use Pydantic validation and keep file/JSON errors explicit. `dump_manifest()` exists to keep tests and future tools from duplicating Pydantic JSON serialization.

### Dataset loader behavior

`load_tier()` should not leave Tier B/D as generic `NotImplementedError` in the public path.

Do not implement Tier B/D loaders in this pass. They are private-data paths tied to M4 spec §3.1.3 / §3.1.5, §9 redaction, `session_db_enabled`, `self_eval_enabled`, and no-PII manifest invariants; doing a partial loader now would blur the M4/M5 boundary.

Implement typed refusals instead:

- `load_tier("B", ...)` raises `ConfigError` explaining that Tier B SessionDB-anonymized loading is deferred to M5/private-data wiring and that M4 supports Tier A/C only.
- `load_tier("D", ...)` raises `ConfigError` explaining that Tier D self-eval loading is deferred to M5/private-data wiring and that M4 supports Tier A/C only.
- Preserve existing Tier A/C paired `input.jsonl` + `expected.jsonl` loader behavior.
- No public path should raise `NotImplementedError` for Tier B/D after this pass.

### Documentation

Update `docs/hermes-evolution/roadmap.md` to mark M4 skeleton as complete and merged via PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6.

Add `docs/hermes-evolution/retros/m4-offline-skeleton.md` with:

- What landed in M4.
- What this finish pass changed.
- What remains M5.
- A carry-forward mapping table with at least these entries explicitly reviewed:
  - `CF-t14-*` / run orchestrator follow-ups: remain M5-bound.
  - `CF-t16-*` / CLI/apply advisories: either closed only if this pass satisfies their own close criteria, or left open.
  - `CF-cc-a` / real `JudgePool.score`: remains M5-bound.
  - GEPA fitness-signal / gate-ordering entries: remain M5-bound.

If a carry-forward item is closed, update `docs/hermes-evolution/specs/m4-carry-forward.md` by appending the required `[CLOSED ...]` marker and retaining the body as audit trail.

Documentation edits are development-time repository edits. They are separate from the runtime guarantee that `nanobot evolve apply` must not mutate files outside its explicit output/preflight contract or git state.

## Testing

Add or update tests under `tests/evolve/`:

- CLI init happy path creates the exact §4.1.1 skeleton.
- CLI init idempotency: second run does not duplicate `.gitignore` lines or overwrite existing `evals/README.md`.
- CLI init partial pre-existing skeleton fills missing pieces.
- CLI init workspace path as a regular file maps to `EXIT_FS`.
- CLI tests must pass explicit `--workspace` paths from `tmp_path`; tests must never touch `~/.nanobot/`.
- CLI report renders the exact text format for a valid manifest.
- CLI report asserts exit codes for missing file (`6`), invalid JSON (`2`), and validation error (`2`).
- CLI apply renders branch/PR preview for a promotable manifest and asserts it uses `manifest.gate_verdicts` in the PR body.
- CLI apply refusal matrix covers `rejected_by_gate`, `no_improvement`, `harness_error`, and `promoted_to_pr` with missing candidate; all assert exit `8`.
- Tier B and Tier D typed refusals are covered and assert no `NotImplementedError`.
- Manifest load/dump helpers validate JSON and Pydantic errors.

Run:

- `pytest -x tests/evolve/`
- `ruff check nanobot/evolve nanobot/cli/evolve.py tests/evolve`

Do not use `--timeout=30` unless the local environment is confirmed to have `pytest-timeout` installed.

## Risks and boundaries

- The biggest scope risk is accidentally implementing M5. Avoid this by keeping `apply` as reduced-surface preflight only, leaving Tier B/D as typed refusals, and leaving `pipeline.build_pipeline()` as a clear M5 boundary.
- CLI behavior should be useful but conservative. The CLI must not make network calls, push, commit, spawn subprocesses, or mutate git state.
- Documentation must not overclaim: M4 is a skeleton, not full offline learning.
- Carry-forward entries must only be marked closed when their own close criteria are satisfied; otherwise the retro should list them as reviewed and left open.
