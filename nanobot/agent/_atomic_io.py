"""Shared atomic-write utility for telemetry and skill manage (M2 §8.5).

Lifted from `nanobot/agent/skills_telemetry.py` per M2 plan task t-01:
- Flag set upgraded to `O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC`
  (with `getattr(os, "...", 0)` fallback on platforms that lack the flag).
- Mode locked to `0o600` (was `0o644`) per decision #71 (R7 fix YEL-SEC-1).
- Mandatory `os.unlink(tmp)` on any failure path so the atomic-write contract
  never leaves `*.tmp.*` orphans even when `os.write` / `os.fsync(fd)` /
  `os.replace` raises (R9-1 telemetry tmp cleanup gate).
- Windows import guard: `import fcntl` is wrapped in `try/except ImportError`
  so this module imports cleanly on Windows where `fcntl` is unavailable
  (R8-1 gate). `atomic_write` itself does not depend on `fcntl`; the import
  is reserved for `fd_file_lock` (M2 task t-02).
"""

from __future__ import annotations

import errno
import json
import os
import secrets
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:  # pragma: no cover - Windows fallback (no fcntl module on win32)
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


class SkillManageError(Exception):
    """Verb-level error carrying a stable `error_code` string (M2 §3.7).

    Co-located with `fd_file_lock` per plan task t-02; may be relocated
    to a dedicated errors module by t-07/t-08 if the surface grows.
    """

    def __init__(self, error_code: str, message: str = "") -> None:
        super().__init__(message or error_code)
        self.error_code = error_code


def atomic_write(path: Path, payload: bytes | bytearray | dict) -> None:
    """fsync(fd) -> os.replace -> fsync(parent_dir) on POSIX.

    Mode 0o600; mandatory unlink(tmp) on any failure (decision #71).

    `payload` may be raw bytes (written verbatim) or a dict (serialized as
    sorted-key indented JSON). The tmp filename embeds pid + 8 bytes of
    `secrets.token_hex` to avoid collisions across concurrent writers in
    the same directory.
    """
    if isinstance(payload, (bytes, bytearray)):
        data = bytes(payload)
    else:
        data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(8)}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW | _CLOEXEC
    replaced = False
    try:
        fd = os.open(tmp, flags, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)
        replaced = True
        if sys.platform != "win32":
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    finally:
        if not replaced:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


@contextmanager
def fd_file_lock(path: Path, *, timeout: float = 1.0) -> Iterator[int]:
    """POSIX advisory exclusive lock on a path-bound fd (M2 §3.7.1 step 5).

    Symlink at `path` -> SkillManageError("PATH_ESCAPE") (defends against
    the `<name>/.lock` symlink-target attack). Detected via a
    `Path.is_symlink()` precheck before any `os.open`.

    Windows (`fcntl is None`) -> RuntimeError. The exact message string is
    contractual (R8-2 gate): callers on Windows must take a different path
    rather than silently degrading.

    Open flags: `O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC`, mode 0o600.
    `errno.ELOOP` from O_NOFOLLOW is mapped to PATH_ESCAPE; ENOENT and
    other OSErrors propagate raw so the caller can map to verb-specific
    codes (e.g. ATOMIC_WRITE_FAILED, not_found).

    Lock acquisition uses `fcntl.flock(LOCK_EX | LOCK_NB)` in a retry
    loop bounded by `time.monotonic() + timeout`. Each backoff is
    `time.sleep(0.01)`. On deadline exceeded the fd is closed and
    `SkillManageError("concurrency_timeout")` is raised.

    Release order on exit (LIFO): `fcntl.flock(LOCK_UN)` then `os.close(fd)`.
    """
    if fcntl is None:
        raise RuntimeError(
            "fd_file_lock is POSIX-only; Windows must take a different path"
        )

    p = Path(path)
    if p.is_symlink():
        raise SkillManageError("PATH_ESCAPE", f"lock path is a symlink: {p}")

    flags = os.O_RDWR | os.O_CREAT | _NOFOLLOW | _CLOEXEC
    try:
        fd = os.open(str(p), flags, 0o600)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise SkillManageError(
                "PATH_ESCAPE", f"O_NOFOLLOW tripped on lock path: {p}"
            ) from e
        raise  # caller maps ENOENT / EACCES / EIO / ENOSPC to verb codes

    deadline = time.monotonic() + max(0.0, timeout)
    locked = False
    try:
        while not locked:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise SkillManageError(
                        "concurrency_timeout",
                        f"could not acquire lock on {p} within {timeout}s",
                    )
                time.sleep(0.01)
        yield fd
    finally:
        if locked:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
