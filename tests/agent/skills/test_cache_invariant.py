"""M2 §10.4 — cache invariance: skill_manage mutations don't poison turn cache.

The contract under test: a turn-in-progress that has already paid for the
``build_skills_summary`` traversal must NOT have its cached prompt fragment
re-derived just because ``skill_manage create`` wrote a new SKILL.md to
disk. Re-reading the disk mid-turn would change the system prompt
underneath the LLM and invalidate the K/V prefix cache.

Equivalently:
* P1 (the summary at turn-start) MUST equal P_mid (the same summary
  recomputed mid-turn after a create), as long as we honor the
  turn-scoped cache.
* P2 (the summary built fresh on the NEXT turn) MUST include the new
  skill — otherwise we'd never observe the freshly created skill.

The production ``SkillsLoader.build_skills_summary`` is itself stateless
(no internal cache). The cache lives at the turn boundary in the caller —
in M2's design the orchestrator builds the summary once per turn and
holds onto the string until the next turn boundary clears it. This test
models that contract with an explicit ``_TurnSkillsCache`` wrapper that
memoizes the first call within a turn and re-traverses on
``invalidate()``. The load-bearing assertions are:

1. Within a turn: cache hit → no extra disk reads (mock counter unchanged).
2. Across turns: P1 != P2 and P2 includes the newly created skill.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from nanobot.agent.skills import SkillsLoader
from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.agent.tools.skill_manage import SkillManageTool


def _make_tool(workspace: Path, telemetry: SkillTelemetry | None) -> SkillManageTool:
    config = type(
        "_Cfg", (), {
            "skill_manage": type(
                "_SM", (), {
                    "max_mutations_per_turn": 1000,
                    "max_body_bytes": 65536,
                    "max_agent_skills": 200,
                    "max_description_len": 280,
                },
            )(),
        },
    )()
    return SkillManageTool(
        workspace=workspace,
        telemetry=telemetry,
        provenance_tag="agent",
        config=config,
        runtime_state=None,
    )


class _TurnSkillsCache:
    """Models the orchestrator's per-turn cache for the skills summary.

    Production-equivalent contract: build once per turn, reuse for the
    rest of the turn. ``invalidate()`` is called at the turn boundary.
    """

    def __init__(self, loader: SkillsLoader) -> None:
        self._loader = loader
        self._cached: Optional[str] = None

    def get(self) -> str:
        if self._cached is None:
            self._cached = self._loader.build_skills_summary()
        return self._cached

    def invalidate(self) -> None:
        self._cached = None


def _seed_user_skill(workspace: Path, name: str, body: str = "# seed\n") -> None:
    """Drop a workspace-tier (user) skill on disk so ``build_skills_summary``
    has at least one entry to render at turn-start.
    """
    skill_dir = workspace / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\ndescription: seed skill\n---\n{body}", encoding="utf-8"
    )


@pytest.mark.asyncio
async def test_within_turn_cache_hit_avoids_extra_disk_reads(
    tmp_path: Path,
) -> None:
    """First call populates the cache; second call within the same turn
    must NOT re-traverse the skills directory. We instrument
    ``Path.iterdir`` to count traversals and assert the count does not
    rise on the second ``cache.get()``.

    A ``skill_manage create`` happens between the two cache.get() calls
    to prove the cache is robust against on-disk mutations within a turn.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _seed_user_skill(workspace, "alpha")

    loader = SkillsLoader(workspace)
    cache = _TurnSkillsCache(loader)

    # Turn-start: build the summary; this consults the disk.
    p1 = cache.get()
    assert "alpha" in p1, f"seed skill missing from P1: {p1!r}"

    # Instrument ``Path.iterdir`` to count subsequent disk traversals.
    original_iterdir = Path.iterdir

    call_count = {"n": 0}

    def _counting_iterdir(self: Path):
        call_count["n"] += 1
        return original_iterdir(self)

    # Mid-turn create: writes ``skills/agent/beta/SKILL.md`` directly on
    # disk via the production tool. The point is to demonstrate that
    # even with a real on-disk write, the cache short-circuits the
    # second build.
    tool = _make_tool(workspace, telemetry=None)
    r = await tool.execute(verb="create", name="beta", body="# beta\n")
    assert r["ok"] is True, r

    # Capture iterdir count AFTER the create (we don't care about reads
    # the create itself performed; we only care about the cache.get path
    # below).
    with patch.object(Path, "iterdir", _counting_iterdir):
        baseline = call_count["n"]
        p_mid = cache.get()
        after = call_count["n"]

    # Cache hit: same string returned, zero new iterdir calls.
    assert p_mid == p1, "within-turn cache must return the previously built summary"
    assert after == baseline, (
        f"cache hit must not re-traverse disk; iterdir grew by "
        f"{after - baseline} (expected 0)"
    )


@pytest.mark.asyncio
async def test_across_turn_invalidation_picks_up_new_skill(
    tmp_path: Path,
) -> None:
    """Cross-turn assertion (load-bearing per spec): after the turn
    boundary invalidates the cache, the rebuilt summary reflects the
    skill that was created mid-prior-turn, and P1 != P2.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _seed_user_skill(workspace, "alpha")

    loader = SkillsLoader(workspace)
    cache = _TurnSkillsCache(loader)

    # Turn 1.
    p1 = cache.get()
    assert "alpha" in p1
    assert "new" not in p1  # the new skill doesn't exist yet

    # Mid-turn-1 create.
    tool = _make_tool(workspace, telemetry=None)
    r = await tool.execute(verb="create", name="new", body="# new\n")
    assert r["ok"] is True, r

    # Still same turn → still P1.
    assert cache.get() == p1

    # ---- Turn boundary ----
    cache.invalidate()

    # Turn 2 rebuild.
    p2 = cache.get()
    assert "new" in p2, (
        f"after turn boundary, the freshly created skill must surface; p2={p2!r}"
    )
    assert p1 != p2, (
        "cross-turn rebuild must yield a different summary string; "
        "otherwise the cache invalidation is broken"
    )
