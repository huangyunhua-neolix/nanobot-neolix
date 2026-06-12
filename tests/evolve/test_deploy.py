"""Tests for ``nanobot.evolve.deploy`` — spec §8."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from nanobot.evolve.deploy import (
    PR_BODY_SECTIONS,
    PROTECTED_BRANCHES,
    assemble_pr_body,
    assert_not_main,
    build_branch_name,
)
from nanobot.evolve.exceptions import ApplyTerminalError
from nanobot.evolve.gates import GateResult
from nanobot.evolve.harness import JudgeSummary, RunManifest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=10,
        median_aggregate=0.8,
        median_process=0.8,
        median_output=0.8,
        median_token=0.8,
        consensus_split_count=0,
    )


def _make_run_manifest(**overrides: object) -> RunManifest:
    fields: dict[str, object] = dict(
        run_id="run-xyz",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
        nanobot_version="0.0.0",
        evolve_extra_version={"dspy": "2.4.0"},
        skill_name="demo-skill",
        baseline_hash="basehash00112233",
        candidate_hashes=["candhash44556677"],
        promoted_candidate_hash="candhash44556677",
        gate_verdicts=[],
        judge_summary=_make_judge_summary(),
        final_status="promoted_to_pr",
        tiers_used=["A", "C"],
        record_count_per_tier={"A": 5, "C": 3},
        judge_pool_health={"pool-a": "ok"},
    )
    fields.update(overrides)
    return RunManifest(**fields)  # type: ignore[arg-type]


def _gate_result(name: str, *, verdict: str = "pass", reason: str | None = None) -> GateResult:
    return GateResult(
        gate_name=name,
        candidate_hash="candhash44556677",
        baseline_hash="basehash00112233",
        verdict=verdict,  # type: ignore[arg-type]
        metrics={"score": 1.0},
        failure_reason=reason,
        timestamp=datetime(2026, 1, 1, 0, 4, tzinfo=timezone.utc),
        duration_ms=42,
    )


# ---------------------------------------------------------------------------
# build_branch_name (§8.1)
# ---------------------------------------------------------------------------


def test_build_branch_name_format() -> None:
    # Spec §8.1 pins the literal concatenation contract; tighten with multiple
    # input combos so any drift (separator change, prefix change, reordering)
    # is caught.
    assert (
        build_branch_name("run-1", "demo-skill", "deadbeef")
        == "evolve/run-1-demo-skill-deadbeef"
    )
    assert (
        build_branch_name("R", "S", "00112233")
        == "evolve/R-S-00112233"
    )


def test_build_branch_name_prefix_always_evolve() -> None:
    name = build_branch_name("anything", "whatever", "abc01234")
    assert name.startswith("evolve/")


# ---------------------------------------------------------------------------
# assert_not_main (§8.1)
# ---------------------------------------------------------------------------


def test_protected_branches_set_is_main_and_master() -> None:
    # Spec §8.1 currently pins exactly main + master at the local hard-check
    # layer; expanding this set is a spec change, not an implementation tweak.
    assert PROTECTED_BRANCHES == frozenset({"main", "master"})


def test_assert_not_main_raises_on_main(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    with pytest.raises(ApplyTerminalError) as exc_info:
        assert_not_main(
            "main", manifest_path=manifest_path, final_status="harness_error"
        )
    # §5.3 STRUCTURED_KWARGS contract: attrs must be stored on the exception.
    assert exc_info.value.final_status == "harness_error"
    assert exc_info.value.manifest_path == manifest_path
    assert "main" in str(exc_info.value)


def test_assert_not_main_raises_on_master(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    with pytest.raises(ApplyTerminalError) as exc_info:
        assert_not_main(
            "master",
            manifest_path=manifest_path,
            final_status="rejected_by_gate",
        )
    assert exc_info.value.final_status == "rejected_by_gate"
    assert exc_info.value.manifest_path == manifest_path
    assert "master" in str(exc_info.value)


def test_assert_not_main_passes_on_feature_branch(tmp_path: Path) -> None:
    # Returns None (no raise) for any non-protected branch — pipeline path.
    result = assert_not_main(
        "evolve/run-1-demo-skill-deadbeef",
        manifest_path=tmp_path / "m.json",
        final_status="promoted_to_pr",
    )
    assert result is None


def test_assert_not_main_passes_on_user_feature_branch(tmp_path: Path) -> None:
    # Spec §8.1 allows user-driven feature/* branches as base.
    assert (
        assert_not_main(
            "feature/m4-offline-skeleton",
            manifest_path=tmp_path / "m.json",
            final_status="promoted_to_pr",
        )
        is None
    )


# ---------------------------------------------------------------------------
# assemble_pr_body (§8.2)
# ---------------------------------------------------------------------------


def _section_headers_in_order(body: str) -> list[str]:
    # Capture every line that starts with "## " — the level used by the spec
    # for the 5 sections. Sub-headers would be "### " etc., so this is exact.
    return [line[3:].strip() for line in body.splitlines() if line.startswith("## ")]


def test_assemble_pr_body_has_5_sections_in_order() -> None:
    manifest = _make_run_manifest()
    body = assemble_pr_body(manifest, [])
    headers = _section_headers_in_order(body)
    # Pin BOTH count and order — a regression that reorders or duplicates the
    # sections must fail loudly.
    assert len(headers) == 5
    assert headers == [
        "Summary",
        "Eval results",
        "Gates passed",
        "Diff stats",
        "Rollback plan",
    ]
    # PR_BODY_SECTIONS constant must stay in sync.
    assert headers == list(PR_BODY_SECTIONS)


def test_assemble_pr_body_includes_manifest_run_id() -> None:
    manifest = _make_run_manifest(run_id="run-pinned-abc")
    body = assemble_pr_body(manifest, [])
    # Surface under Summary so reviewers can find the artifact path fast.
    summary_block = body.split("## Eval results")[0]
    assert "run-pinned-abc" in summary_block


def test_assemble_pr_body_includes_skill_name_and_final_status() -> None:
    manifest = _make_run_manifest(
        skill_name="my-skill", final_status="rejected_by_gate"
    )
    body = assemble_pr_body(manifest, [])
    assert "my-skill" in body
    assert "rejected_by_gate" in body


def test_assemble_pr_body_lists_gate_names() -> None:
    manifest = _make_run_manifest()
    gates = [
        _gate_result("1-test-pass"),
        _gate_result("2-size-cap"),
        _gate_result("3-cache-compat"),
    ]
    body = assemble_pr_body(manifest, gates)
    # Each passing gate name must appear under "## Gates passed".
    gates_section = body.split("## Gates passed", 1)[1].split("## Diff stats", 1)[0]
    for name in ("1-test-pass", "2-size-cap", "3-cache-compat"):
        assert name in gates_section


def test_assemble_pr_body_eval_results_marks_pass_and_fail() -> None:
    manifest = _make_run_manifest(final_status="rejected_by_gate")
    gates = [
        _gate_result("1-test-pass", verdict="pass"),
        _gate_result("2-size-cap", verdict="fail", reason="lines>cap"),
    ]
    body = assemble_pr_body(manifest, gates)
    eval_section = body.split("## Eval results", 1)[1].split("## Gates passed", 1)[0]
    assert "1-test-pass" in eval_section
    assert "PASS" in eval_section
    assert "2-size-cap" in eval_section
    assert "FAIL" in eval_section


def test_assemble_pr_body_rollback_plan_is_one_liner_git_revert() -> None:
    # §8.5: exactly one ``git revert`` line — no schema migrations / cleanup
    # steps for M4 candidates. Multi-line rollback would violate the contract.
    manifest = _make_run_manifest()
    body = assemble_pr_body(manifest, [])
    rollback_section = body.split("## Rollback plan", 1)[1].strip()
    # Pull just the content lines (skip blank lines).
    content_lines = [ln for ln in rollback_section.splitlines() if ln.strip()]
    assert len(content_lines) == 1
    assert "git revert" in content_lines[0]


def test_assemble_pr_body_is_deterministic() -> None:
    # Byte-stability under repeat calls — critical for audit / replay.
    manifest = _make_run_manifest()
    gates = [_gate_result("1-test-pass"), _gate_result("2-size-cap")]
    body1 = assemble_pr_body(manifest, gates)
    body2 = assemble_pr_body(manifest, gates)
    assert body1 == body2
