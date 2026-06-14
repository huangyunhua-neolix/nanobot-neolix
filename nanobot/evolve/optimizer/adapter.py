from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import BinaryIO

from pydantic import ValidationError

from nanobot.evolve.exceptions import ConfigError, OptimizerRunError
from nanobot.evolve.optimizer.schemas import OptimizerInput, OptimizerResult

_STREAM_CAP = 10 * 1024 * 1024
_TRUNCATED = b"<TRUNCATED>"
_ENV_ALLOWLIST = frozenset({"PATH", "HOME", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"})
_READ_CHUNK_SIZE = 64 * 1024


class _CappedStream:
    def __init__(self) -> None:
        self.buffer_ = bytearray()
        self.truncated_ = False

    def append(self, data: bytes) -> None:
        if not data:
            return
        remaining = _STREAM_CAP - len(self.buffer_)
        if remaining > 0:
            self.buffer_.extend(data[:remaining])
        if len(data) > remaining:
            self.truncated_ = True

    def bytes(self) -> bytes:
        captured = bytes(self.buffer_)
        if self.truncated_:
            return captured + _TRUNCATED
        return captured


class OptimizerAdapter:
    def __init__(self, *, optimizer_command: list[str]) -> None:
        if not optimizer_command:
            raise ConfigError("optimizer command must not be empty")
        self.optimizer_command_ = list(optimizer_command)

    def run(self, payload: OptimizerInput) -> OptimizerResult:
        optimizer_dir = Path(payload.output_dir)
        optimizer_dir.mkdir(parents=True, exist_ok=True)

        input_path = optimizer_dir / "optimizer_input.json"
        output_path = optimizer_dir / "optimizer_output.json"
        stdout_path = optimizer_dir / "stdout.txt"
        stderr_path = optimizer_dir / "stderr.txt"

        input_path.write_text(payload.model_dump_json(by_alias=True, indent=2), encoding="utf-8")

        command = self._resolve_command()
        stdout_capture = _CappedStream()
        stderr_capture = _CappedStream()

        try:
            process = subprocess.Popen(
                [*command, "--input", str(input_path), "--output", str(output_path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(optimizer_dir),
                env=self._build_env(),
            )
        except FileNotFoundError as exc:
            raise ConfigError(f"optimizer command not found: {command[0]}") from exc

        stdout_thread = self._start_drain_thread(process.stdout, stdout_capture)
        stderr_thread = self._start_drain_thread(process.stderr, stderr_capture)

        timed_out = False
        try:
            exit_code = process.wait(timeout=payload.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            exit_code = None
            process.wait()
        finally:
            stdout_thread.join()
            stderr_thread.join()
            stdout_path.write_bytes(stdout_capture.bytes())
            stderr_path.write_bytes(stderr_capture.bytes())

        if timed_out:
            raise OptimizerRunError(
                f"optimizer command timed out after {payload.timeout_seconds} seconds",
                run_dir=str(optimizer_dir),
                exit_code=None,
            )
        if exit_code != 0:
            raise OptimizerRunError(
                f"optimizer command exited with {exit_code}",
                run_dir=str(optimizer_dir),
                exit_code=exit_code,
            )
        if not output_path.exists():
            raise OptimizerRunError(
                "missing optimizer output", run_dir=str(optimizer_dir), exit_code=None
            )

        try:
            raw = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise OptimizerRunError(
                f"invalid optimizer output JSON: {exc}",
                run_dir=str(optimizer_dir),
                exit_code=None,
            ) from exc

        try:
            return OptimizerResult.model_validate(raw)
        except ValidationError as exc:
            structured_error = self._structured_error_message(raw)
            if structured_error:
                message = f"invalid optimizer output: {structured_error}"
            else:
                message = f"invalid optimizer output: {exc}"
            raise OptimizerRunError(message, run_dir=str(optimizer_dir), exit_code=None) from exc

    def _resolve_command(self) -> list[str]:
        executable = self.optimizer_command_[0]
        if not executable:
            raise ConfigError("optimizer command executable must not be empty")

        executable_path = Path(executable)
        if executable_path.is_absolute():
            if not executable_path.exists():
                raise ConfigError(f"optimizer command not found: {executable}")
            return [executable, *self.optimizer_command_[1:]]

        if not self._has_path_separator(executable):
            return list(self.optimizer_command_)

        if executable.startswith("./") or executable.startswith("../"):
            resolved_path = (Path.cwd() / executable_path).resolve()
            if not resolved_path.exists():
                raise ConfigError(f"optimizer command not found: {executable}")
            return [str(resolved_path), *self.optimizer_command_[1:]]

        raise ConfigError(f"ambiguous relative optimizer command: {executable}")

    @staticmethod
    def _has_path_separator(value: str) -> bool:
        return any(separator is not None and separator in value for separator in (os.sep, os.altsep))

    @staticmethod
    def _build_env() -> dict[str, str]:
        return {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}

    @staticmethod
    def _start_drain_thread(
        stream: BinaryIO | None, capture: _CappedStream
    ) -> threading.Thread:
        thread = threading.Thread(target=OptimizerAdapter._drain_stream, args=(stream, capture))
        thread.start()
        return thread

    @staticmethod
    def _drain_stream(stream: BinaryIO | None, capture: _CappedStream) -> None:
        if stream is None:
            return
        with stream:
            while True:
                chunk = stream.read(_READ_CHUNK_SIZE)
                if not chunk:
                    return
                capture.append(chunk)

    @staticmethod
    def _structured_error_message(raw: object) -> str | None:
        if not isinstance(raw, dict):
            return None
        error = raw.get("error")
        if not isinstance(error, dict):
            return None
        code = error.get("code")
        message = error.get("message")
        if not isinstance(code, str) or not isinstance(message, str):
            return None
        return f"{code}: {message}"
