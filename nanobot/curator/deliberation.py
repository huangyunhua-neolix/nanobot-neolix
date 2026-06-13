"""Aux deliberation guardrails for the Curator (M3 §6).

Provides:
- ``AuxDeliberationResult`` — strict Pydantic model for the aux model's JSON verdict.
- ``sanitize_untrusted_skill_text`` — strips role-injection delimiters from skill text.
- ``parse_aux_result`` — safe JSON→model parser returning ``None`` on any error.
- ``deliberate_proposal`` — optional async seam (provider factory required); not
  called unless ``CuratorConfig.aux_deliberation`` is ``True`` and a factory is
  supplied.  The command layer is not yet implemented; the seam exists for wiring.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# AuxDeliberationResult
# ---------------------------------------------------------------------------


class AuxDeliberationResult(BaseModel):
    """Strict model for the JSON payload returned by an aux deliberation call.

    Fields
    ------
    verdict:
        One of ``"support"``, ``"caution"``, or ``"reject"``.
    rationale:
        Short human-readable reason (max 500 chars).
    confidence_delta:
        ``"same"`` — aux agrees the existing confidence level is appropriate.
        ``"decrease"`` — aux thinks the curator was over-confident.
        ``"increase"`` is intentionally excluded (aux cannot raise confidence).
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["support", "caution", "reject"]
    rationale: str = Field(max_length=500)
    confidence_delta: Literal["same", "decrease"]


# ---------------------------------------------------------------------------
# Sanitizer
# ---------------------------------------------------------------------------

# Role-injection delimiter patterns to strip.  Order matters: longer tokens first.
_ROLE_DELIMITER_PATTERNS: list[str] = [
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"<\|system\|>",
    r"<\|assistant\|>",
    r"<\|user\|>",
    r"</system>",
    r"</assistant>",
    r"</user>",
    r"<system>",
    r"<assistant>",
    r"<user>",
    r"\[/INST\]",
    r"\[INST\]",
]

_ROLE_DELIMITER_RE = re.compile(
    "|".join(_ROLE_DELIMITER_PATTERNS),
    re.IGNORECASE,
)


def sanitize_untrusted_skill_text(text: str) -> str:
    """Remove role-injection delimiters from untrusted skill text.

    Strips tokens such as ``<system>``, ``<|im_start|>``, ``[INST]``, etc.
    Safe text (without delimiters) is preserved verbatim.

    Args:
        text: Raw skill body or description from an untrusted source.

    Returns:
        The sanitized string with all role delimiters removed.
    """
    return _ROLE_DELIMITER_RE.sub("", text)


# ---------------------------------------------------------------------------
# Safe parser
# ---------------------------------------------------------------------------


def parse_aux_result(text: str) -> AuxDeliberationResult | None:
    """Parse a JSON string into an :class:`AuxDeliberationResult`.

    Returns ``None`` on any JSON decode error, Pydantic validation error, or
    unexpected type — never raises.

    Args:
        text: Raw string from the aux model response.

    Returns:
        A validated :class:`AuxDeliberationResult` or ``None``.
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return AuxDeliberationResult.model_validate(data)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Optional deliberation seam (provider not yet wired)
# ---------------------------------------------------------------------------

_AUX_TIMEOUT_S = 15


async def deliberate_proposal(
    *,
    skill_name: str,
    action: str,
    confidence: str,
    reasons: list[str],
    provider_factory: object,
) -> tuple[AuxDeliberationResult | None, str | None]:
    """Ask an aux model to deliberate on a curator proposal (optional seam).

    This function is a **wiring seam only**.  The command layer and provider
    factory interface are not yet implemented.  Until a concrete
    ``provider_factory`` with a ``chat()`` method is supplied, the function
    returns ``(None, None)`` immediately.

    The prompt is constructed from proposal metadata only — skill body/
    description is intentionally excluded to avoid injecting untrusted content.

    Args:
        skill_name: Name of the skill under review (safe, internal identifier).
        action: Proposed curator action (e.g. ``"delete_candidate"``).
        confidence: Curator confidence level (e.g. ``"high"``).
        reasons: List of reason-code strings from the proposal.
        provider_factory: Object with a ``chat()`` coroutine.  If ``None`` or
            lacks ``chat``, the seam returns ``(None, None)`` immediately.

    Returns:
        A tuple of ``(AuxDeliberationResult | None, warning_message | None)``.
        ``warning_message`` is a short, safe string (no raw model output or
        exception text) when deliberation could not produce a usable verdict.
    """
    if provider_factory is None or not hasattr(provider_factory, "chat"):
        return None, None

    import asyncio

    prompt_lines = [
        "You are a skill-hygiene auditor.  Respond with ONLY valid JSON.",
        "Review this curator proposal and return a deliberation verdict.",
        "",
        f"skill_name: {skill_name}",
        f"action: {action}",
        f"confidence: {confidence}",
        f"reasons: {json.dumps(reasons)}",
        "",
        'Respond with JSON matching exactly: {"verdict": "support"|"caution"|"reject", '
        '"rationale": "<max 500 chars>", "confidence_delta": "same"|"decrease"}',
    ]
    prompt = "\n".join(prompt_lines)

    try:
        raw = await asyncio.wait_for(
            provider_factory.chat(  # type: ignore[union-attr]
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                max_tokens=512,
                temperature=0.0,
            ),
            timeout=_AUX_TIMEOUT_S,
        )
    except TimeoutError:
        return None, "aux deliberation timed out"
    except Exception:  # noqa: BLE001
        return None, "aux deliberation failed"

    result = parse_aux_result(str(raw) if not isinstance(raw, str) else raw)
    if result is None:
        return None, "aux deliberation returned an invalid response"
    return result, None
