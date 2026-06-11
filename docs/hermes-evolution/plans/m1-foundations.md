# M1 · Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 nanobot 中落地 Hermes 自我进化能力的地基层（M1）：skill provenance、三源 SkillsLoader、SkillTelemetry 子系统（双层锁 + RMW 增量合并 + 原子写）、auxiliary provider 配置形态。

**Architecture:** 新增独立模块 `nanobot/agent/skills_telemetry.py` 承载并发安全的计数子系统；对现有 `SkillsLoader` 做"附加"式扩展（新增方法 + keyword-only telemetry 注入，不破坏现有 caller）；`AgentLoop` 在启动期编排 `SkillTelemetry → SkillsLoader → reconcile`，并在 turn 出口 + `atexit` 触发 flush；`AuxiliaryConfig` 通过 Pydantic 根 `model_validator` 保证 preset 引用合法。

**Tech Stack:** Python 3.11+ asyncio，`filelock>=3.25.2`（已在依赖中），`pydantic` v2（root `model_validator`），`pytest`（`asyncio_mode = "auto"`，`multiprocessing.get_context("spawn")`）。

**Spec：** [`docs/hermes-evolution/specs/m1-foundations.md`](../specs/m1-foundations.md)

---

## 文件结构（File Structure）

> 任何与现有代码"行号"挂钩的引用，以 spec §7 caller 实证表为准；下表中行号是 spec 写定时的现状基线。

**新建：**

- `nanobot/agent/skills_telemetry.py` — `SkillTelemetry` 类 + `SkillEntry`/`TelemetryEntrySnapshot`/`TelemetrySnapshot`/`BumpKind`/`Writer` TypedDicts + 内部 `_zero_entry_with_unknown_origin` / `_atomic_write` / `_safe_read_json` / `_rmw_merge` 工具。
- `tests/agent/test_skills_telemetry.py` — `SkillTelemetry` 的单元测试（bump / reconcile / flush / 并发 / 失败降级 / 单飞）。
- `tests/agent/test_subagent_telemetry.py` — 子 agent 复用主 telemetry 的集成测试。
- `tests/agent/test_runner_telemetry_startup.py` — 启动序列硬性合同（init → loader → reconcile → consume）+ keyword-only 验证。
- `tests/webui/test_skills_api_telemetry.py` — WebUI 旁路不污染计数。

**修改：**

- `nanobot/agent/skills.py` — 三源加载、`list_skills_with_shadows()`、`_infer_origin_from_path()`、`_entries_from_agent_dir()`、collision warning（一次）、`__init__` 增加 keyword-only `telemetry`、`build_skills_summary` / `load_skills_for_context` 函数体内 gated bump、`_get_skill_meta` 上方契约注释。
- `nanobot/agent/context.py` — `ContextBuilder.__init__` 接受 `telemetry` 并传给 `SkillsLoader`。
- `nanobot/agent/subagent.py` — `SubagentManager.__init__` 接受 `telemetry`；`_build_subagent_prompt` 构造 `SkillsLoader` 时传 `telemetry`。
- `nanobot/agent/loop.py` — `AgentLoop.__init__` 构造 `SkillTelemetry`、注入 ContextBuilder / SubagentManager、`atexit.register(telemetry.flush)`；`run()` 启动 MCP 后先 `telemetry.reconcile(loader.list_skills_with_shadows())` 再进入 consume 循环；`_run_agent_loop` 返回前调用 `self.telemetry.flush()`。
- `nanobot/webui/skills_api.py` — 显式 `telemetry=None`（虽然是默认值，仍写出显式 kwarg 作为"声明意图"）。
- `nanobot/config/schema.py` — 新增 `AuxiliaryConfig`、`AgentDefaults.auxiliary`、`Config._validate_auxiliary_preset` root `model_validator`。
- `nanobot/providers/factory.py` — 新增 `get_auxiliary_client(config) -> LLMProvider`。

**扩展现有测试：**

- `tests/agent/test_skills_loader.py` — 三源优先级 / collision / `list_skills_with_shadows` / disabled 过滤 / `list_skills` 不触发 bump。
- `tests/config/test_model_presets.py`（或新建 `tests/config/test_auxiliary_config.py`）— `auxiliary.modelPreset` 解析 + camelCase + 校验失败。
- `tests/providers/test_factory.py` — `get_auxiliary_client` 解析 + fallback + 运行时 ConfigError。

**依赖图：**

```
A. SkillTelemetry 核心 (skills_telemetry.py + 单元测试)
        │
        ├──► B. SkillsLoader 三源 + bump hooks (skills.py)
        │       │
        │       └──► C. 上层 wiring (context.py / subagent.py / loop.py / webui)
        │               │
        │               └──► E. 集成测试 (startup / subagent / webui)
        │
D. AuxiliaryConfig + factory (schema.py + factory.py) — 与 A/B/C 并行
```

---

## Phase A: SkillTelemetry 核心模块

### Task A1: 建空模块 + TypedDicts + `SkillTelemetry.__init__` 骨架

**Files:**
- Create: `nanobot/agent/skills_telemetry.py`
- Create: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_skills_telemetry.py
from pathlib import Path

import pytest

from nanobot.agent.skills_telemetry import (
    BumpKind,
    SkillEntry,
    SkillTelemetry,
    TelemetryEntrySnapshot,
    TelemetrySnapshot,
    Writer,
)


def test_construct_on_fresh_workspace_creates_parent_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    # NOTE: workspace 本身不存在，skills/ 不存在 —— 必须由 __init__ 自建
    telem = SkillTelemetry(workspace)
    assert (workspace / "skills").is_dir()
    snap = telem.snapshot()
    assert snap["schema_version"] == 1
    assert snap["entries"] == {}


def test_typeddict_keys_match_spec_field_table() -> None:
    # 静态检查 TypedDict 形态与 spec §4.2 一致
    assert set(SkillEntry.__annotations__) == {
        "name", "effective_origin", "shadowed_origins", "path",
    }
    assert set(TelemetryEntrySnapshot.__annotations__) == {
        "origin", "shadowed", "views", "uses", "patches",
        "entry_created_at", "last_view", "last_use",
    }
    assert set(TelemetrySnapshot.__annotations__) == {
        "schema_version", "updated_at", "entries",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nanobot.agent.skills_telemetry'`

- [ ] **Step 3: Write minimal implementation**

```python
# nanobot/agent/skills_telemetry.py
"""Skill view/use/patch telemetry with two-layer locking and RMW merge."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Literal, TypedDict

BumpKind = Literal["view", "use", "patch"]
Writer = Literal["bump", "reconcile"]


class SkillEntry(TypedDict):
    name: str
    effective_origin: Literal["user", "agent", "builtin"]
    shadowed_origins: list[str]
    path: str


class TelemetryEntrySnapshot(TypedDict):
    origin: Literal["user", "agent", "builtin", "unknown"]
    shadowed: list[str]
    views: int
    uses: int
    patches: int
    entry_created_at: str
    last_view: str | None
    last_use: str | None


class TelemetrySnapshot(TypedDict):
    schema_version: int
    updated_at: str
    entries: dict[str, TelemetryEntrySnapshot]


SCHEMA_VERSION = 1
TELEMETRY_FILENAME = ".telemetry.json"
LOCK_FILENAME = ".telemetry.json.lock"
TMP_GLOB = ".telemetry.json.tmp*"


class SkillTelemetry:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._skills_dir = workspace / "skills"
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._skills_dir / TELEMETRY_FILENAME
        self._lock_path = self._skills_dir / LOCK_FILENAME
        self._lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._entries: dict[str, TelemetryEntrySnapshot] = {}
        self._last_synced_counts: dict[str, dict[str, int]] = {}
        self._dirty = False
        # .tmp residue cleanup happens before any reconcile
        for stale in self._skills_dir.glob(TMP_GLOB):
            try:
                stale.unlink()
            except OSError:
                pass

    def snapshot(self) -> TelemetrySnapshot:
        from copy import deepcopy
        with self._lock:
            return {
                "schema_version": SCHEMA_VERSION,
                "updated_at": _now_iso(),
                "entries": deepcopy(self._entries),
            }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): scaffold SkillTelemetry module + TypedDicts (M1 Task A1)"
```

---

### Task A2: `bump()` in-memory counters with `threading.Lock`

**Files:**
- Modify: `nanobot/agent/skills_telemetry.py`
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_bump_increments_correct_counter_and_timestamp(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.bump("foo", "view")
    telem.bump("foo", "view")
    telem.bump("foo", "use")
    snap = telem.snapshot()
    e = snap["entries"]["foo"]
    assert e["views"] == 2
    assert e["uses"] == 1
    assert e["patches"] == 0
    assert e["origin"] == "unknown"
    assert e["last_view"] is not None
    assert e["last_use"] is not None
    assert e["entry_created_at"] is not None


def test_bump_rejects_unknown_kind(tmp_path: Path) -> None:
    import pytest
    telem = SkillTelemetry(tmp_path / "ws")
    with pytest.raises(ValueError):
        telem.bump("foo", "nope")  # type: ignore[arg-type]


def test_bump_dirty_flag_set(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    assert telem._dirty is False
    telem.bump("foo", "view")
    assert telem._dirty is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agent/test_skills_telemetry.py::test_bump_increments_correct_counter_and_timestamp -v`
Expected: FAIL with `AttributeError: 'SkillTelemetry' object has no attribute 'bump'`

- [ ] **Step 3: Write minimal implementation**

Add to `SkillTelemetry`:

```python
_KIND_TO_COUNTER = {"view": "views", "use": "uses", "patch": "patches"}
_KIND_TO_LAST_TS = {"view": "last_view", "use": "last_use", "patch": None}


def _zero_entry_with_unknown_origin() -> TelemetryEntrySnapshot:
    return {
        "origin": "unknown",
        "shadowed": [],
        "views": 0,
        "uses": 0,
        "patches": 0,
        "entry_created_at": _now_iso(),
        "last_view": None,
        "last_use": None,
    }


# inside class SkillTelemetry:
def bump(self, name: str, kind: BumpKind) -> None:
    if kind not in _KIND_TO_COUNTER:
        raise ValueError(f"unknown bump kind: {kind!r}")
    counter_key = _KIND_TO_COUNTER[kind]
    last_ts_key = _KIND_TO_LAST_TS[kind]
    now = _now_iso()
    with self._lock:
        entry = self._entries.setdefault(name, _zero_entry_with_unknown_origin())
        entry[counter_key] = entry[counter_key] + 1  # type: ignore[literal-required]
        if last_ts_key is not None:
            entry[last_ts_key] = now  # type: ignore[literal-required]
        self._dirty = True
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (3 new tests + 2 prior tests = 5)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): add bump(name, kind) with threading lock (M1 Task A2)"
```

---

### Task A3: Atomic write helper + `_safe_read_json`

**Files:**
- Modify: `nanobot/agent/skills_telemetry.py`
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_atomic_write_creates_file_and_no_tmp_residue(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import _atomic_write
    target = tmp_path / "data.json"
    _atomic_write(target, {"foo": 1})
    assert target.read_text() == '{"foo": 1}' or '"foo": 1' in target.read_text()
    leftover = list(tmp_path.glob("data.json.tmp*"))
    assert leftover == []


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import _atomic_write
    target = tmp_path / "data.json"
    target.write_text('{"old": true}')
    _atomic_write(target, {"new": True})
    import json
    assert json.loads(target.read_text()) == {"new": True}


def test_safe_read_json_returns_default_on_missing(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import _safe_read_json
    result = _safe_read_json(tmp_path / "missing.json")
    assert result is None


def test_safe_read_json_handles_corrupt_file(tmp_path: Path, caplog) -> None:
    import logging
    from nanobot.agent.skills_telemetry import _safe_read_json
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    with caplog.at_level(logging.WARNING):
        result = _safe_read_json(corrupt)
    assert result is None
    backup = next(tmp_path.glob("corrupt.json.corrupted.*"), None)
    assert backup is not None, "corrupted file must be backed up"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py::test_atomic_write_creates_file_and_no_tmp_residue -v`
Expected: FAIL with `ImportError` for `_atomic_write`.

- [ ] **Step 3: Write minimal implementation**

Add to `nanobot/agent/skills_telemetry.py`:

```python
import json
import os
import sys
from loguru import logger


def _atomic_write(path: Path, payload: dict) -> None:
    """tmp + fsync(tmp) + os.replace + fsync(parent_dir) on POSIX."""
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    if sys.platform != "win32":
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _safe_read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        backup = path.with_suffix(path.suffix + f".corrupted.{int(_epoch_ms())}")
        try:
            path.rename(backup)
        except OSError:
            pass
        logger.warning(
            "telemetry: corrupt JSON at {} (kind=json_corruption): {}; backed up to {}",
            path, exc, backup,
        )
        return None


def _epoch_ms() -> float:
    import time
    return time.time() * 1000
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (4 new + 5 prior = 9)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): atomic_write + safe_read_json with corruption backup (M1 Task A3)"
```

---

### Task A4: `_rmw_merge()` 合并规则（核心反 lost-update）

**Files:**
- Modify: `nanobot/agent/skills_telemetry.py`
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_rmw_counters_incremental_add_on_existing_entry() -> None:
    from nanobot.agent.skills_telemetry import _rmw_merge
    on_disk = {
        "schema_version": 1,
        "updated_at": "2026-06-10T00:00:00Z",
        "entries": {
            "foo": {
                "origin": "user", "shadowed": [],
                "views": 100, "uses": 30, "patches": 0,
                "entry_created_at": "2026-06-01T00:00:00Z",
                "last_view": "2026-06-09T00:00:00Z",
                "last_use": None,
            }
        },
    }
    snapshot = {
        "foo": {
            "origin": "unknown", "shadowed": [],
            "views": 10, "uses": 3, "patches": 0,
            "entry_created_at": "2026-06-05T00:00:00Z",
            "last_view": "2026-06-11T01:00:00Z",
            "last_use": None,
        }
    }
    # last_synced_counts says "we previously flushed 7 views, 2 uses for foo"
    last_synced = {"foo": {"views": 7, "uses": 2, "patches": 0}}
    merged = _rmw_merge(on_disk, snapshot, last_synced, writer="bump")
    # Disk had 100 + delta(10-7=3) = 103
    assert merged["entries"]["foo"]["views"] == 103
    # Disk had 30 + delta(3-2=1) = 31
    assert merged["entries"]["foo"]["uses"] == 31
    # origin/shadowed preserved from on_disk (writer="bump" never touches origin)
    assert merged["entries"]["foo"]["origin"] == "user"
    # last_view = max(disk, snapshot)
    assert merged["entries"]["foo"]["last_view"] == "2026-06-11T01:00:00Z"
    # entry_created_at = min(disk, snapshot)
    assert merged["entries"]["foo"]["entry_created_at"] == "2026-06-01T00:00:00Z"


def test_rmw_bump_only_skips_orphan_entry_not_on_disk() -> None:
    from nanobot.agent.skills_telemetry import _rmw_merge
    on_disk = {"schema_version": 1, "updated_at": "x", "entries": {}}
    snapshot = {
        "foo": {
            "origin": "unknown", "shadowed": [],
            "views": 5, "uses": 0, "patches": 0,
            "entry_created_at": "2026-06-11T00:00:00Z",
            "last_view": "2026-06-11T00:00:00Z", "last_use": None,
        }
    }
    merged = _rmw_merge(on_disk, snapshot, {}, writer="bump")
    assert merged["entries"] == {}  # bump cannot resurrect entry reconcile killed


def test_rmw_reconcile_creates_new_entry() -> None:
    from nanobot.agent.skills_telemetry import _rmw_merge
    on_disk = {"schema_version": 1, "updated_at": "x", "entries": {}}
    snapshot = {
        "bar": {
            "origin": "agent", "shadowed": [],
            "views": 0, "uses": 0, "patches": 0,
            "entry_created_at": "2026-06-11T00:00:00Z",
            "last_view": None, "last_use": None,
        }
    }
    merged = _rmw_merge(on_disk, snapshot, {}, writer="reconcile")
    assert merged["entries"]["bar"]["origin"] == "agent"


def test_rmw_writer_reconcile_unknown_origin_does_not_overwrite_known() -> None:
    from nanobot.agent.skills_telemetry import _rmw_merge
    on_disk = {
        "schema_version": 1, "updated_at": "x",
        "entries": {"baz": {
            "origin": "user", "shadowed": [],
            "views": 1, "uses": 0, "patches": 0,
            "entry_created_at": "2026-06-01T00:00:00Z",
            "last_view": None, "last_use": None,
        }},
    }
    snapshot = {"baz": {
        "origin": "unknown", "shadowed": [],
        "views": 1, "uses": 0, "patches": 0,
        "entry_created_at": "2026-06-01T00:00:00Z",
        "last_view": None, "last_use": None,
    }}
    merged = _rmw_merge(on_disk, snapshot, {"baz": {"views": 1, "uses": 0, "patches": 0}},
                        writer="reconcile")
    assert merged["entries"]["baz"]["origin"] == "user"  # unknown never overwrites known


def test_rmw_preserves_unknown_top_level_fields() -> None:
    from nanobot.agent.skills_telemetry import _rmw_merge
    on_disk = {
        "schema_version": 2,
        "updated_at": "x",
        "entries": {"foo": {
            "origin": "user", "shadowed": [], "views": 1, "uses": 0, "patches": 0,
            "entry_created_at": "x", "last_view": None, "last_use": None,
            "cooldown_until": "2026-12-01T00:00:00Z",  # future field
        }},
        "future_top": {"hello": "world"},
    }
    snapshot = {"foo": {
        "origin": "user", "shadowed": [], "views": 1, "uses": 0, "patches": 0,
        "entry_created_at": "x", "last_view": None, "last_use": None,
    }}
    merged = _rmw_merge(on_disk, snapshot, {"foo": {"views": 1, "uses": 0, "patches": 0}},
                        writer="bump")
    assert merged["future_top"] == {"hello": "world"}
    assert merged["entries"]["foo"]["cooldown_until"] == "2026-12-01T00:00:00Z"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k rmw`
Expected: FAIL with ImportError.

- [ ] **Step 3: Write minimal implementation**

```python
def _rmw_merge(
    on_disk: dict | None,
    snapshot: dict,
    last_synced: dict,
    writer: Writer,
) -> dict:
    """Merge per spec §4.3 RMW table.

    on_disk: full telemetry doc as read from disk (None / corrupt → rebuild empty).
    snapshot: in-memory entries dict only ({name: entry}).
    last_synced: {name: {views, uses, patches}} previously flushed by this process.
    writer: "bump" or "reconcile" — controls origin/shadowed merge branch.
    """
    base = on_disk if isinstance(on_disk, dict) and "entries" in on_disk else {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now_iso(),
        "entries": {},
    }
    disk_entries: dict = dict(base.get("entries", {}))
    seen: set[str] = set()

    for name, snap_entry in snapshot.items():
        seen.add(name)
        disk_entry = disk_entries.get(name)
        if disk_entry is None:
            # Branch: entry only in snapshot
            if writer == "bump":
                continue  # do not resurrect
            # writer == "reconcile" → first landing
            disk_entries[name] = dict(snap_entry)
            continue
        # Branch: entry in both
        merged_entry = dict(disk_entry)  # preserve unknown future fields
        last = last_synced.get(name, {"views": 0, "uses": 0, "patches": 0})
        for counter in ("views", "uses", "patches"):
            delta = max(snap_entry.get(counter, 0) - last.get(counter, 0), 0)
            merged_entry[counter] = disk_entry.get(counter, 0) + delta
        merged_entry["last_view"] = _max_iso(disk_entry.get("last_view"), snap_entry.get("last_view"))
        merged_entry["last_use"] = _max_iso(disk_entry.get("last_use"), snap_entry.get("last_use"))
        merged_entry["entry_created_at"] = _min_iso(
            disk_entry.get("entry_created_at"), snap_entry.get("entry_created_at")
        )
        if writer == "reconcile" and snap_entry.get("origin") != "unknown":
            merged_entry["origin"] = snap_entry["origin"]
            merged_entry["shadowed"] = list(snap_entry.get("shadowed", []))
        disk_entries[name] = merged_entry

    # Entries only on disk (snapshot didn't touch them) → keep as-is
    base = dict(base)
    base["entries"] = disk_entries
    base["schema_version"] = max(int(base.get("schema_version", SCHEMA_VERSION)), SCHEMA_VERSION)
    base["updated_at"] = _now_iso()
    return base


def _max_iso(a: str | None, b: str | None) -> str | None:
    if a is None: return b
    if b is None: return a
    return a if a >= b else b


def _min_iso(a: str | None, b: str | None) -> str | None:
    if a is None: return b
    if b is None: return a
    return a if a <= b else b
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (5 new + 9 prior = 14)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): rmw_merge with writer-tag branches + unknown-field passthrough (M1 Task A4)"
```

---

### Task A5: `flush()` with filelock + single-flight + 3-phase pipeline

**Files:**
- Modify: `nanobot/agent/skills_telemetry.py`
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from copy import deepcopy


def test_flush_writes_disk_and_advances_last_synced(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.bump("foo", "view")
    telem.bump("foo", "view")
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 2
    assert telem._last_synced_counts["foo"]["views"] == 2
    assert telem._dirty is False


def test_flush_noop_when_not_dirty(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.flush()  # no bump → no-op
    assert not (tmp_path / "ws" / "skills" / ".telemetry.json").exists()


def test_flush_rmw_preserves_concurrent_process_writes(tmp_path: Path) -> None:
    # Process A: bump 5 views, flush, then bump 3 more
    # Meanwhile simulate "process B" by editing disk directly between flushes
    telem = SkillTelemetry(tmp_path / "ws")
    for _ in range(5):
        telem.bump("shared", "view")
    telem.flush()
    # External process bumps disk by 7 (simulating another nanobot writing)
    path = tmp_path / "ws" / "skills" / ".telemetry.json"
    on_disk = json.loads(path.read_text())
    on_disk["entries"]["shared"]["views"] += 7
    path.write_text(json.dumps(on_disk))
    # Process A bumps 3 more, flush → should be 5+7+3 = 15
    for _ in range(3):
        telem.bump("shared", "view")
    telem.flush()
    final = json.loads(path.read_text())
    assert final["entries"]["shared"]["views"] == 15


def test_flush_single_flight_second_call_is_noop(tmp_path: Path, monkeypatch) -> None:
    import threading
    telem = SkillTelemetry(tmp_path / "ws")
    telem.bump("foo", "view")
    call_count = {"n": 0}
    real_atomic = telem.__class__.__module__ + "._atomic_write"
    from nanobot.agent import skills_telemetry as st
    orig = st._atomic_write
    started = threading.Event()
    block = threading.Event()

    def slow_write(path, payload):
        call_count["n"] += 1
        started.set()
        block.wait(timeout=2.0)
        orig(path, payload)

    monkeypatch.setattr(st, "_atomic_write", slow_write)
    t = threading.Thread(target=telem.flush)
    t.start()
    started.wait(timeout=2.0)
    telem.flush()  # second concurrent flush — must be no-op
    block.set()
    t.join(timeout=2.0)
    assert call_count["n"] == 1
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k flush`
Expected: FAIL with `AttributeError: 'SkillTelemetry' object has no attribute 'flush'`

- [ ] **Step 3: Write minimal implementation**

Add to `SkillTelemetry`:

```python
from copy import deepcopy
import filelock

FILELOCK_TIMEOUT_S = 0.2
FILELOCK_RETRIES = 3
WARN_COALESCE_EVERY = 100


def flush(self, writer: Writer = "bump") -> None:
    # ----- Single-flight gate -----
    if not self._flush_lock.acquire(blocking=False):
        return  # another flush already in flight → no-op
    try:
        # ----- Phase 1: snapshot under self._lock -----
        with self._lock:
            if not self._dirty:
                return
            snapshot = deepcopy(self._entries)
            last_synced_snapshot = deepcopy(self._last_synced_counts)
        # ----- Phase 2: filelock + RMW + atomic write -----
        try:
            success = self._write_phase(snapshot, last_synced_snapshot, writer)
        except Exception:
            self._note_failure("atomic_write_io_error")
            return
        if not success:
            self._note_failure("filelock_timeout")
            return
        # ----- Phase 3: advance _last_synced_counts under self._lock -----
        with self._lock:
            for name, entry in snapshot.items():
                slot = self._last_synced_counts.setdefault(
                    name, {"views": 0, "uses": 0, "patches": 0}
                )
                for k in ("views", "uses", "patches"):
                    slot[k] = entry[k]
            if self._entries == snapshot:
                self._dirty = False
    finally:
        self._flush_lock.release()


def _write_phase(self, snapshot, last_synced_snapshot, writer: Writer) -> bool:
    lock = filelock.FileLock(str(self._lock_path), timeout=FILELOCK_TIMEOUT_S)
    last_err: Exception | None = None
    for attempt in range(FILELOCK_RETRIES):
        try:
            with lock:
                on_disk = _safe_read_json(self._path)
                merged = _rmw_merge(on_disk, snapshot, last_synced_snapshot, writer)
                _atomic_write(self._path, merged)
            return True
        except filelock.Timeout as exc:
            last_err = exc
            continue
    return False


def _note_failure(self, kind: str) -> None:
    bucket = self._failure_counts.setdefault(kind, 0) + 1
    self._failure_counts[kind] = bucket
    if bucket % WARN_COALESCE_EVERY == 0:
        logger.warning(
            "telemetry failure coalesced (kind={}, coalesced_count={})",
            kind, bucket,
        )
```

Also add to `__init__`:

```python
self._failure_counts: dict[str, int] = {}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (4 new + 14 prior = 18)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): 3-phase flush with filelock RMW + single-flight gate (M1 Task A5)"
```

---

### Task A6: `flush()` filelock timeout WARN throttle + `_dirty` preservation

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_flush_filelock_timeout_preserves_dirty_and_last_synced(tmp_path, monkeypatch) -> None:
    import filelock
    from nanobot.agent import skills_telemetry as st
    telem = SkillTelemetry(tmp_path / "ws")
    telem.bump("foo", "view")

    class AlwaysTimeout:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise filelock.Timeout("lock")
        def __exit__(self, *a): return False

    monkeypatch.setattr(st.filelock, "FileLock", AlwaysTimeout)
    telem.flush()
    # disk file never created; in-memory state preserved
    assert not (tmp_path / "ws" / "skills" / ".telemetry.json").exists()
    assert telem._dirty is True
    assert telem._last_synced_counts == {}


def test_warn_throttle_emits_once_per_100_failures(tmp_path, monkeypatch, caplog) -> None:
    import filelock, logging
    from nanobot.agent import skills_telemetry as st
    telem = SkillTelemetry(tmp_path / "ws")

    class AlwaysTimeout:
        def __init__(self, *a, **kw): pass
        def __enter__(self): raise filelock.Timeout("lock")
        def __exit__(self, *a): return False

    monkeypatch.setattr(st.filelock, "FileLock", AlwaysTimeout)
    with caplog.at_level(logging.WARNING):
        for i in range(250):
            telem.bump("foo", "view")
            telem.flush()
    filelock_warns = [r for r in caplog.records if "filelock_timeout" in r.getMessage()]
    # Coalesced every 100 → 2 warnings for 200/250 thresholds; 250 itself doesn't trigger
    assert len(filelock_warns) == 2
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k "filelock_timeout or warn_throttle"`
Expected: PASS (logic in A5 already supports this). If FAIL, fix bookkeeping in `_note_failure`.

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_skills_telemetry.py
git commit -m "test(telemetry): cover filelock timeout warn throttle (M1 Task A6)"
```

---

### Task A7: `reconcile()` arrival / orphan / origin update + frozen disabled skills

**Files:**
- Modify: `nanobot/agent/skills_telemetry.py`
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def _make_entry(name: str, origin: str = "user", path: str = "/x/SKILL.md") -> SkillEntry:
    return {"name": name, "effective_origin": origin, "shadowed_origins": [], "path": path}


def test_reconcile_creates_zero_entry_for_new_skill(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    snap = telem.snapshot()
    e = snap["entries"]["foo"]
    assert e["origin"] == "user"
    assert e["views"] == 0
    assert e["uses"] == 0
    assert e["entry_created_at"] is not None


def test_reconcile_removes_orphan_entry(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    telem.bump("foo", "view")
    telem.flush()
    # remove foo from known list → orphan
    telem.reconcile([])
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert "foo" not in data["entries"]
    assert "foo" not in telem._last_synced_counts


def test_reconcile_freezes_disabled_skill_entry(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    for _ in range(7):
        telem.bump("foo", "view")
    telem.flush()
    # disabled set means foo is neither in known_skills nor an orphan (frozen)
    telem.reconcile(known_skills=[], disabled_skills={"foo"})
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 7


def test_reconcile_does_not_touch_counters_for_existing_entry(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    telem.bump("foo", "view")
    telem.bump("foo", "use")
    telem.flush()
    # Second reconcile with new effective origin — counters must be untouched
    telem.reconcile([_make_entry("foo", origin="agent")])
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 1
    assert data["entries"]["foo"]["uses"] == 1
    assert data["entries"]["foo"]["origin"] == "agent"


def test_reconcile_corrects_unknown_origin_lazy_entry(tmp_path: Path) -> None:
    telem = SkillTelemetry(tmp_path / "ws")
    telem.bump("foo", "view")  # lazy init with origin="unknown"
    telem.reconcile([_make_entry("foo", origin="agent")])
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["origin"] == "agent"
    assert data["entries"]["foo"]["views"] == 1  # counter preserved
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k reconcile`
Expected: FAIL (no `reconcile` method).

- [ ] **Step 3: Write minimal implementation**

Add to `SkillTelemetry`:

```python
def reconcile(
    self,
    known_skills: list[SkillEntry],
    disabled_skills: set[str] | None = None,
) -> None:
    disabled = disabled_skills or set()
    known_names = {e["name"] for e in known_skills}
    with self._lock:
        # 1. Orphan removal: name not in known AND not disabled
        for name in list(self._entries.keys()):
            if name not in known_names and name not in disabled:
                self._entries.pop(name)
                self._last_synced_counts.pop(name, None)
        # 2. Arrival + origin/shadowed update for known
        for entry in known_skills:
            name = entry["name"]
            existing = self._entries.get(name)
            if existing is None:
                # New entry: zero counters with real origin
                self._entries[name] = {
                    "origin": entry["effective_origin"],
                    "shadowed": list(entry["shadowed_origins"]),
                    "views": 0, "uses": 0, "patches": 0,
                    "entry_created_at": _now_iso(),
                    "last_view": None, "last_use": None,
                }
            else:
                # Existing — only patch origin/shadowed (never counters/timestamps)
                existing["origin"] = entry["effective_origin"]
                existing["shadowed"] = list(entry["shadowed_origins"])
        # 3. In-memory pass: fix any "unknown" lazy-init entries that we now know
        for entry in known_skills:
            cur = self._entries.get(entry["name"])
            if cur is not None and cur["origin"] == "unknown":
                cur["origin"] = entry["effective_origin"]
        self._dirty = True
    # 4. Same-window flush so reconcile changes durable atomically
    self.flush(writer="reconcile")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (5 new tests + ~20 prior = 25)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): reconcile arrival/orphan/origin update + disabled freeze (M1 Task A7)"
```

---

### Task A8: `__init__` does NOT hydrate from disk (counter-doubling prevention)

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_restart_does_not_double_counters(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    # Session 1: bump 5, flush, "exit"
    s1 = SkillTelemetry(workspace)
    s1.reconcile([_make_entry("foo")])
    for _ in range(5):
        s1.bump("foo", "view")
    s1.flush()
    del s1

    # Session 2: restart on same workspace, NO bumps, flush
    s2 = SkillTelemetry(workspace)
    # Critical: __init__ must NOT hydrate _entries from disk
    assert s2._entries == {}
    assert s2._last_synced_counts == {}
    # Even a stray flush call (e.g. atexit) must not change disk counter
    s2.flush()
    data = json.loads((workspace / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 5  # unchanged, not 10
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_skills_telemetry.py::test_restart_does_not_double_counters -v`
Expected: PASS (current implementation already satisfies invariant; this test pins it).

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_skills_telemetry.py
git commit -m "test(telemetry): pin no-hydrate invariant on restart (M1 Task A8)"
```

---

### Task A9: Multi-threaded + asyncio concurrent bump safety

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_concurrent_threaded_bumps_no_loss(tmp_path: Path) -> None:
    import threading
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])

    def worker():
        for _ in range(1000):
            telem.bump("foo", "view")

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 10_000


async def test_asyncio_concurrent_bumps_no_loss(tmp_path: Path) -> None:
    import asyncio
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    await asyncio.gather(*[
        asyncio.to_thread(telem.bump, "foo", "view")
        for _ in range(100)
    ])
    telem.flush()
    data = json.loads((tmp_path / "ws" / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["views"] == 100
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k "concurrent or asyncio"`
Expected: PASS (atomic counter increments under `self._lock`).

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_skills_telemetry.py
git commit -m "test(telemetry): concurrent threaded + asyncio bump safety (M1 Task A9)"
```

---

### Task A10: Multi-process RMW增量叠加正确性

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_skills_telemetry.py
def _mp_bump_worker(workspace_str: str, n: int) -> None:
    """Top-level (importable by spawn) worker; takes workspace as arg, not fixture."""
    from pathlib import Path
    from nanobot.agent.skills_telemetry import SkillTelemetry
    telem = SkillTelemetry(Path(workspace_str))
    telem.reconcile([{"name": "shared", "effective_origin": "user",
                      "shadowed_origins": [], "path": "/x"}])
    for _ in range(n):
        telem.bump("shared", "view")
    telem.flush()


def test_multiproc_bumps_via_rmw_no_loss(tmp_path: Path) -> None:
    import multiprocessing as mp
    ctx = mp.get_context("spawn")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    procs = [ctx.Process(target=_mp_bump_worker, args=(str(workspace), 500))
             for _ in range(2)]
    for p in procs: p.start()
    for p in procs: p.join()
    data = json.loads((workspace / "skills" / ".telemetry.json").read_text())
    assert data["entries"]["shared"]["views"] == 1000
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_skills_telemetry.py::test_multiproc_bumps_via_rmw_no_loss -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_skills_telemetry.py
git commit -m "test(telemetry): multi-process RMW increment merge (M1 Task A10)"
```

---

### Task A11: `.tmp` residue cleanup + fsync(dir) coverage

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`

- [ ] **Step 1: Write the failing test**

```python
def test_init_cleans_tmp_residue(tmp_path: Path) -> None:
    skills_dir = tmp_path / "ws" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / ".telemetry.json.tmp").write_text("partial")
    (skills_dir / ".telemetry.json.tmp42").write_text("partial")
    SkillTelemetry(tmp_path / "ws")
    leftover = list(skills_dir.glob(".telemetry.json.tmp*"))
    assert leftover == []


@pytest.mark.skipif(sys.platform == "win32",
                    reason="dir fsync is POSIX-only; spec §4.3 explicitly skips on Windows")
def test_atomic_write_fsyncs_parent_dir(tmp_path: Path, monkeypatch) -> None:
    import os as os_mod
    from nanobot.agent import skills_telemetry as st
    calls: list[int] = []
    orig = os_mod.fsync

    def tracking(fd: int) -> None:
        calls.append(fd)
        orig(fd)

    monkeypatch.setattr(st.os, "fsync", tracking)
    st._atomic_write(tmp_path / "data.json", {"k": "v"})
    # Expect exactly 2 fsyncs: one for tmp fd, one for parent dir fd
    assert len(calls) == 2
```

Add `import sys` and `import pytest` at the top of the test module if not already present.

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k "tmp_residue or fsyncs_parent"`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/agent/test_skills_telemetry.py
git commit -m "test(telemetry): .tmp cleanup + fsync(parent_dir) on POSIX (M1 Task A11)"
```

---

### Task A12: `atexit` register + corruption rebuild + schema_version forward-compat

**Files:**
- Modify: `tests/agent/test_skills_telemetry.py`
- Modify: `nanobot/agent/skills_telemetry.py` (only if any test fails)

- [ ] **Step 1: Write the failing test**

```python
def test_corrupt_file_is_backed_up_and_rebuilt(tmp_path: Path) -> None:
    skills_dir = tmp_path / "ws" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / ".telemetry.json").write_text("{ not json")
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    telem.bump("foo", "view")
    telem.flush()
    final = json.loads((skills_dir / ".telemetry.json").read_text())
    assert final["entries"]["foo"]["views"] == 1
    backups = list(skills_dir.glob(".telemetry.json.corrupted.*"))
    assert len(backups) == 1


def test_schema_version_2_unknown_fields_preserved(tmp_path: Path) -> None:
    skills_dir = tmp_path / "ws" / "skills"
    skills_dir.mkdir(parents=True)
    (skills_dir / ".telemetry.json").write_text(json.dumps({
        "schema_version": 2,
        "updated_at": "x",
        "entries": {
            "foo": {
                "origin": "user", "shadowed": [], "views": 1, "uses": 0, "patches": 0,
                "entry_created_at": "x", "last_view": None, "last_use": None,
                "cooldown_until": "2026-12-01T00:00:00Z",
            }
        },
        "future_top": "preserve_me",
    }))
    telem = SkillTelemetry(tmp_path / "ws")
    telem.reconcile([_make_entry("foo")])
    telem.bump("foo", "view")
    telem.flush()
    data = json.loads((skills_dir / ".telemetry.json").read_text())
    assert data["entries"]["foo"]["cooldown_until"] == "2026-12-01T00:00:00Z"
    assert data["future_top"] == "preserve_me"


def test_atexit_register_flush(tmp_path: Path, monkeypatch) -> None:
    from nanobot.agent import skills_telemetry as st
    registered: list = []
    monkeypatch.setattr(st.atexit, "register", lambda fn: registered.append(fn))
    telem = SkillTelemetry(tmp_path / "ws")
    telem.register_atexit()
    assert telem.flush in registered
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v -k "corrupt or schema_version_2 or atexit"`
Expected: FAIL on `register_atexit` and `import atexit`. Implement these.

- [ ] **Step 3: Write minimal implementation**

Add to `nanobot/agent/skills_telemetry.py`:

```python
import atexit


# inside SkillTelemetry:
def register_atexit(self) -> None:
    """Call once during AgentLoop construction to ensure flush on shutdown."""
    atexit.register(self.flush)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_telemetry.py -v`
Expected: PASS (3 new + ~30 prior)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills_telemetry.py tests/agent/test_skills_telemetry.py
git commit -m "feat(telemetry): atexit registration + corruption recovery + schema forward-compat (M1 Task A12)"
```

---

## Phase B: SkillsLoader 三源 + bump hooks

### Task B1: `_infer_origin_from_path()` single inference site

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_skills_loader.py
from pathlib import Path
from nanobot.agent.skills import SkillsLoader, BUILTIN_SKILLS_DIR


def test_infer_origin_user(tmp_path: Path) -> None:
    loader = SkillsLoader(tmp_path)
    p = tmp_path / "skills" / "foo" / "SKILL.md"
    assert loader._infer_origin_from_path(p) == "user"


def test_infer_origin_agent(tmp_path: Path) -> None:
    loader = SkillsLoader(tmp_path)
    p = tmp_path / "skills" / "agent" / "foo" / "SKILL.md"
    assert loader._infer_origin_from_path(p) == "agent"


def test_infer_origin_builtin(tmp_path: Path) -> None:
    loader = SkillsLoader(tmp_path)
    p = BUILTIN_SKILLS_DIR / "foo" / "SKILL.md"
    assert loader._infer_origin_from_path(p) == "builtin"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_skills_loader.py -v -k infer_origin`
Expected: FAIL with `AttributeError: '_infer_origin_from_path'`

- [ ] **Step 3: Write minimal implementation**

Add to `nanobot/agent/skills.py`:

```python
from typing import Literal


# inside SkillsLoader class:
def _infer_origin_from_path(self, path: Path) -> Literal["user", "agent", "builtin"]:
    """Single inference site for skill physical source (spec §3.1).

    Rules:
    - <workspace>/skills/agent/*  -> "agent"
    - <workspace>/skills/*        -> "user"
    - nanobot/skills/*            -> "builtin"
    """
    try:
        if self.builtin_skills and path.is_relative_to(self.builtin_skills):
            return "builtin"
    except (AttributeError, ValueError):
        pass
    workspace_agent_dir = self.workspace_skills / "agent"
    try:
        if path.is_relative_to(workspace_agent_dir):
            return "agent"
    except ValueError:
        pass
    return "user"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k infer_origin`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): _infer_origin_from_path single inference site (M1 Task B1)"
```

---

### Task B2: `_entries_from_agent_dir()` + skip `agent` as a top-level skill

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_agent_subdir_not_treated_as_top_level_skill(tmp_path: Path) -> None:
    # User has <workspace>/skills/agent/foo/SKILL.md
    skills_dir = tmp_path / "skills"
    (skills_dir / "agent" / "foo").mkdir(parents=True)
    (skills_dir / "agent" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\nbody")
    (skills_dir / "real-user-skill").mkdir()
    (skills_dir / "real-user-skill" / "SKILL.md").write_text("---\nname: rus\n---\nbody")

    loader = SkillsLoader(tmp_path)
    names = {e["name"] for e in loader.list_skills(filter_unavailable=False)}
    # "agent" itself MUST NOT appear as a skill name
    assert "agent" not in names
    # The agent-source skill MUST appear under its real name
    assert "foo" in names
    assert "real-user-skill" in names


def test_entries_from_agent_dir_returns_real_skill_entries(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills" / "agent"
    skills_dir.mkdir(parents=True)
    (skills_dir / "auto-sum" / "SKILL.md").parent.mkdir()
    (skills_dir / "auto-sum" / "SKILL.md").write_text("---\nname: auto-sum\n---\nbody")
    loader = SkillsLoader(tmp_path)
    entries = loader._entries_from_agent_dir()
    assert any(e["name"] == "auto-sum" for e in entries)
    # Source field stays "workspace" per spec §3.1
    assert all(e["source"] == "workspace" for e in entries)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k "agent_subdir or entries_from_agent_dir"`
Expected: FAIL — `_entries_from_agent_dir` missing; also old `_skill_entries_from_dir` includes `agent/` as a top-level entry.

- [ ] **Step 3: Write minimal implementation**

In `nanobot/agent/skills.py` modify `_skill_entries_from_dir`:

```python
def _skill_entries_from_dir(
    self, base: Path, source: str, *, skip_names: set[str] | None = None
) -> list[dict[str, str]]:
    if not base.exists():
        return []
    entries: list[dict[str, str]] = []
    for skill_dir in base.iterdir():
        if not skill_dir.is_dir():
            continue
        # NEW: skip <workspace>/skills/agent/ since it's a source slot, not a skill
        if base == self.workspace_skills and skill_dir.name == "agent":
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        name = skill_dir.name
        if skip_names is not None and name in skip_names:
            continue
        entries.append({"name": name, "path": str(skill_file), "source": source})
    return entries


def _entries_from_agent_dir(self) -> list[dict[str, str]]:
    """Scan <workspace>/skills/agent/ as the agent-source slot.

    Entries still report source="workspace" per spec §3.1 (legacy 2-value field
    untouched for WebUI/CLI back-compat). The 3-value "origin" is computed by
    consumers via _infer_origin_from_path.
    """
    agent_dir = self.workspace_skills / "agent"
    return self._skill_entries_from_dir(agent_dir, "workspace")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS (new tests pass; verify existing tests are still green)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): skip agent/ as top-level skill + _entries_from_agent_dir (M1 Task B2)"
```

---

### Task B3: `list_skills()` 3-source merge + collision warning once

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_list_skills_priority_user_over_agent_over_builtin(tmp_path: Path, monkeypatch) -> None:
    # All three sources have "summarize"
    builtin = tmp_path / "_fake_builtin"
    builtin.mkdir()
    (builtin / "summarize" / "SKILL.md").parent.mkdir()
    (builtin / "summarize" / "SKILL.md").write_text("---\nname: summarize\n---\nbuiltin-body")

    agent_dir = tmp_path / "skills" / "agent" / "summarize"
    agent_dir.mkdir(parents=True)
    (agent_dir / "SKILL.md").write_text("---\nname: summarize\n---\nagent-body")

    user_dir = tmp_path / "skills" / "summarize"
    user_dir.mkdir()
    (user_dir / "SKILL.md").write_text("---\nname: summarize\n---\nuser-body")

    loader = SkillsLoader(tmp_path, builtin_skills_dir=builtin)
    entries = loader.list_skills(filter_unavailable=False)
    names = [e["name"] for e in entries]
    # exactly one "summarize"; the user copy wins
    assert names.count("summarize") == 1
    winner = next(e for e in entries if e["name"] == "summarize")
    assert "user-body" in (tmp_path / "skills" / "summarize" / "SKILL.md").read_text()
    assert winner["path"] == str(user_dir / "SKILL.md")


def test_collision_warning_logged_once_per_loader(tmp_path: Path, caplog) -> None:
    import logging
    builtin = tmp_path / "_fake_builtin"
    builtin.mkdir()
    (builtin / "dup" / "SKILL.md").parent.mkdir()
    (builtin / "dup" / "SKILL.md").write_text("---\nname: dup\n---\nb")
    user = tmp_path / "skills" / "dup"
    user.mkdir(parents=True)
    (user / "SKILL.md").write_text("---\nname: dup\n---\nu")
    with caplog.at_level(logging.WARNING):
        loader = SkillsLoader(tmp_path, builtin_skills_dir=builtin)
        loader.list_skills()
        loader.list_skills()
        loader.list_skills()
    collisions = [r for r in caplog.records if "collision" in r.getMessage().lower()]
    assert len(collisions) == 1
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k "priority or collision_warning"`
Expected: FAIL — current `list_skills` ignores `agent/` and has no collision detector.

- [ ] **Step 3: Write minimal implementation**

In `nanobot/agent/skills.py`, modify `__init__` to do collision detection once:

```python
# inside SkillsLoader.__init__ (after existing assignments):
self._collision_warned = False
self._detect_collisions_once()


def _detect_collisions_once(self) -> None:
    if self._collision_warned:
        return
    from loguru import logger
    user = self._skill_entries_from_dir(self.workspace_skills, "workspace")
    agent = self._entries_from_agent_dir()
    builtin = self._skill_entries_from_dir(self.builtin_skills, "builtin") \
        if self.builtin_skills and self.builtin_skills.exists() else []
    by_name: dict[str, list[tuple[str, str]]] = {}
    for src, entries in (("user", user), ("agent", agent), ("builtin", builtin)):
        for e in entries:
            by_name.setdefault(e["name"], []).append((src, e["path"]))
    for name, locs in by_name.items():
        if len(locs) <= 1:
            continue
        winning_src, winning_path = locs[0]
        hidden = [f"{p}" for _src, p in locs[1:]]
        logger.warning(
            "Skill name collision: '{}' shadowed at {}, hidden at [{}]",
            name, winning_path, ", ".join(hidden),
        )
    self._collision_warned = True
```

Modify `list_skills` to merge agent source between user and builtin:

```python
def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
    skills = self._skill_entries_from_dir(self.workspace_skills, "workspace")
    workspace_names = {entry["name"] for entry in skills}
    # NEW: agent layer (still labelled source="workspace" per §3.1)
    agent_entries = [
        e for e in self._entries_from_agent_dir()
        if e["name"] not in workspace_names
    ]
    skills.extend(agent_entries)
    seen = {e["name"] for e in skills}
    if self.builtin_skills and self.builtin_skills.exists():
        skills.extend(
            self._skill_entries_from_dir(
                self.builtin_skills, "builtin", skip_names=seen
            )
        )
    if self.disabled_skills:
        skills = [s for s in skills if s["name"] not in self.disabled_skills]
    if filter_unavailable:
        return [s for s in skills
                if self._check_requirements(self._get_skill_meta(s["name"]))]
    return skills
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS (new tests + all prior — verify no regression)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): 3-source merge + one-shot collision warning (M1 Task B3)"
```

---

### Task B4: `list_skills_with_shadows()` returning `SkillEntry` TypedDict

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_list_skills_with_shadows_three_source(tmp_path: Path) -> None:
    builtin = tmp_path / "_b"
    builtin.mkdir()
    (builtin / "x").mkdir()
    (builtin / "x" / "SKILL.md").write_text("---\nname: x\n---\nb")
    (tmp_path / "skills" / "agent" / "x").mkdir(parents=True)
    (tmp_path / "skills" / "agent" / "x" / "SKILL.md").write_text("---\nname: x\n---\na")
    (tmp_path / "skills" / "x").mkdir(parents=True)
    (tmp_path / "skills" / "x" / "SKILL.md").write_text("---\nname: x\n---\nu")
    (tmp_path / "skills" / "y").mkdir()
    (tmp_path / "skills" / "y" / "SKILL.md").write_text("---\nname: y\n---\nu")
    loader = SkillsLoader(tmp_path, builtin_skills_dir=builtin)
    rows = loader.list_skills_with_shadows()
    by_name = {r["name"]: r for r in rows}
    assert by_name["x"]["effective_origin"] == "user"
    assert set(by_name["x"]["shadowed_origins"]) == {"agent", "builtin"}
    assert by_name["y"]["effective_origin"] == "user"
    assert by_name["y"]["shadowed_origins"] == []


def test_list_skills_with_shadows_respects_disabled(tmp_path: Path) -> None:
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    (tmp_path / "skills" / "bar").mkdir()
    (tmp_path / "skills" / "bar" / "SKILL.md").write_text("---\nname: bar\n---\n")
    loader = SkillsLoader(tmp_path, disabled_skills={"bar"})
    rows = loader.list_skills_with_shadows()
    names = {r["name"] for r in rows}
    assert names == {"foo"}


def test_list_skills_with_shadows_does_not_call_get_skill_meta(tmp_path, monkeypatch) -> None:
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    loader = SkillsLoader(tmp_path)
    calls = []
    monkeypatch.setattr(loader, "_get_skill_meta", lambda n: calls.append(n) or {})
    loader.list_skills_with_shadows()
    assert calls == []  # MUST NOT touch frontmatter
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k list_skills_with_shadows`
Expected: FAIL — method missing.

- [ ] **Step 3: Write minimal implementation**

```python
# inside SkillsLoader:
def list_skills_with_shadows(self) -> list[dict]:
    """Return one record per visible skill with effective_origin + shadowed_origins.

    Returns dicts conforming to nanobot.agent.skills_telemetry.SkillEntry.
    NEVER calls _get_skill_meta (no frontmatter parsing).
    """
    user_entries = self._skill_entries_from_dir(self.workspace_skills, "workspace")
    agent_entries = self._entries_from_agent_dir()
    builtin_entries = (
        self._skill_entries_from_dir(self.builtin_skills, "builtin")
        if self.builtin_skills and self.builtin_skills.exists() else []
    )
    by_name: dict[str, list[tuple[str, str]]] = {}  # name -> [(origin, path), ...]
    for e in user_entries:
        by_name.setdefault(e["name"], []).append(("user", e["path"]))
    for e in agent_entries:
        by_name.setdefault(e["name"], []).append(("agent", e["path"]))
    for e in builtin_entries:
        by_name.setdefault(e["name"], []).append(("builtin", e["path"]))
    out: list[dict] = []
    for name, locs in by_name.items():
        if name in self.disabled_skills:
            continue
        effective_origin, effective_path = locs[0]
        shadowed = [origin for origin, _p in locs[1:]]
        out.append({
            "name": name,
            "effective_origin": effective_origin,
            "shadowed_origins": shadowed,
            "path": effective_path,
        })
    return out
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): list_skills_with_shadows returning SkillEntry rows (M1 Task B4)"
```

---

### Task B5: keyword-only `telemetry` kwarg + `__init__` signature stable

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_telemetry_param_is_keyword_only(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    telem = SkillTelemetry(tmp_path / "ws")
    # Keyword form must work
    loader = SkillsLoader(tmp_path / "ws", telemetry=telem)
    assert loader.telemetry is telem
    # Positional form must raise TypeError
    import pytest
    with pytest.raises(TypeError):
        SkillsLoader(tmp_path / "ws", None, None, telem)  # type: ignore[misc]


def test_telemetry_default_is_none(tmp_path: Path) -> None:
    loader = SkillsLoader(tmp_path)
    assert loader.telemetry is None
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k telemetry_param`
Expected: FAIL — `__init__` signature missing keyword-only `telemetry`.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/skills.py`:

```python
def __init__(
    self,
    workspace: Path,
    builtin_skills_dir: Path | None = None,
    disabled_skills: set[str] | None = None,
    *,
    telemetry: "SkillTelemetry | None" = None,
) -> None:
    self.workspace = workspace
    self.workspace_skills = workspace / "skills"
    self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    self.disabled_skills = disabled_skills or set()
    self.telemetry = telemetry
    self._collision_warned = False
    self._detect_collisions_once()
```

Add at module top:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from nanobot.agent.skills_telemetry import SkillTelemetry
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): keyword-only telemetry param on SkillsLoader (M1 Task B5)"
```

---

### Task B6: bump-view hook inside `build_skills_summary` (gated on `self.telemetry`)

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_skills_summary_bumps_view_per_returned_skill(tmp_path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\ndescription: f\n---\nbody")
    (tmp_path / "skills" / "bar").mkdir()
    (tmp_path / "skills" / "bar" / "SKILL.md").write_text("---\nname: bar\ndescription: b\n---\nbody")
    telem = SkillTelemetry(tmp_path)
    loader = SkillsLoader(tmp_path, telemetry=telem)
    summary = loader.build_skills_summary()
    assert "foo" in summary and "bar" in summary
    snap = telem.snapshot()
    assert snap["entries"]["foo"]["views"] == 1
    assert snap["entries"]["bar"]["views"] == 1


def test_build_skills_summary_no_bump_when_telemetry_none(tmp_path) -> None:
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\ndescription: f\n---\n")
    loader = SkillsLoader(tmp_path, telemetry=None)
    loader.build_skills_summary()
    # No exception, no side effect — physically impossible to bump
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py::test_build_skills_summary_bumps_view_per_returned_skill -v`
Expected: FAIL — no bump call yet.

- [ ] **Step 3: Modify implementation**

In `build_skills_summary`, after each entry is appended to `lines`, bump if telemetry present:

```python
def build_skills_summary(self, exclude: set[str] | None = None) -> str:
    all_skills = self.list_skills(filter_unavailable=False)
    if not all_skills:
        return ""
    lines: list[str] = []
    for entry in all_skills:
        skill_name = entry["name"]
        if exclude and skill_name in exclude:
            continue
        meta = self._get_skill_meta(skill_name)
        available = self._check_requirements(meta)
        desc = self._get_skill_description(skill_name)
        if available:
            lines.append(f"- **{skill_name}** — {desc}  `{entry['path']}`")
        else:
            missing = self._get_missing_requirements(meta)
            suffix = f" (unavailable: {missing})" if missing else " (unavailable)"
            lines.append(f"- **{skill_name}** — {desc}{suffix}  `{entry['path']}`")
        # M1: bump view counter, gated on telemetry presence
        if self.telemetry is not None:
            self.telemetry.bump(skill_name, "view")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): bump view inside build_skills_summary (M1 Task B6)"
```

---

### Task B7: bump-use hook inside `load_skills_for_context`

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_load_skills_for_context_bumps_use_per_loaded_skill(tmp_path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\nfoo-body")
    (tmp_path / "skills" / "bar").mkdir()
    (tmp_path / "skills" / "bar" / "SKILL.md").write_text("---\nname: bar\n---\nbar-body")
    telem = SkillTelemetry(tmp_path)
    loader = SkillsLoader(tmp_path, telemetry=telem)
    out = loader.load_skills_for_context(["foo", "bar"])
    assert "foo-body" in out and "bar-body" in out
    snap = telem.snapshot()
    assert snap["entries"]["foo"]["uses"] == 1
    assert snap["entries"]["bar"]["uses"] == 1


def test_load_skills_for_context_does_not_bump_missing_skill(tmp_path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    telem = SkillTelemetry(tmp_path)
    loader = SkillsLoader(tmp_path, telemetry=telem)
    loader.load_skills_for_context(["does-not-exist"])
    snap = telem.snapshot()
    # Per spec §7 row (e): bump only after load success → no entry for missing skill
    assert "does-not-exist" not in snap["entries"]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v -k load_skills_for_context`
Expected: FAIL

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/skills.py`:

```python
def load_skills_for_context(self, skill_names: list[str]) -> str:
    parts: list[str] = []
    for name in skill_names:
        markdown = self.load_skill(name)
        if markdown is None:
            continue
        parts.append(f"### Skill: {name}\n\n{self._strip_frontmatter(markdown)}")
        if self.telemetry is not None:
            self.telemetry.bump(name, "use")
    return "\n\n---\n\n".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_skills_loader.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "feat(skills): bump use inside load_skills_for_context after load success (M1 Task B7)"
```

---

### Task B8: `list_skills()` does NOT bump + `_get_skill_meta` contract comment

**Files:**
- Modify: `nanobot/agent/skills.py`
- Modify: `tests/agent/test_skills_loader.py`

- [ ] **Step 1: Write the failing test**

```python
def test_list_skills_never_bumps(tmp_path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    telem = SkillTelemetry(tmp_path)
    loader = SkillsLoader(tmp_path, telemetry=telem)
    for _ in range(10):
        loader.list_skills()
        loader.list_skills_with_shadows()
        loader.load_skill("foo")
    snap = telem.snapshot()
    # foo never bumped — these methods MUST NOT bump per spec §7 hook table
    assert snap["entries"] == {} or all(
        e["views"] == 0 and e["uses"] == 0 for e in snap["entries"].values()
    )
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_skills_loader.py::test_list_skills_never_bumps -v`
Expected: PASS (current B6/B7 only added hooks to `build_skills_summary` and `load_skills_for_context`).

- [ ] **Step 3: Add contract comment above `_get_skill_meta`**

```python
# NOTE: M1 spec elevates this to a contract (provenance read entry); keep signature
# stable. See docs/hermes-evolution/specs/m1-foundations.md §5/§11.
def _get_skill_meta(self, name: str) -> dict:
    ...
```

- [ ] **Step 4: Commit**

```bash
git add nanobot/agent/skills.py tests/agent/test_skills_loader.py
git commit -m "test(skills): pin list_skills no-bump invariant + contract comment on _get_skill_meta (M1 Task B8)"
```

---

## Phase C: 上层 wiring (context / subagent / loop / webui)

### Task C1: `ContextBuilder` accepts and forwards `telemetry`

**Files:**
- Modify: `nanobot/agent/context.py`
- Modify: `tests/agent/test_context_builder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_context_builder.py — append
def test_context_builder_forwards_telemetry_to_loader(tmp_path) -> None:
    from nanobot.agent.context import ContextBuilder
    from nanobot.agent.skills_telemetry import SkillTelemetry
    telem = SkillTelemetry(tmp_path)
    cb = ContextBuilder(tmp_path, telemetry=telem)
    assert cb.skills.telemetry is telem


def test_context_builder_no_telemetry_by_default(tmp_path) -> None:
    from nanobot.agent.context import ContextBuilder
    cb = ContextBuilder(tmp_path)
    assert cb.skills.telemetry is None
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_context_builder.py -v -k telemetry`
Expected: FAIL — `ContextBuilder` does not accept `telemetry`.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/context.py:60`:

```python
def __init__(
    self,
    workspace: Path,
    timezone: str | None = None,
    disabled_skills: list[str] | None = None,
    *,
    telemetry: "SkillTelemetry | None" = None,
) -> None:
    self.workspace = workspace
    ...
    self.skills = SkillsLoader(
        workspace,
        disabled_skills=set(disabled_skills) if disabled_skills else None,
        telemetry=telemetry,
    )
```

Add `TYPE_CHECKING` import for `SkillTelemetry` at the top.

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_context_builder.py -v`
Expected: PASS (new tests + all prior)

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/context.py tests/agent/test_context_builder.py
git commit -m "feat(context): ContextBuilder accepts and forwards telemetry (M1 Task C1)"
```

---

### Task C2: `SubagentManager` accepts and propagates `telemetry`

**Files:**
- Modify: `nanobot/agent/subagent.py`
- Modify: `tests/agent/test_subagent_telemetry.py` *(new file)*

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_subagent_telemetry.py
from pathlib import Path

from nanobot.agent.skills_telemetry import SkillTelemetry


def test_subagent_manager_holds_telemetry(tmp_path: Path) -> None:
    from nanobot.agent.subagent import SubagentManager
    telem = SkillTelemetry(tmp_path)
    mgr = SubagentManager(
        provider=object(), workspace=tmp_path, bus=None, model="m",
        telemetry=telem,
    )
    assert mgr.telemetry is telem


def test_subagent_build_prompt_uses_shared_telemetry(tmp_path: Path) -> None:
    """Constructed SkillsLoader inside _build_subagent_prompt MUST share telemetry."""
    from nanobot.agent.subagent import SubagentManager
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text(
        "---\nname: foo\ndescription: f\n---\nbody"
    )
    telem = SkillTelemetry(tmp_path)
    mgr = SubagentManager(
        provider=object(), workspace=tmp_path, bus=None, model="m",
        telemetry=telem,
    )
    mgr._build_subagent_prompt(workspace=tmp_path)
    snap = telem.snapshot()
    # foo was bumped via build_skills_summary inside subagent prompt construction
    assert snap["entries"]["foo"]["views"] == 1
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_subagent_telemetry.py -v`
Expected: FAIL — `SubagentManager` lacks `telemetry` kwarg.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/subagent.py`:

- Add `telemetry: SkillTelemetry | None = None` kwarg to `SubagentManager.__init__`
- Store `self.telemetry = telemetry`
- In `_build_subagent_prompt` line 362, change construction to:

```python
skills_summary = SkillsLoader(
    root,
    disabled_skills=self.disabled_skills,
    telemetry=self.telemetry,
).build_skills_summary()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_subagent_telemetry.py -v && pytest tests/agent/test_subagent.py -v 2>/dev/null || true`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/subagent.py tests/agent/test_subagent_telemetry.py
git commit -m "feat(subagent): SubagentManager propagates telemetry to inner SkillsLoader (M1 Task C2)"
```

---

### Task C3: `AgentLoop` constructs `SkillTelemetry` and injects everywhere

**Files:**
- Modify: `nanobot/agent/loop.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agent/test_runner_telemetry_startup.py — new
from pathlib import Path

import pytest

from nanobot.agent.skills_telemetry import SkillTelemetry


def test_agent_loop_constructs_telemetry_and_passes_down(tmp_path: Path) -> None:
    from tests.agent.test_loop_runner_integration import _make_loop  # reuse harness
    loop = _make_loop(tmp_path)
    assert isinstance(loop.telemetry, SkillTelemetry)
    assert loop.context.skills.telemetry is loop.telemetry
    assert loop.subagents.telemetry is loop.telemetry
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_runner_telemetry_startup.py -v`
Expected: FAIL — `AgentLoop` does not own `telemetry`.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/loop.py`, around line 269 (before `ContextBuilder` construction):

```python
from nanobot.agent.skills_telemetry import SkillTelemetry

# inside AgentLoop.__init__:
self.telemetry = SkillTelemetry(workspace)
self.telemetry.register_atexit()

self.context = ContextBuilder(
    workspace, timezone=timezone, disabled_skills=disabled_skills,
    telemetry=self.telemetry,
)
self.sessions = session_manager or SessionManager(workspace)
self.tools = ToolRegistry()
self._file_state_store = FileStateStore()
self.runner = AgentRunner(provider)
self.subagents = SubagentManager(
    ...,  # existing kwargs unchanged
    telemetry=self.telemetry,
)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_runner_telemetry_startup.py -v && pytest tests/agent/test_loop_runner_integration.py -v`
Expected: PASS (no regression in existing loop tests).

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/loop.py tests/agent/test_runner_telemetry_startup.py
git commit -m "feat(loop): AgentLoop owns SkillTelemetry + atexit + injects down (M1 Task C3)"
```

---

### Task C4: `AgentLoop.run()` calls `telemetry.reconcile()` before consume loop

**Files:**
- Modify: `nanobot/agent/loop.py`
- Modify: `tests/agent/test_runner_telemetry_startup.py`

- [ ] **Step 1: Write the failing test**

```python
def test_reconcile_runs_before_first_consume(tmp_path: Path) -> None:
    import asyncio
    from tests.agent.test_loop_runner_integration import _make_loop
    loop = _make_loop(tmp_path)
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    reconcile_called = {"flag": False}
    real = loop.telemetry.reconcile

    def spy(known, disabled_skills=None):
        reconcile_called["flag"] = True
        return real(known, disabled_skills=disabled_skills)

    loop.telemetry.reconcile = spy

    async def quick_stop():
        await asyncio.sleep(0.05)
        loop._running = False

    asyncio.run(asyncio.gather(loop.run(), quick_stop()))
    assert reconcile_called["flag"] is True
    snap = loop.telemetry.snapshot()
    assert snap["entries"]["foo"]["origin"] == "user"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_runner_telemetry_startup.py::test_reconcile_runs_before_first_consume -v`
Expected: FAIL — `run()` does not call `reconcile`.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/loop.py` `async def run()` after `await self._connect_mcp()`:

```python
async def run(self) -> None:
    self._running = True
    await self._connect_mcp()
    # M1: reconcile telemetry BEFORE consuming any inbound message
    self.telemetry.reconcile(
        self.context.skills.list_skills_with_shadows(),
        disabled_skills=set(self.context.skills.disabled_skills),
    )
    logger.info("Agent loop started")
    while self._running:
        ...
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_runner_telemetry_startup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/loop.py tests/agent/test_runner_telemetry_startup.py
git commit -m "feat(loop): reconcile telemetry before consume loop (M1 Task C4)"
```

---

### Task C5: Flush telemetry at end of `_run_agent_loop`

**Files:**
- Modify: `nanobot/agent/loop.py`
- Modify: `tests/agent/test_runner_telemetry_startup.py`

- [ ] **Step 1: Write the failing test**

```python
def test_flush_called_at_turn_end(tmp_path: Path, monkeypatch) -> None:
    from tests.agent.test_loop_runner_integration import _make_loop
    loop = _make_loop(tmp_path)
    flush_calls = {"n": 0}
    orig = loop.telemetry.flush

    def spy(writer="bump"):
        flush_calls["n"] += 1
        return orig(writer)

    monkeypatch.setattr(loop.telemetry, "flush", spy)
    # Drive a single _run_agent_loop turn via existing integration harness.
    # (Specifics depend on _make_loop's stub; see harness for canonical pattern.)
    import asyncio
    asyncio.run(loop._run_agent_loop_for_test())  # helper added in test harness if needed
    assert flush_calls["n"] >= 1
```

> If the existing `_make_loop` harness doesn't expose a single-turn entry, the simpler test path is to mock `bus.consume_inbound` to yield one fake `InboundMessage`, then immediately set `loop._running = False`. Adjust the test to match.

- [ ] **Step 2: Run test**

Run: `pytest tests/agent/test_runner_telemetry_startup.py -v -k flush_called_at_turn_end`
Expected: FAIL — no flush in `_run_agent_loop`.

- [ ] **Step 3: Modify implementation**

In `nanobot/agent/loop.py`, at the bottom of `_run_agent_loop` (just before `return ...`):

```python
# M1: flush telemetry once per turn (no-op when not dirty)
try:
    self.telemetry.flush()
except Exception as exc:
    logger.warning("telemetry flush at turn end failed: {}", exc)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/agent/test_runner_telemetry_startup.py -v && pytest tests/agent/test_loop_runner_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/loop.py tests/agent/test_runner_telemetry_startup.py
git commit -m "feat(loop): flush telemetry at end of each agent turn (M1 Task C5)"
```

---

### Task C6: WebUI `skills_api.py` explicit `telemetry=None`

**Files:**
- Modify: `nanobot/webui/skills_api.py`
- Modify: `tests/webui/test_skills_api_telemetry.py` *(new file)*

- [ ] **Step 1: Write the failing test**

```python
# tests/webui/test_skills_api_telemetry.py
from pathlib import Path


def test_webui_payload_does_not_create_or_modify_telemetry_file(tmp_path: Path) -> None:
    from nanobot.webui.skills_api import webui_skills_payload, webui_skill_detail_payload
    (tmp_path / "skills" / "foo").mkdir(parents=True)
    (tmp_path / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")
    for _ in range(10):
        webui_skills_payload(tmp_path)
        webui_skill_detail_payload(tmp_path, "foo")
    # Telemetry file MUST NOT have been created by WebUI calls (it has telemetry=None)
    assert not (tmp_path / "skills" / ".telemetry.json").exists()
```

- [ ] **Step 2: Run test**

Run: `pytest tests/webui/test_skills_api_telemetry.py -v`
Expected: PASS (current behavior — `SkillsLoader` defaults to `telemetry=None`).

- [ ] **Step 3: Make the intent explicit in source**

In `nanobot/webui/skills_api.py` lines 17 and 32, change to:

```python
loader = SkillsLoader(
    workspace_path,
    disabled_skills=disabled_skills,
    telemetry=None,  # WebUI must never bump counters; spec §7 hook table
)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/webui/ -v`
Expected: PASS (no behavioral change; intent now explicit)

- [ ] **Step 5: Commit**

```bash
git add nanobot/webui/skills_api.py tests/webui/test_skills_api_telemetry.py
git commit -m "feat(webui): explicit telemetry=None on SkillsLoader; pin WebUI bypass (M1 Task C6)"
```

---


## Phase D — AuxiliaryConfig + Auxiliary Provider Factory

> Goal: introduce `agents.defaults.auxiliary` config that names an existing `modelPreset` for Curator/aux-model use; build `get_auxiliary_client(config) -> LLMProvider` that resolves the preset through the existing factory, falling back to the main preset when omitted, and raising `ConfigError` when explicitly requested but unresolved. No prompt-cache contamination: aux clients are created on demand, not wired into the main `AgentLoop`.

### Task D1: Define `AuxiliaryConfig` schema (camelCase alias)

**Files:**
- Modify: `nanobot/config/schema.py` (add new class above `AgentDefaults`)
- Test: `tests/config/test_auxiliary_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/config/test_auxiliary_config.py
import pytest


def test_auxiliary_config_accepts_camelcase_alias():
    from nanobot.config.schema import AuxiliaryConfig

    aux = AuxiliaryConfig.model_validate({"modelPreset": "curator-aux"})
    assert aux.model_preset == "curator-aux"


def test_auxiliary_config_accepts_snake_case_field_name():
    from nanobot.config.schema import AuxiliaryConfig

    aux = AuxiliaryConfig.model_validate({"model_preset": "curator-aux"})
    assert aux.model_preset == "curator-aux"


def test_auxiliary_config_defaults_to_none():
    from nanobot.config.schema import AuxiliaryConfig

    aux = AuxiliaryConfig()
    assert aux.model_preset is None


def test_auxiliary_config_serialises_back_to_camelcase():
    from nanobot.config.schema import AuxiliaryConfig

    aux = AuxiliaryConfig(model_preset="curator-aux")
    dumped = aux.model_dump(by_alias=True, exclude_none=True)
    assert dumped == {"modelPreset": "curator-aux"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_auxiliary_config.py -v`
Expected: FAIL with `ImportError` — `AuxiliaryConfig` does not exist.

- [ ] **Step 3: Add `AuxiliaryConfig` class to `nanobot/config/schema.py`**

Insert immediately above `class AgentDefaults(Base):` (currently around line 121):

```python
class AuxiliaryConfig(Base):
    """Auxiliary provider configuration used by Curator/deliberation paths.

    Spec §6. Points at an existing entry under `modelPresets`. Set to None
    (the default) to fall back to the agent's main preset. When set but the
    referenced preset is absent, root-level validation (`Config`) raises a
    ConfigError at load time — never silently fall back in that case.
    """

    model_preset: str | None = Field(default=None, alias="modelPreset")
```

(`Field` is already imported from `pydantic` at the top of the file.)

- [ ] **Step 4: Run the tests**

Run: `pytest tests/config/test_auxiliary_config.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/config/schema.py tests/config/test_auxiliary_config.py
git commit -m "feat(config): add AuxiliaryConfig schema with camelCase alias (M1 Task D1)"
```

---

### Task D2: Wire `auxiliary` field into `AgentDefaults`

**Files:**
- Modify: `nanobot/config/schema.py` (`class AgentDefaults`, currently around line 121)
- Test: `tests/config/test_agent_defaults_auxiliary.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/config/test_agent_defaults_auxiliary.py
def test_agent_defaults_has_auxiliary_default():
    from nanobot.config.schema import AgentDefaults, AuxiliaryConfig

    defaults = AgentDefaults()
    assert isinstance(defaults.auxiliary, AuxiliaryConfig)
    assert defaults.auxiliary.model_preset is None


def test_agent_defaults_accepts_auxiliary_camelcase():
    from nanobot.config.schema import AgentDefaults

    defaults = AgentDefaults.model_validate({"auxiliary": {"modelPreset": "aux-1"}})
    assert defaults.auxiliary.model_preset == "aux-1"


def test_agent_defaults_serialises_auxiliary_back_to_camelcase():
    from nanobot.config.schema import AgentDefaults

    defaults = AgentDefaults.model_validate({"auxiliary": {"modelPreset": "aux-1"}})
    dumped = defaults.model_dump(by_alias=True, exclude_none=True)
    assert dumped["auxiliary"] == {"modelPreset": "aux-1"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_agent_defaults_auxiliary.py -v`
Expected: FAIL — `AgentDefaults` has no `auxiliary` attribute.

- [ ] **Step 3: Add `auxiliary` field to `AgentDefaults`**

In `nanobot/config/schema.py`, inside `class AgentDefaults(Base):`, add (place at the end of the field list — exact position depends on current contents, but keep field ordering local to existing siblings):

```python
    auxiliary: AuxiliaryConfig = Field(default_factory=AuxiliaryConfig)
```

- [ ] **Step 4: Run the tests**

Run: `pytest tests/config/test_agent_defaults_auxiliary.py tests/config/test_auxiliary_config.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/config/schema.py tests/config/test_agent_defaults_auxiliary.py
git commit -m "feat(config): wire AuxiliaryConfig into AgentDefaults (M1 Task D2)"
```

---

### Task D3: Root `Config` validator — auxiliary preset must exist

**Files:**
- Modify: `nanobot/config/schema.py` (`class Config(BaseSettings)`, currently around line 323)
- Test: `tests/config/test_config_auxiliary_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/config/test_config_auxiliary_validation.py
import pytest
from pydantic import ValidationError


def _base_config_dict(extra: dict | None = None) -> dict:
    """Minimal valid Config dict; relies on existing defaults for the rest."""
    payload: dict = {
        "modelPresets": {
            "main": {"model": "gpt-4o-mini", "provider": "openai"},
            "aux-real": {"model": "gpt-4o-mini", "provider": "openai"},
        },
        "agents": {
            "defaults": {"modelPreset": "main"},
        },
    }
    if extra:
        for key, value in extra.items():
            payload[key] = value
    return payload


def test_config_accepts_auxiliary_pointing_at_existing_preset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    payload["agents"]["defaults"]["auxiliary"] = {"modelPreset": "aux-real"}
    cfg = Config.model_validate(payload)
    assert cfg.agents.defaults.auxiliary.model_preset == "aux-real"


def test_config_rejects_auxiliary_pointing_at_missing_preset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    payload["agents"]["defaults"]["auxiliary"] = {"modelPreset": "does-not-exist"}
    with pytest.raises(ValidationError) as excinfo:
        Config.model_validate(payload)
    msg = str(excinfo.value)
    assert "auxiliary" in msg.lower()
    assert "does-not-exist" in msg


def test_config_accepts_auxiliary_unset():
    from nanobot.config.schema import Config

    payload = _base_config_dict()
    cfg = Config.model_validate(payload)
    assert cfg.agents.defaults.auxiliary.model_preset is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/config/test_config_auxiliary_validation.py -v`
Expected: `test_config_rejects_auxiliary_pointing_at_missing_preset` FAILS — no validator yet.

- [ ] **Step 3: Add root model validator to `Config`**

In `nanobot/config/schema.py`, inside `class Config(BaseSettings):`, add (at the end of the class body):

```python
    @model_validator(mode="after")
    def _validate_auxiliary_preset(self) -> "Config":
        """Spec §6 — when agents.defaults.auxiliary.modelPreset is set, it MUST
        reference an existing entry under `modelPresets`. Silent fallback only
        happens when the field is unset (None)."""
        preset = self.agents.defaults.auxiliary.model_preset
        if preset is None:
            return self
        if preset not in self.model_presets:
            raise ValueError(
                f"agents.defaults.auxiliary.modelPreset='{preset}' "
                f"does not match any entry under modelPresets "
                f"(known: {sorted(self.model_presets)})"
            )
        return self
```

Ensure `model_validator` is imported at the top of the file — if not already present, add to the existing pydantic import: `from pydantic import ..., model_validator`.

- [ ] **Step 4: Run the tests**

Run: `pytest tests/config/test_config_auxiliary_validation.py -v`
Expected: all 3 tests PASS.

Also run the broader config suite to confirm no regression:

Run: `pytest tests/config/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/config/schema.py tests/config/test_config_auxiliary_validation.py
git commit -m "feat(config): validate agents.defaults.auxiliary.modelPreset existence (M1 Task D3)"
```

---

### Task D4: `get_auxiliary_client(config)` factory with main-preset fallback

**Files:**
- Modify: `nanobot/providers/factory.py` (append at end of file)
- Test: `tests/providers/test_get_auxiliary_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/providers/test_get_auxiliary_client.py
import pytest
from unittest.mock import patch


def _config_with(aux_preset: str | None):
    """Build a minimal Config with main + optional auxiliary preset."""
    from nanobot.config.schema import Config

    payload: dict = {
        "modelPresets": {
            "main": {"model": "gpt-4o-mini", "provider": "openai"},
            "aux-real": {"model": "gpt-4o-mini", "provider": "openai"},
        },
        "providers": {
            "openai": {"apiKey": "sk-test"},
        },
        "agents": {"defaults": {"modelPreset": "main"}},
    }
    if aux_preset is not None:
        payload["agents"]["defaults"]["auxiliary"] = {"modelPreset": aux_preset}
    return Config.model_validate(payload)


def test_get_auxiliary_client_uses_named_preset_when_set():
    from nanobot.providers.factory import get_auxiliary_client

    cfg = _config_with("aux-real")
    captured: dict[str, object] = {}

    def _fake_make_provider(config, *, preset=None, preset_name=None, model=None):
        captured["preset"] = preset
        captured["preset_name"] = preset_name
        return object()  # sentinel provider

    with patch("nanobot.providers.factory.make_provider", side_effect=_fake_make_provider):
        client = get_auxiliary_client(cfg)
    assert client is not None
    assert captured["preset"] is not None
    assert captured["preset"].model == cfg.model_presets["aux-real"].model


def test_get_auxiliary_client_falls_back_to_main_when_unset():
    from nanobot.providers.factory import get_auxiliary_client

    cfg = _config_with(None)
    captured: dict[str, object] = {}

    def _fake_make_provider(config, *, preset=None, preset_name=None, model=None):
        captured["preset"] = preset
        return object()

    with patch("nanobot.providers.factory.make_provider", side_effect=_fake_make_provider):
        client = get_auxiliary_client(cfg)
    assert client is not None
    # Fallback uses the main preset (whichever defaults.modelPreset is)
    assert captured["preset"] is not None
    assert captured["preset"].model == cfg.model_presets["main"].model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/providers/test_get_auxiliary_client.py -v`
Expected: FAIL with `ImportError` — `get_auxiliary_client` does not exist.

- [ ] **Step 3: Add the factory function**

Append to `nanobot/providers/factory.py`:

```python
def get_auxiliary_client(config: "Config") -> LLMProvider:
    """Return an LLMProvider for Curator/aux-model use (spec §6).

    Resolution order:
      1. If ``agents.defaults.auxiliary.modelPreset`` is set, build a provider
         from that preset. (Existence has been validated at config load.)
      2. Otherwise fall back to the agent's main preset
         (``agents.defaults.modelPreset``).

    The aux provider is constructed independently from the main agent's
    provider chain — it must never share the main provider's prompt-cache
    state. Callers (Curator, deliberation tools) are responsible for caching
    the returned instance for the lifetime of their own session.
    """
    aux_preset_name = config.agents.defaults.auxiliary.model_preset
    if aux_preset_name is not None:
        preset = config.model_presets[aux_preset_name]
    else:
        preset = config.resolve_preset(None)
    return make_provider(config, preset=preset)
```

Also add at the top of the file (after the existing `from nanobot.config.schema import ...` import line), extend the import list to keep `Config` available at runtime — if it isn't already imported, add it:

```python
from nanobot.config.schema import Config, InlineFallbackConfig, ModelPresetConfig
```

(`Config` is already imported per the existing file; the type-quoted annotation `"Config"` keeps forward-refs safe regardless.)

- [ ] **Step 4: Run the tests**

Run: `pytest tests/providers/test_get_auxiliary_client.py -v`
Expected: both tests PASS.

Also confirm no regression in the provider suite:

Run: `pytest tests/providers/ -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nanobot/providers/factory.py tests/providers/test_get_auxiliary_client.py
git commit -m "feat(providers): add get_auxiliary_client with main-preset fallback (M1 Task D4)"
```

---

## Phase E — End-to-End Integration Tests

> Goal: lock the cross-module invariants that single-module tests cannot prove — startup sequencing, subagent telemetry-reuse, WebUI bypass coexisting with an active agent process, and the keyword-only `telemetry` parameter contract.

### Task E1: Startup sequencing — init → reconcile-before-consume

**Files:**
- Test: `tests/integration/test_agent_loop_telemetry_startup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_agent_loop_telemetry_startup.py
"""Spec §4.4 + §7: AgentLoop.run() must invoke SkillTelemetry.reconcile()
AFTER _connect_mcp() returns and BEFORE the inbound-consume loop starts."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


def test_agentloop_run_calls_reconcile_before_consume(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    from nanobot.agent.loop import AgentLoop
    from tests.integration.helpers import (
        build_minimal_agent_loop,
        CONSUME_METHOD_NAME,
    )

    workspace = tmp_path
    (workspace / "skills" / "foo").mkdir(parents=True)
    (workspace / "skills" / "foo" / "SKILL.md").write_text("---\nname: foo\n---\n")

    call_order: list[str] = []
    orig_reconcile = SkillTelemetry.reconcile

    def _spy_reconcile(self, *args, **kwargs):
        call_order.append("reconcile")
        return orig_reconcile(self, *args, **kwargs)

    async def _stub_connect_mcp(self):
        call_order.append("connect_mcp")

    async def _stub_consume(self, *args, **kwargs):
        call_order.append("consume")
        # Stop the loop so run() returns; do not actually await the bus.
        self._running = False

    with patch.object(SkillTelemetry, "reconcile", _spy_reconcile), \
         patch.object(AgentLoop, "_connect_mcp", _stub_connect_mcp), \
         patch.object(AgentLoop, CONSUME_METHOD_NAME, _stub_consume):
        loop = build_minimal_agent_loop(workspace=workspace)
        asyncio.run(loop.run())

    assert "connect_mcp" in call_order, f"_connect_mcp was not invoked: {call_order}"
    assert "reconcile" in call_order, f"reconcile was not invoked: {call_order}"
    assert "consume" in call_order, f"consume was not invoked: {call_order}"
    assert call_order.index("connect_mcp") < call_order.index("reconcile"), (
        f"reconcile must run AFTER _connect_mcp; got {call_order}"
    )
    assert call_order.index("reconcile") < call_order.index("consume"), (
        f"reconcile must run BEFORE consume loop; got {call_order}"
    )
```

Plus the helper file:

```python
# tests/integration/helpers.py
"""Minimal fixture builders for cross-module integration tests."""
from __future__ import annotations

from pathlib import Path

# The post-reconcile consume entry point on AgentLoop. Discover the actual
# name by grepping `nanobot/agent/loop.py` for the `await self._<something>`
# called after `self.telemetry.reconcile(...)` in `async def run(self)`
# (Task C4). Update this constant if the runtime method has a different name.
CONSUME_METHOD_NAME = "_consume_inbound"


def build_minimal_agent_loop(workspace: Path):
    """Build an AgentLoop wired with stub bus + provider for startup tests.

    Reuses existing test scaffolding in `tests/agent/conftest.py` to avoid
    inventing a parallel stub layer. The engineer must adapt the imported
    factory names to match what currently exists in the test suite.
    """
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    # Discover the existing stub factories by running:
    #   grep -rn "FakeProvider\|StubProvider\|make_provider\|make_stub_provider" tests/
    # Replace the import below with the actual symbol found.
    from tests.agent.conftest import make_stub_provider  # noqa: F401  (adapt as needed)

    bus = MessageBus()
    provider = make_stub_provider()
    loop = AgentLoop(
        workspace=workspace,
        bus=bus,
        provider=provider,
        disabled_skills=set(),
    )
    return loop
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_agent_loop_telemetry_startup.py -v`
Expected: FAIL — until Tasks C3 + C4 are merged, `AgentLoop` does not own a `SkillTelemetry` instance and `run()` does not call `reconcile`, so `call_order` won't contain `"reconcile"`.

- [ ] **Step 3: Adjust helper to match real codebase, then re-verify**

Open `nanobot/agent/loop.py` and locate `async def run(self):` (currently around line 851). After Task C4 is merged, the body looks like:

```python
async def run(self) -> None:
    self._running = True
    await self._connect_mcp()
    self.telemetry.reconcile(
        self.context.skills.list_skills_with_shadows(),
        disabled_skills=set(self.context.skills.disabled_skills),
    )
    # ... existing consume loop entry, e.g. await self._consume_inbound()
```

If the consume method is named something other than `_consume_inbound`, update `CONSUME_METHOD_NAME` in `tests/integration/helpers.py` to match. The constant exists precisely so this test does not break when method names evolve.

No production code edits are required by this task — it locks the invariant established in Task C4. A failure here after C4 is merged means the ordering invariant has been broken; debug by reading the current `run()` body.

- [ ] **Step 4: Run the test**

Run: `pytest tests/integration/test_agent_loop_telemetry_startup.py -v`
Expected: PASS — `call_order` is `["connect_mcp", "reconcile", "consume"]`.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/helpers.py tests/integration/test_agent_loop_telemetry_startup.py
git commit -m "test(integration): lock startup order connect_mcp->reconcile->consume (M1 Task E1)"
```

---

### Task E2: Subagent reuses parent's telemetry instance (no duplicate)

**Files:**
- Test: `tests/integration/test_subagent_telemetry_reuse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_subagent_telemetry_reuse.py
"""Spec §4.4 + §7: a subagent spawned by SubagentManager must share the parent
AgentLoop's SkillTelemetry instance — never create its own."""
from __future__ import annotations

from pathlib import Path


def test_subagent_skills_loader_shares_parent_telemetry(tmp_path: Path) -> None:
    from nanobot.agent.skills_telemetry import SkillTelemetry
    from nanobot.agent.subagent import SubagentManager
    from nanobot.agent.skills import SkillsLoader

    workspace = tmp_path
    (workspace / "skills" / "alpha").mkdir(parents=True)
    (workspace / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")

    parent_telemetry = SkillTelemetry(workspace=workspace)
    mgr = SubagentManager(
        workspace=workspace,
        disabled_skills=set(),
        telemetry=parent_telemetry,
    )

    # _build_subagent_prompt is the documented call site (subagent.py:355-371)
    # — calling it bumps view/use counters on whichever telemetry the inner
    # SkillsLoader was constructed with.
    _ = mgr._build_subagent_prompt(task="ignored", parent_session_id="s1")

    snapshot = parent_telemetry.snapshot()
    # alpha was at least viewed during subagent prompt build
    assert "alpha" in snapshot["entries"]
    assert snapshot["entries"]["alpha"]["views"] >= 1


def test_subagent_does_not_create_second_telemetry_file(tmp_path: Path) -> None:
    """Smoke: no extra .telemetry.json* artefacts beyond the parent's one."""
    from nanobot.agent.skills_telemetry import SkillTelemetry
    from nanobot.agent.subagent import SubagentManager

    workspace = tmp_path
    (workspace / "skills" / "alpha").mkdir(parents=True)
    (workspace / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")

    parent_telemetry = SkillTelemetry(workspace=workspace)
    mgr = SubagentManager(
        workspace=workspace,
        disabled_skills=set(),
        telemetry=parent_telemetry,
    )
    mgr._build_subagent_prompt(task="t", parent_session_id="s")
    parent_telemetry.flush()

    files = sorted(p.name for p in (workspace / "skills").iterdir() if p.name.startswith(".telemetry"))
    # exactly the canonical telemetry file, no parallel "subagent" copy
    assert files == [".telemetry.json"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_subagent_telemetry_reuse.py -v`
Expected: FAIL — `SubagentManager.__init__` does not yet accept `telemetry=` (until Task C2 is merged, which this integration test layer assumes is already done).

- [ ] **Step 3: Implementation already covered by Task C2**

No additional production code is required beyond Task C2. If the test still fails after C2 is merged, the failure is a real regression — debug by:

1. Confirm `SubagentManager.__init__` stores `self.telemetry = telemetry`.
2. Confirm `_build_subagent_prompt` constructs `SkillsLoader(..., telemetry=self.telemetry)`.
3. Confirm `SkillsLoader.build_skills_summary` bumps view counters when `self.telemetry is not None`.

- [ ] **Step 4: Run the test**

Run: `pytest tests/integration/test_subagent_telemetry_reuse.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_subagent_telemetry_reuse.py
git commit -m "test(integration): subagent reuses parent SkillTelemetry instance (M1 Task E2)"
```

---

### Task E3: WebUI bypass + concurrent agent process coexistence

**Files:**
- Test: `tests/integration/test_webui_and_agent_concurrent.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_webui_and_agent_concurrent.py
"""Spec §4.3 + §7: with one agent process actively bumping/flushing telemetry,
concurrent WebUI calls (telemetry=None) must:
  (a) never modify the .telemetry.json file
  (b) never crash on partially-written intermediate state
  (c) never block the agent's bump/flush cycle
"""
from __future__ import annotations

import json
import multiprocessing as mp
import time
from pathlib import Path


def _agent_worker(workspace_str: str, iterations: int) -> None:
    """Top-level so it survives `spawn` start-method serialization."""
    from pathlib import Path as P
    from nanobot.agent.skills_telemetry import SkillTelemetry

    workspace = P(workspace_str)
    telemetry = SkillTelemetry(workspace=workspace)
    for i in range(iterations):
        telemetry.bump("alpha", "view")
        if i % 25 == 0:
            telemetry.flush()
    telemetry.flush()


def _webui_worker(workspace_str: str, iterations: int, results_path: str) -> None:
    from pathlib import Path as P
    from nanobot.webui.skills_api import webui_skills_payload, webui_skill_detail_payload

    workspace = P(workspace_str)
    crashes = 0
    for _ in range(iterations):
        try:
            webui_skills_payload(workspace)
            webui_skill_detail_payload(workspace, "alpha")
        except Exception:
            crashes += 1
    P(results_path).write_text(str(crashes))


def test_webui_calls_do_not_modify_telemetry_file_under_active_agent(tmp_path: Path) -> None:
    workspace = tmp_path
    (workspace / "skills" / "alpha").mkdir(parents=True)
    (workspace / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")

    ctx = mp.get_context("spawn")
    results_path = tmp_path / "webui_crashes.txt"

    agent_proc = ctx.Process(target=_agent_worker, args=(str(workspace), 500))
    webui_proc = ctx.Process(
        target=_webui_worker, args=(str(workspace), 200, str(results_path))
    )

    agent_proc.start()
    # Give the agent a head start to ensure .telemetry.json exists
    time.sleep(0.05)
    webui_proc.start()

    agent_proc.join(timeout=30)
    webui_proc.join(timeout=30)
    assert agent_proc.exitcode == 0, f"agent crashed: exitcode={agent_proc.exitcode}"
    assert webui_proc.exitcode == 0, f"webui crashed: exitcode={webui_proc.exitcode}"

    crashes = int(results_path.read_text())
    assert crashes == 0, f"{crashes} WebUI calls crashed on partial state"

    payload = json.loads((workspace / "skills" / ".telemetry.json").read_text())
    # Only the agent should have written counters; WebUI must not alter them
    alpha = payload["entries"]["alpha"]
    assert alpha["views"] >= 500, (
        f"agent's bumps must be preserved; got {alpha['views']}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_webui_and_agent_concurrent.py -v`
Expected: PASS if Tasks A-D are merged; FAIL with import/attribute errors if upstream tasks not yet integrated.

- [ ] **Step 3: No additional production code**

This test exercises only Tasks A (telemetry) + B (loader 3-source) + C6 (WebUI explicit `telemetry=None`). Any failure indicates a regression in one of those tasks.

If the assertion `alpha["views"] >= 500` fails, debug by:
- Reading `.telemetry.json` mid-run: does the agent's flush succeed? (likely an atomic-write or filelock issue from Task A3/A5).
- Confirming `webui_skills_payload` instantiates `SkillsLoader(..., telemetry=None)` per Task C6.

- [ ] **Step 4: Run the test**

Run: `pytest tests/integration/test_webui_and_agent_concurrent.py -v`
Expected: PASS within ~30 s.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_webui_and_agent_concurrent.py
git commit -m "test(integration): WebUI bypass coexists with active agent process (M1 Task E3)"
```

---

## Completion Checklist

Mirror of spec §12. Each box maps to one or more tasks above:

- [ ] **Telemetry core** — A1–A12 merged; unit + concurrency + multi-proc tests pass
- [ ] **SkillsLoader 3-source + collision logging** — B1–B4 merged; warning emitted once per (effective, shadowed) pair
- [ ] **Hook physical placement** — B5–B8 merged; `build_skills_summary` bumps view, `load_skills_for_context` bumps use; `list_skills*` never bumps
- [ ] **Upper-layer wiring** — C1–C5 merged; AgentLoop owns SkillTelemetry, forwards to ContextBuilder + SubagentManager
- [ ] **WebUI bypass** — C6 merged; `telemetry=None` explicit
- [ ] **Auxiliary provider** — D1–D4 merged; preset validation + factory fallback both covered
- [ ] **Integration suite** — E1–E3 green; startup ordering + subagent reuse + WebUI coexistence locked
- [ ] **Spec §11 downstream contracts** — verify M2 entry points (`skill_manage` will read `SkillTelemetry.snapshot()`, will create new entries via reconcile) compile against the merged API surface

When every box is checked, the M1 milestone is complete. Update `docs/hermes-evolution/roadmap.md` row M1 to "completed" and write a 200–500 word retro into the same file under "5. 回顾与教训".
