"""Gateway-related CLI command registrations."""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any

import typer

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
from nanobot.utils.evaluator import evaluate_response
from nanobot.utils.helpers import sync_workspace_templates

# ============================================================================
# OpenAI-Compatible API Server
# ============================================================================


def serve(
    port: int | None = typer.Option(None, "--port", "-p", help="API server port"),
    host: str | None = typer.Option(None, "--host", "-H", help="Bind address"),
    timeout: float | None = typer.Option(None, "--timeout", "-t", help="Per-request timeout (seconds)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show nanobot runtime logs"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the OpenAI-compatible API server (/v1/chat/completions)."""
    try:
        from aiohttp import web  # noqa: F401
    except ImportError:
        console.print("[red]aiohttp is required. Install with: pip install 'nanobot-ai[api]'[/red]")
        raise typer.Exit(1)

    from loguru import logger

    from nanobot.api.server import create_app
    from nanobot.bus.queue import MessageBus
    from nanobot.providers.image_generation import image_gen_provider_configs
    from nanobot.session.manager import SessionManager

    if verbose:
        logger.enable("nanobot")
    else:
        logger.disable("nanobot")

    runtime_config = _load_runtime_config(config, workspace)
    api_cfg = runtime_config.api
    host = host if host is not None else api_cfg.host
    port = port if port is not None else api_cfg.port
    timeout = timeout if timeout is not None else api_cfg.timeout
    sync_workspace_templates(runtime_config.workspace_path)
    bus = MessageBus()
    session_manager = SessionManager(runtime_config.workspace_path)
    try:
        agent_loop = AgentLoop.from_config(
            runtime_config, bus,
            session_manager=session_manager,
            image_generation_provider_configs=image_gen_provider_configs(runtime_config),
        )
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc

    model_name, preset_tag = _model_display(runtime_config)
    console.print(f"{__logo__} Starting OpenAI-compatible API server")
    console.print(f"  [cyan]Endpoint[/cyan] : http://{host}:{port}/v1/chat/completions")
    console.print(f"  [cyan]Model[/cyan]    : {model_name}{preset_tag}")
    console.print("  [cyan]Session[/cyan]  : api:default")
    console.print(f"  [cyan]Timeout[/cyan]  : {timeout}s")
    if host in {"0.0.0.0", "::"}:
        console.print(
            "[yellow]Warning:[/yellow] API is bound to all interfaces. "
            "Only do this behind a trusted network boundary, firewall, or reverse proxy."
        )
    console.print()

    api_app = create_app(agent_loop, model_name=model_name, request_timeout=timeout)

    async def on_startup(_app):
        await agent_loop._connect_mcp()

    async def on_cleanup(_app):
        await agent_loop.close_mcp()

    api_app.on_startup.append(on_startup)
    api_app.on_cleanup.append(on_cleanup)

    web.run_app(api_app, host=host, port=port, print=lambda msg: logger.info(msg))


# ============================================================================
# Gateway / Server
# ============================================================================


def gateway(
    port: int | None = typer.Option(None, "--port", "-p", help="Gateway port"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace directory"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
):
    """Start the nanobot gateway."""
    if verbose:
        logger.remove(_log_handler_id)
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <5}</level> | "
                "<cyan>{extra[channel]}</cyan> | "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            colorize=None,
            filter=lambda record: record["extra"].setdefault("channel", "-") or True,
        )
    cfg = _load_runtime_config(config, workspace)
    _run_gateway(cfg, port=port)


DESKTOP_BOOTSTRAP_PROVIDER = "openai_codex"
DESKTOP_BOOTSTRAP_MODEL = "openai-codex/gpt-5.1-codex"


def _desktop_provider_error_is_recoverable(error: ValueError) -> bool:
    message = str(error)
    return "No API key configured" in message or "requires api_key and api_base" in message


def _desktop_provider_needs_bootstrap(config: Config) -> bool:
    from nanobot.providers.factory import make_provider

    try:
        make_provider(config)
        return False
    except ValueError as e:
        if not _desktop_provider_error_is_recoverable(e):
            raise
        return True


def _reset_desktop_config_to_unconfigured(config: Config) -> bool:
    defaults = config.agents.defaults
    changed = False
    if defaults.model_preset is not None:
        defaults.model_preset = None
        changed = True
    if defaults.provider:
        defaults.provider = ""
        changed = True
    if defaults.model:
        defaults.model = ""
        changed = True
    return changed


def _is_persisted_desktop_bootstrap(config: Config) -> bool:
    defaults = config.agents.defaults
    return (
        defaults.model_preset is None
        and defaults.provider == DESKTOP_BOOTSTRAP_PROVIDER
        and defaults.model == DESKTOP_BOOTSTRAP_MODEL
        and not config.model_presets
    )


def _apply_desktop_runtime_bootstrap(config: Config) -> None:
    defaults = config.agents.defaults
    config.agents.defaults.model_preset = None
    defaults.provider = DESKTOP_BOOTSTRAP_PROVIDER
    defaults.model = DESKTOP_BOOTSTRAP_MODEL


def _load_or_create_desktop_config(config: str | None, workspace: str | None) -> Config:
    """Load the desktop-owned config, creating it on first launch."""
    from nanobot.config.loader import (
        get_config_path,
        load_config,
        resolve_config_env_vars,
        save_config,
        set_config_path,
    )
    from nanobot.config.schema import Config as NanobotConfig

    config_path = Path(config).expanduser().resolve() if config else get_config_path()
    set_config_path(config_path)
    changed = False
    if config_path.exists():
        try:
            loaded = resolve_config_env_vars(load_config(config_path))
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
    else:
        loaded = NanobotConfig()
        changed = True

    if workspace:
        workspace_path = Path(workspace).expanduser()
        loaded.agents.defaults.workspace = str(workspace_path)
        changed = True

    if _is_persisted_desktop_bootstrap(loaded):
        changed = _reset_desktop_config_to_unconfigured(loaded) or changed
    elif _desktop_provider_needs_bootstrap(loaded):
        changed = _reset_desktop_config_to_unconfigured(loaded) or changed

    if changed:
        save_config(loaded, config_path)

    runtime_config = loaded.model_copy(deep=True)
    if _desktop_provider_needs_bootstrap(runtime_config):
        _apply_desktop_runtime_bootstrap(runtime_config)
    return runtime_config


def _configure_desktop_gateway(
    config: Config,
    *,
    webui_port: int,
    webui_socket: str | None,
    token_issue_secret: str,
) -> None:
    """Force a local WebSocket-only gateway for the desktop app process."""
    config.gateway.host = "127.0.0.1"
    config.gateway.port = webui_port
    config.gateway.heartbeat.enabled = False

    extras = dict(getattr(config.channels, "__pydantic_extra__", None) or {})
    for name, section in list(extras.items()):
        if name == "websocket":
            continue
        if isinstance(section, dict):
            extras[name] = {**section, "enabled": False}
        else:
            with suppress(Exception):
                setattr(section, "enabled", False)
            extras[name] = section

    websocket_cfg = extras.get("websocket")
    if not isinstance(websocket_cfg, dict):
        websocket_cfg = {}
    websocket_cfg.update(
        {
            "enabled": True,
            "host": "127.0.0.1",
            "port": webui_port,
            "unix_socket_path": webui_socket or "",
            "path": "/",
            "token_issue_secret": token_issue_secret,
            "websocket_requires_token": True,
            "allow_from": ["*"],
            "streaming": True,
        }
    )
    extras["websocket"] = websocket_cfg
    config.channels.__pydantic_extra__ = extras


def desktop_gateway(
    webui_port: int = typer.Option(0, "--webui-port", min=0, max=65535),
    webui_socket: str | None = typer.Option(None, "--webui-socket", help="Unix socket path for desktop IPC"),
    token_issue_secret: str = typer.Option(..., "--token-issue-secret"),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Desktop workspace directory"),
    config: str | None = typer.Option(None, "--config", "-c", help="Desktop config file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the private local gateway used by nanobot Desktop."""
    if not token_issue_secret.strip():
        console.print("[red]Error: --token-issue-secret is required[/red]")
        raise typer.Exit(1)
    if webui_port <= 0 and not (webui_socket or "").strip():
        console.print("[red]Error: --webui-port or --webui-socket is required[/red]")
        raise typer.Exit(1)
    if verbose:
        logger.remove(_log_handler_id)
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <5}</level> | "
                "<cyan>{extra[channel]}</cyan> | "
                "<level>{message}</level>"
            ),
            level="DEBUG",
            colorize=None,
            filter=lambda record: record["extra"].setdefault("channel", "-") or True,
        )
    cfg = _load_or_create_desktop_config(config, workspace)
    _configure_desktop_gateway(
        cfg,
        webui_port=webui_port,
        webui_socket=webui_socket,
        token_issue_secret=token_issue_secret,
    )
    _run_gateway(
        cfg,
        port=webui_port,
        webui_static_dist=False,
        webui_runtime_surface="native",
        webui_runtime_capabilities={
            "can_restart_engine": True,
            "can_pick_folder": True,
            "can_open_logs": True,
            "can_export_diagnostics": True,
        },
        health_server_enabled=False,
    )


def _run_gateway(
    config: Config,
    *,
    port: int | None = None,
    open_browser_url: str | None = None,
    webui_static_dist: bool = True,
    webui_runtime_surface: str = "browser",
    webui_runtime_capabilities: dict[str, Any] | None = None,
    health_server_enabled: bool = True,
) -> None:
    """Shared gateway runtime; ``open_browser_url`` opens a tab once channels are up."""
    from nanobot.agent.tools.cron import CronTool
    from nanobot.agent.tools.message import MessageTool
    from nanobot.bus.queue import MessageBus
    from nanobot.bus.runtime_events import RuntimeEventBus
    from nanobot.channels.manager import ChannelManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.providers.factory import build_provider_snapshot, load_provider_snapshot
    from nanobot.providers.image_generation import image_gen_provider_configs
    from nanobot.session.manager import SessionManager
    from nanobot.session.webui_turns import WebuiTurnCoordinator
    from nanobot.webui.token_usage import TokenUsageHook

    port = port if port is not None else config.gateway.port

    console.print(f"{__logo__} Starting nanobot gateway version {__version__} on port {port}...")
    sync_workspace_templates(config.workspace_path)
    bus = MessageBus()
    runtime_events = RuntimeEventBus()
    try:
        provider_snapshot = build_provider_snapshot(config)
    except ValueError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(1) from exc
    session_manager = SessionManager(config.workspace_path)

    # Preserve existing single-workspace installs, but keep custom workspaces clean.
    if is_default_workspace(config.workspace_path):
        _migrate_cron_store(config)

    # Create cron service with workspace-scoped store
    cron_store_path = config.workspace_path / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Create agent with cron service
    agent = AgentLoop.from_config(
        config, bus,
        provider=provider_snapshot.provider,
        model=provider_snapshot.model,
        context_window_tokens=provider_snapshot.context_window_tokens,
        cron_service=cron,
        session_manager=session_manager,
        image_generation_provider_configs=image_gen_provider_configs(config),
        provider_snapshot_loader=load_provider_snapshot,
        runtime_events=runtime_events,
        provider_signature=provider_snapshot.signature,
        hooks=[TokenUsageHook(timezone_name=config.agents.defaults.timezone)],
    )
    WebuiTurnCoordinator(
        bus=bus,
        sessions=session_manager,
        schedule_background=lambda coro: agent._schedule_background(coro),
    ).subscribe(runtime_events)

    from nanobot.agent.loop import UNIFIED_SESSION_KEY
    from nanobot.bus.events import OutboundMessage

    def _channel_session_key(channel: str, chat_id: str) -> str:
        return (
            UNIFIED_SESSION_KEY
            if config.agents.defaults.unified_session
            else f"{channel}:{chat_id}"
        )

    async def _deliver_to_channel(
        msg: OutboundMessage, *, record: bool = False, session_key: str | None = None,
    ) -> None:
        """Publish a user-visible message and mirror it into that channel's session."""
        metadata = dict(msg.metadata or {})
        record = record or bool(metadata.pop("_record_channel_delivery", False))
        proactive_webui_metadata = _PROACTIVE_WEBUI_METADATA.get()
        if record and msg.channel == "websocket" and proactive_webui_metadata:
            metadata = {**metadata, **proactive_webui_metadata}
        if metadata != (msg.metadata or {}):
            msg = OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                reply_to=msg.reply_to,
                media=msg.media,
                metadata=metadata,
                buttons=msg.buttons,
            )
        if (
            record
            and msg.channel != "cli"
            and msg.content.strip()
            and hasattr(session_manager, "get_or_create")
            and hasattr(session_manager, "save")
        ):
            key = session_key or _channel_session_key(msg.channel, msg.chat_id)
            session = session_manager.get_or_create(key)
            extra: dict[str, Any] = {"_channel_delivery": True}
            if msg.media:
                extra["media"] = list(msg.media)
            session.add_message("assistant", msg.content, **extra)
            session_manager.save(session)
        await bus.publish_outbound(msg)

    message_tool = getattr(agent, "tools", {}).get("message")
    if isinstance(message_tool, MessageTool):
        message_tool.set_send_callback(_deliver_to_channel)

    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        async def _silent(*_args, **_kwargs):
            pass

        # Dream is an internal job — run directly, not through the agent loop.
        if job.name == "dream":
            from nanobot.agent.memory import MemoryStore

            dream_session_key = MemoryStore.dream_session_key
            build_dream_commit_message = MemoryStore.build_dream_commit_message
            prune_dream_sessions = MemoryStore.prune_dream_sessions

            store = agent.context.memory
            resp = None
            try:
                result = store.build_dream_prompt()
                if result is None:
                    logger.info("Dream: nothing to process")
                    return None
                prompt, last_cursor = result
                key = dream_session_key()
                resp = await agent.process_direct(
                    prompt,
                    session_key=key,
                    ephemeral=True,
                    tools=store.build_dream_tools(),
                    on_progress=_silent,
                )
                if MemoryStore.dream_run_completed(resp):
                    store.set_last_dream_cursor(last_cursor)
                    try:
                        from nanobot.evolve.proposals import maybe_create_dream_proposal

                        maybe_create_dream_proposal(
                            agent,
                            completed=True,
                            processed_entries=last_cursor,
                        )
                    except Exception:
                        logger.exception("Dream evolution proposal creation failed")
                    logger.info("Dream cron job completed, cursor advanced to {}", last_cursor)
                else:
                    logger.warning(
                        "Dream cron job did not complete; cursor remains at {}",
                        store.get_last_dream_cursor(),
                    )
            except Exception:
                logger.exception("Dream cron job failed")
            finally:
                from nanobot.webui.token_usage import record_response_token_usage

                record_response_token_usage(
                    resp,
                    source="dream",
                    timezone_name=config.agents.defaults.timezone,
                )
                if store.git.is_initialized():
                    msg = build_dream_commit_message(
                        "dream: periodic memory consolidation", resp,
                    )
                    sha = store.git.auto_commit(msg)
                    if sha:
                        logger.info("Dream commit: {}", sha)
                store.compact_history()
                prune_dream_sessions(agent.sessions.sessions_dir)
            return None

        # Heartbeat is a system job that checks HEARTBEAT.md for active tasks.
        if job.name == "heartbeat":
            heartbeat_file = config.workspace_path / "HEARTBEAT.md"
            try:
                content = heartbeat_file.read_text(encoding="utf-8")
            except OSError:
                logger.debug("Heartbeat: HEARTBEAT.md missing")
                return None
            if not _heartbeat_has_active_tasks(content):
                logger.debug("Heartbeat: HEARTBEAT.md has no active tasks")
                return None

            channel, chat_id = _pick_heartbeat_target()
            if channel == "cli":
                return None

            prompt = (
                _HEARTBEAT_PREAMBLE
                + f"Review the following HEARTBEAT.md and report any active tasks:\n\n{content}"
            )

            # Internal check: funnel all output through the post-run gate so the
            # turn can't deliver directly via the message tool and skip it.
            suppress_token = None
            if isinstance(message_tool, MessageTool):
                suppress_token = message_tool.set_suppress_delivery(True)
            try:
                resp = await agent.process_direct(
                    prompt,
                    session_key="heartbeat",
                    channel=channel,
                    chat_id=chat_id,
                    on_progress=_silent,
                )
            finally:
                if isinstance(message_tool, MessageTool) and suppress_token is not None:
                    message_tool.reset_suppress_delivery(suppress_token)
            response = resp.content if resp else ""

            # Keep a small tail of heartbeat history so the loop stays bounded.
            session = agent.sessions.get_or_create("heartbeat")
            session.retain_recent_legal_suffix(hb_cfg.keep_recent_messages)
            agent.sessions.save(session)

            if not response:
                return None

            # Fail closed: stay silent on evaluator failure instead of notifying.
            should_notify = await evaluate_response(
                response, prompt, agent.provider, agent.model,
                default_notify=False,
            )
            if should_notify:
                logger.info("Heartbeat: completed, delivering response")
                await _deliver_to_channel(
                    OutboundMessage(channel=channel, chat_id=chat_id, content=response),
                    record=True,
                )
            else:
                logger.info("Heartbeat: silenced by post-run evaluation")
            return response

        reminder_note = (
            "The scheduled time has arrived. Deliver this reminder to the user now, "
            "as a brief and natural message in their language. Speak directly to them — "
            "do not narrate progress, summarize, include user IDs, or add status reports "
            "like 'Done' or 'Reminded'.\n\n"
            f"Reminder: {job.payload.message}"
        )

        cron_tool = agent.tools.get("cron")
        cron_token = None
        if isinstance(cron_tool, CronTool):
            cron_token = cron_tool.set_cron_context(True)

        message_record_token = None
        if isinstance(message_tool, MessageTool):
            message_record_token = message_tool.set_record_channel_delivery(True)

        proactive_webui_metadata = _proactive_delivery_metadata(
            "websocket",
            None,
            turn_seed=f"cron:{job.id}",
            source_label=job.name,
        )
        proactive_token = _PROACTIVE_WEBUI_METADATA.set(proactive_webui_metadata)

        try:
            resp = await agent.process_direct(
                reminder_note,
                session_key=f"cron:{job.id}",
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to or "direct",
                on_progress=_silent,
            )
        finally:
            _PROACTIVE_WEBUI_METADATA.reset(proactive_token)
            if isinstance(cron_tool, CronTool) and cron_token is not None:
                cron_tool.reset_cron_context(cron_token)
            if isinstance(message_tool, MessageTool) and message_record_token is not None:
                message_tool.reset_record_channel_delivery(message_record_token)

        response = resp.content if resp else ""

        if job.payload.deliver and isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return response

        if job.payload.deliver and job.payload.to and response:
            should_notify = await evaluate_response(
                response, reminder_note, agent.provider, agent.model,
            )
            if should_notify:
                proactive_metadata = _proactive_delivery_metadata(
                    job.payload.channel or "cli",
                    job.payload.channel_meta,
                    turn_seed=f"cron:{job.id}",
                    source_label=job.name,
                )
                await _deliver_to_channel(
                    OutboundMessage(
                        channel=job.payload.channel or "cli",
                        chat_id=job.payload.to,
                        content=response,
                        metadata=proactive_metadata,
                    ),
                    record=True,
                    session_key=job.payload.session_key,
                )
        return response

    cron.on_job = on_cron_job

    def _webui_runtime_model_name() -> str | None:
        model = getattr(agent, "model", None)
        if isinstance(model, str):
            stripped = model.strip()
            return stripped or None
        return None

    # Create channel manager (forwards SessionManager so the WebSocket channel
    # can serve the embedded webui's REST surface).
    channels = ChannelManager(
        config,
        bus,
        session_manager=session_manager,
        cron_service=cron,
        webui_runtime_model_name=_webui_runtime_model_name,
        webui_static_dist=webui_static_dist,
        webui_runtime_surface=webui_runtime_surface,
        webui_runtime_capabilities=webui_runtime_capabilities,
    )

    def _pick_heartbeat_target() -> tuple[str, str]:
        """Pick a routable channel/chat target for heartbeat-triggered messages."""
        enabled = set(channels.enabled_channels)
        for item in session_manager.list_sessions():
            key = item.get("key") or ""
            if ":" not in key:
                continue
            channel, chat_id = key.split(":", 1)
            if channel in {"cli", "system"}:
                continue
            if channel in enabled and chat_id:
                return channel, chat_id
        return "cli", "direct"

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")

    hb_cfg = config.gateway.heartbeat
    if hb_cfg.enabled:
        console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")
    else:
        console.print("[yellow]✗[/yellow] Heartbeat: disabled")

    async def _health_server(host: str, health_port: int):
        """Lightweight HTTP health endpoint on the gateway port."""
        import json as _json

        async def handle(reader, writer):
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=5)
            except (asyncio.TimeoutError, ConnectionError):
                writer.close()
                return

            request_line = data.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
            method, path = "", ""
            parts = request_line.split(" ")
            if len(parts) >= 2:
                method, path = parts[0], parts[1]

            if method == "GET" and path == "/health":
                body = _json.dumps({"status": "ok"})
                resp = (
                    f"HTTP/1.0 200 OK\r\n"
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n{body}"
                )
            else:
                body = "Not Found"
                resp = (
                    f"HTTP/1.0 404 Not Found\r\n"
                    f"Content-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    f"\r\n{body}"
                )

            writer.write(resp.encode())
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, host, health_port)
        console.print(f"[green]✓[/green] Health endpoint: http://{host}:{health_port}/health")
        async with server:
            await server.serve_forever()
    # Register Dream system job (idempotent on restart)
    from nanobot.cron.types import CronPayload, CronSchedule
    dream_cfg = config.agents.defaults.dream
    if dream_cfg.enabled:
        cron.register_system_job(CronJob(
            id="dream",
            name="dream",
            schedule=dream_cfg.build_schedule(config.agents.defaults.timezone),
            payload=CronPayload(kind="system_event"),
        ))
        console.print(f"[green]✓[/green] Dream: {dream_cfg.describe_schedule()}")
    else:
        console.print("[yellow]○[/yellow] Dream: disabled")

    # Register Heartbeat system job (idempotent on restart)
    if hb_cfg.enabled:
        cron.register_system_job(CronJob(
            id="heartbeat",
            name="heartbeat",
            schedule=CronSchedule(
                kind="every",
                every_ms=hb_cfg.interval_s * 1000,
                tz=config.agents.defaults.timezone,
            ),
            payload=CronPayload(kind="system_event"),
        ))

    async def _open_browser_when_ready() -> None:
        """Wait for the gateway to bind, then point the user's browser at the webui."""
        if not open_browser_url:
            return
        import webbrowser
        # Channels start asynchronously; a short poll lets us avoid racing the bind.
        for _ in range(40):  # ~4s max
            try:
                reader, writer = await asyncio.open_connection(
                    config.gateway.host or "127.0.0.1", port
                )
                writer.close()
                with suppress(Exception):
                    await writer.wait_closed()
                break
            except OSError:
                await asyncio.sleep(0.1)
        try:
            webbrowser.open(open_browser_url)
            console.print(f"[green]✓[/green] Opened browser at {open_browser_url}")
        except Exception as e:
            console.print(f"[yellow]Could not open browser ({e}); visit {open_browser_url}[/yellow]")

    async def run():
        try:
            await cron.start()
            tasks = [
                agent.run(),
                channels.start_all(),
            ]
            if health_server_enabled:
                tasks.append(_health_server(config.gateway.host, port))
            if open_browser_url:
                tasks.append(_open_browser_when_ready())
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        except Exception:
            import traceback

            console.print("\n[red]Error: Gateway crashed unexpectedly[/red]")
            console.print(traceback.format_exc())
        finally:
            await agent.close_mcp()
            cron.stop()
            agent.stop()
            await channels.stop_all()
            # Flush all cached sessions to durable storage before exit.
            # This prevents data loss on filesystems with write-back
            # caching (rclone VFS, NFS, FUSE mounts, etc.).
            flushed = agent.sessions.flush_all()
            if flushed:
                logger.info("Shutdown: flushed {} session(s) to disk", flushed)

    asyncio.run(run())




def register_gateway_commands(app: typer.Typer) -> None:
    """Register gateway-related commands on the root Typer app."""
    app.command()(serve)
    app.command()(gateway)
    app.command("desktop-gateway", hidden=True)(desktop_gateway)
