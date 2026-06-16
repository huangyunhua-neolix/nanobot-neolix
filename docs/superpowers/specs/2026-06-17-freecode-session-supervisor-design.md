# FreeCode PTY Supervisor Design

## Summary

Add a dedicated `freecode_session` tool that lets a nanobot agent start and supervise a local `freecode` CLI terminal. The nanobot agent acts as the supervisor: it launches the terminal, sends prompts and follow-up input, monitors output, handles low-risk interactive choices autonomously, and asks the user only for high-risk decisions.

This follows the proven shape from the adjacent `freecode-web-submodule` implementation, where `PtyManager` launches the CLI through a PTY and exposes session operations for write, resize, stop, and output handling. Nanobot already has long-running `exec` sessions with stdin support, but `freecode_session` should be a dedicated tool because freecode needs terminal semantics, clearer lifecycle boundaries, and a specialized decision contract. The first nanobot version intentionally omits resize because there is no user-facing terminal viewport yet.

## Goals

- Let nanobot use `freecode` the same way the user does locally: start a terminal, type instructions, read output, and continue the conversation.
- Preserve real terminal behavior with PTY-backed execution rather than plain subprocess pipes.
- Give the supervising nanobot agent a small, explicit tool API for starting, sending input, polling output, listing sessions, and stopping sessions.
- Support default-autonomous supervision: the agent decides routine interactions, but asks the user before high-risk actions.
- Keep the first version focused on local CLI supervision, not WebUI terminal mirroring or multi-agent orchestration.

## Non-goals

- No WebUI terminal pane or browser-side live mirror in the first version.
- No freecode team/crew orchestration in the first version.
- No automatic dependency upgrade, destructive git operation, PR merge, or credential/login handling without user confirmation. Normal branch push and PR creation are allowed when they are part of the user's requested development workflow.
- No attempt to replace nanobot's existing `spawn` subagent tool; `freecode_session` is an external terminal supervisor, not an internal nanobot subagent.

## Existing Context

Nanobot has `exec` and `write_stdin` tools implemented around `ExecSessionManager`. They can run long-lived processes, write stdin, poll output, terminate sessions, and enforce owner session keys. This is useful for shells and simple interactive programs, but it does not provide PTY behavior.

The nearby freecode web implementation uses `web/server/pty-manager.mjs` with `@homebridge/node-pty-prebuilt-multiarch`. It spawns the freecode CLI with terminal settings, keeps one PTY per session, exposes write/resize/kill operations, and records last output timestamps. Nanobot should borrow the lifecycle shape, but implement it in Python as a tool module that fits nanobot's tool registry and tests. Resize remains a follow-up for any future WebUI terminal mirror.

## Proposed Tool API

Add `nanobot/agent/tools/freecode_session.py` with one tool named `freecode_session`.

Parameters:

- `action`: one of `start`, `send`, `poll`, `stop`, `list`.
- `session_id`: required for `send`, `poll`, and `stop`.
- `prompt`: optional initial task text for `start`.
- `chars`: text to write for `send`. This may include `\n`, escape sequences, or control characters.
- `working_dir`: optional workspace for `start`; defaults to the nanobot workspace.
- `command`: optional freecode executable path/name; defaults to `freecode` from PATH or config.
- `args`: optional extra CLI arguments for `start`.
- `yield_time_ms`: optional wait period before returning output; valid for `start`, `send`, and `poll` only.
- `wait_for`: optional text to wait for before returning; valid for `start`, `send`, and `poll` only.
- `wait_timeout_ms`: maximum wait for `wait_for`; valid only when `wait_for` is set.
- `max_output_chars`: output budget for each response; valid for every action that returns session output or session lists.

Actions:

- `start`: launches a PTY-backed freecode process, optionally writes the initial prompt plus newline, waits according to `yield_time_ms` or `wait_for`, and returns the session id plus initial output.
- `send`: writes `chars` to the PTY, waits according to `yield_time_ms` or `wait_for`, and returns new output.
- `poll`: reads buffered output without writing, optionally waiting according to `yield_time_ms` or `wait_for`.
- `stop`: terminates the PTY process and removes the session. It ignores `yield_time_ms`, `wait_for`, and `wait_timeout_ms`.
- `list`: returns active sessions visible to the current nanobot session. It ignores `yield_time_ms`, `wait_for`, and `wait_timeout_ms`.

The result should be a labeled plain-text block for LLM usability, not JSON. It must consistently include these labels when applicable:

- `session_id` for active sessions.
- `state`: running/exited/terminated.
- `elapsed_s` and `idle_s`.
- `output`: the output chunk, with truncation notice when applicable.
- `supervisor_note`: a reminder to ask the user before high-risk decisions when the session appears to be waiting for confirmation.

## PTY Session Manager

Implement a `FreecodeSessionManager` similar in shape to `ExecSessionManager`, but backed by PTY primitives.

Responsibilities:

- Allocate opaque 12-character lowercase hex session ids, matching the existing exec-session style. Treat ids as unguessable handles and never reveal sessions owned by another nanobot session.
- Enforce maximum concurrent freecode sessions.
- Track owner nanobot session key so one chat/session cannot accidentally control another user's terminal.
- Spawn `freecode` in the requested workspace with a terminal type such as `xterm-256color`.
- Continuously read PTY output into a bounded buffer.
- Support writes, polling, stop, and idle cleanup.
- Return output incrementally and truncate oversized chunks.

Implementation choice:

- Prefer Python PTY support that works on Unix-like systems first, because the current active environment is macOS and nanobot's shell tooling already has platform-aware paths.
- Use a narrow adapter class so Windows support can later use a different backend without changing the tool API.
- If PTY support is unavailable, `start` should fail clearly instead of silently falling back to plain pipes. Freecode supervision depends on terminal behavior.

## Supervisor Behavior Contract

The tool description must tell the nanobot agent how to behave as supervisor.

Default-autonomous decisions the supervisor may handle:

- Continue/yes prompts for routine file reads, edits, tests, and local commands.
- Choosing ordinary task execution options when the task intent is clear.
- Asking freecode to inspect errors, rerun tests, or revise code.

Supervisor mechanics:

- Poll until the terminal becomes idle, asks for input, exits, or reaches a configured wait timeout.
- Surface recent output clearly enough for the supervising agent to decide whether the next input is routine or requires user confirmation.

Decisions that must be escalated to the user:

- Deleting many files or destructive filesystem operations.
- `git reset --hard`, force push, branch deletion, or similar destructive git operations.
- Merging PRs, posting comments, or other externally visible actions beyond the requested workflow. Normal branch push and PR creation are allowed when the user has asked the supervisor to complete development work.
- Installing, removing, or upgrading dependencies.
- Entering credentials, logging into external services, or handling secrets.
- Running commands outside the workspace or changing global configuration.

The tool should not attempt to parse every possible prompt perfectly. Instead, it should expose recent output clearly and rely on the supervising agent's reasoning plus the explicit risk boundary above.

## Data Flow

1. User asks nanobot to perform a complex task through freecode.
2. Nanobot calls `freecode_session(action="start", prompt=..., working_dir=...)`.
3. The manager spawns a PTY running `freecode` and writes the initial prompt if provided.
4. Nanobot polls output, reads freecode's progress, and decides when to send follow-up input.
5. If freecode asks for low-risk confirmation, nanobot answers directly.
6. If freecode asks for high-risk confirmation, nanobot asks the user before sending input.
7. When freecode reports completion or exits, nanobot summarizes the result to the user and stops the session if still running.

## Error Handling

- Missing executable: return a clear error that `freecode` was not found and suggest configuring the command/path.
- PTY backend unavailable: return a clear unsupported-platform error.
- Session not found or owned by another nanobot session: return a not-found error without leaking other sessions.
- Startup failure: include the command, workspace, and short diagnostic output.
- Startup timeout: if the PTY starts but produces no usable output before `startup_timeout`, return a clear timeout error while leaving the session available for later polling unless the child process has already exited.
- `wait_for` timeout: return the output observed so far plus a clear note that the requested text was not seen before `wait_timeout_ms`.
- Idle timeout: terminate stale sessions and report that they were cleaned up.
- Output overflow: return the head and tail with an omitted-character count.

## Configuration

Add a small config section, likely under tool config, with defaults:

- `freecode_session.enable`: default true if PTY backend is available.
- `freecode_session.command`: default `freecode`.
- `freecode_session.max_sessions`: default 2.
- `freecode_session.idle_timeout`: default 1800 seconds.
- `freecode_session.startup_timeout`: default 30 seconds. This governs the initial wait for the PTY-backed process to produce usable startup output; it does not cap the lifetime of the session.

If `freecode_session.enable` is true on a platform without a PTY backend, the tool stays registered but `start` returns the clear unsupported-platform error described above. Auto-disable only controls the default config value; explicit enablement must not silently fall back to plain pipes.

The first implementation can keep config minimal and constructor-inject values in tests, as long as the public schema supports command path and session limits.

## Testing Plan

Unit tests should use a tiny mock CLI script instead of real freecode.

Required coverage:

- `start` launches the mock CLI and returns a session id.
- `send` writes to the PTY and returns echoed/processed output.
- `poll` returns incremental output without duplicating old chunks.
- `stop` terminates the process and removes the session.
- `list` shows active sessions and respects owner filtering.
- `send`, `poll`, and `stop` reject cross-owner session ids with the same not-found response used for missing sessions.
- `max_sessions` rejects starts beyond the configured concurrent-session limit.
- `wait_for` succeeds when text appears and returns a clear timeout note when text does not appear before `wait_timeout_ms`.
- output truncation reports omitted characters.
- idle cleanup terminates stale sessions.
- missing command returns a clear error.
- PTY-backend unavailable returns the unsupported-platform error and does not fall back to pipes.
- ANSI/control-character writes pass through the PTY path without being stripped before reaching the child process.
- tool description includes the default-autonomous and high-risk escalation contract. This is a description-lint test; runtime enforcement remains the supervising agent's responsibility, with the tool surfacing `supervisor_note` when output appears to be waiting for confirmation.

A focused integration-style test can run a mock interactive Python program that prints `ready`, reads a line, prints `got:<line>`, asks a yes/no question, and verifies the PTY path handles the interaction.

## Rollout

1. Add the tool and tests behind config.
2. Keep existing `exec` and `write_stdin` behavior unchanged.
3. Document basic usage in the tool description and, if needed later, in user-facing docs.
4. After the first version works, consider optional follow-ups: WebUI live terminal view, richer prompt detection, session transcript persistence, and multi-freecode orchestration.
