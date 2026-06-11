"""M2 §3.7 / §8.6 — multi-process concurrency regressions (t-10 §2, §4).

We use ``multiprocessing`` with the ``spawn`` start method (NOT fork) so
the child interpreter starts fresh — fork on POSIX would inherit the
parent's open file descriptors and any module-level locks, which is
unsafe for tests that probe filelock contention. Each worker function
is a top-level module-scope ``def`` because ``spawn`` needs to be able
to import and call it by name from the child process.

Coverage:

* ``test_workspace_create_lock_caps_quota``: pre-populate 199 valid
  agent-tier skill directories, fork two child processes that race on
  ``skill_manage create("a")`` / ``create("b")``. Layer 0 (the workspace
  ``.create.lock`` filelock) plus the in-lock quota check must allow
  exactly one to succeed — the other must reject with
  ``error_code="quota_exceeded"`` (the real codename in
  ``do_create``; the plan referred to it as ``TOO_MANY_AGENT_SKILLS``,
  which is an alias for the same gate). Final agent-root listing must
  contain exactly 200 skill directories.

* ``test_concurrent_patch_non_overlapping``: two workers patch the same
  skill with non-overlapping search/replace strings. Layer-2 filelock
  serialises them so both edits land. Telemetry's ``patches`` counter
  must reach 2.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
from pathlib import Path

import pytest

# ----- top-level worker functions (multiprocessing-spawn requires this) ----


def _create_worker(workspace_path: str, skill_name: str, result_path: str) -> None:
    """Run ``skill_manage create(<skill_name>)`` and dump the result dict
    as JSON at ``result_path`` so the parent test can inspect both
    success and reject envelopes without a multiprocessing.Queue.

    Top-level so :mod:`multiprocessing` can pickle the function reference
    under start-method ``spawn``.
    """
    import asyncio
    import json as _json
    from pathlib import Path as _Path

    from nanobot.agent.tools.skill_manage import SkillManageTool

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
    tool = SkillManageTool(
        workspace=_Path(workspace_path),
        telemetry=None,
        provenance_tag="agent",
        config=config,
        runtime_state=None,
    )
    result = asyncio.run(tool.execute(verb="create", name=skill_name, body="x"))
    with open(result_path, "w", encoding="utf-8") as fp:
        _json.dump(result, fp)


def _patch_worker(
    workspace_path: str,
    skill_name: str,
    search: str,
    replace: str,
    result_path: str,
) -> None:
    """Run ``skill_manage patch(<skill_name>, search, replace)`` with a
    real ``SkillTelemetry`` so layer 3+4 are exercised, then ``flush()``
    so the on-disk ``.telemetry.json`` reflects this worker's bump.

    Top-level so :mod:`multiprocessing` can pickle the function reference.
    """
    import asyncio
    import json as _json
    from pathlib import Path as _Path

    from nanobot.agent.skills_telemetry import SkillTelemetry
    from nanobot.agent.tools.skill_manage import SkillManageTool

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
    telemetry = SkillTelemetry(_Path(workspace_path))
    tool = SkillManageTool(
        workspace=_Path(workspace_path),
        telemetry=telemetry,
        provenance_tag="agent",
        config=config,
        runtime_state=None,
    )
    result = asyncio.run(
        tool.execute(
            verb="patch", name=skill_name, search=search, replace=replace
        )
    )
    # Force layer 3+4 — bump-only leaves counters in memory.
    telemetry.flush()
    with open(result_path, "w", encoding="utf-8") as fp:
        _json.dump(result, fp)


# ----- helpers ---------------------------------------------------------------


def _seed_agent_skill(agent_root: Path, name: str, body: str = "seed\n") -> None:
    """Materialise a minimal valid agent-tier SKILL.md so SkillsLoader
    counts it toward the quota.
    """
    skill_dir = agent_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\norigin: agent\ndescription: seed\n---\n{body}",
        encoding="utf-8",
    )


def _list_agent_skills(agent_root: Path) -> list[str]:
    """Return names of subdirectories with a SKILL.md under ``agent_root``.

    Filters out lock-sentinel dirs / loose files so only real skill
    directories are counted (matches what ``SkillsLoader`` enumerates).
    """
    if not agent_root.exists():
        return []
    out = []
    for entry in os.listdir(agent_root):
        sd = agent_root / entry
        if sd.is_dir() and (sd / "SKILL.md").exists():
            out.append(entry)
    return out


# ----- §2: workspace .create.lock + quota cap under 2 racing creates -------


@pytest.mark.timeout(30)
def test_workspace_create_lock_caps_quota(tmp_workspace: Path) -> None:
    """Pre-seed 199 agent-tier skills; race two ``create`` procs.

    Exactly one must succeed (final count = 200), and the other must
    return ``error_code="quota_exceeded"``. Layer 0's ``.create.lock``
    + the in-lock ``agent_count >= max_agent_skills`` check is what
    serialises this race; without it, both could pass the quota check
    on a stale shadow snapshot and both would create, blowing past 200.
    """
    agent_root = tmp_workspace / "skills" / "agent"
    agent_root.mkdir(parents=True, exist_ok=True)
    for i in range(199):
        _seed_agent_skill(agent_root, f"seed-{i:03d}")
    assert len(_list_agent_skills(agent_root)) == 199

    ctx = mp.get_context("spawn")
    result_a = tmp_workspace / "_result_a.json"
    result_b = tmp_workspace / "_result_b.json"
    p_a = ctx.Process(
        target=_create_worker,
        args=(str(tmp_workspace), "race-a", str(result_a)),
        name="create-worker-a",
    )
    p_b = ctx.Process(
        target=_create_worker,
        args=(str(tmp_workspace), "race-b", str(result_b)),
        name="create-worker-b",
    )
    p_a.start()
    p_b.start()
    p_a.join(timeout=20)
    p_b.join(timeout=20)
    assert not p_a.is_alive(), "create worker A hung"
    assert not p_b.is_alive(), "create worker B hung"
    assert p_a.exitcode == 0, f"worker A exit={p_a.exitcode}"
    assert p_b.exitcode == 0, f"worker B exit={p_b.exitcode}"

    res_a = json.loads(result_a.read_text(encoding="utf-8"))
    res_b = json.loads(result_b.read_text(encoding="utf-8"))

    successes = [r for r in (res_a, res_b) if r.get("ok") is True]
    rejects = [r for r in (res_a, res_b) if r.get("ok") is False]
    assert len(successes) == 1, f"expected exactly one ok, got {(res_a, res_b)}"
    assert len(rejects) == 1, f"expected exactly one reject, got {(res_a, res_b)}"
    assert rejects[0]["error_code"] == "quota_exceeded", rejects[0]

    final = _list_agent_skills(agent_root)
    assert len(final) == 200, (
        f"expected exactly 200 agent skills after the race, got {len(final)}"
    )


# ----- §4: parallel non-overlapping patches both land ----------------------


@pytest.mark.timeout(30)
def test_concurrent_patch_non_overlapping(tmp_workspace: Path) -> None:
    """Two ``spawn`` workers patch the same skill with disjoint search
    strings. Layer-2 filelock serialises them so both edits land in the
    final SKILL.md and the on-disk telemetry counter reaches 2.
    """
    # Seed the skill directly on disk (bypass the tool — the tool's
    # create path is exercised elsewhere).
    agent_root = tmp_workspace / "skills" / "agent"
    skill_dir = agent_root / "shared"
    skill_dir.mkdir(parents=True, exist_ok=True)
    body = "ALPHA-token and BETA-token coexist here\n"
    (skill_dir / "SKILL.md").write_text(
        f"---\norigin: agent\ndescription: shared\n---\n{body}",
        encoding="utf-8",
    )
    # Pre-register the entry in telemetry so flush(writer="bump") will
    # accept the patch counter (per `_rmw_merge`, writer=="bump" never
    # creates new entries — only reconcile does). This pre-seed is
    # redundant after fix-bump-on-create (do_create now reconciles), but
    # this test seeds the skill DIRECTLY on disk (bypassing the tool), so
    # the reconcile-on-create path is not exercised here — the explicit
    # pre-seed is kept as belt-and-suspenders setup.
    from nanobot.agent.skills_telemetry import SkillTelemetry

    telem_seed = SkillTelemetry(tmp_workspace)
    telem_seed.reconcile([
        {
            "name": "shared",
            "effective_origin": "agent",
            "shadowed_origins": [],
            "path": str(skill_dir / "SKILL.md"),
        }
    ])
    telem_seed.flush(writer="reconcile")

    ctx = mp.get_context("spawn")
    result_a = tmp_workspace / "_patch_a.json"
    result_b = tmp_workspace / "_patch_b.json"
    p_a = ctx.Process(
        target=_patch_worker,
        args=(
            str(tmp_workspace), "shared", "ALPHA-token", "ALPHA-replaced",
            str(result_a),
        ),
        name="patch-worker-a",
    )
    p_b = ctx.Process(
        target=_patch_worker,
        args=(
            str(tmp_workspace), "shared", "BETA-token", "BETA-replaced",
            str(result_b),
        ),
        name="patch-worker-b",
    )
    p_a.start()
    p_b.start()
    p_a.join(timeout=20)
    p_b.join(timeout=20)
    assert not p_a.is_alive(), "patch worker A hung"
    assert not p_b.is_alive(), "patch worker B hung"
    assert p_a.exitcode == 0, f"worker A exit={p_a.exitcode}"
    assert p_b.exitcode == 0, f"worker B exit={p_b.exitcode}"

    res_a = json.loads(result_a.read_text(encoding="utf-8"))
    res_b = json.loads(result_b.read_text(encoding="utf-8"))
    assert res_a.get("ok") is True, res_a
    assert res_b.get("ok") is True, res_b

    # Both replacements must be present in the final SKILL.md.
    final_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "ALPHA-replaced" in final_text, final_text
    assert "BETA-replaced" in final_text, final_text
    assert "ALPHA-token" not in final_text
    assert "BETA-token" not in final_text

    # Telemetry counter for the patched skill must read >= 2 from disk.
    # Each worker drove its own SkillTelemetry instance through layer-4
    # filelock + atomic write, so the two RMW merges on
    # `.telemetry.json` should accumulate.
    telem_disk = json.loads(
        (tmp_workspace / "skills" / ".telemetry.json").read_text(
            encoding="utf-8"
        )
    )
    assert telem_disk["entries"]["shared"]["patches"] == 2, telem_disk
