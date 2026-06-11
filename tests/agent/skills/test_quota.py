"""M2 §3.7 / §5.2 — SkillManageConfig defaults + alias roundtrip.

Extended in t-07 with cheap-reject helpers:
* `_check_body_size` enforces UTF-8 byte count.
* `_check_description_len` enforces Python `str` character count
  (NOT UTF-8 bytes — CJK descriptions must not be inflated 3x).
"""
from __future__ import annotations

import pytest


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


# --- t-07 cheap-reject helpers ------------------------------------------------


def test_check_body_size_enforces_limit():
    from nanobot.agent._atomic_io import SkillManageError
    from nanobot.agent.tools.skill_manage import _check_body_size

    # Exactly at the limit: must not raise.
    _check_body_size(b"x" * 65536, max_body_bytes=65536)
    # One byte over: must raise body_too_large.
    with pytest.raises(SkillManageError) as ei:
        _check_body_size(b"x" * 65537, max_body_bytes=65536)
    assert ei.value.error_code == "body_too_large"


def test_check_body_size_str_input_uses_utf8_bytes():
    from nanobot.agent._atomic_io import SkillManageError
    from nanobot.agent.tools.skill_manage import _check_body_size

    # 280 CJK chars ≈ 840 UTF-8 bytes — must trip a 256-byte limit.
    with pytest.raises(SkillManageError) as ei:
        _check_body_size("中" * 280, max_body_bytes=256)
    assert ei.value.error_code == "body_too_large"


def test_check_description_len_enforces_limit():
    from nanobot.agent._atomic_io import SkillManageError
    from nanobot.agent.tools.skill_manage import _check_description_len

    # Exactly at the limit: must not raise.
    _check_description_len("x" * 280, max_description_len=280)
    # One char over: must raise description_too_long.
    with pytest.raises(SkillManageError) as ei:
        _check_description_len("x" * 281, max_description_len=280)
    assert ei.value.error_code == "description_too_long"


def test_unicode_description_counted_by_chars_not_bytes():
    from nanobot.agent.tools.skill_manage import _check_description_len

    # 280 CJK chars is ~840 UTF-8 bytes; descriptions are char-counted so
    # this must NOT raise even though the UTF-8 byte length is far over 280.
    _check_description_len("中" * 280, max_description_len=280)
