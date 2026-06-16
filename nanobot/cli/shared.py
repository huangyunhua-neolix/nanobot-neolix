"""Shared CLI infrastructure for nanobot Typer command modules."""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import suppress
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
        with suppress(Exception):
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
