# Plan: M4 offline skeleton

## Context

- **Spec**: [`docs/hermes-evolution/specs/m4-offline-skeleton.md`](../specs/m4-offline-skeleton.md) @ commit `ab5445cb` (3512 lines, C-rev19 locked; ~127 decisions).
- **Sibling CF**: [`docs/hermes-evolution/specs/m4-carry-forward.md`](../specs/m4-carry-forward.md). This plan does **not** close any CF entries.
- **Branch**: `feature/m4-offline-skeleton`.
- **Date**: 2026-06-12.
- **Task count**: 19 tasks.
- **Parallel groups**: 8 groups.
- **smoke_cmd_hint**: `pytest -x tests/evolve/ --timeout=30` (Python project per `AGENTS.md`).
- **Working mode**: small-steps-fast-pace — each task 2–5 min for an implementer; tight serialization only where a downstream symbol is imported.

## Project Context (≤200 words; for worker prompts)

nanobot is a Python 3.11+ async AI-agent framework. M4 introduces the `nanobot/evolve/` offline skeleton: DSPy + GEPA bootstrap, 4-tier eval corpus (A synthetic / B SessionDB-anonymized / C curated / D self-eval), judge pool (3-axis rubric 0–1 with weights process=0.4 / output=0.4 / token=0.2, sum-to-one), three deterministic gates (1-test-pass / 2-size-cap / 3-cache-compat), gate orchestration harness, 4-stage redaction (PII / apikey / file-path / custom), PR-only deploy with squash-merge mandate, and `nanobot evolve {init,run,report,apply}` CLI. M5 will add gates 4–5 (LLM-judge + human-review async) and the Darwinian evolver. House style: ruff (E, F, I, N, W; line-length 100; E501 ignored), pytest with `asyncio_mode = "auto"`, Pydantic v2 with `extra="forbid"` + `alias_generator=to_camel`. All runtime models inherit `EvolveBase` from `nanobot/evolve/_base.py`; `RubricScore`/`RubricWeights` live in `nanobot/evolve/schemas.py` (zero-extra-deps). DSPy / GEPA imports must be lazy-guarded behind `EvolveExtraNotInstalled`. **No code may push to `main`**; PR-only via REST API.

## File map

| File | Status | Responsibility |
|---|---|---|
| `nanobot/evolve/__init__.py` | new | Public API exports (§5; lazy-guarded; never crashes on missing extra) |
| `nanobot/evolve/_base.py` | new | `EvolveBase` Pydantic v2 base (`extra="forbid"`, `alias_generator=to_camel`, `populate_by_name=True`, `frozen=False`) per §3.0 |
| `nanobot/evolve/schemas.py` | new | `RubricScore`, `RubricWeights` (`_sum_to_one`), `_assert_odd_pool_size` helper — zero extra deps (§3.3, decisions #87/#93) |
| `nanobot/evolve/exceptions.py` | new | `EvolveError` mixin with `__init_subclass__` STRUCTURED_KWARGS subset check + concrete exceptions (§5.3) |
| `nanobot/evolve/data/__init__.py` | new | `EvalRecord` Pydantic model + 4-tier loaders (§3.1) |
| `nanobot/evolve/judges/__init__.py` | new | Re-export `JudgeConfig` / `JudgePool` / `JudgeResult` / `JudgeConsensus` |
| `nanobot/evolve/judges/rubric.py` | new | `JudgeConfig`, `JudgeResult`, `JudgeConsensus`, `JudgePool` with `_odd_pool_only`, `_validate_quorum_bounds`, `effective_min_quorum` (§3.3) |
| `nanobot/evolve/judges/calibration.py` | new | Cohen κ ≥ 0.6 calibration runner (§7.3 / §7.4) |
| `nanobot/evolve/gates/_constants.py` | new | Cross-gate constants: `GATE_TIMEOUT_MS_HARD`, `SKILL_LINE_HARD_CAP`, `SKILL_LINE_DELTA_CAP`, `RUBRIC_PASS_THRESHOLD`, `TIER_A_PASS_RATE_FLOOR_BPS`, `TIER_C_PASS_RATE_FLOOR_BPS`, `PER_RECORD_TIMEOUT_S` (§6.0 + §6.1 + decisions #111, #115, RF-4 owner) |
| `nanobot/evolve/gates/__init__.py` | new | `Gate` ABC, `GateResult` Pydantic model, `__init_subclass__` populating `_subclasses`, `GATES` list (§3.6) |
| `nanobot/evolve/gates/test_pass.py` | new | `TestPassGate` (gate 1, judge-driven, tier-C strict + tier-A rate floor) (§6.1) |
| `nanobot/evolve/gates/skill_size.py` | new | `SkillSizeGate` (gate 2, lines hard cap + delta cap) (§6.2) |
| `nanobot/evolve/gates/cache_compat.py` | new | `CacheCompatGate` (gate 3, byte-equivalence on stable segment) (§6.3) |
| `nanobot/evolve/harness.py` | new | `OfflineHarness` skeleton + `_run_gates` + `Candidate` / `Baseline` / `SkillContent` / `SkillFrontmatter` / `RunManifest` / `JudgeSummary` + `_compute_final_status` (§3.2 / §3.7 / §6.0 / §6.5) |
| `nanobot/evolve/privacy/__init__.py` | new | Privacy submodule namespace |
| `nanobot/evolve/privacy/redact.py` | new | 4-stage redaction pipeline + per-row sidecar manifest + abort-on-fail (§9.2 / §9.3 / §9.4) |
| `nanobot/evolve/pipeline.py` | new | DSPy + GEPA lazy-import bootstrap; `_lazy_import_gepa()` raising `EvolveExtraNotInstalled` (§3.5.1 + §1) |
| `nanobot/evolve/deploy.py` | new | PR-only deploy stub: branch-naming `evolve/<auto-id>`, hard-check `branch != main`, REST API `POST /pulls`, 5-section PR body assembly, squash-merge precondition (§8) |
| `nanobot/cli/evolve.py` | new | `nanobot evolve {init,run,report,apply}` argparse subcommands + dispatch with handler-order per `MUST_PRECEDE` (§4) |
| `nanobot/cli/commands.py` | modify | Register `evolve` subcommand parser into the existing CLI router |
| `tests/evolve/__init__.py` | new | Test package marker |
| `tests/evolve/test_schemas.py` | new | `RubricScore`, `RubricWeights`, `_assert_odd_pool_size` unit tests |
| `tests/evolve/test_exceptions.py` | new | `EvolveError.__init_subclass__` STRUCTURED_KWARGS subset semantics (positive + negative fixtures per §5.3 test 8) |
| `tests/evolve/test_data.py` | new | `EvalRecord` schema + tier loader smoke |
| `tests/evolve/test_judges.py` | new | `JudgePool` odd-pool, quorum bounds, `effective_min_quorum` |
| `tests/evolve/test_gate_contract.py` | new | §6.4.1 dual-filter assertion (`__module__` prefix + `inspect.isabstract`) on `Gate._subclasses` vs `GATES` |
| `tests/evolve/test_gate_test_pass.py` | new | `TestPassGate` precondition + judge-driven verdict |
| `tests/evolve/test_gate_skill_size.py` | new | `SkillSizeGate` hard-cap + delta-cap |
| `tests/evolve/test_gate_cache_compat.py` | new | `CacheCompatGate` pass/fail + `evidence` always carrying both hashes |
| `tests/evolve/test_harness.py` | new | `_run_gates` short-circuit + manifest construction + `_compute_final_status` decision tree |
| `tests/evolve/test_redact.py` | new | 4-stage pipeline; abort-on-fail; per-row sidecar fields |
| `tests/evolve/test_redact_no_false_positive.py` | new | Regression: `claude-3-5-sonnet` model id MUST NOT be redacted as apikey (§9.2 stage 2 note) |
| `tests/evolve/test_calibration.py` | new | Cohen κ ≥ 0.6 helper produces FAIL when κ < 0.6 |
| `tests/evolve/test_deploy.py` | new | Deploy stub hard-checks `branch != main`; assembles 5-section body |
| `tests/evolve/test_cli_evolve.py` | new | argparse subcommand registration; help text present |
| `tests/evolve/test_pipeline_integration.py` | new | End-to-end smoke: harness builds manifest with stub baseline + stub candidate without invoking DSPy |
| `docs/hermes-evolution/roadmap.md` | modify | Mark M4 in-progress with commit ref (no PR link yet) |

## Tasks

### t-01: scaffold `__init__.py` + `_base.py` + `exceptions.py`

- **Spec**: §3.0, §5.3.
- **Files**: `nanobot/evolve/__init__.py`, `nanobot/evolve/_base.py`, `nanobot/evolve/exceptions.py`, `tests/evolve/__init__.py`, `tests/evolve/test_exceptions.py`.
- **Definition of done**:
  - `from nanobot.evolve import EvolveError` succeeds even without `dspy`/`gepa` installed.
  - `pytest -x tests/evolve/test_exceptions.py` passes; covers both subset-positive and subset-negative `STRUCTURED_KWARGS` cases.
  - `ruff check nanobot/evolve/__init__.py nanobot/evolve/_base.py nanobot/evolve/exceptions.py` clean.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/_base.py
  from pydantic import BaseModel, ConfigDict
  from pydantic.alias_generators import to_camel

  class EvolveBase(BaseModel):
      model_config = ConfigDict(
          extra="forbid",
          alias_generator=to_camel,
          populate_by_name=True,
          frozen=False,
      )
  ```
  ```python
  # nanobot/evolve/exceptions.py — keep verbatim spec §5.3 shapes
  import inspect
  from typing import TYPE_CHECKING, ClassVar
  if TYPE_CHECKING:
      from pathlib import Path

  class EvolveError:
      def __init_subclass__(cls, **kwargs):
          super().__init_subclass__(**kwargs)
          declared = cls.__dict__.get("STRUCTURED_KWARGS")
          if declared is None:
              for base in cls.__mro__[1:]:
                  if base is EvolveError:
                      continue
                  if "STRUCTURED_KWARGS" in base.__dict__:
                      raise TypeError(
                          f"{cls.__name__}: parent {base.__name__} declares STRUCTURED_KWARGS; "
                          f"subclasses MUST redeclare their own STRUCTURED_KWARGS."
                      )
              return
          if not isinstance(declared, frozenset):
              raise TypeError(f"{cls.__name__}.STRUCTURED_KWARGS must be frozenset[str]")
          sig = inspect.signature(cls.__init__)
          kw_only = {n for n, p in sig.parameters.items() if p.kind is inspect.Parameter.KEYWORD_ONLY}
          if not set(declared).issubset(kw_only):
              missing = set(declared) - kw_only
              raise TypeError(
                  f"{cls.__name__}: STRUCTURED_KWARGS={set(declared)!r} contains {missing!r} "
                  f"not in __init__ kw-only params={kw_only!r}"
              )

  class EvolveExtraNotInstalled(EvolveError, ImportError):
      INSTALL_HINT = "pip install nanobot[evolve]"

  class BaselineMismatch(EvolveError, ValueError): ...

  class ApplyTerminalError(EvolveError, ValueError):
      STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"final_status", "manifest_path"})
      MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"ValueError", "ConfigError"})
      def __init__(self, message: str, *, final_status: str, manifest_path: "Path") -> None:
          super().__init__(message)
          self.final_status = final_status
          self.manifest_path = manifest_path

  class JudgeError(EvolveError, RuntimeError):
      MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

  class ManifestPrivacyViolation(EvolveError, RuntimeError):
      STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"violated_invariant"})
      MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})
      def __init__(self, message: str, *, violated_invariant: str,
                   offending_path: "Path | None" = None,
                   offending_fields: "list[str] | None" = None) -> None:
          super().__init__(message)
          self.violated_invariant = violated_invariant
          self.offending_path = offending_path
          self.offending_fields = offending_fields or []

  class EvolveEnvironmentError(EvolveError, RuntimeError):
      STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()
      MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

  class ConfigError(EvolveError, ValueError): ...
  ```
  ```python
  # nanobot/evolve/__init__.py
  """nanobot.evolve — M4 offline skeleton (DSPy + GEPA).

  Lazy: importing this package MUST succeed without DSPy/GEPA installed
  (per §3.5.1 lazy-guard contract). Heavy bits live behind function-local imports.
  """
  from nanobot.evolve.exceptions import (
      EvolveError, EvolveExtraNotInstalled, BaselineMismatch,
      ApplyTerminalError, JudgeError, ManifestPrivacyViolation,
      EvolveEnvironmentError, ConfigError,
  )
  __all__ = [
      "EvolveError", "EvolveExtraNotInstalled", "BaselineMismatch",
      "ApplyTerminalError", "JudgeError", "ManifestPrivacyViolation",
      "EvolveEnvironmentError", "ConfigError",
  ]
  ```
- **Commands**:
  - `ruff check nanobot/evolve/__init__.py nanobot/evolve/_base.py nanobot/evolve/exceptions.py`
  - `pytest -x tests/evolve/test_exceptions.py`
- **Review focus**: correctness (subset semantics — `ManifestPrivacyViolation` MUST import successfully).

### t-02: gate constants module

- **Spec**: §6.0 point 5, §6.1 (thresholds), §6.2.2, §7.2, decision #111, RF-4 owner note in §14.
- **Files**: `nanobot/evolve/gates/_constants.py`.
- **Definition of done**:
  - `from nanobot.evolve.gates._constants import GATE_TIMEOUT_MS_HARD, SKILL_LINE_HARD_CAP, SKILL_LINE_DELTA_CAP, RUBRIC_PASS_THRESHOLD, TIER_A_PASS_RATE_FLOOR_BPS, TIER_C_PASS_RATE_FLOOR_BPS, PER_RECORD_TIMEOUT_S` succeeds.
  - `ruff check nanobot/evolve/gates/_constants.py` clean.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/gates/_constants.py
  """Shared spec-locked gate constants. Owner: M5 round-A Arch reviewer (RF-4)."""
  # Derivation: ceil(TIER_C_FLOOR=5) × PER_RECORD_TIMEOUT_S=30 s × SLACK≈4 × 1000 ms/s = 600_000 ms.
  GATE_TIMEOUT_MS_HARD: int = 600_000

  # Gate 2 (§6.2.2)
  SKILL_LINE_HARD_CAP: int = 400
  SKILL_LINE_DELTA_CAP: int = 150

  # Gate 1 (§6.1.1 / §6.1.2)
  PER_RECORD_TIMEOUT_S: int = 30
  TIER_A_PASS_RATE_FLOOR_BPS: int = 80   # 80/100 = 0.80
  TIER_C_PASS_RATE_FLOOR_BPS: int = 100  # 100/100 = 1.00

  # Judge rubric (§7.2, decision #124)
  RUBRIC_PASS_THRESHOLD: float = 0.6
  ```
- **Commands**:
  - `ruff check nanobot/evolve/gates/_constants.py`
  - `python -c "from nanobot.evolve.gates._constants import GATE_TIMEOUT_MS_HARD; assert GATE_TIMEOUT_MS_HARD == 600_000"`
- **Review focus**: correctness (constant values verbatim from spec).

### t-03: 4-tier data model + loader scaffold

- **Spec**: §3.1.
- **Files**: `nanobot/evolve/data/__init__.py`, `tests/evolve/test_data.py`.
- **Definition of done**:
  - `EvalRecord` Pydantic model with the 9 fields from spec §3.1.1.
  - `load_tier(tier: Literal["A","B","C","D"], skill_name: str, root: Path) -> list[EvalRecord]` joins `input.jsonl` + `expected.jsonl` by `record_id`.
  - `pytest -x tests/evolve/test_data.py` passes (uses a tmp_path with 2 records).
- **Exact code or signature**:
  ```python
  # nanobot/evolve/data/__init__.py
  from datetime import datetime
  from pathlib import Path
  from typing import Iterator, Literal, Optional
  import json

  from pydantic import Field
  from nanobot.evolve._base import EvolveBase

  class EvalRecord(EvolveBase):
      record_id: str
      tier: Literal["A", "B", "C", "D"]
      skill_name: str
      input: dict
      expected: Optional[dict] = None
      match_mode: Literal["loose", "strict", "judge_only", "binary_verdict"]
      privacy_class: Literal["public", "private"]
      created_at: datetime
      source: str
      tags: list[str] = Field(default_factory=list)

  def load_tier(tier: Literal["A","B","C","D"], skill_name: str, root: Path) -> list[EvalRecord]:
      """Read paired input.jsonl + expected.jsonl, join by record_id."""
      # body deferred to implementer — must respect § 3.1 'join by record_id, not by line number'
  ```
- **Commands**:
  - `ruff check nanobot/evolve/data/`
  - `pytest -x tests/evolve/test_data.py`
- **Review focus**: data-integrity (record_id join not line-order).

### t-04: schemas — `RubricScore` / `RubricWeights` / parity helper

- **Spec**: §3.3 (lines 466–527), decisions #84, #87, #93.
- **Files**: `nanobot/evolve/schemas.py`, `tests/evolve/test_schemas.py`.
- **Definition of done**:
  - `RubricWeights()` defaults sum to 1.0 (0.4 + 0.4 + 0.2).
  - `RubricWeights(process=0.5, output=0.5, token=0.5)` raises with sum=1.5 message.
  - `_assert_odd_pool_size(2, context="x")` raises; `_assert_odd_pool_size(3, context="x")` returns None.
  - `pytest -x tests/evolve/test_schemas.py` passes (≥4 assertions).
- **Exact code or signature**:
  ```python
  # nanobot/evolve/schemas.py
  from pydantic import Field, model_validator
  from nanobot.evolve._base import EvolveBase

  class RubricScore(EvolveBase):
      process: float = Field(ge=0.0, le=1.0)
      output: float = Field(ge=0.0, le=1.0)
      token: float = Field(ge=0.0, le=1.0)
      aggregate: float = Field(ge=0.0, le=1.0)

  class RubricWeights(EvolveBase):
      process: float = Field(default=0.4, ge=0.0, le=1.0)
      output: float = Field(default=0.4, ge=0.0, le=1.0)
      token: float = Field(default=0.2, ge=0.0, le=1.0)

      @model_validator(mode="after")
      def _sum_to_one(self) -> "RubricWeights":
          s = self.process + self.output + self.token
          if abs(s - 1.0) > 1e-6:
              raise ValueError(
                  f"RubricWeights must sum to 1.0 (got {s:.6f}); "
                  f"process={self.process}, output={self.output}, token={self.token}"
              )
          return self

  def _assert_odd_pool_size(n: int, *, context: str) -> None:
      if n == 0 or n % 2 == 0:
          raise ValueError(
              f"{context}: judge pool size must be odd and >= 1 (got {n})"
          )
  ```
- **Commands**:
  - `ruff check nanobot/evolve/schemas.py`
  - `pytest -x tests/evolve/test_schemas.py`
- **Review focus**: correctness (sum-to-one + odd-pool both have positive and negative coverage).

### t-05: judge pool — `JudgeConfig` / `JudgePool` / `JudgeResult` / `JudgeConsensus`

- **Spec**: §3.3 (lines 530–680), decisions #81, #86, #89.
- **Files**: `nanobot/evolve/judges/__init__.py`, `nanobot/evolve/judges/rubric.py`, `tests/evolve/test_judges.py`.
- **Definition of done**:
  - `JudgePool(judges=[JudgeConfig(model="anthropic/claude-3-5-sonnet"), JudgeConfig(model="openai/gpt-4o"), JudgeConfig(model="google/gemini-pro")])` constructs successfully; `effective_min_quorum == 2`.
  - `JudgePool(judges=[a, b])` raises (even pool size).
  - `JudgePool(judges=[a, b, c], min_quorum=5)` raises (quorum > len).
  - `pytest -x tests/evolve/test_judges.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/judges/rubric.py
  from datetime import datetime
  from typing import Literal
  from pydantic import ConfigDict, Field, computed_field, field_validator, model_validator

  from nanobot.evolve._base import EvolveBase
  from nanobot.evolve.schemas import RubricScore, RubricWeights, _assert_odd_pool_size

  class JudgeConfig(EvolveBase):
      model: str

  class JudgeResult(EvolveBase):
      eval_record_id: str
      judge_model: str
      score: RubricScore
      reasoning: str
      timestamp: datetime
      prompt_template_version: str

  class JudgeConsensus(EvolveBase):
      eval_record_id: str
      judges: list[JudgeResult]
      median_score: RubricScore
      inter_judge_variance: dict[str, float]
      consensus_verdict: Literal["agree", "split", "single"]

  class JudgePool(EvolveBase):
      model_config = ConfigDict(
          extra="forbid",
          alias_generator=EvolveBase.model_config["alias_generator"],
          populate_by_name=True,
          frozen=True,
      )
      judges: list[JudgeConfig] = Field(..., min_length=1)
      weights: RubricWeights = Field(default_factory=RubricWeights)
      require_consensus: bool = False
      min_quorum: int | None = Field(default=None, ge=1)

      @model_validator(mode="after")
      def _validate_quorum_bounds(self) -> "JudgePool":
          if self.min_quorum is not None and self.min_quorum > len(self.judges):
              raise ValueError(
                  f"JudgePool.min_quorum={self.min_quorum} exceeds len(judges)={len(self.judges)}"
              )
          return self

      @field_validator("judges")
      @classmethod
      def _odd_pool_only(cls, v: list[JudgeConfig]) -> list[JudgeConfig]:
          _assert_odd_pool_size(len(v), context="JudgePool.judges")
          return v

      @computed_field  # type: ignore[misc]
      @property
      def effective_min_quorum(self) -> int:
          if self.min_quorum is not None:
              return self.min_quorum
          return (len(self.judges) // 2) + 1
  ```
  ```python
  # nanobot/evolve/judges/__init__.py
  from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool, JudgeResult, JudgeConsensus
  __all__ = ["JudgeConfig", "JudgePool", "JudgeResult", "JudgeConsensus"]
  ```
- **Commands**:
  - `ruff check nanobot/evolve/judges/`
  - `pytest -x tests/evolve/test_judges.py`
- **Review focus**: correctness (frozen=True; `effective_min_quorum` formula).

### t-06: `Gate` ABC + `GateResult` + `GATES` registry

- **Spec**: §3.6 (lines 800–911), decisions #117, #122.
- **Files**: `nanobot/evolve/gates/__init__.py`.
- **Definition of done**:
  - `from nanobot.evolve.gates import Gate, GateResult, GATES` imports succeed and `GATES == []` (gates appended later in their own modules' import side-effect via t-08..t-10).
  - `Gate.NONDETERMINISTIC` ClassVar default `False`; `Gate._subclasses` exists as list.
  - `ruff check nanobot/evolve/gates/__init__.py` clean.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/gates/__init__.py
  from abc import ABC, abstractmethod
  from datetime import datetime
  from typing import ClassVar, Literal, Optional, TYPE_CHECKING
  from nanobot.evolve._base import EvolveBase

  if TYPE_CHECKING:
      from nanobot.evolve.harness import Candidate, Baseline

  class GateResult(EvolveBase):
      gate_name: str
      candidate_hash: str
      baseline_hash: str
      verdict: Literal["pass", "fail"]
      metrics: dict[str, float]
      evidence: Optional[dict[str, str]] = None
      failure_reason: Optional[str] = None
      timestamp: datetime
      duration_ms: int

  class Gate(ABC):
      NONDETERMINISTIC: ClassVar[bool] = False
      _subclasses: ClassVar[list[type["Gate"]]] = []

      def __init_subclass__(cls, **kwargs: object) -> None:
          super().__init_subclass__(**kwargs)
          Gate._subclasses.append(cls)

      @property
      @abstractmethod
      def name(self) -> str: ...

      @abstractmethod
      def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult: ...

  GATES: list[Gate] = []  # populated by import side-effect from concrete gate modules
  # Note: concrete imports added at the bottom AFTER gates land (t-08..t-10).
  ```
- **Commands**:
  - `ruff check nanobot/evolve/gates/__init__.py`
  - `python -c "from nanobot.evolve.gates import Gate, GateResult, GATES; assert isinstance(GATES, list)"`
- **Review focus**: correctness (`__init_subclass__` populates `_subclasses` at class-body time).

### t-07: gate contract test (dual-filter)

- **Spec**: §6.4.1 (lines 3181–3201), decision #122.
- **Files**: `tests/evolve/test_gate_contract.py`.
- **Definition of done**:
  - Test imports `from nanobot.evolve.gates import Gate, GATES` and runs the dual-filter assertion.
  - Test passes after t-08/t-09/t-10 land (initially fails — that's TDD-correct; the implementer runs it after the three gate modules exist).
- **Exact code or signature**:
  ```python
  # tests/evolve/test_gate_contract.py
  import inspect
  from nanobot.evolve.gates import Gate, GATES
  # Force submodule imports (registers concrete gates into GATES + _subclasses).
  import nanobot.evolve.gates.test_pass  # noqa: F401
  import nanobot.evolve.gates.skill_size  # noqa: F401
  import nanobot.evolve.gates.cache_compat  # noqa: F401

  def test_gates_ordering_matches_name_prefix():
      for i, gate in enumerate(GATES):
          assert gate.name.startswith(f"{i+1}-"), (i, gate.name)

  def test_no_orphan_gate_subclass():
      production_subclasses = {
          c for c in Gate._subclasses
          if c.__module__.startswith("nanobot.evolve.gates.")
          and not inspect.isabstract(c)
      }
      registered = {type(g) for g in GATES}
      orphans = production_subclasses - registered
      assert not orphans, f"orphan production gate subclass(es): {orphans}"
  ```
- **Commands**:
  - `pytest -x tests/evolve/test_gate_contract.py`
- **Review focus**: correctness (both filters applied; orphan detection works).

### t-08: `TestPassGate` (gate 1)

- **Spec**: §6.1 (lines 2943–3055), decisions #115, #119, #120, #121.
- **Files**: `nanobot/evolve/gates/test_pass.py`, `tests/evolve/test_gate_test_pass.py`. Also append to `nanobot/evolve/gates/__init__.py` after `GATES = []`: `from nanobot.evolve.gates.test_pass import TestPassGate; GATES.append(TestPassGate())`.
- **Definition of done**:
  - `TestPassGate().name == "1-test-pass"`.
  - Precondition: `len(tier_c) < 5` raises (gate-internal error → fail verdict in harness; here the gate raises the inner exception which `_run_gates` will wrap).
  - Integer cross-multiplication path: `tier_c_pass=5, tier_c_total=5, tier_a_pass=20, tier_a_total=25` → pass; `tier_a_pass=17, tier_a_total=25` → fail with `failure_reason` starts `"tier-a-rate-floor"`.
  - `pytest -x tests/evolve/test_gate_test_pass.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/gates/test_pass.py
  from datetime import datetime, timezone
  from typing import TYPE_CHECKING
  from nanobot.evolve.gates import Gate, GateResult
  from nanobot.evolve.gates._constants import (
      GATE_TIMEOUT_MS_HARD, PER_RECORD_TIMEOUT_S,
      TIER_A_PASS_RATE_FLOOR_BPS, TIER_C_PASS_RATE_FLOOR_BPS,
  )
  if TYPE_CHECKING:
      from nanobot.evolve.harness import Candidate, Baseline

  class TestPassGate(Gate):
      @property
      def name(self) -> str: return "1-test-pass"

      def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
          # M4 skeleton: harness wires real tier loaders in t-11. Here we accept
          # optional pre-loaded counts via candidate attrs for testability OR
          # return a `pass` stub when no records are present. Real loop body
          # follows §6.1.2 (precondition + per-record subprocess + budget check).
          # Implementer fills loop body; the contract this skeleton MUST satisfy
          # is: returns GateResult with all required fields populated.
          ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/gates/test_pass.py`
  - `pytest -x tests/evolve/test_gate_test_pass.py`
- **Review focus**: correctness, performance (integer cross-multiplication avoids FP wobble per decision #115).
- **smoke_cmd_hint**: `pytest -x tests/evolve/test_gate_test_pass.py tests/evolve/test_gate_contract.py`.

### t-09: `SkillSizeGate` (gate 2)

- **Spec**: §6.2 (lines 3057–3117).
- **Files**: `nanobot/evolve/gates/skill_size.py`, `tests/evolve/test_gate_skill_size.py`. Also append to `nanobot/evolve/gates/__init__.py`: `from nanobot.evolve.gates.skill_size import SkillSizeGate; GATES.append(SkillSizeGate())`.
- **Definition of done**:
  - `SkillSizeGate().name == "2-size-cap"`.
  - `count_lines("a\r\nb\r\nc")` returns 3 (CRLF normalised).
  - `candidate.size_metrics["lines"]=480, baseline=300` → verdict fail, `failure_reason` starts `"hard-cap-exceeded"`.
  - `candidate=380, baseline=180` → fail, `failure_reason` starts `"delta-cap-exceeded"` (delta=200 > 150).
  - `candidate=380, baseline=300` → pass (delta=80, under both caps).
  - `pytest -x tests/evolve/test_gate_skill_size.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/gates/skill_size.py
  import time
  from datetime import datetime, timezone
  from typing import TYPE_CHECKING
  from nanobot.evolve.gates import Gate, GateResult
  from nanobot.evolve.gates._constants import SKILL_LINE_HARD_CAP, SKILL_LINE_DELTA_CAP
  if TYPE_CHECKING:
      from nanobot.evolve.harness import Candidate, Baseline

  def count_lines(content: str) -> int:
      normalized = content.replace("\r\n", "\n").replace("\r", "\n")
      return len(normalized.splitlines())

  class SkillSizeGate(Gate):
      @property
      def name(self) -> str: return "2-size-cap"

      def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
          t0 = time.perf_counter_ns()
          cl = candidate.size_metrics["lines"]
          bl = baseline.size_metrics["lines"]
          delta = cl - bl
          metrics = {
              "candidate_lines": float(cl), "baseline_lines": float(bl),
              "delta_lines": float(delta),
              "hard_cap": float(SKILL_LINE_HARD_CAP),
              "delta_cap": float(SKILL_LINE_DELTA_CAP),
          }
          verdict: str = "pass"
          reason = None
          if cl > SKILL_LINE_HARD_CAP:
              verdict, reason = "fail", f"hard-cap-exceeded: {cl} > {SKILL_LINE_HARD_CAP} lines"
          elif delta > SKILL_LINE_DELTA_CAP:
              verdict, reason = "fail", (
                  f"delta-cap-exceeded: +{delta} > +{SKILL_LINE_DELTA_CAP} lines "
                  f"({cl} vs {bl} baseline)"
              )
          return GateResult(
              gate_name=self.name, candidate_hash=candidate.content_hash,
              baseline_hash=baseline.content_hash, verdict=verdict,  # type: ignore[arg-type]
              metrics=metrics, failure_reason=reason,
              timestamp=datetime.now(timezone.utc),
              duration_ms=int((time.perf_counter_ns() - t0) / 1e6),
          )
  ```
- **Commands**:
  - `ruff check nanobot/evolve/gates/skill_size.py`
  - `pytest -x tests/evolve/test_gate_skill_size.py`
- **Review focus**: correctness (path 1 vs path 2 ordering matches spec).

### t-10: `CacheCompatGate` (gate 3)

- **Spec**: §6.3 (lines 3118–3173), decisions #114, #116.
- **Files**: `nanobot/evolve/gates/cache_compat.py`, `tests/evolve/test_gate_cache_compat.py`. Append to `nanobot/evolve/gates/__init__.py`: `from nanobot.evolve.gates.cache_compat import CacheCompatGate; GATES.append(CacheCompatGate())`.
- **Definition of done**:
  - `CacheCompatGate().name == "3-cache-compat"`.
  - Equal keys → verdict pass, `metrics["byte_diff_present"] == 0.0`, `evidence` contains both `candidate_cache_key` and `baseline_cache_key`.
  - Different keys → verdict fail, `failure_reason` starts `"cache-key-mismatch"`, `evidence` still contains both hashes.
  - `pytest -x tests/evolve/test_gate_cache_compat.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/gates/cache_compat.py
  import time
  from datetime import datetime, timezone
  from typing import TYPE_CHECKING
  from nanobot.evolve.gates import Gate, GateResult
  if TYPE_CHECKING:
      from nanobot.evolve.harness import Candidate, Baseline

  class CacheCompatGate(Gate):
      @property
      def name(self) -> str: return "3-cache-compat"

      def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
          t0 = time.perf_counter_ns()
          equal = candidate.cache_key_hash == baseline.cache_key_hash
          evidence = {
              "candidate_cache_key": candidate.cache_key_hash,
              "baseline_cache_key": baseline.cache_key_hash,
          }
          reason = None if equal else (
              f"cache-key-mismatch: candidate={candidate.cache_key_hash} "
              f"!= baseline={baseline.cache_key_hash}"
          )
          return GateResult(
              gate_name=self.name, candidate_hash=candidate.content_hash,
              baseline_hash=baseline.content_hash,
              verdict="pass" if equal else "fail",
              metrics={"byte_diff_present": 0.0 if equal else 1.0},
              evidence=evidence, failure_reason=reason,
              timestamp=datetime.now(timezone.utc),
              duration_ms=int((time.perf_counter_ns() - t0) / 1e6),
          )
  ```
- **Commands**:
  - `ruff check nanobot/evolve/gates/cache_compat.py`
  - `pytest -x tests/evolve/test_gate_cache_compat.py`
- **Review focus**: data-integrity (evidence on both pass + fail paths per decision #116).

### t-11: harness — `OfflineHarness` skeleton + `_run_gates` + manifest

- **Spec**: §3.2 (lines 403–456), §3.7 (lines 913–973), §6.0 points 3+5, §6.4.2 (short-circuit), §6.5 (`_compute_final_status`).
- **Files**: `nanobot/evolve/harness.py`, `tests/evolve/test_harness.py`.
- **Definition of done**:
  - `SkillFrontmatter`, `SkillContent`, `Baseline`, `Candidate`, `JudgeSummary`, `RunManifest` Pydantic models per spec; `RunManifest.model_config` overrides `frozen=True`.
  - `OfflineHarness(workspace=Path)._run_gates(candidate, baseline) -> list[GateResult]` returns the gate trace with short-circuit on first fail (asserted in test by stub gate that fails first).
  - `_compute_final_status(promoted=None, all_candidates=[c1], baseline=b)` where `c1` has a fail trace → returns `"rejected_by_gate"`.
  - `pytest -x tests/evolve/test_harness.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/harness.py
  from datetime import datetime
  from pathlib import Path
  from typing import Literal, Optional
  from pydantic import ConfigDict

  from nanobot.evolve._base import EvolveBase
  from nanobot.evolve.gates import GATES, Gate, GateResult

  class SkillFrontmatter(EvolveBase):
      name: str
      description: str
      origin: Literal["bundled", "user", "agent"]
      created_by: str
      created_at: datetime
      evolved_from_run: Optional[str] = None
      evolved_at: Optional[datetime] = None
      parent_skill_hash: Optional[str] = None

  class SkillContent(EvolveBase):
      skill_name: str
      skill_md_content: str
      frontmatter: SkillFrontmatter
      body_md: str
      cache_key_hash: str
      size_metrics: dict[str, int]
      content_hash: str

  class Baseline(SkillContent):
      loaded_from: str
      loaded_at: datetime

  class Candidate(SkillContent):
      parent_baseline_hash: str
      gepa_iteration: int
      gepa_seed: Optional[int] = None

  class JudgeSummary(EvolveBase):
      record_count: int
      median_aggregate: float
      median_process: float
      median_output: float
      median_token: float
      consensus_split_count: int

  class RunManifest(EvolveBase):
      model_config = ConfigDict(
          extra="forbid",
          alias_generator=EvolveBase.model_config["alias_generator"],
          populate_by_name=True, frozen=True,
      )
      run_id: str
      started_at: datetime
      finished_at: datetime
      nanobot_version: str
      evolve_extra_version: dict[str, str]
      skill_name: str
      baseline_hash: str
      candidate_hashes: list[str]
      promoted_candidate_hash: Optional[str]
      gate_verdicts: list[GateResult]
      judge_summary: JudgeSummary
      final_status: Literal["promoted_to_pr","rejected_by_gate","no_improvement","harness_error"]
      tiers_used: list[Literal["A","B","C","D"]]
      record_count_per_tier: dict[str, int]
      judge_pool_health: dict[str, str]

  class OfflineHarness:
      def __init__(self, *, workspace: Path) -> None:
          if not workspace.is_dir():
              from nanobot.evolve.exceptions import ConfigError
              raise ConfigError(f"workspace not a directory: {workspace}")
          self._workspace = workspace

      def _run_gates(self, candidate: Candidate, baseline: Baseline) -> list[GateResult]:
          trace: list[GateResult] = []
          for gate in GATES:
              result = gate.evaluate(candidate, baseline)
              trace.append(result)
              if result.verdict == "fail":
                  break
          return trace

      def _compute_final_status(
          self, promoted: Optional[Candidate],
          all_candidates: list[Candidate], baseline: Baseline,
      ) -> Literal["promoted_to_pr","rejected_by_gate","no_improvement"]:
          if promoted is not None:
              return "promoted_to_pr"
          # any_candidate_failed_gate: real impl tracks per-candidate trace map;
          # M4 skeleton: caller passes pre-computed trace via Candidate attrs OR
          # falls through to no_improvement when no fail trace recorded.
          ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/harness.py`
  - `pytest -x tests/evolve/test_harness.py`
- **Review focus**: correctness (short-circuit on first fail; frozen=True on RunManifest).
- **smoke_cmd_hint**: `pytest -x tests/evolve/test_harness.py tests/evolve/test_gate_contract.py`.

### t-12: redaction pipeline (4 stages + sidecar manifest + abort-on-fail)

- **Spec**: §9.2, §9.3, §9.4.
- **Files**: `nanobot/evolve/privacy/__init__.py`, `nanobot/evolve/privacy/redact.py`, `tests/evolve/test_redact.py`.
- **Definition of done**:
  - `redact(text: str, *, custom_patterns: list[Pattern] = None) -> RedactionResult` where `RedactionResult` carries the redacted text and per-stage match counts.
  - Stage order: PII → apikey → file-path → custom.
  - `redact(...)` aborts (raises `ManifestPrivacyViolation` with `violated_invariant="§9.4 redaction stage failure"`) if any stage raises.
  - Custom-pattern amplification (>3× length) raises `ManifestPrivacyViolation`.
  - `pytest -x tests/evolve/test_redact.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/privacy/redact.py
  import re
  from dataclasses import dataclass, field

  EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
  PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")
  OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{20,}")
  ANTHROPIC_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}")
  GITHUB_PAT_RE = re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}")
  AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
  HOME_NIX_RE = re.compile(r"/(?:home|Users)/[^/\s]+/")
  HOME_WIN_RE = re.compile(r"C:\\Users\\[^\\\s]+\\")

  @dataclass
  class RedactionResult:
      text: str
      matches: dict[str, int] = field(default_factory=dict)

  def redact(text: str, *, custom_patterns: list[tuple[str, re.Pattern, str]] | None = None) -> RedactionResult:
      """4-stage in-order redaction. Stage failure → ManifestPrivacyViolation (abort)."""
      # Implementer: each stage MUST NOT redact 'claude-' model id prefix (only 'sk-ant-').
      ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/privacy/`
  - `pytest -x tests/evolve/test_redact.py`
- **Review focus**: security (no PII leak; abort semantics).

### t-13: judge calibration runner (Cohen κ ≥ 0.6)

- **Spec**: §7.3, §7.4.
- **Files**: `nanobot/evolve/judges/calibration.py`, `tests/evolve/test_calibration.py`.
- **Definition of done**:
  - `compute_cohen_kappa(human: list[float], judge: list[float], *, bins: int = 3) -> float` discretises into 3 bins ([0.0, 0.33), [0.33, 0.66), [0.66, 1.0]) and computes per-axis κ then means.
  - `calibrate(records: list[CalibrationRecord], pool: JudgePool) -> CalibrationReport` returns `passed: bool` with threshold `RUBRIC_PASS_THRESHOLD` for individual rubric pass, but **κ threshold is `0.6`** for calibration verdict.
  - `pytest -x tests/evolve/test_calibration.py` passes (uses fixture where κ < 0.6 fails verdict).
- **Exact code or signature**:
  ```python
  # nanobot/evolve/judges/calibration.py
  from dataclasses import dataclass
  CALIBRATION_KAPPA_THRESHOLD: float = 0.6  # Landis & Koch substantial-agreement

  @dataclass
  class CalibrationReport:
      kappa_mean: float
      kappa_per_axis: dict[str, float]
      passed: bool

  def compute_cohen_kappa(human: list[float], judge: list[float], *, bins: int = 3) -> float:
      """Discretise [0,1] floats into `bins` equal bins, then standard Cohen κ."""
      ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/judges/calibration.py`
  - `pytest -x tests/evolve/test_calibration.py`
- **Review focus**: correctness (κ formula + bin edges).

### t-14: pipeline — DSPy + GEPA lazy-import bootstrap

- **Spec**: §3.5, §3.5.1, §1.
- **Files**: `nanobot/evolve/pipeline.py`.
- **Definition of done**:
  - `from nanobot.evolve.pipeline import build_pipeline` does NOT import `dspy`/`gepa` at module top.
  - Calling `build_pipeline()` when `dspy` is absent raises `EvolveExtraNotInstalled` with `INSTALL_HINT == "pip install nanobot[evolve]"`.
  - `ruff check nanobot/evolve/pipeline.py` clean.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/pipeline.py
  from nanobot.evolve.exceptions import EvolveExtraNotInstalled

  def _lazy_import_gepa():
      try:
          import gepa  # noqa: F401
          import dspy  # noqa: F401
      except ImportError as e:
          raise EvolveExtraNotInstalled(
              f"M4 evolve harness needs DSPy + GEPA. {EvolveExtraNotInstalled.INSTALL_HINT}"
          ) from e
      return gepa, dspy

  def build_pipeline(*, skill_name: str, judge_pool, baseline, eval_records):
      """GEPA bootstrap. Implementer wires GEPA `optimize(metric_fn=...)` against rubric."""
      _gepa, _dspy = _lazy_import_gepa()
      ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/pipeline.py`
  - `python -c "from nanobot.evolve.pipeline import build_pipeline; print('ok')"`
- **Review focus**: correctness (no top-level dspy/gepa import).

### t-15: deploy — PR-only with squash-merge precondition

- **Spec**: §8 (lines 3361–3416).
- **Files**: `nanobot/evolve/deploy.py`, `tests/evolve/test_deploy.py`.
- **Definition of done**:
  - `build_branch_name(run_id: str, skill_name: str, candidate_short_sha: str) -> str` returns `f"evolve/{run_id}-{skill_name}-{candidate_short_sha}"`.
  - `assert_not_main(branch: str)` raises `ApplyTerminalError` (with `final_status` + `manifest_path` kwargs filled by caller) when branch in {`main`, `master`}.
  - `assemble_pr_body(manifest: RunManifest, gate_results: list[GateResult]) -> str` returns markdown with exactly 5 `##` headers: `Summary`, `Eval results`, `Gates passed`, `Diff stats`, `Rollback plan`.
  - `pytest -x tests/evolve/test_deploy.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/evolve/deploy.py
  from pathlib import Path
  from nanobot.evolve.exceptions import ApplyTerminalError

  PROTECTED_BRANCHES = {"main", "master"}

  def build_branch_name(run_id: str, skill_name: str, candidate_short_sha: str) -> str:
      return f"evolve/{run_id}-{skill_name}-{candidate_short_sha}"

  def assert_not_main(branch: str, *, manifest_path: Path, final_status: str) -> None:
      if branch in PROTECTED_BRANCHES:
          raise ApplyTerminalError(
              f"refuse to push to protected branch: {branch}",
              final_status=final_status, manifest_path=manifest_path,
          )

  def assemble_pr_body(manifest, gate_results) -> str:
      """5-section markdown body per §8.2."""
      ...
  ```
- **Commands**:
  - `ruff check nanobot/evolve/deploy.py`
  - `pytest -x tests/evolve/test_deploy.py`
- **Review focus**: security (no-main hard-check is non-bypassable).

### t-16: CLI — `nanobot evolve {init,run,report,apply}`

- **Spec**: §4 (lines 995–1184), §4.6 exit codes.
- **Files**: `nanobot/cli/evolve.py`, `nanobot/cli/commands.py` (modify to register), `tests/evolve/test_cli_evolve.py`.
- **Definition of done**:
  - `nanobot evolve --help` lists subcommands `init`, `run`, `report`, `apply`.
  - `nanobot evolve run --help` shows flags `--tiers`, `--judge-pool`, `--workspace`.
  - Dispatch wraps `pydantic.ValidationError` → `ConfigError` (exit 2) per §5.3 wrap rule.
  - Handler order in dispatch: `ApplyTerminalError` before `ConfigError`/`ValueError`; specific RuntimeError subclasses (`JudgeError`, `ManifestPrivacyViolation`, `EvolveEnvironmentError`) before bare `RuntimeError`.
  - `pytest -x tests/evolve/test_cli_evolve.py` passes.
- **Exact code or signature**:
  ```python
  # nanobot/cli/evolve.py
  import argparse
  def register(subparsers: argparse._SubParsersAction) -> None:
      p = subparsers.add_parser("evolve", help="Offline skill evolution (M4)")
      sub = p.add_subparsers(dest="evolve_cmd", required=True)
      sub.add_parser("init", help="Bootstrap workspace evals layout")
      run_p = sub.add_parser("run", help="Run GEPA pipeline")
      run_p.add_argument("--tiers", default="A,C")
      run_p.add_argument("--judge-pool", required=False)
      run_p.add_argument("--workspace", required=True)
      sub.add_parser("report", help="Render report.md from a run").add_argument("run_id")
      sub.add_parser("apply", help="Open PR for a promoted candidate").add_argument("run_id")
      p.set_defaults(func=dispatch)

  def dispatch(args) -> int:
      # Wraps pydantic.ValidationError → ConfigError; orders handlers per MUST_PRECEDE.
      ...
  ```
- **Commands**:
  - `ruff check nanobot/cli/evolve.py nanobot/cli/commands.py`
  - `pytest -x tests/evolve/test_cli_evolve.py`
- **Review focus**: correctness (handler order; ValidationError wrap).

### t-17: redaction regression — `claude-3-5-sonnet` MUST NOT be redacted

- **Spec**: §9.2 stage 2 explicit note.
- **Files**: `tests/evolve/test_redact_no_false_positive.py`.
- **Definition of done**:
  - `redact("model = claude-3-5-sonnet")` returns text unchanged in the `apikey.*` count.
  - `redact("api key sk-ant-abcdefghijklmnopqrstuvwxyz")` substitutes that key but does NOT touch any `claude-*` substring.
  - `pytest -x tests/evolve/test_redact_no_false_positive.py` passes.
- **Exact code or signature**:
  ```python
  # tests/evolve/test_redact_no_false_positive.py
  from nanobot.evolve.privacy.redact import redact

  def test_claude_model_id_not_redacted():
      r = redact("we use claude-3-5-sonnet for judging")
      assert "claude-3-5-sonnet" in r.text
      assert r.matches.get("apikey.anthropic", 0) == 0

  def test_anthropic_key_is_redacted():
      r = redact("token: sk-ant-abcdefghijklmnopqrstuvwxyz1234")
      assert "sk-ant-" not in r.text
      assert r.matches.get("apikey.anthropic", 0) == 1
  ```
- **Commands**:
  - `pytest -x tests/evolve/test_redact_no_false_positive.py`
- **Review focus**: security (false-positive regression coverage).

### t-18: integration smoke — end-to-end without DSPy

- **Spec**: §3.6 + §6.4 + §3.7 (manifest assembly).
- **Files**: `tests/evolve/test_pipeline_integration.py`.
- **Definition of done**:
  - Test constructs a stub `Baseline` + `Candidate` (same `cache_key_hash`, sizes within caps, identical content) → harness `_run_gates` returns 3 GateResults all `verdict="pass"`.
  - Test mutates candidate to differ in cache key → `_run_gates` returns either 1 (fail at gate-1) or 3 with gate-3 fail (depending on gate-1 skeleton return path); assert short-circuit semantics either way: `trace[-1].verdict == "fail"`.
  - Does NOT import `dspy`/`gepa` (asserts via `sys.modules` check after run).
  - `pytest -x tests/evolve/test_pipeline_integration.py` passes.
- **Exact code or signature**: implementer assembles fixtures using `Baseline`/`Candidate` constructors from t-11.
- **Commands**:
  - `pytest -x tests/evolve/test_pipeline_integration.py`
- **Review focus**: correctness (end-to-end + lazy-guard assertion).

### t-19: roadmap update

- **Spec**: working-rule (mark milestone in-progress).
- **Files**: `docs/hermes-evolution/roadmap.md`.
- **Definition of done**:
  - M4 row in roadmap reflects "in-progress @ commit `<this plan's commit hash>`"; no PR link yet.
  - `git diff docs/hermes-evolution/roadmap.md` shows only the M4 row touched.
- **Commands**:
  - `git diff docs/hermes-evolution/roadmap.md`
- **Review focus**: correctness (don't touch other milestone rows).

## Parallel groups

```yaml
parallel_groups:
  - [t-01, t-02]                           # scaffold (exceptions + constants)
  - [t-03, t-04, t-05, t-06]               # data + schemas + judges + Gate ABC
  - [t-07, t-08, t-09, t-10]               # contract test + 3 gates
  - [t-11, t-12, t-13]                     # harness + redaction + calibration
  - [t-14, t-15]                           # pipeline (lazy DSPy) + deploy
  - [t-16]                                 # CLI (depends on exceptions, harness, deploy)
  - [t-17, t-18]                           # redact regression + integration smoke
  - [t-19]                                 # roadmap update
build_state_after: green-after-each-group  # no intentional broken state
```

**Serial reasoning notes**:
- Group 2 depends on group 1: `t-04` / `t-05` consume `EvolveBase` from `t-01`; `t-06` consumes `EvolveBase` + `_constants` from `t-02`.
- Group 3 depends on group 2: contract test + 3 gates consume `Gate`/`GateResult`/`_constants`. Within group 3, the four tasks touch disjoint files but all append to `nanobot/evolve/gates/__init__.py` (the `GATES.append(...)` line). The implementer running group 3 MUST coordinate the append ordering manually (gate-1 first, gate-2 second, gate-3 third) — or land them sequentially. If the executor wants strict parallelism, split `__init__.py` updates into a small follow-up.
- Group 4 depends on groups 2-3: harness imports `GATES` + judge types.
- Group 5 depends on group 4 (deploy uses `RunManifest` from harness; pipeline uses exceptions).
- Group 6 depends on groups 4-5 (CLI dispatches to harness + deploy + raises `ConfigError`/`ApplyTerminalError`).
- Group 7 is independent of group 6 once redaction (t-12) + harness (t-11) exist.

## Smoke command

`pytest -x tests/evolve/ --timeout=30` (root smoke; per-task overrides noted on t-08 / t-11).
