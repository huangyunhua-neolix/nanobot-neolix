from __future__ import annotations

from pathlib import Path

from nanobot.evolve.prompt_templates import snapshot_from_skill_markdown
from nanobot.evolve.schemas import PromptTemplateCandidate, PromptTemplateSnapshot


def skill_markdown(body: str, *, description: str = "Demo skill") -> str:
    return (
        "---\n"
        "name: demo-skill\n"
        f"description: {description}\n"
        "origin: bundled\n"
        "created_by: tests\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "---\n"
        f"{body}"
    )


def write_bundled_skill(root: Path, name: str, body: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    path = skill_dir / "SKILL.md"
    path.write_text(skill_markdown(body), encoding="utf-8")
    return path


def make_snapshot(body: str, *, skill_name: str = "demo-skill") -> PromptTemplateSnapshot:
    return snapshot_from_skill_markdown(
        skill_name=skill_name,
        source_identifier=f"nanobot/skills/{skill_name}/SKILL.md",
        text=skill_markdown(body),
    )


def make_candidate(
    snapshot: PromptTemplateSnapshot,
    proposed_body: str,
    *,
    skill_name: str | None = None,
    baseline_snapshot_hash: str | None = None,
) -> PromptTemplateCandidate:
    return PromptTemplateCandidate(
        skill_name=skill_name or snapshot.skill_name,
        baseline_snapshot_hash=baseline_snapshot_hash or snapshot.snapshot_hash,
        proposed_body=proposed_body,
        intended_improvement="Make the editable text clearer.",
        risk_assessment="Only editable prompt text changes.",
        cache_impact_claim="cache neutral",
    )
