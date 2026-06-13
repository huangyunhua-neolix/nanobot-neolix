"""Tests for nanobot.curator.deliberation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from nanobot.curator.deliberation import (
    AuxDeliberationResult,
    deliberate_proposal,
    parse_aux_result,
    sanitize_untrusted_skill_text,
)

# ---------------------------------------------------------------------------
# AuxDeliberationResult — field acceptance
# ---------------------------------------------------------------------------


def test_aux_deliberation_result_accepts_support() -> None:
    result = AuxDeliberationResult(verdict="support", rationale="looks fine", confidence_delta="same")
    assert result.verdict == "support"
    assert result.confidence_delta == "same"


def test_aux_deliberation_result_accepts_caution() -> None:
    result = AuxDeliberationResult(verdict="caution", rationale="might be needed", confidence_delta="decrease")
    assert result.verdict == "caution"
    assert result.confidence_delta == "decrease"


def test_aux_deliberation_result_accepts_reject() -> None:
    result = AuxDeliberationResult(verdict="reject", rationale="active dependency", confidence_delta="same")
    assert result.verdict == "reject"


def test_aux_deliberation_result_accepts_confidence_delta_same() -> None:
    result = AuxDeliberationResult(verdict="support", rationale="ok", confidence_delta="same")
    assert result.confidence_delta == "same"


def test_aux_deliberation_result_accepts_confidence_delta_decrease() -> None:
    result = AuxDeliberationResult(verdict="caution", rationale="ok", confidence_delta="decrease")
    assert result.confidence_delta == "decrease"


# ---------------------------------------------------------------------------
# AuxDeliberationResult — rejection of invalid values
# ---------------------------------------------------------------------------


def test_aux_deliberation_result_rejects_confidence_delta_increase() -> None:
    with pytest.raises(ValidationError):
        AuxDeliberationResult(verdict="support", rationale="ok", confidence_delta="increase")  # type: ignore[arg-type]


def test_aux_deliberation_result_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        AuxDeliberationResult(verdict="maybe", rationale="ok", confidence_delta="same")  # type: ignore[arg-type]


def test_aux_deliberation_result_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AuxDeliberationResult(verdict="support", rationale="ok", confidence_delta="same", extra_field="bad")  # type: ignore[call-arg]


def test_aux_deliberation_result_rejects_rationale_over_500_chars() -> None:
    long_text = "x" * 501
    with pytest.raises(ValidationError):
        AuxDeliberationResult(verdict="support", rationale=long_text, confidence_delta="same")


def test_aux_deliberation_result_accepts_rationale_exactly_500_chars() -> None:
    text = "a" * 500
    result = AuxDeliberationResult(verdict="support", rationale=text, confidence_delta="same")
    assert len(result.rationale) == 500


# ---------------------------------------------------------------------------
# parse_aux_result
# ---------------------------------------------------------------------------


def test_parse_aux_result_valid_json() -> None:
    payload = json.dumps({"verdict": "support", "rationale": "all good", "confidence_delta": "same"})
    result = parse_aux_result(payload)
    assert result is not None
    assert result.verdict == "support"
    assert result.confidence_delta == "same"


def test_parse_aux_result_valid_reject_payload() -> None:
    payload = json.dumps({"verdict": "reject", "rationale": "dependency found", "confidence_delta": "decrease"})
    result = parse_aux_result(payload)
    assert result is not None
    assert result.verdict == "reject"
    assert result.confidence_delta == "decrease"


def test_parse_aux_result_invalid_json_returns_none() -> None:
    result = parse_aux_result("not json")
    assert result is None


def test_parse_aux_result_empty_string_returns_none() -> None:
    result = parse_aux_result("")
    assert result is None


def test_parse_aux_result_json_array_returns_none() -> None:
    # JSON is valid but not a dict
    result = parse_aux_result('["support", "caution"]')
    assert result is None


def test_parse_aux_result_missing_field_returns_none() -> None:
    payload = json.dumps({"verdict": "support", "rationale": "ok"})  # missing confidence_delta
    result = parse_aux_result(payload)
    assert result is None


def test_parse_aux_result_invalid_verdict_returns_none() -> None:
    payload = json.dumps({"verdict": "maybe", "rationale": "ok", "confidence_delta": "same"})
    result = parse_aux_result(payload)
    assert result is None


def test_parse_aux_result_extra_field_returns_none() -> None:
    payload = json.dumps(
        {"verdict": "support", "rationale": "ok", "confidence_delta": "same", "sneaky": "field"}
    )
    result = parse_aux_result(payload)
    assert result is None


def test_parse_aux_result_confidence_delta_increase_returns_none() -> None:
    payload = json.dumps({"verdict": "support", "rationale": "ok", "confidence_delta": "increase"})
    result = parse_aux_result(payload)
    assert result is None


# ---------------------------------------------------------------------------
# sanitize_untrusted_skill_text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "delimiter",
    [
        "<system>",
        "</system>",
        "<assistant>",
        "</assistant>",
        "<user>",
        "</user>",
        "<|im_start|>",
        "<|im_end|>",
        "<|system|>",
        "<|assistant|>",
        "<|user|>",
        "[INST]",
        "[/INST]",
    ],
)
def test_sanitize_strips_role_delimiter(delimiter: str) -> None:
    text = f"safe text {delimiter} more safe text"
    result = sanitize_untrusted_skill_text(text)
    assert delimiter.lower() not in result.lower(), f"delimiter {delimiter!r} was not stripped"
    assert "safe text" in result
    assert "more safe text" in result


def test_sanitize_preserves_safe_text() -> None:
    safe = "This is a normal skill description with no delimiters."
    assert sanitize_untrusted_skill_text(safe) == safe


def test_sanitize_strips_multiple_delimiters_in_one_string() -> None:
    text = "<system>inject</system> normal <|im_start|>more inject"
    result = sanitize_untrusted_skill_text(text)
    assert "<system>" not in result
    assert "</system>" not in result
    assert "<|im_start|>" not in result
    assert "normal" in result
    assert "inject" in result  # content between delimiters is preserved; only tags removed


def test_sanitize_empty_string() -> None:
    assert sanitize_untrusted_skill_text("") == ""


def test_sanitize_case_insensitive_for_html_style_delimiters() -> None:
    text = "<SYSTEM>evil</SYSTEM>"
    result = sanitize_untrusted_skill_text(text)
    assert "<SYSTEM>" not in result
    assert "</SYSTEM>" not in result


# ---------------------------------------------------------------------------
# deliberate_proposal — seam behavior (no real provider)
# ---------------------------------------------------------------------------


async def test_deliberate_proposal_returns_none_none_when_no_factory() -> None:
    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["zero_uses_after_views"],
        provider_factory=None,
    )
    assert result is None
    assert warning is None


async def test_deliberate_proposal_returns_none_none_when_factory_has_no_chat() -> None:
    class _NoChat:
        pass

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["stale_since_last_use"],
        provider_factory=_NoChat(),
    )
    assert result is None
    assert warning is None


async def test_deliberate_proposal_with_valid_factory_returns_result() -> None:
    """A factory stub that returns valid JSON produces a parsed AuxDeliberationResult."""

    class _FakeProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            return json.dumps({"verdict": "caution", "rationale": "used recently", "confidence_delta": "decrease"})

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["stale_since_last_use"],
        provider_factory=_FakeProvider(),
    )
    assert result is not None
    assert result.verdict == "caution"
    assert result.confidence_delta == "decrease"
    assert warning is None


async def test_deliberate_proposal_with_factory_returning_invalid_json_produces_warning() -> None:
    class _BadProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            return "not valid json"

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["zero_uses_after_views"],
        provider_factory=_BadProvider(),
    )
    assert result is None
    assert warning is not None
    assert isinstance(warning, str)
    # Warning must NOT contain raw provider output or exception messages
    assert "not valid json" not in warning


async def test_deliberate_proposal_factory_exception_produces_safe_warning() -> None:
    class _ErrorProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            raise RuntimeError("disk full — secret path /etc/passwd revealed")

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["stale_since_created"],
        provider_factory=_ErrorProvider(),
    )
    assert result is None
    assert warning is not None
    # Raw exception message must NOT be in the warning
    assert "disk full" not in (warning or "")
    assert "/etc/passwd" not in (warning or "")


# ---------------------------------------------------------------------------
# deliberate_proposal — LLMResponse-like object with .content attribute
# ---------------------------------------------------------------------------


async def test_deliberate_proposal_with_content_object_returns_result() -> None:
    """A factory returning an object with .content str (like LLMResponse) is parsed correctly."""

    class _FakeResponse:
        def __init__(self, content: str) -> None:
            self.content = content

    class _ObjectProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            return _FakeResponse(
                json.dumps({"verdict": "support", "rationale": "looks fine", "confidence_delta": "same"})
            )

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["zero_uses_after_views"],
        provider_factory=_ObjectProvider(),
    )
    assert result is not None, f"Expected a parsed result, got None (warning={warning!r})"
    assert result.verdict == "support"
    assert result.confidence_delta == "same"
    assert warning is None


async def test_deliberate_proposal_with_real_llm_response_object_returns_result() -> None:
    """Using the actual LLMResponse dataclass from nanobot.providers.base succeeds."""
    from nanobot.providers.base import LLMResponse

    valid_json = json.dumps(
        {"verdict": "reject", "rationale": "active dependency found", "confidence_delta": "decrease"}
    )

    class _RealResponseProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            return LLMResponse(content=valid_json)

    result, warning = await deliberate_proposal(
        skill_name="dep-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["stale_since_last_use"],
        provider_factory=_RealResponseProvider(),
    )
    assert result is not None, f"Expected a parsed result, got None (warning={warning!r})"
    assert result.verdict == "reject"
    assert result.confidence_delta == "decrease"
    assert warning is None


async def test_deliberate_proposal_with_content_object_none_content_produces_warning() -> None:
    """A factory returning an object whose .content is None is treated as invalid (not crashy)."""

    class _NoneContentResponse:
        content = None

    class _NoneContentProvider:
        async def chat(self, *, messages, tools, max_tokens, temperature):
            return _NoneContentResponse()

    result, warning = await deliberate_proposal(
        skill_name="test-skill",
        action="delete_candidate",
        confidence="high",
        reasons=["zero_uses_after_views"],
        provider_factory=_NoneContentProvider(),
    )
    assert result is None
    assert warning is not None
    assert isinstance(warning, str)
