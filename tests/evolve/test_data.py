"""Tests for nanobot.evolve.data (M4 §3.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nanobot.evolve.data import EvalRecord, load_tier
from nanobot.evolve.exceptions import ConfigError


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row))
            fh.write("\n")


def _make_fixture(
    root: Path,
    skill: str,
    tier: str,
    input_rows: list[dict],
    expected_rows: list[dict],
) -> Path:
    tier_dir = root / skill / tier
    _write_jsonl(tier_dir / "input.jsonl", input_rows)
    _write_jsonl(tier_dir / "expected.jsonl", expected_rows)
    return tier_dir


def _base_input_row(
    rid: str,
    payload: dict,
    source: str = "synthesizer:s0",
    match_mode: str = "judge_only",
) -> dict:
    return {
        "record_id": rid,
        "input": payload,
        "match_mode": match_mode,
        "privacy_class": "public",
        "created_at": datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        "source": source,
        "tags": [],
    }


def _expected_row(rid: str, payload: dict | None) -> dict:
    return {
        "record_id": rid,
        "expected": payload,
    }


def test_load_tier_round_trip(tmp_path: Path) -> None:
    """Loader returns one EvalRecord per input row, fields fully populated."""
    skill = "demo_skill"
    tier = "A"
    input_rows = [
        _base_input_row("rec-001", {"q": "hello"}),
        _base_input_row("rec-002", {"q": "world"}),
    ]
    expected_rows = [
        _expected_row("rec-001", {"answer": "hi"}),
        _expected_row("rec-002", {"answer": "earth"}),
    ]
    _make_fixture(tmp_path, skill, tier, input_rows, expected_rows)

    records = load_tier(tier, skill, tmp_path)

    assert len(records) == 2
    assert all(isinstance(r, EvalRecord) for r in records)

    by_id = {r.record_id: r for r in records}
    assert by_id["rec-001"].input == {"q": "hello"}
    assert by_id["rec-001"].expected == {"answer": "hi"}
    assert by_id["rec-001"].match_mode == "judge_only"
    assert by_id["rec-001"].tier == "A"
    assert by_id["rec-001"].skill_name == skill
    assert by_id["rec-002"].input == {"q": "world"}
    assert by_id["rec-002"].expected == {"answer": "earth"}


def test_load_tier_joins_by_record_id_not_line_order(tmp_path: Path) -> None:
    """Proof of §3.1 invariant: shuffled expected.jsonl still joins correctly.

    If the loader naively zipped by line index, rec-001 would receive
    rec-003's expected payload. Joining by record_id is the only way to
    pass this test.
    """
    skill = "demo_skill"
    tier = "C"

    input_rows = [
        _base_input_row("rec-001", {"q": "alpha"}, source="curator:alice", match_mode="strict"),
        _base_input_row("rec-002", {"q": "beta"}, source="curator:alice", match_mode="strict"),
        _base_input_row("rec-003", {"q": "gamma"}, source="curator:alice", match_mode="strict"),
    ]
    # expected.jsonl deliberately written in REVERSE line order
    expected_rows = [
        _expected_row("rec-003", {"key_outputs": {"value": "gamma-ok"}}),
        _expected_row("rec-001", {"key_outputs": {"value": "alpha-ok"}}),
        _expected_row("rec-002", {"key_outputs": {"value": "beta-ok"}}),
    ]
    _make_fixture(tmp_path, skill, tier, input_rows, expected_rows)

    records = load_tier(tier, skill, tmp_path)
    by_id = {r.record_id: r for r in records}

    assert by_id["rec-001"].expected == {"key_outputs": {"value": "alpha-ok"}}
    assert by_id["rec-002"].expected == {"key_outputs": {"value": "beta-ok"}}
    assert by_id["rec-003"].expected == {"key_outputs": {"value": "gamma-ok"}}

    # Return order follows input.jsonl, not expected.jsonl.
    assert [r.record_id for r in records] == ["rec-001", "rec-002", "rec-003"]


def test_load_tier_missing_expected_raises(tmp_path: Path) -> None:
    skill = "demo_skill"
    tier = "A"
    input_rows = [
        _base_input_row("rec-001", {"q": "x"}),
        _base_input_row("rec-002", {"q": "y"}),
    ]
    expected_rows = [_expected_row("rec-001", {"answer": "x"})]
    _make_fixture(tmp_path, skill, tier, input_rows, expected_rows)

    with pytest.raises(ValueError, match="rec-002"):
        load_tier(tier, skill, tmp_path)


def test_load_tier_orphan_expected_raises(tmp_path: Path) -> None:
    skill = "demo_skill"
    tier = "A"
    input_rows = [_base_input_row("rec-001", {"q": "x"})]
    expected_rows = [
        _expected_row("rec-001", {"answer": "x"}),
        _expected_row("rec-999", {"answer": "ghost"}),
    ]
    _make_fixture(tmp_path, skill, tier, input_rows, expected_rows)

    with pytest.raises(ValueError, match="rec-999"):
        load_tier(tier, skill, tmp_path)


def test_load_tier_missing_files_raise(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_tier("A", "no_such_skill", tmp_path)


def test_load_tier_missing_input_file_raises(tmp_path: Path) -> None:
    """Only expected.jsonl present — the input.jsonl arm must trip first."""
    skill_dir = tmp_path / "skill_x" / "A"
    skill_dir.mkdir(parents=True)
    _write_jsonl(skill_dir / "expected.jsonl", [_expected_row("r1", {"answer": "x"})])
    with pytest.raises(FileNotFoundError, match="input.jsonl"):
        load_tier("A", "skill_x", tmp_path)


def test_load_tier_missing_expected_file_raises(tmp_path: Path) -> None:
    """Only input.jsonl present — the expected.jsonl arm must trip independently."""
    skill_dir = tmp_path / "skill_x" / "A"
    skill_dir.mkdir(parents=True)
    _write_jsonl(skill_dir / "input.jsonl", [_base_input_row("r1", {"q": "x"})])
    with pytest.raises(FileNotFoundError, match="expected.jsonl"):
        load_tier("A", "skill_x", tmp_path)


def test_load_tier_b_raises_config_error(tmp_path: Path) -> None:
    """Tier B SessionDB-anonymized loading is not wired in M4 (§3.1.3)."""
    with pytest.raises(ConfigError, match="Tier B") as exc_info:
        load_tier("B", "any_skill", tmp_path)
    assert "M5" in str(exc_info.value)
    assert "A/C" in str(exc_info.value)


def test_load_tier_d_raises_config_error(tmp_path: Path) -> None:
    """Tier D self-eval loading is not wired in M4 (§3.1.5)."""
    with pytest.raises(ConfigError, match="Tier D") as exc_info:
        load_tier("D", "any_skill", tmp_path)
    assert "M5" in str(exc_info.value)
    assert "A/C" in str(exc_info.value)


def test_load_tier_in_row_tier_mismatch_raises(tmp_path: Path) -> None:
    """Row carrying a wrong tier label MUST hard-fail, not silently pass through."""
    skill = "skill_x"
    drifted_row = _base_input_row("rec-001", {"q": "x"})
    drifted_row["tier"] = "C"  # path context will say "A"
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [drifted_row],
        [_expected_row("rec-001", {"answer": "x"})],
    )
    with pytest.raises(ValueError, match="disagrees with path-context tier"):
        load_tier("A", skill, tmp_path)


def test_load_tier_in_row_skill_name_mismatch_raises(tmp_path: Path) -> None:
    """Row carrying a wrong skill_name MUST hard-fail too."""
    skill = "skill_x"
    drifted_row = _base_input_row("rec-001", {"q": "x"})
    drifted_row["skill_name"] = "other_skill"
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [drifted_row],
        [_expected_row("rec-001", {"answer": "x"})],
    )
    with pytest.raises(ValueError, match="disagrees with path-context skill_name"):
        load_tier("A", skill, tmp_path)


def test_expected_jsonl_rejects_unknown_keys(tmp_path: Path) -> None:
    """A stray key in expected.jsonl (e.g. match_mode, which now belongs on the
    input side) must trip the whitelist guard. The loader refuses to silently
    accept fields that would shadow the input.jsonl side on merge."""
    skill = "skill_x"
    polluted_expected = _expected_row("rec-001", {"answer": "x"})
    polluted_expected["match_mode"] = "strict"  # not in {record_id, expected}
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [_base_input_row("rec-001", {"q": "x"})],
        [polluted_expected],
    )
    with pytest.raises(ValueError, match="unexpected keys"):
        load_tier("A", skill, tmp_path)


def test_expected_jsonl_overwrite_attack_blocked(tmp_path: Path) -> None:
    """RED #1 regression: an expected.jsonl row carrying an input-side field
    (here `privacy_class`) MUST be rejected. Previously `{**row, **exp_row}`
    would silently let stale expected-side data clobber the input metadata."""
    skill = "skill_x"
    polluted_expected = _expected_row("rec-001", {"answer": "x"})
    polluted_expected["privacy_class"] = "private"  # overwrite-attack vector
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [_base_input_row("rec-001", {"q": "x"})],  # input declares "public"
        [polluted_expected],
    )
    with pytest.raises(ValueError, match="unexpected keys"):
        load_tier("A", skill, tmp_path)


def test_input_missing_record_id_key(tmp_path: Path) -> None:
    """input.jsonl row literally lacking the 'record_id' key — distinct diagnostic
    from a row that contains the key with a blank value."""
    skill = "skill_x"
    bad_row = _base_input_row("rec-001", {"q": "x"})
    del bad_row["record_id"]
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [bad_row],
        [_expected_row("rec-001", {"answer": "x"})],
    )
    with pytest.raises(ValueError, match="missing 'record_id' key"):
        load_tier("A", skill, tmp_path)


def test_input_blank_record_id_value(tmp_path: Path) -> None:
    """input.jsonl row that DOES carry 'record_id' but with an empty string —
    diagnostic must explicitly say 'blank', not be conflated with 'missing key'."""
    skill = "skill_x"
    bad_row = _base_input_row("rec-001", {"q": "x"})
    bad_row["record_id"] = ""
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [bad_row],
        [_expected_row("rec-001", {"answer": "x"})],
    )
    with pytest.raises(ValueError, match="blank 'record_id' value"):
        load_tier("A", skill, tmp_path)


def test_expected_missing_record_id_key(tmp_path: Path) -> None:
    """expected.jsonl mirror of test_input_missing_record_id_key."""
    skill = "skill_x"
    bad_exp = _expected_row("rec-001", {"answer": "x"})
    del bad_exp["record_id"]
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [_base_input_row("rec-001", {"q": "x"})],
        [bad_exp],
    )
    with pytest.raises(ValueError, match="missing 'record_id' key"):
        load_tier("A", skill, tmp_path)


def test_expected_blank_record_id_value(tmp_path: Path) -> None:
    """expected.jsonl mirror of test_input_blank_record_id_value."""
    skill = "skill_x"
    bad_exp = _expected_row("rec-001", {"answer": "x"})
    bad_exp["record_id"] = ""
    _make_fixture(
        tmp_path,
        skill,
        "A",
        [_base_input_row("rec-001", {"q": "x"})],
        [bad_exp],
    )
    with pytest.raises(ValueError, match="blank 'record_id' value"):
        load_tier("A", skill, tmp_path)


def test_load_tier_accepts_null_expected_payload(tmp_path: Path) -> None:
    """Spec §3.1.5: `expected` may be null (Tier-D-shaped record, exercised here
    on the Tier C code path with match_mode='judge_only'). The loader must
    accept it and surface it as EvalRecord.expected == None."""
    skill = "skill_x"
    tier = "C"
    _make_fixture(
        tmp_path,
        skill,
        tier,
        [_base_input_row("rec-001", {"q": "x"}, match_mode="judge_only")],
        [_expected_row("rec-001", None)],
    )

    records = load_tier(tier, skill, tmp_path)
    assert len(records) == 1
    assert records[0].expected is None
    assert records[0].match_mode == "judge_only"
