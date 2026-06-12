"""Tests for the 4-stage redaction pipeline (m4 §9.2/§9.3/§9.4)."""

from __future__ import annotations

import re

import pytest

from nanobot.evolve.exceptions import ManifestPrivacyViolation
from nanobot.evolve.privacy import RedactionResult, redact


# ---------------------------------------------------------------------------
# Stage 1: PII
# ---------------------------------------------------------------------------
def test_email_redacted():
    result = redact("contact me at alice@example.com please")
    assert "[REDACTED:EMAIL]" in result.text
    assert "alice@example.com" not in result.text
    assert result.matches["email"] == 1


def test_phone_redacted():
    result = redact("call +1 555-123-4567 now")
    assert "[REDACTED:PHONE]" in result.text
    assert "555-123-4567" not in result.text


# ---------------------------------------------------------------------------
# Stage 2: API keys — ordering preserved (anthropic before openai)
# ---------------------------------------------------------------------------
def test_anthropic_key_redacted_not_openai():
    result = redact("key=sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv")
    assert "[REDACTED:APIKEY:ANTHROPIC]" in result.text
    assert "[REDACTED:APIKEY:OPENAI]" not in result.text
    assert result.matches.get("apikey:anthropic", 0) == 1
    assert result.matches.get("apikey:openai", 0) == 0


def test_openai_key_redacted():
    # Mixed alnum (no long digit-run) so the upstream PHONE_RE in stage 1
    # does not pre-consume the digits inside the key.
    result = redact("token=sk-AbCdEf12Gh34Ij56Kl78Mn")
    assert "[REDACTED:APIKEY:OPENAI]" in result.text
    assert result.matches.get("apikey:openai", 0) == 1


def test_github_pat_redacted():
    result = redact("ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert "[REDACTED:APIKEY:GITHUB]" in result.text


def test_aws_key_redacted():
    result = redact("AKIAIOSFODNN7EXAMPLE")
    assert "[REDACTED:APIKEY:AWS]" in result.text


# CRITICAL — anchors the t-17 regression test referenced in §9.4 commentary.
def test_claude_model_id_not_redacted():
    """``claude-*`` model identifiers must survive the apikey stage intact.

    Only ``sk-ant-`` (the actual Anthropic API key prefix) may be matched.
    """
    src = "used claude-3-5-sonnet-20241022 model"
    result = redact(src)
    assert result.text == src
    assert "claude-3-5-sonnet-20241022" in result.text
    assert result.matches.get("apikey:openai", 0) == 0
    assert result.matches.get("apikey:anthropic", 0) == 0


# ---------------------------------------------------------------------------
# Stage 3: file paths
# ---------------------------------------------------------------------------
def test_home_path_nix_redacted():
    result = redact("see /Users/alice/notes.md or /home/bob/file")
    assert "/<REDACTED_HOME>/" in result.text
    assert "alice" not in result.text
    assert "bob" not in result.text


def test_home_path_win_redacted():
    result = redact("C:\\Users\\Alice\\Documents\\file")
    assert "C:\\<REDACTED_HOME>\\" in result.text
    assert "Alice" not in result.text


# ---------------------------------------------------------------------------
# Stage ordering / interaction
# ---------------------------------------------------------------------------
def test_stage_order_pii_before_apikey():
    """Email + API key in same input must both redact cleanly, no interference."""
    result = redact("alice@example.com used sk-AbCdEf12Gh34Ij56Kl78Mn")
    assert "[REDACTED:EMAIL]" in result.text
    assert "[REDACTED:APIKEY:OPENAI]" in result.text
    assert "alice@example.com" not in result.text
    assert "sk-AbCdEf12Gh34Ij56Kl78Mn" not in result.text


def test_custom_pattern_applied_last():
    custom = [("project", re.compile(r"PROJ-\d+"), "[REDACTED:PROJECT]")]
    result = redact("see PROJ-42", custom_patterns=custom)
    assert "[REDACTED:PROJECT]" in result.text
    assert result.matches["project"] == 1


# ---------------------------------------------------------------------------
# Failure semantics (§9.4)
# ---------------------------------------------------------------------------
def test_stage_failure_raises_manifest_privacy_violation():
    """A custom replacement that raises must be wrapped as ManifestPrivacyViolation."""

    def boom(_m: re.Match[str]) -> str:
        raise ValueError("synthetic stage failure")

    custom = [("boom", re.compile(r"x"), boom)]
    with pytest.raises(ManifestPrivacyViolation) as exc_info:
        redact("xxx", custom_patterns=custom)
    assert exc_info.value.violated_invariant == "§9.4 redaction stage failure"
    # Underlying cause should be chained.
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_custom_pattern_amplification_raises():
    # Input 100 chars; replacement expands each "a" to 100 "x"s → 10_000 chars → 100x.
    custom = [("amp", re.compile(r"a"), "x" * 100)]
    with pytest.raises(ManifestPrivacyViolation) as exc_info:
        redact("a" * 100, custom_patterns=custom)
    assert exc_info.value.violated_invariant == "§9.4 redaction stage failure"


def test_empty_text_no_amplification():
    """Empty input must not trip the amplification guard (divide-by-zero edge)."""
    result = redact("")
    assert result.text == ""
    assert result.matches == {}


def test_keyboard_interrupt_propagates():
    """KeyboardInterrupt in a stage callable must propagate untouched."""

    def boom(_m: re.Match[str]) -> str:
        raise KeyboardInterrupt

    custom = [("ki", re.compile(r"x"), boom)]
    with pytest.raises(KeyboardInterrupt):
        redact("xxx", custom_patterns=custom)


# ---------------------------------------------------------------------------
# Return shape sanity
# ---------------------------------------------------------------------------
def test_returns_redaction_result_type():
    result = redact("hello world")
    assert isinstance(result, RedactionResult)
    assert isinstance(result.matches, dict)
