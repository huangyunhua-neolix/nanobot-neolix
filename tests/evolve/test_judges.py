import pytest
from pydantic import ValidationError

from nanobot.evolve.judges import JudgeConfig, JudgePool


def _make_three() -> list[JudgeConfig]:
    return [
        JudgeConfig(model="anthropic/claude-3-5-sonnet"),
        JudgeConfig(model="openai/gpt-4o"),
        JudgeConfig(model="google/gemini-pro"),
    ]


def test_three_judges_construct_with_default_quorum() -> None:
    pool = JudgePool(judges=_make_three())
    assert len(pool.judges) == 3
    assert pool.effective_min_quorum == 2


def test_explicit_min_quorum_one_overrides_default() -> None:
    pool = JudgePool(judges=_make_three(), min_quorum=1)
    assert pool.effective_min_quorum == 1


def test_effective_quorum_for_pool_size_one() -> None:
    pool = JudgePool(judges=[JudgeConfig(model="anthropic/claude-3-5-sonnet")])
    assert pool.effective_min_quorum == 1


def test_effective_quorum_for_pool_size_five() -> None:
    judges = _make_three() + [
        JudgeConfig(model="anthropic/claude-3-opus"),
        JudgeConfig(model="openai/gpt-4-turbo"),
    ]
    pool = JudgePool(judges=judges)
    assert pool.effective_min_quorum == 3


def test_even_pool_size_rejected() -> None:
    judges = _make_three()[:2]
    with pytest.raises(ValidationError) as exc:
        JudgePool(judges=judges)
    assert "odd" in str(exc.value)


def test_quorum_exceeding_pool_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        JudgePool(judges=_make_three(), min_quorum=5)
    assert "exceeds len(judges)" in str(exc.value)


def test_empty_judges_rejected_by_min_length() -> None:
    with pytest.raises(ValidationError):
        JudgePool(judges=[])


def test_frozen_pool_rejects_mutation() -> None:
    pool = JudgePool(judges=_make_three())
    with pytest.raises(ValidationError):
        pool.require_consensus = True
