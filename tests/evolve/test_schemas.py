import pytest
from pydantic import ValidationError

from nanobot.evolve.schemas import RubricWeights, _assert_odd_pool_size


def test_rubric_weights_defaults_sum_to_one():
    w = RubricWeights()
    assert w.process == 0.4
    assert w.output == 0.4
    assert w.token == 0.2
    assert abs((w.process + w.output + w.token) - 1.0) < 1e-9


def test_rubric_weights_bad_sum_raises_with_sum_in_message():
    with pytest.raises(ValidationError) as exc_info:
        RubricWeights(process=0.5, output=0.5, token=0.5)
    assert "1.500000" in str(exc_info.value)


def test_assert_odd_pool_size_even_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        _assert_odd_pool_size(2, context="x")


def test_assert_odd_pool_size_zero_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        _assert_odd_pool_size(0, context="x")


def test_assert_odd_pool_size_odd_returns_none():
    assert _assert_odd_pool_size(3, context="x") is None
