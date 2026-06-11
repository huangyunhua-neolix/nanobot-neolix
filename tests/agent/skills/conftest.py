"""Shared fixtures for `tests/agent/skills/` (M2 skill_manage suite).

Currently provides only `tmp_workspace`. Sibling tasks (t-03 provenance,
t-05 quota, t-06+ verbs) extend this conftest with `mock_telemetry`,
`tool_factory`, etc. Keep the file minimal until those land.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Yield a per-test workspace directory under pytest's `tmp_path`.

    The directory exists but is empty; tests creating skills should make
    `<workspace>/skills/agent/...` themselves.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace
