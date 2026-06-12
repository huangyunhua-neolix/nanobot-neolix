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
from typing import ClassVar

import pytest

from nanobot.evolve import EvolveError, ManifestPrivacyViolation


def test_subset_positive_subclass_constructs():
    class OkExc(EvolveError, ValueError):
        STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"x"})

        def __init__(self, msg: str, *, x: int) -> None:
            super().__init__(msg)
            self.x = x

    inst = OkExc("hello", x=42)
    assert inst.x == 42


def test_subset_negative_raises_at_class_definition():
    with pytest.raises(TypeError):
        class BadExc(EvolveError, ValueError):
            STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"missing"})

            def __init__(self, msg: str, *, present: int) -> None:
                super().__init__(msg)
                self.present = present


def test_inheritance_without_redeclaration_raises():
    class ParentExc(EvolveError, ValueError):
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
