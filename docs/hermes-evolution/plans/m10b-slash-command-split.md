# M10b-1 Slash Command Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Dream, Curator, and Evolve slash command handlers out of `nanobot/command/builtin.py` while preserving command behavior and keeping `register_builtin_commands()` as the only built-in registration entry point.

**Architecture:** Create `nanobot/command/dream_command.py` for `/dream`, `/dream-log`, and `/dream-restore`; create `nanobot/command/evolution_command.py` for `/curator` and `/evolve`. Keep metadata, help rendering, simple commands, restart/status priority commands, and router registration in `builtin.py`; import moved handlers inside `register_builtin_commands()` so `builtin.py` does not become a long-lived re-export surface.

**Tech Stack:** Python 3.11, asyncio slash command handlers, existing `CommandRouter`, existing `OutboundMessage`, pytest, ruff.

---

## Scope Check

This plan implements only M10b-1 from `docs/hermes-evolution/specs/m10b-slash-command-split.md`.

It does not split `nanobot/cli/commands.py`, change command UX, change persistence schemas, introduce discovery/plugin registration, or move `BUILTIN_COMMAND_SPECS` out of `builtin.py`.

## File Structure

### Create

- `nanobot/command/dream_command.py`
  - Owns Dream slash command handlers and Dream-only formatting helpers.
  - Depends on `CommandContext`, `OutboundMessage`, `asyncio`, and Dream/evolution domain services.
  - Defines `logger = logging.getLogger(__name__)` so Dream proposal creation failures keep command-local logging after the move.

- `nanobot/command/evolution_command.py`
  - Owns `/curator` and `/evolve` handlers plus command-local parser/authorization helpers.
  - Depends on `CommandContext`, `OutboundMessage`, `asyncio`, Curator services, proposal services, and config types.
  - Imports `asyncio` directly because `/evolve run` uses `asyncio.to_thread()`.

### Modify

- `nanobot/command/builtin.py`
  - Remove Dream handler implementations and helpers.
  - Remove Curator/Evolve handler implementations and helpers.
  - Keep metadata, help, simple commands, `/restart`, `/status`, `/pairing`, and registration.
  - Import moved handlers inside `register_builtin_commands()`.
  - Remove `logging` import and `logger` if they become unused.

- `tests/command/test_builtin_dream.py`
  - Import `cmd_dream_log` and `cmd_dream_restore` from `nanobot.command.dream_command`.

- `tests/command/test_curator_command.py`
  - Keep `BUILTIN_COMMAND_SPECS` and `register_builtin_commands` imports from `nanobot.command.builtin`.
  - Import `cmd_curator` from `nanobot.command.evolution_command`.

- `tests/command/test_evolve_command.py`
  - Keep `BUILTIN_COMMAND_SPECS` and `register_builtin_commands` imports from `nanobot.command.builtin`.
  - Import `cmd_evolve` from `nanobot.command.evolution_command`.

- `tests/command/test_router_dispatchable.py`
  - Add coverage that moved handlers are no longer public attributes on `nanobot.command.builtin`.
  - Add explicit dispatchability coverage for `/evolve` exact/prefix routes.

### Leave unchanged

- `nanobot/evolve/proposals.py`
  - `maybe_create_dream_proposal()` already lives in the evolution domain layer, not in `builtin.py`; do not move it into a command module.

- `tests/cli/test_restart_command.py`
  - Keep imports and patches targeting `nanobot.command.builtin.cmd_restart`, `nanobot.command.builtin.asyncio`, and `nanobot.command.builtin.os.execv`.

---

## Preflight Check

Before implementation, confirm there are no production imports of moved handlers from `nanobot.command.builtin`.

Run:

```bash
python - <<'PY'
from pathlib import Path
patterns = (
    'cmd_dream', 'cmd_dream_log', 'cmd_dream_restore',
    'cmd_curator', 'cmd_evolve', '_parse_curator_args',
    '_EVOLVE_USAGE', '_CURATOR_USAGE', '_extract_changed_files',
    '_format_dream_log_content',
)
for path in Path('.').rglob('*.py'):
    if '.git' in path.parts:
        continue
    text = path.read_text(encoding='utf-8')
    if 'nanobot.command.builtin' not in text:
        continue
    hits = [pattern for pattern in patterns if pattern in text]
    if hits:
        print(f'{path}: {", ".join(hits)}')
PY
```

Expected current output contains only tests:

```text
tests/command/test_builtin_dream.py: cmd_dream_log, cmd_dream_restore
tests/command/test_curator_command.py: cmd_curator
tests/command/test_evolve_command.py: cmd_evolve
```

If production files appear, update those imports to the new modules in the relevant task. Do not add a compatibility re-export unless a production import cannot be safely changed in this PR.

---

## Implementation Tasks

### Task 1: Split Dream slash commands into `dream_command.py`

**Files:**
- Create: `nanobot/command/dream_command.py`
- Modify: `nanobot/command/builtin.py:323-570`, `nanobot/command/builtin.py:994-1011`
- Modify: `tests/command/test_builtin_dream.py:8`
- Test: `tests/command/test_builtin_dream.py`
- Test: `tests/command/test_router_dispatchable.py::TestIsDispatchableCommand`

- [ ] **Step 1: Write the failing Dream import test change**

In `tests/command/test_builtin_dream.py`, replace the existing handler import:

```python
from nanobot.command.builtin import cmd_dream_log, cmd_dream_restore
```

with:

```python
from nanobot.command.dream_command import cmd_dream_log, cmd_dream_restore
```

- [ ] **Step 2: Run the Dream tests to verify they fail**

Run:

```bash
pytest tests/command/test_builtin_dream.py -v
```

Expected: FAIL during collection with:

```text
ModuleNotFoundError: No module named 'nanobot.command.dream_command'
```

- [ ] **Step 3: Create `nanobot/command/dream_command.py`**

Create `nanobot/command/dream_command.py` with this header:

```python
"""Dream slash command handlers."""

from __future__ import annotations

import asyncio
import logging

from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext

logger = logging.getLogger(__name__)
```

Then move these existing definitions from `nanobot/command/builtin.py` into this new file, preserving function bodies exactly except for import locality if ruff requires it:

```python
async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
    ...

def _extract_changed_files(diff: str) -> list[str]:
    ...

def _format_changed_files(diff: str) -> str:
    ...

def _format_dream_log_content(commit, diff: str, *, requested_sha: str | None = None) -> str:
    ...

def _format_dream_restore_list(commits: list) -> str:
    ...

async def cmd_dream_log(ctx: CommandContext) -> OutboundMessage:
    ...

async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    ...
```

The moved `cmd_dream()` body must keep this behavior unchanged:

```python
from nanobot.evolve.proposals import maybe_create_dream_proposal

maybe_create_dream_proposal(
    loop,
    completed=True,
    processed_entries=last_cursor,
)
```

The moved failure logging must keep the same message text:

```python
logger.exception("Dream evolution proposal creation failed")
```

Do not import anything from `nanobot.command.builtin` in `dream_command.py`.

- [ ] **Step 4: Remove Dream implementations from `builtin.py`**

In `nanobot/command/builtin.py`, delete the contiguous Dream block that starts at:

```python
async def cmd_dream(ctx: CommandContext) -> OutboundMessage:
```

and ends after:

```python
async def cmd_dream_restore(ctx: CommandContext) -> OutboundMessage:
    ...
```

After deletion, `_HISTORY_DEFAULT_COUNT = 10` should immediately follow the previous section.

Do not leave compatibility assignments such as:

```python
from nanobot.command.dream_command import cmd_dream
```

at module top level.

- [ ] **Step 5: Update Dream registration in `builtin.py`**

At the start of `register_builtin_commands()` in `nanobot/command/builtin.py`, add local imports for Dream handlers:

```python
def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    from nanobot.command.dream_command import cmd_dream, cmd_dream_log, cmd_dream_restore

    router.priority("/stop", cmd_stop)
```

Keep the existing Dream registrations unchanged:

```python
router.exact("/dream", cmd_dream)
router.exact("/dream-log", cmd_dream_log)
router.prefix("/dream-log ", cmd_dream_log)
router.exact("/dream-restore", cmd_dream_restore)
router.prefix("/dream-restore ", cmd_dream_restore)
```

- [ ] **Step 6: Run Dream and router tests to verify they pass**

Run:

```bash
pytest tests/command/test_builtin_dream.py tests/command/test_router_dispatchable.py::TestIsDispatchableCommand -v
```

Expected: PASS.

- [ ] **Step 7: Run ruff on changed command files**

Run:

```bash
ruff check nanobot/command/builtin.py nanobot/command/dream_command.py tests/command/test_builtin_dream.py
```

Expected: PASS.

- [ ] **Step 8: Commit the Dream split**

Run:

```bash
git add nanobot/command/builtin.py nanobot/command/dream_command.py tests/command/test_builtin_dream.py
git commit -m "$(cat <<'EOF'
refactor(command): split dream slash handlers

Move Dream slash command handlers into a focused internal command module while keeping router registration centralized.

Co-Authored-By: gpt-5.5 <noreply@anthropic.com>
EOF
)"
```

### Task 2: Split Curator and Evolve slash commands into `evolution_command.py`

**Files:**
- Create: `nanobot/command/evolution_command.py`
- Modify: `nanobot/command/builtin.py:704-970`, `nanobot/command/builtin.py:994-1019`
- Modify: `tests/command/test_curator_command.py:12`
- Modify: `tests/command/test_evolve_command.py:12`
- Test: `tests/command/test_curator_command.py`
- Test: `tests/command/test_evolve_command.py`

- [ ] **Step 1: Write the failing Curator/Evolve import test changes**

In `tests/command/test_curator_command.py`, replace:

```python
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, cmd_curator, register_builtin_commands
```

with:

```python
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, register_builtin_commands
from nanobot.command.evolution_command import cmd_curator
```

In `tests/command/test_evolve_command.py`, replace:

```python
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, cmd_evolve, register_builtin_commands
```

with:

```python
from nanobot.command.builtin import BUILTIN_COMMAND_SPECS, register_builtin_commands
from nanobot.command.evolution_command import cmd_evolve
```

- [ ] **Step 2: Run Curator/Evolve tests to verify they fail**

Run:

```bash
pytest tests/command/test_curator_command.py tests/command/test_evolve_command.py -v
```

Expected: FAIL during collection with:

```text
ModuleNotFoundError: No module named 'nanobot.command.evolution_command'
```

- [ ] **Step 3: Create `nanobot/command/evolution_command.py`**

Create `nanobot/command/evolution_command.py` with this header:

```python
"""Runtime evolution slash command handlers."""

from __future__ import annotations

import asyncio

from nanobot.bus.events import OutboundMessage
from nanobot.command.router import CommandContext
```

Then move these existing definitions from `nanobot/command/builtin.py` into this new file, preserving function bodies exactly except for import locality if ruff requires it:

```python
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
    ...


async def cmd_curator(ctx: CommandContext) -> OutboundMessage:
    ...


_EVOLVE_USAGE = (
    "Usage: `/evolve [list|create <skill> <rationale>|show <id>|run <id>]`\n"
    "  list                       List evolution proposals\n"
    "  create <skill> <rationale> Create a manual proposal\n"
    "  show <id>                  Show proposal details\n"
    "  run <id>                   Run proposal locally through offline harness"
)


def _evolve_sender_allowed(ctx: CommandContext) -> bool:
    ...


async def cmd_evolve(ctx: CommandContext) -> OutboundMessage:
    ...
```

The moved `/curator --json --evolve-proposals` branch must still put proposal IDs inside the fenced JSON payload:

```python
payload = report.model_dump(mode="json")
if evolve_proposals:
    payload["evolutionProposalsCreated"] = [
        proposal.proposal_id for proposal in created_evolution_proposals
    ]
raw_json = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
content = f"```json\n{raw_json}```"
```

The moved `/evolve run` branch must still use `asyncio.to_thread()` and redact failures:

```python
result = await asyncio.to_thread(
    ProposalRunner(store).run,
    proposal_id,
    optimizer_command=config.resolve_optimizer_command(),
    tiers=config.default_tier_list(),
    max_candidates=config.max_candidates,
    optimizer_timeout_seconds=config.optimizer_timeout_seconds,
)
```

```python
from nanobot.evolve.privacy.redact import redact

content = f"Evolution run failed: {redact(str(exc)).text}"
```

Do not import anything from `nanobot.command.builtin` in `evolution_command.py`.

- [ ] **Step 4: Remove Curator/Evolve implementations from `builtin.py`**

In `nanobot/command/builtin.py`, delete the contiguous runtime evolution block that starts at:

```python
_CURATOR_USAGE = (
```

and ends after:

```python
async def cmd_evolve(ctx: CommandContext) -> OutboundMessage:
    ...
```

After deletion, `async def cmd_help(ctx: CommandContext) -> OutboundMessage:` should follow `cmd_skill()`.

Do not leave module-level compatibility imports such as:

```python
from nanobot.command.evolution_command import cmd_curator, cmd_evolve
```

- [ ] **Step 5: Update Curator/Evolve registration in `builtin.py`**

Update the local import block at the start of `register_builtin_commands()` to include evolution handlers:

```python
def register_builtin_commands(router: CommandRouter) -> None:
    """Register the default set of slash commands."""
    from nanobot.command.dream_command import cmd_dream, cmd_dream_log, cmd_dream_restore
    from nanobot.command.evolution_command import cmd_curator, cmd_evolve

    router.priority("/stop", cmd_stop)
```

Keep existing Curator/Evolve registrations unchanged:

```python
router.exact("/curator", cmd_curator)
router.prefix("/curator ", cmd_curator)
router.exact("/evolve", cmd_evolve)
router.prefix("/evolve ", cmd_evolve)
```

- [ ] **Step 6: Run Curator/Evolve tests to verify they pass**

Run:

```bash
pytest tests/command/test_curator_command.py tests/command/test_evolve_command.py -v
```

Expected: PASS.

- [ ] **Step 7: Run ruff on changed command files**

Run:

```bash
ruff check nanobot/command/builtin.py nanobot/command/evolution_command.py tests/command/test_curator_command.py tests/command/test_evolve_command.py
```

Expected: PASS.

- [ ] **Step 8: Commit the evolution command split**

Run:

```bash
git add nanobot/command/builtin.py nanobot/command/evolution_command.py tests/command/test_curator_command.py tests/command/test_evolve_command.py
git commit -m "$(cat <<'EOF'
refactor(command): split evolution slash handlers

Move Curator and Evolve slash command handlers into a focused internal command module while preserving centralized registration.

Co-Authored-By: gpt-5.5 <noreply@anthropic.com>
EOF
)"
```

### Task 3: Lock registration and public API boundaries with regression tests

**Files:**
- Modify: `tests/command/test_router_dispatchable.py`
- Possibly modify: `nanobot/command/builtin.py`
- Test: `tests/command/test_router_dispatchable.py`

- [ ] **Step 1: Add failing/passing boundary tests**

In `tests/command/test_router_dispatchable.py`, add this test function near the existing `TestIsDispatchableCommand` tests:

```python
def test_moved_handlers_are_not_reexported_from_builtin() -> None:
    import nanobot.command.builtin as builtin

    assert not hasattr(builtin, "cmd_dream")
    assert not hasattr(builtin, "cmd_dream_log")
    assert not hasattr(builtin, "cmd_dream_restore")
    assert not hasattr(builtin, "cmd_curator")
    assert not hasattr(builtin, "cmd_evolve")
```

In `TestIsDispatchableCommand.test_exact_commands_match`, ensure the exact command assertions include Curator and Evolve:

```python
assert router.is_dispatchable_command("/curator")
assert router.is_dispatchable_command("/evolve")
```

In `TestIsDispatchableCommand.test_prefix_commands_match`, ensure the prefix command assertions include Evolve:

```python
assert router.is_dispatchable_command("/evolve list")
```

- [ ] **Step 2: Run router tests**

Run:

```bash
pytest tests/command/test_router_dispatchable.py -v
```

Expected: PASS. If `test_moved_handlers_are_not_reexported_from_builtin` fails, remove module-level moved handler imports from `builtin.py` and keep them inside `register_builtin_commands()` only.

- [ ] **Step 3: Confirm `builtin.py` has no moved handler implementations or re-export imports**

Run:

```bash
python - <<'PY'
from pathlib import Path
text = Path('nanobot/command/builtin.py').read_text(encoding='utf-8')
for needle in [
    'async def cmd_dream',
    'async def cmd_dream_log',
    'async def cmd_dream_restore',
    'async def cmd_curator',
    'async def cmd_evolve',
    'def _parse_curator_args',
    'def _evolve_sender_allowed',
    'from nanobot.command.dream_command import cmd_dream',
    'from nanobot.command.evolution_command import cmd_curator',
]:
    if needle in text and needle.startswith('from '):
        # Local imports inside register_builtin_commands are allowed.
        continue
    if needle in text:
        raise SystemExit(f'unexpected builtin content: {needle}')
print('builtin split boundary OK')
PY
```

Expected:

```text
builtin split boundary OK
```

Manual review requirement for this step: local imports inside `register_builtin_commands()` are allowed; module-level moved handler imports are not.

- [ ] **Step 4: Commit boundary tests**

Run:

```bash
git add tests/command/test_router_dispatchable.py nanobot/command/builtin.py
git commit -m "$(cat <<'EOF'
test(command): lock slash command split boundary

Verify moved command handlers remain internal to their focused modules while router dispatchability stays unchanged.

Co-Authored-By: gpt-5.5 <noreply@anthropic.com>
EOF
)"
```

### Task 4: Run focused regression suite and clean up imports

**Files:**
- Modify if needed: `nanobot/command/builtin.py`
- Modify if needed: `nanobot/command/dream_command.py`
- Modify if needed: `nanobot/command/evolution_command.py`
- Test: focused command and restart tests

- [ ] **Step 1: Run focused command regression tests**

Run:

```bash
pytest tests/command/test_builtin_dream.py tests/command/test_curator_command.py tests/command/test_evolve_command.py tests/command/test_router_dispatchable.py tests/cli/test_restart_command.py -v
```

Expected: PASS.

- [ ] **Step 2: Run ruff on changed Python files**

Run:

```bash
ruff check nanobot/command/builtin.py nanobot/command/dream_command.py nanobot/command/evolution_command.py tests/command/test_builtin_dream.py tests/command/test_curator_command.py tests/command/test_evolve_command.py tests/command/test_router_dispatchable.py tests/cli/test_restart_command.py
```

Expected: PASS.

If ruff reports unused imports in `builtin.py`, remove only the unused imports. The expected top import block after the split is:

```python
from __future__ import annotations

import asyncio
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
```

Do not remove `asyncio`, `os`, or `sys`; `/restart` still uses them and restart tests patch `nanobot.command.builtin.asyncio` and `nanobot.command.builtin.os.execv`.

- [ ] **Step 3: Run full command test directory**

Run:

```bash
pytest tests/command -v
```

Expected: PASS.

- [ ] **Step 4: Commit cleanup if any files changed**

If Step 2 or Step 3 required fixes, commit them:

```bash
git add nanobot/command/builtin.py nanobot/command/dream_command.py nanobot/command/evolution_command.py tests/command tests/cli/test_restart_command.py
git commit -m "$(cat <<'EOF'
fix(command): clean up slash split regressions

Address focused test or lint regressions after moving slash command handlers into focused modules.

Co-Authored-By: gpt-5.5 <noreply@anthropic.com>
EOF
)"
```

If no files changed, do not create an empty commit.

### Task 5: Final verification and roadmap/spec consistency check

**Files:**
- Read-only verification unless drift is found
- Possibly modify: `docs/hermes-evolution/specs/m10b-slash-command-split.md`
- Possibly modify: `docs/hermes-evolution/roadmap.md`

- [ ] **Step 1: Verify command split success criteria by source scan**

Run:

```bash
python - <<'PY'
from pathlib import Path
builtin = Path('nanobot/command/builtin.py').read_text(encoding='utf-8')
dream = Path('nanobot/command/dream_command.py').read_text(encoding='utf-8')
evolution = Path('nanobot/command/evolution_command.py').read_text(encoding='utf-8')
assert 'async def cmd_dream' not in builtin
assert 'async def cmd_dream_log' not in builtin
assert 'async def cmd_dream_restore' not in builtin
assert 'async def cmd_curator' not in builtin
assert 'async def cmd_evolve' not in builtin
assert 'async def cmd_dream' in dream
assert 'async def cmd_dream_log' in dream
assert 'async def cmd_dream_restore' in dream
assert 'async def cmd_curator' in evolution
assert 'async def cmd_evolve' in evolution
assert 'def register_builtin_commands' in builtin
assert 'BUILTIN_COMMAND_SPECS' in builtin
print('M10b-1 source split verified')
PY
```

Expected:

```text
M10b-1 source split verified
```

- [ ] **Step 2: Run final focused tests**

Run:

```bash
pytest tests/command/test_builtin_dream.py tests/command/test_curator_command.py tests/command/test_evolve_command.py tests/command/test_router_dispatchable.py tests/cli/test_restart_command.py -v
```

Expected: PASS.

- [ ] **Step 3: Run final lint**

Run:

```bash
ruff check nanobot/command tests/command tests/cli/test_restart_command.py
```

Expected: PASS.

- [ ] **Step 4: Check docs still match implementation**

Confirm these doc statements remain true:

- `docs/hermes-evolution/specs/m10b-slash-command-split.md` names the created modules as `dream_command.py` and `evolution_command.py`.
- `docs/hermes-evolution/roadmap.md` describes M10b as command-surface split with M10b-1 slash commands and M10b-2 CLI commands.
- No implementation added a command registry, discovery mechanism, schema migration, or feature flag.

If docs drifted, update only the incorrect lines and commit:

```bash
git add docs/hermes-evolution/specs/m10b-slash-command-split.md docs/hermes-evolution/roadmap.md
git commit -m "$(cat <<'EOF'
docs(command): align M10b slash split notes

Keep the M10b design and roadmap consistent with the implemented slash command module split.

Co-Authored-By: gpt-5.5 <noreply@anthropic.com>
EOF
)"
```

If docs still match, do not create an empty commit.

---

## Verification Plan

Run before opening a PR:

```bash
pytest tests/command/test_builtin_dream.py tests/command/test_curator_command.py tests/command/test_evolve_command.py tests/command/test_router_dispatchable.py tests/cli/test_restart_command.py -v
pytest tests/command -v
ruff check nanobot/command tests/command tests/cli/test_restart_command.py
```

Optional source boundary check:

```bash
python - <<'PY'
from pathlib import Path
builtin = Path('nanobot/command/builtin.py').read_text(encoding='utf-8')
for forbidden in ['async def cmd_dream', 'async def cmd_curator', 'async def cmd_evolve']:
    assert forbidden not in builtin, forbidden
print('builtin.py no longer contains moved handler implementations')
PY
```

## Safety Checklist

- No command name changes.
- No argument parsing changes.
- No output format changes.
- No proposal persistence changes.
- No config schema changes.
- No CLI command changes.
- No new registry/discovery/plugin architecture.
- No feature flag.
- `cmd_restart()` remains in `builtin.py`.
- `register_builtin_commands()` remains the only built-in router registration entry point.
- Tests import moved handlers from their new modules.
- `builtin.py` does not grow long-lived re-export shims for moved handlers.

## Self-Review

- Spec coverage: the plan creates `dream_command.py` and `evolution_command.py`, keeps metadata/registration in `builtin.py`, preserves command behavior through existing tests, adds public-boundary tests, and updates no CLI/WebUI/AgentLoop code.
- Placeholder scan: no placeholder markers, no unspecified tests, no unnamed files.
- Type consistency: all handler signatures remain `async def cmd_*(ctx: CommandContext) -> OutboundMessage`; router registration still receives the same handler callables; tests use the new module paths.
