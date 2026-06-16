# M10b-2 CLI Command Split Design

## Status

Approved for specification on 2026-06-16 after M10b-1 merged. Revised on 2026-06-16 after spec review.

## Context

M10 is a technical-debt stabilization milestone for the Hermes self-evolution work. M10b is command-surface cleanup split into slices:

1. **M10b-1 Slash command split** — completed in PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21; focused on `nanobot/command/builtin.py`.
2. **M10b-2 CLI command split** — this design; focused on reducing `nanobot/cli/commands.py` without changing CLI behavior.

`nanobot/cli/commands.py` is still a mixed-responsibility module of about 2,086 lines. It currently owns Typer app creation, console/logging setup, onboarding, OpenAI-compatible API server startup, gateway/desktop-gateway startup, interactive agent mode, channel status/login, plugins/status commands, provider OAuth commands, and the `nanobot evolve` argparse bridge.

Current observed sizes after M10b-1:

- `nanobot/cli/commands.py`: about 2,086 lines
- `nanobot/cli/evolve.py`: about 572 lines
- `nanobot/agent/loop.py`: about 1,806 lines
- `nanobot/channels/websocket.py`: about 1,178 lines
- `webui/src/components/settings/SettingsView.tsx`: about 6,016 lines
- `nanobot/command/builtin.py`: about 501 lines

This slice should prove the CLI command-surface split pattern with a low-risk subset before touching the interactive `agent()` command or broader CLI registration model.

## Goals

1. Reduce `nanobot/cli/commands.py` responsibility and line count.
2. Move gateway-related CLI command handlers and helpers into a focused internal module.
3. Move provider OAuth CLI command handlers and helpers into a focused internal module.
4. Preserve existing command names, options, help behavior, exit behavior, output text intent, logging behavior, config loading semantics, and side effects.
5. Keep `nanobot.cli.commands.app` as the single public Typer app entry point.
6. Avoid introducing automatic command discovery, plugin command registration, or a new CLI framework.

## Non-goals

This slice will not:

- Split the interactive `agent()` command.
- Split onboarding, channel, plugin, status, or `nanobot evolve` bridge commands.
- Rewrite the Typer app bootstrap.
- Move global console/logging setup out of `commands.py`.
- Change config schema or config file migration behavior.
- Change gateway runtime semantics, WebUI runtime capabilities, heartbeat, Dream cron, or cron delivery behavior.
- Change OAuth storage paths, provider aliases, login/logout UX, or provider registry semantics.
- Introduce command discovery or a plugin registry.

## Proposed Architecture

Create two focused internal modules under `nanobot/cli/` and one small shared-support module:

```text
nanobot/cli/
├── commands.py              # app, shared console/log setup, onboard, agent, channels, plugins, status, evolve bridge
├── shared.py                # low-level CLI globals/helpers shared by focused command modules
├── gateway_commands.py      # serve, gateway, desktop-gateway, gateway runtime helpers
├── provider_commands.py     # provider Typer sub-app, login/logout handlers and OAuth helpers
└── evolve.py                # existing argparse evolve surface; unchanged in this slice
```

`shared.py` is intentionally small and exists to prevent circular imports between `commands.py` and the moved command modules. It should own only infrastructure that is needed by both the root app module and the moved modules.

### `shared.py`

Move these shared infrastructure responsibilities from `commands.py` only as needed by both root and focused modules:

- `console = Console()`
- loguru setup, including `_log_handler_id`
- `_model_display()`
- `_load_runtime_config()`
- `_warn_deprecated_config_keys()`
- `_migrate_cron_store()`
- `_heartbeat_has_active_tasks()`
- `_proactive_delivery_metadata()`
- `_PROACTIVE_WEBUI_METADATA`
- constants used by those helpers, including `_WEBUI_TURN_META_KEY`, `_WEBUI_MESSAGE_SOURCE_META_KEY`, and `_HEARTBEAT_PREAMBLE`

`shared.py` must not import `nanobot.cli.commands`, `gateway_commands`, or `provider_commands`. It is a one-directional dependency target for CLI modules.

### `gateway_commands.py`

Move these responsibilities from `commands.py`:

- `serve()`
- `gateway()`
- `desktop_gateway()`
- Gateway and desktop-gateway helpers:
  - `_desktop_provider_error_is_recoverable()`
  - `_desktop_provider_needs_bootstrap()`
  - `_reset_desktop_config_to_unconfigured()`
  - `_is_persisted_desktop_bootstrap()`
  - `_apply_desktop_runtime_bootstrap()`
  - `_load_or_create_desktop_config()`
  - `_configure_desktop_gateway()`
  - `_run_gateway()`
- Desktop bootstrap constants:
  - `DESKTOP_BOOTSTRAP_PROVIDER`
  - `DESKTOP_BOOTSTRAP_MODEL`

The module should expose one registration function:

```python
def register_gateway_commands(app: typer.Typer) -> None:
    ...
```

`register_gateway_commands(app)` registers the same `serve`, `gateway`, and hidden `desktop-gateway` commands that currently use decorators in `commands.py`. These commands must remain flat root commands, not a nested `gateway` Typer sub-app. The preferred implementation is plain handler functions plus explicit registration inside `register_gateway_commands()`, for example `app.command()(serve)`, `app.command()(gateway)`, and `app.command("desktop-gateway", hidden=True)(desktop_gateway)`.

Behavior must remain unchanged:

- `nanobot serve` still starts the OpenAI-compatible API server with the same options and startup output.
- `nanobot gateway` still loads runtime config, applies verbose logging behavior, and calls the same gateway runtime path.
- `nanobot desktop-gateway` remains hidden and enforces the same `--token-issue-secret` and socket/port validation.
- `_run_gateway()` still wires MessageBus, RuntimeEventBus, provider snapshot, SessionManager, CronService, ChannelManager, Dream/Heartbeat cron jobs, WebUI turn coordination, health endpoint, and shutdown flushing identically.
- Default-workspace cron migration behavior remains unchanged.

### `provider_commands.py`

Move these responsibilities from `commands.py`:

- `provider_app = typer.Typer(...)`
- `provider_login()`
- `provider_logout()`
- Provider OAuth handler registries and helpers:
  - `_LOGIN_HANDLERS`
  - `_LOGOUT_HANDLERS`
  - `_PROVIDER_DISPLAY`
  - `_register_login()`
  - `_register_logout()`
  - `_resolve_oauth_provider()`
  - `_login_openai_codex()`
  - `_logout_openai_codex()`
  - `_login_github_copilot()`
  - `_logout_github_copilot()`
  - `_delete_oauth_files()`

The module should expose one registration function:

```python
def register_provider_commands(app: typer.Typer) -> None:
    ...
```

`register_provider_commands(app)` attaches the same `provider` Typer sub-app to the root app via `app.add_typer(provider_app, name="provider")`. Unlike gateway commands, provider commands remain nested under the existing `provider` sub-app so `nanobot provider login` and `nanobot provider logout` help output stays equivalent.

Behavior must remain unchanged:

- `nanobot provider login <provider>` keeps the same supported provider names, aliases, output, and exit behavior.
- `nanobot provider logout <provider>` removes the same token and lock files and keeps the same output for removed/missing/skipped paths.
- Unknown OAuth providers still print the supported list and exit with code 1.
- OAuth imports remain lazy inside provider-specific handlers so optional dependencies stay optional until the relevant command runs.

### `commands.py`

`commands.py` remains the public CLI entry point. It keeps:

- `app = typer.Typer(...)`
- CLI rendering helpers and interactive prompt helpers not needed by moved modules
- onboarding command
- interactive `agent()` command
- channel status/login commands
- plugin/status commands
- `nanobot evolve` Typer-to-argparse bridge

`commands.py` imports shared CLI infrastructure from `nanobot.cli.shared` instead of owning it directly when that infrastructure is needed by moved modules.

After creating `app`, `commands.py` imports registration functions from the new modules and calls them once:

```python
from nanobot.cli.gateway_commands import register_gateway_commands
from nanobot.cli.provider_commands import register_provider_commands

register_gateway_commands(app)
register_provider_commands(app)
```

Import discipline is mandatory for this slice:

1. `shared.py` must not import `commands.py`, `gateway_commands.py`, or `provider_commands.py`.
2. `gateway_commands.py` and `provider_commands.py` must not import from `nanobot.cli.commands`.
3. `commands.py` may import `shared.py`, `gateway_commands.py`, and `provider_commands.py`.
4. Optional heavyweight dependencies remain lazy inside the command/helper functions that already load them lazily today.

This creates one-way dependencies and follows the explicit-registration pattern proven by M10b-1: the root entry point owns registration, focused modules own command families, and no discovery or compatibility re-export layer is introduced.

## Public API and Import Compatibility

Stable public surface for this slice:

- CLI command names and options:
  - `nanobot serve`
  - `nanobot gateway`
  - `nanobot desktop-gateway`
  - `nanobot provider login`
  - `nanobot provider logout`
- `nanobot.cli.commands.app` as the root Typer app.
- Existing console output intent and exit-code behavior.
- Direct imports of moved helper functions from `nanobot.cli.commands` are not public API and should be migrated to the new module paths.

Internal surface:

- Handler functions such as `serve`, `gateway`, `desktop_gateway`, `provider_login`, and `provider_logout` are internal implementation details.
- Tests should prefer invoking `app` through `CliRunner` rather than importing moved handlers directly.
- `nanobot.cli.commands` should not grow long-lived re-export shims for moved handlers unless current-code search finds non-test production imports that cannot be updated safely in the same PR.

Default implementation target: **no compatibility re-export** for moved handlers.

## Request Flow

The CLI flow remains equivalent:

```text
nanobot CLI entry point
  ↓
nanobot.cli.commands.app
  ↓
Typer command registration from commands.py + focused command modules
  ↓
registered command callback
  ↓
existing runtime side effects / console output / exit code
```

Only handler definition locations and command registration style change.

## Compatibility Strategy

1. Keep command names and options unchanged.
2. Keep `nanobot.cli.commands.app` as the only public app imported by tests and entry points.
3. Register moved commands through explicit registration functions, not discovery.
4. Do not change `nanobot/cli/evolve.py` or the `nanobot evolve` bridge in this slice.
5. Do not alter provider OAuth storage logic, gateway config mutation logic, or runtime wiring.
6. Update monkeypatch paths only where tests patch moved module-local symbols. Prefer `CliRunner` tests against `app` when possible.
7. Update existing internal helper imports in tests from `nanobot.cli.commands` to the new module paths. Known current call sites:
   - `tests/cli/test_commands.py` imports `_configure_desktop_gateway`; update it to `nanobot.cli.gateway_commands`.
   - `tests/cli/test_commands.py` imports `_load_or_create_desktop_config`; update it to `nanobot.cli.gateway_commands`.
8. Update structural tests that inspect `nanobot/cli/commands.py` for moved gateway internals. Known current call site: `tests/agent/skills/test_dream_e2e.py` checks Dream cron wiring in `nanobot/cli/commands.py`; after `_run_gateway()` moves, that test should inspect `nanobot/cli/gateway_commands.py` instead.

## Error Handling

No error-handling semantics should change.

- `serve()` still exits with code 1 when the API extra dependency is unavailable or provider config is invalid.
- `gateway()` and `desktop_gateway()` keep existing Typer exit behavior and printed errors.
- `desktop_gateway()` still rejects missing token secret and missing port/socket before running gateway startup.
- Provider OAuth unknown-provider and optional-dependency errors keep their current printed messages and `typer.Exit(1)` behavior.
- `_run_gateway()` keeps its existing runtime exception handling and shutdown cleanup semantics.

## Observability Strategy

Implementation must preserve:

- Existing loguru logger configuration and verbose mode behavior.
- Existing startup output for `serve`, `gateway`, and `desktop-gateway`.
- Existing gateway runtime logs emitted by the same services.
- Existing OAuth success/failure output.

Implementation does not need to preserve:

- Handler function `__module__` values.
- Source line numbers in tracebacks.

## Testing Strategy

Run existing focused CLI tests after migration:

- `tests/cli/test_commands.py`
- `tests/agent/skills/test_dream_e2e.py`
- Any gateway/provider tests discovered during implementation.

Add or preserve coverage that verifies:

- `nanobot serve --help` remains registered.
- `nanobot gateway --help` remains registered.
- `nanobot desktop-gateway --help` remains registered, while remaining hidden from top-level help.
- `nanobot provider login --help` remains registered.
- `nanobot provider logout --help` remains registered.
- Provider logout behavior for OpenAI Codex and GitHub Copilot still removes the expected files.
- Unknown provider login/logout behavior remains unchanged.
- Tests that import `_configure_desktop_gateway` and `_load_or_create_desktop_config` import them from `nanobot.cli.gateway_commands`.
- The Dream cron structural test inspects the module that owns `_run_gateway()` after the move.

Run lint on changed Python files:

```bash
uv run ruff check nanobot/cli/commands.py nanobot/cli/shared.py nanobot/cli/gateway_commands.py nanobot/cli/provider_commands.py tests/cli/test_commands.py tests/agent/skills/test_dream_e2e.py
```

## Risks and Mitigations

### Risk: Circular import between `commands.py` and moved modules

Mitigation: prevent the cycle by introducing `nanobot/cli/shared.py` up front and enforcing one-way imports: shared infrastructure lives in `shared.py`; focused modules import from `shared.py`; `commands.py` imports shared infrastructure and calls focused module registration functions. Focused modules must not import from `nanobot.cli.commands`.

### Risk: Verbose logging behavior drifts

Mitigation: moved gateway handlers should reuse the same `logger` object and `_log_handler_id` from `shared.py` rather than creating an independent log configuration.

### Risk: Typer help output changes accidentally

Mitigation: add help registration tests for the moved commands and preserve the same command decorators/options when moving handlers.

### Risk: Provider OAuth optional dependencies become eager imports

Mitigation: keep OAuth library imports inside provider-specific login/logout functions.

### Risk: Moving `_run_gateway()` is too large for one slice

Mitigation: move it with the gateway command family because it is command-local runtime wiring. Do not split its internals in this slice; preserving behavior is safer than extracting additional abstractions. Before moving it, implementation must grep `_run_gateway()` for module-global references and either import those globals from `shared.py` or keep them as lazy local imports. The implementation should not silently invent new parameters for `_run_gateway()` unless a test proves that is safer.

## Rollback Strategy

This slice should land as a focused PR with no schema, persistence, command UX, or gateway behavior changes. If CLI command registration or gateway startup breaks after merge, rollback is a normal PR revert of the split commit(s).

No feature flag is needed because:

- Command names and options do not change.
- The root Typer app remains `nanobot.cli.commands.app`.
- No data migration is introduced.
- Reverting restores previous handler locations.

## Success Criteria

- `commands.py` is materially smaller and no longer contains gateway or provider OAuth command implementations.
- `shared.py` owns only low-level CLI infrastructure needed by both the root app and moved modules, and imports no command modules.
- `gateway_commands.py` owns `serve`, `gateway`, `desktop-gateway`, and gateway runtime helpers.
- `provider_commands.py` owns provider login/logout command handlers and OAuth helpers.
- Existing command names, options, help behavior, output intent, exit behavior, config loading, logging, and side effects are preserved.
- `nanobot.cli.commands.app` remains the single public root Typer app.
- No moved module imports from `nanobot.cli.commands`.
- No command discovery/plugin registry/new CLI framework is introduced.
- Focused CLI tests pass.
- Lint passes on changed Python files.
