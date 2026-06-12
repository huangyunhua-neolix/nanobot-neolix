"""PR-only deploy helpers — spec §8.

Three thin pure functions used by ``nanobot evolve apply`` (t-14 / pipeline)
to materialise the PR-only deploy contract:

* :func:`build_branch_name` — deterministic ``evolve/<run_id>-<skill>-<sha>`` form
  per §8.1 Branch naming.
* :func:`assert_not_main` — hard refusal to push to a protected branch
  (`main` / `master`); raises :class:`ApplyTerminalError` per §8.1.
* :func:`assemble_pr_body` — 5-section Markdown body per §8.2.

The module is import-side-effect free; pipeline code wires it to git plumbing
and the GitHub REST API at a higher layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from nanobot.evolve.exceptions import ApplyTerminalError

if TYPE_CHECKING:
    from nanobot.evolve.gates import GateResult
    from nanobot.evolve.harness import RunManifest


# §8.1: branch protection set — spec pins exactly these two names; other
# protected refs are enforced server-side via GitHub branch protection.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master"})


def build_branch_name(run_id: str, skill_name: str, candidate_short_sha: str) -> str:
    """Return the deterministic evolve branch name per §8.1.

    Format: ``evolve/<run_id>-<skill_name>-<candidate_short_sha>``. The caller
    is responsible for trimming ``candidate_short_sha`` to the spec-mandated
    8 hex chars (§8.1) — this helper does not re-trim so the test layer can
    pin the exact concatenation contract.
    """
    return f"evolve/{run_id}-{skill_name}-{candidate_short_sha}"


def assert_not_main(branch: str, *, manifest_path: Path, final_status: str) -> None:
    """Refuse to operate on a protected branch (§8.1 no-main invariant).

    Raises :class:`ApplyTerminalError` (exit 8 per §4.6) carrying the structured
    ``final_status`` / ``manifest_path`` kwargs so the CLI can persist the
    abort state into the run manifest before exiting.
    """
    if branch in PROTECTED_BRANCHES:
        raise ApplyTerminalError(
            f"refuse to push to protected branch: {branch}",
            final_status=final_status,
            manifest_path=manifest_path,
        )


# §8.2 — the 5 section headers, in spec-prescribed order. Exposed so tests
# can pin the order without re-encoding the literal list.
PR_BODY_SECTIONS: tuple[str, ...] = (
    "Summary",
    "Eval results",
    "Gates passed",
    "Diff stats",
    "Rollback plan",
)


def assemble_pr_body(
    manifest: "RunManifest", gate_results: list["GateResult"]
) -> str:
    """Render the 5-section PR body Markdown per §8.2.

    Sections (in fixed order): Summary, Eval results, Gates passed, Diff stats,
    Rollback plan. Section bodies are deterministic given the inputs so the PR
    text is byte-stable across re-runs of the same run_id (testability + audit).

    Per §8.2 / §8.5 the Rollback line is a single ``git revert <sha>`` placeholder
    — the real squash-merge SHA is amended in by a webhook / follow-up tool
    after GitHub creates it; M4 candidates do not require additional cleanup.
    """
    promoted = manifest.promoted_candidate_hash or "<none>"
    short_sha = promoted[:8] if promoted != "<none>" else "<none>"

    passed = [r for r in gate_results if r.verdict == "pass"]
    failed = [r for r in gate_results if r.verdict == "fail"]

    # --- Summary ----------------------------------------------------------
    summary_lines = [
        "## Summary",
        f"Evolve run `{manifest.run_id}` for skill `{manifest.skill_name}` "
        f"(final status: `{manifest.final_status}`).",
        f"Baseline `{manifest.baseline_hash[:8]}` → promoted candidate `{short_sha}`.",
    ]

    # --- Eval results -----------------------------------------------------
    eval_lines = ["## Eval results"]
    if gate_results:
        for r in gate_results:
            verdict_token = "PASS" if r.verdict == "pass" else "FAIL"
            metric_blob = (
                ", ".join(f"{k}={v}" for k, v in sorted(r.metrics.items()))
                if r.metrics
                else "no-metrics"
            )
            eval_lines.append(f"- {r.gate_name}: {verdict_token} — {metric_blob}")
    else:
        eval_lines.append("- (no gate results recorded)")
    eval_lines.append(f"- Run manifest: `{manifest.run_id}`")

    # --- Gates passed -----------------------------------------------------
    gates_passed_lines = ["## Gates passed"]
    if passed:
        for r in passed:
            gates_passed_lines.append(f"- {r.gate_name}")
    else:
        gates_passed_lines.append("- (none)")
    if failed:
        # Surface failures alongside so reviewers don't have to cross-ref.
        for r in failed:
            reason = r.failure_reason or "unspecified"
            gates_passed_lines.append(f"- ~~{r.gate_name}~~ (FAILED: {reason})")

    # --- Diff stats -------------------------------------------------------
    # Skeleton: full +/- line counts require the diff plumbing in t-14 pipeline.
    # We render a deterministic stub including the candidate short SHA; pipeline
    # is expected to post-process this section once it has the patch in hand.
    diff_lines = [
        "## Diff stats",
        f"candidate hash: `{short_sha}` (full: `{promoted}`)",
        f"files changed: 1 (skill `{manifest.skill_name}` SKILL.md)",
    ]

    # --- Rollback plan ----------------------------------------------------
    # §8.5 Precondition: PR is squash-merged → single-parent commit → bare
    # ``git revert <sha>`` is valid (no ``-m <parent>`` needed).
    rollback_lines = [
        "## Rollback plan",
        "`git revert <sha>`  # single-parent commit per §8.4 squash-merge mandate",
    ]

    blocks = [
        "\n".join(summary_lines),
        "\n".join(eval_lines),
        "\n".join(gates_passed_lines),
        "\n".join(diff_lines),
        "\n".join(rollback_lines),
    ]
    return "\n\n".join(blocks) + "\n"
