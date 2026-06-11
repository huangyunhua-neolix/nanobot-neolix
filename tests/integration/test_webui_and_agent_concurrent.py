"""Spec §4.3 + §7 (M1 Task E3): with one agent process actively bumping/flushing
telemetry, concurrent WebUI calls (telemetry=None) must:
  (a) never modify the .telemetry.json file
  (b) never crash on partially-written intermediate state
  (c) never block the agent's bump/flush cycle
"""

from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path


def _agent_worker(workspace_str: str, iterations: int) -> None:
    """Top-level so it survives `spawn` start-method serialization."""
    from pathlib import Path as P

    from nanobot.agent.skills_telemetry import SkillTelemetry

    workspace = P(workspace_str)
    telemetry = SkillTelemetry(workspace=workspace)
    # Match real AgentLoop startup: reconcile-before-first-bump so the `alpha`
    # entry is created on disk by the legitimate entry-creator path. Per spec
    # §4.4 invariant 3, `bump` (the default writer) never resurrects unknown
    # entries — only `reconcile` does. Without this seed, the bumps below
    # would be silently skipped in `_rmw_merge` and `.telemetry.json` would
    # end up with `entries: {}`.
    telemetry.reconcile([{
        "name": "alpha",
        "effective_origin": "user",
        "shadowed_origins": [],
        "path": str(workspace / "skills" / "alpha" / "SKILL.md"),
    }])
    for i in range(iterations):
        telemetry.bump("alpha", "view")
        if i % 25 == 0:
            telemetry.flush()
    telemetry.flush()


def _webui_worker(workspace_str: str, iterations: int, results_path: str) -> None:
    from pathlib import Path as P

    from nanobot.webui.skills_api import webui_skill_detail_payload, webui_skills_payload

    workspace = P(workspace_str)
    crashes = 0
    for _ in range(iterations):
        try:
            webui_skills_payload(workspace)
            webui_skill_detail_payload(workspace, "alpha")
        except Exception:
            crashes += 1
    P(results_path).write_text(str(crashes))


def test_webui_calls_do_not_modify_telemetry_file_under_active_agent(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "skills" / "alpha").mkdir(parents=True)
    (workspace / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")

    ctx = mp.get_context("spawn")
    results_path = tmp_path / "webui_crashes.txt"

    agent_proc = ctx.Process(target=_agent_worker, args=(str(workspace), 500))
    webui_proc = ctx.Process(
        target=_webui_worker, args=(str(workspace), 200, str(results_path))
    )

    agent_proc.start()
    # Give the agent a head start to ensure .telemetry.json exists.
    time.sleep(0.05)
    webui_proc.start()

    agent_proc.join(timeout=60)
    webui_proc.join(timeout=60)
    assert agent_proc.exitcode == 0, f"agent crashed: exitcode={agent_proc.exitcode}"
    assert webui_proc.exitcode == 0, f"webui crashed: exitcode={webui_proc.exitcode}"

    crashes = int(results_path.read_text())
    assert crashes == 0, f"{crashes} WebUI calls crashed on partial state"

    payload = json.loads((workspace / "skills" / ".telemetry.json").read_text())
    # Only the agent should have written counters; WebUI must not alter them.
    alpha = payload["entries"]["alpha"]
    assert alpha["views"] >= 500, (
        f"agent's bumps must be preserved; got {alpha['views']}"
    )
