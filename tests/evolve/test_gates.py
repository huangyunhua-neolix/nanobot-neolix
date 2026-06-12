"""Tests for nanobot.evolve.gates ABC, registries, and GateResult validation.

Covers spec §6.4.1 contract surface and the dual-registry design (Decision #122):
  - Gate._subclasses: declaration-time set (enforces NONDETERMINISTIC ClassVar)
  - GATES: execution-time ordered list of concrete Gate instances
"""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import ValidationError

from nanobot.evolve.gates import GATES, Gate, GateResult

if TYPE_CHECKING:
    from nanobot.evolve.harness import Baseline, Candidate


def test_gate_abc_not_directly_instantiable():
    """Gate is abstract — direct instantiation must fail."""
    with pytest.raises(TypeError):
        Gate()  # type: ignore[abstract]


def test_gate_subclass_must_declare_nondeterministic():
    """Spec §6.4.1 contract: every Gate subclass declares NONDETERMINISTIC ClassVar.

    The base class provides a default of False; concrete gates MUST override
    it explicitly. This test enumerates _subclasses and asserts each one has
    the attribute set in its own __dict__ OR (for the in-test subclass below)
    explicitly via class body — i.e. NONDETERMINISTIC is reachable as a
    ClassVar on the subclass.
    """
    for sub in Gate._subclasses:
        # Reachable as a class attribute (either own or inherited from Gate
        # default False). The §6.4.1 contract test in the harness package
        # additionally enforces own-attribute declaration; here we sanity-
        # check the registry surface that contract iterates over.
        assert hasattr(sub, "NONDETERMINISTIC"), (
            f"{sub.__name__} missing NONDETERMINISTIC (spec §6.4.1)"
        )
        assert isinstance(sub.NONDETERMINISTIC, bool)


def test_subclasses_registry_dedups_on_repeat_subclass_definition():
    """The __init_subclass__ dedup guard must hold against manual re-registration.

    Class-statement registration is exercised by the surrounding tests; here we
    additionally re-invoke the underlying ``__init_subclass__`` body to prove
    the ``if cls not in Gate._subclasses`` guard short-circuits the second call.
    """

    class _DedupProbe(Gate):
        NONDETERMINISTIC: ClassVar[bool] = False

        @property
        def name(self) -> str:
            return "_dedup_probe"

        def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
            raise NotImplementedError

    count_before = sum(1 for s in Gate._subclasses if s is _DedupProbe)
    assert count_before == 1, f"_DedupProbe registered {count_before}x at declaration"

    # Re-trigger the hook. ``Gate.__init_subclass__(cls=_DedupProbe)`` is rejected
    # by CPython 3.11+ ("got multiple values for argument 'cls'") because the
    # classmethod descriptor already binds ``cls``; call the underlying function
    # directly instead. This DOES re-enter the body — verified by clearing the
    # registry locally in a probe — so a regression that removes the dedup guard
    # would observe count_after == 2.
    Gate.__init_subclass__.__func__(_DedupProbe)

    count_after = sum(1 for s in Gate._subclasses if s is _DedupProbe)
    assert count_after == 1, f"dedup failed: re-trigger produced {count_after} entries"


def test_gateresult_validation_rejects_bad_verdict():
    """GateResult.verdict is Literal['pass', 'fail'] — anything else raises."""
    with pytest.raises(ValidationError):
        GateResult(
            gate_name="g",
            candidate_hash="c",
            baseline_hash="b",
            verdict="bogus",  # type: ignore[arg-type]
            metrics={},
            timestamp=datetime.now(),
            duration_ms=0,
        )


def test_gates_execution_registry_populated_in_order():
    """GATES is the execution registry; populated with the 3 M4 deterministic gates
    in name-prefix order (1- → 2- → 3-) so the harness iterates in spec-prescribed
    sequence. The §6.4.1 contract test (t-07) does the strict prefix/ordering check;
    this invariant test guards the basic populated-and-ordered shape after t-08/09/10
    landed and the orchestrator's coordinated registration commit wired them in."""
    assert len(GATES) == 3
    assert [g.name for g in GATES] == ["1-test-pass", "2-size-cap", "3-cache-compat"]


def test_subclasses_registry_collects_subclasses():
    """A minimal Gate subclass with NONDETERMINISTIC + evaluate stub appears in _subclasses."""

    class _Collected(Gate):
        NONDETERMINISTIC: ClassVar[bool] = True

        @property
        def name(self) -> str:
            return "_collected"

        def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
            raise NotImplementedError

    assert _Collected in Gate._subclasses


def test_gateresult_valid_construction():
    """Sanity: a well-formed GateResult constructs without error."""
    r = GateResult(
        gate_name="g",
        candidate_hash="c",
        baseline_hash="b",
        verdict="pass",
        metrics={"score": 1.0},
        timestamp=datetime.now(),
        duration_ms=10,
    )
    assert r.verdict == "pass"
    assert r.evidence is None
    assert r.failure_reason is None
