"""nanobot.evolve.data — 4-tier eval data model + loader (M4 §3.1).

Spec authority: docs/hermes-evolution/specs/m4-offline-skeleton.md §3.1.

Data-integrity invariant (§3.1, line 365):
    "...两文件由同一脚本一次写出，行序对齐 record_id 但读取仍以 record_id join,
     不依赖行号."
Loader MUST join input.jsonl + expected.jsonl by ``record_id``, never by line index.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field

from nanobot.evolve._base import EvolveBase

Tier = Literal["A", "B", "C", "D"]


class EvalRecord(EvolveBase):
    """Single eval sample (input + expected + metadata); tier-agnostic.

    Mirrors spec §3.1.1 (the 9 fields). ``tags`` defaults to empty list.
    """

    record_id: str
    tier: Tier
    skill_name: str
    input: dict
    expected: Optional[dict] = None
    match_mode: Literal["loose", "strict", "judge_only", "binary_verdict"]
    privacy_class: Literal["public", "private"]
    created_at: datetime
    source: str
    tags: list[str] = Field(default_factory=list)


def _read_jsonl(path: Path) -> list[dict]:
    """Read a jsonl file; blank lines tolerated; malformed lines raise."""
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{lineno}: malformed JSON line: {exc}"
                ) from exc
    return records


def load_tier(tier: Tier, skill_name: str, root: Path) -> list[EvalRecord]:
    """Read paired ``input.jsonl`` + ``expected.jsonl`` and join by ``record_id``.

    Layout: ``<root>/<skill_name>/<tier>/{input,expected}.jsonl``.

    Join semantics (§3.1, line 365): records are matched by ``record_id``,
    NOT by line number. A missing pair on either side is an error; extra
    records on either side are an error. ``expected`` may be ``null`` in
    the expected.jsonl payload (Tier D-like cases).

    Return order is the order of records in ``input.jsonl``.
    """
    if tier in ("B", "D"):
        raise NotImplementedError(
            f"Tier {tier} requires a dedicated loader per spec §3.1.3/§3.1.5 "
            f"(Tier B uses session-jsonl-by-date; Tier D uses per-task JSON triples); "
            f"pending t-11 harness wiring."
        )

    tier_dir = Path(root) / skill_name / tier
    input_path = tier_dir / "input.jsonl"
    expected_path = tier_dir / "expected.jsonl"

    if not input_path.is_file():
        raise FileNotFoundError(f"missing input file: {input_path}")
    if not expected_path.is_file():
        raise FileNotFoundError(f"missing expected file: {expected_path}")

    input_rows = _read_jsonl(input_path)
    expected_rows = _read_jsonl(expected_path)

    expected_by_id: dict[str, dict] = {}
    for row in expected_rows:
        rid = row.get("record_id")
        if not rid:
            raise ValueError(
                f"{expected_path}: row missing 'record_id': {row!r}"
            )
        if rid in expected_by_id:
            raise ValueError(
                f"{expected_path}: duplicate record_id {rid!r}"
            )
        expected_by_id[rid] = row

    seen_input_ids: set[str] = set()
    out: list[EvalRecord] = []
    for row in input_rows:
        rid = row.get("record_id")
        if not rid:
            raise ValueError(f"{input_path}: row missing 'record_id': {row!r}")
        if rid in seen_input_ids:
            raise ValueError(f"{input_path}: duplicate record_id {rid!r}")
        seen_input_ids.add(rid)

        exp_row = expected_by_id.pop(rid, None)
        if exp_row is None:
            raise ValueError(
                f"record_id {rid!r} present in {input_path.name} but missing "
                f"from {expected_path.name}"
            )

        merged = {**row, **exp_row}
        # Loader fills tier + skill_name from path context if record omits them,
        # making fixture writing less verbose and aligning with the on-disk
        # convention (tier directory IS the source of truth for tier label).
        # If the row carries an explicit value, it MUST match path-context;
        # silent drift would let a mis-curated corpus pass through to the harness.
        if "tier" in merged:
            if merged["tier"] != tier:
                raise ValueError(
                    f"{input_path}:rid={rid!r}: in-row tier={merged['tier']!r} "
                    f"disagrees with path-context tier={tier!r}"
                )
        else:
            merged["tier"] = tier

        if "skill_name" in merged:
            if merged["skill_name"] != skill_name:
                raise ValueError(
                    f"{input_path}:rid={rid!r}: in-row skill_name={merged['skill_name']!r} "
                    f"disagrees with path-context skill_name={skill_name!r}"
                )
        else:
            merged["skill_name"] = skill_name

        out.append(EvalRecord.model_validate(merged))

    if expected_by_id:
        leftover = sorted(expected_by_id.keys())
        raise ValueError(
            f"record_id(s) present in {expected_path.name} but missing from "
            f"{input_path.name}: {leftover}"
        )

    return out


__all__ = ["EvalRecord", "Tier", "load_tier"]
