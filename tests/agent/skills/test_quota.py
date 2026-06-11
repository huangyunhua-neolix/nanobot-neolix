"""M2 §3.7 / §5.2 — SkillManageConfig defaults + alias roundtrip."""
from __future__ import annotations


def test_skill_manage_config_defaults():
    from nanobot.config.schema import SkillManageConfig

    cfg = SkillManageConfig()
    assert cfg.max_mutations_per_turn == 5
    assert cfg.max_body_bytes == 65536
    assert cfg.max_agent_skills == 200
    assert cfg.max_description_len == 280


def test_skill_manage_config_alias():
    from nanobot.config.schema import SkillManageConfig

    # JSON via camelCase alias should populate snake_case attribute.
    cfg = SkillManageConfig.model_validate({"maxBodyBytes": 1024})
    assert cfg.max_body_bytes == 1024
    assert cfg.max_mutations_per_turn == 5  # default preserved
    # snake_case input also works (populate_by_name=True)
    cfg2 = SkillManageConfig.model_validate({"max_mutations_per_turn": 7})
    assert cfg2.max_mutations_per_turn == 7


def test_skill_manage_config_via_agent_defaults():
    from nanobot.config.schema import Config

    cfg = Config.model_validate(
        {"agents": {"defaults": {"skillManage": {"maxBodyBytes": 1024}}}}
    )
    assert cfg.agents.defaults.skill_manage.max_body_bytes == 1024
    # Other knobs retain defaults.
    assert cfg.agents.defaults.skill_manage.max_mutations_per_turn == 5
    assert cfg.agents.defaults.skill_manage.max_agent_skills == 200
    assert cfg.agents.defaults.skill_manage.max_description_len == 280
