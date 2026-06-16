# FreeCode PTY Supervisor Design

## Summary

Add a dedicated `freecode_session` tool that lets a nanobot agent start and supervise a local `freecode` CLI terminal. The nanobot agent acts as the supervisor: it launches the terminal, sends prompts and follow-up input, monitors output, handles low-risk interactive choices autonomously, and asks the user only for high-risk decisions.

This follows the proven shape from the adjacent `freecode-web-submodule` implementation, where `PtyManager` launches the CLI through a PTY and exposes session operations for write, resize, stop, and output handling. Nanobot already has long-running `exec` sessions with stdin support, but `freecode_session` should be a dedicated tool because freecode needs terminal semantics, clearer lifecycle boundaries, and a specialized decision contract.

## Goals

- Let nanobot use `freecode` the same way the user does locally: start a terminal, type instructions, read output, and continue the conversation.
- Preserve real terminal behavior with PTY-backed execution rather than plain subprocess pipes.
- Give the supervising nanobot agent a small, explicit tool API for starting, sending input, polling output, listing sessions, and stopping sessions.
- Support default-autonomous supervision: the agent decides routine interactions, but asks the user before high-risk actions.
- Keep the first version focused on local CLI supervision, not WebUI terminal mirroring or multi-agent orchestration.

## Non-goals

- No WebUI terminal pane or browser-side live mirror in the first version.
- No freecode team/crew orchestration in the first version.
- No automatic push, PR creation, dependency upgrade, destructive git operation, or credential/login handling without user confirmation.
- No attempt to replace nanobot's existing `spawn` subagent tool; `freecode_session` is an external terminal supervisor, not an internal nanobot subagent.

## Existing Context

Nanobot has `exec` and `write_stdin` tools implemented around `ExecSessionManager`. They can run long-lived processes, write stdin, poll output, terminate sessions, and enforce owner session keys. This is useful for shells and simple interactive programs, but it does not provide PTY behavior.

The nearby freecode web implementation uses `web/server/pty-manager.mjs` with `@homebridge/node-pty-prebuilt-multiarch`. It spawns the freecode CLI with terminal settings, keeps one PTY per session, exposes write/resize/kill operations, and records last output timestamps. Nanobot should borrow the lifecycle shape, but implement it in Python as a tool module that fits nanobot's tool registry and tests.

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
- `yield_time_ms`: wait period before returning output.
- `wait_for`: optional text to wait for before returning.
- `wait_timeout_ms`: maximum wait for `wait_for`.
- `max_output_chars`: output budget for each response.

Actions:

- `start`: launches a PTY-backed freecode process, optionally writes the initial prompt plus newline, and returns the session id plus initial output.
- `send`: writes `chars` to the PTY, waits briefly, and returns new output.
- `poll`: reads buffered output without writing.
- `stop`: terminates the PTY process and removes the session.
- `list`: returns active sessions visible to the current nanobot session.

The result should be plain text for LLM usability, but consistently include:

- `session_id` for active sessions.
- process state: running/exited/terminated.
- elapsed time and idle time.
- output chunk, with truncation notice when applicable.
- a reminder to ask the user before high-risk decisions when the session appears to be waiting for confirmation.

## PTY Session Manager

Implement a `FreecodeSessionManager` similar in shape to `ExecSessionManager`, but backed by PTY primitives.

Responsibilities:

- Allocate short random session ids.
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
- Polling until the terminal becomes idle or asks for input.

Decisions that must be escalated to the user:

- Deleting many files or destructive filesystem operations.
- `git reset --hard`, force push, branch deletion, or similar destructive git operations.
- Pushing to remote, creating or merging PRs, posting comments, or other externally visible actions.
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
- Idle timeout: terminate stale sessions and report that they were cleaned up.
- Output overflow: return the head and tail with an omitted-character count.

## Configuration

Add a small config section, likely under tool config, with defaults:

- `freecode_session.enable`: default true if PTY backend is available.
- `freecode_session.command`: default `freecode`.
- `freecode_session.max_sessions`: default 2.
- `freecode_session.idle_timeout`: default 1800 seconds.
- `freecode_session.startup_timeout`: default 30 seconds.

The first implementation can keep config minimal and constructor-inject values in tests, as long as the public schema supports command path and session limits.

## Testing Plan

Unit tests should use a tiny mock CLI script instead of real freecode.

Required coverage:

- `start` launches the mock CLI and returns a session id.
- `send` writes to the PTY and returns echoed/processed output.
- `poll` returns incremental output without duplicating old chunks.
- `stop` terminates the process and removes the session.
- `list` shows active sessions and respects owner filtering.
- output truncation reports omitted characters.
- idle cleanup terminates stale sessions.
- missing command returns a clear error.
- tool description includes the default-autonomous and high-risk escalation contract.

A focused integration-style test can run a mock interactive Python program that prints `ready`, reads a line, prints `got:<line>`, asks a yes/no question, and verifies the PTY path handles the interaction.

## Rollout

1. Add the tool and tests behind config.
2. Keep existing `exec` and `write_stdin` behavior unchanged.
3. Document basic usage in the tool description and, if needed later, in user-facing docs.
4. After the first version works, consider optional follow-ups: WebUI live terminal view, richer prompt detection, session transcript persistence, and multi-freecode orchestration.
