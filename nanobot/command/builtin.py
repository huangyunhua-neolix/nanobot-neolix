"""Built-in slash command handlers."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import suppress
from dataclasses import dataclass

from nanobot import __version__
from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext, CommandRouter
from nanobot.utils.helpers import build_status_content
from nanobot.utils.restart import set_restart_notice_to_env

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BuiltinCommandSpec:
    command: str
    title: str
    description: str
    icon: str
    arg_hint: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "command": self.command,
            "title": self.title,
            "description": self.description,
            "icon": self.icon,
            "arg_hint": self.arg_hint,
        }


BUILTIN_COMMAND_SPECS: tuple[BuiltinCommandSpec, ...] = (
    BuiltinCommandSpec(
        "/new",
        "New chat",
        "Stop the current task and start a fresh conversation.",
        "square-pen",
    ),
    BuiltinCommandSpec(
        "/stop",
        "Stop current task",
        "Cancel the active agent turn for this chat.",
        "square",
    ),
    BuiltinCommandSpec(
        "/restart",
        "Restart nanobot",
        "Restart the bot process in place.",
        "rotate-cw",
    ),
    BuiltinCommandSpec(
        "/status",
        "Show status",
        "Display runtime, provider, and channel status.",
        "activity",
    ),
    BuiltinCommandSpec(
        "/model",
        "Switch model preset",
        "Show or switch the active model preset.",
        "brain",
        "[preset]",
    ),
    BuiltinCommandSpec(
        "/history",
        "Show conversation history",
        "Print the last N persisted conversation messages.",
        "history",
        "[n]",
    ),
    BuiltinCommandSpec(
        "/goal",
        "Start long-running goal",
        "Tell the agent to treat the request as a long-running goal.",
        "activity",
        "<goal>",
    ),
    BuiltinCommandSpec(
        "/dream",
        "Run Dream",
        "Manually trigger memory consolidation.",
        "sparkles",
    ),
    BuiltinCommandSpec(
        "/dream-log",
        "Show Dream log",
        "Show what the last Dream consolidation changed.",
        "book-open",
    ),
    BuiltinCommandSpec(
        "/dream-restore",
        "Restore memory",
        "Revert memory to a previous Dream snapshot.",
        "undo-2",
    ),
    BuiltinCommandSpec(
        "/skill",
        "List skills",
        "List all enabled skills available to the agent.",
        "wrench",
    ),
    BuiltinCommandSpec(
        "/help",
        "Show help",
        "List available slash commands.",
        "circle-help",
    ),
    BuiltinCommandSpec(
        "/pairing",
        "Manage pairing",
        "List, approve, deny or revoke pairing requests.",
        "shield",
        "[list|approve <code>|deny <code>|revoke <user_id>]",
    ),
    BuiltinCommandSpec(
        "/curator",
        "Review skills",
        "Review skill telemetry and propose safe cleanup actions.",
        "scissors",
        "[--dry-run|--apply] [--json] [--include-protected]",
    ),
    BuiltinCommandSpec(
        "/evolve",
        "Evolve proposals",
        "Create, inspect, and run offline evolution proposals.",
        "git-pull-request",
        "[list|create <skill> <rationale>|show <id>|run <id>]",
    ),
)


def builtin_command_palette() -> list[dict[str, str]]:
    """Return structured command metadata for UI command palettes."""
    return [spec.as_dict() for spec in BUILTIN_COMMAND_SPECS]


async def cmd_stop(ctx: CommandContext) -> OutboundMessage:
    """Cancel all active tasks and subagents for the session."""
    loop = ctx.loop
    msg = ctx.msg
    total = await loop._cancel_active_tasks(ctx.key)
    content = f"Stopped {total} task(s)." if total else "No active task to stop."
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content=content,
        metadata=dict(msg.metadata or {})
    )


async def cmd_restart(ctx: CommandContext) -> OutboundMessage:
    """Restart the process in-place via os.execv."""
    msg = ctx.msg
    set_restart_notice_to_env(
        channel=msg.channel,
        chat_id=msg.chat_id,
        metadata=dict(msg.metadata or {}),
    )

    async def _do_restart():
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable, "-m", "nanobot"] + sys.argv[1:])

    asyncio.create_task(_do_restart())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Restarting...",
        metadata=dict(msg.metadata or {})
    )


async def cmd_status(ctx: CommandContext) -> OutboundMessage:
    """Build an outbound status message for a session."""
    loop = ctx.loop
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    ctx_est = 0
    with suppress(Exception):
        ctx_est, _ = loop.consolidator.estimate_session_prompt_tokens(session)
    if ctx_est <= 0:
        ctx_est = loop._last_usage.get("prompt_tokens", 0)

    # Fetch web search provider usage (best-effort, never blocks the response)
    search_usage_text: str | None = None
    # Never let usage fetch break /status
    with suppress(Exception):
        from nanobot.utils.searchusage import fetch_search_usage
        web_cfg = getattr(loop, "web_config", None)
        search_cfg = getattr(web_cfg, "search", None) if web_cfg else None
        if search_cfg is not None:
            provider = getattr(search_cfg, "provider", "duckduckgo")
            api_key = getattr(search_cfg, "api_key", "") or None
            usage = await fetch_search_usage(provider=provider, api_key=api_key)
            search_usage_text = usage.format()
    active_tasks = loop._active_tasks.get(ctx.key, [])
    task_count = sum(1 for t in active_tasks if not t.done())
    with suppress(Exception):
        task_count += loop.subagents.get_running_count_by_session(ctx.key)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_status_content(
            version=__version__, model=loop.model,
            start_time=loop._start_time, last_usage=loop._last_usage,
            context_window_tokens=loop.context_window_tokens,
            session_msg_count=len(session.get_history(max_messages=0)),
            context_tokens_estimate=ctx_est,
            search_usage_text=search_usage_text,
            active_task_count=task_count,
            max_completion_tokens=getattr(
                getattr(loop.provider, "generation", None), "max_tokens", 8192
            ),
        ),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


async def cmd_new(ctx: CommandContext) -> OutboundMessage:
    """Stop active task and start a fresh session."""
    loop = ctx.loop
    await loop._cancel_active_tasks(ctx.key)
    session = ctx.session or loop.sessions.get_or_create(ctx.key)
    snapshot = session.messages[session.last_consolidated:]
    session.clear()
    loop.sessions.save(session)
    loop.sessions.invalidate(session.key)
    if snapshot:
        loop._schedule_background(loop.consolidator.archive(snapshot, session_key=ctx.key))
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content="New session started.",
        metadata=dict(ctx.msg.metadata or {})
    )


def _format_preset_names(names: list[str]) -> str:
    return ", ".join(f"`{name}`" for name in names) if names else "(none configured)"


def _model_preset_names(loop) -> list[str]:
    names = set(loop.model_presets)
    names.add("default")
    return ["default", *sorted(name for name in names if name != "default")]


def _active_model_preset_name(loop) -> str:
    return loop.model_preset or "default"


def _command_error_message(exc: Exception) -> str:
    return str(exc.args[0]) if isinstance(exc, KeyError) and exc.args else str(exc)


def _model_command_status(loop) -> str:
    names = _model_preset_names(loop)
    active = _active_model_preset_name(loop)
    return "\n".join([
        "## Model",
        f"- Current model: `{loop.model}`",
        f"- Current preset: `{active}`",
        f"- Available presets: {_format_preset_names(names)}",
    ])


async def cmd_model(ctx: CommandContext) -> OutboundMessage:
    """Show or switch model presets."""
    loop = ctx.loop
    args = ctx.args.strip()
    metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}

    if not args:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=_model_command_status(loop),
            metadata=metadata,
        )

    parts = args.split()
    if len(parts) != 1:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: `/model [preset]`",
            metadata=metadata,
        )

    name = parts[0]
    try:
        loop.set_model_preset(name)
    except (KeyError, ValueError) as exc:
        names = _model_preset_names(loop)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                f"Could not switch model preset: {_command_error_message(exc)}\n\n"
                f"Available presets: {_format_preset_names(names)}"
            ),
            metadata=metadata,
        )

    max_tokens = getattr(getattr(loop.provider, "generation", None), "max_tokens", None)
    lines = [
        f"Switched model preset to `{loop.model_preset}`.",
        f"- Model: `{loop.model}`",
        f"- Context window: {loop.context_window_tokens}",
    ]
    if max_tokens is not None:
        lines.append(f"- Max output tokens: {max_tokens}")
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content="\n".join(lines),
        metadata=metadata,
    )


async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    """Manually trigger a Dream consolidation run."""
    import time

    loop = ctx.loop
    msg = ctx.msg

    async def _run_dream():
        from nanobot.agent.memory import MemoryStore

        dream_session_key = MemoryStore.dream_session_key
        build_dream_commit_message = MemoryStore.build_dream_commit_message
        prune_dream_sessions = MemoryStore.prune_dream_sessions

        store = loop.context.memory
        content = ""
        resp = None
        t0 = time.monotonic()
        try:
            result = store.build_dream_prompt()
            if result is None:
                await loop.bus.publish_outbound(OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Dream: nothing to process.",
                ))
                return
            prompt, last_cursor = result
            key = dream_session_key()
            resp = await loop.process_direct(
                prompt,
                session_key=key,
                ephemeral=True,
                tools=store.build_dream_tools(),
            )
            elapsed = time.monotonic() - t0
            if MemoryStore.dream_run_completed(resp):
                store.set_last_dream_cursor(last_cursor)
                try:
                    from nanobot.evolve.proposals import maybe_create_dream_proposal

                    maybe_create_dream_proposal(
                        loop,
                        completed=True,
                        processed_entries=last_cursor,
                    )
                except Exception:
                    logger.exception("Dream evolution proposal creation failed")
                content = f"Dream completed in {elapsed:.1f}s."
            else:
                content = (
                    f"Dream did not complete after {elapsed:.1f}s; "
                    "memory cursor was not advanced."
                )
        except Exception as e:
            elapsed = time.monotonic() - t0
            content = f"Dream failed after {elapsed:.1f}s: {e}"
        finally:
            from nanobot.webui.token_usage import record_response_token_usage

            record_response_token_usage(
                resp,
                source="dream",
                timezone_name=getattr(loop.context, "timezone", None),
            )
            if store.git.is_initialized():
                commit_msg = build_dream_commit_message("dream: manual run", resp)
                sha = store.git.auto_commit(commit_msg)
                if sha:
                    content += f" (commit {sha})"
            store.compact_history()
            prune_dream_sessions(loop.sessions.sessions_dir)
        await loop.bus.publish_outbound(OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=content,
        ))

    asyncio.create_task(_run_dream())
    return OutboundMessage(
        channel=msg.channel, chat_id=msg.chat_id, content="Dreaming...",
    )


def _extract_changed_files(diff: str) -> list[str]:
    """Extract changed file paths from a unified diff."""
    files: list[str] = []
    seen: set[str] = set()
    for line in diff.splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        path = parts[3]
        if path.startswith("b/"):
            path = path[2:]
        if path in seen:
            continue
        seen.add(path)
        files.append(path)
    return files


def _format_changed_files(diff: str) -> str:
    files = _extract_changed_files(diff)
    if not files:
        return "No tracked memory files changed."
    return ", ".join(f"`{path}`" for path in files)


def _format_dream_log_content(commit, diff: str, *, requested_sha: str | None = None) -> str:
    files_line = _format_changed_files(diff)
    lines = [
        "## Dream Update",
        "",
        "Here is the selected Dream memory change." if requested_sha else "Here is the latest Dream memory change.",
        "",
        f"- Commit: `{commit.sha}`",
        f"- Time: {commit.timestamp}",
        f"- Changed files: {files_line}",
    ]
    if diff:
        lines.extend([
            "",
            f"Use `/dream-restore {commit.sha}` to undo this change.",
            "",
            "```diff",
            diff.rstrip(),
            "```",
        ])
    else:
        lines.extend([
            "",
            "Dream recorded this version, but there is no file diff to display.",
        ])
    return "\n".join(lines)


def _format_dream_restore_list(commits: list) -> str:
    lines = [
        "## Dream Restore",
        "",
        "Choose a Dream memory version to restore. Latest first:",
        "",
    ]
    for c in commits:
        lines.append(f"- `{c.sha}` {c.timestamp} - {c.message.splitlines()[0]}")
    lines.extend([
        "",
        "Preview a version with `/dream-log <sha>` before restoring it.",
        "Restore a version with `/dream-restore <sha>`.",
    ])
    return "\n".join(lines)


async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    """Show what the last Dream changed.

    Default: diff of the latest commit (HEAD~1 vs HEAD).
    With /dream-log <sha>: diff of that specific commit.
    """
    store = ctx.loop.consolidator.store
    git = store.git

    if not git.is_initialized():
        if store.get_last_dream_cursor() == 0:
            msg = "Dream has not run yet. Run `/dream`, or wait for the next scheduled Dream cycle."
        else:
            msg = "Dream history is not available because memory versioning is not initialized."
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content=msg, metadata={"render_as": "text"},
        )

    args = ctx.args.strip()

    if args:
        # Show diff of a specific commit
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        if not result:
            content = (
                f"Couldn't find Dream change `{sha}`.\n\n"
                "Use `/dream-restore` to list recent versions, "
                "or `/dream-log` to inspect the latest one."
            )
        else:
            commit, diff = result
            content = _format_dream_log_content(commit, diff, requested_sha=sha)
    else:
        # Default: show the latest commit's diff
        commits = git.log(max_entries=1)
        result = git.show_commit_diff(commits[0].sha) if commits else None
        if result:
            commit, diff = result
            content = _format_dream_log_content(commit, diff)
        else:
            content = "Dream memory has no saved versions yet."

    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    """Restore memory files from a previous dream commit.

    Usage:
        /dream-restore          — list recent commits
        /dream-restore <sha>    — revert a specific commit
    """
    store = ctx.loop.consolidator.store
    git = store.git
    if not git.is_initialized():
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="Dream history is not available because memory versioning is not initialized.",
        )

    args = ctx.args.strip()
    if not args:
        # Show recent commits for the user to pick
        commits = git.log(max_entries=10)
        if not commits:
            content = "Dream memory has no saved versions to restore yet."
        else:
            content = _format_dream_restore_list(commits)
    else:
        sha = args.split()[0]
        result = git.show_commit_diff(sha)
        changed_files = _format_changed_files(result[1]) if result else "the tracked memory files"
        new_sha = git.revert(sha)
        if new_sha:
            content = (
                f"Restored Dream memory to the state before `{sha}`.\n\n"
                f"- New safety commit: `{new_sha}`\n"
                f"- Restored files: {changed_files}\n\n"
                f"Use `/dream-log {new_sha}` to inspect the restore diff."
            )
        else:
            content = (
                f"Couldn't restore Dream change `{sha}`.\n\n"
                "It may not exist, or it may be the first saved version with no earlier state to restore."
            )
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=content, metadata={"render_as": "text"},
    )


_HISTORY_DEFAULT_COUNT = 10
_HISTORY_MAX_COUNT = 50
_HISTORY_MAX_CONTENT_CHARS = 200


def _format_history_message(msg: dict) -> str | None:
    """Format a single history message for display. Returns None to skip."""
    role = msg.get("role")
    if role not in ("user", "assistant"):
        return None
    content = msg.get("content") or ""
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        content = " ".join(parts)
    content = str(content).strip()
    if not content:
        return None
    if len(content) > _HISTORY_MAX_CONTENT_CHARS:
        content = content[:_HISTORY_MAX_CONTENT_CHARS] + "…"
    label = "👤 You" if role == "user" else "🤖 Bot"
    return f"{label}: {content}"


async def cmd_history(ctx: CommandContext) -> OutboundMessage:
    """Show the last N messages of the current session (default 10, max 50).

    Usage: /history [count]
    """
    count = _HISTORY_DEFAULT_COUNT
    if ctx.args.strip():
        try:
            count = max(1, min(int(ctx.args.strip()), _HISTORY_MAX_COUNT))
        except ValueError:
            return OutboundMessage(
                channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
                content="Usage: /history [count] — e.g. /history 5 (default: 10, max: 50)",
                metadata=dict(ctx.msg.metadata or {}),
            )

    session = ctx.session or ctx.loop.sessions.get_or_create(ctx.key)
    history = session.get_history(max_messages=0)
    visible = [_format_history_message(m) for m in history]
    visible = [m for m in visible if m is not None]
    recent = visible[-count:]

    if not recent:
        return OutboundMessage(
            channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
            content="No conversation history yet.",
            metadata=dict(ctx.msg.metadata or {}),
        )

    header = f"Last {len(recent)} message(s):\n"
    return OutboundMessage(
        channel=ctx.msg.channel, chat_id=ctx.msg.chat_id,
        content=header + "\n".join(recent),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


_GOAL_PROMPT_TEMPLATE = """The user declared a sustained objective for this thread.

Inspect or clarify if needed, then call `long_task` with the refined objective (and optional short ui_summary). Work proceeds as normal assistant turns using your usual tools. When the objective is fully done and verified, call `complete_goal` with a brief recap. If the user later cancels or changes direction, still call `complete_goal` with an honest recap (then `long_task` again only after there is no active goal). Do not use `long_task` / `complete_goal` for trivial one-shot answers.

Goal:
{goal}
"""


async def cmd_goal(ctx: CommandContext) -> OutboundMessage | None:
    """Rewrite /goal into a normal agent turn that nudges long_task use."""
    goal = ctx.args.strip()
    if not goal:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Usage: /goal <long-running task description>",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )
    if ctx.session is None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=(
                "A task is already running for this chat. "
                "Use `/stop` first, then send `/goal <long-running task description>` again."
            ),
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    ctx.msg.metadata = {
        **dict(ctx.msg.metadata or {}),
        "original_command": "/goal",
        "original_content": ctx.raw,
        "goal_started_at": time.time(),
    }
    ctx.msg.content = _GOAL_PROMPT_TEMPLATE.format(goal=goal)
    return None


async def cmd_pairing(ctx: CommandContext) -> OutboundMessage:
    """List, approve, deny or revoke pairing requests."""
    from nanobot.pairing import PAIRING_COMMAND_META_KEY, handle_pairing_command

    reply = handle_pairing_command(ctx.msg.channel, ctx.args)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=reply,
        metadata={PAIRING_COMMAND_META_KEY: True},
    )


async def cmd_skill(ctx: CommandContext) -> OutboundMessage:
    """List all enabled skills (name and description only)."""
    loop = ctx.loop
    skills = loop.context.skills.list_skills(filter_unavailable=False)
    if not skills:
        content = "No skills available."
    else:
        lines = [f"Available skills ({len(skills)}):", ""]
        for entry in skills:
            desc = loop.context.skills._get_skill_description(entry["name"])
            lines.append(f"- **{entry['name']}** — {desc}")
        content = "\n".join(lines)
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata=dict(ctx.msg.metadata or {}),
    )

_CURATOR_USAGE = (
    "Usage: `/curator [--dry-run|--apply] [--json] [--include-protected] "
    "[--evolve-proposals]`\n"
    "  --dry-run           Analyse skills without making changes (default)\n"
    "  --apply             Apply safe deletions (respects forced-dry-run window)\n"
    "  --json              Output machine-readable JSON wrapped in a fenced block\n"
    "  --include-protected Include PROTECT/KEEP proposals in output\n"
    "  --evolve-proposals  Create offline evolution proposals for patch/merge candidates"
)


def _parse_curator_args(raw_args: str) -> tuple[bool, bool, bool, bool, str | None]:
    """Parse /curator flag string.

    Returns:
        (apply, include_protected, as_json, evolve_proposals, error_msg)
        error_msg is None when parsing succeeds.
    """
    apply = False
    dry_run_explicit = False
    include_protected = False
    as_json = False
    evolve_proposals = False

    for token in raw_args.split():
        if token == "--apply":
            apply = True
        elif token == "--dry-run":
            dry_run_explicit = True
        elif token == "--include-protected":
            include_protected = True
        elif token == "--json":
            as_json = True
        elif token == "--evolve-proposals":
            evolve_proposals = True
        else:
            return False, False, False, False, f"unknown flag: {token}"

    if apply and dry_run_explicit:
        return False, False, False, False, "--dry-run and --apply are mutually exclusive"

    return apply, include_protected, as_json, evolve_proposals, None


async def cmd_curator(ctx: CommandContext) -> OutboundMessage:
    """Review skill telemetry and propose safe cleanup actions."""
    from nanobot.config.schema import CuratorConfig
    from nanobot.curator.report import format_text_report
    from nanobot.curator.service import CuratorService

    loop = ctx.loop
    args = ctx.args.strip()

    apply, include_protected, as_json, evolve_proposals, error = _parse_curator_args(args)
    if error is not None:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=f"{error}\n\n{_CURATOR_USAGE}",
            metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
        )

    # Resolve config: use loop.curator_config if present (set in tests / advanced wiring),
    # otherwise fall back to a default CuratorConfig.
    curator_config: CuratorConfig = getattr(loop, "curator_config", None) or CuratorConfig()

    service = CuratorService(
        workspace=str(loop.workspace),
        skills=loop.context.skills,
        telemetry=loop.telemetry,
        config=curator_config,
    )

    report = service.run(apply=apply, include_protected=include_protected)

    created_evolution_proposals = []
    if evolve_proposals:
        from nanobot.config.schema import EvolutionConfig
        from nanobot.evolve.proposals import ProposalStore, proposals_from_curator

        evolution_config = getattr(loop, "evolution_config", None) or EvolutionConfig()
        if evolution_config.enabled and "curator" in evolution_config.proposal_triggers:
            store = ProposalStore(evolution_config.resolve_workspace(loop.workspace))
            created_evolution_proposals = proposals_from_curator(store, report.proposals)

    if as_json:
        import json

        payload = report.model_dump(mode="json")
        if evolve_proposals:
            payload["evolutionProposalsCreated"] = [
                proposal.proposal_id for proposal in created_evolution_proposals
            ]
        raw_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        content = f"```json\n{raw_json}```"
        metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}
    else:
        forced_until = service.resolve_forced_dry_run_until()
        content = format_text_report(report, forced_until=forced_until)
        metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}

        if evolve_proposals:
            proposal_lines = [
                content,
                "",
                f"Evolution proposals created: {len(created_evolution_proposals)}",
            ]
            proposal_lines.extend(
                f"- `{proposal.proposal_id}`" for proposal in created_evolution_proposals
            )
            content = "\n".join(proposal_lines)

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=content,
        metadata=metadata,
    )


_EVOLVE_USAGE = (
    "Usage: `/evolve [list|create <skill> <rationale>|show <id>|run <id>]`\n"
    "  list                       List evolution proposals\n"
    "  create <skill> <rationale> Create a manual proposal\n"
    "  show <id>                  Show proposal details\n"
    "  run <id>                   Run proposal locally through offline harness"
)


def _evolve_sender_allowed(ctx: CommandContext) -> bool:
    if ctx.msg.channel in {"cli", "websocket"} or ctx.msg.metadata.get("webui") is True:
        return True

    sender_id = str(ctx.msg.sender_id)
    channels_config = getattr(ctx.loop, "channels_config", None)
    channel_config = getattr(channels_config, ctx.msg.channel, None) if channels_config is not None else None
    if isinstance(channel_config, dict):
        allow_list = channel_config.get("allow_from") or channel_config.get("allowFrom") or []
    else:
        allow_list = getattr(channel_config, "allow_from", None) or []
    if "*" in allow_list or sender_id in allow_list:
        return True
    if sender_id.count("|") == 1:
        sid, username = sender_id.split("|", 1)
        if sid in allow_list or username in allow_list:
            return True

    from nanobot.pairing import is_approved

    return is_approved(ctx.msg.channel, sender_id)


async def cmd_evolve(ctx: CommandContext) -> OutboundMessage:
    """Create, inspect, and run offline evolution proposals."""
    from nanobot.config.schema import EvolutionConfig
    from nanobot.evolve.proposals import (
        ProposalRunner,
        ProposalStore,
        create_manual_proposal,
        format_proposal_list,
        format_proposal_show,
        format_run_result,
    )

    loop = ctx.loop
    config = getattr(loop, "evolution_config", None) or EvolutionConfig()
    metadata = {**dict(ctx.msg.metadata or {}), "render_as": "text"}

    if not config.enabled:
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content="Runtime evolution proposals are disabled by config.",
            metadata=metadata,
        )

    store = ProposalStore(config.resolve_workspace(loop.workspace))
    parts = ctx.args.strip().split(maxsplit=2)
    action = parts[0] if parts else "list"

    if action == "list":
        content = format_proposal_list(store.list())
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=metadata,
        )

    if action == "show" and len(parts) >= 2:
        try:
            content = format_proposal_show(store.get(parts[1]))
        except (FileNotFoundError, ValueError) as exc:
            content = str(exc)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=metadata,
        )

    if action == "create" and len(parts) >= 3:
        if not _evolve_sender_allowed(ctx):
            content = "Evolution proposal creation requires an approved sender."
        elif "manual" not in config.proposal_triggers:
            content = "Manual evolution proposals are disabled by config."
        else:
            try:
                proposal = create_manual_proposal(store, skill_name=parts[1], rationale=parts[2])
                content = format_proposal_show(proposal)
            except ValueError as exc:
                content = str(exc)
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=content,
            metadata=metadata,
        )

    if action == "run" and len(parts) >= 2:
        if not _evolve_sender_allowed(ctx):
            return OutboundMessage(
                channel=ctx.msg.channel,
                chat_id=ctx.msg.chat_id,
                content="Evolution runs require an approved sender.",
                metadata=metadata,
            )
        proposal_id = parts[1]

        async def _run_proposal() -> None:
            try:
                result = await asyncio.to_thread(
                    ProposalRunner(store).run,
                    proposal_id,
                    optimizer_command=config.resolve_optimizer_command(),
                    tiers=config.default_tier_list(),
                    max_candidates=config.max_candidates,
                    optimizer_timeout_seconds=config.optimizer_timeout_seconds,
                )
                content = format_run_result(result)
            except Exception as exc:
                from nanobot.evolve.privacy.redact import redact

                content = f"Evolution run failed: {redact(str(exc)).text}"
            await loop.bus.publish_outbound(
                OutboundMessage(
                    channel=ctx.msg.channel,
                    chat_id=ctx.msg.chat_id,
                    content=content,
                    metadata=metadata,
                )
            )

        loop._schedule_background(_run_proposal())
        return OutboundMessage(
            channel=ctx.msg.channel,
            chat_id=ctx.msg.chat_id,
            content=f"Evolution run started for `{proposal_id}`.",
            metadata=metadata,
        )

    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=_EVOLVE_USAGE,
        metadata=metadata,
    )


async def cmd_help(ctx: CommandContext) -> OutboundMessage:
    """Return available slash commands."""
    return OutboundMessage(
        channel=ctx.msg.channel,
        chat_id=ctx.msg.chat_id,
        content=build_help_text(),
        metadata={**dict(ctx.msg.metadata or {}), "render_as": "text"},
    )


def build_help_text() -> str:
    """Build canonical help text shared across channels."""
    lines = ["🐈 nanobot commands:"]
    for spec in BUILTIN_COMMAND_SPECS:
        command = spec.command
        if spec.arg_hint:
            command = f"{command} {spec.arg_hint}"
        lines.append(f"{command} — {spec.description}")
    return "\n".join(lines)


def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    router.priority("/stop", cmd_stop)
    router.priority("/restart", cmd_restart)
    router.priority("/status", cmd_status)
    router.exact("/new", cmd_new)
    router.exact("/status", cmd_status)
    router.exact("/model", cmd_model)
    router.prefix("/model ", cmd_model)
    router.exact("/history", cmd_history)
    router.prefix("/history ", cmd_history)
    router.exact("/goal", cmd_goal)
    router.prefix("/goal ", cmd_goal)
    router.exact("/dream", cmd_dream)
    router.exact("/dream-log", cmd_dream_log)
    router.prefix("/dream-log ", cmd_dream_log)
    router.exact("/dream-restore", cmd_dream_restore)
    router.prefix("/dream-restore ", cmd_dream_restore)
    router.exact("/skill", cmd_skill)
    router.exact("/help", cmd_help)
    router.exact("/pairing", cmd_pairing)
    router.prefix("/pairing ", cmd_pairing)
    router.exact("/curator", cmd_curator)
    router.prefix("/curator ", cmd_curator)
    router.exact("/evolve", cmd_evolve)
    router.prefix("/evolve ", cmd_evolve)
