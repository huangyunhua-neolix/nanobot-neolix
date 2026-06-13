"""Tests for CuratorConfig in nanobot.config.schema."""

import pytest
from pydantic import ValidationError

from nanobot.config.schema import AgentDefaults, CuratorConfig


def test_curator_config_defaults_are_conservative() -> None:
    cfg = CuratorConfig()

    assert cfg.enabled is True
    assert cfg.forced_dry_run_until == "auto"
    assert cfg.protect_list == []
    assert cfg.protect_patterns == []
    assert cfg.min_views_for_delete == 30
    assert cfg.max_uses_for_delete == 0
    assert cfg.stale_days == 30
    assert cfg.low_use_ratio == pytest.approx(0.02)
    assert cfg.apply_delete_mode == "auto_high"
    assert cfg.aux_deliberation is False


def test_curator_config_camel_aliases() -> None:
    cfg = CuratorConfig.model_validate(
        {
            "forcedDryRunUntil": "auto",
            "protectList": ["skill-a"],
            "protectPatterns": ["tmp-*"],
            "minViewsForDelete": 50,
            "maxUsesForDelete": 1,
            "staleDays": 14,
            "lowUseRatio": 0.05,
            "applyDeleteMode": "manual_only",
            "auxDeliberation": True,
        }
    )

    assert cfg.forced_dry_run_until == "auto"
    assert cfg.protect_list == ["skill-a"]
    assert cfg.protect_patterns == ["tmp-*"]
    assert cfg.min_views_for_delete == 50
    assert cfg.max_uses_for_delete == 1
    assert cfg.stale_days == 14
    assert cfg.low_use_ratio == pytest.approx(0.05)
    assert cfg.apply_delete_mode == "manual_only"
    assert cfg.aux_deliberation is True


@pytest.mark.parametrize(
    "bad_value",
    [
        "",  # empty string
        "2025-01-01T00:00:00",  # naive — no Z or offset
        "2025-01-01T00:00:00+05:30",  # offset — not allowed, only Z
        "someday",  # arbitrary string
        "2025-01-01",  # date-only, not datetime
        "2025-01-01T00:00:00.000Z",  # subsecond — not YYYY-MM-DDTHH:MM:SSZ
    ],
)
def test_reject_invalid_forced_dry_run_until(bad_value: str) -> None:
    with pytest.raises(ValidationError):
        CuratorConfig(forced_dry_run_until=bad_value)


@pytest.mark.parametrize(
    "bad_calendar_value",
    [
        "2025-13-01T00:00:00Z",  # month 13
        "2025-01-32T00:00:00Z",  # day 32
        "2025-01-01T25:00:00Z",  # hour 25
        "2025-02-30T00:00:00Z",  # Feb 30 never exists
        "2025-04-31T00:00:00Z",  # April has 30 days
        "2025-01-01T00:60:00Z",  # minute 60
        "2025-01-01T00:00:60Z",  # second 60
    ],
)
def test_reject_invalid_calendar_forced_dry_run_until(bad_calendar_value: str) -> None:
    with pytest.raises(ValidationError):
        CuratorConfig(forced_dry_run_until=bad_calendar_value)


def test_accept_valid_utc_forced_dry_run_until() -> None:
    cfg = CuratorConfig(forced_dry_run_until="2099-12-31T23:59:59Z")
    assert cfg.forced_dry_run_until == "2099-12-31T23:59:59Z"


def test_agent_defaults_contains_curator() -> None:
    defaults = AgentDefaults()

    assert isinstance(defaults.curator, CuratorConfig)
    assert defaults.curator.forced_dry_run_until == "auto"
