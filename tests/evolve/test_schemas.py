import pytest
from pydantic import ValidationError

from nanobot.evolve.schemas import RubricScore, RubricWeights, assert_odd_pool_size


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
        assert_odd_pool_size(2, context="x")


def test_assert_odd_pool_size_zero_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        assert_odd_pool_size(0, context="x")


def test_assert_odd_pool_size_odd_returns_none():
    assert assert_odd_pool_size(3, context="x") is None


def test_rubric_score_valid_construction():
    score = RubricScore(process=0.5, output=0.7, token=0.3, aggregate=0.5)
    dumped = score.model_dump()
    assert dumped == {"process": 0.5, "output": 0.7, "token": 0.3, "aggregate": 0.5}
    round_trip = RubricScore(**dumped)
    assert round_trip == score


def test_rubric_score_field_out_of_range_rejected():
    with pytest.raises(ValidationError):
        RubricScore(process=1.5, output=0.5, token=0.3, aggregate=0.5)


def test_rubric_score_aggregate_out_of_range_rejected():
    with pytest.raises(ValidationError):
        RubricScore(process=0.5, output=0.5, token=0.3, aggregate=-0.1)


def test_rubric_weights_negative_weight_rejected():
    with pytest.raises(ValidationError):
        RubricWeights(process=-0.1, output=0.6, token=0.5)


def test_rubric_weights_tolerance_edge_inside():
    # sum equals 1.0 - 5e-7 (within 1e-6 tolerance) -> accepted
    w = RubricWeights(process=0.4, output=0.4, token=0.2 - 5e-7)
    assert abs((w.process + w.output + w.token) - 1.0) <= 1e-6


def test_rubric_weights_tolerance_edge_outside():
    # sum equals 1.0 - 5e-6 (outside 1e-6 tolerance) -> ValidationError
    with pytest.raises(ValidationError):
        RubricWeights(process=0.4, output=0.4, token=0.2 - 5e-6)


def test_assert_odd_pool_size_one_returns_none():
    assert assert_odd_pool_size(1, context="x") is None


def test_assert_odd_pool_size_negative_raises():
    with pytest.raises(ValueError, match=r"must be odd and >= 1"):
        assert_odd_pool_size(-1, context="x")
