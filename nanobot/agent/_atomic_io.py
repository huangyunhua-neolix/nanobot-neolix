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

import json
import os
import secrets
import sys
from pathlib import Path

try:  # pragma: no cover - Windows fallback (no fcntl module on win32)
    import fcntl  # noqa: F401  # reserved for fd_file_lock (t-02)
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


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
