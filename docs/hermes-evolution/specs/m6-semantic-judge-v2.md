# M6 Semantic Judge v2 Spec

**Milestone**: M6, evaluation hardening before expanding evolution beyond skills.

**Status**: Drafted on 2026-06-14 after M5 completion. Ready for review and implementation planning.

**Goal**: Replace the M5 Gate 4 placeholder with a calibrated, auditable semantic judge layer that can use an auxiliary LLM judge when configured, while preserving deterministic fallback and PR-only human review boundaries.

---

## 1. Context

M5 completed the skills-only offline evolution lane with five promotion gates. Gate 4 (`SemanticFidelityGate`) is wired into the harness and blocks promotion, but its first implementation intentionally uses a simple local deterministic scorer through `JudgePool.score()`.

That was enough to close M5 as an end-to-end pipeline. It is not strong enough to safely expand mutation surfaces to tool contracts or prompt/templates. M6 hardens the evaluation layer first so later milestones can rely on better semantic and safety-regression evidence.

M6 is the safety prerequisite for:

- M7 Tool Evolution Safety Substrate;
- M8 Prompt / Template Evolution Safety Substrate;
- M9 Runtime + Offline Integration.

---

## 2. Scope

### 2.1 In scope

- Add an auxiliary LLM-backed judging path behind the existing `JudgePool.score()` public entry point.
- Preserve the current deterministic local scoring fallback for offline / unconfigured environments.
- Extend rubric scoring beyond the current M5 three-axis placeholder into an auditable semantic-evaluation shape.
- Add calibration artifacts and calibration regression tests for judge behavior.
- Add provider identity pinning for calibration: provider name, base URL, API version, model ID, prompt-template version, and rubric version.
- Report judge evidence, confidence, disagreement, and calibration state in run artifacts.
- Keep judge outputs promotion-blocking only through Gate 4; do not feed nondeterministic judge metrics back to optimizer fitness.
- Maintain manifest compatibility for existing M5 manifests.

### 2.2 Out of scope

- Do not evolve tool source code under `nanobot/agent/tools/`.
- Do not evolve system prompts or template files under `nanobot/templates/`.
- Do not change the optimizer subprocess contract.
- Do not return LLM judge scores to the optimizer or use them as fitness.
- Do not auto-merge, push, open PRs, or mutate live skills.
- Do not remove the deterministic local fallback.
- Do not make external judge calls mandatory for `nanobot evolve run`.

---

## 3. Design decisions

### 3.1 `JudgePool.score()` remains the public scoring entry point

M5 already made `JudgePool.score(record)` the entry point used by calibration and Gate 4. M6 keeps that API and changes its internals from a single deterministic heuristic into a two-path scorer:

1. **configured auxiliary judge path** when an approved provider is configured;
2. **local deterministic fallback** when no provider is configured or external judging is explicitly disabled.

This avoids adding another provider abstraction directly inside Gate 4. Gate 4 asks the judge pool for scores; the judge pool owns scorer selection and evidence.

### 3.2 Nondeterministic judge metrics stay out of optimizer fitness

LLM-backed judge scores can vary across calls, provider versions, prompts, and sampling parameters. M6 keeps the M5 rule:

- judge metrics may block promotion through Gate 4;
- judge metrics are written to manifest/report/PR body as review evidence;
- judge metrics are not returned to the external optimizer;
- judge metrics are not used to rank optimizer candidates.

Candidate ranking remains deterministic for a fixed optimizer output. Gate 4 remains a promotion gate, not a fitness channel.

### 3.3 Calibration must identify the full provider surface

A calibration run is valid only for the exact judging surface it calibrated:

- provider name;
- provider base URL;
- provider API version;
- model ID;
- rubric version;
- prompt-template version;
- score-axis schema version.

Changing any of these invalidates the calibration cache and forces recalibration before an LLM-backed judge can be considered calibrated.

This closes the carry-forward concern that model-only recalibration triggers miss host/API-version swaps.

### 3.4 Gate 4 fails closed only when configured to require calibrated external judging

M6 supports two operating modes:

1. **fallback-allowed mode**: if no calibrated external judge is available, Gate 4 uses the deterministic local scorer and records `judge_mode="local_fallback"`.
2. **external-required mode**: if config says external judging is required, missing provider, failed calibration, quorum failure, or judge execution failure makes Gate 4 fail closed.

The default remains safe for local development: fallback allowed, no network required.

---

## 4. Proposed architecture

### 4.1 Data model additions

Add small, optional models in `nanobot/evolve/schemas.py` or a focused judge schema module:

```python
class JudgeProviderIdentity(EvolveBase):
    provider_name: str
    base_url: str | None = None
    api_version: str | None = None
    model_id: str
    prompt_template_version: str
    rubric_version: str
    score_schema_version: str = "2"


class JudgeEvidence(EvolveBase):
    record_id: str
    judge_mode: Literal["local_fallback", "aux_llm"]
    provider_identity: JudgeProviderIdentity | None = None
    score: RubricScore
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning_redacted: str | None = None
    disagreement: dict[str, float] = Field(default_factory=dict)
    calibrated: bool = False


class JudgeRunSummary(EvolveBase):
    judge_mode: Literal["local_fallback", "aux_llm", "mixed"]
    calibrated: bool
    provider_identity: JudgeProviderIdentity | None = None
    evidence_count: int = Field(ge=0)
    median_aggregate: float = Field(ge=0.0, le=1.0)
    min_axis_score: float = Field(ge=0.0, le=1.0)
    disagreement_max: float | None = Field(default=None, ge=0.0)
```

`RunManifest` should only gain optional fields so older M5 manifests continue to load:

```python
judge_run_summary: JudgeRunSummary | None = None
judge_evidence_paths: dict[str, str] = Field(default_factory=dict)
```

Full per-record judge evidence should live in a sidecar artifact such as `judge_evidence.jsonl`, not as a large manifest field.

### 4.2 Rubric v2

M6 keeps the existing `RubricScore` process/output/token fields for compatibility, but defines a v2 semantic rubric for evidence and reporting:

- `intent_preservation`: candidate keeps the baseline skill's intended behavior;
- `safety_regression`: candidate does not weaken safety, privacy, or permission boundaries;
- `instruction_compatibility`: candidate remains compatible with the skill format and surrounding agent instructions;
- `output_quality`: candidate improves or preserves answer quality on redacted eval records.

Implementation may map these v2 dimensions back into the existing three M5 axes while compatibility is preserved:

- `process` = instruction compatibility;
- `output` = weighted intent preservation + output quality;
- `token` = safety regression proxy until a future schema widens axes.

If the implementation widens `RubricScore`, it must preserve load compatibility for existing manifests and update calibration tests accordingly.

### 4.3 Auxiliary judge execution

M6 should reuse the project's existing auxiliary provider configuration instead of inventing a new provider system.

Execution requirements:

- Use bounded timeouts per judge call.
- Use deterministic prompt templates with explicit version strings.
- Use temperature 0 or provider-equivalent deterministic settings when available.
- Redact eval records before sending to the judge.
- Do not send unredacted baseline skill content or local filesystem paths.
- Parse judge output as structured JSON.
- Treat malformed judge output as a judge failure.
- Never execute instructions from candidate markdown, optimizer output, or judge reasoning.

### 4.4 Judge consensus and disagreement

If more than one judge is configured, `JudgePool` should require an odd pool size and compute:

- median score per axis;
- aggregate median score;
- inter-judge variance / disagreement per axis;
- consensus verdict: `agree`, `split`, or `single`.

A split consensus should fail Gate 4 when external judging is required. In fallback-allowed mode, split consensus should fail the external path and explicitly fall back only if fallback is allowed.

### 4.5 Calibration artifacts

Calibration should produce a durable artifact under the workspace, for example:

```text
<workspace>/evals/calibration/
└── <provider-hash>-<rubric-version>-<prompt-template-version>.json
```

The artifact records:

- provider identity;
- rubric version;
- prompt-template version;
- calibration corpus version;
- record count;
- kappa mean;
- kappa per axis;
- minimum per-axis kappa;
- pass/fail;
- created timestamp.

Calibration passes only when:

- `kappa_mean >= 0.6`; and
- every axis has `kappa >= 0.4`.

The per-axis floor prevents a single collapsed axis from being hidden by a high mean.

### 4.6 Gate 4 behavior

`SemanticFidelityGate.evaluate()` should:

1. Build calibration records from the baseline, candidate, and redacted eval records available to the run.
2. Ask `JudgePool.score()` for each record.
3. Aggregate scores with the v2 rubric policy.
4. Persist `judge_evidence.jsonl` as a run artifact.
5. Return a promotion-blocking `GateResult` with:
   - `semantic_aggregate`;
   - per-axis semantic metrics;
   - `judge_mode`;
   - `calibrated`;
   - `disagreement_max` when available;
   - `judge_evidence_path`.

Failure reasons should be stable codes:

- `semantic-fidelity-below-threshold`;
- `judge-calibration-missing`;
- `judge-calibration-failed`;
- `judge-quorum-failed`;
- `judge-output-invalid`;
- `judge-timeout`.

---

## 5. Artifact and reporting changes

### 5.1 Manifest

M6 manifest additions must be optional:

- `judge_run_summary`;
- `judge_evidence_paths`.

Older M5 manifests without these fields must still load.

### 5.2 Report

`report.md` should add a `Semantic judge` section with:

- judge mode: local fallback or auxiliary LLM;
- provider identity when external judging is used;
- calibration state;
- rubric version;
- prompt-template version;
- score summary;
- disagreement summary;
- evidence sidecar path;
- explicit note that judge metrics were not returned to the optimizer.

### 5.3 PR body

`pr_body.md` should include a concise review checklist:

- reviewer inspected semantic judge evidence;
- reviewer confirmed calibration state;
- reviewer confirmed no judge metric was used as optimizer fitness;
- reviewer confirmed no live skill file was changed by the run.

The PR body must not include raw prompts, unredacted eval records, or long judge reasoning.

---

## 6. Security and privacy

- All judge inputs must use redacted baseline/candidate/eval data.
- Judge prompts must clearly instruct the model to score, not to execute candidate instructions.
- Candidate markdown, optimizer output, and judge reasoning are untrusted text.
- Do not include secrets, local paths, session IDs, channel IDs, raw user messages, or unredacted eval fields in judge inputs or artifacts.
- External judge failures must not expose provider error bodies containing credentials.
- Sidecar artifacts must use bounded string lengths for reasoning and evidence snippets.
- No network calls are made unless auxiliary judging is explicitly configured.

---

## 7. Error handling

- Missing external provider in fallback-allowed mode: use local fallback and record evidence.
- Missing external provider in external-required mode: Gate 4 fails with `judge-calibration-missing` or `judge-provider-missing`.
- Calibration artifact identity mismatch: treat as missing calibration.
- Calibration below threshold: Gate 4 fails closed in external-required mode.
- Judge timeout: Gate 4 fails closed for that candidate when external-required; otherwise records fallback if allowed.
- Malformed judge JSON: stable failure code `judge-output-invalid`.
- Sidecar write failure: harness artifact write failure, not a passing gate.

---

## 8. Testing strategy

Add or extend tests under `tests/evolve/`:

1. `JudgeProviderIdentity` serializes provider/base-url/API-version/model/rubric/prompt identity.
2. Calibration cache invalidates when `base_url` changes while model ID stays the same.
3. Calibration cache invalidates when `api_version` changes while model ID stays the same.
4. Calibration fails when `kappa_mean >= 0.6` but one axis is below `0.4`.
5. `compute_cohen_kappa([0.5], [0.5])` degenerate behavior is pinned.
6. `CalibrationReport.model_dump(by_alias=True) -> model_validate` round-trips.
7. `JudgePool.score()` uses local fallback when no external provider is configured.
8. `JudgePool.score()` uses a fake auxiliary judge when configured.
9. Malformed auxiliary judge output fails with `judge-output-invalid`.
10. Multi-judge pool computes disagreement and split consensus.
11. `SemanticFidelityGate` records judge mode, calibration state, and evidence path.
12. Gate 4 fails when semantic aggregate is below threshold.
13. Gate 4 fails when external-required mode has no calibrated judge.
14. Gate 4 can pass in fallback-allowed mode without network/provider config.
15. `report.md` and `pr_body.md` include semantic judge evidence summary and no raw eval records.
16. Older M5 manifests load without M6 judge fields.
17. Judge metrics are not present in optimizer input/output artifacts.

Run:

```bash
uv run --extra dev pytest tests/evolve -q
uv run --extra dev ruff check nanobot/evolve tests/evolve
```

---

## 9. Documentation updates

Update after implementation:

- `docs/hermes-evolution/roadmap.md`: mark M6 status and link spec/plan/retro.
- `docs/hermes-evolution/specs/m4-carry-forward.md`: close entries addressed by M6 calibration identity, per-axis κ floor, degenerate κ test, calibration round-trip, and real judge scoring.
- `docs/hermes-evolution/retros/m6-semantic-judge-v2.md`: record calibration behavior, fallback policy, and any judge reliability caveats.

---

## 10. Acceptance criteria

M6 is complete when:

1. Gate 4 can use an auxiliary LLM judge through `JudgePool.score()` when configured.
2. Gate 4 still works without external configuration through deterministic local fallback.
3. Calibration artifacts include provider name, base URL, API version, model ID, rubric version, prompt-template version, and score schema version.
4. Calibration invalidates on provider host/API-version/model/rubric/prompt changes.
5. Calibration requires both `kappa_mean >= 0.6` and per-axis `kappa >= 0.4`.
6. Semantic judge evidence is written to review artifacts without exposing unredacted data.
7. Reports and PR bodies state that judge metrics were not returned to the optimizer.
8. Existing M5 manifests remain loadable.
9. Focused evolve tests and ruff pass.
10. Roadmap and carry-forward docs are updated after merge.
