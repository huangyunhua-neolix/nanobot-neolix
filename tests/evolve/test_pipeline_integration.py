"""Integration smoke for the 3-gate pipeline (spec §3.6 / §6.4 / §3.7).

Exercises the real ``GATES`` registry (``TestPassGate``, ``SkillSizeGate``,
``CacheCompatGate``) through ``OfflineHarness._run_gates`` with stub
``Baseline`` + ``Candidate`` pydantic instances. Also pins the
``EvolveExtraNotInstalled`` lazy-import contract: walking the gate chain MUST
NOT pull ``dspy`` or ``gepa`` into ``sys.modules`` — those are reserved for
the GEPA-driven ``run`` path that t-14 / t-15 will introduce.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nanobot.evolve.harness import (
    Baseline,
    Candidate,
    OfflineHarness,
    SkillFrontmatter,
)


def _frontmatter() -> SkillFrontmatter:
    return SkillFrontmatter(
        name="demo-skill",
        description="demo",
        origin="bundled",
        created_by="tests",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _baseline() -> Baseline:
    return Baseline(
        skill_name="demo-skill",
        skill_md_content="# demo",
        frontmatter=_frontmatter(),
        body_md="body",
        cache_key_hash="key-shared",
        # Populate the gate-1 + gate-2 keys on the baseline too; gate-1 reads
        # candidate.size_metrics, gate-2 reads both. Keeping the shape
        # symmetric avoids per-gate divergence creeping in.
        size_metrics={
            "lines": 280,
            "tier_c_pass": 10,
            "tier_c_total": 10,
            "tier_a_pass": 24,
            "tier_a_total": 25,
        },
        content_hash="base-hash",
        loaded_from="bundled:demo-skill",
        loaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _candidate(
    *,
    cache_key_hash: str = "key-shared",
    content_hash: str = "cand-hash",
    lines: int = 300,
) -> Candidate:
    return Candidate(
        skill_name="demo-skill",
        skill_md_content="# demo v2",
        frontmatter=_frontmatter(),
        body_md="body v2",
        cache_key_hash=cache_key_hash,
        size_metrics={
            # Gate 2: within 400 hard cap and 150 delta cap (vs baseline 280).
            "lines": lines,
            # Gate 1: tier-C 10/10 (>=1.00), tier-A 24/25 (>=0.80).
            "tier_c_pass": 10,
            "tier_c_total": 10,
            "tier_a_pass": 24,
            "tier_a_total": 25,
        },
        content_hash=content_hash,
        parent_baseline_hash="base-hash",
        gepa_iteration=1,
    )


@pytest.fixture
def clean_lazy_module_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop dspy/gepa from sys.modules so a sibling test that imported them
    cannot mask a real lazy-guard regression in the gate pipeline."""
    monkeypatch.delitem(sys.modules, "dspy", raising=False)
    monkeypatch.delitem(sys.modules, "gepa", raising=False)


def test_pipeline_build_pipeline_is_deprecated_shim_without_gepa_imports(
    clean_lazy_module_state: None,
) -> None:
    import nanobot.evolve.pipeline as pipeline
    from nanobot.evolve.exceptions import EvolveExtraNotInstalled

    assert not hasattr(pipeline, "_lazy_import_gepa")
    with pytest.raises(EvolveExtraNotInstalled, match="subprocess optimizer adapter"):
        pipeline.build_pipeline(
            skill_name="demo-skill",
            judge_pool=None,
            baseline=None,
            eval_records=[],
        )
    assert "dspy" not in sys.modules
    assert "gepa" not in sys.modules


def test_pipeline_all_three_gates_pass_with_aligned_candidate(
    tmp_path: Path, clean_lazy_module_state: None
) -> None:
    harness = OfflineHarness(workspace=tmp_path)  # uses real GATES registry
    baseline = _baseline()
    candidate = _candidate()

    trace = harness._run_gates(candidate, baseline)

    assert len(trace) == 3, f"expected 3 gate results, got {len(trace)}: {trace}"
    assert [r.verdict for r in trace] == ["pass", "pass", "pass"]
    # Order MUST match the module-level GATES registry (§6.4.1).
    assert [r.gate_name for r in trace] == ["1-test-pass", "2-size-cap", "3-cache-compat"]


def test_pipeline_cache_mismatch_last_gate_fails(
    tmp_path: Path, clean_lazy_module_state: None
) -> None:
    # Diverge only on cache_key_hash. Gate-1 and gate-2 should still pass
    # (size_metrics are aligned), so the fail manifests at gate-3.
    harness = OfflineHarness(workspace=tmp_path)
    baseline = _baseline()
    candidate = _candidate(cache_key_hash="key-DIFFERENT", content_hash="cand-mut")

    trace = harness._run_gates(candidate, baseline)

    # With these inputs gates 1 + 2 pass deterministically (tier counters meet
    # floors, line counts within caps), so the only reachable outcome is
    # `len(trace) == 3` with `trace[-1]` = the 3-cache-compat fail.
    # If `_run_gates` ever changes to short-circuit on PASS too, this test
    # would catch the regression via the strict len/order/verdict asserts below.
    assert trace, "trace must not be empty"
    assert trace[-1].verdict == "fail"
    # With aligned size_metrics, gate-3 is the one that catches this.
    assert len(trace) == 3
    assert trace[-1].gate_name == "3-cache-compat"
    assert trace[-1].failure_reason is not None
    assert "cache-key-mismatch" in trace[-1].failure_reason


def test_pipeline_does_not_import_dspy_or_gepa(
    tmp_path: Path, clean_lazy_module_state: None
) -> None:
    """The gate-evaluation path MUST stay free of dspy/gepa imports.

    Those are reserved for the GEPA-driven ``run`` orchestrator (t-14/t-15)
    behind the ``EvolveExtraNotInstalled`` lazy guard. A regression that
    eagerly imports either at gate time would silently break the
    ``nanobot[evolve]`` extras-not-installed UX.
    """
    harness = OfflineHarness(workspace=tmp_path)
    harness._run_gates(_candidate(), _baseline())

    assert "dspy" not in sys.modules, (
        "lazy-import contract violated: dspy ended up in sys.modules "
        "after _run_gates — the gate pipeline must not import dspy"
    )
    assert "gepa" not in sys.modules, (
        "lazy-import contract violated: gepa ended up in sys.modules "
        "after _run_gates — the gate pipeline must not import gepa"
    )


def test_evolve_modules_stay_decoupled_from_runtime_lane() -> None:
    import ast

    forbidden_prefixes = (
        "nanobot.agent.loop",
        "nanobot.agent.runner",
        "nanobot.channels",
        "nanobot.command",
        "nanobot.api.server",
        "nanobot.agent.tools",
        "dspy",
        "gepa",
    )
    root = Path(__file__).resolve().parents[2] / "nanobot" / "evolve"
    assert root.is_dir(), f"evolve scan root must exist: {root}"
    python_files = sorted(root.rglob("*.py"))
    assert python_files, f"evolve scan must inspect at least one Python file under {root}"

    offenders: list[str] = []
    for path in python_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            module = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if any(
                        module == prefix or module.startswith(f"{prefix}.")
                        for prefix in forbidden_prefixes
                    ):
                        offenders.append(f"{path}:{module}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden_prefixes
                ):
                    offenders.append(f"{path}:{module}")
    assert offenders == []
