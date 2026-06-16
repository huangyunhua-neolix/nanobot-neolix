from pathlib import Path

import pytest
from pydantic import ValidationError

from nanobot.config.schema import AgentDefaults, EvolutionConfig
from nanobot.evolve.exceptions import ConfigError


def test_evolution_config_defaults_are_proposal_safe() -> None:
    cfg = EvolutionConfig()

    assert cfg.enabled is True
    assert cfg.workspace is None
    assert cfg.proposal_triggers == ["manual", "curator", "dream"]
    assert cfg.optimizer_command == []
    assert cfg.use_noop_optimizer_when_unset is True
    assert cfg.default_tiers == "A,C"
    assert cfg.max_candidates == 8
    assert cfg.optimizer_timeout_seconds == 600


def test_evolution_config_camel_aliases() -> None:
    cfg = EvolutionConfig.model_validate(
        {
            "workspace": "~/custom-evolve",
            "proposalTriggers": ["manual", "curator"],
            "optimizerCommand": ["python", "optimizer.py"],
            "useNoopOptimizerWhenUnset": False,
            "defaultTiers": "A",
            "maxCandidates": 3,
            "optimizerTimeoutSeconds": 45,
        }
    )

    assert cfg.workspace == "~/custom-evolve"
    assert cfg.proposal_triggers == ["manual", "curator"]
    assert cfg.optimizer_command == ["python", "optimizer.py"]
    assert cfg.use_noop_optimizer_when_unset is False
    assert cfg.default_tiers == "A"
    assert cfg.max_candidates == 3
    assert cfg.optimizer_timeout_seconds == 45


def test_evolution_config_resolves_workspace_from_agent_workspace() -> None:
    cfg = EvolutionConfig()

    assert cfg.resolve_workspace(Path("/tmp/nanobot-workspace")) == Path("/tmp/nanobot-workspace")


def test_evolution_config_resolves_configured_workspace() -> None:
    cfg = EvolutionConfig(workspace="~/nanobot-evolve")

    assert str(cfg.resolve_workspace(Path("/tmp/ignored"))).endswith("nanobot-evolve")


def test_evolution_config_uses_noop_optimizer_fallback() -> None:
    cfg = EvolutionConfig()

    command = cfg.resolve_optimizer_command()

    assert command[:3] == [__import__("sys").executable, "-m", "nanobot.evolve.noop_optimizer"]


def test_evolution_config_requires_optimizer_when_noop_disabled() -> None:
    cfg = EvolutionConfig(use_noop_optimizer_when_unset=False)

    with pytest.raises(ConfigError, match="optimizerCommand"):
        cfg.resolve_optimizer_command()


def test_evolution_config_rejects_unknown_trigger() -> None:
    with pytest.raises(ValidationError):
        EvolutionConfig(proposal_triggers=["manual", "unknown"])


def test_agent_defaults_contains_evolution_config() -> None:
    defaults = AgentDefaults()

    assert isinstance(defaults.evolution, EvolutionConfig)
    assert defaults.evolution.enabled is True
