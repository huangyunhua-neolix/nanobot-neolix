"""Shared artifact writers for offline evolution review lanes."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from nanobot.evolve.privacy.redact import redact

_REVIEW_TRUNCATION_SUFFIX = "..."


def redact_json_value(value: Any) -> Any:
    """Recursively redact strings in a JSON-like value.

    Mapping keys are stringified so the result can be serialized as JSON. Tuples are
    emitted as lists because JSON has no tuple type. Non-string scalar values are
    preserved unchanged.
    """
    if isinstance(value, str):
        return redact(value).text
    if isinstance(value, Mapping):
        return {redact(str(key)).text: redact_json_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact_json_value(child) for child in value]
    if isinstance(value, tuple):
        return [redact_json_value(child) for child in value]
    return value


def atomic_write_text(path: Path, text: str) -> None:
    """Write text through a sibling temp file and atomically replace the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(text)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def write_redacted_json_artifact(
    path: Path,
    value: Any,
    *,
    ensure_ascii: bool = False,
) -> None:
    """Write a recursively redacted, deterministic JSON artifact."""
    text = json.dumps(
        redact_json_value(value),
        indent=2,
        sort_keys=True,
        ensure_ascii=ensure_ascii,
    )
    atomic_write_text(path, f"{text}\n")


def write_jsonl_artifact(
    path: Path,
    rows: Iterable[Any],
    *,
    sort_keys: bool = True,
    compact: bool = True,
) -> None:
    """Write recursively redacted rows as JSON Lines."""
    dump_options: dict[str, object] = {
        "sort_keys": sort_keys,
        "ensure_ascii": False,
    }
    if compact:
        dump_options["separators"] = (",", ":")
    lines = [json.dumps(redact_json_value(row), **dump_options) for row in rows]
    atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


class OwnedJsonlEvidenceWriter:
    """Owns one JSONL evidence path for a single harness run lane.

    Lifecycle:
    1. ``remove_untrusted()`` — call before writing any harness-controlled rows
       to clear any optimizer-created target at the evidence path.
    2. ``buffer(row_json)`` — accumulate trusted JSON lines in memory.
    3. ``publish()`` — atomically write buffered lines to the evidence path.
    """

    def __init__(self, path: Path, *, evidence_name: str) -> None:
        self._path = path
        self._evidence_name = evidence_name
        self._rows: list[str] = []

    def remove_untrusted(self) -> None:
        """Remove any optimizer-created target before harness ownership.

        Unlinks regular files and symlinks. Fails closed on directories or other
        non-regular targets with a clear error containing the evidence name.
        """
        try:
            mode = self._path.lstat().st_mode
        except FileNotFoundError:
            return
        if stat.S_ISDIR(mode):
            raise IsADirectoryError(
                f"{self._evidence_name} judge evidence path is a directory: {self._path}"
            )
        if not stat.S_ISREG(mode) and not stat.S_ISLNK(mode):
            raise OSError(
                f"{self._evidence_name} judge evidence path is not a regular file or symlink: {self._path}"
            )
        self._path.unlink()

    def buffer(self, row_json: str) -> None:
        """Accumulate a trusted JSON line in memory."""
        self._rows.append(row_json)

    def publish(self) -> str | None:
        """Atomically write buffered lines to the evidence path.

        Returns the filename on success or ``None`` if there are no rows.
        Fails closed if the publish target exists and is not a regular file.
        """
        if not self._rows:
            return None
        try:
            mode = self._path.lstat().st_mode
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(mode):
                raise OSError(
                    f"{self._evidence_name} judge evidence path is not a regular file: {self._path}"
                )
        atomic_write_text(self._path, "\n".join(self._rows) + "\n")
        return self._path.name


def markdown_review_text(value: object, *, max_chars: int = 500) -> str:
    """Redact, escape code fences, and bound text for review markdown."""
    text = "<none>" if value is None else str(value)
    redacted = redact(text).text.replace("```", "'''")
    if len(redacted) <= max_chars:
        return redacted
    if max_chars <= len(_REVIEW_TRUNCATION_SUFFIX):
        return _REVIEW_TRUNCATION_SUFFIX[:max_chars]
    return redacted[: max_chars - len(_REVIEW_TRUNCATION_SUFFIX)] + _REVIEW_TRUNCATION_SUFFIX
