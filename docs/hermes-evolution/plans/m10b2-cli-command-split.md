# M10b-2 CLI Command Split Implementation Plan

**Status:** Implemented and verified locally on 2026-06-17. Focused CLI tests and Ruff passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split gateway and provider OAuth CLI command implementations out of `nanobot/cli/commands.py` while preserving the public `nanobot.cli.commands.app` Typer entry point and existing CLI behavior.

**Architecture:** Introduce `nanobot/cli/shared.py` as the one-way dependency target for CLI globals and shared helpers. Move flat gateway command handlers and gateway runtime wiring into `nanobot/cli/gateway_commands.py`, move the nested provider Typer app and OAuth handlers into `nanobot/cli/provider_commands.py`, then have `commands.py` explicitly register both command families on the existing root app.

**Tech Stack:** Python 3.11, Typer, Rich, Loguru, pytest, `uv run`, Ruff.

---

## Context

M10b-1 already split high-change slash commands out of `nanobot/command/builtin.py`. M10b-2 applies the same explicit-registration pattern to the Typer CLI surface.

Approved spec: `docs/hermes-evolution/specs/m10b2-cli-command-split.md`.

Do not change command names, command options, help behavior, output intent, config loading semantics, gateway runtime wiring, provider OAuth storage paths, or optional dependency laziness.

## File Structure

### Create

- `nanobot/cli/shared.py`
  - Owns `console`, loguru handler setup, proactive WebUI metadata helpers, heartbeat helper, runtime config loading, deprecated-config warnings, cron-store migration, and model display formatting.
  - Must not import `nanobot.cli.commands`, `nanobot.cli.gateway_commands`, or `nanobot.cli.provider_commands`.

- `nanobot/cli/gateway_commands.py`
  - Owns `serve`, `gateway`, `desktop_gateway`, desktop bootstrap helpers, `_configure_desktop_gateway()`, `_load_or_create_desktop_config()`, and `_run_gateway()`.
  - Exposes `register_gateway_commands(app: typer.Typer) -> None`.
  - Must not import `nanobot.cli.commands`.

- `nanobot/cli/provider_commands.py`
  - Owns `provider_app`, provider login/logout commands, OAuth provider resolver, login/logout registries, provider-specific handlers, and `_delete_oauth_files()`.
  - Exposes `register_provider_commands(app: typer.Typer) -> None`.
  - Must not import `nanobot.cli.commands`.

### Modify

- `nanobot/cli/commands.py`
  - Import shared globals/helpers from `nanobot.cli.shared`.
  - Create root `app` as before.
  - Call `register_gateway_commands(app)` and `register_provider_commands(app)` once after app creation.
  - Keep onboarding, interactive `agent()`, channel, plugin/status, and `evolve` bridge commands in place.

- `tests/cli/test_commands.py`
  - Update moved helper imports.
  - Add or preserve help/registration coverage for moved commands.
  - Add import-boundary checks for the new modules.

- `tests/agent/skills/test_dream_e2e.py`
  - Update the Dream cron structural assertion to inspect `nanobot/cli/gateway_commands.py` because `_run_gateway()` moves there.

## Implementation Tasks

### Task 1: Extract shared CLI infrastructure

**Files:**
- Create: `nanobot/cli/shared.py`
- Modify: `nanobot/cli/commands.py:1-160`, `nanobot/cli/commands.py:599-660`
- Modify: `tests/cli/test_commands.py:1-40`, `tests/cli/test_commands.py:988-1008`, `tests/cli/test_commands.py:1553-1590`

- [x] **Step 1: Update tests to target the new shared module**

In `tests/cli/test_commands.py`, replace the top import:

```python
from nanobot.cli.commands import _proactive_delivery_metadata, app
```

with:

```python
from nanobot.cli.commands import app
from nanobot.cli.shared import _proactive_delivery_metadata
```

In `test_heartbeat_has_active_tasks()` and `test_heartbeat_skips_bundled_template()`, replace:

```python
from nanobot.cli.commands import _heartbeat_has_active_tasks
```

with:

```python
from nanobot.cli.shared import _heartbeat_has_active_tasks
```

In `test_migrate_cron_store_moves_legacy_file()` and `test_migrate_cron_store_skips_when_workspace_file_exists()`, replace:

```python
from nanobot.cli.commands import _migrate_cron_store
```

with:

```python
from nanobot.cli.shared import _migrate_cron_store
```

- [x] **Step 2: Add a shared import-boundary test**

Append this test near the cron migration tests in `tests/cli/test_commands.py`:

```python
def test_cli_shared_has_no_command_module_imports() -> None:
    source = Path("nanobot/cli/shared.py").read_text(encoding="utf-8")

    assert "nanobot.cli.commands" not in source
    assert "nanobot.cli.gateway_commands" not in source
    assert "nanobot.cli.provider_commands" not in source
```

- [x] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_proactive_websocket_delivery_gets_fresh_turn_id tests/cli/test_commands.py::test_heartbeat_has_active_tasks tests/cli/test_commands.py::test_heartbeat_skips_bundled_template tests/cli/test_commands.py::test_migrate_cron_store_moves_legacy_file tests/cli/test_commands.py::test_migrate_cron_store_skips_when_workspace_file_exists tests/cli/test_commands.py::test_cli_shared_has_no_command_module_imports -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'nanobot.cli.shared'`.

- [x] **Step 4: Create `nanobot/cli/shared.py` with moved infrastructure**

Create `nanobot/cli/shared.py` with the following structure and move the implementations unchanged from `commands.py`:

```python
"""Shared CLI infrastructure for nanobot Typer command modules."""

from __future__ import annotations

import os
import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console

from nanobot.config.schema import Config

# Force UTF-8 encoding for Windows console.
if sys.platform == "win32":
    if sys.stdout.encoding != "utf-8":
        os.environ["PYTHONIOENCODING"] = "utf-8"
        with __import__("contextlib").suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logger.remove()
_log_handler_id = logger.add(
    sys.stderr,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <5}</level> | "
        "<cyan>{extra[channel]}</cyan> | "
        "<level>{message}</level>"
    ),
    level="INFO",
    colorize=None,
    filter=lambda record: record["extra"].setdefault("channel", "-") or True,
)

console = Console()

_WEBUI_TURN_META_KEY = "webui_turn_id"
_WEBUI_MESSAGE_SOURCE_META_KEY = "_webui_message_source"
_PROACTIVE_WEBUI_METADATA: ContextVar[dict[str, Any] | None] = ContextVar(
    "proactive_webui_metadata",
    default=None,
)

_HEARTBEAT_PREAMBLE = (
    "[Your response will be delivered directly to the user's messaging app. "
    "Output ONLY the final user-facing message. Never reference internal "
    "files (HEARTBEAT.md, AWARENESS.md, etc.), your instructions, or your "
    "decision process. If nothing needs reporting, respond with just "
    "'All clear.' and nothing else.]\n\n"
)


def _proactive_delivery_metadata(
    channel: str,
    metadata: dict[str, Any] | None,
    *,
    turn_seed: str,
    source_label: str | None = None,
) -> dict[str, Any]:
    """Return channel metadata for a fresh proactive delivery turn."""
    out = dict(metadata or {})
    out.pop(_WEBUI_TURN_META_KEY, None)
    if channel == "websocket":
        out[_WEBUI_TURN_META_KEY] = f"{turn_seed}:{uuid.uuid4().hex}"
        source: dict[str, str] = {"kind": "cron"}
        if source_label:
            source["label"] = source_label
        out[_WEBUI_MESSAGE_SOURCE_META_KEY] = source
    return out


def _heartbeat_has_active_tasks(content: str) -> bool:
    """True if HEARTBEAT.md has task lines, ignoring headers, blanks and comments."""
    in_comment = False
    in_active_section: bool = False
    for line in content.splitlines():
        stripped = line.strip()
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if not stripped or stripped.startswith("#"):
            if stripped.startswith("##") and not stripped.startswith("###"):
                heading = stripped.lstrip("#").strip().lower()
                in_active_section = heading.startswith("active tasks")
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped[4:]:
                in_comment = True
            continue
        if in_active_section is False:
            continue
        return True
    return False


def _model_display(config: Config) -> tuple[str, str]:
    """Return (resolved_model_name, preset_tag) for display strings."""
    resolved = config.resolve_preset()
    name = config.agents.defaults.model_preset
    tag = f" (preset: {name})" if name else ""
    return resolved.model, tag


def _load_runtime_config(config: str | None = None, workspace: str | None = None) -> Config:
    """Load config and optionally override the active workspace."""
    from nanobot.config.loader import load_config, resolve_config_env_vars, set_config_path

    config_path = None
    if config:
        config_path = Path(config).expanduser().resolve()
        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_path}[/red]")
            raise typer.Exit(1)
        set_config_path(config_path)
        console.print(f"[dim]Using config: {config_path}[/dim]")

    try:
        loaded = resolve_config_env_vars(load_config(config_path))
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e
    _warn_deprecated_config_keys(config_path)
    if workspace:
        loaded.agents.defaults.workspace = workspace
    return loaded


def _warn_deprecated_config_keys(config_path: Path | None) -> None:
    """Hint users to remove obsolete keys from their config file."""
    import json

    from nanobot.config.loader import get_config_path

    path = config_path or get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if "memoryWindow" in raw.get("agents", {}).get("defaults", {}):
        console.print(
            "[dim]Hint: `memoryWindow` in your config is no longer used "
            "and can be safely removed.[/dim]"
        )


def _migrate_cron_store(config: Config) -> None:
    """One-time migration: move legacy global cron store into the workspace."""
    from nanobot.config.paths import get_cron_dir

    legacy_path = get_cron_dir() / "jobs.json"
    new_path = config.workspace_path / "cron" / "jobs.json"
    if legacy_path.is_file() and not new_path.exists():
        new_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.move(str(legacy_path), str(new_path))
```

- [x] **Step 5: Update `commands.py` to import shared infrastructure**

In `nanobot/cli/commands.py`, remove the moved definitions:

- Windows UTF-8 setup block at lines 15-22
- direct `from loguru import logger` setup block at lines 26-41
- `from rich.console import Console`
- `_WEBUI_TURN_META_KEY`, `_WEBUI_MESSAGE_SOURCE_META_KEY`, `_PROACTIVE_WEBUI_METADATA`
- `_proactive_delivery_metadata()`
- `console = Console()`
- `_HEARTBEAT_PREAMBLE`
- `_heartbeat_has_active_tasks()`
- `_model_display()`
- `_load_runtime_config()`
- `_warn_deprecated_config_keys()`
- `_migrate_cron_store()`

Add this import after other project imports:

```python
from nanobot.cli.shared import (  # noqa: E402
    _HEARTBEAT_PREAMBLE,
    _PROACTIVE_WEBUI_METADATA,
    _heartbeat_has_active_tasks,
    _load_runtime_config,
    _log_handler_id,
    _migrate_cron_store,
    _model_display,
    _proactive_delivery_metadata,
    console,
    logger,
)
```

Keep `import sys` in `commands.py`; the interactive command and verbose logging paths still need it.

- [x] **Step 6: Run the focused tests and verify they pass**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_proactive_websocket_delivery_gets_fresh_turn_id tests/cli/test_commands.py::test_heartbeat_has_active_tasks tests/cli/test_commands.py::test_heartbeat_skips_bundled_template tests/cli/test_commands.py::test_migrate_cron_store_moves_legacy_file tests/cli/test_commands.py::test_migrate_cron_store_skips_when_workspace_file_exists tests/cli/test_commands.py::test_cli_shared_has_no_command_module_imports -v
```

Expected: PASS.

- [x] **Step 7: Run lint for touched files**

Run:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py tests/cli/test_commands.py
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add nanobot/cli/commands.py nanobot/cli/shared.py tests/cli/test_commands.py
git commit -m "refactor(cli): extract shared CLI infrastructure"
```

### Task 2: Move provider OAuth commands

**Files:**
- Create: `nanobot/cli/provider_commands.py`
- Modify: `nanobot/cli/commands.py:1880-2050`
- Modify: `tests/cli/test_commands.py:251-331`

- [x] **Step 1: Add provider registration and import-boundary tests**

Append these tests near the existing provider logout/login tests in `tests/cli/test_commands.py`:

```python
def test_provider_help_remains_registered() -> None:
    result = runner.invoke(app, ["provider", "--help"])

    assert result.exit_code == 0
    assert "login" in result.stdout
    assert "logout" in result.stdout


def test_provider_login_help_remains_registered() -> None:
    result = runner.invoke(app, ["provider", "login", "--help"])

    assert result.exit_code == 0
    assert "OAuth provider" in result.stdout


def test_provider_logout_help_remains_registered() -> None:
    result = runner.invoke(app, ["provider", "logout", "--help"])

    assert result.exit_code == 0
    assert "OAuth provider" in result.stdout


def test_provider_commands_module_has_no_commands_import() -> None:
    source = Path("nanobot/cli/provider_commands.py").read_text(encoding="utf-8")

    assert "nanobot.cli.commands" not in source
```

- [x] **Step 2: Run the provider tests and verify the boundary test fails**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_provider_help_remains_registered tests/cli/test_commands.py::test_provider_login_help_remains_registered tests/cli/test_commands.py::test_provider_logout_help_remains_registered tests/cli/test_commands.py::test_provider_commands_module_has_no_commands_import tests/cli/test_commands.py::test_provider_logout_openai_codex_removes_local_oauth_files tests/cli/test_commands.py::test_provider_logout_openai_codex_succeeds_when_no_local_oauth_file tests/cli/test_commands.py::test_provider_logout_github_copilot_removes_local_oauth_files tests/cli/test_commands.py::test_provider_logout_github_copilot_succeeds_when_no_local_oauth_file tests/cli/test_commands.py::test_provider_logout_rejects_unknown_provider tests/cli/test_commands.py::test_provider_login_rejects_unknown_provider -v
```

Expected: FAIL because `nanobot/cli/provider_commands.py` does not exist yet.

- [x] **Step 3: Create `provider_commands.py` by moving the provider block unchanged**

Create `nanobot/cli/provider_commands.py` with this module header:

```python
"""Provider OAuth CLI command registrations."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

import typer

from nanobot import __logo__
from nanobot.cli.shared import console
```

Then move the provider block from `nanobot/cli/commands.py` into this module:

- `provider_app = typer.Typer(help="Manage providers")`
- `_LOGIN_HANDLERS`
- `_LOGOUT_HANDLERS`
- `_PROVIDER_DISPLAY`
- `_register_login()`
- `_register_logout()`
- `_resolve_oauth_provider()`
- `provider_login()` without the `@provider_app.command("login")` decorator
- `provider_logout()` without the `@provider_app.command("logout")` decorator
- `_login_openai_codex()`
- `_logout_openai_codex()`
- `_logout_github_copilot()`
- `_delete_oauth_files()`
- `_login_github_copilot()`

Add explicit registration at the bottom of `provider_commands.py`:

```python
def register_provider_commands(app: typer.Typer) -> None:
    """Attach provider OAuth commands to the root Typer app."""
    provider_app.command("login")(provider_login)
    provider_app.command("logout")(provider_logout)
    app.add_typer(provider_app, name="provider")
```

Do not import anything from `nanobot.cli.commands`.

- [x] **Step 4: Register provider commands from `commands.py`**

In `nanobot/cli/commands.py`, remove the entire provider OAuth block from `provider_app = typer.Typer(help="Manage providers")` through `_login_github_copilot()`.

After root `app = typer.Typer(...)` is created, add:

```python
from nanobot.cli.provider_commands import register_provider_commands  # noqa: E402

register_provider_commands(app)
```

Keep this registration before the `if __name__ == "__main__":` block and after `app` exists. It can appear near app creation so provider commands are registered before tests import `app`.

- [x] **Step 5: Remove now-unused imports from `commands.py`**

Remove imports from `commands.py` that become unused after provider extraction:

```python
from collections.abc import Callable
```

Only remove `Path`, `suppress`, or `typer` if Ruff proves they are unused. At this point `Path`, `suppress`, and `typer` are still used by other command families.

- [x] **Step 6: Run provider tests and verify they pass**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_provider_help_remains_registered tests/cli/test_commands.py::test_provider_login_help_remains_registered tests/cli/test_commands.py::test_provider_logout_help_remains_registered tests/cli/test_commands.py::test_provider_commands_module_has_no_commands_import tests/cli/test_commands.py::test_provider_logout_openai_codex_removes_local_oauth_files tests/cli/test_commands.py::test_provider_logout_openai_codex_succeeds_when_no_local_oauth_file tests/cli/test_commands.py::test_provider_logout_github_copilot_removes_local_oauth_files tests/cli/test_commands.py::test_provider_logout_github_copilot_succeeds_when_no_local_oauth_file tests/cli/test_commands.py::test_provider_logout_rejects_unknown_provider tests/cli/test_commands.py::test_provider_login_rejects_unknown_provider -v
```

Expected: PASS.

- [x] **Step 7: Run lint for touched files**

Run:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add nanobot/cli/commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py
git commit -m "refactor(cli): move provider OAuth commands"
```

### Task 3: Move gateway commands and runtime wiring

**Files:**
- Create: `nanobot/cli/gateway_commands.py`
- Modify: `nanobot/cli/commands.py:667-1455`
- Modify: `tests/cli/test_commands.py:1112-1730`
- Modify: `tests/agent/skills/test_dream_e2e.py:1-170`

- [x] **Step 1: Update gateway helper imports in tests**

In `tests/cli/test_commands.py`, replace every direct import of moved gateway helpers:

```python
from nanobot.cli.commands import _configure_desktop_gateway
from nanobot.cli.commands import _load_or_create_desktop_config
```

with:

```python
from nanobot.cli.gateway_commands import _configure_desktop_gateway
from nanobot.cli.gateway_commands import _load_or_create_desktop_config
```

- [x] **Step 2: Add gateway help and import-boundary tests**

Append these tests near the existing gateway tests in `tests/cli/test_commands.py`:

```python
def test_serve_help_remains_registered() -> None:
    result = runner.invoke(app, ["serve", "--help"])

    assert result.exit_code == 0
    assert "API server port" in result.stdout
    assert "OpenAI-compatible" in result.stdout


def test_gateway_help_remains_registered() -> None:
    result = runner.invoke(app, ["gateway", "--help"])

    assert result.exit_code == 0
    assert "Gateway port" in result.stdout
    assert "Workspace directory" in result.stdout


def test_desktop_gateway_help_remains_registered() -> None:
    result = runner.invoke(app, ["desktop-gateway", "--help"])

    assert result.exit_code == 0
    assert "--token-issue-secret" in result.stdout
    assert "--webui-port" in result.stdout


def test_desktop_gateway_stays_hidden_from_top_level_help() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "desktop-gateway" not in result.stdout


def test_gateway_commands_module_has_no_commands_import() -> None:
    source = Path("nanobot/cli/gateway_commands.py").read_text(encoding="utf-8")

    assert "nanobot.cli.commands" not in source
```

- [x] **Step 3: Update the Dream cron structural test path**

In `tests/agent/skills/test_dream_e2e.py`, update the module docstring bullet from:

```python
* ``nanobot/cli/commands.py`` — the cron Dream job calls
```

to:

```python
* ``nanobot/cli/gateway_commands.py`` — the cron Dream job calls
```

In `test_cli_commands_dream_path_uses_context_memory()`, replace:

```python
rel = "nanobot/cli/commands.py"
```

with:

```python
rel = "nanobot/cli/gateway_commands.py"
```

- [x] **Step 4: Run gateway-focused tests and verify they fail**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_serve_help_remains_registered tests/cli/test_commands.py::test_gateway_help_remains_registered tests/cli/test_commands.py::test_desktop_gateway_help_remains_registered tests/cli/test_commands.py::test_desktop_gateway_stays_hidden_from_top_level_help tests/cli/test_commands.py::test_gateway_commands_module_has_no_commands_import tests/cli/test_commands.py::test_configure_desktop_gateway_forces_local_websocket_only tests/cli/test_commands.py::test_load_or_create_desktop_config_bootstraps_without_api_key tests/cli/test_commands.py::test_load_or_create_desktop_config_repairs_existing_unconfigured_default tests/cli/test_commands.py::test_load_or_create_desktop_config_unwinds_persisted_bootstrap tests/agent/skills/test_dream_e2e.py::test_cli_commands_dream_path_uses_context_memory -v
```

Expected: FAIL because `nanobot/cli/gateway_commands.py` does not exist yet.

- [x] **Step 5: Create `gateway_commands.py` by moving gateway code unchanged**

Create `nanobot/cli/gateway_commands.py` with this module header:

```python
"""Gateway-related CLI command registrations."""

from __future__ import annotations

import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import typer
from aiohttp import web

from nanobot import __logo__, __version__
from nanobot.agent.loop import AgentLoop
from nanobot.cli.shared import (
    _HEARTBEAT_PREAMBLE,
    _PROACTIVE_WEBUI_METADATA,
    _heartbeat_has_active_tasks,
    _load_runtime_config,
    _log_handler_id,
    _migrate_cron_store,
    _model_display,
    _proactive_delivery_metadata,
    console,
    logger,
)
from nanobot.config.paths import is_default_workspace
from nanobot.config.schema import Config
from nanobot.utils.helpers import sync_workspace_templates
```

Move these definitions from `commands.py` into `gateway_commands.py`:

- `serve()` without the `@app.command()` decorator
- `gateway()` without the `@app.command()` decorator
- `DESKTOP_BOOTSTRAP_PROVIDER`
- `DESKTOP_BOOTSTRAP_MODEL`
- `_desktop_provider_error_is_recoverable()`
- `_desktop_provider_needs_bootstrap()`
- `_reset_desktop_config_to_unconfigured()`
- `_is_persisted_desktop_bootstrap()`
- `_apply_desktop_runtime_bootstrap()`
- `_load_or_create_desktop_config()`
- `_configure_desktop_gateway()`
- `desktop_gateway()` without the `@app.command("desktop-gateway", hidden=True)` decorator
- `_run_gateway()`

Keep all lazy imports inside those functions exactly as they are today.

At the bottom of `gateway_commands.py`, add:

```python
def register_gateway_commands(app: typer.Typer) -> None:
    """Register gateway-related commands on the root Typer app."""
    app.command()(serve)
    app.command()(gateway)
    app.command("desktop-gateway", hidden=True)(desktop_gateway)
```

Do not import anything from `nanobot.cli.commands`.

- [x] **Step 6: Register gateway commands from `commands.py`**

In `nanobot/cli/commands.py`, remove the moved OpenAI-compatible API server and gateway block from the `# OpenAI-Compatible API Server` section through the end of `_run_gateway()`.

After root `app = typer.Typer(...)` is created, add:

```python
from nanobot.cli.gateway_commands import register_gateway_commands  # noqa: E402

register_gateway_commands(app)
```

If both gateway and provider registration imports are near app creation, keep the order:

```python
from nanobot.cli.gateway_commands import register_gateway_commands  # noqa: E402
from nanobot.cli.provider_commands import register_provider_commands  # noqa: E402

register_gateway_commands(app)
register_provider_commands(app)
```

- [x] **Step 7: Fix imports after the move**

Run Ruff to identify unused imports:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/gateway_commands.py
```

Expected: FAIL if imports are stale.

Remove only imports that Ruff reports as unused. Common removals from `commands.py` after this task are:

```python
from typing import Any
from nanobot.config.paths import is_default_workspace
from nanobot.utils.helpers import sync_workspace_templates
```

Do not remove imports still used by onboarding or interactive agent mode.

- [x] **Step 8: Run gateway-focused tests and verify they pass**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_serve_help_remains_registered tests/cli/test_commands.py::test_gateway_help_remains_registered tests/cli/test_commands.py::test_desktop_gateway_help_remains_registered tests/cli/test_commands.py::test_desktop_gateway_stays_hidden_from_top_level_help tests/cli/test_commands.py::test_gateway_commands_module_has_no_commands_import tests/cli/test_commands.py::test_gateway_uses_workspace_from_config_by_default tests/cli/test_commands.py::test_gateway_uses_configured_port_when_cli_flag_is_missing tests/cli/test_commands.py::test_gateway_cli_port_overrides_configured_port tests/cli/test_commands.py::test_configure_desktop_gateway_forces_local_websocket_only tests/cli/test_commands.py::test_load_or_create_desktop_config_bootstraps_without_api_key tests/cli/test_commands.py::test_load_or_create_desktop_config_repairs_existing_unconfigured_default tests/cli/test_commands.py::test_load_or_create_desktop_config_unwinds_persisted_bootstrap tests/agent/skills/test_dream_e2e.py::test_cli_commands_dream_path_uses_context_memory -v
```

Expected: PASS.

- [x] **Step 9: Run lint for touched files**

Run:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

Expected: PASS.

- [x] **Step 10: Commit**

```bash
git add nanobot/cli/commands.py nanobot/cli/gateway_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
git commit -m "refactor(cli): move gateway commands"
```

### Task 4: Enforce command split boundaries

**Files:**
- Modify: `tests/cli/test_commands.py`
- Possibly modify: `nanobot/cli/commands.py`, `nanobot/cli/shared.py`, `nanobot/cli/gateway_commands.py`, `nanobot/cli/provider_commands.py`

- [x] **Step 1: Add structural boundary tests for `commands.py`**

Append these tests near the other import-boundary tests in `tests/cli/test_commands.py`:

```python
def test_commands_py_no_longer_defines_moved_gateway_handlers() -> None:
    source = Path("nanobot/cli/commands.py").read_text(encoding="utf-8")

    assert "def serve(" not in source
    assert "def gateway(" not in source
    assert "def desktop_gateway(" not in source
    assert "def _run_gateway(" not in source
    assert "DESKTOP_BOOTSTRAP_PROVIDER" not in source


def test_commands_py_no_longer_defines_provider_oauth_handlers() -> None:
    source = Path("nanobot/cli/commands.py").read_text(encoding="utf-8")

    assert "provider_app = typer.Typer" not in source
    assert "def provider_login(" not in source
    assert "def provider_logout(" not in source
    assert "def _login_openai_codex(" not in source
    assert "def _login_github_copilot(" not in source


def test_commands_py_registers_focused_cli_modules_explicitly() -> None:
    source = Path("nanobot/cli/commands.py").read_text(encoding="utf-8")

    assert "from nanobot.cli.gateway_commands import register_gateway_commands" in source
    assert "from nanobot.cli.provider_commands import register_provider_commands" in source
    assert "register_gateway_commands(app)" in source
    assert "register_provider_commands(app)" in source
```

- [x] **Step 2: Run boundary tests and verify they pass**

Run:

```bash
uv run pytest tests/cli/test_commands.py::test_cli_shared_has_no_command_module_imports tests/cli/test_commands.py::test_gateway_commands_module_has_no_commands_import tests/cli/test_commands.py::test_provider_commands_module_has_no_commands_import tests/cli/test_commands.py::test_commands_py_no_longer_defines_moved_gateway_handlers tests/cli/test_commands.py::test_commands_py_no_longer_defines_provider_oauth_handlers tests/cli/test_commands.py::test_commands_py_registers_focused_cli_modules_explicitly -v
```

Expected: PASS. If a test fails, remove the stale moved handler or stale import from `commands.py` rather than adding compatibility re-exports.

- [x] **Step 3: Verify no production code imports moved internals from `commands.py`**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
patterns = (
    "from nanobot.cli.commands import _configure_desktop_gateway",
    "from nanobot.cli.commands import _load_or_create_desktop_config",
    "from nanobot.cli.commands import _migrate_cron_store",
    "from nanobot.cli.commands import _heartbeat_has_active_tasks",
    "from nanobot.cli.commands import provider_login",
    "from nanobot.cli.commands import provider_logout",
)
for path in Path('.').rglob('*.py'):
    if '.venv' in path.parts:
        continue
    text = path.read_text(encoding='utf-8')
    for pattern in patterns:
        if pattern in text:
            print(f'{path}: {pattern}')
PY
```

Expected: no output. If output appears, update the import to `nanobot.cli.shared`, `nanobot.cli.gateway_commands`, or `nanobot.cli.provider_commands` as appropriate.

- [x] **Step 4: Run lint for changed files**

Run:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
git commit -m "test(cli): pin CLI command split boundaries"
```

### Task 5: Focused regression verification

**Files:**
- Possibly modify only if focused tests expose migration mistakes.

- [x] **Step 1: Run focused CLI and Dream tests**

Run:

```bash
uv run pytest tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py -v
```

Expected: PASS.

- [x] **Step 2: Run lint on the M10b-2 changed Python files**

Run:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

Expected: PASS.

- [x] **Step 3: Run import smoke checks**

Run:

```bash
uv run python - <<'PY'
from typer.testing import CliRunner
from nanobot.cli.commands import app

runner = CliRunner()
commands = [
    ["serve", "--help"],
    ["gateway", "--help"],
    ["desktop-gateway", "--help"],
    ["provider", "login", "--help"],
    ["provider", "logout", "--help"],
]
for command in commands:
    result = runner.invoke(app, command)
    if result.exit_code != 0:
        raise SystemExit(f"{command} failed: {result.stdout}\n{result.exception}")
print("CLI command smoke checks passed")
PY
```

Expected: output includes `CLI command smoke checks passed`.

- [x] **Step 4: Check file-size direction**

Run:

```bash
uv run python - <<'PY'
from pathlib import Path
for path in [
    Path('nanobot/cli/commands.py'),
    Path('nanobot/cli/shared.py'),
    Path('nanobot/cli/gateway_commands.py'),
    Path('nanobot/cli/provider_commands.py'),
]:
    print(f"{path}: {len(path.read_text(encoding='utf-8').splitlines())} lines")
PY
```

Expected: `nanobot/cli/commands.py` is materially smaller than the pre-split size of about 2,086 lines.

- [x] **Step 5: Commit any verification fixes**

If Steps 1-4 required fixes, commit them:

```bash
git add nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
git commit -m "fix(cli): stabilize CLI command split"
```

If no fixes were required, do not create an empty commit.

### Task 6: Final implementation review and plan status update

**Files:**
- Modify: `docs/hermes-evolution/plans/m10b2-cli-command-split.md`

- [x] **Step 1: Run the final verification commands**

Run:

```bash
uv run pytest tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py -v
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

Expected: PASS.

- [x] **Step 2: Update this plan checklist after implementation**

After all implementation tasks are complete and verified, replace each completed task checkbox in this file from `- [x]` to `- [x]`. Add this status line below the title:

```markdown
**Status:** Implemented and verified locally on 2026-06-16. Focused CLI tests and Ruff passed.
```

Do not mark the roadmap complete until the implementation PR has merged.

- [x] **Step 3: Commit the plan status update**

```bash
git add docs/hermes-evolution/plans/m10b2-cli-command-split.md
git commit -m "docs(hermes): mark M10b-2 plan executed"
```

## Verification Plan

Before opening the implementation PR, run:

```bash
uv run pytest tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py -v
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

Optional broader smoke check:

```bash
uv run pytest tests/cli -v
```

## Safety Checklist

- `nanobot.cli.commands.app` remains the root public Typer app.
- `nanobot serve`, `nanobot gateway`, and hidden `nanobot desktop-gateway` remain flat root commands.
- `nanobot provider login` and `nanobot provider logout` remain under the `provider` sub-app.
- `gateway_commands.py` and `provider_commands.py` do not import from `nanobot.cli.commands`.
- `shared.py` does not import any CLI command module.
- OAuth optional imports remain inside provider-specific handlers.
- `_run_gateway()` runtime wiring is moved without internal refactoring.
- No command discovery, plugin registry, compatibility re-export layer, schema migration, or feature flag is introduced.

## Self-Review

- Spec coverage: gateway split, provider split, shared module, explicit registration, import discipline, helper import test migration, Dream structural test migration, help registration coverage, and focused lint/test commands are all mapped to tasks.
- Placeholder scan: no `TBD`, no open-ended "add tests" step without concrete code, no unnamed files.
- Type consistency: registration functions are consistently named `register_gateway_commands(app: typer.Typer) -> None` and `register_provider_commands(app: typer.Typer) -> None`; moved helper import paths match the approved spec.
