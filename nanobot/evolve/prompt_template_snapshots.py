from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from nanobot.evolve.prompt_template_boundaries import (
    PromptTemplateBoundaryError,
    parse_editable_regions,
)
from nanobot.evolve.schemas import PromptTemplateSnapshot

_DEFAULT_BUNDLED_SKILLS_DIR = Path(__file__).resolve().parents[2] / "nanobot" / "skills"


def normalize_body_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text.removeprefix("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", text)


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [json_safe(child) for child in value]
    if isinstance(value, tuple):
        return [json_safe(child) for child in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def hash_json(value: Any) -> str:
    encoded = json.dumps(
        json_safe(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_skill_markdown(text: str) -> tuple[dict[str, Any], str]:
    normalized = normalize_body_text(text)
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end < 0:
        return {}, normalized
    frontmatter_text = normalized[4:end]
    body = normalized[end + 5 :]
    try:
        parsed = yaml.safe_load(frontmatter_text) or {}
    except YAMLError:
        parsed = _parse_lenient_frontmatter(frontmatter_text)
    if not isinstance(parsed, dict):
        raise PromptTemplateBoundaryError("frontmatter must be a YAML mapping")
    return parsed, body


def _parse_lenient_frontmatter(frontmatter_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def line_count(text: str) -> int:
    if text == "":
        return 0
    return len(text.splitlines())


def snapshot_from_skill_markdown(
    *,
    skill_name: str,
    source_identifier: str,
    text: str,
) -> PromptTemplateSnapshot:
    frontmatter, body = parse_skill_markdown(text)
    body = normalize_body_text(body)
    regions = parse_editable_regions(body)
    frontmatter_hash = hash_json(frontmatter)
    body_hash = hash_text(body)
    cache_key_hash = hash_text(str(frontmatter.get("description", "")))
    body_line_count = line_count(body)
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
    snapshot_hash = hash_json(snapshot_payload)
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
