"""PTY-backed FreeCode session supervision tool."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import Field

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import current_request_session_key
from nanobot.agent.tools.schema import (
    ArraySchema,
    IntegerSchema,
    StringSchema,
    tool_parameters_schema,
)
from nanobot.config.schema import Base
from nanobot.security.workspace_policy import WorkspaceBoundaryError, resolve_allowed_path

DEFAULT_YIELD_MS = 1000
MAX_YIELD_MS = 30_000
DEFAULT_WAIT_TIMEOUT_MS = 10_000
MAX_WAIT_TIMEOUT_MS = 120_000
DEFAULT_MAX_OUTPUT_CHARS = 10_000
MAX_OUTPUT_CHARS = 50_000

_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC_RE = re.compile(r"\x1b\][^\x07]*(?:\x07|\x1b\\)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t", "\x03"}
_CONFIRM_RE = re.compile(r"(?i)(continue\?\s*\[[yn]/?[yn]?\]|\[y/n\]|yes/no|proceed\?)")
_ALLOW_RE = re.compile(
    r"(?i)\b(pytest|ruff check|run tests?|read file|edit file|inspect errors?|rerun tests?|revise code)\b"
)
_DENY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "destructive git operation",
        re.compile(r"(?i)\bgit\s+(reset\s+--hard|push\s+--force|branch\s+-D|rebase|filter-branch)\b"),
    ),
    ("pull request merge", re.compile(r"(?i)\b(merge\s+PR|merge\s+pull request|gh\s+pr\s+merge)\b")),
    ("secret access", re.compile(r"(?i)(\.env\b|~/\.aws/credentials|~/\.ssh|id_rsa|private key|api[_-]?key|token)")),
    ("package or tool installation", re.compile(r"(?i)\b(brew|apt|pip\s+install\s+--user|npm\s+install\s+-g|npm\s+-g)\b")),
    ("privilege escalation", re.compile(r"(?i)\b(sudo|su\s+-|chmod\s+777|chown\b)")),
    ("remote script execution", re.compile(r"(?i)\b(curl|wget)\b.*\|\s*(bash|sh|python|ruby|perl)\b")),
    ("outside workspace write", re.compile(r"(?i)\b(/etc/|/var/|~/\.config|\.bashrc|\.zshrc|crontab|launchd|systemd)")),
    ("database mutation", re.compile(r"(?i)\b(drop\s+table|drop\s+database|truncate\s+table|migration|migrate)\b")),
    ("process kill", re.compile(r"(?i)\b(kill\s+-9|pkill|killall)\b")),
    ("non-loopback listener", re.compile(r"(?i)\b(listen|bind)\b.*\b(0\.0\.0\.0|::)\b")),
)


class FreecodeSessionToolConfig(Base):
    """Configuration for the FreeCode PTY supervisor tool."""

    enable: bool = True
    command: str = "freecode"
    allowed_args: list[str] = Field(default_factory=list)
    allowed_env_keys: list[str] = Field(default_factory=list)
    extra_workspace_roots: list[str] = Field(default_factory=list)
    max_sessions: int = Field(default=2, ge=1, le=8)
    idle_timeout: int = Field(default=900, ge=60, le=86_400)
    startup_timeout: int = Field(default=10, ge=1, le=120)


@dataclass(slots=True)
class SessionResult:
    session_id: str | None
    state: str
    output: str
    elapsed_s: float
    idle_s: float
    needs_user_confirmation: bool = False
    supervisor_note: str | None = None
    truncated_chars: int = 0


@dataclass(frozen=True, slots=True)
class PromptDecision:
    needs_user_confirmation: bool
    note: str | None = None


def clamp_int(value: int | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    return min(max(value, minimum), maximum)


def sanitize_output(text: str) -> str:
    text = _OSC_RE.sub("", text)
    text = _CSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


def validate_input_chars(chars: str | None) -> str | None:
    if not chars:
        return None
    for ch in chars:
        if ch in _ALLOWED_CONTROL_CHARS:
            continue
        code = ord(ch)
        if code < 0x20 or code == 0x7F or 0x80 <= code <= 0x9F:
            return "input contains unsupported control characters"
    return None


def truncate_output(output: str, max_output_chars: int) -> tuple[str, int]:
    if len(output) <= max_output_chars:
        return output, 0
    half = max_output_chars // 2
    omitted = len(output) - max_output_chars
    return (
        output[:half]
        + f"\n\n... ({omitted:,} chars truncated) ...\n\n"
        + output[-half:],
        omitted,
    )


def format_session_result(
    *,
    session_id: str | None,
    state: str,
    output: str,
    elapsed_s: float,
    idle_s: float,
    needs_user_confirmation: bool = False,
    supervisor_note: str | None = None,
    truncated_chars: int = 0,
) -> str:
    parts: list[str] = []
    if session_id:
        parts.append(f"session_id: {session_id}")
    parts.append(f"state: {state}")
    parts.append(f"elapsed_s: {elapsed_s:.1f}")
    parts.append(f"idle_s: {idle_s:.1f}")
    parts.append(f"needs_user_confirmation: {str(needs_user_confirmation).lower()}")
    if supervisor_note:
        parts.append(f"supervisor_note: {supervisor_note}")
    if truncated_chars:
        parts.append(f"truncated_chars: {truncated_chars}")
    parts.append("output:")
    parts.append(output or "(no output yet)")
    return "\n".join(parts)


def classify_prompt(output: str) -> PromptDecision:
    recent = sanitize_output(output)[-4000:]
    if not _CONFIRM_RE.search(recent):
        return PromptDecision(False)
    for label, pattern in _DENY_PATTERNS:
        if pattern.search(recent):
            return PromptDecision(True, f"User confirmation required: {label}.")
    if _ALLOW_RE.search(recent):
        return PromptDecision(False)
    return PromptDecision(True, "Unrecognized confirmation prompt; ask the user before replying.")


class PtyProcess(Protocol):
    def read_nonblocking(self, size: int = 4096, timeout: float = 0) -> str: ...
    def write(self, data: str) -> int: ...
    def terminate(self, force: bool = False) -> bool: ...
    def isalive(self) -> bool: ...


class PtyBackend(Protocol):
    def spawn(self, command: str, args: list[str], cwd: str, env: dict[str, str]) -> PtyProcess: ...


class PexpectBackend:
    def spawn(self, command: str, args: list[str], cwd: str, env: dict[str, str]) -> PtyProcess:
        import pexpect

        return pexpect.spawn(
            command,
            args,
            cwd=cwd,
            env=env,
            encoding="utf-8",
            codec_errors="replace",
            echo=False,
            dimensions=(40, 120),
        )


@dataclass(slots=True)
class _FreecodeSession:
    session_id: str
    process: PtyProcess
    command: str
    args: list[str]
    cwd: str
    owner_session_key: str | None
    started_at: float
    last_access: float
    pending_confirmation: bool = False
    chunks: list[str] | None = None

    def __post_init__(self) -> None:
        if self.chunks is None:
            self.chunks = []

    def is_alive(self) -> bool:
        return self.process.isalive()


class FreecodeSessionManager:
    def __init__(
        self,
        *,
        config: FreecodeSessionToolConfig | None = None,
        workspace: str = ".",
        backend: PtyBackend | None = None,
    ) -> None:
        self.config = config or FreecodeSessionToolConfig()
        self.workspace = str(Path(workspace).expanduser().resolve(strict=False))
        self.backend = backend or PexpectBackend()
        self._sessions: dict[str, _FreecodeSession] = {}
        self._lock = asyncio.Lock()

    async def start(
        self,
        *,
        prompt: str | None,
        working_dir: str | None,
        args: list[str] | None,
        yield_time_ms: int,
        wait_for: str | None,
        wait_timeout_ms: int,
        max_output_chars: int,
    ) -> SessionResult:
        async with self._lock:
            await self._cleanup_locked()
            if len(self._sessions) >= self.config.max_sessions:
                return self._error("maximum freecode sessions reached")
            resolved = self._resolve_working_dir(working_dir)
            if isinstance(resolved, str):
                return self._error(resolved)
            argv = self._validate_args(args or [])
            if isinstance(argv, str):
                return self._error(argv)
            command = self._resolve_command()
            if command is None:
                return self._error(f"freecode command not found: {self.config.command}")
            try:
                process = await asyncio.to_thread(
                    self.backend.spawn,
                    command,
                    argv,
                    str(resolved),
                    self._child_env(),
                )
            except Exception as exc:
                return self._error(f"failed to start freecode: {exc}")
            session_id = uuid.uuid4().hex[:12]
            now = time.monotonic()
            session = _FreecodeSession(
                session_id=session_id,
                process=process,
                command=command,
                args=argv,
                cwd=str(resolved),
                owner_session_key=current_request_session_key(),
                started_at=now,
                last_access=now,
            )
            self._sessions[session_id] = session
        if prompt:
            await self._write(session, prompt + "\n")
        return await self._poll_session(
            session,
            yield_time_ms=yield_time_ms,
            wait_for=wait_for,
            wait_timeout_ms=wait_timeout_ms,
            max_output_chars=max_output_chars,
        )

    async def send(
        self,
        session_id: str | None,
        *,
        chars: str | None,
        yield_time_ms: int,
        wait_for: str | None,
        wait_timeout_ms: int,
        max_output_chars: int,
    ) -> SessionResult:
        session = await self._get_owned(session_id)
        if session is None:
            return self._error("session not found")
        chars_error = validate_input_chars(chars)
        if chars_error:
            return self._error(chars_error)
        if chars:
            await self._write(session, chars)
        return await self._poll_session(
            session,
            yield_time_ms=yield_time_ms,
            wait_for=wait_for,
            wait_timeout_ms=wait_timeout_ms,
            max_output_chars=max_output_chars,
        )

    async def poll(
        self,
        session_id: str | None,
        *,
        yield_time_ms: int,
        wait_for: str | None,
        wait_timeout_ms: int,
        max_output_chars: int,
    ) -> SessionResult:
        session = await self._get_owned(session_id)
        if session is None:
            return self._error("session not found")
        return await self._poll_session(
            session,
            yield_time_ms=yield_time_ms,
            wait_for=wait_for,
            wait_timeout_ms=wait_timeout_ms,
            max_output_chars=max_output_chars,
        )

    async def list(self, *, max_output_chars: int) -> SessionResult:
        owner = current_request_session_key()
        async with self._lock:
            await self._cleanup_locked()
            rows = []
            for session in self._sessions.values():
                if owner != session.owner_session_key:
                    continue
                state = "running" if session.is_alive() else "exited"
                rows.append(f"{session.session_id} cwd={session.cwd} state={state}")
        output, truncated = truncate_output("\n".join(rows), max_output_chars)
        return SessionResult(None, "list", output, 0.0, 0.0, truncated_chars=truncated)

    async def stop(self, session_id: str | None, *, max_output_chars: int) -> SessionResult:
        session = await self._get_owned(session_id)
        if session is None:
            return self._error("session not found")
        await asyncio.to_thread(session.process.terminate, True)
        async with self._lock:
            self._sessions.pop(session.session_id, None)
        output, truncated = truncate_output(sanitize_output("Session terminated."), max_output_chars)
        return SessionResult(
            session.session_id,
            "terminated",
            output,
            self._elapsed(session),
            0.0,
            truncated_chars=truncated,
        )

    def _resolve_command(self) -> str | None:
        command = self.config.command
        command_path = Path(command).expanduser()
        if command_path.is_absolute():
            return str(command_path) if command_path.exists() else None
        return shutil.which(command)

    def _resolve_working_dir(self, working_dir: str | None) -> Path | str:
        try:
            return resolve_allowed_path(
                working_dir or self.workspace,
                workspace=self.workspace,
                allowed_root=self.workspace,
                extra_allowed_roots=self.config.extra_workspace_roots,
                strict=False,
            )
        except WorkspaceBoundaryError as exc:
            return str(exc)

    def _validate_args(self, args: list[str]) -> list[str] | str:
        allowed = set(self.config.allowed_args)
        for arg in args:
            if arg not in allowed:
                return f"disallowed freecode arg: {arg}"
        return list(args)

    def _child_env(self) -> dict[str, str]:
        env = {
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "TERM": os.environ.get("TERM", "xterm-256color"),
            "COLORTERM": os.environ.get("COLORTERM", "truecolor"),
            "PYTHONUNBUFFERED": "1",
        }
        for key in self.config.allowed_env_keys:
            value = os.environ.get(key)
            if value is not None:
                env[key] = value
        return env

    async def _get_owned(self, session_id: str | None) -> _FreecodeSession | None:
        if not session_id:
            return None
        owner = current_request_session_key()
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return None
        if owner != session.owner_session_key:
            return None
        return session

    async def _write(self, session: _FreecodeSession, chars: str) -> None:
        await asyncio.to_thread(session.process.write, chars)

    async def _poll_session(
        self,
        session: _FreecodeSession,
        *,
        yield_time_ms: int,
        wait_for: str | None,
        wait_timeout_ms: int,
        max_output_chars: int,
    ) -> SessionResult:
        wait_timed_out = False
        deadline = self._poll_deadline(wait_for, wait_timeout_ms, yield_time_ms)
        while True:
            await self._drain(session)
            combined = "".join(session.chunks or [])
            if wait_for and wait_for in combined:
                break
            if time.monotonic() >= deadline:
                wait_timed_out = wait_for is not None
                break
            if not wait_for and yield_time_ms <= 0:
                break
            await asyncio.sleep(0.02)
        raw = "".join(session.chunks or [])
        if session.chunks is not None:
            session.chunks.clear()
        now = time.monotonic()
        idle_s = max(0.0, now - session.last_access)
        sanitized = sanitize_output(raw)
        decision = classify_prompt(sanitized)
        session.pending_confirmation = decision.needs_user_confirmation
        session.last_access = now
        output, truncated = truncate_output(sanitized, max_output_chars)
        state = "running" if session.is_alive() else "exited"
        if state == "exited":
            async with self._lock:
                self._sessions.pop(session.session_id, None)
        note = decision.note
        if wait_timed_out:
            timeout_note = f"wait_for text not seen before timeout: {wait_for}"
            note = f"{note} {timeout_note}" if note else timeout_note
        return SessionResult(
            session.session_id,
            state,
            output,
            self._elapsed(session),
            idle_s,
            decision.needs_user_confirmation,
            note,
            truncated,
        )

    def _poll_deadline(
        self,
        wait_for: str | None,
        wait_timeout_ms: int,
        yield_time_ms: int,
    ) -> float:
        wait_ms = wait_timeout_ms if wait_for else yield_time_ms
        return time.monotonic() + wait_ms / 1000

    async def _drain(self, session: _FreecodeSession) -> None:
        while True:
            try:
                chunk = await asyncio.to_thread(session.process.read_nonblocking, 4096, 0)
            except Exception:
                break
            if not chunk:
                break
            assert session.chunks is not None
            session.chunks.append(chunk)

    async def _cleanup_locked(self) -> None:
        now = time.monotonic()
        stale = [
            sid
            for sid, session in self._sessions.items()
            if not session.pending_confirmation
            and now - session.last_access > self.config.idle_timeout
        ]
        for sid in stale:
            session = self._sessions.pop(sid)
            with suppress(Exception):
                await asyncio.to_thread(session.process.terminate, True)

    def _elapsed(self, session: _FreecodeSession) -> float:
        return max(0.0, time.monotonic() - session.started_at)

    def _error(self, message: str) -> SessionResult:
        return SessionResult(None, "error", sanitize_output(message), 0.0, 0.0)


@tool_parameters(
    tool_parameters_schema(
        required=["action"],
        action=StringSchema(
            "Session action.",
            enum=("start", "send", "poll", "stop", "list"),
        ),
        session_id=StringSchema("Session id for send, poll, and stop.", nullable=True),
        prompt=StringSchema("Initial task text to send after start.", nullable=True),
        chars=StringSchema(
            "Text to write for send. Allows printable text, CR/LF/TAB, and Ctrl-C.",
            nullable=True,
        ),
        working_dir=StringSchema("Workspace for start. Must stay inside allowed roots.", nullable=True),
        args=ArraySchema(StringSchema("Allowed FreeCode CLI argument."), nullable=True),
        yield_time_ms=IntegerSchema(
            description="Optional wait before returning output for start/send/poll.",
            minimum=0,
            maximum=MAX_YIELD_MS,
            nullable=True,
        ),
        wait_for=StringSchema("Optional text to wait for in start/send/poll output.", nullable=True),
        wait_timeout_ms=IntegerSchema(
            description="Maximum wait for wait_for.",
            minimum=0,
            maximum=MAX_WAIT_TIMEOUT_MS,
            nullable=True,
        ),
        max_output_chars=IntegerSchema(
            description="Maximum output characters to return.",
            minimum=1000,
            maximum=MAX_OUTPUT_CHARS,
            nullable=True,
        ),
    )
)
class FreecodeSessionTool(Tool):
    """Start and supervise local FreeCode CLI PTY sessions."""

    config_key = "freecode_session"
    _scopes = {"core", "subagent"}

    @classmethod
    def config_cls(cls):
        return FreecodeSessionToolConfig

    @classmethod
    def enabled(cls, ctx: Any) -> bool:
        return ctx.config.freecode_session.enable

    @classmethod
    def create(cls, ctx: Any) -> Tool:
        cfg = ctx.config.freecode_session
        return cls(config=cfg, workspace=ctx.workspace)

    def __init__(
        self,
        *,
        config: FreecodeSessionToolConfig | None = None,
        workspace: str = ".",
        manager: FreecodeSessionManager | None = None,
    ) -> None:
        self.config = config or FreecodeSessionToolConfig()
        self.workspace = workspace
        self._manager = manager or FreecodeSessionManager(config=self.config, workspace=self.workspace)

    @property
    def name(self) -> str:
        return "freecode_session"

    @property
    def description(self) -> str:
        return (
            "Start and supervise local FreeCode CLI PTY sessions. Auto-confirm only narrow, "
            "routine prompts inside the allowed workspace. Escalate unrecognized or high-risk "
            "prompts including destructive filesystem/git operations, PR merge, dependency or "
            "tool installation, secrets, sudo, remote script execution, non-workspace writes, "
            "network listeners, process kills, and database mutations. Results include "
            "needs_user_confirmation and supervisor_note when user confirmation is required."
        )

    async def execute(
        self,
        action: str,
        session_id: str | None = None,
        prompt: str | None = None,
        chars: str | None = None,
        working_dir: str | None = None,
        args: list[str] | None = None,
        yield_time_ms: int | None = None,
        wait_for: str | None = None,
        wait_timeout_ms: int | None = None,
        max_output_chars: int | None = None,
        **kwargs: Any,
    ) -> str:
        chars_error = validate_input_chars(chars)
        if chars_error:
            return f"Error: {chars_error}"
        output_limit = clamp_int(max_output_chars, DEFAULT_MAX_OUTPUT_CHARS, 1000, MAX_OUTPUT_CHARS)
        yield_ms = clamp_int(yield_time_ms, DEFAULT_YIELD_MS, 0, MAX_YIELD_MS)
        wait_ms = clamp_int(wait_timeout_ms, DEFAULT_WAIT_TIMEOUT_MS, 0, MAX_WAIT_TIMEOUT_MS)
        if action == "start":
            result = await self._manager.start(
                prompt=prompt,
                working_dir=working_dir,
                args=args,
                yield_time_ms=yield_ms,
                wait_for=wait_for,
                wait_timeout_ms=wait_ms,
                max_output_chars=output_limit,
            )
        elif action == "send":
            result = await self._manager.send(
                session_id,
                chars=chars,
                yield_time_ms=yield_ms,
                wait_for=wait_for,
                wait_timeout_ms=wait_ms,
                max_output_chars=output_limit,
            )
        elif action == "poll":
            result = await self._manager.poll(
                session_id,
                yield_time_ms=yield_ms,
                wait_for=wait_for,
                wait_timeout_ms=wait_ms,
                max_output_chars=output_limit,
            )
        elif action == "stop":
            result = await self._manager.stop(session_id, max_output_chars=output_limit)
        elif action == "list":
            result = await self._manager.list(max_output_chars=output_limit)
        else:
            return f"Error: unsupported freecode_session action: {action}"
        return format_session_result(
            session_id=result.session_id,
            state=result.state,
            output=result.output,
            elapsed_s=result.elapsed_s,
            idle_s=result.idle_s,
            needs_user_confirmation=result.needs_user_confirmation,
            supervisor_note=result.supervisor_note,
            truncated_chars=result.truncated_chars,
        )
