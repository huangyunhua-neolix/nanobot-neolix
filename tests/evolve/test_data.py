"""Tests for nanobot.evolve.data (M4 §3.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nanobot.evolve.data import EvalRecord, load_tier


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


def _base_input_row(rid: str, payload: dict, source: str = "synthesizer:s0") -> dict:
    return {
        "record_id": rid,
        "input": payload,
        "privacy_class": "public",
        "created_at": datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        "source": source,
        "tags": [],
    }


def _expected_row(rid: str, payload: dict | None, match_mode: str = "judge_only") -> dict:
    return {
        "record_id": rid,
        "expected": payload,
        "match_mode": match_mode,
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
        _base_input_row("rec-001", {"q": "alpha"}, source="curator:alice"),
        _base_input_row("rec-002", {"q": "beta"}, source="curator:alice"),
        _base_input_row("rec-003", {"q": "gamma"}, source="curator:alice"),
    ]
    # expected.jsonl deliberately written in REVERSE line order
    expected_rows = [
        _expected_row("rec-003", {"key_outputs": {"value": "gamma-ok"}}, match_mode="strict"),
        _expected_row("rec-001", {"key_outputs": {"value": "alpha-ok"}}, match_mode="strict"),
        _expected_row("rec-002", {"key_outputs": {"value": "beta-ok"}}, match_mode="strict"),
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


def test_load_tier_b_raises_not_implemented(tmp_path: Path) -> None:
    """Tier B has a dedicated session-jsonl layout (§3.1.3); generic loader refuses."""
    with pytest.raises(NotImplementedError, match="Tier B"):
        load_tier("B", "any_skill", tmp_path)


def test_load_tier_d_raises_not_implemented(tmp_path: Path) -> None:
    """Tier D has a per-task JSON-triple layout (§3.1.5); generic loader refuses."""
    with pytest.raises(NotImplementedError, match="Tier D"):
        load_tier("D", "any_skill", tmp_path)


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
