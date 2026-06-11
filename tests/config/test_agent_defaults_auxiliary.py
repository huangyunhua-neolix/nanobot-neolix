"""AgentDefaults.auxiliary wiring tests (M1 Task D2)."""


def test_agent_defaults_has_auxiliary_default():
    from nanobot.config.schema import AgentDefaults, AuxiliaryConfig

    defaults = AgentDefaults()
    assert isinstance(defaults.auxiliary, AuxiliaryConfig)
    assert defaults.auxiliary.model_preset is None


def test_agent_defaults_accepts_auxiliary_camelcase():
    from nanobot.config.schema import AgentDefaults

    defaults = AgentDefaults.model_validate({"auxiliary": {"modelPreset": "aux-1"}})
    assert defaults.auxiliary.model_preset == "aux-1"


def test_agent_defaults_serialises_auxiliary_back_to_camelcase():
    from nanobot.config.schema import AgentDefaults

    defaults = AgentDefaults.model_validate({"auxiliary": {"modelPreset": "aux-1"}})
    dumped = defaults.model_dump(by_alias=True, exclude_none=True)
    assert dumped["auxiliary"] == {"modelPreset": "aux-1"}
