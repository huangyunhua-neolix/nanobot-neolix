"""4-stage redaction pipeline for offline self-evolution artifacts.

Spec refs: m4-offline-skeleton §9.2 (stage order), §9.3 (sidecar audit),
§9.4 (refusal mode + failure semantics).

Stage order is fixed:
    1. PII          (email, phone)
    2. apikey       (anthropic BEFORE openai, then github, aws)
    3. file-path    (POSIX-style home dirs, Windows home dirs)
    4. custom       (caller-supplied (label, pattern, replacement) tuples)

Each stage is wrapped: any non-system exception is re-raised as
``ManifestPrivacyViolation(violated_invariant="§9.4 redaction stage failure")``
chained from the underlying error. ``KeyboardInterrupt`` / ``SystemExit`` /
``asyncio.CancelledError`` propagate transparently.

The result ``RedactionResult.matches`` (dict[str, int]) is the structured
proof artifact expected by §9.3 sidecar manifests.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Callable, Union

from nanobot.evolve.exceptions import ManifestPrivacyViolation

# ---------------------------------------------------------------------------
# Stage 1: PII
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\-\s().]{7,}\d")

# ---------------------------------------------------------------------------
# Stage 2: API keys.
# ANTHROPIC_KEY_RE MUST be applied before OPENAI_KEY_RE; otherwise the more
# permissive ``sk-[A-Za-z0-9]{20,}`` pattern would swallow ``sk-ant-...``.
# Note: ``claude-*`` model identifiers do NOT match either pattern (no
# ``sk-`` prefix) — this is anchored by `test_claude_model_id_not_redacted`.
# ---------------------------------------------------------------------------
ANTHROPIC_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}")
OPENAI_KEY_RE = re.compile(r"sk-[A-Za-z0-9]{20,}")
GITHUB_PAT_RE = re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{40,}")
AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")

# ---------------------------------------------------------------------------
# Stage 3: file paths (home directories).
# ---------------------------------------------------------------------------
HOME_NIX_RE = re.compile(r"/(?:home|Users)/[^/\s]+/")
HOME_WIN_RE = re.compile(r"C:\\Users\\[^\\\s]+\\")


__all__ = [
    "EMAIL_RE",
    "PHONE_RE",
    "ANTHROPIC_KEY_RE",
    "OPENAI_KEY_RE",
    "GITHUB_PAT_RE",
    "AWS_KEY_RE",
    "HOME_NIX_RE",
    "HOME_WIN_RE",
    "RedactionResult",
    "redact",
]


Replacement = Union[str, Callable[[re.Match[str]], str]]
CustomPattern = tuple[str, re.Pattern[str], Replacement]


@dataclass
class RedactionResult:
    """Output of :func:`redact`.

    Attributes
    ----------
    text:
        Redacted text.
    matches:
        Per-label substitution counts. Zero-count labels are omitted.
        Keys: ``"email"``, ``"phone"``, ``"apikey:anthropic"``,
        ``"apikey:openai"``, ``"apikey:github"``, ``"apikey:aws"``,
        ``"path:home_nix"``, ``"path:home_win"``, plus any custom labels.
    """

    text: str
    matches: dict[str, int] = field(default_factory=dict)


_INVARIANT = "§9.4 redaction stage failure"


def _apply(
    text: str,
    pattern: re.Pattern[str],
    replacement: Replacement,
    label: str,
    matches: dict[str, int],
) -> str:
    """Apply a single regex substitution and record the count.

    ``re.subn`` returns ``(new_text, count)``; we only record non-zero counts
    so the sidecar manifest stays compact (§9.3).
    """
    new_text, count = pattern.subn(replacement, text)
    if count:
        matches[label] = matches.get(label, 0) + count
    return new_text


def _run_stage(
    stage_name: str,
    func: Callable[[], str],
) -> str:
    """Run a stage callable, converting non-system exceptions to
    ``ManifestPrivacyViolation`` per §9.4.

    ``KeyboardInterrupt``, ``SystemExit`` and ``asyncio.CancelledError``
    propagate untouched so the host process can be torn down cleanly.
    """
    try:
        return func()
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        raise
    except Exception as exc:
        raise ManifestPrivacyViolation(
            f"redaction stage {stage_name!r} failed: {exc!r}",
            violated_invariant=_INVARIANT,
        ) from exc


def redact(
    text: str,
    *,
    custom_patterns: list[CustomPattern] | None = None,
) -> RedactionResult:
    """Run the 4-stage redaction pipeline.

    Parameters
    ----------
    text:
        Input text to scrub.
    custom_patterns:
        Optional list of ``(label, compiled_pattern, replacement)`` tuples
        applied last, in order. ``replacement`` follows :func:`re.sub`
        semantics (string with backrefs or callable).

    Returns
    -------
    RedactionResult

    Raises
    ------
    ManifestPrivacyViolation
        If any stage raises, or if the redacted output exceeds 3× the input
        length (amplification guard — suggests a runaway custom replacement
        or attacker-crafted input).
    """
    matches: dict[str, int] = {}
    out = text

    # Stage 1: PII
    def _stage_pii(s: str) -> str:
        s = _apply(s, EMAIL_RE, "[REDACTED:EMAIL]", "email", matches)
        s = _apply(s, PHONE_RE, "[REDACTED:PHONE]", "phone", matches)
        return s

    out = _run_stage("pii", lambda: _stage_pii(out))

    # Stage 2: API keys. Anthropic first to preserve specificity.
    def _stage_apikey(s: str) -> str:
        s = _apply(
            s, ANTHROPIC_KEY_RE, "[REDACTED:APIKEY:ANTHROPIC]", "apikey:anthropic", matches
        )
        s = _apply(s, OPENAI_KEY_RE, "[REDACTED:APIKEY:OPENAI]", "apikey:openai", matches)
        s = _apply(s, GITHUB_PAT_RE, "[REDACTED:APIKEY:GITHUB]", "apikey:github", matches)
        s = _apply(s, AWS_KEY_RE, "[REDACTED:APIKEY:AWS]", "apikey:aws", matches)
        return s

    out = _run_stage("apikey", lambda: _stage_apikey(out))

    # Stage 3: file paths
    def _stage_path(s: str) -> str:
        s = _apply(s, HOME_NIX_RE, "/<REDACTED_HOME>/", "path:home_nix", matches)
        s = _apply(s, HOME_WIN_RE, r"C:\<REDACTED_HOME>\\", "path:home_win", matches)
        return s

    out = _run_stage("file-path", lambda: _stage_path(out))

    # Stage 4: custom patterns
    if custom_patterns:
        def _stage_custom(s: str) -> str:
            for label, pat, repl in custom_patterns:
                s = _apply(s, pat, repl, label, matches)
            return s

        out = _run_stage("custom", lambda: _stage_custom(out))

    # Amplification guard (§9.4). Skip when input is empty to avoid the
    # degenerate "any output is infinite expansion" case.
    if len(text) > 0 and len(out) > 3 * len(text):
        factor = len(out) / len(text)
        raise ManifestPrivacyViolation(
            f"redaction amplified input by {factor:.1f}x (>3x threshold)",
            violated_invariant=_INVARIANT,
        )

    return RedactionResult(text=out, matches=matches)
