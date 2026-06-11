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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _RuntimeConfigView:
    """Snapshot of the four SkillManageConfig knobs the dispatcher needs.

    Built per ``execute()`` call so a hot-reload of the running config
    takes effect on the next mutation, but the dispatcher itself never
    reads the config more than once per call (M2 §3.7 stability guarantee).
    """

    max_mutations_per_turn: int
    max_body_bytes: int
    max_agent_skills: int
    max_description_len: int


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
    INVALID_ARGS: Final[str] = "invalid_args"
    BODY_TOO_LARGE: Final[str] = "body_too_large"
    DESCRIPTION_TOO_LONG: Final[str] = "description_too_long"
    NOT_IMPLEMENTED: Final[str] = "not_implemented"
    NAME_EXISTS: Final[str] = "name_exists"
    NAME_COLLISION: Final[str] = "name_collision"
    TIER_LOCKED: Final[str] = "tier_locked"
    NOT_FOUND: Final[str] = "not_found"
    QUOTA_EXCEEDED: Final[str] = "quota_exceeded"
    RATE_LIMITED: Final[str] = "rate_limited"
    RATE_CAPPED: Final[str] = "rate_capped"  # Legacy alias kept for reviewers
    LOCK_BUSY: Final[str] = "lock_busy"
    PATH_ESCAPE: Final[str] = "path_escape"
    ATOMIC_WRITE_FAILED: Final[str] = "atomic_write_failed"
    SEARCH_NOT_FOUND: Final[str] = "search_not_found"
    SEARCH_AMBIGUOUS: Final[str] = "search_ambiguous"
    CORRUPT_SKILL: Final[str] = "corrupt_skill"
    INTERNAL_ERROR: Final[str] = "internal_error"


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
        config: Any = None,
        runtime_state: Any = None,
    ) -> None:
        _validate_provenance_tag(provenance_tag)
        self._workspace_ = workspace
        self._telemetry_ = telemetry
        self._provenance_tag_ = provenance_tag
        self._config_ = config
        self._runtime_state_ = runtime_state

    @classmethod
    def create(cls, ctx: ToolContext) -> Tool:
        # Read provenance_tag exactly once at construction time. Subsequent
        # ctx.provenance_tag mutations must not bleed into this instance.
        captured_tag = getattr(ctx, "provenance_tag", "agent")
        # Telemetry / runtime_state / config travel as ctx attributes when
        # available; tests may construct the tool directly with kwargs.
        telemetry = getattr(ctx, "telemetry", None)
        config = getattr(ctx, "config", None)
        runtime_state = getattr(ctx, "runtime_state", None)
        return cls(
            workspace=getattr(ctx, "workspace", None),
            telemetry=telemetry,
            provenance_tag=captured_tag,
            config=config,
            runtime_state=runtime_state,
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

    # --- Rate-cap helpers (M2 §3.7 / plan §t-08 step A) ---------------------
    #
    # SYNCHRONOUS, no `await`. Consults & mutates
    # `runtime_state._runtime_vars["skill_manage.mutations_this_turn"]`
    # ONCE per call. On reject, NO telemetry bump, NO disk write.

    _RATE_CAP_KEY: Final[str] = "skill_manage.mutations_this_turn"

    def _resolve_skill_manage_config(self) -> "_RuntimeConfigView":
        """Pull the four knobs off the wired config; fall back to spec
        defaults so unit tests that omit `config=` still exercise real
        bounds rather than infinity.
        """
        cfg = getattr(self._config_, "skill_manage", None)
        if cfg is None and self._config_ is not None:
            cfg = self._config_
        return _RuntimeConfigView(
            max_mutations_per_turn=getattr(cfg, "max_mutations_per_turn", 5),
            max_body_bytes=getattr(cfg, "max_body_bytes", 65536),
            max_agent_skills=getattr(cfg, "max_agent_skills", 200),
            max_description_len=getattr(cfg, "max_description_len", 280),
        )

    def _increment_mutation_counter_or_reject(
        self,
        runtime_state: Any,
        max_mutations_per_turn: int,
    ) -> bool:
        """Synchronous gate. Returns True on accept, False on rate-cap reject.

        The orchestrator (`AgentRunner._run_core`) resets the counter at the
        TOP of each iteration, so this method only ever has to compare
        against a value within `[0, max_mutations_per_turn]`.
        """
        if runtime_state is None:
            return True  # back-compat: harnesses without runtime_state skip
        rt_vars = getattr(runtime_state, "_runtime_vars", None)
        if rt_vars is None:
            return True
        current = rt_vars.get(self._RATE_CAP_KEY, 0)
        if current >= max_mutations_per_turn:
            return False
        rt_vars[self._RATE_CAP_KEY] = current + 1
        return True

    async def execute(self, **kwargs: Any) -> Any:
        """Dispatch to the appropriate verb pipeline (M2 §4.3)."""
        from nanobot.agent.tools import skill_manage_ops as _ops

        verb_raw = kwargs.get("verb", "")
        name = kwargs.get("name", "")

        # Verb resolution first (so reject envelopes always carry the verb
        # the caller sent, or empty if malformed).
        try:
            verb = SkillManageVerb(verb_raw)
        except ValueError:
            return _reject(
                str(verb_raw),
                str(name),
                _ErrorCode.INVALID_VERB,
                f"unknown verb: {verb_raw!r}",
            )

        cfg = self._resolve_skill_manage_config()

        # --- Step A: rate-cap gate (synchronous, before cheap-rejects) -----
        if not self._increment_mutation_counter_or_reject(
            self._runtime_state_, cfg.max_mutations_per_turn,
        ):
            return _reject(
                verb.value, str(name), _ErrorCode.RATE_LIMITED,
                f"max_mutations_per_turn={cfg.max_mutations_per_turn} reached",
            )

        # --- Step B: cheap-rejects (no on-disk state) ----------------------
        try:
            _validate_skill_name(name)
        except SkillManageError as e:
            return _reject(verb.value, str(name), e.error_code, str(e))

        description = kwargs.get("description")
        if isinstance(description, str):
            try:
                _check_description_len(
                    description, max_description_len=cfg.max_description_len,
                )
            except SkillManageError as e:
                return _reject(verb.value, name, e.error_code, str(e))

        body = kwargs.get("body")
        if isinstance(body, (str, bytes, bytearray)):
            try:
                _check_body_size(body, max_body_bytes=cfg.max_body_bytes)
            except SkillManageError as e:
                return _reject(verb.value, name, e.error_code, str(e))

        # --- Step C: verb dispatch ----------------------------------------
        if self._workspace_ is None:
            return _reject(
                verb.value, name, _ErrorCode.INTERNAL_ERROR,
                "tool has no workspace bound",
            )

        if verb is SkillManageVerb.CREATE:
            return _ops.do_create(
                workspace=self._workspace_,
                telemetry=self._telemetry_,
                provenance_tag=self._provenance_tag_,
                name=name,
                description=description if isinstance(description, str) else None,
                body=body if isinstance(body, str) else None,
                requires=kwargs.get("requires"),
                max_agent_skills=cfg.max_agent_skills,
            )
        if verb is SkillManageVerb.EDIT:
            return _ops.do_edit(
                workspace=self._workspace_,
                telemetry=self._telemetry_,
                provenance_tag=self._provenance_tag_,
                name=name,
                description=description if isinstance(description, str) else None,
                requires=kwargs.get("requires"),
                body=body if isinstance(body, str) else None,
            )
        if verb is SkillManageVerb.PATCH:
            return _ops.do_patch(
                workspace=self._workspace_,
                telemetry=self._telemetry_,
                provenance_tag=self._provenance_tag_,
                name=name,
                description=description if isinstance(description, str) else None,
                requires=kwargs.get("requires"),
                search=kwargs.get("search"),
                replace=kwargs.get("replace"),
            )
        if verb is SkillManageVerb.DELETE:
            return _ops.do_delete(
                workspace=self._workspace_,
                telemetry=self._telemetry_,
                provenance_tag=self._provenance_tag_,
                name=name,
            )

        # Unreachable: enum already enumerated above.
        return _reject(
            verb.value, name, _ErrorCode.INVALID_VERB,
            f"unhandled verb: {verb!r}",
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
