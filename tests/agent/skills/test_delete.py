"""M2 t-04 — `bump(kind='delete')` tombstone + reconcile reuse-create reset.

These tests pin decision #66:

1. `bump(name, "delete")` flips an in-memory + on-disk `tombstone=True`
   flag and does NOT mutate any counter (M1 invariant 3: counters are
   monotonic on every code path except reuse-create reset).
2. `reconcile()` with the same name back in `known_skills` (i.e. the
   skill file was re-created with the same name) zeroes counters,
   refreshes `entry_created_at`, and removes the `tombstone` key —
   the only counter-reset path in the system.
3. Reconcile on an entry that has NEVER been tombstoned does not reset
   counters (preserves M1 invariant 3 monotonicity).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from nanobot.agent.skills_telemetry import SkillEntry, SkillTelemetry


def _make_entry(name: str, origin: str = "agent",
                path: str = "/x/SKILL.md") -> SkillEntry:
    return {
        "name": name,
        "effective_origin": origin,
        "shadowed_origins": [],
        "path": path,
    }


def _telemetry_path(workspace: Path) -> Path:
    return workspace / "skills" / ".telemetry.json"


def test_tombstone_reuse_zero(tmp_workspace: Path) -> None:
    """Bump-delete sets tombstone; subsequent reconcile resets on reuse."""
    telem = SkillTelemetry(tmp_workspace)
    telem.reconcile([_make_entry("myskill")])
    # Seed counters to non-zero values
    for _ in range(5):
        telem.bump("myskill", "view")
    for _ in range(3):
        telem.bump("myskill", "use")
    for _ in range(2):
        telem.bump("myskill", "patch")
    telem.flush()
    on_disk_before = json.loads(_telemetry_path(tmp_workspace).read_text())
    original_created_at = on_disk_before["entries"]["myskill"]["entry_created_at"]
    assert on_disk_before["entries"]["myskill"]["views"] == 5
    assert on_disk_before["entries"]["myskill"]["uses"] == 3
    assert on_disk_before["entries"]["myskill"]["patches"] == 2

    # Agent deletes the skill: tombstone flag set, counters unchanged.
    telem.bump("myskill", "delete")
    telem.flush()
    on_disk_after_delete = json.loads(_telemetry_path(tmp_workspace).read_text())
    entry_after_delete = on_disk_after_delete["entries"]["myskill"]
    assert entry_after_delete["tombstone"] is True
    assert entry_after_delete["views"] == 5
    assert entry_after_delete["uses"] == 3
    assert entry_after_delete["patches"] == 2

    # Sleep to ensure the new ISO-second timestamp differs from the original.
    time.sleep(1.1)

    # Agent re-creates the skill file with the same name → reconcile sees
    # it again. The reconcile MUST zero counters, refresh entry_created_at,
    # and remove the tombstone key.
    telem.reconcile([_make_entry("myskill")])
    telem.flush()
    on_disk_after_reuse = json.loads(_telemetry_path(tmp_workspace).read_text())
    entry_after_reuse = on_disk_after_reuse["entries"]["myskill"]
    assert entry_after_reuse["views"] == 0
    assert entry_after_reuse["uses"] == 0
    assert entry_after_reuse["patches"] == 0
    assert "tombstone" not in entry_after_reuse
    assert entry_after_reuse["entry_created_at"] > original_created_at


def test_bump_delete_no_counter_mutation(tmp_workspace: Path) -> None:
    """`bump(kind='delete')` flips tombstone only — no counter change."""
    telem = SkillTelemetry(tmp_workspace)
    telem.reconcile([_make_entry("foo")])
    for _ in range(5):
        telem.bump("foo", "view")
    for _ in range(3):
        telem.bump("foo", "use")
    for _ in range(2):
        telem.bump("foo", "patch")

    snap_before = telem.snapshot()
    e_before = snap_before["entries"]["foo"]
    assert e_before["views"] == 5
    assert e_before["uses"] == 3
    assert e_before["patches"] == 2
    assert "tombstone" not in e_before

    telem.bump("foo", "delete")
    snap_after = telem.snapshot()
    e_after = snap_after["entries"]["foo"]
    assert e_after["views"] == 5
    assert e_after["uses"] == 3
    assert e_after["patches"] == 2
    assert e_after["tombstone"] is True

    telem.flush()
    on_disk = json.loads(_telemetry_path(tmp_workspace).read_text())
    entry = on_disk["entries"]["foo"]
    assert entry["views"] == 5
    assert entry["uses"] == 3
    assert entry["patches"] == 2
    assert entry["tombstone"] is True


def test_reconcile_no_tombstone_no_reset(tmp_workspace: Path) -> None:
    """Reconcile on a never-tombstoned entry MUST keep counters monotonic."""
    telem = SkillTelemetry(tmp_workspace)
    telem.reconcile([_make_entry("bar")])
    for _ in range(4):
        telem.bump("bar", "view")
    for _ in range(2):
        telem.bump("bar", "use")
    telem.flush()
    on_disk_first = json.loads(_telemetry_path(tmp_workspace).read_text())
    original_created_at = on_disk_first["entries"]["bar"]["entry_created_at"]
    assert on_disk_first["entries"]["bar"]["views"] == 4
    assert on_disk_first["entries"]["bar"]["uses"] == 2
    assert "tombstone" not in on_disk_first["entries"]["bar"]

    # Sleep so any (forbidden) refresh of entry_created_at would be visible.
    time.sleep(1.1)

    # A second reconcile with the same skill — origin can change, but
    # counters and entry_created_at MUST be untouched.
    telem.reconcile([_make_entry("bar", origin="user")])
    telem.flush()
    on_disk_after = json.loads(_telemetry_path(tmp_workspace).read_text())
    entry_after = on_disk_after["entries"]["bar"]
    assert entry_after["views"] == 4
    assert entry_after["uses"] == 2
    assert entry_after["patches"] == 0
    assert entry_after["entry_created_at"] == original_created_at
    assert "tombstone" not in entry_after
    assert entry_after["origin"] == "user"


# --- t-08 additions: full delete-verb pipeline coverage --------------------


import pytest  # noqa: E402  (module-level test below tolerates late import)

from nanobot.agent.tools.skill_manage import SkillManageTool  # noqa: E402


def _make_tool(tmp_workspace: Path, telemetry=None) -> SkillManageTool:
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
        workspace=tmp_workspace,
        telemetry=telemetry,
        provenance_tag="agent",
        config=config,
        runtime_state=None,
    )


@pytest.mark.asyncio
async def test_delete_removes_skill_md_and_dir(tmp_workspace: Path) -> None:
    tool = _make_tool(tmp_workspace)
    await tool.execute(verb="create", name="zap", body="x")
    skill_md = tmp_workspace / "skills" / "agent" / "zap" / "SKILL.md"
    skill_dir = skill_md.parent
    assert skill_md.exists()
    r = await tool.execute(verb="delete", name="zap")
    assert r["ok"] is True
    assert not skill_md.exists()
    # Best-effort dir cleanup — empty dir + lock should be gone.
    assert not skill_dir.exists()


@pytest.mark.asyncio
async def test_delete_idempotent_or_not_found(tmp_workspace: Path) -> None:
    """Per t-08 chosen semantics: missing skill → `not_found` reject
    (no telemetry mutation, no lock errors). Documented choice."""
    tool = _make_tool(tmp_workspace)
    r = await tool.execute(verb="delete", name="ghost")
    assert r["ok"] is False
    assert r["error_code"] == "not_found"


@pytest.mark.asyncio
async def test_delete_tier_locked_for_non_agent_tier(
    tmp_workspace: Path,
) -> None:
    user_dir = tmp_workspace / "skills" / "ours"
    user_dir.mkdir(parents=True)
    (user_dir / "SKILL.md").write_text(
        "---\norigin: user\n---\nbody\n", encoding="utf-8"
    )
    tool = _make_tool(tmp_workspace)
    r = await tool.execute(verb="delete", name="ours")
    assert r["ok"] is False
    assert r["error_code"] == "tier_locked"


@pytest.mark.asyncio
async def test_delete_bumps_tombstone_then_reuse_zeroes(
    tmp_workspace: Path,
) -> None:
    """Close-loop with t-04: delete → tombstone, reconcile-on-recreate → zero."""
    telem = SkillTelemetry(tmp_workspace)
    tool = _make_tool(tmp_workspace, telemetry=telem)
    await tool.execute(verb="create", name="loopy", body="orig")
    telem.reconcile([_make_entry("loopy", "agent",
                                 path=str(tmp_workspace / "skills/agent/loopy/SKILL.md"))])
    for _ in range(3):
        telem.bump("loopy", "view")
    telem.flush()
    snap_before = telem.snapshot()
    assert snap_before["entries"]["loopy"]["views"] == 3

    # Delete via tool — should bump kind=delete (tombstone).
    r = await tool.execute(verb="delete", name="loopy")
    assert r["ok"], r
    telem.flush()
    snap_after = telem.snapshot()
    assert snap_after["entries"]["loopy"]["tombstone"] is True
    # Counters are still monotonic at this point.
    assert snap_after["entries"]["loopy"]["views"] == 3

    # Recreate — reconcile clears the tombstone & zeroes counters.
    await tool.execute(verb="create", name="loopy", body="reborn")
    telem.reconcile([_make_entry(
        "loopy", "agent",
        path=str(tmp_workspace / "skills/agent/loopy/SKILL.md"),
    )])
    snap_reused = telem.snapshot()
    assert snap_reused["entries"]["loopy"]["views"] == 0
    assert "tombstone" not in snap_reused["entries"]["loopy"]
