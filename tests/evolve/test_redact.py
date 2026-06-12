"""Tests for the 4-stage redaction pipeline (m4 §9.2/§9.3/§9.4)."""

from __future__ import annotations

import asyncio
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
    """Modern ``sk-proj-`` shape (current OpenAI default for project keys)."""
    src = "OPENAI_API_KEY=sk-proj-AbCdEf12Gh34Ij56Kl78MnOpQrStUv0123"
    r = redact(src)
    assert "[REDACTED:APIKEY:OPENAI]" in r.text
    assert r.matches["apikey:openai"] == 1
    assert "sk-proj-" not in r.text


def test_openai_key_legacy_shape_redacted():
    """Legacy synthetic ``sk-AbCdEf...`` shape — regression coverage."""
    result = redact("token=sk-AbCdEf12Gh34Ij56Kl78Mn")
    assert "[REDACTED:APIKEY:OPENAI]" in result.text
    assert result.matches.get("apikey:openai", 0) == 1


def test_github_pat_redacted():
    result = redact("ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert "[REDACTED:APIKEY:GITHUB]" in result.text


def test_github_pat_new_format_redacted():
    """Fine-grained ``github_pat_`` shape (Y3): 11-char prefix + 82-char body."""
    # github_pat_ + 82 body chars = 93 total after the literal prefix.
    body = "11ABCDEFG" + "a" * 73  # 9 + 73 = 82
    src = f"auth=github_pat_{body}"
    r = redact(src)
    assert "[REDACTED:APIKEY:GITHUB]" in r.text
    assert r.matches["apikey:github"] == 1


def test_aws_key_redacted():
    result = redact("AKIAIOSFODNN7EXAMPLE")
    assert "[REDACTED:APIKEY:AWS]" in result.text


def test_aws_asia_temp_creds_redacted():
    """Y4: STS temp credentials use the ``ASIA`` prefix."""
    r = redact("aws_session=ASIAIOSFODNN7EXAMPLE")
    assert "[REDACTED:APIKEY:AWS]" in r.text
    assert r.matches["apikey:aws"] == 1


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


def test_home_path_nix_eos_redacted():
    """R6: ``/Users/alice`` at end-of-string must redact (no trailing slash)."""
    r = redact("see /Users/alice")
    assert "alice" not in r.text
    assert r.matches.get("path:home_nix", 0) >= 1


def test_home_path_root_redacted():
    """R4: bare ``/root`` home dir."""
    r = redact("cwd /root/work/file.txt")
    assert "/root/work" not in r.text
    assert r.matches.get("path:home_nix", 0) >= 1


def test_home_path_volumes_redacted():
    """R4: ``/Volumes/...`` macOS external mounts."""
    r = redact("on /Volumes/Backup/data.bin go")
    assert "/Volumes/Backup" not in r.text
    assert r.matches.get("path:home_nix", 0) >= 1


def test_var_folders_redacted():
    """R4: macOS ephemeral ``/var/folders/...`` and ``/private/var/folders/...``."""
    r = redact("temp at /var/folders/xq/abc123/T/tmpfile and /private/var/folders/y_/d/e/x")
    assert "/var/folders/xq" not in r.text
    assert "/private/var/folders/y_" not in r.text
    assert r.matches.get("path:var_folders", 0) >= 2


def test_home_path_win_redacted():
    """R7: exact-equality on redacted output; no double-backslash artifact."""
    r = redact("C:\\Users\\Alice\\Documents\\file")
    assert r.text == "C:\\<REDACTED_HOME>\\Documents\\file"
    assert "Alice" not in r.text
    assert r.matches["path:home_win"] == 1


def test_home_path_win_lowercase_drive_redacted():
    """R5: case-insensitive drive + ``users``."""
    r = redact("path c:\\users\\bob\\stuff")
    assert "bob" not in r.text
    assert r.matches.get("path:home_win", 0) == 1


def test_home_path_win_forward_slash_redacted():
    """R5: Windows-style path with forward-slash separators."""
    r = redact("see C:/Users/Carol/notes")
    assert "Carol" not in r.text
    assert r.matches.get("path:home_win", 0) == 1


# ---------------------------------------------------------------------------
# Stage ordering / interaction (R8 — these tests MUST bite)
# ---------------------------------------------------------------------------
def test_stage_order_apikey_specificity_preserved():
    """If PII stage ran before apikey AND PHONE_RE had no lookbehind, the digit
    run in ``sk-ant-...`` would be consumed as a phone. This test bites if
    either stage ordering changes OR the PHONE_RE lookbehind regresses (R1+R8)."""
    src = "key=sk-ant-1234567890abcdefghij done"
    r = redact(src)
    assert r.matches.get("apikey:anthropic", 0) == 1
    assert r.matches.get("phone", 0) == 0
    assert "[REDACTED:APIKEY:ANTHROPIC]" in r.text
    assert "sk-ant-1234567890abcdefghij" not in r.text


def test_audit_trail_correct_for_github_pat_with_digit_run():
    """§9.3 sidecar correctness: ``github_pat_...`` containing a digit run
    must report ``apikey:github == 1`` and ``phone == 0`` (R8b)."""
    body = "11ABCDEFG0123456789" + "a" * 63  # 19 + 63 = 82
    src = f"use github_pat_{body} here"
    r = redact(src)
    assert r.matches.get("apikey:github", 0) == 1
    assert r.matches.get("phone", 0) == 0


def test_stage_order_pii_email_and_apikey():
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
# Idempotence (Y5)
# ---------------------------------------------------------------------------
def test_redact_is_idempotent():
    """Round-2 Y5: redact(redact(x)) == redact(x) and second-pass matches
    are empty (the placeholder tokens themselves are not secrets)."""
    src = "alice@example.com and sk-AbCdEf12Gh34Ij56Kl78Mn"
    r1 = redact(src)
    r2 = redact(r1.text)
    assert r2.text == r1.text
    assert r2.matches == {} or all(v == 0 for v in r2.matches.values())


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


def test_amplification_message_pins_3x_threshold():
    """Y6: the literal ``3`` must appear in the amplification message so a
    silent threshold drift (e.g. to 5x) is caught."""
    custom = [("amp", re.compile(r"a"), "x" * 100)]
    with pytest.raises(ManifestPrivacyViolation) as exc:
        redact("a" * 100, custom_patterns=custom)
    assert "3" in str(exc.value)


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


def test_system_exit_propagates():
    """Y2: SystemExit raised inside a stage callable must propagate untouched."""

    def boom(_m: re.Match[str]) -> str:
        raise SystemExit(2)

    custom = [("sysexit", re.compile(r"x"), boom)]
    with pytest.raises(SystemExit):
        redact("xxx", custom_patterns=custom)


def test_cancelled_error_propagates():
    """Y2: asyncio.CancelledError raised inside a stage must propagate untouched."""

    def boom(_m: re.Match[str]) -> str:
        raise asyncio.CancelledError

    custom = [("cancelled", re.compile(r"x"), boom)]
    with pytest.raises(asyncio.CancelledError):
        redact("xxx", custom_patterns=custom)


# ---------------------------------------------------------------------------
# Return shape sanity
# ---------------------------------------------------------------------------
def test_returns_redaction_result_type():
    result = redact("hello world")
    assert isinstance(result, RedactionResult)
    assert isinstance(result.matches, dict)


# ---------------------------------------------------------------------------
# R3-9 — direct 4-stage ordering witness: APIKEY (stage 2) runs BEFORE PATH (3)
# ---------------------------------------------------------------------------
#
# Witness: an Anthropic key embedded INSIDE a ``/Users/...`` path component.
# Under the spec §9.2 order (PII → APIKEY → PATH → CUSTOM):
#   1. PII: no match (the key has no @ or phone digits)
#   2. APIKEY: ``sk-ant-AAAA...`` → ``[REDACTED:APIKEY:ANTHROPIC]`` AND
#      matches["apikey:anthropic"] increments.
#   3. PATH: HOME_NIX_RE then swallows ``/Users/[REDACTED:APIKEY:ANTHROPIC]/``
#      wholesale, but the apikey count + sentinel-was-applied invariant has
#      already been recorded in stage 2.
#
# Regression check: if PATH ran FIRST (stages reordered), HOME_NIX_RE would
# swallow ``/Users/sk-ant-AAAA.../`` directly and APIKEY stage would never see
# the key → matches["apikey:anthropic"] == 0. The count-of-1 assertion below
# is the load-bearing proof of stage order.
def test_stage_order_apikey_runs_before_path():
    """Spec §9.2: APIKEY (stage 2) runs BEFORE PATH (stage 3).

    A successful APIKEY-stage hit on a key embedded in a ``/Users/...`` path
    can only occur if APIKEY runs first; otherwise HOME_NIX_RE eats the whole
    path component (including the raw key) before APIKEY can pattern-match.
    The match-count = 1 assertion is the ordering proof.
    """
    text = "config at /Users/sk-ant-AAAAAAAAAAAAAAAAAAAAAAAAAA/.config"
    result = redact(text)
    # Stage-2 ordering proof: APIKEY stage saw and counted the key.
    assert result.matches.get("apikey:anthropic", 0) == 1, (
        "APIKEY stage failed to fire on the embedded key — suggests PATH "
        "stage ran first and swallowed it"
    )
    # The raw key MUST NOT survive in the output.
    assert "sk-ant-AAAAAAAAAAAAAAAAAAAAAAAAAA" not in result.text
