from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from nanobot.evolve.schemas import PromptTemplateSnapshot

_EDITABLE_START = "<!-- evolve:prompt-editable:start -->"
_EDITABLE_END = "<!-- evolve:prompt-editable:end -->"
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_DEFAULT_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parents[2] / "nanobot" / "skills"


class PromptTemplateBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class EditableRegion:
    start_line: int
    end_line: int


def _normalize_body_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text.removeprefix("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [_json_safe(child) for child in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        _json_safe(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _parse_skill_markdown(text: str) -> tuple[dict[str, Any], str]:
    normalized = _normalize_body_text(text)
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return {}, normalized
    frontmatter_text = normalized[4:end]
    body = normalized[end + 5 :]
    parsed = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(parsed, dict):
        raise PromptTemplateBoundaryError("frontmatter must be a YAML mapping")
    return parsed, body


def _line_count(text: str) -> int:
    if text == "":
        return 0
    return len(text.splitlines())


def parse_editable_regions(body: str) -> list[EditableRegion]:
    lines = body.splitlines()
    in_fence = False
    active_start: int | None = None
    regions: list[EditableRegion] = []
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        stripped = line.strip()
        if stripped == _EDITABLE_START:
            if active_start is not None:
                raise PromptTemplateBoundaryError("nested editable region marker")
            active_start = index + 1
            continue
        if stripped == _EDITABLE_END:
            if active_start is None:
                raise PromptTemplateBoundaryError("unbalanced editable region marker")
            regions.append(EditableRegion(start_line=active_start, end_line=index - 1))
            active_start = None
    if active_start is not None:
        raise PromptTemplateBoundaryError("unbalanced editable region marker")
    return regions


def snapshot_from_skill_markdown(
    *,
    skill_name: str,
    source_identifier: str,
    text: str,
) -> PromptTemplateSnapshot:
    frontmatter, body = _parse_skill_markdown(text)
    body = _normalize_body_text(body)
    regions = parse_editable_regions(body)
    frontmatter_hash = _hash_json(frontmatter)
    body_hash = _hash_text(body)
    cache_key_hash = _hash_text(str(frontmatter.get("description", "")))
    body_line_count = _line_count(body)
    snapshot_payload = {
        "skill_name": skill_name,
        "source_kind": "bundled",
        "source_identifier": source_identifier,
        "frontmatter_hash": frontmatter_hash,
        "body_hash": body_hash,
        "cache_key_hash": cache_key_hash,
        "editable_region_count": len(regions),
        "body_line_count": body_line_count,
    }
    snapshot_hash = _hash_json(snapshot_payload)
    return PromptTemplateSnapshot(
        skill_name=skill_name,
        source_kind="bundled",
        source_identifier=source_identifier,
        frontmatter_hash=frontmatter_hash,
        body_hash=body_hash,
        cache_key_hash=cache_key_hash,
        editable_region_count=len(regions),
        body_line_count=body_line_count,
        snapshot_hash=snapshot_hash,
        body_text=body,
    )


def capture_bundled_prompt_template_snapshot(
    bundled_skills_dir: Path = _DEFAULT_BUNDLED_SKILLS_DIR,
) -> list[PromptTemplateSnapshot]:
    if not bundled_skills_dir.exists():
        return []
    snapshots: list[PromptTemplateSnapshot] = []
    for path in sorted(bundled_skills_dir.glob("*/SKILL.md"), key=lambda item: item.parent.name):
        skill_name = path.parent.name
        source_identifier = f"nanobot/skills/{skill_name}/SKILL.md"
        snapshots.append(
            snapshot_from_skill_markdown(
                skill_name=skill_name,
                source_identifier=source_identifier,
                text=path.read_text(encoding="utf-8"),
            )
        )
    return snapshots
