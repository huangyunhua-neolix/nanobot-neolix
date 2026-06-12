"""Tests for `nanobot.agent._atomic_io.atomic_write` (M2 task t-01).

Covers the M2 §8.5 lifted contract:
- O_NOFOLLOW / O_CLOEXEC flag set with platform fallback
- mode 0o600 on tmp file
- exactly one `os.replace` call
- parent-dir fsync on POSIX, skipped on Windows
- mandatory `os.unlink(tmp)` on every failure path (R9-1 telemetry tmp
  cleanup gate)
- CSPRNG smoke: 100 distinct nonces from `secrets.token_hex(8)`
- R8-1 import-on-Windows gate (pure import test, runs everywhere)
- R8-1b end-to-end Windows write smoke (Windows runner only)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from nanobot.agent import _atomic_io
from nanobot.agent._atomic_io import atomic_write


def test_module_imports_on_any_platform() -> None:
    """R8-1: module must import even on Windows where `fcntl` is absent."""
    import importlib

    mod = importlib.import_module("nanobot.agent._atomic_io")
    assert hasattr(mod, "atomic_write")


def test_writes_dict_as_sorted_json(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    atomic_write(target, {"b": 2, "a": 1})
    text = target.read_text(encoding="utf-8")
    assert json.loads(text) == {"a": 1, "b": 2}
    # sort_keys=True → "a" key appears before "b"
    assert text.index('"a"') < text.index('"b"')


def test_writes_bytes_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    payload = b"\x00\x01raw bytes\xff"
    atomic_write(target, payload)
    assert target.read_bytes() == payload


def test_writes_bytearray_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "blob.bin"
    payload = bytearray(b"hello")
    atomic_write(target, payload)
    assert target.read_bytes() == b"hello"


def test_no_tmp_residue_on_success(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    atomic_write(target, {"foo": 1})
    assert list(tmp_path.glob("data.json.tmp*")) == []


def test_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    target.write_text('{"old": true}')
    atomic_write(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_open_flags_include_nofollow_and_cloexec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """flag set must be O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC."""
    captured: dict[str, int] = {}
    real_open = os.open

    def tracking_open(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        # Capture the first os.open call (the tmp-file create); subsequent
        # calls are for the parent-dir fsync (O_RDONLY).
        if "flags" not in captured:
            captured["flags"] = flags
            captured["mode"] = mode
        return real_open(p, flags, mode, *args, **kwargs)

    monkeypatch.setattr(_atomic_io.os, "open", tracking_open)
    atomic_write(tmp_path / "data.json", {"k": 1})
    expected = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_TRUNC
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    assert captured["flags"] == expected
    # Even on platforms missing one of the constants, the actually-set bits
    # must still include all available ones (i.e. the module-level fallback
    # to 0 doesn't accidentally mask a real bit).
    assert captured["flags"] & os.O_WRONLY
    assert captured["flags"] & os.O_CREAT
    assert captured["flags"] & os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        assert captured["flags"] & os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        assert captured["flags"] & os.O_CLOEXEC


def test_tmp_file_mode_is_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mode argument to os.open for the tmp file must be 0o600 (decision #71)."""
    captured: dict[str, int] = {}
    real_open = os.open

    def tracking_open(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "mode" not in captured:
            captured["mode"] = mode
        return real_open(p, flags, mode, *args, **kwargs)

    monkeypatch.setattr(_atomic_io.os, "open", tracking_open)
    atomic_write(tmp_path / "data.json", {"k": 1})
    assert captured["mode"] == 0o600


def test_os_replace_called_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def tracking_replace(src, dst):  # type: ignore[no-untyped-def]
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(_atomic_io.os, "replace", tracking_replace)
    atomic_write(tmp_path / "data.json", {"k": 1})
    assert len(calls) == 1


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="parent-dir fsync is POSIX-only; spec §4.3 explicitly skips on Windows",
)
def test_parent_dir_fsync_on_posix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two fsync calls expected on POSIX: one for tmp fd, one for parent dir."""
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd):  # type: ignore[no-untyped-def]
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(_atomic_io.os, "fsync", tracking_fsync)
    atomic_write(tmp_path / "data.json", {"k": 1})
    assert len(fsync_calls) == 2


def test_parent_dir_fsync_skipped_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If sys.platform == "win32", parent-dir fsync MUST be skipped (one fsync only)."""
    monkeypatch.setattr(_atomic_io, "sys", _Win32Stub())
    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def tracking_fsync(fd):  # type: ignore[no-untyped-def]
        fsync_calls.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(_atomic_io.os, "fsync", tracking_fsync)
    atomic_write(tmp_path / "data.json", {"k": 1})
    # Only the tmp-file fd fsync; no parent-dir fsync.
    assert len(fsync_calls) == 1


class _Win32Stub:
    """Minimal stand-in for `sys` so `sys.platform == "win32"` is True."""

    platform = "win32"


def _count_tmp_orphans(directory: Path, base: str) -> int:
    return len(list(directory.glob(f"{base}.tmp*")))


def test_cleanup_on_os_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R9-1: os.write raising must leave NO `*.tmp.*` orphan."""
    target = tmp_path / "data.json"

    def boom(fd, data):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(_atomic_io.os, "write", boom)
    with pytest.raises(OSError, match="disk full"):
        atomic_write(target, {"k": 1})
    assert _count_tmp_orphans(tmp_path, "data.json") == 0
    assert not target.exists()


def test_cleanup_on_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R9-1: os.fsync(fd) raising must leave NO `*.tmp.*` orphan."""
    target = tmp_path / "data.json"

    def boom(fd):  # type: ignore[no-untyped-def]
        raise OSError("fsync failed")

    monkeypatch.setattr(_atomic_io.os, "fsync", boom)
    with pytest.raises(OSError, match="fsync failed"):
        atomic_write(target, {"k": 1})
    assert _count_tmp_orphans(tmp_path, "data.json") == 0
    assert not target.exists()


def test_cleanup_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R9-1: os.replace raising must leave NO `*.tmp.*` orphan."""
    target = tmp_path / "data.json"

    def boom(src, dst):  # type: ignore[no-untyped-def]
        raise OSError("replace failed")

    monkeypatch.setattr(_atomic_io.os, "replace", boom)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write(target, {"k": 1})
    assert _count_tmp_orphans(tmp_path, "data.json") == 0
    assert not target.exists()


def test_cleanup_tolerates_already_unlinked_tmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`os.unlink(tmp)` raising FileNotFoundError must be swallowed."""
    target = tmp_path / "data.json"

    def boom_replace(src, dst):  # type: ignore[no-untyped-def]
        # delete the tmp file before re-raising, so the cleanup path hits
        # FileNotFoundError on its os.unlink call.
        os.unlink(src)
        raise OSError("replace failed after tmp vanished")

    monkeypatch.setattr(_atomic_io.os, "replace", boom_replace)
    with pytest.raises(OSError, match="replace failed after tmp vanished"):
        atomic_write(target, {"k": 1})
    assert _count_tmp_orphans(tmp_path, "data.json") == 0


def test_csprng_nonces_are_distinct(tmp_path: Path) -> None:
    """100 successive writes must use 100 distinct nonces (CSPRNG smoke)."""
    nonces: set[str] = set()
    target = tmp_path / "data.json"

    captured: list[str] = []
    real_open = os.open

    # Wrap os.open just to capture which tmp filename is being created.
    def tracking_open(p, flags, mode=0o777, *args, **kwargs):  # type: ignore[no-untyped-def]
        path_str = os.fspath(p)
        if ".tmp." in path_str:
            captured.append(path_str)
        return real_open(p, flags, mode, *args, **kwargs)

    import unittest.mock as _mock

    with _mock.patch.object(_atomic_io.os, "open", side_effect=tracking_open):
        for _ in range(100):
            atomic_write(target, {"k": 1})

    for path in captured:
        # tmp filename: data.json.tmp.<pid>.<16hex>
        suffix = path.rsplit(".", 1)[-1]
        assert len(suffix) == 16, f"expected 16-hex token suffix, got {suffix!r}"
        nonces.add(suffix)
    assert len(nonces) == 100, f"expected 100 distinct nonces, got {len(nonces)}"


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="R8-1b end-to-end gate runs only on Windows runner",
)
def test_atomic_write_round_trip_on_windows(tmp_path: Path) -> None:
    """R8-1b: `atomic_write(b"hello")` succeeds on Windows (no parent-dir fsync)."""
    target = tmp_path / "hello.bin"
    atomic_write(target, b"hello")
    assert target.read_bytes() == b"hello"
