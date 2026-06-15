"""Prompt-template artifact writing helpers for OfflineHarness run lanes."""

from __future__ import annotations

from pathlib import Path

from nanobot.evolve.artifacts import (
    OwnedJsonlEvidenceWriter,
    atomic_write_text,
    write_jsonl_artifact,
    write_redacted_json_artifact,
)
from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool
from nanobot.evolve.prompt_template_review import (
    build_prompt_template_judge_record,
    render_prompt_template_review,
)
from nanobot.evolve.schemas import (
    PromptTemplateCandidate,
    PromptTemplateSnapshot,
    PromptTemplateValidationResult,
)

_PROMPT_TEMPLATE_JUDGE_EVIDENCE_PATH = "prompt_template_judge_evidence.jsonl"
_PROMPT_TEMPLATE_ARTIFACT_PATHS: dict[str, str] = {
    "prompt_template_snapshot": "prompt_template_snapshot.json",
    "prompt_template_candidates": "prompt_template_candidates.jsonl",
    "prompt_template_review": "prompt_template_review.md",
}


def prompt_template_artifact_plan() -> dict[str, str]:
    """Return the base artifact path plan for prompt templates."""
    return dict(_PROMPT_TEMPLATE_ARTIFACT_PATHS)


def matching_prompt_template_snapshot(
    candidate: PromptTemplateCandidate,
    snapshot: list[PromptTemplateSnapshot],
) -> PromptTemplateSnapshot | None:
    """Return the baseline snapshot matching a prompt/template candidate."""
    return next(
        (
            item
            for item in snapshot
            if item.skill_name == candidate.skill_name
            and item.snapshot_hash == candidate.baseline_snapshot_hash
        ),
        None,
    )


def write_prompt_template_judge_evidence(
    run_dir: Path,
    snapshot: list[PromptTemplateSnapshot],
    candidates: list[PromptTemplateCandidate],
    validation_results: list[PromptTemplateValidationResult],
) -> tuple[list[PromptTemplateValidationResult], str | None]:
    """Write deterministic judge evidence for accepted non-noop prompt candidates.

    Returns updated validation results (with judge_evidence_path set where applicable)
    and the evidence filename if any rows were written, otherwise None.
    """
    evidence_path = run_dir / _PROMPT_TEMPLATE_JUDGE_EVIDENCE_PATH
    writer = OwnedJsonlEvidenceWriter(evidence_path, evidence_name="prompt template")
    writer.remove_untrusted()

    judge_pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
    updated_results = list(validation_results)
    for index, (candidate, result) in enumerate(zip(candidates, validation_results)):
        if result.verdict != "accept" or result.cache_impact == "candidate_noop":
            continue
        baseline = matching_prompt_template_snapshot(candidate, snapshot)
        if baseline is None:
            continue
        evidence = judge_pool.score_with_evidence(
            build_prompt_template_judge_record(candidate, baseline)
        )
        writer.buffer(evidence.model_dump_json(by_alias=True))
        updated_results[index] = result.model_copy(
            update={"judge_evidence_path": _PROMPT_TEMPLATE_JUDGE_EVIDENCE_PATH}
        )

    published = writer.publish()
    return updated_results, published


def write_prompt_template_artifacts(
    run_dir: Path,
    snapshot: list[PromptTemplateSnapshot],
    candidates: list[PromptTemplateCandidate],
    validation_results: list[PromptTemplateValidationResult],
    judge_evidence_path: str | None,
) -> dict[str, str]:
    """Write inert prompt/template snapshot, candidate, and review artifacts."""
    if not snapshot and not candidates:
        return {}

    artifact_paths = prompt_template_artifact_plan()
    if judge_evidence_path is not None:
        artifact_paths["prompt_template_judge_evidence"] = judge_evidence_path
    write_redacted_json_artifact(
        run_dir / artifact_paths["prompt_template_snapshot"],
        [item.model_dump(mode="json", by_alias=True) for item in snapshot],
    )
    write_jsonl_artifact(
        run_dir / artifact_paths["prompt_template_candidates"],
        [candidate.model_dump(mode="json", by_alias=True) for candidate in candidates],
    )
    atomic_write_text(
        run_dir / artifact_paths["prompt_template_review"],
        render_prompt_template_review(snapshot, candidates, validation_results),
    )
    return artifact_paths
