"""Privacy / redaction utilities for offline self-evolution (§9 of M4 spec)."""

from nanobot.evolve.privacy.redact import (
    ANTHROPIC_KEY_RE,
    AWS_KEY_RE,
    EMAIL_RE,
    GITHUB_PAT_RE,
    HOME_NIX_RE,
    HOME_WIN_RE,
    OPENAI_KEY_RE,
    PHONE_RE,
    RedactionResult,
    redact,
)

__all__ = [
    "ANTHROPIC_KEY_RE",
    "AWS_KEY_RE",
    "EMAIL_RE",
    "GITHUB_PAT_RE",
    "HOME_NIX_RE",
    "HOME_WIN_RE",
    "OPENAI_KEY_RE",
    "PHONE_RE",
    "RedactionResult",
    "redact",
]
