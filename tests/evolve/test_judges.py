from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from pydantic.alias_generators import to_camel

from nanobot.evolve._base import EvolveBase
from nanobot.evolve.judges import JudgeConfig, JudgeConsensus, JudgePool, JudgeResult
from nanobot.evolve.schemas import RubricScore


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


def _make_rubric_score() -> RubricScore:
    return RubricScore(process=0.8, output=0.7, token=0.9, aggregate=0.78)


def test_judge_config_construction() -> None:
    cfg = JudgeConfig(model="anthropic/claude-3-5-sonnet")
    assert cfg.model == "anthropic/claude-3-5-sonnet"
    round_trip = JudgeConfig.model_validate(cfg.model_dump())
    assert round_trip == cfg


def test_judge_result_valid() -> None:
    result = JudgeResult(
        eval_record_id="rec-1",
        judge_model="anthropic/claude-3-5-sonnet",
        score=_make_rubric_score(),
        reasoning="solid",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        prompt_template_version="v1",
    )
    round_trip = JudgeResult.model_validate(result.model_dump())
    assert round_trip == result


def test_judge_result_rejects_bad_score_type() -> None:
    with pytest.raises(ValidationError):
        JudgeResult(
            eval_record_id="rec-1",
            judge_model="anthropic/claude-3-5-sonnet",
            score="not-a-rubric",  # type: ignore[arg-type]
            reasoning="x",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            prompt_template_version="v1",
        )


def _make_judge_result(model: str = "anthropic/claude-3-5-sonnet") -> JudgeResult:
    return JudgeResult(
        eval_record_id="rec-1",
        judge_model=model,
        score=_make_rubric_score(),
        reasoning="r",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        prompt_template_version="v1",
    )


def test_judge_consensus_verdict_literal_enforced() -> None:
    JudgeConsensus(
        eval_record_id="rec-1",
        judges=[_make_judge_result()],
        median_score=_make_rubric_score(),
        inter_judge_variance={"process": 0.0},
        consensus_verdict="agree",
    )
    with pytest.raises(ValidationError):
        JudgeConsensus(
            eval_record_id="rec-1",
            judges=[_make_judge_result()],
            median_score=_make_rubric_score(),
            inter_judge_variance={"process": 0.0},
            consensus_verdict="bogus",  # type: ignore[arg-type]
        )


def test_judge_consensus_verdict_split_and_single() -> None:
    for verdict in ("split", "single"):
        c = JudgeConsensus(
            eval_record_id="rec-1",
            judges=[_make_judge_result()],
            median_score=_make_rubric_score(),
            inter_judge_variance={"process": 0.0},
            consensus_verdict=verdict,  # type: ignore[arg-type]
        )
        assert c.consensus_verdict == verdict


def test_judge_pool_explicit_min_quorum_equals_pool_size() -> None:
    pool = JudgePool(judges=_make_three(), min_quorum=3)
    assert pool.effective_min_quorum == 3


def test_judge_pool_config_inherits_evolve_base_keys() -> None:
    assert JudgePool.model_config["extra"] == "forbid"
    assert JudgePool.model_config["alias_generator"] is EvolveBase.model_config["alias_generator"]
    assert JudgePool.model_config["alias_generator"] is to_camel
    assert JudgePool.model_config["populate_by_name"] is True
    assert JudgePool.model_config["frozen"] is True


def test_judge_pool_frozen_rejects_mutation() -> None:
    pool = JudgePool(judges=_make_three())
    with pytest.raises(ValidationError):
        pool.require_consensus = True
