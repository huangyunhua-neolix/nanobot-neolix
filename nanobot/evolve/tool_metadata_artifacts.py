"""Tool-metadata artifact writing helpers for OfflineHarness run lanes."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nanobot.evolve.artifacts import (
    OwnedJsonlEvidenceWriter,
    atomic_write_text,
    write_jsonl_artifact,
    write_redacted_json_artifact,
)
from nanobot.evolve.judges.rubric import JudgeConfig, JudgePool
from nanobot.evolve.schemas import (
    ToolContractSnapshot,
    ToolMetadataCandidate,
    ToolMetadataValidationResult,
)
from nanobot.evolve.tool_metadata import (
    build_tool_metadata_judge_record,
    render_tool_metadata_review,
)

_TOOL_METADATA_JUDGE_EVIDENCE_PATH = "tool_metadata_judge_evidence.jsonl"
_TOOL_METADATA_ARTIFACT_PATHS: dict[str, str] = {
    "tool_contract_snapshot": "tool_contract_snapshot.json",
    "tool_metadata_candidates": "tool_metadata_candidates.jsonl",
    "tool_metadata_review": "tool_metadata_review.md",
}


def tool_metadata_artifact_plan() -> dict[str, str]:
    """Return the base artifact path plan for tool metadata."""
    return dict(_TOOL_METADATA_ARTIFACT_PATHS)


def matching_tool_snapshot(
    candidate: ToolMetadataCandidate,
    snapshot: list[ToolContractSnapshot],
) -> ToolContractSnapshot | None:
    """Return the baseline snapshot matching a metadata candidate contract."""
    return next(
        (
            item
            for item in snapshot
            if item.tool_name == candidate.tool_name
            and item.schema_hash == candidate.baseline_schema_hash
        ),
        None,
    )


def review_validation_results(
    results: list[ToolMetadataValidationResult],
    safe_single_line_reason: Callable[[str], str],
) -> list[ToolMetadataValidationResult]:
    """Return validation results with review-friendly rejection reasons."""
    return [
        result.model_copy(
            update={
                "reason": safe_single_line_reason(
                    f"{result.reason_code}: {result.reason}"
                    if result.verdict == "reject" and result.reason_code and result.reason
                    else result.reason or "<none>"
                )
            }
        )
        for result in results
    ]


def write_tool_metadata_judge_evidence(
    run_dir: Path,
    snapshot: list[ToolContractSnapshot],
    candidates: list[ToolMetadataCandidate],
    validation_results: list[ToolMetadataValidationResult],
) -> tuple[list[ToolMetadataValidationResult], str | None]:
    """Write deterministic judge evidence for accepted metadata candidates.

    Returns updated validation results (with judge_evidence_path set where applicable)
    and the evidence filename if any rows were written, otherwise None.
    """
    evidence_path = run_dir / _TOOL_METADATA_JUDGE_EVIDENCE_PATH
    writer = OwnedJsonlEvidenceWriter(evidence_path, evidence_name="tool metadata")
    writer.remove_untrusted()

    # One local judge keeps JudgePool's odd-size quorum invariant without tuning.
    judge_pool = JudgePool(judges=[JudgeConfig(model="local/deterministic")])
    updated_results = list(validation_results)
    for index, (candidate, result) in enumerate(zip(candidates, validation_results)):
        if result.verdict != "accept":
            continue
        baseline = matching_tool_snapshot(candidate, snapshot)
        if baseline is None:
            continue
        evidence = judge_pool.score_with_evidence(
            build_tool_metadata_judge_record(candidate, baseline)
        )
        writer.buffer(evidence.model_dump_json(by_alias=True))
        updated_results[index] = result.model_copy(
            update={"judge_evidence_path": _TOOL_METADATA_JUDGE_EVIDENCE_PATH}
        )

    published = writer.publish()
    return updated_results, published


def write_tool_metadata_artifacts(
    run_dir: Path,
    snapshot: list[ToolContractSnapshot],
    candidates: list[ToolMetadataCandidate],
    validation_results: list[ToolMetadataValidationResult],
    judge_evidence_path: str | None,
    safe_single_line_reason: Callable[[str], str],
) -> dict[str, str]:
    """Write metadata artifacts after optional judge evidence has been written."""
    if not snapshot and not candidates:
        return {}

    artifact_paths = tool_metadata_artifact_plan()
    if judge_evidence_path is not None:
        artifact_paths["tool_metadata_judge_evidence"] = judge_evidence_path
    write_redacted_json_artifact(
        run_dir / artifact_paths["tool_contract_snapshot"],
        [item.model_dump(mode="json", by_alias=True) for item in snapshot],
        ensure_ascii=True,
    )
    write_jsonl_artifact(
        run_dir / artifact_paths["tool_metadata_candidates"],
        [candidate.model_dump(mode="json", by_alias=True) for candidate in candidates],
        sort_keys=False,
        compact=True,
    )
    atomic_write_text(
        run_dir / artifact_paths["tool_metadata_review"],
        render_tool_metadata_review(
            snapshot,
            candidates,
            review_validation_results(validation_results, safe_single_line_reason),
        ),
    )
    return artifact_paths
