# M10b Slash Command Split Design

## Status

Approved for planning on 2026-06-16.

## Context

M10 is a technical-debt stabilization milestone for the Hermes self-evolution work. The current roadmap identifies M10b as command-surface cleanup, especially around large command modules.

After M9, `nanobot/command/builtin.py` has grown into a mixed-responsibility module containing command metadata, router registration, help rendering, simple utility commands, Dream commands, Curator commands, and M9 `/evolve` commands. This makes future evolution work risky because changes to one command family require editing a large shared file.

Current observed sizes:

- `nanobot/command/builtin.py`: about 1,019 lines
- `nanobot/cli/commands.py`: about 2,086 lines
- `nanobot/agent/loop.py`: about 1,806 lines
- `nanobot/channels/websocket.py`: about 1,178 lines
- `webui/src/components/settings/SettingsView.tsx`: about 6,016 lines

This design covers only the first M10b slice: splitting evolution-related slash commands out of `builtin.py` while preserving behavior.

## Goals

1. Reduce `builtin.py` responsibility and line count.
2. Move high-change evolution-related slash commands into focused modules.
3. Preserve all existing slash command names, arguments, output formats, and side effects.
4. Keep `register_builtin_commands()` as the single router registration entry point.
5. Avoid introducing a new command discovery or plugin architecture in this slice.
6. Keep direct imports from `nanobot.command.builtin` compatible during this transition.

## Non-goals

This slice will not:

- Split `nanobot/cli/commands.py`.
- Rewrite `CommandRouter`.
- Add automatic command discovery.
- Change any slash command UX or command names.
- Change Dream, Curator, or Evolve business behavior.
- Refactor WebUI Settings, AgentLoop, or WebSocketChannel.
- Introduce a plugin command registry.

## Proposed Architecture

Create three focused modules under `nanobot/command/`:

```text
nanobot/command/
├── builtin.py              # metadata, help, simple commands, router registration
├── dream_command.py        # /dream, /dream-log, /dream-restore
├── curator_command.py      # /curator
└── evolve_command.py       # /evolve
```

### `dream_command.py`

Move these responsibilities from `builtin.py`:

- `cmd_dream()`
- `cmd_dream_log()`
- `cmd_dream_restore()`
- Dream formatting helpers used only by those handlers

Behavior must remain unchanged:

- Manual `/dream` still schedules the Dream run and returns `Dreaming...`.
- Dream completion still advances the cursor before attempting M9 proposal creation.
- Dream proposal creation failure remains isolated and logged without changing Dream success semantics.
- `/dream-log` and `/dream-restore` output formats remain unchanged.

### `curator_command.py`

Move these responsibilities from `builtin.py`:

- `_CURATOR_USAGE`
- `_parse_curator_args()`
- `cmd_curator()`

Behavior must remain unchanged:

- `/curator` remains default dry-run.
- `--apply` and `--dry-run` remain mutually exclusive.
- `--include-protected` behavior remains unchanged.
- `--json --evolve-proposals` remains a single fenced JSON payload.
- `--evolve-proposals` still creates proposals only when config allows.

### `evolve_command.py`

Move these responsibilities from `builtin.py`:

- `_EVOLVE_USAGE`
- `_evolve_sender_allowed()`
- `cmd_evolve()`

Behavior must remain unchanged:

- `/evolve list`, `show`, `create`, and `run` keep their current text output.
- `/evolve create` and `/evolve run` keep approved-sender enforcement.
- `/evolve run` still schedules work in the background and redacts failure output.
- The CLI `nanobot evolve` surface is not touched.

### `builtin.py`

`builtin.py` remains the public built-in command entry point. It will keep:

- `BuiltinCommandSpec`
- `BUILTIN_COMMAND_SPECS`
- `cmd_help()` and `build_help_text()`
- small existing command handlers not part of this slice
- `cmd_pairing()`
- `register_builtin_commands()`

To reduce compatibility risk, `builtin.py` will temporarily re-export migrated handlers by importing them from their new modules. Existing code or tests that import `cmd_evolve`, `cmd_curator`, or Dream handlers from `nanobot.command.builtin` should continue to work.

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

2. Keep direct handler imports compatible from `builtin.py` for this first split.

3. Update tests that monkeypatch module-local dependencies to patch the new module paths, so tests validate the new boundaries rather than depending on `builtin.py` internals.

4. Do not alter `BUILTIN_COMMAND_SPECS` in this slice except for import-related adjustments if needed.

## Error Handling

No error-handling semantics should change.

- Dream proposal creation errors are logged and do not turn a completed Dream run into a failed user-visible response.
- Curator argument errors return the existing usage/error text.
- Evolve background run errors are redacted before being sent to the chat channel.
- Proposal lookup and run failures keep their current user-facing messages.

## Testing Strategy

Run existing focused command tests after migration:

- `tests/command/test_evolve_command.py`
- `tests/command/test_curator_command.py`
- Dream command tests under `tests/command/`
- Router dispatchability tests under `tests/command/`

Adjust monkeypatch paths from `nanobot.command.builtin.*` to the new module paths where the patched symbol moved.

Add or preserve coverage that verifies:

- `/dream`, `/dream-log`, `/dream-restore`, `/curator`, and `/evolve` are still registered.
- Direct imports from `nanobot.command.builtin` still work for migrated handlers during this transition.
- `/curator --json --evolve-proposals` remains one fenced JSON payload.
- `/evolve create/run` approved-sender behavior remains intact.

Run lint on changed Python files.

## Risks and Mitigations

### Risk: Monkeypatch tests still pass through compatibility imports but not new module boundaries

Mitigation: update monkeypatch targets to new modules when symbols moved.

### Risk: Circular imports between `builtin.py` and new command modules

Mitigation: new command modules should import only shared types such as `CommandContext`, `OutboundMessage`, and domain services. They must not import `BUILTIN_COMMAND_SPECS` or `register_builtin_commands()`.

### Risk: Help metadata drifts from handlers

Mitigation: keep `BUILTIN_COMMAND_SPECS` centralized in `builtin.py` for this slice. A later M10b slice can decide whether metadata should live next to handlers.

### Risk: Hidden direct imports from `builtin.py`

Mitigation: keep re-exports in `builtin.py` for migrated handlers.

## Success Criteria

- `builtin.py` is materially smaller and no longer contains Dream, Curator, or Evolve handler implementations.
- The new modules have clear command-family responsibilities.
- All existing command behavior is preserved.
- Focused command tests pass.
- Lint passes on changed Python files.
- No new command registry or discovery abstraction is introduced.
