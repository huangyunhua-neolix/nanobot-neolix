# M10b-1 Slash Command Split Design

## Status

Approved for planning on 2026-06-16. Revised on 2026-06-16 after spec review.

## Context

M10 is a technical-debt stabilization milestone for the Hermes self-evolution work. The roadmap originally named M10b as "CLI command split" because `nanobot/cli/commands.py` is one of the largest command-surface files. Review clarified that M10b should be treated as broader command-surface cleanup, with multiple slices:

1. **M10b-1 Slash command split** — this design; focused on `nanobot/command/builtin.py`.
2. **M10b-2 CLI command split** — later slice; focused on `nanobot/cli/commands.py`.

This slice comes first even though `builtin.py` is not the largest file because it is the highest-change surface for recent Hermes evolution work. M3 added `/curator`, M9 added `/evolve`, and Dream integration now creates runtime evolution proposals. Keeping these handlers inside one shared module makes follow-up evolution work riskier because unrelated command families share imports, helper functions, logging context, and tests.

Current observed sizes:

- `nanobot/command/builtin.py`: about 1,019 lines
- `nanobot/cli/commands.py`: about 2,086 lines
- `nanobot/agent/loop.py`: about 1,806 lines
- `nanobot/channels/websocket.py`: about 1,178 lines
- `webui/src/components/settings/SettingsView.tsx`: about 6,016 lines

This design covers only M10b-1: splitting high-change slash command handlers out of `builtin.py` while preserving runtime behavior.

## Goals

1. Reduce `builtin.py` responsibility and line count.
2. Move high-change slash command handlers into focused internal modules.
3. Preserve all existing slash command names, arguments, output formats, scheduling behavior, config checks, and side effects.
4. Keep `register_builtin_commands()` as the single router registration entry point.
5. Avoid introducing command discovery, a plugin registry, or a metadata DSL in this slice.
6. Make public API boundaries explicit: slash command names and `register_builtin_commands()` remain stable; handler function import paths are internal.

## Non-goals

This slice will not:

- Split `nanobot/cli/commands.py`; that remains M10b-2.
- Rewrite `CommandRouter`.
- Add automatic command discovery.
- Change any slash command UX or command names.
- Change Dream, Curator, or Evolve business behavior.
- Refactor WebUI Settings, AgentLoop, or WebSocketChannel.
- Introduce a plugin command registry.
- Co-locate command metadata with handlers; `BUILTIN_COMMAND_SPECS` stays centralized for this slice.

## Prioritization Rationale

M10 contains several larger files, but this slice is prioritized by change frequency and coupling risk rather than raw line count.

- `SettingsView.tsx` is larger, but it is mostly WebUI settings surface and can be isolated as M10a.
- `nanobot/cli/commands.py` is larger, but CLI command splitting can follow once the runtime slash command boundary is proven.
- `nanobot/command/builtin.py` is smaller but directly contains Dream, Curator, and `/evolve`, the command families most likely to change as Hermes evolution continues.

The forcing function is near-term evolution work: future changes should be able to edit Dream or evolution proposal commands without reopening a 1,000-line mixed built-in command file.

## Proposed Architecture

Create two focused internal modules under `nanobot/command/`:

```text
nanobot/command/
├── builtin.py              # metadata, help, simple commands, router registration
├── dream_command.py        # /dream, /dream-log, /dream-restore
└── evolution_command.py    # /curator and /evolve
```

This intentionally avoids a three-module split. `/curator` and `/evolve` are both part of the runtime-to-offline evolution command surface after M9:

- `/curator --evolve-proposals` creates proposal records from Curator findings.
- `/evolve` lists, shows, creates, and runs those proposal records.
- Both handlers depend on evolution config, proposal storage, and approved-sender/runtime safety checks.

Keeping them together reduces file churn and preserves a cohesive boundary without creating one tiny module per command.

### `dream_command.py`

Move these responsibilities from `builtin.py`:

- `cmd_dream()`
- `cmd_dream_log()`
- `cmd_dream_restore()`
- Dream-only helpers:
  - `_extract_changed_files()`
  - `_format_changed_files()`
  - `_format_dream_log_content()`
  - `_format_dream_restore_list()`
  - `_maybe_create_dream_evolution_proposal()`

Behavior must remain unchanged:

- Manual `/dream` still schedules the Dream run and returns `Dreaming...`.
- Dream completion still advances the cursor before attempting M9 proposal creation.
- Dream proposal creation failure remains isolated and logged without changing Dream success semantics.
- `/dream-log` and `/dream-restore` output formats remain unchanged.

The module should define its own logger:

```python
logger = logging.getLogger(__name__)
```

Log message text and severity should stay equivalent, but the logger name will change from `nanobot.command.builtin` to `nanobot.command.dream_command`. This is acceptable and should be documented in tests/review notes; byte-identical logger names are not a compatibility requirement.

### `evolution_command.py`

Move these responsibilities from `builtin.py`:

- `_CURATOR_USAGE`
- `_parse_curator_args()`
- `cmd_curator()`
- `_EVOLVE_USAGE`
- `_evolve_sender_allowed()`
- `cmd_evolve()`

Behavior must remain unchanged:

- `/curator` remains default dry-run.
- `--apply` and `--dry-run` remain mutually exclusive.
- `--include-protected` behavior remains unchanged.
- `--json --evolve-proposals` remains a single fenced JSON payload followed by the existing proposal footer behavior.
- `--evolve-proposals` still creates proposals only when config allows.
- `/evolve list`, `show`, `create`, and `run` keep their current text output.
- `/evolve create` and `/evolve run` keep approved-sender enforcement.
- `/evolve run` still schedules work in the background and redacts failure output.
- The CLI `nanobot evolve` surface is not touched.

The module must import `asyncio` directly because `/evolve run` uses `asyncio.to_thread()` for background proposal execution.

The module should define its own logger if it logs command-local failures:

```python
logger = logging.getLogger(__name__)
```

### `builtin.py`

`builtin.py` remains the public built-in command entry point. It keeps:

- `BuiltinCommandSpec`
- `BUILTIN_COMMAND_SPECS`
- `cmd_help()` and `build_help_text()`
- small existing command handlers not part of this slice
- `cmd_pairing()`
- `cmd_restart()`
- `register_builtin_commands()`

`register_builtin_commands()` imports the moved handlers and registers the same exact/prefix routes as today. No other registration entry point is added.

`BUILTIN_COMMAND_SPECS` remains centralized in `builtin.py`. This is intentional for M10b-1: it minimizes metadata churn while handler movement is validated. A later M10b slice may revisit handler/metadata co-location, but this design does not partially introduce that model.

## Public API and Import Compatibility

Stable public surface for this slice:

- Slash command names and arguments:
  - `/dream`
  - `/dream-log`
  - `/dream-restore`
  - `/curator`
  - `/evolve`
- `register_builtin_commands(router)` as the built-in registration entry point.
- Help/palette metadata generated from `BUILTIN_COMMAND_SPECS`.

Internal surface:

- Handler functions such as `cmd_dream`, `cmd_curator`, and `cmd_evolve` are internal implementation details.
- Tests should import handlers from their new modules after migration.
- `nanobot.command.builtin` should not grow long-lived re-export shims for moved handlers unless implementation discovers non-test production imports that cannot be updated safely in the same PR.

If a temporary re-export is required during implementation, it must be explicitly time-boxed:

1. Add a comment naming it as an M10b-1 compatibility shim.
2. Add a test proving the compatibility path works.
3. Add a follow-up item in the implementation plan to remove it in M10b cleanup once internal imports are migrated.

Default implementation target: **no compatibility re-export** unless current-code search proves it is needed.

## Request Flow

The runtime flow remains identical:

```text
InboundMessage
  ↓
AgentLoop._state_command()
  ↓
CommandRouter.dispatch()
  ↓
registered handler
  ↓
OutboundMessage
```

Only handler definition locations change. `register_builtin_commands()` remains the only registration function used by `AgentLoop`.

## Compatibility Strategy

1. Keep command names and registration rules unchanged:
   - `/dream`
   - `/dream-log`
   - `/dream-restore`
   - `/curator`
   - `/evolve`

2. Update tests to import moved handlers from the new modules, so tests validate the new boundaries rather than depending on `builtin.py` internals.

3. Update monkeypatch paths only where the patched symbol moved. Domain-level monkeypatches such as `nanobot.evolve.proposals.*` should remain unchanged.

4. Do not alter `BUILTIN_COMMAND_SPECS` content except for import/reference adjustments required by handler movement. Command labels, descriptions, icons, and usage strings must remain behaviorally equivalent.

5. Preserve `cmd_restart()` in `builtin.py`; tests that patch `nanobot.command.builtin.asyncio` or `nanobot.command.builtin.os.execv` remain outside this slice.

## Error Handling

No error-handling semantics should change.

- Dream proposal creation errors are logged and do not turn a completed Dream run into a failed user-visible response.
- Curator argument errors return the existing usage/error text.
- Evolve background run errors are redacted before being sent to the chat channel.
- Proposal lookup and run failures keep their current user-facing messages.
- Approved-sender checks for `/evolve create` and `/evolve run` remain enforced.

## Observability Strategy

Moving handlers changes Python module names, so logger names may change. This is acceptable if observability intent is preserved.

Implementation must preserve:

- Existing log severity for command-local failures.
- Existing user-visible messages.
- Existing background-task success/failure publication behavior.
- Existing redaction before user-visible `/evolve run` failure output.

Implementation does not need to preserve:

- Byte-identical logger names.
- Exact line numbers in log records.
- `nanobot.command.builtin` as the source module for Dream/evolution logs.

The new modules should use module-local loggers rather than importing a logger from `builtin.py`.

## Rollback Strategy

This slice should land as a single focused PR with no schema, persistence, command UX, or router changes. If runtime command dispatch breaks after merge, rollback is a normal PR revert of the split commit(s).

No feature flag is needed because:

- The command names and router entry point do not change.
- No user data migration is introduced.
- No command discovery or plugin mechanism is introduced.
- Reverting restores the previous handler locations.

## Testing Strategy

Run existing focused command tests after migration:

- `tests/command/test_evolve_command.py`
- `tests/command/test_curator_command.py`
- Dream command tests under `tests/command/`
- Router dispatchability tests under `tests/command/`
- `tests/cli/test_restart_command.py` to ensure restart command patches are unaffected.

Adjust imports and monkeypatch paths from `nanobot.command.builtin.*` to the new module paths only when the symbol moved:

- Dream handler/helper tests should target `nanobot.command.dream_command.*`.
- Curator and Evolve handler/helper tests should target `nanobot.command.evolution_command.*`.
- Registration and help tests should continue to target `nanobot.command.builtin.*` where they validate `register_builtin_commands()` or `BUILTIN_COMMAND_SPECS`.

Add or preserve coverage that verifies:

- `/dream`, `/dream-log`, `/dream-restore`, `/curator`, and `/evolve` are still registered.
- `register_builtin_commands()` remains the only built-in registration entry point needed by `AgentLoop`.
- `/curator --json --evolve-proposals` remains one fenced JSON payload plus the existing proposal footer behavior.
- `/evolve create/run` approved-sender behavior remains intact.
- Dream completion still advances the cursor before attempting proposal creation.
- `cmd_restart()` remains in `builtin.py` and existing restart tests still patch the same module path.

Run lint on changed Python files.

## Risks and Mitigations

### Risk: Roadmap/spec scope drift

Mitigation: name this slice M10b-1 and update the roadmap to clarify M10b sequencing: slash command split first, CLI command split later.

### Risk: Over-splitting creates churn without enough payoff

Mitigation: use two modules, not three. Keep Curator and Evolve together as `evolution_command.py` because they share the runtime evolution proposal surface.

### Risk: Tests validate compatibility shims instead of new boundaries

Mitigation: default to no re-export from `builtin.py`; update direct handler imports in tests to the new modules. If a temporary shim is required, test it explicitly and time-box its removal.

### Risk: Circular imports between `builtin.py` and new command modules

Mitigation: new command modules should import only shared types such as `CommandContext`, `OutboundMessage`, and domain services. They must not import `BUILTIN_COMMAND_SPECS` or `register_builtin_commands()`.

### Risk: Help metadata drifts from handlers

Mitigation: keep `BUILTIN_COMMAND_SPECS` centralized in `builtin.py` for this slice. Do not introduce partial handler-owned metadata.

### Risk: Observability continuity is weakened

Mitigation: use module-local loggers in new modules and preserve log severity/message intent. Treat logger-name changes as expected, not as regressions.

### Risk: Hidden production imports from `builtin.py`

Mitigation: implementation must grep for imports of moved handlers before editing. If only tests import them, update tests. If production imports exist, either update those imports in the same PR or add an explicitly time-boxed compatibility shim.

## Success Criteria

- `builtin.py` is materially smaller and no longer contains Dream, Curator, or Evolve handler implementations.
- `dream_command.py` owns Dream slash command handlers and Dream-only helpers.
- `evolution_command.py` owns Curator and Evolve slash command handlers and their command-local helpers.
- Existing command names, argument behavior, output formats, background scheduling, sender authorization, and proposal side effects are preserved.
- `register_builtin_commands()` remains the only built-in router registration entry point.
- `BUILTIN_COMMAND_SPECS` remains centralized and behaviorally unchanged.
- Focused command tests pass.
- Lint passes on changed Python files.
- No new command registry, discovery abstraction, schema migration, or feature flag is introduced.
