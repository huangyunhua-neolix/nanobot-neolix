# Plan: M2 — `skill_manage` 工具（Hermes 自我进化）

## Context
**Spec:** [`docs/hermes-evolution/specs/m2-skill-manage.md`](../specs/m2-skill-manage.md) (commit `f081d6cd`)
**Roadmap row:** [`docs/hermes-evolution/roadmap.md`](../roadmap.md) §3 M2
**Upstream M1 retro:** [`docs/hermes-evolution/retros/m1-foundations.md`](../retros/m1-foundations.md)
**Branch:** `feature/m2-skill-manage` (orchestrator-owned)
**Base:** `origin/main`

## Project Context
M2 ships `skill_manage`，一个 4-verb 工具（`create / edit / patch / delete`），让主 agent / Subagent / Dream 在受控前提下改写 `<workspace>/skills/agent/<name>/SKILL.md`。M1 已锁的 telemetry 4 invariants、provenance 三源、auxiliary provider 不动；M2 是 telemetry `patch` kind 的首位调用方，并通过 §4.4 矩阵把 builtin/user/hub 三 tier 标记为绝对 read-only。安全护栏含 path-escape (`O_NOFOLLOW`) / case-fold 唯一 / 配额 / workspace create-lock / per-iteration rate-cap / lock-path symlink defense / atomic-write 0o600 + cleanup-on-error / 5-layer 全局锁序。Lock primitive 是新增的 `nanobot/agent/_atomic_io.fd_file_lock` context manager（POSIX-only，Windows raise `RuntimeError`）；M1 telemetry 的 `_atomic_write` 同时 lift 到该模块并升级 flag 集（O_NOFOLLOW + O_CLOEXEC + 0o600 + mandatory unlink-on-error），通过 module-attribute 间接调用保留 monkeypatch 钩子（M1 telemetry 测试 unmodified 通过）。Windows: `import fcntl` 走 `try/except` (precedent `nanobot/channels/msteams.py:29-32`)，`fd_file_lock` POSIX-only。CI matrix 已含 `windows-latest`，acceptance gates R8-1 / R8-1b / R8-2 / R9-1 自动覆盖。

## Conventions encoded in tasks
- Python 3.11+, asyncio throughout, line length 100, ruff E,F,I,N,W (E501 ignored).
- `pytest asyncio_mode="auto"`. Tests mirror package: `tests/agent/skills/test_<unit>.py`.
- **Naming**: 项目既有 nanobot 代码使用 `snake_case` 函数名（`_atomic_write`、`bump`、`flush`）；本 plan 全程沿用项目惯例 (snake-case functions, `_trailing_underscore` instance attrs, `snake_case` locals)。Spec §14.4 表已锁定。
- **Lock acquisition order (§8.6)**: 0 workspace create-lock → 1 skill in-proc threading.Lock → 2 skill `fd_file_lock` → 3 telemetry `_flush_lock` → 4 telemetry filelock。释放反序。任何取 >1 锁的任务在 DoD 中显式声明顺序。
- **Windows 与 POSIX 行为**：`atomic_write` 跨平台；`fd_file_lock` POSIX-only，Windows raise `RuntimeError("fd_file_lock is POSIX-only; ...")`。POSIX-only 测试用 `@pytest.mark.skipif(sys.platform == "win32", ...)`。Import-only / Windows-e2e gates 在两平台都跑。
- **PR / push**: 由 orchestrator 负责（full-cycle-dev §4.7）；plan 不创建 PR-related 任务。

## File map
| File | Status | Responsibility |
|---|---|---|
| `nanobot/agent/_atomic_io.py` | new | 公共 utility 模块；导出 `atomic_write`（lifted from `skills_telemetry._atomic_write`，flag 升级为 `O_WRONLY\|O_CREAT\|O_TRUNC\|O_NOFOLLOW\|O_CLOEXEC` + mode 0o600 + mandatory `unlink(tmp)` on error）与 `fd_file_lock(path, *, timeout=1.0)` context manager（`os.open(O_RDWR\|O_CREAT\|O_NOFOLLOW\|O_CLOEXEC, 0o600)` + `fcntl.flock(LOCK_EX\|LOCK_NB)` retry-loop + LIFO cleanup）。顶部 `try: import fcntl / except ImportError: fcntl = None`。Spec §3.7.1 / §8.5。 |
| `nanobot/agent/skills_telemetry.py` | modify | 顶部 re-export `from nanobot.agent._atomic_io import atomic_write as _atomic_write`；类内部所有写盘点改走 `from nanobot.agent import skills_telemetry as _self_module; _self_module._atomic_write(...)`（module-attribute 间接调用，保 monkeypatch hook）。新增 `BumpKind` 扩 `"delete"` enum，`bump(name, kind="delete")` set `entry.tombstone=True`；reconcile 路径在重建该 entry 时清零 counters。其他 M1 行为不动。Spec §4.3 step 5.5 / §7.1 / §7.4。 |
| `nanobot/agent/skills.py` | modify | `SkillsLoader.list_skills_with_shadows()` 已存在（M1）；M2 不改其语义，仅作为消费者引用稳定。**No code edits**——仅由 plan 任务在 SkillManageTool 中调用。 |
| `nanobot/agent/tools/context.py` | modify | `ToolContext` dataclass 追加 `provenance_tag: str = "agent"` 字段（带默认值，向后兼容所有现有 caller）。RequestContext 不变。Spec §4.2 Option A。 |
| `nanobot/agent/tools/skill_manage.py` | new | `SkillManageTool(Tool, ContextAware)`：verb dispatch + name validation (`_validate_skill_name`, `re.ASCII`) + case-fold 唯一性 + 配额 (body / count / description) + path-escape (`Path.resolve(strict=True).is_relative_to(...)` + `O_NOFOLLOW`) + tier 矩阵 (`list_skills_with_shadows()`) + 5-layer 锁取序 + verb pipeline (read → in-memory mutate → atomic_write → telemetry.bump → release LIFO) + 错误码枚举 + JSON return shape + `_increment_mutation_counter_or_reject` 同步函数。`__init__` 接 `provenance_tag: str = "agent"` keyword（Dream 路径用），并对 `subagent:<id>` 做 `^[A-Za-z0-9_-]{1,64}$ / re.ASCII` fullmatch；不通过 → `ValueError`。`Tool.create(cls, ctx)` 从 `ctx.provenance_tag` 一次读入 `self._provenance_tag_`（write-once-at-construction）。Spec §4.* / §3.* / §8.*。估算 500-700 LOC。 |
| `nanobot/agent/tools/skill_manage_ops.py` | new (conditional) | 若 `skill_manage.py` ≥700 LOC 时切出 4 个 verb 的具体读写 pipeline（spec §4.1 拆分阈值）。t-08 末尾 LOC 检查决定是否需要本文件。 |
| `nanobot/agent/tools/loader.py` / entry-point 注册 | modify | `pyproject.toml` 在 `[project.entry-points."nanobot.tools"]` 追加 `skill_manage = "nanobot.agent.tools.skill_manage:SkillManageTool"`，或确认 `loader.py` 走 `pkgutil` 自动发现。M2 不改 loader 行为，仅注册新 tool。 |
| `nanobot/config/schema.py` | modify | 新增 `SkillManageConfig(BaseModel)` 含 `max_mutations_per_turn: int = 5` (alias `maxMutationsPerTurn`)、`max_body_bytes: int = 65536` (alias `maxBodyBytes`)、`max_agent_skills: int = 200` (alias `maxAgentSkills`)、`max_description_len: int = 280` (alias `maxDescriptionLen`)；嵌入 `AgentDefaults.skill_manage`（alias `skillManage`）。Spec §3.7 / §5.2 / §14。 |
| `nanobot/agent/runner.py` | modify | `AgentRunSpec` dataclass 加 `runtime_state: RuntimeState | None = None`（W1 注入路径，§5.2.2）。`_run_core` for-loop 顶部（line ~343）加 `if spec.runtime_state is not None: spec.runtime_state._runtime_vars["skill_manage.mutations_this_turn"] = 0`。同作用域已有 `workspace_violation_counts` (line 337)。 |
| `nanobot/agent/loop.py` | modify | `AgentLoop` 已有的 `RuntimeState` 引用（line 506/621/1174 三个 `AgentRunSpec` 构造点）显式填入 `runtime_state=self._runtime_state`。 |
| `nanobot/agent/subagent.py` | modify | `_build_tools(workspace, tools_config, *, task_id: str)` 签名加 `task_id` keyword 参数；构造 `ToolContext(provenance_tag=f"subagent:{task_id}", ...)`。`_run_subagent`（line ~233）调用点把外层 `task_id` 传入。Spec §8.3。 |
| `nanobot/agent/memory.py` | modify | `MemoryStore.__init__` 加 `telemetry: SkillTelemetry | None = None` keyword 参数；`build_dream_tools()` 末尾 `tools.register(SkillManageTool(workspace=workspace, telemetry=self.telemetry, provenance_tag="dream"))`。Spec §6.1。 |
| `nanobot/agent/context.py` | modify | ContextBuilder `MemoryStore(...)` 实例化点（line 73 / 110）显式注入 `telemetry=...`（透传 AgentLoop 提供的单例）。Spec §6.5。 |
| `nanobot/cli/commands.py` | modify | line ~1103 `MemoryStore(...)` 调用点显式注入 `telemetry=...`。Spec §6.5。 |
| `nanobot/command/builtin.py` | modify | line ~338 `MemoryStore(...)` 调用点显式注入 `telemetry=...`。Spec §6.5。 |
| `nanobot/templates/agent/dream.md` | modify | "Skill discovery & creation" 段（line ~92-99）追加一行优先用 `skill_manage` 而非 `WriteFileTool`。Spec §6.2。 |
| `tests/agent/skills/__init__.py` | new | 空文件（pytest package marker）。 |
| `tests/agent/skills/conftest.py` | new | shared fixtures：`tmp_workspace`、`mock_telemetry`、`tool_factory`（构造默认 / subagent / dream 三种 provenance_tag 的 SkillManageTool）。 |
| `tests/agent/skills/test_atomic_io.py` | new | 覆盖 `atomic_write` flag set / mode 0o600 / cleanup-on-error / nonce CSPRNG（100 个 distinct hex）+ Windows-import gate (R8-1) + Windows e2e (R8-1b) + telemetry tmp cleanup post-lift (R9-1)。 |
| `tests/agent/skills/test_fd_file_lock.py` | new | POSIX-only 覆盖 `fd_file_lock` 嵌套 LIFO / 异常路径 fd-close / lock-release / errno (`ENOENT/ELOOP/EACCES`) 映射 / retry-loop 超时 → `concurrency_timeout` / Windows POSIX-only RuntimeError (R8-2)。 |
| `tests/agent/skills/test_validate_name.py` | new | name 校验单元：`re.ASCII` + Unicode confusables reject + 路径注入 + 保留名 + dot-leading + 长度边界。 |
| `tests/agent/skills/test_quota.py` | new | `maxBodyBytes` / `maxAgentSkills` (workspace create-lock parallel race) / `maxDescriptionLen` cheap reject 不持锁不 bump。 |
| `tests/agent/skills/test_create.py` | new | create verb 单元 + frontmatter `created_by` / `created_at` 写入 + case-fold collision + name_exists + tier 矩阵 reject 行为。 |
| `tests/agent/skills/test_edit_patch.py` | new | edit / patch verb：in-memory 重组 + atomic replace + bump `kind="patch"` + frontmatter `last_patched_at/patched_by` + search uniqueness + YAML round-trip 合同。 |
| `tests/agent/skills/test_delete.py` | new | delete 持双锁单点释放 + tombstone bump + reuse-create 后 reconcile counter 清零 + idempotent `not_found` + `<name>/.lock` 残留无害。 |
| `tests/agent/skills/test_path_escape.py` | new | `<workspace>/skills/agent/<name>` 预置 symlink → `PATH_ESCAPE`；`<name>/.lock` symlink；`.create.lock` symlink；resolve(strict=True) 兜底。 |
| `tests/agent/skills/test_provenance.py` | new | `provenance_tag` write-once-at-construction（构造后 mutate `ctx.provenance_tag` 不影响实例）+ `subagent:<id>` 校验 + Dream 路径 `created_by="dream"`。 |
| `tests/agent/skills/test_rate_cap.py` | new | per-iteration reset + 同 iteration 5 次额度 + asyncio 并行 increment-and-check 同步性 + subagent 独立配额。 |
| `tests/agent/skills/test_lock_order.py` | new | 双线程 skill_manage + telemetry-only bump 不死锁；workspace create-lock 在 `create` verb 取 / `edit/patch/delete` 不取。 |
| `tests/agent/skills/test_concurrency.py` | new | multiprocess.spawn 跨 filelock 并发 patch；filelock 超时 mock → `concurrency_timeout`。Worker 用 top-level fn + 显式 workspace 路径。 |
| `tests/agent/skills/test_integration.py` | new | 闭环 1 (create→edit→delete→list_skills)；闭环 2 (create→reconcile)；闭环 3 (create→reconcile→delete→reconcile orphan 清)。 |
| `tests/agent/skills/test_cache_invariant.py` | new | turn-in-progress mid-turn create；assert build_skills_summary 在该 turn 内不重新读盘；下一 turn 起点新内容生效。 |
| `tests/agent/skills/test_dream_e2e.py` | new | 触发 Dream → `skill_manage create` → frontmatter `created_by == "dream"`；MemoryStore 三 caller (context.py / cli / builtin) 全部显式注入 telemetry，缺一即测试 fail-fast。 |
| `tests/agent/test_skills_telemetry.py` | unchanged | M1 既有 monkeypatch chain 必须**无需修改**通过——M2 acceptance gate (Spec §10.6 R5)。 |
| `docs/hermes-evolution/plans/m2-skill-manage-progress.md` | created during execution | 由 fc-implementer 维护进度（不在本 plan-write 阶段创建）。 |

## Tasks

### t-01: lift `_atomic_write` to `nanobot/agent/_atomic_io.py` + add Windows import guard + flag/mode upgrade
- **Spec:** §8.5 (Option A — M2-mandated, decision #68)，§3.7.1 R8 Windows import guard (decision #73)
- **Files:** `nanobot/agent/_atomic_io.py` (new); `nanobot/agent/skills_telemetry.py` (modify — re-export + module-attribute indirection); `tests/agent/skills/__init__.py` (new); `tests/agent/skills/conftest.py` (new); `tests/agent/skills/test_atomic_io.py` (new)
- **Definition of done:**
  - `python -c "import nanobot.agent._atomic_io"` succeeds（包括 Windows runner — R8-1 gate）。
  - `from nanobot.agent.skills_telemetry import _atomic_write` 仍可 import (M1 back-compat)。
  - `pytest tests/agent/test_skills_telemetry.py -v` exit code 0，**0 个测试改动**（R5 acceptance gate）。
  - `pytest tests/agent/skills/test_atomic_io.py -v` 全绿；含 R8-1 / R8-1b (Windows e2e atomic_write) / R9-1 (telemetry tmp cleanup post-lift)。
- **Code:**
  ```python
  # nanobot/agent/_atomic_io.py
  from __future__ import annotations
  import errno
  import json
  import os
  import secrets
  import sys
  import time
  from contextlib import contextmanager
  from pathlib import Path
  from typing import Iterator

  try:  # pragma: no cover - Windows fallback
      import fcntl
  except ImportError:  # pragma: no cover
      fcntl = None  # type: ignore[assignment]

  _NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
  _CLOEXEC = getattr(os, "O_CLOEXEC", 0)


  def atomic_write(path: Path, payload: bytes | dict) -> None:
      """fsync(fd) → os.replace → fsync(parent_dir) on POSIX.
      Mode 0o600; mandatory unlink(tmp) on any failure (decision #71)."""
      data: bytes
      if isinstance(payload, (bytes, bytearray)):
          data = bytes(payload)
      else:
          data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
      tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(8)}")
      flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _NOFOLLOW | _CLOEXEC
      replaced = False
      try:
          fd = os.open(tmp, flags, 0o600)
          try:
              os.write(fd, data)
              os.fsync(fd)
          finally:
              os.close(fd)
          os.replace(tmp, path)
          replaced = True
          if sys.platform != "win32":
              dir_fd = os.open(str(path.parent), os.O_RDONLY)
              try:
                  os.fsync(dir_fd)
              finally:
                  os.close(dir_fd)
      finally:
          if not replaced:
              try:
                  os.unlink(tmp)
              except FileNotFoundError:
                  pass
  ```
  ```python
  # nanobot/agent/skills_telemetry.py (top of file)
  from nanobot.agent._atomic_io import atomic_write as _atomic_write  # re-export for M1 monkeypatch hook

  # All internal write call-sites change from `_atomic_write(path, payload)` to:
  #     from nanobot.agent import skills_telemetry as _self_module
  #     _self_module._atomic_write(path, payload)
  ```
- **Commands:**
  - `pytest tests/agent/skills/test_atomic_io.py -v` → expect: all gates pass.
  - `pytest tests/agent/test_skills_telemetry.py -v` → expect: M1 套件 0 修改 全绿。
  - `ruff check nanobot/agent/_atomic_io.py nanobot/agent/skills_telemetry.py`
- **Review focus:** `data-integrity` (durability sequence, cleanup-on-error), `security` (mode 0o600, partial-write leak)

### t-02: implement `fd_file_lock` context manager (POSIX-only)
- **Spec:** §3.7.1 step 5（decision #69 amended / #72），R7 + R8 acceptance gates，§10.6
- **Files:** `nanobot/agent/_atomic_io.py` (modify — append `fd_file_lock`); `tests/agent/skills/test_fd_file_lock.py` (new)
- **Definition of done:**
  - `fd_file_lock(path, *, timeout=1.0)` context manager 暴露在 `_atomic_io` 模块顶层。
  - POSIX 平台行为：`is_symlink` precheck → raise `SkillManageError("PATH_ESCAPE")` if symlink → `os.open(O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC, 0o600)` → `fcntl.flock(LOCK_EX|LOCK_NB)` retry-loop with `time.monotonic` deadline → `yield fd` → finally `LOCK_UN` + `os.close(fd)`。
  - Windows: `fcntl is None` 时 raise `RuntimeError("fd_file_lock is POSIX-only; Windows must take a different path")` (R8-2 gate)。
  - errno 映射：`ELOOP → PATH_ESCAPE`；`ENOENT` 不 swallow（让 caller 按 verb 上下文分流）；其余 OSError → 由 caller 译为 `ATOMIC_WRITE_FAILED` / `not_found`。
  - retry-loop 超时 → raise `SkillManageError("concurrency_timeout")`，fd 已 close。
  - Test: 嵌套 with 内层 raise → 内层 lock 释放 + fd close 再外层（LIFO）；并发子进程 acquire 同一 path 在第一进程退出后立即成功。
- **Code:** 见 spec §3.7.1 step 5 / step 6 完整代码块（采用 spec 文本逐字落地，error_code 字符串字面量保持 `PATH_ESCAPE` / `concurrency_timeout`）。
- **Commands:**
  - `pytest tests/agent/skills/test_fd_file_lock.py -v` → POSIX 全绿；Windows 仅跑 R8-2 RuntimeError gate。
  - `ruff check nanobot/agent/_atomic_io.py`
- **Review focus:** `security` (TOCTOU closure), `correctness` (LIFO release ordering), `data-integrity` (no fd-leak on exception)

### t-03: extend `ToolContext` with `provenance_tag` field
- **Spec:** §4.2 Option A (decision #46)，§4.2.1 write-once-at-construction (decision #63)
- **Files:** `nanobot/agent/tools/context.py` (modify); `tests/agent/skills/test_provenance.py` (new — only `provenance_tag` field test in this task; full SkillManageTool provenance tests defer to t-09)
- **Definition of done:**
  - `ToolContext` dataclass 追加 `provenance_tag: str = "agent"`（带默认值；不 freeze 整个 dataclass）。
  - 现有所有 `ToolContext(...)` callsite 不需改动（默认值兜底）。
  - 单元测试 assert 字段默认值 = `"agent"`，可被 `subagent:<id>` 等任意 string 设置。
- **Code:**
  ```python
  # nanobot/agent/tools/context.py — ToolContext dataclass
  @dataclass
  class ToolContext:
      config: Any
      workspace: str
      bus: Any | None = None
      subagent_manager: Any | None = None
      cron_service: Any | None = None
      sessions: Any | None = None
      file_state_store: Any = field(default=None)
      provider_snapshot_loader: Callable[[], Any] | None = None
      image_generation_provider_configs: dict[str, Any] | None = None
      timezone: str = "UTC"
      workspace_sandbox: Any | None = None
      runtime_events: Any | None = None
      provenance_tag: str = "agent"  # M2 §4.2 Option A
  ```
- **Commands:**
  - `pytest tests/agent/skills/test_provenance.py::test_tool_context_default_provenance_tag -v`
  - `ruff check nanobot/agent/tools/context.py`
- **Review focus:** `correctness`

### t-04: extend telemetry with `tombstone` schema-additive field + `kind="delete"` bump
- **Spec:** §4.3 step 5.5 / §7.1 / §7.4 (decision #66)
- **Files:** `nanobot/agent/skills_telemetry.py` (modify — `BumpKind` enum + bump dispatch + reconcile re-zero on tombstone)
- **Definition of done:**
  - `BumpKind` Literal 扩 `"delete"`。`bump(name, kind="delete")` set `entry["tombstone"] = True`，**不**修改 counters；`bump-after-replace, bump-before-release` 序保留（telemetry 内部锁层 3+4，spec §8.6）。
  - reconcile 在重建该 entry 时如看到 `tombstone == True` 且文件已重新存在（reuse-create）→ 重置 `views=0, uses=0, patches=0`、刷新 `entry_created_at`、`tombstone` 字段移除。
  - schema_version 不变（M1 invariant：tombstone 是 additive optional 字段，老 reader `.get("tombstone", False)` 透明）。
  - Counters 单调累计（`bump(kind="delete")` 不 decrement 任何 counter）。
- **Commands:**
  - `pytest tests/agent/test_skills_telemetry.py -v` → M1 套件全绿。
  - `pytest tests/agent/skills/test_delete.py::test_tombstone_reuse_zero -v`（test scaffold 在 t-08 完整落地，此处仅编译时 import 通过）。
  - `ruff check nanobot/agent/skills_telemetry.py`
- **Review focus:** `data-integrity` (M1 invariant 4 unbroken; reuse-create counter zeroing), `correctness`
- **Lock order:** telemetry layer 3 → layer 4 (释放反序)。不取 layer 0/1/2。

### t-05: add `SkillManageConfig` to config schema
- **Spec:** §3.7 / §5.2 / §14.1
- **Files:** `nanobot/config/schema.py` (modify); `tests/agent/skills/test_quota.py` (new — config 默认值断言部分)
- **Definition of done:**
  - 新增 `class SkillManageConfig(BaseModel)`：`max_mutations_per_turn: int = 5`、`max_body_bytes: int = 65536`、`max_agent_skills: int = 200`、`max_description_len: int = 280`，全部 alias 为对应 camelCase。
  - 嵌入 `AgentDefaults`：`skill_manage: SkillManageConfig = Field(default_factory=SkillManageConfig, alias="skillManage")`。
  - JSON `{"agents": {"defaults": {"skillManage": {"maxBodyBytes": 1024}}}}` 解析后 `cfg.agents.defaults.skill_manage.max_body_bytes == 1024`（双向 alias）。
- **Commands:**
  - `pytest tests/agent/skills/test_quota.py::test_skill_manage_config_defaults -v`
  - `pytest tests/agent/skills/test_quota.py::test_skill_manage_config_alias -v`
  - `ruff check nanobot/config/schema.py`
- **Review focus:** `api-contract` (alias bidirectional)

### t-06: wire `runtime_state` into `AgentRunSpec` + per-iteration reset (W1)
- **Spec:** §5.2.1 / §5.2.2 (decision #67 plan-author choice — W1 selected)
- **Files:** `nanobot/agent/runner.py` (modify — `AgentRunSpec` + `_run_core` for-loop top); `nanobot/agent/loop.py` (modify — three `AgentRunSpec` callsites at line ~506, ~621, ~1174)
- **Definition of done:**
  - `AgentRunSpec` dataclass 加 `runtime_state: RuntimeState | None = None`（默认 None 保 back-compat）。
  - `_run_core` for-loop 顶部（line ~343 `for iteration in range(spec.max_iterations):` 内）紧挨 `workspace_violation_counts` 同作用域加：
    ```python
    if spec.runtime_state is not None:
        spec.runtime_state._runtime_vars["skill_manage.mutations_this_turn"] = 0
    ```
  - `AgentLoop` 三个 `AgentRunSpec(...)` 构造点显式填 `runtime_state=self._runtime_state`（在 loop.py:506 / :621 / :1174 上下文检查实际属性名，必要时该任务可调整为 `self.runtime_state`）。
  - 测试：构造 mock spec.runtime_state；连续 3 iteration 后该 dict key 在每 iteration 顶部回到 0。
- **Code:**
  ```python
  # nanobot/agent/runner.py — AgentRunSpec dataclass
  @dataclass
  class AgentRunSpec:
      ...
      runtime_state: "RuntimeState | None" = None
  ```
- **Commands:**
  - `pytest tests/agent/skills/test_rate_cap.py::test_per_iteration_reset -v`
  - `pytest tests/agent/test_loop_runner_integration.py -v` → 不能 regress。
  - `ruff check nanobot/agent/runner.py nanobot/agent/loop.py`
- **Review focus:** `correctness` (per-iteration scope), `coherence` (W1 documented as plan-author choice)

### t-07: implement `SkillManageTool` shell — name validation, quota cheap-rejects, error_code enum, JSON shape
- **Spec:** §4.1 / §4.2 / §4.5 / §4.6 / §4.6.1 / §3.5 / §3.6 / §3.7
- **Files:** `nanobot/agent/tools/skill_manage.py` (new); `tests/agent/skills/test_validate_name.py` (new); `tests/agent/skills/test_quota.py` (modify — append cheap-reject cases); `tests/agent/skills/test_provenance.py` (modify — append write-once construction tests)
- **Definition of done:**
  - 文件含：`SkillManageVerb(StrEnum)` + `SkillManageError(Exception)` (`error_code` attribute) + tool parameters schema (verb / name / description / body / requires / search / replace) + `SkillManageTool(Tool, ContextAware)` 类骨架 (`__init__(*, workspace, telemetry, provenance_tag="agent")` + `Tool.create(cls, ctx)` 读 `ctx.provenance_tag` once → `self._provenance_tag_`) + `_validate_skill_name(name)` (`re.compile(r"^[a-z0-9][a-z0-9-]*$", re.ASCII)` + dot-leading reject + reserved names + length 1-64) + `_validate_provenance_tag(tag)` (`subagent:<id>` 匹 `^[A-Za-z0-9_-]{1,64}$ / re.ASCII`) + cheap-reject helpers (`_check_body_size` / `_check_description_len`) + error_code 枚举 string 常量 + JSON return shape helper (`_ok(...)` / `_reject(verb, name, code, msg)`)。
  - **execute() 暂返回 `_reject("not_implemented")` placeholder** —— verb pipeline 在 t-08 落地。
  - 单元测试覆盖：所有 invalid name 形态 + reserved names + dot-leading + Unicode confusables (`re.ASCII` reject) + body/description cheap reject + provenance_tag write-once-at-construction (mutate ctx 后实例值不变) + `subagent:` ValueError on bad id。
- **Commands:**
  - `pytest tests/agent/skills/test_validate_name.py tests/agent/skills/test_quota.py tests/agent/skills/test_provenance.py -v`
  - `ruff check nanobot/agent/tools/skill_manage.py`
- **Review focus:** `security` (Unicode confusables, path injection), `correctness` (write-once contract)

### t-08: implement create / edit / patch / delete verb pipelines (full lock-order, atomic write, telemetry bump)
- **Spec:** §4.3 / §4.4 / §3.7 (workspace create-lock) / §8.1 / §8.5 / §8.6
- **Files:** `nanobot/agent/tools/skill_manage.py` (modify — replace placeholder execute with full dispatch); `nanobot/agent/tools/skill_manage_ops.py` (new conditional, see §4.1 拆分阈值); `tests/agent/skills/test_create.py` (new); `tests/agent/skills/test_edit_patch.py` (new); `tests/agent/skills/test_delete.py` (new); `tests/agent/skills/test_path_escape.py` (new)
- **Definition of done:**
  - **`create` verb**：cheap-rejects → `os.makedirs(<workspace>/skills/agent/, exist_ok=True)` (R5 fix YEL-R5-1 mkdir-on-first-create) → enter `fd_file_lock(<workspace>/skills/agent/.create.lock, timeout=1.0)` (layer 0) → re-check `maxAgentSkills` → in-proc lock per name (layer 1) → `fd_file_lock(<workspace>/skills/agent/<name>/.lock, timeout=1.0)` (layer 2) → mkdir `<name>/` → atomic_write SKILL.md (frontmatter `origin="agent"`, `created_at=now()`, `created_by=self._provenance_tag_`) → release LIFO (layer 2 → 1 → 0)。**不** bump telemetry (`create` 依赖 reconcile)。case-fold 唯一性 + `list_skills_with_shadows()` reject 同名 (any tier) — `error_code="name_exists"` (same-tier) / `"name_collision"` (case-variant)。
  - **`edit/patch` verbs**：cheap-rejects → `_validate_skill_name` → `list_skills_with_shadows()` shadow 检查 (effective_origin != "agent" → `tier_locked`) → in-proc lock (layer 1) → `fd_file_lock(<name>/.lock)` (layer 2) → path-escape (`Path.resolve(strict=True).is_relative_to(skills_agent_root.resolve(strict=True))` + `O_NOFOLLOW` open) → read SKILL.md → in-memory parse YAML frontmatter + body → mutate (`edit`: replace body; `patch`: `body.replace(search, replace, 1)` with single-occurrence guard) → write `last_patched_at=now()` / `patched_by=self._provenance_tag_` → atomic_write SKILL.md → telemetry.bump(name, kind="patch") (内部走 layer 3 → 4，向下) → release LIFO (layer 2 → 1)。**不**取 layer 0。
  - **`delete` verb**：`list_skills_with_shadows()` shadow 检查 → in-proc lock (layer 1) → `fd_file_lock(<name>/.lock)` (layer 2) → re-check SKILL.md exists（idempotent `not_found`）→ `unlink SKILL.md` → `rmdir <name>/`（残留文件 WARN log + 保留目录）→ telemetry.bump(name, kind="delete") (tombstone) → unlink `<name>/.lock` (best-effort) → release LIFO (layer 2 → 1)。**不**取 layer 0。
  - **rate-cap**：`_increment_mutation_counter_or_reject(runtime_state) -> bool` 同步函数（**禁止任何 await**）作为所有 verb 的最早 reject 闸（在 cheap-rejects 之前但在 `__init__` 校验之后）；走 `runtime_state._runtime_vars["skill_manage.mutations_this_turn"]` int 计数器；超限 → `error_code="rate_limited"`，不 bump 不写盘。
  - **errno 映射** (per spec §3.7.1 step 6)：context-aware mapping of `ENOENT/ELOOP/EACCES/EBUSY/EIO/ENOSPC` → `not_found / PATH_ESCAPE / ATOMIC_WRITE_FAILED`。
  - **LOC 检查**：t-08 末尾若 `nanobot/agent/tools/skill_manage.py` ≥700 行 → 切出 `skill_manage_ops.py` (4 verb 实现) 保留 `skill_manage.py` 为 dispatch + 校验 + error 映射。
  - 测试：each verb × each provenance tier 16 cell 矩阵；create case-fold collision (macOS-like behavior simulation)；edit YAML round-trip (comment loss acceptable for agent-tier)；patch search ambiguous/missing reject (no bump no write)；delete tombstone reuse zero counters；path-escape `<name>` symlink → `PATH_ESCAPE`；`<name>/.lock` symlink → `PATH_ESCAPE`；`.create.lock` symlink → `PATH_ESCAPE`。
- **Commands:**
  - `pytest tests/agent/skills/test_create.py tests/agent/skills/test_edit_patch.py tests/agent/skills/test_delete.py tests/agent/skills/test_path_escape.py -v`
  - `ruff check nanobot/agent/tools/skill_manage.py` (+ `skill_manage_ops.py` if split)
- **Review focus:** `security` (path-escape + tier matrix + symlink defense), `data-integrity` (atomic write + tombstone + lock order), `correctness` (verb semantics)
- **Lock order acquired:** layer 0 (create only) → 1 → 2 → (telemetry's internal 3 → 4 in bump)，释放反序。

### t-09: rate-cap synchronicity + subagent budget isolation tests
- **Spec:** §5.2.1 / §10.6 R4 YEL-14 + YEL-11
- **Files:** `tests/agent/skills/test_rate_cap.py` (new — full body)
- **Definition of done:**
  - `pytest tests/agent/skills/test_rate_cap.py -v` 全绿，含：
    - 同 iteration 5 次成功 + 第 6 次任意 verb → `rate_limited` (`_runtime_vars["skill_manage.mutations_this_turn"] == 5`)。
    - 下一 iteration 顶部 reset 为 0。
    - 两个并行 `asyncio.gather` task counter=4 起 → assert 恰一成功 / 一 `rate_limited` (mutual exclusion of read+check+increment)。
    - 静态扫描 / manual gate：`ast.walk(_increment_mutation_counter_or_reject)` 不含 `Await`。
    - subagent 独立配额：父 4 次 → spawn subagent → 子 5 次成功；嵌套 grandchild 又 5 次。
- **Commands:**
  - `pytest tests/agent/skills/test_rate_cap.py -v`
- **Review focus:** `correctness` (no await in critical region), `concurrency` (asyncio fairness)

### t-10: lock-order regression + multiprocess concurrency tests
- **Spec:** §8.1 / §8.6 / §10.2 / §10.6 YEL-4 + RED-1
- **Files:** `tests/agent/skills/test_lock_order.py` (new); `tests/agent/skills/test_concurrency.py` (new)
- **Definition of done:**
  - **lock-order**：双线程 — thread A `skill_manage edit("foo")` (持 1+2 → bump telemetry → 走 3+4)；thread B 同时 telemetry-only bump 同 name (走 3+4 only)。两线程必须各自完成无死锁，最终 telemetry counter 与文件状态一致。
  - **workspace create-lock cap**：199 agent skills + 并发 2 进程 `create("a")` / `create("b")` → 一成功一 `TOO_MANY_AGENT_SKILLS`；最终目录恰 200 个 skill。
  - **delete/edit/patch 不取 layer 0**：mock create-lock acquire；assert 这三 verb 在执行路径上不调用之。
  - **multiprocess.spawn**：top-level worker fn + 显式 workspace 路径；两 worker 并发 patch 同 skill（不重叠 search/replace）→ 最终文件含两处修改 + counter += 2。
  - **filelock 超时**：mock `fd_file_lock` 始终超时（构造长持锁子进程）→ `concurrency_timeout`。
- **Commands:**
  - `pytest tests/agent/skills/test_lock_order.py tests/agent/skills/test_concurrency.py -v`
- **Review focus:** `concurrency` (deadlock freedom, layer-0 scoping), `data-integrity` (cap consistency under race)

### t-11: SubagentManager `_build_tools` task_id wiring
- **Spec:** §8.3 (decision #40 + #40a)
- **Files:** `nanobot/agent/subagent.py` (modify); `tests/agent/skills/test_provenance.py` (modify — append subagent path test)
- **Definition of done:**
  - `_build_tools(workspace=None, tools_config=None, *, task_id: str)` 签名加 `task_id` keyword-only 参数。
  - 构造 `ToolContext(provenance_tag=f"subagent:{task_id}", config=cfg, workspace=str(root.resolve()), ...)`。
  - `_run_subagent` (line ~233) 调用点把外层 `task_id` (生成于 line ~168 `task_id = str(uuid.uuid4())[:8]`) 传入。
  - 测试：spawn subagent → SkillManageTool 实例的 `self._provenance_tag_ == f"subagent:{task_id}"`；后续在 main agent ctx 上 mutate `ctx.provenance_tag = "agent"` 不影响 subagent 实例（write-once）。
- **Commands:**
  - `pytest tests/agent/skills/test_provenance.py::test_subagent_provenance_tag -v`
  - `pytest tests/agent/test_subagent.py -v` → 不能 regress（如有 _build_tools 既存测试需更新调用方）。
  - `ruff check nanobot/agent/subagent.py`
- **Review focus:** `correctness`, `api-contract`

### t-12: MemoryStore.__init__ telemetry injection + Dream tool registration
- **Spec:** §6.1 / §6.5 (R3 fix RED-2)
- **Files:** `nanobot/agent/memory.py` (modify); `nanobot/agent/context.py` (modify — line 73 / 110 callsites); `nanobot/cli/commands.py` (modify — line ~1103); `nanobot/command/builtin.py` (modify — line ~338); `tests/agent/skills/test_dream_e2e.py` (new)
- **Definition of done:**
  - `MemoryStore.__init__(..., *, telemetry: SkillTelemetry | None = None)` keyword-only 参数加入。
  - `MemoryStore.build_dream_tools()` 末尾 `tools.register(SkillManageTool(workspace=workspace, telemetry=self.telemetry, provenance_tag="dream"))`。
  - 三个 prod caller 显式传 `telemetry=...`：context.py:73 / context.py:110（ContextBuilder），cli/commands.py:1103，command/builtin.py:338。
  - **Fail-fast**：MemoryStore 内若收到 `telemetry is None` 且 build_dream_tools 被调用 → SkillManageTool 调用时落到 NPE 走不到（让上层 fail-fast in tests）。dream-e2e 测试 lock 三 caller 的注入路径都接通。
  - 测试：mock provider 触发 Dream → assert 落盘 SKILL.md frontmatter `created_by == "dream"`。
- **Commands:**
  - `pytest tests/agent/skills/test_dream_e2e.py -v`
  - `pytest tests/agent/test_dream.py tests/agent/test_dream_session.py tests/agent/test_dream_tools.py -v` → 不能 regress。
  - `ruff check nanobot/agent/memory.py nanobot/agent/context.py nanobot/cli/commands.py nanobot/command/builtin.py`
- **Review focus:** `api-contract` (init signature additivity), `correctness` (3 callsites all wired)

### t-13: ToolLoader entry-point registration
- **Spec:** §4.1 / §4.2 (Tool 注册由 entry_points 自动发现，spec 已锁实现)
- **Files:** `pyproject.toml` (modify — `[project.entry-points."nanobot.tools"]` 追加 `skill_manage = "nanobot.agent.tools.skill_manage:SkillManageTool"` if existing pattern matches; otherwise `nanobot/agent/tools/loader.py` 自动 `pkgutil` scan 已覆盖 — 任务 verifies which path applies and adds entry-point only if needed)
- **Definition of done:**
  - `ToolRegistry.tool_names` 在 main agent / subagent / dream 三 scope 下都含 `skill_manage`。
  - 单元测试构造 `ToolLoader().load(ctx, registry, scope="core")` → assert `"skill_manage" in registry.tool_names`。
- **Commands:**
  - `pytest tests/agent/skills/test_dream_e2e.py::test_skill_manage_registered -v`
  - `pytest tests/agent/test_tool_loader.py -v` (if exists) → 不能 regress。
  - `ruff check nanobot/agent/tools/`
- **Review focus:** `api-contract`

### t-14: Dream template update + integration close-loop tests
- **Spec:** §6.2 / §10.3 / §10.4
- **Files:** `nanobot/templates/agent/dream.md` (modify); `tests/agent/skills/test_integration.py` (new); `tests/agent/skills/test_cache_invariant.py` (new)
- **Definition of done:**
  - dream.md "Skill discovery & creation" 段（line ~92-99）加首行：`Prefer the \`skill_manage\` tool over manual file writes for create/edit/patch/delete; it enforces tier safety, writes provenance frontmatter, and counts toward telemetry. The legacy WriteFileTool path remains for emergency-only fallback.`
  - **闭环 1**：create("foo") → list_skills 含 "foo" → edit("foo") → 文件含 `last_patched_at` → delete("foo") → list_skills 不再含 "foo"。
  - **闭环 2 (reconcile 衔接)**：create("bar") → flush telemetry → 重启进程 → reconcile 写零计数 entry + `origin="agent"`。
  - **闭环 3 (orphan 清理)**：create("baz") → reconcile → delete("baz") + tombstone bump → 重启 → reconcile 物理删 entry。
  - **cache invariance**：构造 turn-in-progress（拿到 prompt P1）→ mid-turn create("new") → 该 turn 内 build_skills_summary 不重读盘（mock 调用次数 == turn 起点 1 次）→ 下一 turn build → P2 含 "new"，P1 ≠ P2。
- **Commands:**
  - `pytest tests/agent/skills/test_integration.py tests/agent/skills/test_cache_invariant.py -v`
  - `ruff check nanobot/templates/agent/dream.md` (no-op for markdown, but verify no Python files affected)
- **Review focus:** `correctness` (reconcile invariants 1-4 unbroken), `cache-invariance`

### t-15: Final smoke — full M2 test suite + ruff clean + acceptance gates
- **Spec:** §10.6 (all R4-R9 acceptance gates)
- **Files:** none — verification-only task; updates `docs/hermes-evolution/plans/m2-skill-manage-progress.md` (created during execution, not by plan-write).
- **Definition of done:**
  - `pytest -x tests/agent/skills/ tests/agent/test_skills_telemetry.py -v` 全绿（含 R8-1 / R8-1b on Windows runner via `windows-latest` matrix；R8-2 POSIX-skip Windows; R9-1 monkeypatch on Linux）。
  - `ruff check nanobot/agent/_atomic_io.py nanobot/agent/skills_telemetry.py nanobot/agent/tools/skill_manage.py nanobot/agent/tools/context.py nanobot/agent/runner.py nanobot/agent/loop.py nanobot/agent/subagent.py nanobot/agent/memory.py nanobot/agent/context.py nanobot/cli/commands.py nanobot/command/builtin.py nanobot/config/schema.py` → 0 issue。
  - 全仓库 smoke：`pytest -x tests/ -k "not slow"` 不能 regress (M1 套件 + 现有 agent 套件)。
  - GitHub Actions CI matrix (`ubuntu-latest`/`windows-latest` × py3.13/py3.14) 全绿（acceptance 中的 Windows-specific 测试 R8-1/R8-1b/R8-2 在 windows-latest 自动跑）。
- **Commands:**
  - `pytest -x tests/agent/skills/ tests/agent/test_skills_telemetry.py -v`
  - `pytest -x tests/agent/ -v --ignore=tests/agent/skills/`
  - `ruff check nanobot/`
- **Review focus:** `verification` (cross-cutting acceptance), `coherence`

## Parallel groups

```yaml
parallel_groups:
  - [t-01, t-03, t-05]    # foundation, fully file-disjoint (atomic_io new, ToolContext field, config schema)
  - [t-02]                 # appends fd_file_lock to _atomic_io.py — same file as t-01, must serialize
  - [t-04]                 # modifies skills_telemetry.py BumpKind/reconcile — depends on t-01 re-export landing
  - [t-06]                 # runner+loop wiring (AgentRunSpec.runtime_state + per-iteration reset)
  - [t-07]                 # SkillManageTool shell (new file; depends on t-03 ToolContext field, t-05 config)
  - [t-08]                 # full verb pipelines (modifies skill_manage.py; depends on t-02 fd_file_lock, t-04 tombstone, t-06 rate-cap reset)
  - [t-09, t-10, t-11]     # rate-cap tests / lock-order + multiprocess tests / subagent wiring — file-disjoint
  - [t-12, t-13]           # MemoryStore telemetry injection + Dream registration / entry-point — file-disjoint
  - [t-14]                 # template + integration + cache invariance
  - [t-15]                 # smoke gate (verification only, no edits)
```

**Group justification:**
- **Group 1** `[t-01, t-03, t-05]`: t-01 creates `_atomic_io.py` + adds re-export top-of-file in `skills_telemetry.py`; t-03 only touches `tools/context.py`; t-05 only touches `config/schema.py`. All file-disjoint.
- **Group 2** `[t-02]`: appends `fd_file_lock` to `_atomic_io.py` — same file as t-01, must serialize after.
- **Group 3** `[t-04]`: modifies `skills_telemetry.py` (BumpKind enum + reconcile re-zero) — must serialize after t-01's re-export indirection landed (they touch overlapping regions).
- **Group 4** `[t-06]`: `runner.py` + `loop.py`; disjoint from prior groups.
- **Group 5** `[t-07]`: new `skill_manage.py`; needs t-03 (`ToolContext.provenance_tag`) + t-05 (`SkillManageConfig`).
- **Group 6** `[t-08]`: rewrites verb pipelines in `skill_manage.py`; needs t-02 (`fd_file_lock`), t-04 (tombstone bump), t-06 (rate-cap reset point).
- **Group 7** `[t-09, t-10, t-11]`: t-09 only `test_rate_cap.py`; t-10 only `test_lock_order.py` + `test_concurrency.py`; t-11 modifies `subagent.py` + appends to `test_provenance.py` — but t-07 already created `test_provenance.py` (no append conflict here as t-11 adds new test fns). All file-disjoint.
- **Group 8** `[t-12, t-13]`: t-12 (`memory.py` + `context.py` + `cli/commands.py` + `command/builtin.py` + `test_dream_e2e.py`) and t-13 (`pyproject.toml` or `loader.py`) — file-disjoint.
- **Group 9** `[t-14]`: `templates/agent/dream.md` + new `test_integration.py` + `test_cache_invariant.py`.
- **Group 10** `[t-15]`: smoke verification only.

`build_state_after`: each task ends with green tests (TDD); no intentional broken-build window.

## Smoke command
```
pytest -x tests/agent/skills/ tests/agent/test_skills_telemetry.py && ruff check nanobot/agent/_atomic_io.py nanobot/agent/tools/skill_manage.py nanobot/agent/skills_telemetry.py nanobot/agent/tools/context.py nanobot/agent/runner.py nanobot/agent/loop.py nanobot/agent/subagent.py nanobot/agent/memory.py nanobot/config/schema.py
```
