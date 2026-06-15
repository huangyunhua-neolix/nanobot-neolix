# M8 Prompt / Template Evolution Safety Substrate Retro

## Status

Implemented, pending PR review and merge.

## What shipped

M8 adds an artifact-only prompt/template evolution lane for bundled skills. The offline harness now captures deterministic snapshots from `nanobot/skills/*/SKILL.md`, passes those snapshots to the optimizer, accepts optional body-only prompt/template candidates, validates them fail-closed, and writes redacted review artifacts for human review.

## Safety boundaries preserved

- Bundled skill source files are read-only during offline runs.
- Prompt/template candidates are inert artifacts only.
- Runtime prompt loading and prompt cache behavior are unchanged.
- Candidate frontmatter mutation is rejected before editable-region parsing.
- Body changes outside explicit editable markers are rejected.
- Safety/tool/sandbox/review wording regressions are rejected.
- Judge evidence is local review evidence only and is never included in optimizer input or output.

## Verification

The M8 branch passed focused prompt/template tests, existing M7 tool metadata regressions, report/PR checklist tests, the full `tests/evolve` suite, and `ruff check nanobot/evolve tests/evolve`.

## Follow-ups

- M8.x may add editable markers to selected bundled skills in a separate source-editing PR.
- M8.x may design shadow materialization for candidate skill files, but only with explicit proposed-vs-applied audit trails and no automatic source overwrite.
- M9 may propose offline prompt/template evolution jobs from runtime telemetry, but runtime must still never apply prompt candidates directly.
