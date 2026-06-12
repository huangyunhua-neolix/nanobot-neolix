"""Tests for ``nanobot.cli.evolve`` (M4 t-16).

Covers:
  * argparse surface — subcommands, required flags, defaults
  * dispatch handler-order chain (spec §5.3) — ApplyTerminalError before
    ConfigError/ValueError; specific RuntimeError subclasses before bare
    RuntimeError
  * ``pydantic.ValidationError`` → ``ConfigError`` wrap path
  * exit-code mapping (spec §4.6)
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from nanobot.cli import evolve as evolve_cli
from nanobot.evolve.exceptions import (
    ApplyTerminalError,
    ConfigError,
    EvolveEnvironmentError,
    GateInternalError,
    JudgeError,
    ManifestPrivacyViolation,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build a top-level argparse parser with the evolve tree registered."""
    parser = argparse.ArgumentParser(prog="nanobot")
    subs = parser.add_subparsers(dest="command", required=True)
    evolve_cli.register(subs)
    return parser


def _ns_with_handler(handler) -> argparse.Namespace:
    """Build a Namespace whose ``func`` callable is the supplied handler."""
    ns = argparse.Namespace()
    ns.func = handler
    return ns


# ---------------------------------------------------------------------------
# argparse surface
# ---------------------------------------------------------------------------


def test_evolve_help_lists_all_subcommands(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evolve", "--help"])
    out = capsys.readouterr().out
    for sub in ("init", "run", "report", "apply"):
        assert sub in out


def test_run_help_shows_flags(capsys):
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evolve", "run", "--help"])
    out = capsys.readouterr().out
    assert "--tiers" in out
    assert "--judge-pool" in out
    assert "--workspace" in out


def test_run_tiers_default_is_a_c():
    parser = _build_parser()
    args = parser.parse_args(["evolve", "run", "--workspace", "/tmp"])
    assert args.tiers == "A,C"
    assert args.judge_pool is None
    assert args.workspace == "/tmp"


def test_run_requires_workspace():
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["evolve", "run"])


def test_init_workspace_optional():
    parser = _build_parser()
    args = parser.parse_args(["evolve", "init"])
    assert args.workspace is None
    args2 = parser.parse_args(["evolve", "init", "--workspace", "/tmp/ws"])
    assert args2.workspace == "/tmp/ws"


def test_report_takes_positional_run_id():
    parser = _build_parser()
    args = parser.parse_args(["evolve", "report", "run-abc"])
    assert args.run_id == "run-abc"


def test_apply_takes_positional_run_id():
    parser = _build_parser()
    args = parser.parse_args(["evolve", "apply", "run-xyz"])
    assert args.run_id == "run-xyz"


# ---------------------------------------------------------------------------
# Dispatch — exit-code mapping (spec §4.6)
# ---------------------------------------------------------------------------


def test_dispatch_success_returns_zero():
    ns = _ns_with_handler(lambda _a: 0)
    assert evolve_cli.dispatch(ns) == 0


def test_dispatch_handler_returns_none_treated_as_zero():
    ns = _ns_with_handler(lambda _a: None)
    assert evolve_cli.dispatch(ns) == 0


def test_dispatch_config_error_maps_to_2():
    def boom(_a):
        raise ConfigError("bad config")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 2


def test_dispatch_apply_terminal_maps_to_3():
    def boom(_a):
        raise ApplyTerminalError(
            "pr fail",
            final_status="apply_failed",
            manifest_path=Path("/tmp/m.json"),
        )

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 3


def test_dispatch_judge_error_maps_to_4():
    def boom(_a):
        raise JudgeError("judge unreachable")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 4


def test_dispatch_privacy_violation_maps_to_5():
    def boom(_a):
        raise ManifestPrivacyViolation(
            "leak",
            violated_invariant="no-pii",
        )

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 5


def test_dispatch_environment_error_maps_to_6():
    def boom(_a):
        raise EvolveEnvironmentError("missing dspy")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 6


def test_dispatch_bare_runtime_error_maps_to_1():
    def boom(_a):
        raise RuntimeError("unexpected")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 1


def test_dispatch_bare_value_error_maps_to_config_exit():
    def boom(_a):
        raise ValueError("bad input")

    # ValueError that is NOT a typed Evolve exception still goes to the
    # config-error exit slot (caller passed bad input).
    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 2


# ---------------------------------------------------------------------------
# Dispatch — handler-order invariant (spec §5.3)
# ---------------------------------------------------------------------------


def test_apply_terminal_precedes_config_error_when_both_inheritances_exist():
    """Synthetic exception that subclasses both ApplyTerminalError + ConfigError.

    Proves the ``except ApplyTerminalError`` arm fires first, matching the
    ``MUST_PRECEDE`` invariant declared in
    ``nanobot.evolve.exceptions.ApplyTerminalError``.
    """

    class DualError(ApplyTerminalError, ConfigError):
        # ApplyTerminalError requires kw-only fields; we redeclare to satisfy
        # EvolveError.__init_subclass__ invariant 2.
        from typing import ClassVar

        STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset(
            {"final_status", "manifest_path"}
        )

    def boom(_a):
        raise DualError(
            "dual",
            final_status="apply_failed",
            manifest_path=Path("/tmp/m.json"),
        )

    # If ConfigError caught it first we'd see 2; ApplyTerminalError must
    # win and yield 3.
    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 3


def test_judge_error_precedes_bare_runtime_error():
    """JudgeError is a RuntimeError; its specific arm must fire first."""

    def boom(_a):
        raise JudgeError("judge failure")

    # If bare RuntimeError caught first we'd see 1; specific arm yields 4.
    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 4


def test_privacy_violation_precedes_bare_runtime_error():
    def boom(_a):
        raise ManifestPrivacyViolation("leak", violated_invariant="no-pii")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 5


def test_environment_error_precedes_bare_runtime_error():
    def boom(_a):
        raise EvolveEnvironmentError("env missing")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 6


def test_dispatch_gate_internal_error_maps_to_7():
    """``GateInternalError`` MUST surface on its own exit slot (T16-FIX-1).

    Before the explicit arm landed, ``GateInternalError(EvolveError,
    RuntimeError)`` silently degraded to ``EXIT_RUNTIME=1`` via the bare
    ``except RuntimeError`` arm, violating the ``MUST_PRECEDE={"RuntimeError"}``
    invariant declared on the exception class.
    """

    def boom(_a):
        raise GateInternalError("tier-C records missing for gate eval")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == evolve_cli.EXIT_GATE_INTERNAL
    assert evolve_cli.EXIT_GATE_INTERNAL == 7


def test_gate_internal_error_precedes_bare_runtime_error_via_dual_inheritance():
    """Pin handler-order against a future swap of the two RuntimeError arms.

    A subclass that ISA both ``GateInternalError`` (specific) and
    ``RuntimeError`` (bare) MUST hit the gate-internal arm first. If a
    refactor moved ``except RuntimeError`` above ``except GateInternalError``
    the result would silently become ``EXIT_RUNTIME=1``.
    """
    from typing import ClassVar

    class _GateAndRuntimeError(GateInternalError):
        # EvolveError.__init_subclass__ requires explicit STRUCTURED_KWARGS
        # redeclaration when a parent declares it.
        STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()

    def boom(_a):
        raise _GateAndRuntimeError("synthetic dual-inheritance probe")

    assert evolve_cli.dispatch(_ns_with_handler(boom)) == 7


# ---------------------------------------------------------------------------
# Dispatch — pydantic.ValidationError → ConfigError wrap (spec §5.3)
# ---------------------------------------------------------------------------


class _ToyModel(BaseModel):
    n: int


def test_validation_error_is_wrapped_to_config_error_exit():
    def boom(_a):
        # Real ValidationError construction goes through pydantic itself.
        _ToyModel(n="not-an-int")

    rc = evolve_cli.dispatch(_ns_with_handler(boom))
    assert rc == 2  # ConfigError exit code


def test_validation_error_wrap_preserves_cause():
    """The ValidationError → ConfigError raise MUST chain ``__cause__``."""
    captured: dict[str, BaseException] = {}

    original_print = evolve_cli._print_err

    def capturing_print(category, exc):
        captured["category"] = category
        captured["exc"] = exc
        return original_print(category, exc)

    evolve_cli._print_err = capturing_print  # type: ignore[assignment]
    try:

        def boom(_a):
            _ToyModel(n="not-an-int")

        evolve_cli.dispatch(_ns_with_handler(boom))
    finally:
        evolve_cli._print_err = original_print  # type: ignore[assignment]

    assert captured["category"] == "config"
    exc = captured["exc"]
    assert isinstance(exc, ConfigError)
    assert isinstance(exc.__cause__, ValidationError)


# ---------------------------------------------------------------------------
# Dispatch — defensive: handler missing
# ---------------------------------------------------------------------------


def test_dispatch_missing_handler_raises_config_error_exit():
    ns = argparse.Namespace()  # no ``func`` attribute
    # Bare ConfigError raise inside dispatch is caught by the dispatch chain
    # and mapped to exit 2 — assert the public contract holds.
    assert evolve_cli.dispatch(ns) == 2


# ---------------------------------------------------------------------------
# run_run — workspace validation
# ---------------------------------------------------------------------------


def test_run_run_missing_workspace_raises_config_error(tmp_path):
    parser = _build_parser()
    missing = tmp_path / "does-not-exist"
    args = parser.parse_args(["evolve", "run", "--workspace", str(missing)])
    rc = evolve_cli.dispatch(args)
    assert rc == 2  # ConfigError exit code


def test_run_run_valid_workspace_returns_zero(tmp_path):
    parser = _build_parser()
    args = parser.parse_args(["evolve", "run", "--workspace", str(tmp_path)])
    rc = evolve_cli.dispatch(args)
    assert rc == 0


def test_run_init_not_implemented_raises_runtime_exit():
    parser = _build_parser()
    args = parser.parse_args(["evolve", "init"])
    # NotImplementedError subclasses RuntimeError → exit 1.
    rc = evolve_cli.dispatch(args)
    assert rc == 1


def test_run_report_not_implemented_raises_runtime_exit():
    """Mirror of init coverage — report stub MUST land on EXIT_RUNTIME (T16-FIX-2)."""
    parser = _build_parser()
    args = parser.parse_args(["evolve", "report", "run-abc"])
    rc = evolve_cli.dispatch(args)
    assert rc == evolve_cli.EXIT_RUNTIME


def test_run_apply_not_implemented_raises_runtime_exit():
    """Mirror of init coverage — apply stub MUST land on EXIT_RUNTIME (T16-FIX-2)."""
    parser = _build_parser()
    args = parser.parse_args(["evolve", "apply", "run-xyz"])
    rc = evolve_cli.dispatch(args)
    assert rc == evolve_cli.EXIT_RUNTIME


# ---------------------------------------------------------------------------
# typer-shim integration (T16-FIX-2)
#
# nanobot/cli/commands.py registers an ``evolve`` typer command that
# prepends ``"evolve"`` to ctx.args, runs argparse register/dispatch, and
# translates the int return code into ``typer.Exit(rc)``. The shim is the
# actual user surface (``nanobot evolve ...``) — exercise it directly.
# ---------------------------------------------------------------------------


def test_typer_shim_evolve_help_lists_subcommands():
    """The typer shim must hand --help through to argparse and exit cleanly."""
    from typer.testing import CliRunner

    from nanobot.cli.commands import app

    runner = CliRunner()
    result = runner.invoke(app, ["evolve", "--help"])
    # argparse --help exits 0 via SystemExit; typer translates to exit_code 0.
    assert result.exit_code == 0
    # argparse writes --help to stdout; CliRunner captures via .output.
    out = result.output
    for sub in ("init", "run", "report", "apply"):
        assert sub in out, f"subcommand {sub!r} missing from help: {out!r}"


def test_typer_shim_propagates_dispatch_exit_code(monkeypatch):
    """Synthetic ``dispatch`` override returning 4 must surface as exit_code 4."""
    from typer.testing import CliRunner

    from nanobot.cli import evolve as _evolve
    from nanobot.cli.commands import app

    monkeypatch.setattr(_evolve, "dispatch", lambda _args: 4)

    runner = CliRunner()
    # init is a registered subcommand with no required flags so argparse
    # parsing succeeds; the patched dispatch then returns 4.
    result = runner.invoke(app, ["evolve", "init"])
    assert result.exit_code == 4


def test_typer_shim_run_missing_workspace_returns_config_exit(tmp_path):
    """End-to-end: nonexistent workspace path → ConfigError → exit 2."""
    from typer.testing import CliRunner

    from nanobot.cli.commands import app

    missing = tmp_path / "nope"
    runner = CliRunner()
    result = runner.invoke(app, ["evolve", "run", "--workspace", str(missing)])
    assert result.exit_code == evolve_cli.EXIT_CONFIG


def test_typer_shim_run_valid_workspace_returns_zero(tmp_path):
    """End-to-end: valid workspace dir → run_run → exit 0."""
    from typer.testing import CliRunner

    from nanobot.cli.commands import app

    runner = CliRunner()
    result = runner.invoke(app, ["evolve", "run", "--workspace", str(tmp_path)])
    assert result.exit_code == evolve_cli.EXIT_OK
