# M5 Darwinian Evolver Spec

**Milestone**: M5.1, the first real offline evolution slice on top of the M4 skeleton.

**Status**: Design approved for planning on 2026-06-14.

**Goal**: Turn the M4 offline skeleton into a real skill-evolution pipeline by invoking an external optimizer through a subprocess-only boundary, validating returned skill candidates, running existing gates, and producing PR-only review artifacts.

**Non-goal**: This spec does not implement tool-description evolution, system-prompt evolution, full semantic-fidelity gate 4, full PR-human gate 5, automatic git push, automatic commit, HTTP API triggers, or runtime-lane changes.

---

## 1. Context

M4 created the offline evolution skeleton: `nanobot/evolve/`, `OfflineHarness`, `Candidate` / `Baseline` / `RunManifest`, three deterministic gates, CLI surface, and PR-only deploy helpers. The current gap is that `nanobot.evolve.pipeline.build_pipeline()` still raises `NotImplementedError`, and `nanobot evolve run` only validates the workspace.

M5.1 fills that gap with the smallest safe real evolution path:

1. Load exactly one baseline skill from the workspace.
2. Build an optimizer input bundle from the baseline and evaluation records.
3. Invoke an external optimizer command by subprocess.
4. Read optimizer output candidates from files.
5. Validate every returned candidate against the baseline and manifest contract.
6. Run the existing M4 gates in order.
7. Promote the best passing candidate.
8. Write manifest, report, diff patch, and PR body artifacts.

This preserves the M4/M5 offline-lane rule: evolution output is reviewable, PR-only, and never directly overwrites live skills.

---

## 2. Scope

### 2.1 In scope

- A subprocess-only optimizer adapter.
- A documented optimizer input/output file contract.
- A real `OfflineHarness.run()` orchestration path for one skill per run.
- CLI wiring for `nanobot evolve run` to call the real harness path.
- Candidate validation before gates run.
- Existing gates 1-3 reused unchanged as the first promotion barrier.
- PR-only artifact generation:
  - `manifest.json`
  - `report.md`
  - `diff.patch`
  - `pr_body.md`
  - optimizer input/output audit files
- Tests for subprocess invocation, validation, gate integration, CLI dispatch, and PR-only filesystem boundaries.
- Documentation updates to roadmap and M5 carry-forward/retro notes after implementation.

### 2.2 Out of scope

- Importing GEPA, DSPy, Darwinian Evolver, or other AGPL/large optimizer packages directly into nanobot.
- Running optimizer code in-process.
- Docker/container isolation as the default path.
- Tool source evolution under `nanobot/agent/tools/`.
- System prompt or template evolution under `nanobot/templates/`.
- Runtime-lane integration with `AgentLoop`, `AgentRunner`, channels, slash commands, or WebUI.
- Direct git push, direct PR creation, direct commit, or direct overwrite of `<workspace>/skills/agent/<name>/SKILL.md`.
- Tier B/D default enablement.
- Full gate 4 semantic-fidelity judge and full gate 5 branch-protection enforcement.

---

## 3. Design decisions

### 3.1 M5 is split into M5.1 and later M5.x slices

M5.1 implements the first real evolution loop for skills only. Later M5 slices may add gate 4, gate 5, richer eval tiers, and broader evolution surfaces.

Reason: the full roadmap M5 mixes optimizer integration, licensing, gates, deployment, and prompt/tool evolution. Shipping the first real skill optimizer path gives an end-to-end system that is reviewable and testable without expanding every surface at once.

### 3.2 AGPL isolation is subprocess-only

Nanobot invokes the optimizer as an external command. Nanobot does not import the optimizer's Python modules and does not include optimizer source code in this repository.

The adapter boundary is:

```text
nanobot/evolve -> subprocess command -> optimizer work dir -> output JSON/files -> nanobot/evolve
```

This keeps dependency and license boundaries explicit. The optimizer command can be a local binary, a wrapper script, or a development fake used by tests, as long as it obeys the file contract.

### 3.3 Optimizer metrics are deterministic by default

M5.1 promotion uses:

1. optimizer-reported score for ranking candidates within the same baseline,
2. existing deterministic gates 1-3 for eligibility,
3. PR review artifacts for human judgment.

Nondeterministic gate metrics, including future LLM judge scores, are report-only by default and do not feed optimizer fitness aggregation in M5.1. This closes the M4 carry-forward concern about noisy gate-4 metrics polluting GEPA search.

### 3.4 PR-only remains hard law

`nanobot evolve run` writes artifacts under the run directory. `nanobot evolve apply --manifest ...` previews or materializes PR-only artifacts, but it does not modify live skill files, commit, push, or call GitHub.

---

## 4. File-level architecture

### 4.1 New modules

#### `nanobot/evolve/optimizer/__init__.py`

Public exports for optimizer adapter primitives.

Exports:

- `OptimizerAdapter`
- `OptimizerInput`
- `OptimizerCandidate`
- `OptimizerResult`
- `OptimizerRunError`

#### `nanobot/evolve/optimizer/schema.py`

Pydantic models for the subprocess file contract.

Key models:

```python
class OptimizerInput(EvolveBase):
    run_id: str
    skill_name: str
    baseline_hash: str
    baseline_skill_md: str
    eval_records_path: str
    output_dir: str
    max_candidates: int
    timeout_seconds: int

class OptimizerCandidate(EvolveBase):
    skill_name: str
    skill_md_content: str
    score: float = Field(ge=0.0, le=1.0)
    iteration: int = Field(ge=1)
    rationale: str = Field(max_length=2000)

class OptimizerResult(EvolveBase):
    candidates: list[OptimizerCandidate]
    optimizer_name: str
    optimizer_version: str | None = None
```

These models intentionally avoid importing `dspy`, `gepa`, provider classes, or runtime agent modules.

#### `nanobot/evolve/optimizer/adapter.py`

Runs the external command and parses output.

Responsibilities:

- Create a per-run optimizer work directory.
- Write `optimizer_input.json`.
- Invoke command with bounded timeout.
- Capture stdout/stderr to files.
- Load `optimizer_output.json`.
- Validate the output with `OptimizerResult`.
- Raise typed errors on missing files, invalid JSON, timeout, non-zero exit, or empty candidate list.

The command contract is:

```bash
<optimizer-command> --input <run_dir>/optimizer_input.json --output <run_dir>/optimizer_output.json
```

No shell interpolation is used. The adapter calls `subprocess.run([...], shell=False, timeout=...)`.

#### `nanobot/evolve/report.py`

Small deterministic renderers for run output.

Responsibilities:

- `render_run_report(manifest, gate_results_by_candidate, optimizer_result) -> str`
- no filesystem writes;
- no external calls;
- stable section ordering.

`deploy.assemble_pr_body()` remains the PR-body renderer.

### 4.2 Modified modules

#### `nanobot/evolve/harness.py`

Add real orchestration while keeping existing models and gate behavior.

New/changed APIs:

```python
class OfflineHarness:
    def run(
        self,
        *,
        skill_name: str,
        optimizer_command: list[str],
        tiers: list[str],
        max_candidates: int = 8,
        optimizer_timeout_seconds: int = 600,
    ) -> RunManifest:
        ...
```

Additional private helpers:

- `_load_baseline_skill(skill_name) -> Baseline`
- `_load_eval_records(skill_name, tiers) -> Path`
- `_candidate_from_optimizer(candidate, baseline, run_id) -> Candidate`
- `_validate_candidate(candidate, baseline) -> None`
- `_rank_candidates(optimizer_result) -> list[OptimizerCandidate]`
- `_write_run_artifacts(...) -> None`
- `_build_diff_patch(baseline, promoted) -> str`

Validation requirements:

- returned `skill_name` must equal requested skill name;
- candidate frontmatter `name` must match skill name;
- candidate frontmatter `origin` must be `agent`;
- candidate frontmatter `created_by` must be `dspy:gepa` for M5.1-generated candidates;
- candidate frontmatter `evolved_from_run` must equal the current run id;
- candidate frontmatter `parent_skill_hash` must equal baseline content hash;
- candidate `parent_baseline_hash` must equal baseline content hash;
- candidate must not contain absolute path claims or write-path fields;
- candidate content hash is computed by nanobot, not trusted from optimizer output;
- empty or duplicate candidate bodies are rejected;
- candidate markdown must parse as a single skill document.

#### `nanobot/evolve/pipeline.py`

Replace `build_pipeline()`'s `NotImplementedError` role with a compatibility wrapper around the new optimizer adapter, or reduce it to a deprecated internal shim.

The module must continue to import without optional optimizer dependencies installed.

#### `nanobot/cli/evolve.py`

Update `run_run(args)` to call `OfflineHarness.run()`.

CLI additions:

```text
nanobot evolve run \
  --workspace <path> \
  --skill <skill-name> \
  --optimizer-command <cmd> [<arg> ...] \
  --tiers A,C \
  --max-candidates 8 \
  --optimizer-timeout-seconds 600
```

Notes:

- `--workspace` stays required.
- `--skill` is required for M5.1.
- `--optimizer-command` is required for real runs and consumes the remaining argv tokens as an argument vector.
- tests may pass a Python fake optimizer script as `--optimizer-command <python> <fake_optimizer.py>`.
- the command is stored as `list[str]` and executed with `shell=False`; no shell-style string splitting is performed after argparse.

#### `nanobot/evolve/deploy.py`

Keep branch naming and PR body contracts. Replace the M4 diff-stat stub if `diff.patch` line stats are available from the run artifact writer.

No direct git push or live skill overwrite is added.

#### `nanobot/config/schema.py`

M5.1 does not change config schema. Optimizer command, timeout, candidate limit, skill name, and tiers are supplied by CLI flags for this first slice.

A later M5.x spec may add config defaults after the CLI contract has stabilized.

---

## 5. Optimizer file contract

### 5.1 Input file

Nanobot writes `optimizer_input.json` inside the run directory.

Required fields:

```json
{
  "runId": "20260614T120000Z-demo-skill",
  "skillName": "demo-skill",
  "baselineHash": "basehash00112233",
  "baselineSkillMd": "---\nname: demo-skill\n...",
  "evalRecordsPath": "/abs/path/to/evals/bundle.ndjson",
  "outputDir": "/abs/path/to/evals/runs/<run_id>/optimizer",
  "maxCandidates": 8,
  "timeoutSeconds": 600
}
```

The optimizer may read `baselineSkillMd` and `evalRecordsPath`, then must write `optimizer_output.json` to the path supplied by `--output`.

### 5.2 Output file

The optimizer writes:

```json
{
  "optimizerName": "external-gepa-wrapper",
  "optimizerVersion": "0.1.0",
  "candidates": [
    {
      "skillName": "demo-skill",
      "skillMdContent": "---\nname: demo-skill\n...",
      "score": 0.82,
      "iteration": 1,
      "rationale": "Improved instruction specificity."
    }
  ]
}
```

Nanobot treats this file as untrusted input. It validates schema, recomputes hashes, parses skill frontmatter, and rejects invalid candidates before running gates.

### 5.3 Audit files

Each run directory stores:

```text
<workspace>/evals/runs/<run_id>/
├── manifest.json
├── report.md
├── diff.patch
├── pr_body.md
├── optimizer/
│   ├── optimizer_input.json
│   ├── optimizer_output.json
│   ├── stdout.txt
│   └── stderr.txt
└── candidates/
    ├── <candidate_hash>.SKILL.md
    └── ...
```

The run directory is append-only for a single run. Re-running with the same run id must fail unless a future explicit `--force` design is approved.

---

## 6. Data flow

```text
CLI args
  -> OfflineHarness.run()
  -> load baseline SKILL.md
  -> build eval bundle
  -> OptimizerAdapter.run()
  -> optimizer_output.json
  -> validate OptimizerResult
  -> convert to Candidate models
  -> run gates 1-3 in score order
  -> first passing candidate is promoted
  -> write manifest/report/diff/pr_body artifacts
```

Candidate ranking:

1. Sort optimizer candidates by descending `score`.
2. For equal score, sort by ascending `iteration`.
3. For equal score and iteration, sort by candidate content hash for deterministic tie-break.
4. Run gates in that order.
5. Promote the first candidate with all gates passing.
6. If candidates exist but all fail gates, final status is `rejected_by_gate`.
7. If no valid candidate remains after validation, final status is `no_improvement` unless the adapter itself failed.

---

## 7. Error handling

### 7.1 Optimizer command errors

Introduce:

```python
class OptimizerRunError(EvolveError, RuntimeError):
    STRUCTURED_KWARGS = frozenset({"run_dir", "exit_code"})
    MUST_PRECEDE = frozenset({"RuntimeError"})
```

Use it for:

- timeout;
- non-zero exit;
- missing output file;
- invalid JSON;
- output schema validation failure;
- empty `candidates` when the command claims success.

CLI mapping is pinned as:

- command missing, empty, or invalid command config -> exit 2 (`ConfigError`);
- command executable not found -> exit 2 (`ConfigError`, operator supplied an invalid command);
- command timed out -> exit 1 (`OptimizerRunError`);
- command ran and returned non-zero -> exit 1 (`OptimizerRunError`);
- command produced missing/invalid output -> exit 1 (`OptimizerRunError`).

The implementation must add tests for each mapped branch and update the evolve exit-code table if the table is touched in the same PR.

### 7.2 Candidate validation errors

Per-candidate validation failure should not abort the whole run if other candidates remain. The invalid candidate is recorded in `report.md` with a safe reason string.

Abort the run only when:

- baseline cannot be loaded;
- eval bundle cannot be built;
- optimizer command cannot be executed;
- optimizer output is missing or invalid at the top level;
- artifact write fails.

### 7.3 Gate errors

Existing `_run_gates()` behavior remains:

- `Exception` from a gate becomes a synthetic fail `GateResult`.
- `KeyboardInterrupt`, `SystemExit`, and `asyncio.CancelledError` propagate.
- Gate chain short-circuits on first fail per candidate.

---

## 8. Security and privacy

### 8.1 Subprocess safety

- Use `subprocess.run(args, shell=False, timeout=...)`.
- Do not construct shell strings.
- Persist stdout/stderr but cap report rendering to bounded excerpts.
- Do not include environment secrets in report or manifest.
- Use a dedicated optimizer work directory inside the run directory.
- Treat optimizer output as untrusted.

### 8.2 Path safety

- Optimizer output cannot specify write paths.
- Nanobot decides all artifact paths.
- Candidate files are written under `<run_dir>/candidates/` using computed content hashes.
- No optimizer-controlled path is opened for writing.

### 8.3 Privacy boundary

M5.1 uses Tier A/C by default. Tier B/D remain opt-in and are not required for the first real optimizer path.

If eval bundle generation touches session-derived records, it must use the existing redaction facade and preserve the M4 rule: no `raw_*`, `user_*`, session id, channel id, IP, email, phone, or local file path fields in exported eval records.

### 8.4 Prompt/cache boundary

M5.1 evolves skills only. It must not alter stable prompt templates or tool descriptions. Gate 3 remains the guard that rejects cache-key drift.

---

## 9. Gate policy

### 9.1 M5.1 gates

M5.1 runs the existing M4 gate registry:

1. `1-test-pass`
2. `2-size-cap`
3. `3-cache-compat`

No gate reorder is made in M5.1. The M4 carry-forward item about cheap-first ordering should be revisited in the M5.1 retrospective using observed gate-3 failure rate.

### 9.2 Future gate 4/5 extension points

M5.1 must not hard-code assumptions that block future gate 4/5.

Allowed future extension:

- `SemanticFidelityGate` with `NONDETERMINISTIC = True`
- `PrHumanReviewGate` or manifest status check gate
- additional `final_status` values in a later spec, without removing or renaming existing statuses

Policy for nondeterministic metrics:

- default: report-only;
- excluded from optimizer fitness;
- if a future spec includes them in fitness, it must define averaging, seeding, or variance bounding.

### 9.3 Long-running gate budget

M5.1 should add a cross-reference or docstring note to the `Gate.evaluate` contract: long-running gates must check budget between records. This is needed before gate 4 is implemented, and it closes the M4 carry-forward concern without adding a new `LONG_RUNNING` abstraction yet.

---

## 10. CLI behavior

### 10.1 `nanobot evolve run`

Required happy path:

```bash
nanobot evolve run \
  --workspace /path/to/workspace \
  --skill demo-skill \
  --optimizer-command /path/to/optimizer-wrapper \
  --tiers A,C
```

Expected output:

```text
Run: <run_id>
Skill: demo-skill
Status: promoted_to_pr | rejected_by_gate | no_improvement
Manifest: <workspace>/evals/runs/<run_id>/manifest.json
Report: <workspace>/evals/runs/<run_id>/report.md
```

### 10.2 `nanobot evolve report`

Existing report command should continue to read `--manifest`. It may gain prefix `run_id` resolution later, but M5.1 can keep manifest-path-first behavior.

### 10.3 `nanobot evolve apply`

`apply` remains PR-only. For a promoted manifest it renders branch name and PR body. It must not push or mutate live skills.

---

## 11. Test strategy

### 11.1 Optimizer adapter tests

Use a temporary Python script as a fake external optimizer. The script writes a valid `optimizer_output.json`.

Tests:

- writes `optimizer_input.json` with expected fields;
- invokes command with `shell=False` semantics through argument list;
- captures stdout/stderr;
- parses valid output;
- raises typed error for timeout;
- raises typed error for non-zero exit;
- raises typed error for missing output;
- raises typed error for invalid JSON;
- rejects empty candidate list.

### 11.2 Candidate validation tests

Tests:

- rejects mismatched skill name;
- rejects mismatched frontmatter name;
- rejects empty skill content;
- rejects duplicate candidate body;
- recomputes candidate hash instead of trusting optimizer;
- sets `parent_baseline_hash` from baseline;
- sets evolution provenance fields consistently;
- rejects path-like output fields if the schema ever grows one.

### 11.3 Harness integration tests

Tests:

- full fake optimizer happy path promotes first passing candidate;
- first high-score candidate fails a gate, second lower-score candidate passes and is promoted;
- all candidates fail gates -> `rejected_by_gate`;
- all candidates invalid -> `no_improvement` with validation warnings;
- artifact files exist and are under run directory;
- live skill file is unchanged;
- gate order remains 1, 2, 3;
- optimizer packages are not imported during adapter/harness tests.

### 11.4 CLI tests

Tests:

- `evolve run` requires `--skill`;
- `evolve run` requires `--optimizer-command`;
- happy path exits 0 and prints manifest path;
- missing workspace maps to config exit;
- optimizer failure maps to pinned exit;
- `report` and `apply` remain compatible with M4 manifests.

### 11.5 Decoupling tests

Extend existing evolve decoupling tests if present:

- `nanobot/evolve/**` does not import `nanobot.agent.loop`, `nanobot.agent.runner`, channels, command, API server, or tool modules;
- optimizer adapter does not import `dspy`, `gepa`, or AGPL package names;
- subprocess adapter does not use `shell=True`.

---

## 12. Implementation boundaries

### 12.1 No runtime lane changes

Do not modify:

- `nanobot/agent/loop.py`
- `nanobot/agent/runner.py`
- `nanobot/channels/**`
- `nanobot/command/**`
- `nanobot/api/server.py`

unless a later approved spec explicitly expands scope.

### 12.2 No broad config expansion

Prefer CLI flags and small internal models. Add config only for stable defaults that are hard to pass repeatedly.

### 12.3 No direct dependency addition unless necessary

M5.1 should not add GEPA/DSPy/Darwinian packages to core dependencies. If test-only helpers need dependencies, prefer stdlib fake optimizer scripts.

---

## 13. Carry-forward handling

M5.1 explicitly addresses these M4 carry-forward items:

- Nondeterministic gate metrics: report-only by default, excluded from optimizer fitness.
- Gate budget-check duty: add docstring/cross-reference before future long-running gate 4.
- Gate ordering: keep 1->2->3 for M5.1; record observed gate-3 failure rate in retro.
- Decision-log/carry-forward review: M5.1 retro must review `docs/hermes-evolution/specs/m4-carry-forward.md` and close entries whose criteria are met.

M5.1 does not close full gate 4/5 carry-forward items, because those gates remain later M5.x work.

---

## 14. Acceptance criteria

M5.1 is complete when:

1. `nanobot evolve run --workspace ... --skill ... --optimizer-command ...` can execute a fake external optimizer and produce a promoted candidate in a run directory.
2. The adapter never imports optimizer packages in-process.
3. Candidate output is validated before gates run.
4. Existing gates 1-3 decide promotion eligibility.
5. `manifest.json`, `report.md`, `diff.patch`, and `pr_body.md` are written deterministically.
6. The live skill file is not modified by `run` or `apply`.
7. Focused evolve tests pass.
8. `ruff check nanobot/evolve nanobot/cli/evolve.py tests/evolve` passes.
9. Roadmap marks M5.1 implemented only after PR merge.

---

## 15. Deferred work

- M5.2: full semantic-fidelity gate 4 with judge pool and nondeterminism policy.
- M5.3: PR-human gate 5 with branch protection / CODEOWNERS checks.
- M5.4: richer GEPA/Darwinian optimizer integration once the subprocess contract is proven.
- M5.5: tool-description evolution.
- M5.6: system-prompt/template evolution.
- Future: HTTP/API trigger surface if there is a concrete operator need.
