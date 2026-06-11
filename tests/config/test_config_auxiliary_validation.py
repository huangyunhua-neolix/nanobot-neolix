"""Root Config validator for agents.defaults.auxiliary.modelPreset (M1 Task D3)."""

import pytest
from pydantic import ValidationError


def _base_config_dict(extra: dict | None = None) -> dict:
    """Minimal valid Config dict; relies on existing defaults for the rest."""
    payload: dict = {
        "modelPresets": {
            "main": {"model": "gpt-4o-mini", "provider": "openai"},
            "aux-real": {"model": "gpt-4o-mini", "provider": "openai"},
        },
        "agents": {
            "defaults": {"modelPreset": "main"},
        },
    }
    if extra:
        for key, value in extra.items():
            payload[key] = value
    return payload


def test_config_accepts_auxiliary_pointing_at_existing_preset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    payload["agents"]["defaults"]["auxiliary"] = {"modelPreset": "aux-real"}
    cfg = Config.model_validate(payload)
    assert cfg.agents.defaults.auxiliary.model_preset == "aux-real"


def test_config_rejects_auxiliary_pointing_at_missing_preset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    payload["agents"]["defaults"]["auxiliary"] = {"modelPreset": "does-not-exist"}
    with pytest.raises(ValidationError) as excinfo:
        Config.model_validate(payload)
    msg = str(excinfo.value)
    assert "auxiliary" in msg.lower()
    assert "does-not-exist" in msg


def test_config_accepts_auxiliary_unset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    cfg = Config.model_validate(payload)
    assert cfg.agents.defaults.auxiliary.model_preset is None
