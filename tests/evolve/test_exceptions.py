"""Tests for nanobot.evolve.exceptions per spec §5.3 test 8.

Covers:
- subset-positive: a subclass declaring STRUCTURED_KWARGS that maps cleanly
  onto its __init__ kw-only params constructs without error.
- subset-negative: a subclass declaring STRUCTURED_KWARGS containing a name
  NOT in __init__ kw-only params raises TypeError at class definition time.
- inheritance-negative: a subclass whose parent declares STRUCTURED_KWARGS
  and which does NOT redeclare its own raises TypeError at class definition
  time.
- regression-positive: ManifestPrivacyViolation (the most complex declared
  exception) constructs from keyword arguments without error.
"""
import typing
from pathlib import Path
from typing import ClassVar

import pytest

from nanobot.evolve import (
    ApplyTerminalError,
    EvolveEnvironmentError,
    EvolveError,
    EvolveExtraNotInstalled,
    GateInternalError,
    JudgeError,
    ManifestPrivacyViolation,
)


def test_subset_positive_subclass_constructs():
    class OkExc(EvolveError, ValueError):  # noqa: N818 — test fixture
        STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"x"})

        def __init__(self, msg: str, *, x: int) -> None:
            super().__init__(msg)
            self.x = x

    inst = OkExc("hello", x=42)
    assert inst.x == 42


def test_subset_negative_raises_at_class_definition():
    with pytest.raises(TypeError):
        class BadExc(EvolveError, ValueError):  # noqa: N818 — test fixture
            STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"missing"})

            def __init__(self, msg: str, *, present: int) -> None:
                super().__init__(msg)
                self.present = present


def test_inheritance_without_redeclaration_raises():
    class ParentExc(EvolveError, ValueError):  # noqa: N818 — test fixture
        STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"x"})

        def __init__(self, msg: str, *, x: int) -> None:
            super().__init__(msg)
            self.x = x

    with pytest.raises(TypeError):
        class ChildExc(ParentExc):  # noqa: N801 — intentional test name
            def __init__(self, msg: str, *, x: int) -> None:
                super().__init__(msg, x=x)


def test_manifest_privacy_violation_constructs():
    inst = ManifestPrivacyViolation(message="x", violated_invariant="inv1")
    assert inst.violated_invariant == "inv1"
    assert inst.offending_path is None
    assert inst.offending_fields == []


def test_apply_terminal_error_ctor():
    path = Path("/tmp/m.json")
    inst = ApplyTerminalError(message="x", final_status="abort", manifest_path=path)
    assert inst.final_status == "abort"
    assert inst.manifest_path == path


def test_apply_terminal_error_message_positional_or_kwarg():
    path = Path("/tmp/m.json")
    pos = ApplyTerminalError("msg", final_status="abort", manifest_path=path)
    kw = ApplyTerminalError(message="msg", final_status="abort", manifest_path=path)
    assert pos.args[0] == "msg"
    assert kw.args[0] == "msg"
    assert pos.final_status == kw.final_status == "abort"
    assert pos.manifest_path == kw.manifest_path == path


def test_manifest_privacy_violation_ctor():
    path = Path("/tmp/leak.json")
    inst = ManifestPrivacyViolation(
        message="oops",
        violated_invariant="no_pii",
        offending_path=path,
        offending_fields=["email", "phone"],
    )
    assert inst.violated_invariant == "no_pii"
    assert inst.offending_path == path
    assert inst.offending_fields == ["email", "phone"]


def test_manifest_privacy_violation_message_positional_or_kwarg():
    pos = ManifestPrivacyViolation("m", violated_invariant="inv")
    kw = ManifestPrivacyViolation(message="m", violated_invariant="inv")
    assert pos.args[0] == "m"
    assert kw.args[0] == "m"
    assert pos.violated_invariant == kw.violated_invariant == "inv"


def test_judge_error_no_structured_kwargs():
    err = JudgeError("boom")
    assert str(err) == "boom"
    # JudgeError does not declare STRUCTURED_KWARGS in its own __dict__.
    assert "STRUCTURED_KWARGS" not in JudgeError.__dict__


def test_evolve_extra_not_installed_install_hint():
    assert hasattr(EvolveExtraNotInstalled, "INSTALL_HINT")
    assert "pip install" in EvolveExtraNotInstalled.INSTALL_HINT
    assert "nanobot[evolve]" in EvolveExtraNotInstalled.INSTALL_HINT


def test_evolve_environment_error_empty_frozenset_branch():
    # Declared as frozenset() — the empty-set branch must accept it at
    # class-definition time (already happened at import), and instances
    # must construct cleanly.
    assert EvolveEnvironmentError.STRUCTURED_KWARGS == frozenset()
    inst = EvolveEnvironmentError("env failure")
    assert str(inst) == "env failure"


def test_structured_kwargs_must_be_frozenset_type():
    with pytest.raises(TypeError):
        class BadTypeExc(EvolveError, ValueError):  # noqa: N818 — test fixture
            STRUCTURED_KWARGS = {"foo"}  # set, not frozenset

            def __init__(self, msg: str, *, foo: int) -> None:
                super().__init__(msg)
                self.foo = foo


def test_gate_internal_error_round_trip():
    """GateInternalError: positional message via mixin → RuntimeError args[0]."""
    err = GateInternalError("tier-c-empty: gate-1 requires ≥1 record")
    assert isinstance(err, RuntimeError)
    assert isinstance(err, EvolveError)
    assert err.args[0] == "tier-c-empty: gate-1 requires ≥1 record"
    assert GateInternalError.STRUCTURED_KWARGS == frozenset()
    assert "RuntimeError" in GateInternalError.MUST_PRECEDE


def test_get_type_hints_resolves_on_apply_terminal_error():
    # Regression guard: Path must be importable at module top so that
    # typing.get_type_hints can resolve the annotations without NameError.
    hints = typing.get_type_hints(ApplyTerminalError.__init__)
    assert "manifest_path" in hints
