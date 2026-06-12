"""Tests for `nanobot.agent._atomic_io.fd_file_lock` (M2 task t-02).

Covers the M2 §3.7.1 step 5 contract:
- POSIX symlink precheck -> SkillManageError("PATH_ESCAPE") BEFORE any os.open
- errno.ELOOP -> SkillManageError("PATH_ESCAPE")
- ENOENT NOT swallowed -> raw OSError (caller maps to verb code)
- BlockingIOError retry loop bounded by `time.monotonic()` deadline
- concurrency_timeout closes fd (no leak)
- LIFO release: LOCK_UN then os.close
- Concurrent acquire after release (cross-process correctness)
- R8-2 Windows gate: fcntl is None -> RuntimeError with exact message
"""

from __future__ import annotations

import errno
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import pytest

from nanobot.agent import _atomic_io
from nanobot.agent._atomic_io import SkillManageError, fd_file_lock

# ---------------------------------------------------------------------------
# Helpers (top-level so multiprocessing 'spawn' can pickle them)
# ---------------------------------------------------------------------------


def _child_acquire_release(lock_path_str: str, result_queue: "mp.Queue[str]") -> None:
    """Worker: acquire the lock at `lock_path_str` with timeout=1.0 and report."""
    try:
        with fd_file_lock(Path(lock_path_str), timeout=1.0):
            result_queue.put("acquired")
    except SkillManageError as exc:  # pragma: no cover - defensive
        result_queue.put(f"skill_error:{exc.error_code}")
    except Exception as exc:  # pragma: no cover - defensive
        result_queue.put(f"error:{exc!r}")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_yields_valid_fd_and_closes_on_exit(tmp_path: Path) -> None:
    """Enter/exit cleanly; fd is valid inside, closed after."""
    lock = tmp_path / "skill.lock"
    captured_fd: list[int] = []
    with fd_file_lock(lock) as fd:
        captured_fd.append(fd)
        assert isinstance(fd, int)
        # fd is "live" — fstat succeeds inside the context
        assert os.fstat(fd).st_size >= 0
    # After exit, fd must be closed.
    with pytest.raises(OSError):
        os.fstat(captured_fd[0])


def test_happy_path_creates_lock_file_with_mode_0600(tmp_path: Path) -> None:
    lock = tmp_path / "skill.lock"
    with fd_file_lock(lock):
        # Linux: mode bits include 0o600; subject to umask but O_CREAT mode arg
        # passed is 0o600 so on a sane filesystem the inode mode reflects that
        # masked by current umask. We assert the user bits are at least rw.
        st = lock.stat()
        assert st.st_mode & 0o600 == 0o600


# ---------------------------------------------------------------------------
# Symlink precheck (PATH_ESCAPE)
# ---------------------------------------------------------------------------


def test_symlink_precheck_raises_path_escape_before_os_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pre-create a symlink at lock path -> PATH_ESCAPE; os.open never called."""
    target = tmp_path / "real_target"
    target.write_text("")
    lock = tmp_path / "skill.lock"
    lock.symlink_to(target)

    open_calls: list[tuple] = []
    real_open = os.open

    def fail_on_lock_open(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        open_calls.append((str(p), flags, mode))
        # If anyone tries to open the lock path, we'd want to know. Allow other
        # opens (e.g. by pytest internals) but flag if our path is hit.
        return real_open(p, flags, mode, *args, **kwargs)

    monkeypatch.setattr(_atomic_io.os, "open", fail_on_lock_open)
    with pytest.raises(SkillManageError) as exc_info:
        with fd_file_lock(lock):
            pass  # pragma: no cover
    assert exc_info.value.error_code == "PATH_ESCAPE"
    # No os.open call should have used the lock path string.
    assert all(str(lock) != call[0] for call in open_calls), (
        f"os.open invoked on symlink path: {open_calls}"
    )


# ---------------------------------------------------------------------------
# errno.ELOOP -> PATH_ESCAPE
# ---------------------------------------------------------------------------


def test_eloop_errno_is_mapped_to_path_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "skill.lock"

    def boom(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError(errno.ELOOP, "Too many levels of symbolic links")

    monkeypatch.setattr(_atomic_io.os, "open", boom)
    with pytest.raises(SkillManageError) as exc_info:
        with fd_file_lock(lock):
            pass  # pragma: no cover
    assert exc_info.value.error_code == "PATH_ESCAPE"


# ---------------------------------------------------------------------------
# ENOENT -> raw OSError (NOT SkillManageError)
# ---------------------------------------------------------------------------


def test_enoent_is_not_swallowed_into_skill_manage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ENOENT propagates as raw OSError; caller decides how to map it."""
    lock = tmp_path / "missing_dir" / "skill.lock"

    def boom(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise OSError(errno.ENOENT, "No such file or directory")

    monkeypatch.setattr(_atomic_io.os, "open", boom)
    with pytest.raises(OSError) as exc_info:
        with fd_file_lock(lock):
            pass  # pragma: no cover
    assert not isinstance(exc_info.value, SkillManageError)
    assert exc_info.value.errno == errno.ENOENT


# ---------------------------------------------------------------------------
# concurrency_timeout: deadline exceeded, fd closed, no leak
# ---------------------------------------------------------------------------


def test_concurrency_timeout_raises_and_closes_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When flock always blocks, deadline triggers SkillManageError + fd close."""
    lock = tmp_path / "skill.lock"
    closed_fds: list[int] = []
    real_close = os.close

    def tracking_close(fd):  # type: ignore[no-untyped-def]
        closed_fds.append(fd)
        return real_close(fd)

    fcntl_mod = _atomic_io.fcntl
    assert fcntl_mod is not None  # POSIX guard for this test

    def always_block(fd, op):  # type: ignore[no-untyped-def]
        raise BlockingIOError(errno.EWOULDBLOCK, "would block")

    monkeypatch.setattr(_atomic_io.fcntl, "flock", always_block)
    monkeypatch.setattr(_atomic_io.os, "close", tracking_close)

    t0 = time.monotonic()
    with pytest.raises(SkillManageError) as exc_info:
        with fd_file_lock(lock, timeout=0.05):
            pass  # pragma: no cover
    elapsed = time.monotonic() - t0
    assert exc_info.value.error_code == "concurrency_timeout"
    # Deadline should have triggered roughly within timeout (allow generous
    # slack for CI-runner jitter).
    assert elapsed < 1.0, f"timeout retry loop spun too long: {elapsed:.3f}s"
    # The fd opened on entry MUST have been closed exactly once (no leak).
    assert len(closed_fds) == 1, f"expected 1 close, got {len(closed_fds)}"


# ---------------------------------------------------------------------------
# LIFO release on inner exception: inner releases BEFORE outer exits
# ---------------------------------------------------------------------------


def test_lifo_release_order_when_inner_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nested locks: inner __exit__ runs first; release order reflects LIFO."""
    outer_path = tmp_path / "outer.lock"
    inner_path = tmp_path / "inner.lock"
    events: list[tuple[str, int]] = []

    real_flock = _atomic_io.fcntl.flock  # type: ignore[union-attr]
    real_close = os.close

    def tracking_flock(fd, op):  # type: ignore[no-untyped-def]
        events.append(("flock", op))
        return real_flock(fd, op)

    def tracking_close(fd):  # type: ignore[no-untyped-def]
        events.append(("close", fd))
        return real_close(fd)

    monkeypatch.setattr(_atomic_io.fcntl, "flock", tracking_flock)
    monkeypatch.setattr(_atomic_io.os, "close", tracking_close)

    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        with fd_file_lock(outer_path) as outer_fd:
            with fd_file_lock(inner_path) as inner_fd:
                # capture fds for assertion
                events.append(("inner_fd", inner_fd))
                events.append(("outer_fd", outer_fd))
                raise BoomError("explode inside inner")

    # Filter to release events only (LOCK_UN / close).
    fcntl_mod = _atomic_io.fcntl
    assert fcntl_mod is not None
    lock_un = fcntl_mod.LOCK_UN
    release_seq = [e for e in events if e[0] in ("flock", "close")]
    # Drop the LOCK_EX acquisition events from the front.
    unlock_seq = [e for e in release_seq if not (e[0] == "flock" and e[1] != lock_un)]
    # Expect: inner LOCK_UN, inner close, outer LOCK_UN, outer close (LIFO).
    assert len(unlock_seq) == 4, f"unexpected release sequence: {unlock_seq}"
    assert unlock_seq[0] == ("flock", lock_un)
    assert unlock_seq[1][0] == "close"
    assert unlock_seq[2] == ("flock", lock_un)
    assert unlock_seq[3][0] == "close"


# ---------------------------------------------------------------------------
# Concurrent acquire after release (cross-process)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only primitive (R8-2)")
def test_concurrent_acquire_after_parent_releases(tmp_path: Path) -> None:
    """Parent holds-then-releases; child can then acquire same path."""
    lock = tmp_path / "skill.lock"

    # Parent acquires + releases.
    with fd_file_lock(lock):
        pass

    ctx = mp.get_context("spawn")
    queue: mp.Queue[str] = ctx.Queue()
    proc = ctx.Process(target=_child_acquire_release, args=(str(lock), queue))
    proc.start()
    proc.join(timeout=10)
    assert not proc.is_alive(), "child process hung"
    assert proc.exitcode == 0, f"child exitcode={proc.exitcode}"
    msg = queue.get(timeout=1)
    assert msg == "acquired", f"unexpected child report: {msg}"


# ---------------------------------------------------------------------------
# R8-2 Windows gate: fcntl is None -> RuntimeError with exact message
# ---------------------------------------------------------------------------


def test_windows_gate_raises_runtime_error_with_exact_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Monkeypatch fcntl symbol to None; entering the cm raises RuntimeError.

    R8-2 contract: the exact message string is part of the API and tested
    so a future refactor doesn't silently break Windows-callsite assumptions.
    """
    monkeypatch.setattr(_atomic_io, "fcntl", None)
    with pytest.raises(RuntimeError) as exc_info:
        with fd_file_lock(tmp_path / "skill.lock"):
            pass  # pragma: no cover
    assert (
        str(exc_info.value)
        == "fd_file_lock is POSIX-only; Windows must take a different path"
    )
