from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nanobot.curator.models import Confidence, CuratorAction, CuratorProposal, ProposalReason
from nanobot.evolve.proposals import (
    EvolutionProposal,
    ProposalRunner,
    ProposalStore,
    create_dream_proposal,
    create_manual_proposal,
    format_proposal_list,
    format_proposal_show,
    proposals_from_curator,
)
from nanobot.evolve.schemas import EvolutionProposalContext, JudgeSummary, RunManifest


@pytest.mark.parametrize("skill_name", ["../secret", "nested/skill", "nested\\skill", "bad\nname"])
def test_create_manual_proposal_rejects_path_like_skill_names(
    tmp_path: Path,
    skill_name: str,
) -> None:
    store = ProposalStore(tmp_path)

    with pytest.raises(ValueError, match="skill_name"):
        create_manual_proposal(store, skill_name=skill_name, rationale="try it")


def test_create_manual_proposal_redacts_sensitive_rationale(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)

    proposal = create_manual_proposal(
        store,
        skill_name="demo-skill",
        rationale="Improve answers for alice@example.com and /Users/alice/private.txt",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    loaded = store.get(proposal.proposal_id)
    data = json.loads((tmp_path / "evals" / "proposals" / f"{proposal.proposal_id}.json").read_text())
    assert data["schemaVersion"] == "1"
    assert loaded.schema_version == "1"
    assert loaded.skill_name == "demo-skill"
    assert loaded.source == "manual"
    assert "alice@example.com" not in loaded.rationale_redacted
    assert "/Users/alice" not in loaded.rationale_redacted
    assert "[REDACTED:EMAIL]" in loaded.rationale_redacted
    assert loaded.status == "proposed"
    assert (tmp_path / "evals" / "proposals" / f"{proposal.proposal_id}.json").is_file()


def test_proposal_store_initializes_proposal_directory(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)

    assert store.proposals_dir.is_dir()


def test_create_manual_proposal_does_not_touch_skills_dir(tmp_path: Path) -> None:
    skill_path = tmp_path / "skills" / "agent" / "demo-skill" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_content = (
        "---\n"
        "name: demo-skill\n"
        "description: Demo skill\n"
        "origin: agent\n"
        "created_by: test\n"
        "created_at: 2026-01-01T00:00:00Z\n"
        "---\n"
        "Use concise answers.\n"
    )
    skill_path.write_text(skill_content, encoding="utf-8")

    create_manual_proposal(
        ProposalStore(tmp_path),
        skill_name="demo-skill",
        rationale="try offline improvement",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert skill_path.read_text(encoding="utf-8") == skill_content


def test_proposal_store_lists_newest_first(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    first = store.create(
        source="manual",
        skill_name="alpha",
        rationale="first",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )
    second = store.create(
        source="dream",
        skill_name="beta",
        rationale="second",
        now=datetime(2026, 6, 16, 12, 1, tzinfo=timezone.utc),
    )

    assert [p.proposal_id for p in store.list()] == [second.proposal_id, first.proposal_id]


def test_proposal_store_rejects_path_traversal_lookup(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)

    with pytest.raises(ValueError, match="letters"):
        store.get("../outside")


@pytest.mark.parametrize("prefix", ["evolve-*", "evolve-?", "evolve-[abc]"])
def test_proposal_store_rejects_glob_wildcard_lookup(tmp_path: Path, prefix: str) -> None:
    store = ProposalStore(tmp_path)

    with pytest.raises(ValueError, match="letters"):
        store.get(prefix)


def test_proposal_store_rejects_too_short_prefix(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)

    with pytest.raises(ValueError, match="at least"):
        store.get("evolve")


def test_proposal_store_rejects_ambiguous_prefix(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    store.write(
        EvolutionProposal(
            proposal_id="evolve-20260616T120000Z-demo-skill-0001",
            created_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
            source="manual",
            skill_name="demo-skill",
            rationale_redacted="one",
        )
    )
    store.write(
        EvolutionProposal(
            proposal_id="evolve-20260616T120000Z-demo-skill-0002",
            created_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
            source="manual",
            skill_name="demo-skill",
            rationale_redacted="two",
        )
    )

    with pytest.raises(ValueError, match="ambiguous"):
        store.get("evolve-20260616T120000Z-demo-skill")


def test_proposals_from_curator_turns_patch_and_merge_into_evolution_proposals(
    tmp_path: Path,
) -> None:
    store = ProposalStore(tmp_path)
    curator_proposals = [
        CuratorProposal(
            name="demo-skill",
            origin="agent",
            action=CuratorAction.PATCH_CANDIDATE,
            confidence=Confidence.MEDIUM,
            reasons=[ProposalReason(code="patch_churn_low_use", params={"uses": 1})],
        ),
        CuratorProposal(
            name="cleanup-me",
            origin="agent",
            action=CuratorAction.DELETE_CANDIDATE,
            confidence=Confidence.HIGH,
            reasons=[ProposalReason(code="zero_uses_after_views", params={"views": 40})],
        ),
    ]

    created = proposals_from_curator(
        store,
        curator_proposals,
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    assert len(created) == 1
    assert created[0].source == "curator"
    assert created[0].skill_name == "demo-skill"
    assert created[0].trigger_ref == "curator:patch_candidate"
    assert "patch_churn_low_use" in created[0].rationale_redacted


def test_format_proposal_list_and_show(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    proposal = store.create(
        source="manual",
        skill_name="demo-skill",
        rationale="make answers clearer",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    list_text = format_proposal_list(store.list())
    show_text = format_proposal_show(proposal)

    assert "Evolution proposals" in list_text
    assert proposal.proposal_id in list_text
    assert "demo-skill" in list_text
    assert "Proposal" in show_text
    assert "make answers clearer" in show_text


def _judge_summary() -> JudgeSummary:
    return JudgeSummary(
        record_count=0,
        median_aggregate=0.0,
        median_process=0.0,
        median_output=0.0,
        median_token=0.0,
        consensus_split_count=0,
    )


def _run_manifest(run_id: str = "run-1") -> RunManifest:
    return RunManifest(
        run_id=run_id,
        started_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 6, 16, 12, 1, tzinfo=timezone.utc),
        nanobot_version="0.0.0",
        evolve_extra_version={"optimizer": "stub"},
        skill_name="demo-skill",
        baseline_hash="basehash00112233",
        candidate_hashes=[],
        promoted_candidate_hash=None,
        gate_verdicts=[],
        judge_summary=_judge_summary(),
        final_status="no_improvement",
        tiers_used=["A"],
        record_count_per_tier={"A": 0},
        judge_pool_health={},
    )


def test_create_dream_proposal_deduplicates_trigger_ref(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    first = create_dream_proposal(
        store,
        skill_name="dream-memory",
        rationale="Dream completed after processing 12 history entries.",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
        trigger_ref="dream:cursor:12",
    )
    second = create_dream_proposal(
        store,
        skill_name="dream-memory",
        rationale="Dream completed after processing 12 history entries.",
        now=datetime(2026, 6, 16, 12, 1, tzinfo=timezone.utc),
        trigger_ref="dream:cursor:12",
    )

    assert second.proposal_id == first.proposal_id
    assert len(store.list()) == 1


def test_proposal_runner_rejects_path_like_skill_name_before_writing_run_dir(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    proposal = EvolutionProposal.model_construct(
        schema_version="1",
        proposal_id="evolve-20260616T120000Z-demo-skill-0001",
        created_at=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
        source="manual",
        skill_name="../../secret",
        rationale_redacted="try path escape",
        status="proposed",
    )
    store.write(proposal)

    with pytest.raises(ValueError, match="skill_name"):
        ProposalRunner(store).run(
            proposal.proposal_id,
            optimizer_command=["python", "optimizer.py"],
            tiers=["A"],
            max_candidates=1,
            optimizer_timeout_seconds=5,
        )

    assert not (tmp_path / "evals" / "runs").exists()


def test_proposal_store_rejects_running_proposal_transition(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    proposal = store.create(
        source="manual",
        skill_name="demo-skill",
        rationale="try offline improvement",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    running = store.mark_running(proposal)

    with pytest.raises(RuntimeError, match="already running"):
        store.mark_running(running)


def test_proposal_store_rejects_completed_proposal_rerun(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    proposal = store.create(
        source="manual",
        skill_name="demo-skill",
        rationale="try offline improvement",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )
    running = store.mark_running(proposal)
    completed = store.mark_completed(running, _run_manifest("run-1"))

    with pytest.raises(RuntimeError, match="already completed"):
        store.mark_running(completed)


def test_proposal_runner_marks_completed_and_records_manifest(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = ProposalStore(tmp_path)
    proposal = store.create(
        source="manual",
        skill_name="demo-skill",
        rationale="try offline improvement",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    class StubHarness:
        def __init__(self, *, workspace: Path) -> None:
            assert workspace == tmp_path

        def run(self, **kwargs) -> RunManifest:
            assert kwargs == {
                "skill_name": "demo-skill",
                "optimizer_command": ["python", "optimizer.py"],
                "tiers": ["A", "C"],
                "max_candidates": 4,
                "optimizer_timeout_seconds": 30,
                "proposal_context": EvolutionProposalContext(
                    proposal_id="evolve-20260616T120000Z-demo-skill-0001",
                    source="manual",
                ),
            }
            return _run_manifest("run-1")

    monkeypatch.setattr("nanobot.evolve.proposals.OfflineHarness", StubHarness)

    runner = ProposalRunner(store)
    result = runner.run(
        proposal.proposal_id,
        optimizer_command=["python", "optimizer.py"],
        tiers=["A", "C"],
        max_candidates=4,
        optimizer_timeout_seconds=30,
    )

    assert result.proposal.status == "completed"
    assert result.proposal.run_id == "run-1"
    assert result.proposal.manifest_path == "evals/runs/run-1/manifest.json"
    assert store.get(proposal.proposal_id).status == "completed"


def test_proposal_runner_marks_failed_with_redacted_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = ProposalStore(tmp_path)
    proposal = store.create(
        source="manual",
        skill_name="demo-skill",
        rationale="try offline improvement",
        now=datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc),
    )

    class StubHarness:
        def __init__(self, *, workspace: Path) -> None:
            pass

        def run(self, **kwargs):
            raise RuntimeError("failed for alice@example.com")

    monkeypatch.setattr("nanobot.evolve.proposals.OfflineHarness", StubHarness)

    runner = ProposalRunner(store)

    with pytest.raises(RuntimeError):
        runner.run(
            proposal.proposal_id,
            optimizer_command=["python", "optimizer.py"],
            tiers=["A"],
            max_candidates=1,
            optimizer_timeout_seconds=5,
        )

    failed = store.get(proposal.proposal_id)
    assert failed.status == "failed"
    assert "alice@example.com" not in failed.error_redacted
    assert "[REDACTED:EMAIL]" in failed.error_redacted
