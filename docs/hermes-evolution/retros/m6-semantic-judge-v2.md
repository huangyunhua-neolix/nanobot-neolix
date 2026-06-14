# M6 Semantic Judge v2 Retro

## Status

M6 is implemented and pending PR merge into `main`.

## What changed

- `JudgePool.score()` remains the deterministic compatibility scoring entry point.
- `JudgePool.score_with_evidence()` emits reviewable judge evidence for Gate 4.
- Gate 4 writes `judge_evidence.jsonl` sidecar artifacts during offline runs.
- `RunManifest` records optional `judge_run_summary` and `judge_evidence_paths` while remaining compatible with M5 manifests.
- Calibration now includes provider identity, corpus-version keying, `kappa_min`, and a per-axis κ floor.
- Reports and PR bodies surface semantic judge state and explicitly say judge metrics are not optimizer fitness.

## Safety boundaries preserved

- Judge metrics do not return to the optimizer.
- The deterministic local fallback remains available.
- External judging is optional unless explicitly required.
- Run/apply still do not mutate live skill files, push branches, or open PRs.
- Reports redact and bound free-form evidence paths before rendering.

## Review outcomes

- Schema compatibility review found the M5 manifest compatibility path intact.
- Calibration review confirmed provider identity and per-axis floor behavior.
- Auxiliary judge review drove prompt-injection hardening, typed client boundaries, custom weights, and reasoning redaction before persistence.
- Gate/harness review found and fixed the even-count median calculation for judge summaries.
- Report/PR body review added output-stable float rendering, evidence-path redaction coverage, and negative checklist gating coverage.

## Follow-ups

- M7 should use M6 evidence when designing tool contract evolution.
- M8 should reuse provider identity and prompt-template versioning for prompt/template evolution.
- M10 can still pick up unrelated carry-forward hardening: redaction regex boundary tests, CLI exit-code cleanup, and test-quality debt.
