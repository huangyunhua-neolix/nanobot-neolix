from __future__ import annotations

import json
from pathlib import Path

import pytest

from nanobot.evolve.artifacts import (
    atomic_write_text,
    markdown_review_text,
    redact_json_value,
    write_jsonl_artifact,
    write_redacted_json_artifact,
)

_SECRET_PATH = "/Users/alice/private"
_SECRET_EMAIL = "alice@example.com"
_SECRET_KEY = "sk-ant-abcdefghijklmnopqrstuvwxyzABCDEF"


def test_atomic_write_text_replaces_contents_without_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "artifact.md"
    path.write_text("old", encoding="utf-8")

    atomic_write_text(path, "new")

    assert path.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob("artifact.md.*.tmp")) == []


def test_write_redacted_json_artifact_recursively_redacts_nested_strings(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    value = {
        "outer": {
            "path": _SECRET_PATH,
            "items": [
                {"email": _SECRET_EMAIL},
                ("prefix", _SECRET_KEY),
            ],
        },
    }

    write_redacted_json_artifact(path, value)

    text = path.read_text(encoding="utf-8")
    assert _SECRET_PATH not in text
    assert _SECRET_EMAIL not in text
    assert _SECRET_KEY not in text
    assert "/<REDACTED_HOME>/" in text
    assert "[REDACTED:EMAIL]" in text
    assert "[REDACTED:APIKEY:ANTHROPIC]" in text
    assert text.endswith("\n")


def test_write_redacted_json_artifact_redacts_secret_shaped_mapping_keys(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.json"
    value = {
        _SECRET_EMAIL: "email key value",
        _SECRET_PATH: "path key value",
    }

    write_redacted_json_artifact(path, value)

    text = path.read_text(encoding="utf-8")
    assert _SECRET_EMAIL not in text
    assert _SECRET_PATH not in text
    assert "[REDACTED:EMAIL]" in text
    assert "/<REDACTED_HOME>/" in text


def test_write_jsonl_artifact_preserves_row_order_and_redacts_strings(tmp_path: Path) -> None:
    path = tmp_path / "artifact.jsonl"
    rows = [
        {"index": 2, "text": _SECRET_EMAIL},
        {"index": 1, "text": _SECRET_KEY},
    ]

    write_jsonl_artifact(path, rows)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["index"] for line in lines] == [2, 1]
    assert _SECRET_EMAIL not in path.read_text(encoding="utf-8")
    assert _SECRET_KEY not in path.read_text(encoding="utf-8")
    assert "[REDACTED:EMAIL]" in lines[0]
    assert "[REDACTED:APIKEY:ANTHROPIC]" in lines[1]


def test_write_redacted_json_artifact_can_escape_non_ascii_for_compatibility(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.json"

    write_redacted_json_artifact(path, {"message": "工具"}, ensure_ascii=True)

    assert path.read_text(encoding="utf-8") == '{\n  "message": "\\u5de5\\u5177"\n}\n'


def test_write_jsonl_artifact_can_preserve_key_order_and_default_spacing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.jsonl"
    rows = [{"zeta": 1, "alpha": 2}]

    write_jsonl_artifact(path, rows, sort_keys=False, compact=False)

    assert path.read_text(encoding="utf-8") == '{"zeta": 1, "alpha": 2}\n'


def test_write_jsonl_artifact_empty_rows_produce_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"

    write_jsonl_artifact(path, [])

    assert path.read_text(encoding="utf-8") == ""


def test_markdown_review_text_escapes_redacts_and_bounds_text() -> None:
    value = f"Start ``` {_SECRET_EMAIL} {_SECRET_KEY} end"

    text = markdown_review_text(value, max_chars=44)

    assert "```" not in text
    assert "'''" in text
    assert _SECRET_EMAIL not in text
    assert _SECRET_KEY not in text
    assert "[REDACTED:" in text
    assert len(text) == 44
    assert text.endswith("...")


def test_markdown_review_text_none_returns_none_marker() -> None:
    assert markdown_review_text(None) == "<none>"


def test_redact_json_value_preserves_non_string_scalars_unchanged() -> None:
    assert redact_json_value(None) is None
    assert redact_json_value(True) is True
    assert redact_json_value(False) is False
    assert redact_json_value(7) == 7
    assert redact_json_value(3.5) == 3.5


def test_atomic_write_text_creates_missing_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "parents" / "artifact.md"

    atomic_write_text(path, "created")

    assert path.read_text(encoding="utf-8") == "created"


def test_atomic_write_text_removes_temp_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "artifact.md"

    def fail_replace(self: Path, target: Path) -> Path:
        if self.name.startswith("artifact.md.") and self.name.endswith(".tmp"):
            raise OSError("replace failed")
        return original_replace(self, target)

    original_replace = Path.replace
    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(path, "new")

    assert not path.exists()
    assert list(tmp_path.glob("artifact.md.*.tmp")) == []
