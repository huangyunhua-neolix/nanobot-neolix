"""Runtime evolution slash command handlers."""

from __future__ import annotations

import asyncio

from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext

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
