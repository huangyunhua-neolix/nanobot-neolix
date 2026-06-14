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

import re
from pathlib import Path
from typing import TYPE_CHECKING

from nanobot.evolve.exceptions import ApplyTerminalError

if TYPE_CHECKING:
    from nanobot.evolve.gates import GateResult
    from nanobot.evolve.schemas import RunManifest


# §8.1: branch protection set — spec pins exactly these two names; other
# protected refs are enforced server-side via GitHub branch protection.
PROTECTED_BRANCHES: frozenset[str] = frozenset({"main", "master"})


# Charset rejected by ``_validate_no_newlines``. Beyond raw ``\n`` / ``\r``,
# markdown renderers (GitHub, GitLab, CommonMark.js) also split on the Unicode
# line-separators U+2028 / U+2029 and the NEL (U+0085) character — any of these
# in an interpolated field could forge a fake ``## `` header and break the
# 5-section invariant pinned by §8.2. NUL is added for defense in depth (git
# refnames + most parsers reject it, but it's free).
_FORBIDDEN_NEWLINE_CHARS: frozenset[str] = frozenset(
    {"\n", "\r", "\u2028", "\u2029", "\u0085", "\x00"}
)


# §8.1: per git-check-ref-format, forbid characters that confuse the refname
# parser, command-line flag parsing, or downstream markdown rendering. Listed
# explicitly here (rather than negated charset) so reviewers can audit.
_FORBIDDEN_BRANCH_CHARS: frozenset[str] = frozenset(
    {
        " ",  # spaces break ``git rev-parse``
        "~",
        "^",
        ":",
        "?",
        "*",
        "[",
        "\\",
        "\x00",
    }
)


def _validate_branch_component(name: str, *, component: str) -> None:
    """Reject obviously-unsafe inputs that would later confuse git or markdown.

    Mirrors the most relevant subset of ``git-check-ref-format`` rules plus the
    newline / control-char guard from :func:`_validate_no_newlines`. Raises
    :class:`ValueError` naming both ``component`` and the violation so callers
    can debug. Empty values, leading dash (flag injection into git CLI),
    ``..`` / ``@{`` substrings, ``.lock`` suffix, leading or trailing slash,
    embedded ``//``, and ASCII control chars are all rejected.
    """
    if not name:
        raise ValueError(f"build_branch_name: {component!r} must not be empty")
    if name.startswith("-"):
        raise ValueError(
            f"build_branch_name: {component!r}={name!r} starts with '-' "
            f"(would be parsed as a flag by git)"
        )
    if name.startswith("/"):
        raise ValueError(f"build_branch_name: {component!r}={name!r} starts with '/'")
    if name.endswith("/"):
        raise ValueError(f"build_branch_name: {component!r}={name!r} ends with '/'")
    if name.endswith("."):
        raise ValueError(f"build_branch_name: {component!r}={name!r} ends with '.'")
    if name.endswith(".lock"):
        raise ValueError(
            f"build_branch_name: {component!r}={name!r} ends with '.lock' "
            f"(reserved by git-check-ref-format)"
        )
    if ".." in name:
        raise ValueError(f"build_branch_name: {component!r}={name!r} contains '..'")
    if "@{" in name:
        raise ValueError(f"build_branch_name: {component!r}={name!r} contains '@{{'")
    if "//" in name:
        raise ValueError(f"build_branch_name: {component!r}={name!r} contains '//'")
    for ch in name:
        if ch in _FORBIDDEN_BRANCH_CHARS:
            raise ValueError(
                f"build_branch_name: {component!r}={name!r} contains forbidden "
                f"char {ch!r} (U+{ord(ch):04X})"
            )
        if ch in _FORBIDDEN_NEWLINE_CHARS:
            raise ValueError(
                f"build_branch_name: {component!r}={name!r} contains line-break "
                f"char U+{ord(ch):04X}"
            )
        # ASCII control chars (0x00-0x1F + 0x7F) — covers any newline / NEL
        # already enumerated above, plus less-common DEL / SOH / etc.
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValueError(
                f"build_branch_name: {component!r}={name!r} contains ASCII "
                f"control char U+{ord(ch):04X}"
            )


def build_branch_name(run_id: str, skill_name: str, candidate_short_sha: str) -> str:
    """Return the deterministic evolve branch name per §8.1.

    Format: ``evolve/<run_id>-<skill_name>-<candidate_short_sha>``.

    Validates each component against git-check-ref-format (via
    :func:`_validate_branch_component`) and additionally enforces that
    ``candidate_short_sha`` is exactly 8 lowercase hex chars (the spec §8.1
    short-SHA contract — previously delegated to the caller, now enforced at
    the leaf so downstream code cannot accidentally pass full SHAs or upper-
    case digests). Raises :class:`ValueError` on any violation.
    """
    _validate_branch_component(run_id, component="run_id")
    _validate_branch_component(skill_name, component="skill_name")
    _validate_branch_component(candidate_short_sha, component="candidate_short_sha")
    if len(candidate_short_sha) != 8:
        raise ValueError(
            f"build_branch_name: candidate_short_sha={candidate_short_sha!r} "
            f"must be exactly 8 chars (spec §8.1), got len={len(candidate_short_sha)}"
        )
    if not all(c in "0123456789abcdef" for c in candidate_short_sha):
        raise ValueError(
            f"build_branch_name: candidate_short_sha={candidate_short_sha!r} "
            f"must be lowercase hex [0-9a-f]"
        )
    return f"evolve/{run_id}-{skill_name}-{candidate_short_sha}"


def assert_not_main(branch: str, *, manifest_path: Path, final_status: str) -> None:
    """Refuse to operate on a protected branch (§8.1 no-main invariant).

    Normalizes ``branch`` before comparison (strip whitespace, strip
    ``refs/heads/`` prefix, case-fold) so common bypasses — ``MAIN``,
    ``" main "``, ``"main\\n"``, ``"refs/heads/main"`` — are all blocked.
    Substring matches like ``feature/main-thing`` or
    ``evolve/run-1-main-deadbeef`` correctly pass because normalization
    does not strip path components.

    Raises :class:`ApplyTerminalError` (exit 8 per §4.6) carrying the structured
    ``final_status`` / ``manifest_path`` kwargs so the CLI can persist the
    abort state into the run manifest before exiting.
    """
    # Casefold BEFORE prefix-strip so uppercase variants like
    # ``REFS/HEADS/MAIN`` are recognized.
    normalized = branch.strip().casefold()
    if normalized.startswith("refs/heads/"):
        normalized = normalized[len("refs/heads/") :]
    if normalized in PROTECTED_BRANCHES:
        raise ApplyTerminalError(
            f"refuse to push to protected branch: {branch!r} "
            f"(normalized: {normalized!r})",
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


def _validate_no_newlines(**fields: str) -> None:
    """Defense-in-depth leaf guard for ``assemble_pr_body``.

    A single line-break character smuggled into ``skill_name`` /
    ``final_status`` / ``run_id`` / ``gate_name`` / ``failure_reason`` would
    let the caller forge extra ``## `` headers and break the 5-section
    invariant pinned by §8.2. The rejected charset is
    :data:`_FORBIDDEN_NEWLINE_CHARS` — ASCII LF/CR, Unicode line/paragraph
    separators (U+2028 / U+2029), NEL (U+0085), and NUL. The error message
    names both the offending field and the specific code point so callers
    can debug.
    """
    for name, value in fields.items():
        for ch in value:
            if ch in _FORBIDDEN_NEWLINE_CHARS:
                raise ValueError(
                    f"assemble_pr_body: field {name!r} contains line-break "
                    f"char U+{ord(ch):04X} — would break the 5-section "
                    f"markdown invariant"
                )
        # Threat: triple-backtick opens a fenced code block in the RENDERED
        # PR view that swallows following ``## `` headers, corrupting the
        # visible 5-section layout even though the raw-text invariant
        # (R3-5 ``re.findall``) still passes. Defense-in-depth — block at
        # leaf so no future GateResult plugin can leak it through.
        if "```" in value:
            raise ValueError(
                f"assemble_pr_body: field {name!r} contains triple-backtick — "
                f"would open a fenced code block and break rendered PR layout "
                f"(swallowing subsequent ## section headers from rendered view)"
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

    Precondition: interpolated string fields (``manifest.skill_name``,
    ``manifest.final_status``, ``manifest.run_id``, and ``gate_name`` /
    ``failure_reason`` on each ``GateResult``) MUST NOT contain ``\\n`` or
    ``\\r``. Validation raises :class:`ValueError` naming the offending field
    — this is a defense-in-depth leaf check; the 5-section invariant cannot
    rely on caller hygiene.
    """
    _validate_no_newlines(
        skill_name=manifest.skill_name,
        final_status=manifest.final_status,
        run_id=manifest.run_id,
    )
    for r in gate_results:
        _validate_no_newlines(
            gate_name=r.gate_name,
            failure_reason=r.failure_reason or "",
        )

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
    # TODO(M5): replace stub with real +/- counts from the candidate diff
    # (see CF-t14-pipeline-wiring — pipeline.py needs to thread `Patch` into
    # RunManifest first).
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
    body = "\n\n".join(blocks) + "\n"

    # Self-check: spec §8.2 5-section invariant. Inputs are already newline-
    # validated upstream so user data cannot inject ``## `` headers; this
    # post-assembly assertion catches STRUCTURAL drift from future edits to
    # this function (e.g. accidentally dropping or renaming a section).
    headers = re.findall(r"^## (.+)$", body, flags=re.MULTILINE)
    if headers != list(PR_BODY_SECTIONS):
        raise RuntimeError(
            f"assemble_pr_body internal invariant violated: "
            f"rendered headers={headers!r} vs expected={list(PR_BODY_SECTIONS)!r}"
        )
    return body
