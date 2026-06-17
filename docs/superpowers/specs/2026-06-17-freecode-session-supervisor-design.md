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
- `chars`: text to write for `send`. The tool accepts printable text plus CR/LF/TAB by default; Ctrl-C may be allowed as an explicit interruption path. Other raw control characters and escape sequences are rejected unless a future config explicitly enables raw mode.
- `working_dir`: optional workspace for `start`; defaults to the nanobot workspace. The resolved real path must stay inside the configured workspace allow-roots and must reject symlink escapes.
- `args`: optional extra freecode CLI arguments for `start`, validated against an allow-list.
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
- `output`: sanitized output chunk, with truncation notice when applicable. Strip or escape ANSI CSI/OSC sequences and C0/C1 control characters before returning to the LLM or chat channel, while preserving line breaks and tabs.
- `needs_user_confirmation`: `true` when the recent output appears to ask for a decision outside the small auto-confirm allow-list.
- `supervisor_note`: a reminder to ask the user before high-risk decisions when the session appears to be waiting for confirmation.

## PTY Session Manager

Implement a `FreecodeSessionManager` similar in shape to `ExecSessionManager`, but backed by PTY primitives.

Responsibilities:

- Allocate opaque 12-character lowercase hex session ids, matching the existing exec-session style. Treat ids as unguessable handles and never reveal sessions owned by another nanobot session.
- Enforce maximum concurrent freecode sessions.
- Track owner nanobot session key from `current_request_session_key()` so one chat/session cannot accidentally control another user's terminal. `list` only returns sessions owned by the current key, and `send`, `poll`, and `stop` treat cross-owner ids exactly like missing ids.
- Spawn only the configured `freecode_session.command` path in the requested workspace. The caller cannot override the executable path through tool parameters.
- Resolve `working_dir` with realpath and require it to stay inside configured workspace allow-roots: the current nanobot workspace plus any explicit extra roots from config.
- Continuously read PTY output into a bounded in-memory ring buffer. This keeps the first version simple while leaving transcript persistence or WebUI mirroring as later append-only sinks.
- Support writes, polling, stop, and idle cleanup. Pause idle cleanup while the session has a pending user-confirmation escalation.
- Return sanitized output incrementally and truncate oversized chunks.

Implementation choice:

- Use `pexpect` for the first PTY backend. It gives a mature Python PTY abstraction with expect/read/write semantics that map directly to `wait_for`, while keeping the manager API independent from the backend. If dependency policy blocks adding `pexpect`, the implementation plan must explicitly switch to a stdlib `pty` + `selectors` backend before coding starts.
- Define a narrow `PtyBackend` adapter with `spawn()`, `read()`, `write()`, `terminate()`, and `is_alive()` so Windows support or a stdlib backend can be added later without changing the tool API.
- If PTY support is unavailable, `start` should fail clearly instead of silently falling back to plain pipes. Freecode supervision depends on terminal behavior.

## Supervisor Behavior Contract

The tool description must tell the nanobot agent how to behave as supervisor.

Default-autonomous decisions are deliberately narrow. The supervisor may auto-confirm only when the recent output matches a small allow-list of routine prompts, such as continuing a local file read/edit/test inside the allowed workspace or asking freecode to inspect errors, rerun tests, or revise code. The prompt classifier must inspect the action description immediately preceding the confirmation prompt, not just the final `Continue?` line.

Default behavior for unrecognized prompts is escalate, not auto-yes. The tool should set `needs_user_confirmation: true` and include a `supervisor_note` when the recent prompt falls outside the allow-list or matches any deny-list pattern.

Supervisor mechanics:

- Poll until the terminal becomes idle, asks for input, exits, or reaches a configured wait timeout.
- Surface recent sanitized output clearly enough for the supervising agent to decide whether the next input is routine or requires user confirmation.
- Apply a deny-list to the recent output before auto-confirming. Deny-list matches always require user confirmation.

Decisions that must be escalated to the user:

- Destructive filesystem operations, including recursive deletes, mass rewrites, or operations outside the requested files.
- Destructive git operations: `git reset --hard`, force push, branch deletion, history rewrite, or similar.
- Merging PRs, posting comments, or other externally visible actions beyond the requested workflow. Normal branch push and PR creation are allowed when the user has asked the supervisor to complete development work.
- Installing, removing, or upgrading dependencies or tools, including package-manager commands such as `brew`, `apt`, `pip --user`, or `npm -g`.
- Entering credentials, logging into external services, reading secrets, or printing environment variables/dotfiles such as `.env`, `~/.aws/credentials`, `~/.ssh/**`, private keys, or tokens.
- Running commands outside the workspace, changing global configuration, writing shell startup files, writing `~/.config/**`, crontabs, launchd/systemd files, or other persistence locations.
- Privilege escalation (`sudo`, `su`, setuid changes), ownership/permission broadening (`chmod 777`, broad `chmod +x`, `chown`), or killing processes the supervisor did not start.
- Piping remote content into interpreters (`curl|bash`, `wget|sh`, similar), opening non-loopback listeners, or initiating unexplained network egress.
- Database or migration commands that can mutate or drop persistent data.

The tool is not a full policy engine; the supervising agent still makes final decisions. The tool must, however, provide conservative prompt classification signals (`needs_user_confirmation` and `supervisor_note`) so the agent does not treat arbitrary `yes/no` prompts as safe.

## Data Flow

1. User asks nanobot to perform a complex task through freecode.
2. Nanobot calls `freecode_session(action="start", prompt=..., working_dir=...)`.
3. The manager validates the workspace allow-root, spawns a PTY running the configured `freecode`, and writes the initial prompt if provided.
4. Nanobot polls sanitized output, reads freecode's progress, and decides when to send follow-up input.
5. If freecode asks for a prompt that matches the narrow allow-list and no deny-list pattern appears in recent output, nanobot may answer directly.
6. If freecode asks for a high-risk or unrecognized confirmation, nanobot asks the user before sending input; idle cleanup pauses while this escalation is pending.
7. When freecode reports completion or exits, nanobot summarizes the result to the user and stops the session if still running.

## Error Handling

- Missing executable: return a clear error that `freecode` was not found and suggest configuring the command/path.
- PTY backend unavailable: return a clear unsupported-platform error.
- Session not found or owned by another nanobot session: return a not-found error without leaking other sessions.
- Workspace outside allow-roots or symlink escape: reject before spawning and return a clear workspace-boundary error.
- Disallowed CLI arg or caller-supplied executable override: reject before spawning.
- Startup failure: include the configured command, workspace, and short sanitized diagnostic output.
- Startup timeout: if the PTY starts but produces no usable output before `startup_timeout`, return a clear timeout error while leaving the session available for later polling unless the child process has already exited.
- `wait_for` timeout: return the output observed so far plus a clear note that the requested text was not seen before `wait_timeout_ms`.
- Idle timeout: terminate stale sessions and report that they were cleaned up.
- Output overflow: return the head and tail with an omitted-character count.

## Configuration

Add a small config section, likely under tool config, with defaults:

- `freecode_session.enable`: default true if PTY backend is available.
- `freecode_session.command`: default `freecode`; resolved from config/PATH at startup and not overrideable per tool call.
- `freecode_session.allowed_args`: default allow-list for safe freecode CLI flags needed by this tool.
- `freecode_session.extra_workspace_roots`: default empty list of additional allowed realpaths.
- `freecode_session.max_sessions`: default 2.
- `freecode_session.idle_timeout`: default 900 seconds. Idle cleanup pauses while a user-confirmation escalation is pending.
- `freecode_session.startup_timeout`: default 10 seconds. This governs the initial wait for the PTY-backed process to produce usable startup output; it does not cap the lifetime of the session.

If `freecode_session.enable` is true on a platform without a PTY backend, the tool stays registered but `start` returns the clear unsupported-platform error described above. Auto-disable only controls the default config value; explicit enablement must not silently fall back to plain pipes.

The first implementation can keep config minimal and constructor-inject values in tests, as long as the public schema supports command path and session limits.

## Rejected Alternatives

- Extending `exec` with `pty=true`: rejected for the first version because the supervision flow needs stricter workspace confinement, command pinning, prompt classification, sanitized output, and a freecode-specific risk contract. Keeping it separate avoids expanding the blast radius of the general shell tool.
- Plain subprocess pipes: rejected because freecode is a terminal application and may render prompts, ANSI output, or interactive behavior differently without a PTY.

## Testing Plan

Unit tests should use a tiny mock CLI script instead of real freecode.

Required coverage:

- `start` launches the mock CLI and returns a session id.
- `send` writes to the PTY and returns echoed/processed output.
- `poll` returns incremental output without duplicating old chunks.
- `stop` terminates the process and removes the session.
- `list` shows only sessions owned by the current nanobot session key.
- `send`, `poll`, and `stop` reject cross-owner session ids with the same not-found response used for missing sessions.
- `start` rejects workspaces outside allow-roots, including symlink escapes.
- `start` uses the configured freecode command and rejects caller-supplied executable overrides or disallowed args.
- `max_sessions` rejects starts beyond the configured concurrent-session limit.
- `wait_for` succeeds when text appears and returns a clear timeout note when text does not appear before `wait_timeout_ms`.
- output truncation reports omitted characters.
- output sanitization strips or escapes ANSI CSI/OSC and unsafe control characters before returning to the LLM/chat channel.
- idle cleanup terminates stale sessions, but pauses while `needs_user_confirmation` is pending.
- missing command returns a clear error.
- PTY-backend unavailable returns the unsupported-platform error and does not fall back to pipes.
- allowed control-character writes (CR/LF/TAB and explicit Ctrl-C interrupt) pass through, while other raw control/escape sequences are rejected by default.
- prompt-classification tests cover at least one allow-listed low-risk prompt and deny/escalate examples for `git reset --hard`, PR merge, secret read, package install, `sudo`, `curl|bash`, non-workspace write, and database mutation.
- tool description includes the default-autonomous and high-risk escalation contract. This is a description-lint test; runtime enforcement remains the supervising agent's responsibility, with the tool surfacing `needs_user_confirmation` and `supervisor_note` when output appears to be waiting for confirmation.

A focused integration-style test can run a mock interactive Python program that prints `ready`, reads a line, prints `got:<line>`, asks a yes/no question, and verifies the PTY path handles the interaction.

## Rollout

1. Add the tool and tests behind config.
2. Keep existing `exec` and `write_stdin` behavior unchanged.
3. Document basic usage in the tool description and, if needed later, in user-facing docs.
4. After the first version works, consider optional follow-ups: WebUI live terminal view, richer prompt detection, session transcript persistence, and multi-freecode orchestration.
