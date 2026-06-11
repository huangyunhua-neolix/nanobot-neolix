"""M2 §3.7 / §8.6 — lock-layer acquisition order regression tests (t-10 §1, §3, §5).

These tests pin behaviours of the layer 0..4 cooperative-locking pipeline
that no other test in the suite covers in combination:

1. ``test_edit_and_telemetry_no_deadlock`` — two threads each holding a
   different *subset* of the lock stack must not deadlock. Thread A runs
   ``skill_manage edit("foo")`` (acquires layer 1 = in-process per-name
   ``threading.Lock``, then layer 2 = ``<skill>/.lock`` filelock, then
   inside that bumps telemetry → layer 3 ``_flush_lock`` + layer 4
   ``.telemetry.json.lock`` filelock on the subsequent flush). Thread B
   concurrently does a *telemetry-only* ``bump`` + ``flush`` against the
   same name (so it walks layers 3+4 only). LIFO-release discipline +
   strict ascending acquisition order means the two paths never grab
   the same lock in opposite order, so no deadlock is possible.

2. ``test_delete_edit_patch_skip_layer_0`` — only ``create`` may take
   layer 0 (``<agent_root>/.create.lock``). The other three verbs must
   skip layer 0 entirely; ``edit`` / ``patch`` / ``delete`` already hold
   the per-name layer 1+2 locks and must not contend on the workspace-
   wide create gate.

3. ``test_filelock_timeout_maps_to_lock_busy`` — a layer-2 filelock that
   raises :class:`SkillManageError` ``concurrency_timeout`` (e.g. because
   another writer is still inside its critical section) must surface to
   the caller as the verb-shape ``error_code="lock_busy"`` reject. This
   pins the mapping in ``skill_manage_ops._edit_or_patch`` /
   ``do_create`` / ``do_delete``.

The companion file ``test_concurrency.py`` covers the multi-process
quota-cap and parallel-patch races (t-10 §2 and §4).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nanobot.agent._atomic_io import SkillManageError
from nanobot.agent.skills_telemetry import SkillTelemetry
from nanobot.agent.tools.skill_manage import SkillManageTool

# ----- shared fixture ---------------------------------------------------------


def _build_tool(workspace: Path, telemetry=None):
    """Construct a SkillManageTool wired to a generous-limit config.

    Mirrors the local ``tool_factory`` in ``test_create.py`` /
    ``test_edit_patch.py`` so we exercise the same dispatcher path. We
    inline the helper rather than importing it because conftest.py only
    ships ``tmp_workspace``; the per-test ``tool_factory`` lives inside
    each sibling test module's local fixture.
    """

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


async def _seed(tool, name: str, body: str = "seed body\n") -> None:
    r = await tool.execute(verb="create", name=name, body=body)
    assert r["ok"], r


# ----- §1: lock-order — concurrent edit + telemetry-only bump ----------------


@pytest.mark.timeout(10)
@pytest.mark.asyncio
async def test_edit_and_telemetry_no_deadlock(tmp_workspace: Path) -> None:
    """Thread A: full edit pipeline (layers 1+2 → bump → 3+4 on flush).
    Thread B: telemetry-only bump+flush (layers 3+4 only).

    Both threads must finish, telemetry must reflect both bumps, and the
    SKILL.md body must show thread A's new content. The 10s pytest-timeout
    converts a deadlock into a test failure rather than a CI hang.
    """
    telem = SkillTelemetry(tmp_workspace)
    tool = _build_tool(tmp_workspace, telemetry=telem)
    await _seed(tool, "foo", body="original body\n")

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    new_body = "edited body via thread A\n"

    def _thread_a() -> None:
        try:
            barrier.wait(timeout=5)
            # Run the dispatcher synchronously: SkillManageTool.execute is
            # async but the verb pipeline is fully synchronous below the
            # `async def`. We call it via asyncio.run on a private event
            # loop in this thread.
            import asyncio
            result = asyncio.run(
                tool.execute(verb="edit", name="foo", body=new_body)
            )
            assert result["ok"], result
            # Force layer 3+4 here so disk reflects thread A's bump too.
            telem.flush()
        except BaseException as exc:  # pragma: no cover - propagate
            errors.append(exc)

    def _thread_b() -> None:
        try:
            barrier.wait(timeout=5)
            # Telemetry-only path: layers 3+4 only.
            telem.bump("foo", "view")
            telem.flush()
        except BaseException as exc:  # pragma: no cover - propagate
            errors.append(exc)

    t_a = threading.Thread(target=_thread_a, name="edit-worker")
    t_b = threading.Thread(target=_thread_b, name="bump-worker")
    t_a.start()
    t_b.start()
    t_a.join(timeout=8)
    t_b.join(timeout=8)
    assert not t_a.is_alive(), "edit thread deadlocked"
    assert not t_b.is_alive(), "bump thread deadlocked"
    assert not errors, f"worker raised: {errors!r}"

    # Final SKILL.md content must match the edit (thread A wins on body
    # because thread B never touched the file).
    skill_md = tmp_workspace / "skills" / "agent" / "foo" / "SKILL.md"
    text = skill_md.read_text(encoding="utf-8")
    assert new_body.strip() in text

    # Telemetry counters: both bumps must have landed (1 patch from edit,
    # 1 view from thread B). We use the persisted snapshot — `flush()`
    # already drove it through layers 3+4.
    snap = telem.snapshot()["entries"]
    assert snap["foo"]["patches"] == 1
    assert snap["foo"]["views"] == 1


# ----- §3: delete / edit / patch must NOT take layer 0 -----------------------


@pytest.mark.asyncio
async def test_delete_edit_patch_skip_layer_0(
    tmp_workspace: Path, monkeypatch
) -> None:
    """Wrap ``fd_file_lock`` to record every path it is asked to lock.

    Only ``create`` should hit ``<agent_root>/.create.lock`` (layer 0);
    the other three verbs must lock only their per-skill ``<name>/.lock``
    (layer 2).
    """
    telem = SkillTelemetry(tmp_workspace)
    tool = _build_tool(tmp_workspace, telemetry=telem)
    # Seed BEFORE we install the recorder so the create-time layer-0 acquire
    # doesn't pollute the recording.
    await _seed(tool, "foo", body="some body with sentinel-here token\n")

    from nanobot.agent.tools import skill_manage_ops as _ops

    locked_paths: list[str] = []
    real_fd_file_lock = _ops.fd_file_lock

    def _recording_lock(path, *args, **kwargs):
        locked_paths.append(str(path))
        return real_fd_file_lock(path, *args, **kwargs)

    monkeypatch.setattr(_ops, "fd_file_lock", _recording_lock)

    # ----- edit -----
    locked_paths.clear()
    r = await tool.execute(verb="edit", name="foo", body="brand new\n")
    assert r["ok"], r
    assert not any(p.endswith("/.create.lock") for p in locked_paths), (
        f"edit acquired layer-0 .create.lock: {locked_paths!r}"
    )
    assert any(p.endswith("/foo/.lock") for p in locked_paths), (
        f"edit did not acquire layer-2 <foo>/.lock: {locked_paths!r}"
    )

    # ----- patch -----
    # Re-seed a known sentinel so patch's search is deterministic.
    await tool.execute(
        verb="edit", name="foo", body="hello sentinel world\n"
    )
    locked_paths.clear()
    r = await tool.execute(
        verb="patch", name="foo", search="sentinel", replace="moon"
    )
    assert r["ok"], r
    assert not any(p.endswith("/.create.lock") for p in locked_paths), (
        f"patch acquired layer-0 .create.lock: {locked_paths!r}"
    )
    assert any(p.endswith("/foo/.lock") for p in locked_paths), (
        f"patch did not acquire layer-2 <foo>/.lock: {locked_paths!r}"
    )

    # ----- delete -----
    locked_paths.clear()
    r = await tool.execute(verb="delete", name="foo")
    assert r["ok"], r
    assert not any(p.endswith("/.create.lock") for p in locked_paths), (
        f"delete acquired layer-0 .create.lock: {locked_paths!r}"
    )
    assert any(p.endswith("/foo/.lock") for p in locked_paths), (
        f"delete did not acquire layer-2 <foo>/.lock: {locked_paths!r}"
    )


# ----- §5: filelock timeout → lock_busy reject -------------------------------


@pytest.mark.asyncio
async def test_filelock_timeout_maps_to_lock_busy(
    tmp_workspace: Path, monkeypatch
) -> None:
    """Patch ``fd_file_lock`` to ALWAYS raise ``concurrency_timeout``;
    the verb wrapper must convert that into ``error_code='lock_busy'``
    rather than letting the exception bubble out of ``execute()``.
    """
    tool = _build_tool(tmp_workspace, telemetry=None)
    await _seed(tool, "foo", body="seed\n")

    from nanobot.agent.tools import skill_manage_ops as _ops

    def _always_timeout(*_args, **_kwargs):
        raise SkillManageError(
            "concurrency_timeout",
            "simulated layer-2 timeout",
        )

    monkeypatch.setattr(_ops, "fd_file_lock", _always_timeout)

    r_edit = await tool.execute(verb="edit", name="foo", body="x\n")
    assert r_edit["ok"] is False
    assert r_edit["error_code"] == "lock_busy", r_edit

    r_patch = await tool.execute(
        verb="patch", name="foo", search="seed", replace="x"
    )
    assert r_patch["ok"] is False
    assert r_patch["error_code"] == "lock_busy", r_patch

    r_delete = await tool.execute(verb="delete", name="foo")
    assert r_delete["ok"] is False
    assert r_delete["error_code"] == "lock_busy", r_delete

    # Create also must surface `lock_busy` if its layer-0 OR layer-2 lock
    # times out — same mapping branch in `do_create`.
    r_create = await tool.execute(verb="create", name="newone", body="y")
    assert r_create["ok"] is False
    assert r_create["error_code"] == "lock_busy", r_create
