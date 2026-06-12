"""4-stage redaction pipeline for offline self-evolution artifacts.

Spec refs: m4-offline-skeleton §9.2 (stage order), §9.3 (sidecar audit),
§9.4 (refusal mode + failure semantics).

Stage order is fixed:
    1. PII          (email, phone)
    2. apikey       (anthropic BEFORE openai, then github, aws)
    3. file-path    (POSIX-style home dirs, Windows home dirs, /var/folders)
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
# PHONE_RE uses negative lookbehind / lookahead so it ONLY matches digit runs
# that are not embedded inside identifier-like tokens. Without these guards,
# ``sk-ant-1234567890abcdef...`` would match the digit run and corrupt the
# downstream apikey stage (round-2 R1). Real phone numbers are typically
# preceded by whitespace, line start, ``(`` or ``+`` — none of which trip
# the lookbehind.
PHONE_RE = re.compile(r"(?<![A-Za-z_\-])\+?\d[\d\-\s().]{7,}\d(?![A-Za-z_\-])")

# ---------------------------------------------------------------------------
# Stage 2: API keys.
# Specificity ordering: ANTHROPIC_KEY_RE MUST run before OPENAI_KEY_RE, because
# both share the ``sk-`` prefix and the openai pattern is now permissive enough
# (modern ``sk-proj-``/``sk-svcacct-``/``sk-admin-`` shapes contain hyphens) to
# swallow ``sk-ant-...`` if executed first. The stage-2 function below pins
# this ordering — do NOT reorder without re-validating
# ``test_anthropic_key_redacted_not_openai`` and the round-2 R1/R8 anchors.
# Note: ``claude-*`` model identifiers do NOT match either pattern (no
# ``sk-`` prefix) — this is anchored by ``test_claude_model_id_not_redacted``.
# ---------------------------------------------------------------------------
ANTHROPIC_KEY_RE = re.compile(r"sk-ant-[A-Za-z0-9\-]{20,}")
# Accepts both legacy ``sk-AbCdEf...`` and modern hyphenated prefixes
# (``sk-proj-``, ``sk-svcacct-``, ``sk-admin-``, ``sk-None-``). Allowing
# hyphens / underscores in the body covers project-key shapes that include
# internal separators.
OPENAI_KEY_RE = re.compile(r"sk-(?:proj-|svcacct-|admin-|None-)?[A-Za-z0-9_\-]{20,}")
# GitHub PAT shapes:
#   - Classic: ``ghp_`` + 36 alnum
#   - Fine-grained: ``github_pat_`` + exactly 82 chars of [A-Za-z0-9_]
# Word-boundary anchors prevent eating trailing context.
GITHUB_PAT_RE = re.compile(r"ghp_[A-Za-z0-9]{36}\b|github_pat_[A-Za-z0-9_]{82}\b")
# AWS access-key-ID prefixes (all 8): IAM user, STS temp, group, user, role,
# instance-profile, managed-policy, virtual-MFA. Body is fixed 16 [0-9A-Z].
AWS_KEY_RE = re.compile(r"(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}")

# ---------------------------------------------------------------------------
# Stage 3: file paths (home directories + ephemeral macOS dirs).
# HOME_NIX_RE: ``/home``, ``/Users``, ``/Volumes`` and bare ``/root`` —
# end-anchor allows trailing slash, word-boundary OR end-of-string so
# ``/Users/alice`` at EOS gets redacted (round-2 R6).
# HOME_WIN_RE: any drive letter (case-insensitive), forward OR backslash
# separators — handles ``c:\users\bob``, ``C:/Users/Alice``, etc. (round-2 R5).
# VAR_FOLDERS_RE: macOS ephemeral temp dirs ``/var/folders/xx/yy/...`` and the
# ``/private`` mount-point variant.
# ---------------------------------------------------------------------------
HOME_NIX_RE = re.compile(r"/(?:home|Users|Volumes|root)(?:/[^/\s]+)?(?:/|\b|$)")
HOME_WIN_RE = re.compile(r"[A-Za-z]:[/\\]Users[/\\][^/\\\s]+[/\\]?", re.IGNORECASE)
VAR_FOLDERS_RE = re.compile(
    r"/(?:private/)?var/folders/[A-Za-z0-9_+]+/[A-Za-z0-9_+]+(?:/[^\s]*)?"
)


__all__ = [
    "EMAIL_RE",
    "PHONE_RE",
    "ANTHROPIC_KEY_RE",
    "OPENAI_KEY_RE",
    "GITHUB_PAT_RE",
    "AWS_KEY_RE",
    "HOME_NIX_RE",
    "HOME_WIN_RE",
    "VAR_FOLDERS_RE",
    "RedactionResult",
    "redact",
]


Replacement = Union[str, Callable[[re.Match[str]], str]]
CustomPattern = tuple[str, re.Pattern[str], Replacement]


# Intentional @dataclass (not EvolveBase): internal-only return type, not serialised
# into the RunManifest sidecar — avoids the camelCase alias-generation overhead.
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
        ``"path:home_nix"``, ``"path:home_win"``, ``"path:var_folders"``,
        plus any custom labels.
    """

    text: str
    matches: dict[str, int] = field(default_factory=dict)


_INVARIANT = "§9.4 redaction stage failure"


def _redact_win_home(m: re.Match[str]) -> str:
    """Preserve the original drive prefix and trailing separator semantics.

    Round-2 R7: the original ``r"C:\\<REDACTED_HOME>\\\\"`` raw-string
    replacement produced a double-trailing-backslash artifact and hard-coded
    the drive letter. A callable lets us echo back the drive (``c:`` or
    ``C:``) and whether the match consumed a trailing separator.
    """
    s = m.group(0)
    drive = s[:2]  # e.g. "C:", "c:", "D:"
    tail_sep = s[-1] if s and s[-1] in ("/", "\\") else ""
    return f"{drive}\\<REDACTED_HOME>{tail_sep}"


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

    # Stage 2: API keys. Anthropic first to preserve specificity (see
    # stage-2 header comment for the full rationale).
    def _stage_apikey(s: str) -> str:
        s = _apply(
            s, ANTHROPIC_KEY_RE, "[REDACTED:APIKEY:ANTHROPIC]", "apikey:anthropic", matches
        )
        s = _apply(s, OPENAI_KEY_RE, "[REDACTED:APIKEY:OPENAI]", "apikey:openai", matches)
        s = _apply(s, GITHUB_PAT_RE, "[REDACTED:APIKEY:GITHUB]", "apikey:github", matches)
        s = _apply(s, AWS_KEY_RE, "[REDACTED:APIKEY:AWS]", "apikey:aws", matches)
        return s

    out = _run_stage("apikey", lambda: _stage_apikey(out))

    # Stage 3: file paths. HOME_WIN_RE FIRST so that a Windows path with
    # forward-slash separators (``C:/Users/Carol/notes``) isn't pre-consumed
    # by HOME_NIX_RE — the drive-letter prefix is the more specific marker.
    # VAR_FOLDERS_RE before HOME_NIX_RE for the same reason (``/var/folders/...``
    # would otherwise hit no rule cleanly; explicit takes precedence).
    def _stage_path(s: str) -> str:
        s = _apply(s, HOME_WIN_RE, _redact_win_home, "path:home_win", matches)
        s = _apply(s, VAR_FOLDERS_RE, "/<REDACTED:VAR_FOLDERS>", "path:var_folders", matches)
        s = _apply(s, HOME_NIX_RE, "/<REDACTED_HOME>/", "path:home_nix", matches)
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
    # degenerate "any output is infinite expansion" case. The 3x threshold
    # is pinned in this message for `test_amplification_message_pins_3x_threshold`.
    if len(text) > 0 and len(out) > 3 * len(text):
        factor = len(out) / len(text)
        raise ManifestPrivacyViolation(
            f"redaction amplified input by {factor:.1f}x (>3x threshold)",
            violated_invariant=_INVARIANT,
        )

    return RedactionResult(text=out, matches=matches)
