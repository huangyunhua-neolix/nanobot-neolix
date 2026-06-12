import pytest
from pydantic import ValidationError

from nanobot.evolve._base import EvolveBase


class _FakeModel(EvolveBase):
    record_id: str


def test_evolve_base_accepts_snake_case_input():
    m = _FakeModel(record_id="x")
    assert m.record_id == "x"
    assert _FakeModel(**m.model_dump()) == m


def test_evolve_base_accepts_camel_case_alias():
    m = _FakeModel(recordId="x")
    assert m.record_id == "x"


def test_evolve_base_dump_uses_alias_by_default_or_explicit():
    m = _FakeModel(record_id="x")
    assert m.model_dump(by_alias=True) == {"recordId": "x"}


def test_evolve_base_rejects_extra_field():
    with pytest.raises(ValidationError):
        _FakeModel(record_id="x", bogus_extra="y")


def test_evolve_base_default_frozen_false():
    m = _FakeModel(record_id="x")
    m.record_id = "y"
    assert m.record_id == "y"
