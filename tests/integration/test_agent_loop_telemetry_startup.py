"""Spec §4.4 + §7: AgentLoop.run() must invoke SkillTelemetry.reconcile() AFTER
_connect_mcp() returns and BEFORE the first inbound-consume call (M1 Task E1)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_agentloop_run_orders_connect_mcp_then_reconcile_then_consume(tmp_path: Path) -> None:
    from nanobot.agent.loop import AgentLoop
    from nanobot.agent.skills_telemetry import SkillTelemetry
    from nanobot.bus.queue import MessageBus

    workspace = tmp_path
    (workspace / "skills" / "foo").mkdir(parents=True)
    (workspace / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")

    call_order: list[str] = []
    orig_reconcile = SkillTelemetry.reconcile

    def _spy_reconcile(self, *args, **kwargs):
        call_order.append("reconcile")
        return orig_reconcile(self, *args, **kwargs)

    async def _stub_connect_mcp(self):
        call_order.append("connect_mcp")

    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"

    with patch.object(SkillTelemetry, "reconcile", _spy_reconcile), \
         patch.object(AgentLoop, "_connect_mcp", _stub_connect_mcp):
        loop = AgentLoop(bus=bus, provider=provider, workspace=workspace)

        async def _consume_marker():
            call_order.append("consume")
            # Stop the loop so the CancelledError below propagates instead of
            # being swallowed by the `continue` branch.
            loop._running = False
            raise asyncio.CancelledError()

        loop.bus.consume_inbound = _consume_marker  # type: ignore[assignment]

        async def driver() -> None:
            try:
                await loop.run()
            except asyncio.CancelledError:
                pass

        asyncio.run(driver())

    assert "connect_mcp" in call_order, f"_connect_mcp was not invoked: {call_order}"
    assert "reconcile" in call_order, f"reconcile was not invoked: {call_order}"
    assert "consume" in call_order, f"bus.consume_inbound was not invoked: {call_order}"
    assert call_order.index("connect_mcp") < call_order.index("reconcile"), (
        f"reconcile must run AFTER _connect_mcp; got {call_order}"
    )
    assert call_order.index("reconcile") < call_order.index("consume"), (
        f"reconcile must run BEFORE first consume; got {call_order}"
    )
