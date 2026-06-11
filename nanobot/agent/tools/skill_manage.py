"""skill_manage runtime tool — validation shell (M2 §4 / plan task t-07).

This module lays the SHELL only:

* :class:`SkillManageVerb` enum.
* JSON parameter schema for the function-call interface.
* :class:`SkillManageTool` class skeleton with a write-once
  ``provenance_tag`` capture at construction time.
* Cheap-reject helpers that consult no on-disk state and raise before any
  lock acquisition: :func:`_validate_skill_name`,
  :func:`_check_body_size`, :func:`_check_description_len`.
* :func:`_validate_provenance_tag` — internal precondition validator (raises
  :class:`ValueError`).
* :class:`_ErrorCode` namespace of canonical ``error_code`` strings.
* :func:`_ok` / :func:`_reject` JSON return-shape helpers.
* :meth:`SkillManageTool.execute` placeholder that runs the validators and
  returns ``_reject("not_implemented")`` once they pass — proves the
  validation layer end-to-end without the full lock pipeline (which is t-08
  territory).

The actual create/edit/patch/delete verb pipelines (locks, atomic writes,
telemetry bumps) are intentionally NOT in this module. See task t-08.

NOTE: :class:`SkillManageError` is reused from ``nanobot.agent._atomic_io``
(shipped by t-01/t-02). Do NOT redefine it here.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Final

from nanobot.agent._atomic_io import SkillManageError
from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.context import ToolContext
from nanobot.agent.tools.schema import (
    ArraySchema,
    StringSchema,
    tool_parameters_schema,
)


class SkillManageVerb(StrEnum):
    """Verb selector for the skill_manage tool (M2 §4.1)."""

    CREATE = "create"
    EDIT = "edit"
    PATCH = "patch"
    DELETE = "delete"


class _ErrorCode:
    """Canonical ``error_code`` strings returned via :func:`_reject` (M2 §4.5).

    Declared here so t-08's verb pipelines reference one source of truth.
    More codes may be added in t-08 (atomic_write_failed, path_escape, …).
    """

    INVALID_NAME: Final[str] = "invalid_name"
    INVALID_VERB: Final[str] = "invalid_verb"
    BODY_TOO_LARGE: Final[str] = "body_too_large"
    DESCRIPTION_TOO_LONG: Final[str] = "description_too_long"
    NOT_IMPLEMENTED: Final[str] = "not_implemented"
    NAME_EXISTS: Final[str] = "name_exists"
    NAME_COLLISION: Final[str] = "name_collision"
    TIER_LOCKED: Final[str] = "tier_locked"
    NOT_FOUND: Final[str] = "not_found"
    QUOTA_EXCEEDED: Final[str] = "quota_exceeded"
    RATE_CAPPED: Final[str] = "rate_capped"


# --- Validation primitives ----------------------------------------------------

# ASCII-only — Unicode confusables (Cyrillic 'а', em-dash, NBSP, …) MUST be
# rejected. `re.ASCII` is mandatory; do not drop it.
_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9-]*$", re.ASCII)
_SUBAGENT_ID_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_-]{1,64}$", re.ASCII)

# Reserved tier directory names — case-insensitive reject.
_RESERVED_NAMES: Final[frozenset[str]] = frozenset({"agent", "user", "bundled", "hub"})

_NAME_MIN_LEN: Final[int] = 1
_NAME_MAX_LEN: Final[int] = 64


def _validate_skill_name(name: str) -> None:
    """Raise :class:`SkillManageError` (``invalid_name``) if ``name`` is unsafe.

    Rules (M2 §3.5, §3.6):

    * Length ``1 <= len <= 64``.
    * Pattern ``^[a-z0-9][a-z0-9-]*$`` (ASCII).
    * No leading dot, no embedded dot, no whitespace, no path-separators.
    * Not one of the reserved tier names (``agent``, ``user``, ``bundled``,
      ``hub``); compared case-insensitively.
    """
    if not isinstance(name, str):
        raise SkillManageError(
            _ErrorCode.INVALID_NAME, f"name must be str, got {type(name).__name__}"
        )
    n = len(name)
    if n < _NAME_MIN_LEN:
        raise SkillManageError(
            _ErrorCode.INVALID_NAME, "name must be at least 1 character"
        )
    if n > _NAME_MAX_LEN:
        raise SkillManageError(
            _ErrorCode.INVALID_NAME,
            f"name must be at most {_NAME_MAX_LEN} characters (got {n})",
        )
    # Explicit dot-leading reject for a clear error_code mapping even though
    # the regex would already fail — the spec requires this distinct check.
    if name.startswith("."):
        raise SkillManageError(
            _ErrorCode.INVALID_NAME, "name must not begin with '.'"
        )
    if not _NAME_RE.fullmatch(name):
        raise SkillManageError(
            _ErrorCode.INVALID_NAME,
            "name must match ^[a-z0-9][a-z0-9-]*$ (ASCII lowercase, digits, "
            "and '-'; first char must be alphanumeric)",
        )
    if name.lower() in _RESERVED_NAMES:
        raise SkillManageError(
            _ErrorCode.INVALID_NAME,
            f"name '{name}' is reserved (tier directory name)",
        )


def _validate_provenance_tag(tag: str) -> None:
    """Raise :class:`ValueError` if ``tag`` is not a well-formed provenance tag.

    Allowed forms:

    * Literal ``"agent"``.
    * ``"subagent:<id>"`` where ``<id>`` matches ``^[A-Za-z0-9_-]{1,64}$``.

    Anything else (Unicode, whitespace, bare ``"subagent:"``, oversized id,
    other prefixes) is rejected. This is an internal precondition — not a
    user-visible verb reject — so it raises ``ValueError`` rather than
    :class:`SkillManageError`.
    """
    if not isinstance(tag, str):
        raise ValueError(f"provenance_tag must be str, got {type(tag).__name__}")
    if tag == "agent":
        return
    if tag.startswith("subagent:"):
        sub_id = tag[len("subagent:"):]
        if not _SUBAGENT_ID_RE.fullmatch(sub_id):
            raise ValueError(
                f"invalid subagent id in provenance_tag: {tag!r} "
                f"(must match ^[A-Za-z0-9_-]{{1,64}}$)"
            )
        return
    raise ValueError(
        f"invalid provenance_tag: {tag!r} "
        f"(allowed: 'agent' or 'subagent:<id>')"
    )


def _check_body_size(body: bytes | str, max_body_bytes: int) -> None:
    """Reject if UTF-8-encoded ``body`` exceeds ``max_body_bytes``.

    Pure: consults no state. Called BEFORE any lock acquisition.
    """
    if isinstance(body, str):
        size = len(body.encode("utf-8"))
    else:
        size = len(body)
    if size > max_body_bytes:
        raise SkillManageError(
            _ErrorCode.BODY_TOO_LARGE,
            f"body is {size} bytes; limit is {max_body_bytes}",
        )


def _check_description_len(desc: str, max_description_len: int) -> None:
    """Reject if ``desc`` exceeds ``max_description_len`` *characters*.

    Counts Python ``str`` characters (UTF-32 code points), NOT UTF-8 bytes —
    so a 280-char description of CJK text is still acceptable even though
    it is ~840 bytes UTF-8 encoded.
    """
    if len(desc) > max_description_len:
        raise SkillManageError(
            _ErrorCode.DESCRIPTION_TOO_LONG,
            f"description is {len(desc)} characters; limit is {max_description_len}",
        )


# --- JSON return-shape helpers (M2 §4.6.1) ------------------------------------


def _ok(verb: str, name: str, **extras: Any) -> dict[str, Any]:
    """Return the canonical success envelope for a skill_manage call."""
    return {"ok": True, "verb": verb, "name": name, **extras}


def _reject(verb: str, name: str, code: str, msg: str = "") -> dict[str, Any]:
    """Return the canonical reject envelope for a skill_manage call."""
    return {
        "ok": False,
        "verb": verb,
        "name": name,
        "error_code": code,
        "error_message": msg,
    }


# --- Tool class ---------------------------------------------------------------


_PARAM_SCHEMA: Final[dict[str, Any]] = tool_parameters_schema(
    verb=StringSchema(
        "Operation to perform: create | edit | patch | delete.",
        enum=("create", "edit", "patch", "delete"),
    ),
    name=StringSchema(
        "Skill name. Must match ^[a-z0-9][a-z0-9-]*$, length 1..64, "
        "and must not be a reserved tier name (agent, user, bundled, hub).",
        min_length=1,
        max_length=64,
    ),
    description=StringSchema(
        "One-line skill description (≤ max_description_len chars).",
        max_length=280,
        nullable=True,
    ),
    body=StringSchema(
        "Full skill body for create/edit (UTF-8). Subject to max_body_bytes "
        "after encoding. Ignored for delete; for patch use search/replace.",
        nullable=True,
    ),
    requires=ArraySchema(
        items=StringSchema(""),
        description="Optional list of skill names this skill depends on.",
        nullable=True,
    ),
    search=StringSchema(
        "patch only: literal string to search for in the existing body.",
        nullable=True,
    ),
    replace=StringSchema(
        "patch only: literal replacement text for `search`.",
        nullable=True,
    ),
    required=["verb", "name"],
)


@tool_parameters(_PARAM_SCHEMA)
class SkillManageTool(Tool):
    """Runtime tool that lets the agent manage its own skill files (M2).

    This task ships only the validation shell — the four verb pipelines
    (with locks, atomic writes, telemetry bumps, runtime_state quota
    enforcement) land in t-08.

    The ``provenance_tag`` is captured ONCE from the :class:`ToolContext`
    at construction time and stored as ``self._provenance_tag_``. Mutating
    ``ctx.provenance_tag`` later does NOT affect existing tool instances —
    each subagent / dream context constructs its own tool with its own tag.
    The trailing underscore on ``_provenance_tag_`` is the project's
    Google-style "private mutable bound at construction" convention.
    """

    def __init__(
        self,
        *,
        workspace: Any,
        telemetry: Any,
        provenance_tag: str = "agent",
    ) -> None:
        _validate_provenance_tag(provenance_tag)
        self._workspace_ = workspace
        self._telemetry_ = telemetry
        self._provenance_tag_ = provenance_tag

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        # Read provenance_tag exactly once at construction time. Subsequent
        # ctx.provenance_tag mutations must not bleed into this instance.
        captured_tag = getattr(ctx, "provenance_tag", "agent")
        return cls(
            workspace=getattr(ctx, "workspace", None),
            telemetry=None,  # t-08 wires the real SkillsTelemetry instance
            provenance_tag=captured_tag,
        )

    @classmethod
    def enabled(cls, ctx: ToolContext) -> bool:  # pragma: no cover - trivial
        return getattr(ctx, "workspace", None) is not None

    @property
    def name(self) -> str:
        return "skill_manage"

    @property
    def description(self) -> str:
        return (
            "Manage agent-tier skill files: create, edit, patch (search/replace), "
            "or delete a skill by name. Bundled and user-tier skills are read-only "
            "from this tool. Names must be lowercase ASCII (a-z 0-9 hyphen)."
        )

    @property
    def exclusive(self) -> bool:
        # Mutates files under workspace; must not run alongside other writers.
        return True

    async def execute(self, **kwargs: Any) -> Any:
        """Validate inputs and return a canonical JSON envelope.

        Until t-08 lands the verb pipelines this returns
        ``_reject("not_implemented")`` once validation passes, proving the
        cheap-reject layer is end-to-end wired through the tool dispatch.
        """
        verb_raw = kwargs.get("verb", "")
        name = kwargs.get("name", "")

        # Verb is the most informative thing for any reject envelope; resolve
        # it first so the caller always sees the verb they sent (or empty if
        # malformed).
        try:
            verb = SkillManageVerb(verb_raw)
        except ValueError:
            return _reject(
                str(verb_raw),
                str(name),
                _ErrorCode.INVALID_VERB,
                f"unknown verb: {verb_raw!r}",
            )

        # Name validation — cheap, no state.
        try:
            _validate_skill_name(name)
        except SkillManageError as e:
            return _reject(verb.value, str(name), e.error_code, str(e))

        # Description / body cheap-reject (description is char-counted; body
        # is UTF-8 byte-counted). Limits come from SkillManageConfig (t-05),
        # which is wired by t-08 — until then we use the documented spec
        # defaults so the placeholder still exercises real bounds.
        description = kwargs.get("description")
        if isinstance(description, str):
            try:
                _check_description_len(description, max_description_len=280)
            except SkillManageError as e:
                return _reject(verb.value, name, e.error_code, str(e))

        body = kwargs.get("body")
        if isinstance(body, (str, bytes, bytearray)):
            try:
                _check_body_size(body, max_body_bytes=65536)
            except SkillManageError as e:
                return _reject(verb.value, name, e.error_code, str(e))

        # Validation passed — verb pipeline (t-08) not yet wired.
        return _reject(
            verb.value,
            name,
            _ErrorCode.NOT_IMPLEMENTED,
            "verb pipeline lands in t-08",
        )


__all__ = [
    "SkillManageError",
    "SkillManageTool",
    "SkillManageVerb",
    "_ErrorCode",
    "_check_body_size",
    "_check_description_len",
    "_ok",
    "_reject",
    "_validate_provenance_tag",
    "_validate_skill_name",
]
