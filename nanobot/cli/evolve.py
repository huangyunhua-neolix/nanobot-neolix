"""CLI surface for ``nanobot evolve`` (M4 t-16).

Pure ``argparse``-based subcommand registration + dispatch. The four
subcommands (``init`` / ``run`` / ``report`` / ``apply``) are wired through
``register(subparsers)``; ``dispatch(args)`` runs the handler bound by argparse
and maps exceptions to the exit codes pinned in the offline-evolution spec
(§4.6 / §5.3).

Handler-order invariant (MUST match ``EvolveError.MUST_PRECEDE`` documentary
hints in ``nanobot.evolve.exceptions``):

* ``ApplyTerminalError`` BEFORE ``ConfigError`` / ``ValueError`` — both share
  ``ValueError`` ancestry, and ``ApplyTerminalError`` carries the richer PR
  terminal-failure context that ``ConfigError``'s handler would silently
  swallow if reordered.
* ``JudgeError`` / ``ManifestPrivacyViolation`` / ``EvolveEnvironmentError``
  BEFORE bare ``RuntimeError`` — same MRO trap on the ``RuntimeError`` side.

The ``pydantic.ValidationError`` → ``ConfigError`` wrap happens at the
dispatch boundary so callers (including stubs in this module) can rely on
the structured ``ConfigError`` surface without each one re-implementing the
wrap. The wrap preserves ``__cause__`` via ``raise ... from exc``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError

from nanobot.evolve.exceptions import (
    ApplyTerminalError,
    ConfigError,
    EvolveEnvironmentError,
    JudgeError,
    ManifestPrivacyViolation,
)

# Exit codes — keep aligned with spec §4.6.
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_CONFIG = 2
EXIT_APPLY_TERMINAL = 3
EXIT_JUDGE = 4
EXIT_PRIVACY = 5
EXIT_ENV = 6


# ---------------------------------------------------------------------------
# Handler stubs
# ---------------------------------------------------------------------------


def run_init(args: argparse.Namespace) -> int:
    """Initialize a workspace skeleton on disk.

    M4 t-16 ships the CLI surface only; the on-disk skeleton initializer
    is owned by a follow-up task. Raising ``NotImplementedError`` keeps the
    contract honest until that lands.
    """
    raise NotImplementedError("evolve init is not wired yet (M4 follow-up)")


def run_run(args: argparse.Namespace) -> int:
    """Validate the workspace and dispatch a harness run.

    Spec carve-out for t-16: the full GEPA/judge pipeline requires fixtures
    (LLM keys, DSPy setup) that the CLI test layer cannot supply. We MUST
    minimally invoke ``nanobot.evolve.harness`` so the workspace path is
    validated through the same ``ConfigError`` channel the harness uses
    everywhere else.
    """
    # Local import keeps the CLI import path light and avoids dragging the
    # full harness import graph (DSPy, judges, gates) into ``--help``.
    from nanobot.evolve.harness import OfflineHarness

    workspace = Path(args.workspace).expanduser()
    if not workspace.exists():
        raise ConfigError(f"workspace does not exist: {workspace}")

    # OfflineHarness.__init__ itself raises ConfigError for non-directory
    # workspaces; this gives us the validation hook the spec demands without
    # requiring a real GEPA run.
    OfflineHarness(workspace=workspace)
    return EXIT_OK


def run_report(args: argparse.Namespace) -> int:
    """Print a structured report for a completed run."""
    raise NotImplementedError("evolve report is not wired yet (M4 follow-up)")


def run_apply(args: argparse.Namespace) -> int:
    """Apply a promoted run via PR deployment."""
    raise NotImplementedError("evolve apply is not wired yet (M4 follow-up)")


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    """Attach the ``evolve`` subcommand tree to a parent parser.

    The parent ``argparse`` parser owns the top-level command dispatch; this
    function only registers the ``evolve <sub>`` surface and binds each
    leaf's ``func=`` default so ``dispatch`` can run it.
    """
    evolve_parser: argparse.ArgumentParser = subparsers.add_parser(
        "evolve",
        help="Offline skill evolution (DSPy + GEPA + judge pool).",
        description="Offline self-evolution skeleton (M4).",
    )
    evolve_subs = evolve_parser.add_subparsers(
        dest="evolve_cmd",
        metavar="<subcommand>",
        required=True,
    )

    # init -----------------------------------------------------------------
    init_p = evolve_subs.add_parser("init", help="Initialize an evolve workspace.")
    init_p.add_argument(
        "--workspace",
        default=None,
        help="Workspace directory (defaults to ~/.nanobot/evolve/default).",
    )
    init_p.set_defaults(func=run_init)

    # run ------------------------------------------------------------------
    run_p = evolve_subs.add_parser("run", help="Run a single evolve cycle.")
    run_p.add_argument(
        "--tiers",
        default="A,C",
        help="Comma-separated eval tiers to run (default: A,C).",
    )
    run_p.add_argument(
        "--judge-pool",
        default=None,
        help="Optional judge-pool identifier override.",
    )
    run_p.add_argument(
        "--workspace",
        required=True,
        help="Workspace directory (required).",
    )
    run_p.set_defaults(func=run_run)

    # report ---------------------------------------------------------------
    report_p = evolve_subs.add_parser("report", help="Print a structured report for a run.")
    report_p.add_argument("run_id", help="Run identifier.")
    report_p.set_defaults(func=run_report)

    # apply ----------------------------------------------------------------
    apply_p = evolve_subs.add_parser("apply", help="Apply a promoted run via PR deployment.")
    apply_p.add_argument("run_id", help="Run identifier.")
    apply_p.set_defaults(func=run_apply)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(args: argparse.Namespace) -> int:
    """Run ``args.func(args)`` and map exceptions to spec-pinned exit codes.

    Two-layer exception handling:

    1. Inner ``try`` wraps ``pydantic.ValidationError`` into ``ConfigError``
       (spec §5.3 wrap rule). This MUST happen before exit-code mapping so
       the outer chain can see the wrapped exception type.
    2. Outer ``try`` maps each exception class to its spec exit code. The
       branch order honours ``EvolveError.MUST_PRECEDE`` — see module-level
       docstring for rationale.
    """
    try:
        try:
            handler = getattr(args, "func", None)
            if handler is None:
                # argparse with ``required=True`` should make this unreachable,
                # but belt-and-braces in case a future caller hands us a
                # Namespace built outside the registered parser tree.
                raise ConfigError("no evolve subcommand handler bound")
            result = handler(args)
        except ValidationError as exc:
            # Preserve traceback context for callers that inspect __cause__.
            raise ConfigError(f"invalid configuration: {exc}") from exc
    # --- spec §5.3 handler-order chain ------------------------------------
    # ApplyTerminalError MUST precede ConfigError/ValueError (shared MRO).
    except ApplyTerminalError as exc:
        _print_err("apply terminal", exc)
        return EXIT_APPLY_TERMINAL
    except ConfigError as exc:
        _print_err("config", exc)
        return EXIT_CONFIG
    except ValueError as exc:
        # Bare ValueError (non-Evolve) still maps to ConfigError exit slot
        # — caller passed bad input that didn't surface a typed exception.
        _print_err("config", exc)
        return EXIT_CONFIG
    # Specific RuntimeError subclasses MUST precede bare RuntimeError.
    except JudgeError as exc:
        _print_err("judge", exc)
        return EXIT_JUDGE
    except ManifestPrivacyViolation as exc:
        _print_err("privacy violation", exc)
        return EXIT_PRIVACY
    except EvolveEnvironmentError as exc:
        _print_err("environment", exc)
        return EXIT_ENV
    except RuntimeError as exc:
        _print_err("runtime", exc)
        return EXIT_RUNTIME

    if isinstance(result, int):
        return result
    return EXIT_OK


def _print_err(category: str, exc: BaseException) -> None:
    """Emit a one-line stderr diagnostic; full traceback is left to caller."""
    import sys

    print(f"evolve: {category} error: {exc}", file=sys.stderr)
