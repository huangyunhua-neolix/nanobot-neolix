"""Regression-pin: ``claude-*`` model identifiers vs ``sk-ant-*`` API keys.

Spec ref: m4-offline-skeleton §9.2 stage 2 — Anthropic model names
(``claude-3-5-sonnet``, ``claude-3-opus``, ``claude-3-haiku`` ...) are NOT
secrets and MUST NOT be redacted by the APIKEY stage; only literal
``sk-ant-...`` keys are. This file pins that boundary so any future
tightening of ``ANTHROPIC_KEY_RE`` that accidentally widens to model ids
fails CI loudly.
"""

from __future__ import annotations

from nanobot.evolve.privacy import redact


# ---------------------------------------------------------------------------
# Negative cases: model identifiers must pass through untouched
# ---------------------------------------------------------------------------
def test_claude_model_id_not_redacted():
    r = redact("we use claude-3-5-sonnet for judging")
    assert "claude-3-5-sonnet" in r.text
    assert r.matches.get("apikey:anthropic", 0) == 0


def test_claude_opus_model_id_not_redacted():
    r = redact("model: claude-3-opus")
    assert "claude-3-opus" in r.text
    assert r.matches.get("apikey:anthropic", 0) == 0


def test_claude_versioned_model_id_not_redacted():
    """Date-suffixed identifiers (``claude-3-opus-20240229``) — common shape."""
    r = redact("pinned: claude-3-opus-20240229 release")
    assert "claude-3-opus-20240229" in r.text
    assert r.matches.get("apikey:anthropic", 0) == 0


def test_claude_haiku_model_id_not_redacted():
    r = redact("fallback: claude-3-haiku is cheaper")
    assert "claude-3-haiku" in r.text
    assert r.matches.get("apikey:anthropic", 0) == 0


def test_claude_4_family_versioned_model_id_not_redacted():
    """Current Anthropic naming (claude-sonnet-4, claude-opus-4, claude-haiku-4)
    with date suffix — production shape as of 2025. Pin so any future regex
    drift that widens beyond `sk-` prefix still catches the model-id slip.
    """
    r = redact("benchmark: claude-sonnet-4-20250514 vs claude-opus-4-1-20250805")
    assert "claude-sonnet-4-20250514" in r.text
    assert "claude-opus-4-1-20250805" in r.text
    assert r.matches.get("apikey:anthropic", 0) == 0


# ---------------------------------------------------------------------------
# Positive case: actual sk-ant-* key still gets redacted
# ---------------------------------------------------------------------------
def test_anthropic_key_is_redacted():
    r = redact("token: sk-ant-abcdefghijklmnopqrstuvwxyz1234")
    assert "sk-ant-" not in r.text
    assert r.matches.get("apikey:anthropic", 0) == 1
