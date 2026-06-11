"""skill_manage verb pipelines (M2 §4.3 step 1-4).

This module implements the four verb operations behind ``SkillManageTool``:

* :func:`do_create` — quota-checked create with layer-0/1/2 lock acquisition.
* :func:`do_edit`   — replace-body edit on an agent-tier skill.
* :func:`do_patch`  — single-occurrence search/replace edit.
* :func:`do_delete` — tombstone-emitting delete.

The dispatcher in :mod:`nanobot.agent.tools.skill_manage` performs cheap
rejects + verb routing and calls into these helpers. All telemetry bumps,
atomic writes, and lock acquisitions live in this module so the public
shell stays under the 700-LOC review ceiling (plan §t-08 last bullet).

Lock layer ordering (spec §3.7 / §8.6 LIFO release):

* Layer 0 — ``<workspace>/skills/agent/.create.lock``  (CREATE only)
* Layer 1 — module-level :class:`threading.Lock` keyed by skill name
* Layer 2 — ``<workspace>/skills/agent/<name>/.lock``
* Layers 3 / 4 — telemetry's own internal locks, taken inside ``bump``.
"""

from __future__ import annotations

import errno
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from nanobot.agent._atomic_io import (
    SkillManageError,
    atomic_write,
    fd_file_lock,
)

logger = logging.getLogger(__name__)

# --- Module-level layer-1 (in-process, per-name) lock registry --------------

# A single shared mutex protects the table itself. The per-name locks are
# regular ``threading.Lock`` objects; they are LAZY (created on demand) and
# never removed during process lifetime — the cardinality is bounded by
# ``max_agent_skills`` (default 200) so leak risk is negligible.
_NAME_LOCK_TABLE_GUARD = threading.Lock()
_NAME_LOCKS: dict[str, threading.Lock] = {}


def _get_name_lock(name: str) -> threading.Lock:
    with _NAME_LOCK_TABLE_GUARD:
        lock = _NAME_LOCKS.get(name)
        if lock is None:
            lock = threading.Lock()
            _NAME_LOCKS[name] = lock
        return lock


# --- errno → error_code mapping (spec §3.7.1 step 6) ------------------------

_ERRNO_TO_CODE: dict[int, str] = {
    errno.ENOENT: "not_found",
    errno.ELOOP: "path_escape",
    errno.EACCES: "atomic_write_failed",
    errno.EBUSY: "lock_busy",
    errno.EIO: "atomic_write_failed",
    errno.ENOSPC: "atomic_write_failed",
    errno.EEXIST: "name_exists",
    errno.ENOTDIR: "path_escape",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ws_path(workspace: Any) -> Path:
    """Coerce the workspace argument (str | Path) into a Path."""
    if isinstance(workspace, Path):
        return workspace
    return Path(str(workspace))


def _agent_root(workspace: Any) -> Path:
    return _ws_path(workspace) / "skills" / "agent"


# --- Frontmatter helpers ----------------------------------------------------


_FM_OPEN = "---\n"
_FM_CLOSE = "\n---\n"


def _serialize_skill(frontmatter: dict[str, Any], body: str) -> bytes:
    """Render `<frontmatter>\\n---\\n<body>` as UTF-8 bytes.

    `frontmatter` is dumped via ``yaml.safe_dump`` with sort_keys=False so
    the field order in the source remains reviewer-friendly. Trailing
    newline of yaml output is preserved; body is appended verbatim.
    """
    fm_text = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if not fm_text.endswith("\n"):
        fm_text += "\n"
    payload = "---\n" + fm_text + "---\n" + body
    return payload.encode("utf-8")


def _parse_skill(text: str) -> tuple[dict[str, Any], str]:
    """Split a SKILL.md into (frontmatter dict, body str).

    A SKILL.md without a frontmatter block returns ``({}, full_text)``.
    Bad YAML raises :class:`SkillManageError` with code ``corrupt_skill``.
    """
    if not text.startswith("---"):
        return ({}, text)
    # Find closing fence on its own line.
    rest = text[3:]
    # Skip the first newline after opening fence.
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    # Match the full 5-byte close fence "\n---\n" (matching what
    # `_serialize_skill` emits). Searching for "\n---" alone would split a
    # body whose first post-frontmatter bytes are "----" (markdown HR),
    # leaving a stray '-' attached to the body on round-trip.
    end = rest.find("\n---\n")
    if end < 0:
        return ({}, text)
    fm_text = rest[:end]
    # Skip "\n---\n" — exactly 5 chars.
    after = rest[end + 5:]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        raise SkillManageError(
            "corrupt_skill", f"frontmatter is not valid YAML: {exc}"
        )
    if not isinstance(fm, dict):
        raise SkillManageError(
            "corrupt_skill", "frontmatter must be a YAML mapping"
        )
    return (fm, after)


# --- Path-escape defense (spec §3.7.1 step 6) -------------------------------


def _safe_skill_md_path(workspace: Any, name: str) -> Path:
    """Resolve ``<workspace>/skills/agent/<name>/SKILL.md`` and assert it
    stays under the agent root, with O_NOFOLLOW semantics on read.

    Raises ``SkillManageError(path_escape)`` on a symlink at <name>/ or
    SKILL.md, or a resolved path outside of <skills/agent>/.

    Threat-model boundary (spec §security boundary): the leaf is
    O_NOFOLLOW-protected on open (TOCTOU swap of the leaf raises ELOOP);
    intermediate components are bounded by the workspace trust boundary
    plus layer-1+layer-2 cooperative locking. A non-cooperating writer
    with workspace access can still swap an intermediate directory
    between resolve() and open() — that scenario is INTENTIONALLY out of
    scope per spec (workspace integrity is a precondition).
    """
    agent_root = _agent_root(workspace).resolve(strict=True)
    candidate = agent_root / name / "SKILL.md"
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise SkillManageError("not_found", str(exc)) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SkillManageError(
                "path_escape", f"O_NOFOLLOW tripped: {candidate}"
            ) from exc
        raise
    try:
        resolved.relative_to(agent_root)
    except ValueError as exc:
        raise SkillManageError(
            "path_escape", f"{candidate} resolves outside agent root: {resolved}"
        ) from exc
    # Defense in depth: also reject if any path component on the way is a
    # symlink. ``resolve(strict=True)`` already mirrors the kernel's link
    # resolution, but we want O_NOFOLLOW open on the leaf so a TOCTOU
    # symlink swap between resolve() and open() is still caught.
    return candidate


def _read_skill_md_no_follow(path: Path) -> str:
    """Open ``path`` with O_NOFOLLOW + O_RDONLY and return UTF-8 text.

    Reuses the same flag set as :mod:`nanobot.agent._atomic_io` for write
    paths so symlink protection is symmetric across read/write.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    flags = os.O_RDONLY | nofollow | cloexec
    try:
        fd = os.open(str(path), flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise SkillManageError(
                "path_escape", f"O_NOFOLLOW tripped on read: {path}"
            ) from exc
        raise
    try:
        chunks: list[bytes] = []
        while True:
            buf = os.read(fd, 1 << 16)
            if not buf:
                break
            chunks.append(buf)
    finally:
        os.close(fd)
    return b"".join(chunks).decode("utf-8")


# --- Tier resolution (M1 list_skills_with_shadows) --------------------------


def _list_with_shadows(workspace: Any, disabled: set[str] | None = None) -> list[dict]:
    """Cheap pass-through to M1's :class:`SkillsLoader`.

    Built fresh each call because the verb pipelines mutate the on-disk
    layout under us; caching would be wrong.
    """
    from nanobot.agent.skills import SkillsLoader

    loader = SkillsLoader(_ws_path(workspace), disabled_skills=disabled or set())
    return loader.list_skills_with_shadows()


def _entry_for(name: str, shadows: list[dict]) -> dict | None:
    """Case-fold lookup so 'MySkill' collides with 'myskill'."""
    target = name.casefold()
    for e in shadows:
        if e["name"].casefold() == target:
            return e
    return None


# --- Verb implementations ---------------------------------------------------


def _reject(verb: str, name: str, code: str, msg: str = "") -> dict[str, Any]:
    """Local copy of skill_manage._reject; we duplicate the helper to avoid
    a circular import while keeping the shape identical."""
    return {
        "ok": False,
        "verb": verb,
        "name": name,
        "error_code": code,
        "error_message": msg,
    }


def _ok(verb: str, name: str, **extras: Any) -> dict[str, Any]:
    return {"ok": True, "verb": verb, "name": name, **extras}


def _map_oserror(exc: OSError, verb: str, name: str) -> dict[str, Any]:
    code = _ERRNO_TO_CODE.get(exc.errno or 0, "internal_error")
    return _reject(verb, name, code, str(exc))


def _cleanup_empty_skill_dir(skill_dir: Path) -> None:
    """Best-effort cleanup of `<name>/` on a failed create (YEL-DI-#4).

    Used by both the inner ``atomic_write`` failure branch and the outer
    layer-2 lock-acquisition failure branch of :func:`do_create` so a
    retry isn't blocked by a phantom ``name_exists``. On ENOTEMPTY we
    unlink the layer-2 ``.lock`` sentinel (the only file WE placed) and
    retry; any other residue is left intact. All OSErrors swallowed.
    """
    try:
        os.rmdir(skill_dir)
        return
    except OSError as exc:
        if exc.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            return
    try:
        os.unlink(skill_dir / ".lock")
    except OSError:
        pass
    try:
        os.rmdir(skill_dir)
    except OSError:
        pass


def do_create(
    *,
    workspace: Any,
    telemetry: Any,
    provenance_tag: str,
    name: str,
    description: str | None,
    body: str | None,
    requires: list[str] | None,
    max_agent_skills: int,
) -> dict[str, Any]:
    """`create` verb pipeline (spec §4.3 step 1)."""
    agent_root = _agent_root(workspace)
    # YEL-R5-1 fix: ensure the parent directory exists before fd_file_lock
    # tries to open `.create.lock` inside it.
    try:
        os.makedirs(agent_root, exist_ok=True)
    except OSError as exc:
        return _map_oserror(exc, "create", name)

    create_lock_path = agent_root / ".create.lock"
    try:
        # Layer 0: cross-process gate around quota-check + new-dir-create
        with fd_file_lock(create_lock_path, timeout=1.0):
            shadows = _list_with_shadows(workspace)
            agent_count = sum(
                1 for e in shadows if e["effective_origin"] == "agent"
            )
            if agent_count >= max_agent_skills:
                return _reject(
                    "create",
                    name,
                    "quota_exceeded",
                    f"agent tier already holds {agent_count} of "
                    f"{max_agent_skills} max",
                )

            existing = _entry_for(name, shadows)
            if existing is not None:
                if existing["effective_origin"] == "agent" \
                        and existing["name"] == name:
                    return _reject(
                        "create", name, "name_exists",
                        f"agent-tier skill '{name}' already exists",
                    )
                # Different tier OR case-variant in same tier → collision.
                return _reject(
                    "create", name, "name_collision",
                    f"name collides with {existing['effective_origin']}-tier "
                    f"'{existing['name']}'",
                )

            # Layer 1: in-process per-name lock
            with _get_name_lock(name):
                skill_dir = agent_root / name
                # Layer 2: fd lock on per-skill .lock file. The skill dir
                # doesn't exist yet, so we mkdir before acquiring layer 2;
                # mkdir failure on EEXIST falls through to name_exists.
                try:
                    os.mkdir(skill_dir, mode=0o700)
                except FileExistsError:
                    return _reject(
                        "create", name, "name_exists",
                        f"directory <skills/agent/{name}> already exists",
                    )
                except OSError as exc:
                    return _map_oserror(exc, "create", name)

                lock_path = skill_dir / ".lock"
                try:
                    with fd_file_lock(lock_path, timeout=1.0):
                        skill_md = skill_dir / "SKILL.md"
                        frontmatter = {
                            "origin": "agent",
                            "created_at": _now_iso(),
                            "created_by": provenance_tag,
                            "description": description or "",
                            "requires": list(requires or []),
                        }
                        try:
                            atomic_write(
                                skill_md,
                                _serialize_skill(frontmatter, body or ""),
                            )
                        except OSError as exc:
                            # YEL-DI-#4: best-effort cleanup of the empty
                            # `<name>/` dir we just created so a retry
                            # doesn't trip on phantom `name_exists`.
                            _cleanup_empty_skill_dir(skill_dir)
                            return _map_oserror(exc, "create", name)
                        # fix-bump-on-create: register the new entry on disk
                        # immediately via `telemetry.reconcile`. Without this,
                        # `_rmw_merge(writer="bump")` skips entries with
                        # `disk_entry is None` while flush phase 3 advances
                        # `_last_synced_counts` regardless → first patch
                        # counter for a freshly-created skill is permanently
                        # lost. Reconcile is the only legitimate creator of
                        # new on-disk entries (M1 invariant 3).
                        #
                        # Lock-order note: telemetry.reconcile internally
                        # acquires layer-3 (telemetry threading.Lock) and
                        # layer-4 (telemetry filelock). Both layers are
                        # numerically higher than layer-2 (held here), so
                        # ascending acquisition is preserved (spec §8.6).
                        #
                        # Failure handling mirrors `_edit_or_patch`: only
                        # OPERATIONAL OSError is swallowed + WARN-logged.
                        # The create itself MUST still succeed — the SKILL.md
                        # is already on disk; telemetry registration failure
                        # must not surface as a failed create envelope.
                        if telemetry is not None:
                            try:
                                shadows_after = _list_with_shadows(workspace)
                                known_entries = [
                                    {
                                        "name": e["name"],
                                        "effective_origin": e[
                                            "effective_origin"
                                        ],
                                        "shadowed_origins": list(
                                            e["shadowed_origins"]
                                        ),
                                        "path": e["path"],
                                    }
                                    for e in shadows_after
                                ]
                                telemetry.reconcile(known_entries)
                            except OSError as exc:
                                logger.warning(
                                    "skill_manage telemetry.reconcile failed "
                                    "(verb=create, name=%s): %s",
                                    name, exc,
                                )
                except SkillManageError as exc:
                    # Layer-2 failure: clean up the empty dir so subsequent
                    # creates aren't blocked by a phantom name_exists.
                    _cleanup_empty_skill_dir(skill_dir)
                    return _reject("create", name, exc.error_code, str(exc))
    except SkillManageError as exc:
        # Layer-0 failure (e.g. concurrency_timeout or PATH_ESCAPE on
        # `.create.lock`).
        code = "lock_busy" if exc.error_code == "concurrency_timeout" \
            else exc.error_code.lower()
        return _reject("create", name, code, str(exc))
    except RuntimeError as exc:
        # Windows: fd_file_lock raises RuntimeError. Surface as lock_busy
        # so the caller sees a verb-shaped reject rather than a 500.
        return _reject("create", name, "lock_busy", str(exc))

    # Telemetry: do NOT bump counters on create. Reconcile (called inside
    # the layer-2 lock above) registers the new entry with zero counters
    # so the first subsequent patch's counter delta is captured correctly
    # (fix-bump-on-create).
    return _ok("create", name)


def _open_load_skill(workspace: Any, name: str) -> tuple[Path, dict[str, Any], str]:
    """Resolve + read SKILL.md with path-escape defense.

    Returns (path, frontmatter_dict, body_str). Raises SkillManageError on
    path_escape, not_found, corrupt_skill.
    """
    skill_md = _safe_skill_md_path(workspace, name)
    raw = _read_skill_md_no_follow(skill_md)
    fm, body = _parse_skill(raw)
    return skill_md, fm, body


def _edit_or_patch(
    *,
    verb: str,
    workspace: Any,
    telemetry: Any,
    provenance_tag: str,
    name: str,
    description: str | None,
    requires: list[str] | None,
    body: str | None,
    search: str | None,
    replace: str | None,
) -> dict[str, Any]:
    """Shared body for `edit` and `patch` (spec §4.3 step 2/3)."""
    shadows = _list_with_shadows(workspace)
    entry = _entry_for(name, shadows)
    if entry is None:
        return _reject(verb, name, "not_found", f"skill '{name}' not found")
    if entry["effective_origin"] != "agent":
        return _reject(
            verb, name, "tier_locked",
            f"skill '{name}' is owned by tier "
            f"'{entry['effective_origin']}' and cannot be modified",
        )

    try:
        with _get_name_lock(name):
            skill_dir = _agent_root(workspace) / name
            lock_path = skill_dir / ".lock"
            try:
                with fd_file_lock(lock_path, timeout=1.0):
                    try:
                        skill_md, fm, current_body = _open_load_skill(
                            workspace, name
                        )
                    except SkillManageError as exc:
                        return _reject(verb, name, exc.error_code, str(exc))
                    except OSError as exc:
                        return _map_oserror(exc, verb, name)

                    if verb == "edit":
                        new_body = body if body is not None else current_body
                    else:  # patch
                        if search is None or replace is None:
                            return _reject(
                                verb, name, "invalid_args",
                                "patch requires both 'search' and 'replace'",
                            )
                        count = current_body.count(search)
                        if count == 0:
                            return _reject(
                                verb, name, "search_not_found",
                                "search string not present in body",
                            )
                        if count > 1:
                            return _reject(
                                verb, name, "search_ambiguous",
                                f"search string appears {count} times "
                                f"(must be unique)",
                            )
                        new_body = current_body.replace(search, replace, 1)

                    new_fm = dict(fm)
                    if description is not None:
                        new_fm["description"] = description
                    if requires is not None:
                        new_fm["requires"] = list(requires)
                    new_fm["last_patched_at"] = _now_iso()
                    new_fm["patched_by"] = provenance_tag

                    try:
                        atomic_write(
                            skill_md, _serialize_skill(new_fm, new_body)
                        )
                    except OSError as exc:
                        return _map_oserror(exc, verb, name)
            except SkillManageError as exc:
                code = "lock_busy" if exc.error_code == "concurrency_timeout" \
                    else exc.error_code.lower()
                return _reject(verb, name, code, str(exc))
            except RuntimeError as exc:
                return _reject(verb, name, "lock_busy", str(exc))
    except SkillManageError as exc:
        return _reject(verb, name, exc.error_code, str(exc))

    # Telemetry: edit/patch both bump the patch counter. M1's bump kind
    # vocabulary uses "patch" for any agent-driven edit. Only swallow
    # OPERATIONAL errors here — programmer-error classes (RuntimeError,
    # AssertionError, ValueError on unknown kind, KeyError) propagate so
    # bugs surface in tests instead of being silently dropped (YEL-DI-#1).
    if telemetry is not None:
        try:
            telemetry.bump(name, "patch")
        except OSError as exc:
            logger.warning(
                "skill_manage telemetry.bump failed (kind=patch, name=%s): %s",
                name, exc,
            )
    return _ok(verb, name)


def do_edit(
    *,
    workspace: Any,
    telemetry: Any,
    provenance_tag: str,
    name: str,
    description: str | None,
    requires: list[str] | None,
    body: str | None,
) -> dict[str, Any]:
    return _edit_or_patch(
        verb="edit",
        workspace=workspace,
        telemetry=telemetry,
        provenance_tag=provenance_tag,
        name=name,
        description=description,
        requires=requires,
        body=body,
        search=None,
        replace=None,
    )


def do_patch(
    *,
    workspace: Any,
    telemetry: Any,
    provenance_tag: str,
    name: str,
    description: str | None,
    requires: list[str] | None,
    search: str | None,
    replace: str | None,
) -> dict[str, Any]:
    return _edit_or_patch(
        verb="patch",
        workspace=workspace,
        telemetry=telemetry,
        provenance_tag=provenance_tag,
        name=name,
        description=description,
        requires=requires,
        body=None,
        search=search,
        replace=replace,
    )


def do_delete(
    *,
    workspace: Any,
    telemetry: Any,
    provenance_tag: str,
    name: str,
) -> dict[str, Any]:
    """`delete` verb pipeline (spec §4.3 step 4).

    Idempotency choice (documented per plan §t-08 ambiguity): missing
    SKILL.md returns ``not_found`` reject WITHOUT bumping telemetry. This
    is the clearer of the two readings of "idempotent not_found" — the
    "idempotent" descriptor refers to no-op-on-missing rather than
    success-on-missing.
    """
    shadows = _list_with_shadows(workspace)
    entry = _entry_for(name, shadows)
    if entry is None:
        return _reject("delete", name, "not_found", f"skill '{name}' not found")
    if entry["effective_origin"] != "agent":
        return _reject(
            "delete", name, "tier_locked",
            f"skill '{name}' is owned by tier "
            f"'{entry['effective_origin']}' and cannot be deleted",
        )

    skill_dir = _agent_root(workspace) / name
    lock_path = skill_dir / ".lock"
    # YEL-SEC-1 / YEL-DI-#4: route through the same path-escape defense
    # used by edit/patch BEFORE we acquire the layer-2 lock. The resolve
    # must succeed while SKILL.md is still on disk (resolve(strict=True)
    # raises if missing), and ELOOP/relative_to checks reject symlink
    # redirects pointing outside the agent root.
    try:
        safe_skill_md = _safe_skill_md_path(workspace, name)
    except SkillManageError as exc:
        return _reject("delete", name, exc.error_code, str(exc))
    try:
        with _get_name_lock(name):
            try:
                with fd_file_lock(lock_path, timeout=1.0):
                    if not safe_skill_md.exists():
                        return _reject(
                            "delete", name, "not_found",
                            "SKILL.md vanished before delete",
                        )
                    try:
                        os.unlink(safe_skill_md)
                    except FileNotFoundError:
                        return _reject(
                            "delete", name, "not_found",
                            "SKILL.md vanished before delete",
                        )
                    except OSError as exc:
                        return _map_oserror(exc, "delete", name)

                    # Best-effort dir cleanup. Skip if the dir still has
                    # other content (e.g. a user-dropped README); telemetry
                    # bump still happens because SKILL.md is what defines
                    # the skill.
                    try:
                        # Probe for non-lock content before rmdir.
                        residue = [
                            p for p in skill_dir.iterdir()
                            if p.name != ".lock"
                        ]
                        if not residue:
                            # Best-effort: a peer process that opened
                            # `.lock` fd before we got here holds a flock
                            # on an unlinked inode for a microsecond
                            # window. Not a corruption risk — SKILL.md is
                            # already gone and any re-create acquires
                            # layer-0 (`.create.lock`) first, ensuring
                            # serial reuse.
                            try:
                                os.unlink(lock_path)
                            except OSError:
                                pass
                            try:
                                os.rmdir(skill_dir)
                            except OSError:
                                pass
                    except OSError:
                        pass
            except SkillManageError as exc:
                code = "lock_busy" if exc.error_code == "concurrency_timeout" \
                    else exc.error_code.lower()
                return _reject("delete", name, code, str(exc))
            except RuntimeError as exc:
                return _reject("delete", name, "lock_busy", str(exc))
    except SkillManageError as exc:
        return _reject("delete", name, exc.error_code, str(exc))

    # Tombstone — counters stay monotonic; reconcile resets if reused.
    # Same narrowing as edit/patch: only OPERATIONAL OSError swallowed
    # (and logged); programmer-errors propagate (YEL-DI-#1).
    if telemetry is not None:
        try:
            telemetry.bump(name, "delete")
        except OSError as exc:
            logger.warning(
                "skill_manage telemetry.bump failed (kind=delete, name=%s): %s",
                name, exc,
            )
    return _ok("delete", name)


__all__ = [
    "do_create",
    "do_delete",
    "do_edit",
    "do_patch",
    "_ERRNO_TO_CODE",
    "_get_name_lock",
    "_now_iso",
    "_serialize_skill",
    "_parse_skill",
]
