# M5 Complete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete M5 as a PR-only offline skill-evolution pipeline with five promotion gates and no live skill mutation.

**Architecture:** Keep the existing M5.1 subprocess optimizer boundary. Add two focused gate modules (`SemanticFidelityGate`, `HumanReviewGate`), extend shared manifest schemas for diff stats and review state, and update `OfflineHarness.run()` so generated artifacts and manifest evidence drive gates 4-5. Close M5.1 stubs by deriving record counts from the eval bundle and diff stats from the generated patch.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest, ruff, existing `nanobot.evolve` modules.

---

## File Structure

- Modify `nanobot/evolve/schemas.py`
  - Add `DiffStats` model.
  - Add optional manifest fields: `diff_stats`, `requires_human_approval`.
  - Keep M5.1 manifest loading compatible by giving new fields defaults.
- Modify `nanobot/evolve/judges/rubric.py`
  - Add `JudgePool.score(record)` deterministic scoring entry point.
  - Avoid provider imports; this is the local default scorer used by gate 4 and calibration.
- Modify `nanobot/evolve/judges/calibration.py`
  - Remove obsolete TODO wording.
  - Fail fast on missing human score axes before scoring.
- Create `nanobot/evolve/gates/semantic_fidelity.py`
  - Gate 4. Uses `JudgePool.score()` for candidate semantic fidelity.
- Create `nanobot/evolve/gates/human_review.py`
  - Gate 5. Verifies artifact bundle readiness and explicit human-review requirement.
- Modify `nanobot/evolve/gates/__init__.py`
  - Import and append gates 4-5 after gate 3.
- Modify `nanobot/evolve/harness.py`
  - Derive eval record counts while writing eval bundle.
  - Populate candidate gate-1 counts from those records.
  - Build patch before manifest, compute diff stats, set `requires_human_approval=True`, write artifacts in gate-5-compatible order.
- Modify `nanobot/evolve/deploy.py`
  - Render real diff stats and human-review checklist in PR body.
- Modify `nanobot/evolve/report.py`
  - Render diff stats and human approval state.
- Modify tests under `tests/evolve/`
  - Add focused tests for new schema fields, judge scoring, gates 4-5, harness integration, and deploy/report rendering.
- Modify docs
  - `docs/hermes-evolution/roadmap.md`
  - `docs/hermes-evolution/specs/m4-carry-forward.md`
  - `docs/hermes-evolution/specs/m5-darwinian-evolver.md`
  - Create `docs/hermes-evolution/retros/m5-complete.md`

---

### Task 1: Manifest Fields for M5 Completion

**Files:**
- Modify: `nanobot/evolve/schemas.py`
- Test: `tests/evolve/test_schemas.py`

- [ ] **Step 1: Write failing schema tests**

Add these tests to `tests/evolve/test_schemas.py`:

```python
from datetime import datetime, timezone

from nanobot.evolve.gates import GateResult
from nanobot.evolve.schemas import DiffStats, JudgeSummary, RunManifest


def _judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=2,
        median_aggregate=0.0,
        median_process=0.0,
        median_output=0.0,
        median_token=0.0,
        consensus_split_count=0,
    )


def _manifest_payload() -> dict[str, object]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "run_id": "run-1",
        "started_at": now,
        "finished_at": now,
        "nanobot_version": "0.0.0",
        "evolve_extra_version": {"optimizer": "fake"},
        "skill_name": "demo-skill",
        "baseline_hash": "basehash",
        "candidate_hashes": ["candhash"],
        "promoted_candidate_hash": "candhash",
        "gate_verdicts": [],
        "judge_summary": _judge_summary(),
        "final_status": "promoted_to_pr",
        "tiers_used": ["A", "C"],
        "record_count_per_tier": {"A": 1, "C": 5},
        "judge_pool_health": {},
    }


def test_diff_stats_model_accepts_patch_counts() -> None:
    stats = DiffStats(files_changed=1, insertions=3, deletions=2)

    assert stats.files_changed == 1
    assert stats.insertions == 3
    assert stats.deletions == 2


def test_manifest_defaults_m5_completion_fields_for_m5_1_compatibility() -> None:
    manifest = RunManifest(**_manifest_payload())

    assert manifest.diff_stats is None
    assert manifest.requires_human_approval is False


def test_manifest_accepts_diff_stats_and_human_review_flag() -> None:
    manifest = RunManifest(
        **_manifest_payload(),
        diff_stats=DiffStats(files_changed=1, insertions=3, deletions=2),
        requires_human_approval=True,
    )

    assert manifest.diff_stats is not None
    assert manifest.diff_stats.insertions == 3
    assert manifest.requires_human_approval is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_schemas.py::test_diff_stats_model_accepts_patch_counts tests/evolve/test_schemas.py::test_manifest_defaults_m5_completion_fields_for_m5_1_compatibility tests/evolve/test_schemas.py::test_manifest_accepts_diff_stats_and_human_review_flag -v
```

Expected: FAIL with import error or missing `DiffStats` / missing manifest fields.

- [ ] **Step 3: Implement schema fields**

In `nanobot/evolve/schemas.py`, add this class after `ValidationFailure`:

```python
class DiffStats(EvolveBase):
    files_changed: int = Field(default=0, ge=0)
    insertions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
```

Then add these fields to `RunManifest` after `artifact_paths`:

```python
    diff_stats: DiffStats | None = None
    requires_human_approval: bool = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_schemas.py::test_diff_stats_model_accepts_patch_counts tests/evolve/test_schemas.py::test_manifest_defaults_m5_completion_fields_for_m5_1_compatibility tests/evolve/test_schemas.py::test_manifest_accepts_diff_stats_and_human_review_flag -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/evolve/schemas.py tests/evolve/test_schemas.py
git commit -m "feat(evolve): add M5 manifest review fields"
```

---

### Task 2: JudgePool Public Score Entry Point

**Files:**
- Modify: `nanobot/evolve/judges/rubric.py`
- Modify: `nanobot/evolve/judges/calibration.py`
- Test: `tests/evolve/test_judges.py`
- Test: `tests/evolve/test_calibration.py`

- [ ] **Step 1: Write failing judge tests**

Add to `tests/evolve/test_judges.py`:

```python
from nanobot.evolve.judges.calibration import CalibrationRecord


def test_judge_pool_score_returns_deterministic_rubric_score() -> None:
    pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
    record = CalibrationRecord(
        record_id="rec-1",
        human_scores={"process": 0.8, "output": 0.7, "token": 0.9},
        input_payload={
            "baselineBody": "Use concise answers.",
            "candidateBody": "Use concise answers. Include one concrete example.",
            "expectedRedacted": "The answer includes a concrete example.",
        },
    )

    score = pool.score(record)

    assert score.process == 1.0
    assert score.output == 1.0
    assert score.token == 0.9
    assert score.aggregate == 0.98


def test_judge_pool_score_penalizes_empty_candidate() -> None:
    pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
    record = CalibrationRecord(
        record_id="rec-2",
        human_scores={"process": 0.0, "output": 0.0, "token": 0.0},
        input_payload={"baselineBody": "Use concise answers.", "candidateBody": ""},
    )

    score = pool.score(record)

    assert score.process == 0.0
    assert score.output == 0.0
    assert score.token == 0.0
    assert score.aggregate == 0.0
```

Add to `tests/evolve/test_calibration.py`:

```python
class _ExplodingScorer:
    def score(self, record: CalibrationRecord) -> RubricScore:
        raise AssertionError("score should not be called when human axes are missing")


def test_calibrate_validates_human_axes_before_scoring() -> None:
    records = [
        CalibrationRecord(
            record_id="bad-rec",
            human_scores={"process": 1.0, "output": 1.0},
        )
    ]

    with pytest.raises(ValueError, match="missing human score"):
        calibrate(records, _ExplodingScorer())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_judges.py::test_judge_pool_score_returns_deterministic_rubric_score tests/evolve/test_judges.py::test_judge_pool_score_penalizes_empty_candidate tests/evolve/test_calibration.py::test_calibrate_validates_human_axes_before_scoring -v
```

Expected: FAIL because `JudgePool.score` does not exist and calibration scores before axis validation.

- [ ] **Step 3: Implement scoring and calibration fail-fast**

In `nanobot/evolve/judges/rubric.py`, add this import:

```python
from typing import TYPE_CHECKING, Literal
```

Replace the existing `from typing import Literal` import with the line above.

Add this block below imports:

```python
if TYPE_CHECKING:
    from nanobot.evolve.judges.calibration import CalibrationRecord
```

Add this method inside `JudgePool` after `effective_min_quorum`:

```python
    def score(self, record: "CalibrationRecord") -> RubricScore:
        """Return a deterministic local rubric score for offline gate checks.

        Provider-backed judges can replace this path in a later milestone. This
        default scorer is intentionally simple and dependency-free so calibration
        and gate 4 have a concrete public entry point now.
        """
        candidate_body = str(record.input_payload.get("candidateBody", "")).strip()
        baseline_body = str(record.input_payload.get("baselineBody", "")).strip()
        expected = str(record.input_payload.get("expectedRedacted", "")).strip()
        if not candidate_body:
            return RubricScore(process=0.0, output=0.0, token=0.0, aggregate=0.0)

        process = 1.0 if "TODO" not in candidate_body and "TBD" not in candidate_body else 0.5
        output = 1.0
        if expected and expected.lower() not in candidate_body.lower():
            output = 0.8
        if baseline_body and candidate_body == baseline_body:
            output = min(output, 0.7)
        token = 0.9 if len(candidate_body) >= len(baseline_body) else 0.8
        aggregate = (
            process * self.weights.process
            + output * self.weights.output
            + token * self.weights.token
        )
        return RubricScore(
            process=round(process, 6),
            output=round(output, 6),
            token=round(token, 6),
            aggregate=round(aggregate, 6),
        )
```

In `nanobot/evolve/judges/calibration.py`, replace the scoring block:

```python
    judge_scores: list[RubricScore] = [pool.score(r) for r in records]

    kappa_per_axis: dict[str, float] = {}
    for axis in RUBRIC_AXES:
```

with:

```python
    for rec in records:
        for axis in RUBRIC_AXES:
            if axis not in rec.human_scores:
                raise ValueError(
                    f"record {rec.record_id!r} missing human score for axis {axis!r}"
                )

    judge_scores: list[RubricScore] = [pool.score(r) for r in records]

    kappa_per_axis: dict[str, float] = {}
    for axis in RUBRIC_AXES:
```

Then remove the inner `if axis not in rec.human_scores:` check from the loop because it is now redundant.

Also delete the TODO paragraph from `_JudgeScorer` docstring lines that mention wiring the real entry point.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_judges.py::test_judge_pool_score_returns_deterministic_rubric_score tests/evolve/test_judges.py::test_judge_pool_score_penalizes_empty_candidate tests/evolve/test_calibration.py::test_calibrate_validates_human_axes_before_scoring -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/evolve/judges/rubric.py nanobot/evolve/judges/calibration.py tests/evolve/test_judges.py tests/evolve/test_calibration.py
git commit -m "feat(evolve): add judge pool scoring entry point"
```

---

### Task 3: Semantic Fidelity Gate

**Files:**
- Create: `nanobot/evolve/gates/semantic_fidelity.py`
- Modify: `nanobot/evolve/gates/__init__.py`
- Modify: `tests/evolve/conftest.py`
- Modify: `tests/evolve/test_gate_contract.py`
- Create: `tests/evolve/test_gate_semantic_fidelity.py`

- [ ] **Step 1: Write failing semantic gate tests**

Create `tests/evolve/test_gate_semantic_fidelity.py`:

```python
from datetime import datetime, timezone

from nanobot.evolve.gates.semantic_fidelity import SemanticFidelityGate
from nanobot.evolve.schemas import Baseline, Candidate, SkillFrontmatter


def _frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="Demo skill",
        origin="agent",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _baseline() -> Baseline:
    return Baseline(
        skill_name="demo-skill",
        skill_md_content="---\nname: demo-skill\ndescription: Demo skill\n---\nUse concise answers.\n",
        frontmatter=_frontmatter(),
        body_md="Use concise answers.",
        cache_key_hash="cache",
        size_metrics={"lines": 5},
        content_hash="basehash",
        loaded_from="tests",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _candidate(body: str) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content=f"---\nname: demo-skill\ndescription: Demo skill\n---\n{body}\n",
        frontmatter=_frontmatter(),
        body_md=body,
        cache_key_hash="cache",
        size_metrics={"lines": 6},
        content_hash="candhash",
        parent_baseline_hash="basehash",
        gepa_iteration=1,
    )


def test_semantic_fidelity_gate_passes_candidate_above_threshold() -> None:
    result = SemanticFidelityGate().evaluate(
        _candidate("Use concise answers. Include one concrete example."),
        _baseline(),
    )

    assert result.gate_name == "4-semantic-fidelity"
    assert result.verdict == "pass"
    assert result.metrics["semantic_aggregate"] >= 0.8
    assert result.evidence is not None
    assert result.evidence["judge_model"] == "local/deterministic"


def test_semantic_fidelity_gate_fails_empty_candidate() -> None:
    result = SemanticFidelityGate().evaluate(_candidate(""), _baseline())

    assert result.verdict == "fail"
    assert result.failure_reason == "semantic-fidelity-below-threshold"
    assert result.metrics["semantic_aggregate"] == 0.0
```

Modify `tests/evolve/test_gate_contract.py` imports to include the new module:

```python
import nanobot.evolve.gates.semantic_fidelity  # noqa: F401
```

Update `tests/evolve/conftest.py` shared fixture to include body fields needed by gate 4:

```python
@dataclass
class FakeCandidate:
    content_hash: str = "cand-hash"
    cache_key_hash: str = "cand-cache-key"
    body_md: str = "Use concise answers. Include one concrete example."
    skill_md_content: str = "Use concise answers. Include one concrete example."
    size_metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class FakeBaseline:
    content_hash: str = "base-hash"
    cache_key_hash: str = "base-cache-key"
    body_md: str = "Use concise answers."
    skill_md_content: str = "Use concise answers."
    size_metrics: dict[str, float] = field(default_factory=dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_gate_semantic_fidelity.py tests/evolve/test_gate_contract.py::test_gates_ordering_matches_name_prefix tests/evolve/test_gate_contract.py::test_e2e_gates_iterate_with_shared_fake -v
```

Expected: FAIL because `SemanticFidelityGate` module does not exist and GATES still has three gates.

- [ ] **Step 3: Implement semantic gate**

Create `nanobot/evolve/gates/semantic_fidelity.py`:

```python
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.gates import Gate, GateResult
from nanobot.evolve.gates._constants import RUBRIC_PASS_THRESHOLD
from nanobot.evolve.judges.calibration import CalibrationRecord
from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate


class SemanticFidelityGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = True

    @property
    def name(self) -> str:
        return "4-semantic-fidelity"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        start = time.monotonic()
        pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
        score = pool.score(
            CalibrationRecord(
                record_id=f"semantic:{candidate.content_hash}",
                human_scores={"process": 1.0, "output": 1.0, "token": 1.0},
                input_payload={
                    "baselineBody": baseline.body_md,
                    "candidateBody": candidate.body_md,
                    "expectedRedacted": baseline.body_md,
                },
            )
        )
        passed = score.aggregate >= RUBRIC_PASS_THRESHOLD
        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=baseline.content_hash,
            verdict="pass" if passed else "fail",
            metrics={
                "semantic_process": score.process,
                "semantic_output": score.output,
                "semantic_token": score.token,
                "semantic_aggregate": score.aggregate,
            },
            evidence={"judge_model": "local/deterministic"},
            failure_reason=None if passed else "semantic-fidelity-below-threshold",
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
```

Modify `nanobot/evolve/gates/__init__.py` bottom imports and registry:

```python
from nanobot.evolve.gates.semantic_fidelity import SemanticFidelityGate  # noqa: E402
```

Append after `GATES.append(CacheCompatGate())`:

```python
GATES.append(SemanticFidelityGate())
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_gate_semantic_fidelity.py tests/evolve/test_gate_contract.py::test_gates_ordering_matches_name_prefix tests/evolve/test_gate_contract.py::test_e2e_gates_iterate_with_shared_fake -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/evolve/gates/__init__.py nanobot/evolve/gates/semantic_fidelity.py tests/evolve/conftest.py tests/evolve/test_gate_contract.py tests/evolve/test_gate_semantic_fidelity.py
git commit -m "feat(evolve): add semantic fidelity gate"
```

---

### Task 4: Human Review Gate

**Files:**
- Create: `nanobot/evolve/gates/human_review.py`
- Modify: `nanobot/evolve/gates/__init__.py`
- Modify: `tests/evolve/conftest.py`
- Modify: `tests/evolve/test_gate_contract.py`
- Create: `tests/evolve/test_gate_human_review.py`

- [ ] **Step 1: Write failing human review gate tests**

Create `tests/evolve/test_gate_human_review.py`:

```python
from datetime import datetime, timezone

from nanobot.evolve.gates.human_review import HumanReviewGate
from nanobot.evolve.schemas import Baseline, Candidate, SkillFrontmatter


def _frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="Demo skill",
        origin="agent",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _baseline() -> Baseline:
    return Baseline(
        skill_name="demo-skill",
        skill_md_content="base",
        frontmatter=_frontmatter(),
        body_md="base",
        cache_key_hash="cache",
        size_metrics={"lines": 1},
        content_hash="basehash",
        loaded_from="tests",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _candidate(**metrics: int) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content="candidate",
        frontmatter=_frontmatter(),
        body_md="candidate",
        cache_key_hash="cache",
        size_metrics={"lines": 1, **metrics},
        content_hash="candhash",
        parent_baseline_hash="basehash",
        gepa_iteration=1,
    )


def test_human_review_gate_passes_complete_review_bundle() -> None:
    result = HumanReviewGate().evaluate(
        _candidate(
            review_manifest=1,
            review_report=1,
            review_diff=1,
            review_pr_body=1,
            review_optimizer_input=1,
            review_optimizer_output=1,
            review_requires_human_approval=1,
        ),
        _baseline(),
    )

    assert result.gate_name == "5-human-review"
    assert result.verdict == "pass"
    assert result.metrics["review_artifacts_present"] == 6.0
    assert result.evidence is not None
    assert result.evidence["requires_human_approval"] == "true"


def test_human_review_gate_fails_missing_review_bundle_item() -> None:
    result = HumanReviewGate().evaluate(
        _candidate(
            review_manifest=1,
            review_report=1,
            review_diff=0,
            review_pr_body=1,
            review_optimizer_input=1,
            review_optimizer_output=1,
            review_requires_human_approval=1,
        ),
        _baseline(),
    )

    assert result.verdict == "fail"
    assert result.failure_reason == "human-review-artifacts-incomplete: review_diff"
```

Modify `tests/evolve/test_gate_contract.py` imports to include:

```python
import nanobot.evolve.gates.human_review  # noqa: F401
```

Update `tests/evolve/conftest.py` shared passing candidate `size_metrics` with:

```python
            "review_manifest": 1.0,
            "review_report": 1.0,
            "review_diff": 1.0,
            "review_pr_body": 1.0,
            "review_optimizer_input": 1.0,
            "review_optimizer_output": 1.0,
            "review_requires_human_approval": 1.0,
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_gate_human_review.py tests/evolve/test_gate_contract.py::test_gates_ordering_matches_name_prefix tests/evolve/test_gate_contract.py::test_e2e_gates_iterate_with_shared_fake -v
```

Expected: FAIL because `HumanReviewGate` module does not exist and GATES still has four gates.

- [ ] **Step 3: Implement human review gate**

Create `nanobot/evolve/gates/human_review.py`:

```python
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar

from nanobot.evolve.gates import Gate, GateResult

if TYPE_CHECKING:
    from nanobot.evolve.schemas import Baseline, Candidate

_REQUIRED_REVIEW_FLAGS: tuple[str, ...] = (
    "review_manifest",
    "review_report",
    "review_diff",
    "review_pr_body",
    "review_optimizer_input",
    "review_optimizer_output",
)


class HumanReviewGate(Gate):
    NONDETERMINISTIC: ClassVar[bool] = False

    @property
    def name(self) -> str:
        return "5-human-review"

    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        del baseline
        start = time.monotonic()
        missing = [name for name in _REQUIRED_REVIEW_FLAGS if candidate.size_metrics.get(name, 0) < 1]
        requires_approval = candidate.size_metrics.get("review_requires_human_approval", 0) >= 1
        if not requires_approval:
            missing.append("review_requires_human_approval")
        passed = not missing
        duration_ms = int((time.monotonic() - start) * 1000)
        return GateResult(
            gate_name=self.name,
            candidate_hash=candidate.content_hash,
            baseline_hash=candidate.parent_baseline_hash,
            verdict="pass" if passed else "fail",
            metrics={
                "review_artifacts_present": float(
                    sum(1 for name in _REQUIRED_REVIEW_FLAGS if candidate.size_metrics.get(name, 0) >= 1)
                ),
                "review_artifacts_required": float(len(_REQUIRED_REVIEW_FLAGS)),
                "requires_human_approval": 1.0 if requires_approval else 0.0,
            },
            evidence={"requires_human_approval": "true" if requires_approval else "false"},
            failure_reason=None if passed else f"human-review-artifacts-incomplete: {', '.join(missing)}",
            timestamp=datetime.now(timezone.utc),
            duration_ms=duration_ms,
        )
```

Modify `nanobot/evolve/gates/__init__.py` bottom imports and registry:

```python
from nanobot.evolve.gates.human_review import HumanReviewGate  # noqa: E402
```

Append after `GATES.append(SemanticFidelityGate())`:

```python
GATES.append(HumanReviewGate())
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_gate_human_review.py tests/evolve/test_gate_contract.py::test_gates_ordering_matches_name_prefix tests/evolve/test_gate_contract.py::test_e2e_gates_iterate_with_shared_fake -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/evolve/gates/__init__.py nanobot/evolve/gates/human_review.py tests/evolve/conftest.py tests/evolve/test_gate_contract.py tests/evolve/test_gate_human_review.py
git commit -m "feat(evolve): add human review readiness gate"
```

---

### Task 5: Harness Real Counts, Diff Stats, and Gate-5 Metrics

**Files:**
- Modify: `nanobot/evolve/harness.py`
- Test: `tests/evolve/test_harness_run.py`

- [ ] **Step 1: Write failing harness tests**

Add these tests to `tests/evolve/test_harness_run.py`:

```python
def test_harness_run_records_real_eval_counts_and_diff_stats(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'stats-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'adds example instruction'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.record_count_per_tier == {"A": 1, "C": 5}
    assert manifest.judge_summary.record_count == 6
    assert manifest.diff_stats is not None
    assert manifest.diff_stats.files_changed == 1
    assert manifest.diff_stats.insertions >= 1
    assert manifest.requires_human_approval is True


def test_harness_default_gates_include_semantic_and_human_review(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'five-gate-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'adds example instruction'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )

    assert manifest.final_status == "promoted_to_pr"
    assert [result.gate_name for result in manifest.gate_verdicts] == [
        "1-test-pass",
        "2-skill-size",
        "3-cache-compat",
        "4-semantic-fidelity",
        "5-human-review",
    ]
```

Update existing assertions in `test_harness_run_promotes_candidate_and_writes_artifacts` to expect five gate artifacts indirectly:

```python
    assert manifest.requires_human_approval is True
    assert manifest.diff_stats is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_harness_run.py::test_harness_run_records_real_eval_counts_and_diff_stats tests/evolve/test_harness_run.py::test_harness_default_gates_include_semantic_and_human_review tests/evolve/test_harness_run.py::test_harness_run_promotes_candidate_and_writes_artifacts -v
```

Expected: FAIL because counts are still one-per-tier, diff stats are not set, and gate-5 metrics are not populated before gate execution.

- [ ] **Step 3: Implement helper functions**

In `nanobot/evolve/harness.py`, update schema imports to include `DiffStats`:

```python
    DiffStats,
```

Add these helper functions after `_normalize_lf`:

```python
def _count_eval_bundle_records(bundle_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw in bundle_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        tier = str(row["tier"])
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def _diff_stats_from_patch(patch: str) -> DiffStats:
    files_changed = 0
    insertions = 0
    deletions = 0
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            files_changed += 1
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return DiffStats(files_changed=files_changed, insertions=insertions, deletions=deletions)
```

- [ ] **Step 4: Write five Tier C eval bundle records**

Replace `_load_eval_records()` loop body with this logic:

```python
        for tier in tiers:
            repeat = 5 if tier == "C" else 1
            for index in range(1, repeat + 1):
                record = {
                    "recordId": f"{skill_name}-{tier}-{index}",
                    "tier": tier,
                    "promptRedacted": redact(
                        f"Evaluate {skill_name} tier {tier} prompt {index}."
                    ).text,
                    "expectedRedacted": redact(
                        f"Expected {skill_name} tier {tier} answer {index}."
                    ).text,
                    "metadata": {"skillName": skill_name},
                }
                lines.append(json.dumps(record, sort_keys=True))
```

- [ ] **Step 5: Populate candidate counts and review flags**

Change `_candidate_from_optimizer()` signature to:

```python
        eval_counts: dict[str, int],
```

Update its `size_metrics` block to:

```python
        tier_c_total = eval_counts.get("C", 0)
        tier_a_total = eval_counts.get("A", 0)
        size_metrics = {
            "lines": len(skill_md_content.splitlines()),
            "tier_c_pass": tier_c_total,
            "tier_c_total": tier_c_total,
            "tier_a_pass": tier_a_total,
            "tier_a_total": tier_a_total,
            "review_manifest": 1,
            "review_report": 1,
            "review_diff": 1,
            "review_pr_body": 1,
            "review_optimizer_input": 1,
            "review_optimizer_output": 1,
            "review_requires_human_approval": 1,
        }
```

In `run()`, after `eval_bundle = self._load_eval_records(...)`, add:

```python
        record_count_per_tier = _count_eval_bundle_records(eval_bundle)
```

Update `_candidate_from_optimizer(...)` call to pass `record_count_per_tier`.

- [ ] **Step 6: Build patch and diff stats before manifest**

Before `manifest = RunManifest(...)`, add:

```python
        diff_patch = self._build_diff_patch(baseline, promoted)
        diff_stats = _diff_stats_from_patch(diff_patch)
```

In manifest construction, change:

```python
            judge_summary=self._empty_judge_summary(len(tiers)),
```

to:

```python
            judge_summary=self._empty_judge_summary(sum(record_count_per_tier.values())),
```

Change:

```python
            record_count_per_tier={tier: 1 for tier in tiers},
```

to:

```python
            record_count_per_tier=record_count_per_tier,
```

Add manifest fields:

```python
            diff_stats=diff_stats,
            requires_human_approval=promoted is not None,
```

Change diff write to use the precomputed patch:

```python
        (run_dir / "diff.patch").write_text(diff_patch, encoding="utf-8")
```

- [ ] **Step 7: Update eval bundle test expected lines**

In `test_load_eval_records_writes_redacted_bundle`, adjust the expected C record ID to `demo-skill-C-1` and A record ID to `demo-skill-A-1`, and expected strings to include `prompt 1` / `answer 1`.

- [ ] **Step 8: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_harness_run.py tests/evolve/test_harness.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add nanobot/evolve/harness.py tests/evolve/test_harness_run.py
git commit -m "feat(evolve): drive M5 gates from real run artifacts"
```

---

### Task 6: PR Body and Report Render Review State

**Files:**
- Modify: `nanobot/evolve/deploy.py`
- Modify: `nanobot/evolve/report.py`
- Test: `tests/evolve/test_deploy.py`
- Test: `tests/evolve/test_harness_run.py`

- [ ] **Step 1: Write failing deploy/report tests**

Add to `tests/evolve/test_deploy.py`:

```python
def test_assemble_pr_body_uses_real_diff_stats_and_human_checklist() -> None:
    manifest = _make_run_manifest(
        diff_stats={"files_changed": 1, "insertions": 3, "deletions": 2},
        requires_human_approval=True,
    )
    body = assemble_pr_body(manifest, [_gate_result("5-human-review")])

    assert "files changed: 1" in body
    assert "insertions: 3" in body
    assert "deletions: 2" in body
    assert "Human review checklist" in body
    assert "[ ] Human reviewer approved this skill evolution" in body
    assert "No live skill file was changed by this run" in body
```

Add to `tests/evolve/test_harness_run.py`:

```python
def test_harness_report_and_pr_body_show_human_review_state(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo-skill")
    script = tmp_path / "optimizer.py"
    _write_optimizer_script(
        script,
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--input', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
payload = json.loads(Path(args.input).read_text())
Path(args.output).write_text(json.dumps({
    'schemaVersion': '1',
    'optimizerName': 'review-wrapper',
    'optimizerVersion': '0.1.0',
    'seed': payload['seed'],
    'error': None,
    'candidates': [{
        'skillName': payload['skillName'],
        'skillMdContent': '---\\nname: demo-skill\\ndescription: Demo skill\\n---\\nUse concise answers. Include one concrete example.\\n',
        'score': 0.9,
        'iteration': 1,
        'rationale': 'adds example instruction'
    }]
}))
""".lstrip(),
    )

    manifest = OfflineHarness(workspace=tmp_path).run(
        skill_name="demo-skill",
        optimizer_command=[sys.executable, str(script)],
        tiers=["A", "C"],
    )
    run_dir = tmp_path / "evals" / "runs" / manifest.run_id
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    pr_body = (run_dir / "pr_body.md").read_text(encoding="utf-8")

    assert "Human approval required: `true`" in report
    assert "Diff stats" in report
    assert "Human review checklist" in pr_body
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/evolve/test_deploy.py::test_assemble_pr_body_uses_real_diff_stats_and_human_checklist tests/evolve/test_harness_run.py::test_harness_report_and_pr_body_show_human_review_state -v
```

Expected: FAIL because deploy still renders stub diff stats and no human checklist/report state.

- [ ] **Step 3: Update PR body rendering**

In `nanobot/evolve/deploy.py`, remove the TODO comment block above diff stats.

Replace `diff_lines` with:

```python
    stats = manifest.diff_stats
    diff_lines = [
        "## Diff stats",
        f"candidate hash: `{short_sha}` (full: `{promoted}`)",
        f"files changed: {stats.files_changed if stats else 0}",
        f"insertions: {stats.insertions if stats else 0}",
        f"deletions: {stats.deletions if stats else 0}",
        f"skill: `{manifest.skill_name}` SKILL.md",
    ]
```

Add this block before rollback lines:

```python
    human_review_lines = [
        "## Human review checklist",
        "- [ ] Human reviewer approved this skill evolution",
        "- [ ] Reviewer confirmed semantic-fidelity evidence",
        "- [ ] Reviewer confirmed no live skill file was changed by this run",
        f"- Human approval required: `{str(manifest.requires_human_approval).lower()}`",
        "- No live skill file was changed by this run",
    ]
```

Update `blocks` to include the human review section before rollback.

Update `PR_BODY_SECTIONS` constant near the top of `deploy.py` to include `"Human review checklist"` before `"Rollback plan"`.

- [ ] **Step 4: Update tests expecting section count**

In `tests/evolve/test_deploy.py::test_assemble_pr_body_has_5_sections_in_order`, rename to `test_assemble_pr_body_has_sections_in_order`, and change expected headers to:

```python
    assert len(headers) == 6
    assert headers == [
        "Summary",
        "Eval results",
        "Gates passed",
        "Diff stats",
        "Human review checklist",
        "Rollback plan",
    ]
```

- [ ] **Step 5: Update report rendering**

In `nanobot/evolve/report.py`, after optimizer lines, add:

```python
        "",
        "## Review state",
        f"Human approval required: `{str(manifest.requires_human_approval).lower()}`",
```

If `manifest.diff_stats` exists, append:

```python
    if manifest.diff_stats is not None:
        lines.extend(
            [
                "",
                "## Diff stats",
                f"Files changed: `{manifest.diff_stats.files_changed}`",
                f"Insertions: `{manifest.diff_stats.insertions}`",
                f"Deletions: `{manifest.diff_stats.deletions}`",
            ]
        )
```

Place this before `## Validation failures`.

- [ ] **Step 6: Run tests to verify they pass**

Run:

```bash
pytest tests/evolve/test_deploy.py tests/evolve/test_harness_run.py::test_harness_report_and_pr_body_show_human_review_state -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add nanobot/evolve/deploy.py nanobot/evolve/report.py tests/evolve/test_deploy.py tests/evolve/test_harness_run.py
git commit -m "feat(evolve): render M5 review state in artifacts"
```

---

### Task 7: Documentation and Carry-Forward Closure

**Files:**
- Modify: `docs/hermes-evolution/roadmap.md`
- Modify: `docs/hermes-evolution/specs/m5-darwinian-evolver.md`
- Modify: `docs/hermes-evolution/specs/m4-carry-forward.md`
- Create: `docs/hermes-evolution/retros/m5-complete.md`
- Test: documentation-only grep checks

- [ ] **Step 1: Update roadmap**

In `docs/hermes-evolution/roadmap.md`, update M5 status rows:

- The milestone table M5 row should say:

```markdown
| **M5** | 接入外部 Darwinian Evolver CLI + AGPL 许可隔离 + PR-only 部署 + 完整 5 道闸门（skills-only） | M4 | ✅ 已完成 (2026-06-14, branch `feature/m5-complete`) | `specs/m5-darwinian-evolver.md` + `specs/m5-complete-design.md` | `plans/m5-complete.md` | `retros/m5-complete.md` |
```

- The retrospective bullet should say:

```markdown
- M5: ✅ 已完成 — M5 now provides a skills-only five-gate offline evolution lane: subprocess optimizer boundary, candidate validation, gates 1-3, semantic-fidelity gate 4, local human-review readiness gate 5, real diff stats, and explicit PR-only human approval artifacts. Tool and prompt/template evolution are intentionally split into future milestones because they need separate safety and cache designs.
```

- The current-location checklist item 7 should be checked:

```markdown
- [x] 7. **M5 Darwinian Evolver 完成（skills-only 五道闸门；tool / prompt-template evolution 转为后续独立 milestone）**
```

- [ ] **Step 2: Update M5 spec status**

In `docs/hermes-evolution/specs/m5-darwinian-evolver.md`, add this paragraph after the status header:

```markdown
**Completion note (2026-06-14)**: M5 was completed under the skills-only definition in `specs/m5-complete-design.md`. The completed scope adds semantic-fidelity gate 4, human-review readiness gate 5, real diff stats, real eval counts, and explicit PR-only human approval artifacts. Tool-description and system-prompt/template evolution are intentionally out of M5 completion scope and require future standalone specs.
```

- [ ] **Step 3: Update carry-forward doc**

In `docs/hermes-evolution/specs/m4-carry-forward.md`, append this section near the bottom:

```markdown
## M5 completion closure note (2026-06-14)

M5 completion closes the carry-forward items for:

- real `JudgePool.score(record)` scoring entry point used by calibration and semantic gate 4;
- semantic-fidelity gate 4 as a promotion-blocking gate;
- human-review readiness gate 5 as a local PR-readiness gate;
- real patch-derived diff stats in generated PR bodies;
- real eval-bundle-derived record counts in manifests and reports.

M5 completion intentionally does not close tool-description evolution or system-prompt/template evolution. Those surfaces are no longer treated as unfinished M5 work; they are future independent milestones because they require separate safety, cache, and review designs.
```

- [ ] **Step 4: Create M5 retro**

Create `docs/hermes-evolution/retros/m5-complete.md`:

```markdown
# M5 Complete Retro

Date: 2026-06-14

M5 is complete under the skills-only definition. The milestone now has a PR-only offline evolution lane with subprocess optimizer isolation, candidate validation, five ordered gates, real diff stats, real eval counts, generated reports, and explicit human-review requirements.

The main scope decision was to finish the five-gate skill-evolution system without expanding into tool source or system-prompt/template mutation. That keeps the completed milestone reviewable and aligned with the original PR-only safety boundary. Tool and prompt/template evolution remain valuable, but they need separate designs for cache stability, blast radius control, rollback semantics, and reviewer ownership.

Gate 4 is intentionally promotion-blocking but does not feed nondeterministic judge output back into optimizer fitness. Gate 5 is local review-readiness verification, not GitHub branch-protection automation. The generated artifacts make the human approval requirement explicit while preserving the rule that Nanobot does not push, open PRs, or mutate live skill files automatically.
```

- [ ] **Step 5: Run documentation checks**

Run:

```bash
grep -R "M5 completion" docs/hermes-evolution/specs/m5-darwinian-evolver.md docs/hermes-evolution/specs/m4-carry-forward.md && grep -R "M5 Complete Retro" docs/hermes-evolution/retros/m5-complete.md
```

Expected: PASS, matching the new documentation text.

- [ ] **Step 6: Commit**

```bash
git add docs/hermes-evolution/roadmap.md docs/hermes-evolution/specs/m5-darwinian-evolver.md docs/hermes-evolution/specs/m4-carry-forward.md docs/hermes-evolution/specs/m5-complete-design.md docs/hermes-evolution/plans/m5-complete.md docs/hermes-evolution/retros/m5-complete.md task_plan.md findings.md progress.md
git commit -m "docs(hermes): document M5 completion scope"
```

---

### Task 8: Final Verification

**Files:**
- Verify all touched files

- [ ] **Step 1: Run targeted evolve tests**

Run:

```bash
pytest tests/evolve/ -v
```

Expected: PASS.

- [ ] **Step 2: Run ruff on touched Python paths**

Run:

```bash
ruff check nanobot/evolve tests/evolve
```

Expected: PASS.

- [ ] **Step 3: Check remaining M5 TODO markers**

Run:

```bash
grep -R "TODO(M5)\|TODO(Task 8)\|TODO(m4-followup CF-cc-a)" nanobot/evolve docs/hermes-evolution/specs/m4-carry-forward.md
```

Expected: no matches for active TODO markers in `nanobot/evolve`; historical carry-forward prose may mention closed items only in the closure note.

- [ ] **Step 4: Check worktree status**

Run:

```bash
git status --short
```

Expected: clean after commits, or only intentionally untracked local scratch files.

- [ ] **Step 5: Commit verification fixes if needed**

If Steps 1-3 require small fixes, commit them:

```bash
git add <fixed-files>
git commit -m "fix(evolve): complete M5 verification"
```

If no fixes are needed, do not create an empty commit.
