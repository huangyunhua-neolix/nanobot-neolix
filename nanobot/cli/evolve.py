"""CLI surface for ``nanobot evolve`` (M4 t-16).

Pure ``argparse``-based subcommand registration + dispatch. The four
subcommands (``init`` / ``run`` / ``report`` / ``apply``) are wired through
``register(subparsers)``; ``dispatch(args)`` runs the handler bound by argparse
and maps exceptions to the exit codes pinned in the offline-evolution spec
(§4.6 / §5.3).

Handler-order invariant (MUST match ``EvolveError.MUST_PRECEDE`` documentary
hints in ``nanobot.evolve.exceptions``):

* ``BaselineMismatch`` / ``ApplyTerminalError`` / ``ConfigError`` BEFORE
  bare ``ValueError`` — all three inherit ``ValueError``; the specific arms
  must fire first so each lands on its spec-pinned slot rather than the
  generic ``EXIT_CONFIG`` fallback.
* ``JudgeError`` / ``ManifestPrivacyViolation`` / ``EvolveEnvironmentError``
  / ``GateInternalError`` BEFORE bare ``RuntimeError`` — same MRO trap on
  the ``RuntimeError`` side. ``GateInternalError`` carries
  ``MUST_PRECEDE = {"RuntimeError"}``; spec §4.6 has no dedicated slot for
  it, so it currently maps to ``EXIT_CONFIG`` as a precondition-violation
  flavor (see CF-Drift1-a for the pending spec amendment).

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
    BaselineMismatch,
    ConfigError,
    EvolveEnvironmentError,
    EvolveExtraNotInstalled,
    GateInternalError,
    JudgeError,
    ManifestPrivacyViolation,
)

# Exit codes — normative per spec §4.6 (drift-R1 renumber).
EXIT_OK = 0
EXIT_RUNTIME = 1
EXIT_CONFIG = 2
EXIT_EXTRA_MISSING = 3  # EvolveExtraNotInstalled
EXIT_PRIVACY = 4  # ManifestPrivacyViolation
EXIT_JUDGE = 5  # JudgeError (retry-eligible per spec §4.6)
EXIT_FS = 6  # FileNotFoundError / FileExistsError / OSError
EXIT_BASELINE = 7  # BaselineMismatch (harness invariant — never retry)
EXIT_APPLY_TERMINAL = 8  # ApplyTerminalError


# ---------------------------------------------------------------------------
# run_init helpers
# ---------------------------------------------------------------------------

_REQUIRED_GITIGNORE_LINES = ("evals/runs/", "evals/self/", "evals/sessions/")

_EVALS_README = """\
# nanobot evolve evals

This directory holds evaluation artefacts for offline skill evolution (M4).

## Tiers

| Tier | Description |
|------|-------------|
| A    | Synthetic prompts with deterministic expected outputs. |
| C    | Golden traces recorded from real sessions (privacy-scrubbed). |

## Record format

Each record is a newline-delimited JSON file (`*.ndjson`) with fields:
`id`, `tier`, `prompt`, `expected`, `metadata`.

## Privacy

Tier-C records **must** be scrubbed of PII before commit. The harness gate
rejects manifests that fail `ManifestPrivacyViolation` checks.

## M4/M5 boundary

M4 scope: `synthetic/` and `golden/` eval authoring, `runs/` output capture,
GEPA scoring pipeline, judge-pool dispatch.

M5 scope: automated apply, PR deployment, and continuous self-evolution loop.
"""


def _default_workspace() -> Path:
    return Path("~/.nanobot/evolve/default").expanduser()


def _manifest_path_arg(args: argparse.Namespace) -> Path:
    manifest = getattr(args, "manifest", None)
    if not manifest:
        raise ConfigError("--manifest is required for this M4 skeleton command")
    return Path(manifest).expanduser()


def _none_if_empty(value: str | None) -> str:
    return value if value else "<none>"


def _format_manifest_report(manifest: object) -> str:
    candidates = (
        ",".join(manifest.candidate_hashes)  # type: ignore[union-attr]
        if manifest.candidate_hashes  # type: ignore[union-attr]
        else "<none>"
    )
    tiers = ",".join(
        f"{tier}={manifest.record_count_per_tier[tier]}"  # type: ignore[union-attr]
        for tier in sorted(manifest.record_count_per_tier)  # type: ignore[union-attr]
    )
    lines = [
        f"Run: {manifest.run_id}",  # type: ignore[union-attr]
        f"Skill: {manifest.skill_name}",  # type: ignore[union-attr]
        f"Status: {manifest.final_status}",  # type: ignore[union-attr]
        f"Promoted candidate: {_none_if_empty(manifest.promoted_candidate_hash)}",  # type: ignore[union-attr]
        f"Baseline: {manifest.baseline_hash}",  # type: ignore[union-attr]
        f"Candidates: {candidates}",
        "Gates:",
    ]
    lines.extend(
        f"- {gate.gate_name}: {gate.verdict}"
        for gate in manifest.gate_verdicts  # type: ignore[union-attr]
    )
    summary = manifest.judge_summary  # type: ignore[union-attr]
    lines.extend(
        [
            f"Tiers: {tiers}",
            "Judge summary: "
            f"records={summary.record_count}, "
            f"aggregate={summary.median_aggregate}, "
            f"process={summary.median_process}, "
            f"output={summary.median_output}, "
            f"token={summary.median_token}, "
            f"splits={summary.consensus_split_count}",
        ]
    )
    return "\n".join(lines)


def _workspace_from_arg(value: str | None) -> Path:
    if value is None:
        return _default_workspace()
    return Path(value).expanduser()


def _touch_if_missing(path: Path) -> None:
    if path.exists() and not path.is_file():
        raise FileExistsError(f"expected file path exists and is not a file: {path}")
    if not path.exists():
        path.write_text("", encoding="utf-8")


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _ensure_gitignore_patterns(path: Path) -> None:
    """Append any missing patterns from _REQUIRED_GITIGNORE_LINES.

    Uses exact-line semantics: a stripped, non-comment line must exactly
    match the pattern. Does not rewrite the file if all patterns are present.
    """
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    existing_non_comment = {
        line.strip()
        for line in existing_lines
        if line.strip() and not line.strip().startswith("#")
    }

    missing = [p for p in _REQUIRED_GITIGNORE_LINES if p not in existing_non_comment]
    if not missing:
        return

    current_content = "\n".join(existing_lines)
    if existing_lines and not current_content.endswith("\n"):
        current_content += "\n"
    addition = "\n".join(missing) + "\n"
    new_content = current_content + addition

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Handler stubs
# ---------------------------------------------------------------------------


def run_init(args: argparse.Namespace) -> int:
    """Initialize an M4 evolve workspace skeleton on disk."""
    workspace = _workspace_from_arg(args.workspace)
    if workspace.exists() and not workspace.is_dir():
        raise FileExistsError(f"workspace path exists and is not a directory: {workspace}")

    (workspace / "evals" / "synthetic").mkdir(parents=True, exist_ok=True)
    _touch_if_missing(workspace / "evals" / "synthetic" / ".gitkeep")
    (workspace / "evals" / "golden").mkdir(parents=True, exist_ok=True)
    _touch_if_missing(workspace / "evals" / "golden" / ".gitkeep")
    (workspace / "evals" / "runs").mkdir(parents=True, exist_ok=True)
    _ensure_gitignore_patterns(workspace / ".gitignore")
    _write_if_missing(workspace / "evals" / "README.md", _EVALS_README)
    return EXIT_OK


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
    """Print a deterministic text summary for a completed run manifest."""
    from nanobot.evolve.harness import load_manifest

    manifest = load_manifest(_manifest_path_arg(args))
    print(_format_manifest_report(manifest))
    return EXIT_OK


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
    report_p.add_argument("run_id", nargs="?", default=None, help="Run identifier (M5 prefix resolution).")
    report_p.add_argument("--manifest", default=None, help="Run manifest JSON path.")
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
    # --- spec §4.6 handler-order chain ------------------------------------
    # Most-specific first. ValueError-subclasses (BaselineMismatch,
    # ApplyTerminalError, ConfigError) MUST precede `except ValueError`.
    # RuntimeError-subclasses (JudgeError, ManifestPrivacyViolation,
    # EvolveEnvironmentError, GateInternalError) MUST precede the bare
    # `except RuntimeError`.
    except EvolveExtraNotInstalled as exc:
        _print_err("extra missing", exc)
        return EXIT_EXTRA_MISSING
    except ManifestPrivacyViolation as exc:
        _print_err("privacy violation", exc)
        return EXIT_PRIVACY
    except JudgeError as exc:
        _print_err("judge", exc)
        return EXIT_JUDGE
    except BaselineMismatch as exc:
        # MUST precede ConfigError / ValueError (inherits ValueError).
        # Harness invariant; never retry.
        _print_err("baseline mismatch", exc)
        return EXIT_BASELINE
    except ApplyTerminalError as exc:
        # MUST precede ConfigError / ValueError (shared MRO via ValueError).
        _print_err("apply terminal", exc)
        return EXIT_APPLY_TERMINAL
    except GateInternalError as exc:
        # Spec §4.6 has no dedicated slot for GateInternalError; map to
        # EXIT_CONFIG as a precondition-violation flavor pending spec
        # amendment (see CF-Drift1-a). MUST precede bare RuntimeError.
        _print_err("gate-internal", exc)
        return EXIT_CONFIG
    except EvolveEnvironmentError as exc:
        # Per spec §5.3 line 2562: environment errors map to EXIT_CONFIG.
        _print_err("environment", exc)
        return EXIT_CONFIG
    except ConfigError as exc:
        _print_err("config", exc)
        return EXIT_CONFIG
    except (FileNotFoundError, FileExistsError, OSError) as exc:
        _print_err("filesystem", exc)
        return EXIT_FS
    except ValueError as exc:
        # Bare ValueError (non-Evolve) still maps to ConfigError exit slot
        # — caller passed bad input that didn't surface a typed exception.
        _print_err("config", exc)
        return EXIT_CONFIG
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
