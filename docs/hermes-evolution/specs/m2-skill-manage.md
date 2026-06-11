# M2 · skill_manage 工具 设计 Spec

> **Milestone**：M2（运行时回路第一段）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第二阶段。
>
> **状态**：设计已锁定（2026-06-11，Q1–Q13 决策全部 approved；R3 patch 已合入：14 RED + 12 YELLOW 全部 resolved；R4 patch 已合入：2 RED + 17 YELLOW 全部 resolved；R5 patch 已合入：7 residual YELLOW 全部 resolved；R6 patch 已合入：2 RED + 12 YELLOW 全部 resolved；R7 patch 已合入：6 residual YELLOW 全部 resolved，convergence target zero red/yellow）。
>
> **依赖**：M1（[`m1-foundations.md`](./m1-foundations.md)），需要 telemetry / provenance / SkillsLoader 三源结构均已落地。
>
> **下游**：M3（Curator）将基于本 milestone 的 `patches` 计数与 `last_patched_at` 字段判定 skill 健康度；M3 还要在 `skill_manage` 上加 dry-run / protect-list / cooldown 等策略层。

## 0. 调研与决策出处

- 总体研究：[`docs/hermes-self-evolution.md`](../../hermes-self-evolution.md)
- 总路线图：[`roadmap.md`](../roadmap.md)，§3 表格 M2 行
- 上游 spec：[`m1-foundations.md`](./m1-foundations.md)（特别是 §1.1 / §3.1 / §4 / §5 / §11）
- 本 spec 决策日志见 [§13](#13-决策日志)（沿用 M1 编号风格，新决策从 #37 起）

## 1. 范围与非范围

### 1.1 M2 做（in-scope）

1. **新增运行时工具 `skill_manage`** —— 单一工具表面 + `verb: Literal["create", "edit", "patch", "delete"]` 区分四类语义。所有动作只能落在 `<workspace>/skills/agent/<name>/SKILL.md` 上。
2. **Provenance × verb 矩阵硬性收紧**：bundled / user / hub 三类 skill 全部拒绝任何写入；agent 类 skill 是唯一合法写入对象（详见 [§4.4 矩阵](#44-provenance--verb-矩阵)）。
3. **Frontmatter 字段扩展**：在 `metadata.nanobot.provenance` 命名空间下新增**三个**可选字段 `created_by: string`（`agent` / `subagent:<task_id>` / `dream`，与 M1 `created_at` 配对）、`last_patched_at: ISO8601`、`patched_by: string`（同 enum）。三个字段对 M1 reader (`_get_skill_meta(name).get("provenance", {})`) 自然透传，不需要 M1 改一行代码。
4. **Telemetry 接入**：成功的 `edit` / `patch` 调用 `telemetry.bump(name, "patch")`（M1 已实现的 patch 计数器，M2 是首位调用方）；`create` / `delete` 仅依赖 M1 启动期 reconcile 的 sync 语义（详见 [§7.2](#72-create--delete-依赖-m1-reconcile)）。
5. **运行时频次保护**：每 turn 内最多允许 N 次成功的 `skill_manage` 写动作（默认 5，配置可调），超过阈值的调用直接对 LLM 返回错误，不落盘、不计数。
6. **并发护栏**：复用 M1 telemetry 的两层锁模型（per-skill `filelock` + 进程内 `threading.Lock`），保证同名并发写不丢失。
7. **Dream 整合点**：在 `MemoryStore.build_dream_tools()` 中追加 `SkillManageTool` 注册；同步更新 `nanobot/templates/agent/dream.md` 提示 Dream 优先使用 `skill_manage` 而非 `WriteFileTool` / `ApplyPatchTool`。原有 fs 工具**保留为 escape hatch**，不删除。
8. **Subagent 共用**：subagent 与主 agent 共用同一 `<workspace>/skills/agent/` 目录与同一 telemetry 实例；新建/编辑的 skill 通过 `provenance.created_by` / `patched_by` 标签区分血缘（不通过目录或命名空间区分）。
9. **测试覆盖**：单元（每 verb × provenance tier）、并发（同名并行 `patch`）、集成（create→edit→delete→reconcile 闭环）、cache 稳定性（mid-turn 写不影响当前 turn prompt segment）、Dream 端到端（Dream 调 `skill_manage` 后 frontmatter 正确）。

### 1.2 M2 不做（out-of-scope，明确留给 M3 及之后）

| 排除项 | 留给 |
|---|---|
| Curator 行为（确定性状态机 / aux-model 审议 / dry-run） | M3 |
| `skill_manage --dry-run` | M3（Curator dry-run 默认值是同一个机制） |
| `/curator` slash 命令 | M3 |
| protect-list / pin / cooldown 等策略层 | M3 |
| Telemetry 触发的自动 skill 创建（如 "看到 N 次 stale recipe → 自动建议 skill"） | M3 |
| Dream 中 `WriteFileTool(skills_dir)` 的最终下线 | M3（M2 仅添加新工具，不撤旧） |
| agent → user 的提升机制（"这个 agent skill 用得很好，要不要 promote 到 user 层"） | M3 或更晚 |
| LLM-as-judge / rubric 评估 skill 质量 | M4 |
| DSPy / GEPA / MIPROv2 离线管线对 skill 的优化 | M4 |
| Darwinian Evolver 改写 skill 内容 | M5 |

## 2. 文件系统结构（沿用 M1 §1.1）

M2 不引入新顶层目录。所有 skill 写动作只触碰：

```
<workspace>/
└── skills/
    └── agent/                       # M1 已定义，agent-authored skills 唯一合法目录
        ├── auto-summarize/
        │   ├── SKILL.md             # M2 写入；frontmatter 含 nanobot.provenance（M1+M2 字段并集）
        │   └── .lock                # M2 新增：per-skill filelock，序列化 edit/patch
        └── debug-recovery/SKILL.md
```

约束（沿用 + 新增）：

- `<workspace>/skills/agent/` 目录的存在性：M1 SkillsLoader 视空目录为 0 skill；M2 `create` 首次调用时按需 `mkdir -p` 该目录与 `<name>/` 子目录（与 M1 §11 的 "M2 实现首次 create skill 时按需 mkdir" 接口契约一致）。
- `<name>/.lock` 文件由 `filelock` 库自动管理，建议加入 `<workspace>/.gitignore`：

  ```
  skills/agent/*/.lock
  ```

  与 M1 §2 telemetry `.lock` 的 gitignore 同源（filelock 临时文件不该入库）。

- **唯一可写路径**：M2 不允许写 `<workspace>/skills/<name>/`（user 层）或 `nanobot/skills/<name>/`（builtin 层）。任何 verb 试图触碰这两条路径都按 [§4.4 矩阵](#44-provenance--verb-矩阵) reject。

## 3. 数据模型与 Frontmatter 扩展

### 3.1 已锁定字段（M1，回顾）

```yaml
---
name: auto-summarize
description: Summarize long web pages into 5-bullet TL;DR
metadata:
  nanobot:
    provenance:
      origin: agent                       # M1：M2 仍然只能写 "agent"
      created_at: 2026-06-09T14:22:00Z    # M1：首次 create 时写入
---
```

M1 §5 已规定读取入口为 `loader._get_skill_meta(name).get("provenance", {})`，M2 不改读取契约。

### 3.2 M2 新增字段（**全部可选**）

| 字段 | 类型 | 含义 | 何时写入 |
|---|---|---|---|
| `created_by` | `"agent"` \| `"subagent:<task_id>"` \| `"dream"` | 首次 create 调用方的身份；与 `created_at` 配对 | `create` verb |
| `last_patched_at` | ISO8601 UTC | 最近一次成功 `edit` / `patch` 的时间 | `edit` / `patch` verb（每次成功覆写） |
| `patched_by` | `"agent"` \| `"subagent:<task_id>"` \| `"dream"` | 最近一次成功 `edit` / `patch` 的调用方身份 | `edit` / `patch` verb（每次成功覆写） |

写入路径：`metadata.nanobot.provenance.{created_by,last_patched_at,patched_by}` —— 与 M1 字段同层级，**绝不**新建 namespace。

### 3.3 字段语义边界（防误读）

- `origin == "agent"` 是 M2 写入的硬性不变量（见 §4.4 矩阵）。M2 **不**写入 `origin: "user" | "builtin" | "hub"`，那是 M1 reconcile 推断的 effective origin，不是出生证。
- `created_by` 与 M1 的 `created_at` 配对落盘；user 把文件从 `<workspace>/skills/agent/` 手动拖到 `<workspace>/skills/` 仍保留这两字段——形成"该 user skill 起源自 agent，由 X 创建"的天然足迹（沿用 M1 §5 同款设计）。
- `subagent:<task_id>` 中的 `<task_id>` 复用 `SubagentManager` 现有 task_id 字符串（详见 §8.3）。M2 不为 subagent 单独发明 ID 体系。
- 所有 ISO8601 时间用 UTC，与 M1 telemetry `entry_created_at` 保持一致。

### 3.4 与 M1 reader 的兼容性

M1 `_get_skill_meta(name).get("provenance", {})` 返回的就是 `metadata.nanobot.provenance` dict。M2 新加的三个 key 自然以 dict 字段形式出现，未识别字段对 M3 / 未来 milestone 必须通过 `.get(key)` 读取（forward-compat），与 M1 §4.1 schema 演进规则一致。

### 3.5 task_id 输入校验（R3 fix RED-6）

`provenance.created_by` / `patched_by` 的 `subagent:<task_id>` 形式中，`<task_id>` 来自 `SubagentManager` (`nanobot/agent/subagent.py:168` `task_id = str(uuid.uuid4())[:8]` —— 当前实现是 8 hex 字符 UUID 前缀)。M2 在工具表面**单独验证** `task_id`，作为深度防御（防止未来 SubagentManager 改成接受外部 ID）：

- 正则：`^[A-Za-z0-9_-]{1,64}$`
- 编译标志：`re.ASCII`（与 §4.6 同款；防 Unicode confusables）
- 校验位置：`SkillManageTool.__init__` 接收的 `provenance_tag` 一旦以 `subagent:` 前缀，剩余部分必须 fullmatch 上述正则；不通过则 `__init__` 立即 `ValueError`，不允许构造一个会落 YAML 注入的工具实例。
- 决策 Log #47：信任边界设在工具表面（构造期），不是 YAML 序列化期。如果允许构造但靠 `yaml.safe_dump` 转义，未来加 `yaml.dump` 之类的代码改动就可能破洞。

### 3.6 名字 case-fold 唯一性（R3 fix RED-5）

跨 case 的同名碰撞在 macOS（HFS+/APFS 默认 case-insensitive）和 NTFS 默认配置下会真实落到同一磁盘文件。`create("Foo")` 紧接 `create("foo")` 在 Linux 上会建俩文件、在 macOS 上一个会覆盖另一个，**两边都是 bug**。

- `create` verb 必须在 §4.6 name 正则通过后再做：扫描 `<workspace>/skills/agent/` 下已有 skill name，**任何**已有 name 满足 `existing.casefold() == new_name.casefold()` 即 reject。
- 跨 tier 也 reject——agent 不能用 case 变体影子掉 user 层 skill（`Foo` agent vs `foo` user）。
- 校验**不**对 builtin / hub tier 做 casefold 比较（这两个 tier 命名约定明确为 kebab-case，agent 只要 §4.6 名规通过就不会和它们碰撞；省一次扫描）。
- Telemetry / log 仍记录 user 输入的原 case（不 casefold），保留可读性。
- `error_code = "name_collision"`（与既有 `name_exists` 区分：前者是 case 变体撞，后者是精确同名撞）。
- **R4 fix YEL-6（Security YEL-1）—— 信息泄露评估**：跨 tier `name_collision` 给 LLM 一个调试 hint：通过 case 变体探测 user-tier 已有 skill 名（"Foo" 报 collision → "foo" 在 user 层存在）。这条 side-channel **接受**为已知非缺陷：agent 本就拥有 user-tier skill 的读权限——`SkillsLoader.list_skills_with_shadows()`（§4.4 矩阵判定来源）原本就让 agent 在 prompt context 中看到全部 user-tier skill name。`name_collision` 没有暴露任何 agent 没有的新信息。统一为 `name_exists`（Option B）会损失同 tier vs cross-tier 的调试可读性，权衡后选择保留区分。M3 review 不得"统一" two codes for fictional security gain。
- 决策 Log #51 + Log #62。

### 3.7 硬性配额（R3 fix RED-9）

防止 LLM 一头扎进无界生成。配额优先级：cheap reject 先于持锁 + 写盘 + telemetry bump。

| 配额 | 默认值 | 配置 key | error_code |
|---|---|---|---|
| `maxBodyBytes` | 64 KiB（65536 字节，按 UTF-8 编码后字节数计） | `agents.defaults.skillManage.maxBodyBytes` | `BODY_TOO_LARGE` |
| `maxAgentSkills` | 200（`<workspace>/skills/agent/` 下含 `SKILL.md` 的子目录数） | `agents.defaults.skillManage.maxAgentSkills` | `TOO_MANY_AGENT_SKILLS` |
| `maxDescriptionLen` | 280（frontmatter `description` 字段字符数；非字节） | `agents.defaults.skillManage.maxDescriptionLen` | `DESCRIPTION_TOO_LONG` |

校验顺序（同一调用内，越早越便宜）：

1. `_validate_skill_name`（§4.6）—— `invalid_name`
2. case-fold 唯一性 / `name_exists`（§3.6 / §4.4 矩阵）
3. **`maxBodyBytes`** / **`maxDescriptionLen`** —— cheap reject，不持任何锁
4. **`maxAgentSkills`** —— 见下方"workspace create-lock"协议（不能 cheap reject，必须持 workspace 锁内 re-check）
5. 进入 §8.1 锁路径 → 写盘 → bump

`maxBodyBytes` / `maxDescriptionLen` 闸直接返回对应 `error_code`，**不**进锁，**不**写盘，**不**触 telemetry。
决策 Log #52。

#### `maxAgentSkills` workspace-level create-lock（R4 fix RED-1 — Security RED-1 + Data-integrity YEL-D）

**问题**：原 R3 设计在 step 3 cheap-check `maxAgentSkills` 后才进 §8.1 per-name lock。两个并发 `create("foo")` + `create("bar")` 在 `maxAgentSkills=200` 边界各自看到 `count==199`，都通过 quota，分别拿不同 per-name lock，**都**写成功 → final count = 201。Per-name lock 物理上无法约束全局上限。

**采纳协议（Option A）**：引入 workspace-level 创建锁。

- **新锁**：`<workspace>/skills/agent/.create.lock` —— 独立 filelock，仅 `create` verb 使用。
- **粒度**：workspace 级（**单把锁**对应整个 `<workspace>/skills/agent/`），不是 per-name。
- **取序**：在 §8.6 全局锁顺序的**最顶端**——先 acquire create-lock，再 per-skill in-proc lock，再 per-skill filelock，再 telemetry locks（§8.6 表格已扩为 5 行）。
- **协议**（仅 `create`）：
  1. 通过 §4.6 + §3.6 + `maxBodyBytes` / `maxDescriptionLen` cheap checks。
  1.5. **workspace-level mkdir-on-first-create（R5 fix YEL-R5-1）**：在 acquire create-lock **之前**，执行 `os.makedirs(<workspace>/skills/agent/, exist_ok=True)`（race-safe、idempotent）。`fd_file_lock(...)` 内部 `os.open(O_CREAT)` 要求 lock 文件的父目录已存在，否则抛 `FileNotFoundError`；新 workspace 首次 `create` 时该父目录不存在，必须先 `makedirs` 才能进 step 2。`exist_ok=True` 保证多进程并发首次 create 时各自的 `makedirs` 调用都成功（最先完成的真建目录，后续的 no-op）。本步骤覆盖 workspace-level 父目录创建；§8.8 ghost-dir 重建中提到的 mkdir-on-first-create 同时覆盖该 workspace 父目录与 per-name `<name>/` 子目录两层（详见 §8.8 R5 修订）。
  2. **acquire** create-lock 通过 §3.7.1 R7 mandated `fd_file_lock(workspace / "skills/agent/.create.lock", timeout=1.0)` context manager；该 helper 内部完成 `is_symlink` precheck + `os.open(..., O_NOFOLLOW | O_CREAT | O_CLOEXEC, 0o600)` + `fcntl.flock(fd, LOCK_EX | LOCK_NB)` retry-loop，超时 → `concurrency_timeout`。
  3. **持 create-lock** 中：扫 `<workspace>/skills/agent/` 子目录数（`os.scandir` + 仅含 `SKILL.md` 的子目录计数）；若 `>= maxAgentSkills` → release create-lock，return `error_code = "TOO_MANY_AGENT_SKILLS"`。
  4. **持 create-lock** 中：取 §8.1 per-name in-proc + filelock，做 mkdir + atomic write SKILL.md。
  5. release per-name filelock → release per-name in-proc lock → release create-lock（LIFO）。
- **`delete` / `edit` / `patch` 不取 create-lock**：delete 不可能违反上限；edit/patch 不改子目录数；per-name 锁已足够。

**为什么不用 Option B / C**：
- Option B（per-name lock 内 re-check）：cap 仍可被 LLM 通过反复 fail 调用探测（每次 fail 都耗 per-name lock 一轮 IO），不可接受。
- Option C（软上限）：违背安全初衷（防 LLM 失控生成无界 skill）。

决策 Log #60。

#### §3.7.1 Lock-path symlink defense（R5 fix YEL-R5-5 — Security A）

§4.6.1 的 symlink defense 已覆盖 `<name>/SKILL.md` 一类 per-skill 路径，但**未**显式覆盖 `<workspace>/skills/agent/.create.lock` 与 `<workspace>/skills/agent/<name>/.lock` 两类**锁文件**自身的路径。攻击者若提前在这两条固定路径上预置 symlink，`filelock.FileLock(...).acquire()` 会沿 symlink 把 advisory lock 落到 `<workspace>` 之外的目标文件，造成跨进程互斥失效或 lock 状态污染外部文件。

**协议**（适用于本 spec 引入的所有 filelock 路径）：

1. 在 acquire lock **之前**，先做 `if Path(<lock_path>).is_symlink(): raise SkillManageError(error_code="PATH_ESCAPE")`。该 fast-path 检查避免大多数情况下走到 fd 阶段。
2. 同款检查覆盖：
   - `<workspace>/skills/agent/.create.lock`（§3.7 step 2，仅 `create` verb）。
   - `<workspace>/skills/agent/<name>/.lock`（§8.1 per-skill filelock，所有 verb）。
3. **R6/R7 修订（YEL-DI-1 / YEL-SEC-1 / YEL-FEAS-1）—— fd-mode lock 关闭 TOCTOU**：`is_symlink()` precheck 与 lock acquisition 之间存在 TOCTOU window（attacker 可在 precheck 后、open 前替换为 symlink）。`filelock.UnixFileLock` 实测使用 `open(path, "a")`，**会 follow symlink**。**R7 fix YEL-FEAS-1**：经验证 `filelock 3.19.1`（pinned `>=3.25.2`）的 `BaseFileLock.__init__(lock_file: str | os.PathLike[str], ...)` **不接受预开 fd**，且 `_unix.UnixFileLock._acquire` 自身调用 `os.open(self.lock_file, ...)` —— 不存在公开钩子注入预开 fd。**因此"委托给 filelock" 分支是 dead-letter**。M2 必须**直接走 `fcntl.flock(fd, LOCK_EX)`**，**禁止**任何 monkey-patch / subclass-and-override `filelock` 私有方法的实现路径（filelock 版本 bump 时会静默断裂）。
4. **唯一可行实现路径（R7 mandated）—— 直接 `fcntl.flock(fd)`**：

   ```python
   fd = os.open(<lock_path>, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
   fcntl.flock(fd, fcntl.LOCK_EX)   # blocking; LOCK_EX | LOCK_NB if timeout needed via SIGALRM 或 retry-loop
   try:
       # critical section
       ...
   finally:
       fcntl.flock(fd, fcntl.LOCK_UN)
       os.close(fd)
   ```

   该路径是唯一 POSIX-correct 方案：(a) `O_NOFOLLOW` 在 syscall 层关闭 TOCTOU；(b) 不依赖 `filelock` 内部行为（`open(path, "a")` follows symlinks）；(c) 退出时确定性释放，不依赖 GC。

   **Windows scope**（R7 fix YEL-FEAS-2 — Option A 采纳）：lock-path symlink defense 在 M2 是 **POSIX-only**。Windows 无 `os.O_NOFOLLOW` 且无 `fcntl`，`filelock.WindowsFileLock` 使用 `msvcrt.locking` 接收 path string，存在与 POSIX-pre-R6 同款 symlink-following bug。Windows fallback 仅做 best-effort：`is_symlink` precheck + `Path(path).resolve(strict=True).is_relative_to(skills_agent_root.resolve(strict=True))` 兜底；TOCTOU window 仍存在。该 gap 列入 §12 carried-forward debt（M3 Curator 可用 Windows-specific `CreateFile(FILE_FLAG_OPEN_REPARSE_POINT)` 关闭）。Justification：nanobot 主部署目标为 POSIX，Windows multiprocess + symlink combined attack 在单用户开发者场景下非现实威胁。

5. **`fd_file_lock` context-manager 合同（R7 fix YEL-FEAS-4 + YEL-DI-1）**：`nanobot/agent/_atomic_io.py`（§8.5 lifted utility）必须提供 `fd_file_lock` context manager，把 fd lifecycle / lock release / close 顺序封装在一处：

   ```python
   @contextmanager
   def fd_file_lock(path: Path, *, timeout: float = 1.0) -> Iterator[int]:
       # 1. is_symlink precheck (step 1 above)
       if path.is_symlink():
           raise SkillManageError(error_code="PATH_ESCAPE")
       # 2. open with O_NOFOLLOW (Windows fallback per step 4)
       flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
       try:
           fd = os.open(path, flags, 0o600)
       except OSError as e:
           if e.errno == errno.ELOOP:
               raise SkillManageError(error_code="PATH_ESCAPE") from e
           if e.errno == errno.ENOENT:
               # context-aware mapping (per step 6 below): caller decides not_found vs ATOMIC_WRITE_FAILED
               raise
           raise SkillManageError(error_code="ATOMIC_WRITE_FAILED") from e
       # 3. fcntl.flock(fd, LOCK_EX | LOCK_NB) retry-loop with timeout (default 1.0s; SIGALRM 不可移植，用 LOCK_NB + sleep loop)
       deadline = time.monotonic() + timeout
       acquired = False
       try:
           while True:
               try:
                   fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                   acquired = True
                   break
               except BlockingIOError:
                   if time.monotonic() >= deadline:
                       raise SkillManageError(error_code="concurrency_timeout")
                   time.sleep(0.01)
           # 4. yield + LIFO release
           yield fd
       finally:
           if acquired:
               try:
                   fcntl.flock(fd, fcntl.LOCK_UN)
               except OSError:
                   pass  # best-effort; close 仍会释放
           os.close(fd)
   ```

   **Windows import guard（R8 fix YEL-FEAS-NEW-1 — 决策 #73）**：`nanobot/agent/_atomic_io.py` 顶部对 `fcntl` 的引入 MUST 走 try/except 模式，与项目现有 precedent `nanobot/channels/msteams.py:29-32` 完全同款：

   ```python
   try:
       import fcntl
   except ImportError:
       fcntl = None
   ```

   使用约束：

   - `atomic_write(path, data, mode=0o600)` **不依赖** `fcntl`，Windows 上仍可正常 import 与调用（写文件 + `os.replace` 是跨平台的）。
   - `fd_file_lock(path, *, timeout=1.0)` 函数体顶部 assert `fcntl is not None`，否则 `raise RuntimeError("fd_file_lock is POSIX-only; Windows must take a different path")`，与决策 #70 的 Windows POSIX-only 范围一致。
   - 这样 `from nanobot.agent._atomic_io import atomic_write as _atomic_write` 在 `skills_telemetry.py` 顶部不会让 nanobot Windows 启动崩溃；只有真正调用 `fd_file_lock` 的 M2 verb 路径才会撞 `RuntimeError`。
   - `skills_telemetry.py` 自己的 `fsync(parent_dir)` 已在 M1 用 `if sys.platform != "win32":` gate，与本 import guard 复合使用是安全的。

   §8.5 lifted utility 段落的 `_atomic_io.py` 强制要求与本段为同一合同（R6 YEL-DI-3 / R7 YEL-FEAS-1 + 本段 R8 YEL-FEAS-NEW-1 共同构成完整 helper 形状）；§8.5 仅引用，不重复定义。

   **Caller pattern (mandatory)** — `create` verb 嵌套两层 `fd_file_lock`，自动 LIFO 释放：

   ```python
   with fd_file_lock(workspace / "skills/agent/.create.lock") as create_fd:
       # critical section: name validation, mkdir <name>/, etc.
       with fd_file_lock(workspace / f"skills/agent/{name}/.lock") as name_fd:
           # inner critical section
   # exit order: name lock released → name fd closed → create lock released → create fd closed (LIFO)
   ```

   `edit/patch/delete` 仅嵌套一层 per-name `fd_file_lock`。**禁止**手写 `os.open + fcntl.flock + try/finally` 散布在 verb 实现里 —— 必须统一走 `fd_file_lock` helper，避免 fd-leak / lock-not-released 风险。

6. **errno 错误映射（R7 fix YEL-FEAS-3 — 按 verb 上下文）**：

   | errno | Verb context | Maps to |
   |---|---|---|
   | `ELOOP` | any | `PATH_ESCAPE`（symlink detected at syscall level） |
   | `ENOENT` | `edit/patch/delete`（per-name `<name>/.lock` open） | `not_found`（与 §4.3 delete idempotency 一致：skill dir 已被并发删除，is no-op） |
   | `ENOENT` | `create`（workspace-level `.create.lock` open with `O_CREAT`） | 理论不可能（§3.7 step 1.5 mkdir 保证父目录在）；若发生 → `ATOMIC_WRITE_FAILED` |
   | `EACCES` / `EBUSY` / `EIO` / `ENOSPC` | any | `ATOMIC_WRITE_FAILED` |
   | `flock` retry-loop 超时 | any | `concurrency_timeout` |

   失败路径不 bump，不持任何下游锁。

§10.6 R5 增补 test gate："planted symlink at `<workspace>/skills/agent/.create.lock` → `PATH_ESCAPE` reject before filelock acquire" 与"planted symlink at `<workspace>/skills/agent/<name>/.lock` → 同款 reject"。R6 增补 test gate："Lock-path symlink defense — 注入 `<workspace>/skills/agent/.create.lock` 为指向外部文件的 symlink，调用 create；assert `os.open` 抛 `OSError(errno.ELOOP)` 而非静默 follow（即使 is_symlink precheck 被绕过）。" R7 增补 test gate（§10.6 详见）：(a) `fd_file_lock` 异常路径 — raise inside `with fd_file_lock(...)`；assert fd 已 close 且 lock 已释放（子进程可立即重新获取）；(b) per-name lock-fd open 时并发删除 `<name>/` 触发 ENOENT → `error_code == "not_found"`（不是 `ATOMIC_WRITE_FAILED`）。

决策 Log #67-A（R5）：lock 文件路径自身的 symlink 校验，与 §4.6.1 SKILL.md 路径校验同款合同。R6 修订：lock-path defense 不再依赖 `filelock` 库内部行为（pure-Python 实现 follows symlinks）；M2 plan 必须自行 `os.open(O_NOFOLLOW)` 取 fd 后委托给 lock 实现。R7 修订（决策 #69 amended + #70 + #72）：放弃"委托给 filelock"分支（filelock 无 fd-mode 构造器），mandate 直接 `fcntl.flock(fd)`；新增 `fd_file_lock` context-manager 包装器；Windows lock-path defense 缩回 POSIX-only。详见 §13 Decision #69 amended / #70 / #72。

## 4. 工具表面（`skill_manage`）

### 4.1 物理位置与命名（决策 #38；R3 fix RED-14）

- 单文件 `nanobot/agent/tools/skill_manage.py`，与 `nanobot/agent/tools/self.py`（当前 484 LOC，是同 namespace 内最大单 tool 文件）平级。
- 不拆 `skill_create.py` / `skill_edit.py` 等多文件——`Tool` 注册表里只有一个 `skill_manage` 入口；多文件会让 description 在 registry 里重复 4 份，浪费 prompt cache。
- 估算 LOC：500–700 行（verb dispatch + 4 个 verb 实现 + name/quota 校验 + error 映射）。`self.py` 484 LOC 是项目内同类 tool 的实测上界参考。
- **拆分阈值**：若实施 plan 阶段实际超过 700 LOC，fc-architect 必须把"verb 实现细节"切出去——拆为 `nanobot/agent/tools/skill_manage.py`（tool 表面 + dispatch + 校验 + error 映射）+ `nanobot/agent/tools/skill_manage_ops.py`（4 个 verb 的具体读写实现 + 锁内 pipeline）。前者保持稳定接口，后者随实现细节演化。
- **不存在 `nanobot/agent/tools/my.py`**——上一轮 spec 误引用，本轮以 `self.py` 为准。

### 4.2 verb dispatch 表

```python
class SkillManageVerb(StrEnum):
    CREATE = "create"
    EDIT   = "edit"
    PATCH  = "patch"
    DELETE = "delete"


@tool_parameters(
    tool_parameters_schema(
        verb=StringSchema("Which mutation to perform.", enum=[v.value for v in SkillManageVerb]),
        name=StringSchema("Skill name (kebab-case, no slashes)."),
        # create / edit only
        description=StringSchema(
            "Frontmatter description; required for create, optional for edit.",
            nullable=True,
        ),
        body=StringSchema(
            "Full SKILL.md body below the frontmatter; required for create and edit.",
            nullable=True,
        ),
        requires=ObjectSchema(
            "Optional `requires` block forwarded to frontmatter (M1 supports it).",
            nullable=True,
        ),
        # patch only
        search=StringSchema(
            "Exact text to find in the existing body. Required for patch.",
            nullable=True,
        ),
        replace=StringSchema(
            "Replacement text. Required for patch.",
            nullable=True,
        ),
        required=["verb", "name"],
    )
)
class SkillManageTool(Tool, ContextAware):
    """Create, edit, patch, or delete an agent-authored skill.
    Mutates only `<workspace>/skills/agent/<name>/SKILL.md`.

    `provenance_tag: str = "agent"` controls what is written into
    `created_by` / `patched_by` frontmatter. Resolution priority (R4 §4.2):
      1. `__init__` keyword `provenance_tag` (used by Dream path which
         bypasses ToolLoader and registers directly via `tools.register(
         SkillManageTool(...))` — NOT via `Tool.create(cls, ctx)`).
      2. `ToolContext.provenance_tag` read inside `Tool.create(cls, ctx)`
         at **construction** time (used by main agent + Subagent paths
         via ToolLoader). NOT read via `set_context(rc: RequestContext)` —
         `RequestContext` remains the 5-field frozen dataclass per
         decision #40a and has no `provenance_tag` field.
      3. Default `"agent"`.

    Once stored as `self._provenance_tag_` at construction, mutations to
    the source `ToolContext` (which is mutable) MUST NOT affect this
    instance — write-once-at-construction (YEL-7 / decision #63).

    Each scope's registry-builder sets the tag explicitly:
      - main agent → `ToolContext(provenance_tag="agent")` (default;
                     read in `Tool.create(cls, ctx)` at construction)
      - subagent  → `ToolContext(provenance_tag=f"subagent:{task_id}")`
                    in SubagentManager._build_tools (subagent.py:130-149)
      - dream     → `SkillManageTool(provenance_tag="dream")` directly
                    in MemoryStore.build_dream_tools (memory.py:470, §6.1)
    No `_scopes` class attribute and no ToolLoader filtering — scope
    discipline is enforced by **which registry-builder calls register()**.

    `__init__` validates `provenance_tag`: if it starts with `"subagent:"`,
    the suffix must fullmatch `^[A-Za-z0-9_-]{1,64}$` with `re.ASCII`
    (RED-6); otherwise `ValueError` (no YAML-injectable instance ever
    constructed).
    """
```

Scope routing（R3 fix RED-3 — bridging strategy 已明确锁定）:

`ToolLoader.load(ctx, registry, scope=...)`（`nanobot/agent/tools/loader.py:86-148`）通过 `entry_points` 自动发现 builtins，没有提供 closure 钩子。`SkillManageTool` 通过下述 **Option A** 拿到 `provenance_tag`：

**Option A（采纳）—— 扩 `ToolContext`，构造期读 `provenance_tag`**

> **R4 澄清（YEL-1 + Coherence YEL-1）**：`ToolContext` 与 `RequestContext` 是两类完全不同的 ctx：
>
> - `ToolContext`（`nanobot/agent/tools/context.py:47-60`，**mutable** dataclass）—— 工具**构造期**注入；`Tool.create(cls, ctx: ToolContext)`（`nanobot/agent/tools/base.py:184`）使用。**这是 `provenance_tag` 的读取位置**。
> - `RequestContext`（`context.py:14-21`，frozen 5-field）—— 工具**调用期**注入；`set_context(ctx: RequestContext)`（参见 `self.py:127`、`spawn.py:50`、`cron.py:78`、`long_task.py:60`、`message.py:102` 现有签名）使用。决策 Log #40a 已锁定 `RequestContext` 不扩字段。
>
> M2 扩的是 `ToolContext`，不动 `RequestContext`。

- `nanobot/agent/tools/context.py` `ToolContext` dataclass（line 47-60）追加 `provenance_tag: str = "agent"` 字段（带默认值，向后兼容所有现有 caller）。
- `SkillManageTool.create(cls, ctx: ToolContext)` 在**构造期**从 `ctx.provenance_tag` 读取并存为实例字段 `self._provenance_tag_`（蛇形 + 尾下划线，遵循项目命名规约）。读取**仅一次**（write-once-at-construction，YEL-7 fix），后续调用 `set_context(rc: RequestContext)` 与 `provenance_tag` 完全无关，且 `RequestContext` 仍保 5 字段不变。
- 三个 scope 的 registry-builder 显式构造不同 `ToolContext`：
  - **主 agent**：默认 `ToolContext(provenance_tag="agent", ...)`（无须显式传，吃默认值）。
  - **Subagent**：`SubagentManager._build_tools`（`nanobot/agent/subagent.py:130-149`）构造 `ToolContext(provenance_tag=f"subagent:{task_id}", ...)`。`_build_tools` 签名追加 `task_id: str` 参数，由 `_run_subagent`（line 233 调用点）把外层 `task_id` 闭包传入。
  - **Dream**：`MemoryStore.build_dream_tools()` 不走 `ToolLoader`，直接 `tools.register(SkillManageTool(provenance_tag="dream", ...))`；这条路径**不**经过 `Tool.create(cls, ctx)` 工厂，所以 `SkillManageTool.__init__` 必须**保留** keyword-only `provenance_tag: str = "agent"` 参数作为 Dream 路径兜底。优先级：`__init__` 显式参数 > `ToolContext.provenance_tag`（经 `Tool.create` 路径） > 默认 `"agent"`。

**拒绝的备选：**

- **Option B（post-load registry.replace）**——`ToolLoader().load(...)` 之后再做 `registry.replace(name="skill_manage", new_instance=SkillManageTool(provenance_tag=...))`。被拒：`ToolRegistry` 没有 `replace` 原语（要新增 API），且 mutate-after-load 破坏 loader 的 single-source-of-truth 语义。
- **Option C（每次 tool 调用从 RuntimeState 读 tag）**——被拒：失去构造期不可变保证，每次调用必查 + 每个 verb 都要写防御代码；命名空间还要与 §5.2 rate-cap counter 共享 `_runtime_vars`，平添冲撞风险。

> M2 不引入 ToolLoader scope-filter 机制。哪个 scope 装载本工具，由该 scope 的 registry-builder 通过 `ToolContext.provenance_tag` 显式决定。决策 Log #46。

#### 4.2.1 `provenance_tag` write-once-at-construction（R4 fix YEL-7 — Security YEL-2）

`ToolContext` 是 `@dataclass`（**未** `frozen=True`），任意持有 ctx 引用的代码可 `ctx.provenance_tag = "agent"` 覆写。这会让 SubagentManager 已设的 `"subagent:<id>"` tag 被静默升级为 `"agent"`，最终 frontmatter 错误归因。

**合同**：
- `SkillManageTool.create(cls, ctx: ToolContext)` 在构造期**仅一次**读 `ctx.provenance_tag`，存为 `self._provenance_tag_`；后续所有写盘路径（`created_by` / `patched_by`）只读 `self._provenance_tag_`，**不**回头读 `ctx.provenance_tag`。
- 构造完成后 `ctx.provenance_tag` 的任何 mutation **不**影响该工具实例（write-once-at-construction）。
- `ToolContext` 整体保持 mutable（其他字段如 `cron_service` / `subagent_manager` 由不同 scope 在不同时点注入），但 `provenance_tag` 字段语义为"工具构造期消费者只读一次后丢弃源"。
- 这条契约由实施 plan 强制（不靠 freeze 整个 dataclass，避免破坏其他 tool 对 mutable ctx 的依赖）。

决策 Log #63。

### 4.3 verb 语义详表

| verb | 必填参数 | 选填 | 副作用 | 失败模式（节选） |
|---|---|---|---|---|
| `create` | `name`, `body`, `description` | `requires` | `os.makedirs(<workspace>/skills/agent/<name>/, exist_ok=True)`（R4 YEL-5：处理 delete 后 `<name>/` 目录残留 `.DS_Store` 等场景）+ 写 `SKILL.md`（含 frontmatter）；写 `created_at = now()`、`created_by`。**注意：name 复用 delete 过的 name 不继承 telemetry 旧 counter**（参见 §4.3 delete tombstone 协议 YEL-17 fix） | name 已存在于任何 tier（agent/user/builtin/hub） → reject；name 不合规 → reject |
| `edit` | `name`, `body` | `description` | 全量重写 agent-tier skill body + frontmatter；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent → reject |
| `patch` | `name`, `search`, `replace` | — | 在 agent-tier body 内做一次 search/replace（要求 `search` 在文件中**唯一**出现）；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent / `search` 找不到或多次出现 → reject |
| `delete` | `name` | — | 删除 `<workspace>/skills/agent/<name>/` 整个目录（详细协议见下） | name 不存在 / origin ≠ agent → reject |

#### `delete` 顺序协议（R3 fix RED-12 — 全程持锁，禁止 mid-flow 释放）

R2 提案在 step 5 释放 filelock 后做 step 6 unlink `.lock`，存在 race：step 5 之后、step 6 之前，并发 `create` 拿到锁建新 SKILL.md，被 step 6/7 误删。R3 修订为**全程持双锁**，单点释放：

1. 取进程内 `_skill_inproc_locks[name]: threading.Lock`（懒创建；锁顺序：先 in-proc 后 filelock，与 telemetry 同款，详见 §8.6）。
2. 取 `fd_file_lock(<workspace>/skills/agent/<name>/.lock, timeout=1.0)`（helper from `nanobot/agent/_atomic_io.py`，参见 §3.7.1 step 5；超时 → `concurrency_timeout`）。
3. **持锁中** 重新检查 `SKILL.md` 是否仍存在；若已不存在（被并发 delete 抢先），按幂等返回 `not_found`，**跳到第 7 步释放双锁**。
4. **持锁中** `unlink SKILL.md`。
5. **持锁中** `rmdir <name>/`——此时目录除 `.lock` 之外应已空（M2 不创建其他文件）；若有意外残留（`.DS_Store` / 用户手动放入），记 WARN log，**保留 `<name>/` 目录不强制 rm**（让运维介入），跳到第 7 步。
5.5. **持锁中** bump telemetry tombstone（**R4 fix YEL-17 — Data-integrity YEL-H**）：调 `telemetry.bump(name, kind="delete")`（M1 已支持的 kind 集需扩——若 M1 未实装 `"delete"` kind，M2 plan 阶段把它加为 M1 telemetry 的最小补丁；不破 telemetry schema_version，仅扩 enum 兼容追加）。bump 把该 entry 标记为 `tombstone=true`（schema-additive 字段）。**目的**：防止"delete 后 reuse 同 name → 旧 telemetry counter 被新 skill 误继承"——reconcile 在重建该 entry 时看到 tombstone 标记会**清零**所有 counter（`views=0, uses=0, patches=0`，`entry_created_at` / `created_by` 重写为新 skill 的）。
6. **持锁中** 尝试 `unlink <name>/.lock`——若 EBUSY / EACCES（罕见，仅当其他平台对持锁文件加排他保护），WARN log 继续；`.lock` 是 advisory，留下来无害（内核 fd 持有的锁状态早已随我们 `fd_file_lock` 上下文退出时的 fd close 释放）。
7. 释放 `fd_file_lock`（即 §3.7.1 step 5 持有的 fd-locked file，自 R6/R7 起 lock 实现已切到 `nanobot/agent/_atomic_io.fd_file_lock`，参见决策 #69 / #72），再释放 `threading.Lock`（与第 1-2 步反序）。R9 fix YEL-FEAS-R8-4：本步骤不再用 `FileLock` 命名以与 §3.7.1 / §8.1 / §8.6 保持一致——M2 active per-skill lock primitive 是 `fd_file_lock`，`filelock.FileLock` 仅保留在 telemetry layer 4（§8.6）。
8. 返回成功 `{"ok": True, "verb": "delete", ...}`。

**Tombstone 与 §7.2 reconcile 切分的协调**：YEL-17 引入的 tombstone bump **不**违反 §7.2 "M2 不在 delete 路径直接 mutate telemetry-entry 的 origin/exists 字段"原则——tombstone 是 additive flag（仅 set），entry 删除仍由 reconcile 完成（M1 invariant 4 仍守）。只是从"delete 不 bump"升级为"delete bump 一次 tombstone-marker"，事件流仍单调累计。决策 Log #66。

**核心修订点**：原 R2 step 5（"退出 filelock 后再 unlink `.lock`"）被合并进持锁段。`.lock` 文件 unlink 即使失败也是无害的（advisory，会被新进程覆写）；保留 `.lock` 比中途释放锁制造 race window 更稳。

**正确性论证**：从第 1 步取双锁开始，到第 7 步双锁全部释放为止，任何并发 acquirer（被第 2 步阻塞的请求）只能在第 7 步之后才拿到锁；它们 pipeline 第一步是"读 SKILL.md"，看到文件不存在 → §4.5 返回 `not_found`，安全 no-op。`.lock` 即使被并发 acquirer 在我们 step 7 之后重建也无所谓——`filelock` 用的是内核 `flock`/`fcntl` advisory lock，**锁状态由内核 fd 持有，文件只是稳定句柄**。

决策 Log #50：double-lock single-release 协议替代 R2 mid-flow release。

> **拒绝的备选**：把锁放到 workspace 顶层独立 `locks/` 目录，避开"删自己锁"问题。被拒理由：破坏 M1 "skill 是 self-contained 单目录" 的属性，给 reconcile / list_skills 引入新外部依赖路径。维持 per-skill `.lock`。

#### `edit` verb 实现协议（R3 fix RED-8 — 全量重写必须真正"全量+原子"）

`edit` 在概念上是"全量重写"，但在实现上**禁止**就地 mutate 文件。所有四个 verb（含 patch / edit）都走同一 in-memory 重组 + atomic replace pipeline：

1. **持锁后**（in-proc lock + per-skill `fd_file_lock`，§8.6 第 1+2 层已持有；per-skill 锁实现见 §3.7.1 step 5）把 `<name>/SKILL.md` 全量读入 string `current`。
2. 解析 `current` 的 YAML frontmatter（`yaml.safe_load`），dict 是 `meta`；把 frontmatter 后的部分作为 `body_str`。
3. **In-memory 变换**：
   - `edit`：`new_body = caller_body`；`new_meta` 在 `meta` 上覆盖 `description`（若传）+ 写 `last_patched_at` / `patched_by`。
   - `patch`：`new_body = body_str.replace(search, replace, 1)`（要求 `search` 在 `body_str` 出现且仅出现 1 次，否则前置 reject）；`new_meta` 同 edit 写 `last_patched_at` / `patched_by`。
4. **In-memory 重组**：`new_content = "---\n" + yaml.safe_dump(new_meta, sort_keys=False, allow_unicode=True) + "---\n" + new_body`。
5. **Atomic replace**：走 §8.5 atomic-write helper 一次性整体替换文件。
6. **持锁中** bump telemetry（**R4 fix YEL-15 — Data-integrity YEL-F**）：调 `telemetry.bump(name, kind="patch")`。在 §8.6 全局锁序中，此调用从 skill 1+2 层进入 telemetry 3+4 层（top-down），不破序。
7. 释放 per-skill `fd_file_lock`（第 2 层）→ 释放 in-proc lock（第 1 层），LIFO。返回。

**bump-after-replace, bump-before-release**：bump 必须发生在 atomic-replace **之后**（保证 telemetry 反映已落盘事件）且 filelock **释放之前**（保证 §8.6 锁序，避免下一个 acquirer 看到 stale telemetry）。如果 bump 抛 IOError → 不 fall-through、不重试（§7.3 已规定 IO error 路径），但**文件已落盘成功**——telemetry 短暂落后属 §7.2 carried-forward "bump-flush crash window"已记录债务。

**禁止**任何"先 truncate 文件再 append"或"in-place sed"路径——这两种写法都会让 crash-mid-write 留下半截 SKILL.md，后续 `yaml.safe_load` 抛异常，skill 整体失活。

**YAML 序列化合同（R4 fix YEL-13 — Data-integrity YEL-C）**：
- frontmatter 重新写出走 `yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)`。
- **comment 不保留**：parse → mutate → dump pipeline 是语义级 round-trip，不是文本级。任何 `# pinned by ops` 风格的人工注释会在下一次 `edit` / `patch` 之后丢失。**Acceptable for agent-tier**（`<workspace>/skills/agent/`）—— agent 拥有这类文件，注释也是 agent 自己写的；**user-tier 文件本就被 §4.4 矩阵 reject**，永远不被 `skill_manage` 编辑，所以 user 添加的 ops 注释不会丢。
- **style / quoting drift acceptable**：YAML 解析等价的风格变化（单引号 vs 双引号、boolean unquoted vs quoted）会产生噪声 git diff。M3 Curator **不得**把这类"cosmetic frontmatter diff"解读为 content change（决策 Log #56 已规定 Curator 看 `patches` 计数 + `last_patched_at` 等结构化字段，不依赖 raw diff）。
- **nested-dict key order**：PyYAML 5.1+ 在 `sort_keys=False` 下保留 insertion order。**已满足**（R5 fix YEL-R5-7）—— `pyproject.toml` 现行 pin `pyyaml>=6.0,<7.0.0` 已 subsume `>=5.1`，无需为 M2 新增 pin。plan-author 仅需在 M2 任何依赖调整中**保持**该现有约束不被放宽（不要把 `pyyaml` 改为 `>=4.x` 或 unconstrained）；现状下本条 spec 无需 action，仅作合同存档。

决策 Log #48：edit 在 spec 层是"verb 语义全量重写"，在实现层是"in-memory 重组 + atomic 整体替换"，两者一致；M3 review 时不得改成 in-place。

#### 为什么 `edit` 与 `patch` 共存而不合并（决策 #37）

合并方案（"用 `patch` + 空 `search` 表达全量重写"）被排除，理由如下：

1. **失败模式语义错位**：`patch` 的核心失败模式是 "search 找不到 / 多次出现"，对全量重写毫无意义；强行让 `search=""` 走该路径会逼 LLM 在错误信息里看到不相关的提示。
2. **Telemetry 语义清洁**：M1 设计 `patches` 计数器只用于"局部修补"——若 `edit` 也走 patch 路径，全量重写会误抬 `patches`，让 M3 Curator "patches 高 = skill 不稳定"的启发式判读失真。**M2 决定 `edit` 也 bump `patches`**（与 patch 共用计数器，符合 M1 §4.1 字段语义"M2 起由 skill_manage 触发"的承诺），但 verb 仍分两个，给 M3 留下"只看 verb tag 即可拆分两类频次"的可能。
3. **LLM 表意**：verb 即意图。"全量重写"和"局部替换"在 prompt 描述里是两件事，让 LLM 显式选择降低误用率。
4. **实现复用**：两 verb 内部都走同一 `_acquire_locks → read → mutate → write_atomic → bump → update_provenance` pipeline，仅 mutate 步骤不同；不存在维护成本翻倍。

> 备选方案及其拒绝理由记录在决策日志 #37。M3 review 时若仍想合并，必须先解释 telemetry 语义如何切分。

### 4.4 Provenance × verb 矩阵（**硬性合同**）

| verb | bundled (`builtin`) | user | agent | hub |
|---|---|---|---|---|
| `create` | n/a — `create` 不接受 tier 参数，永远落 `agent` 层 | — | — | — |
| `edit` | reject | reject | **allow** | reject |
| `patch` | reject | reject | **allow** | reject |
| `delete` | reject | reject | **allow** | reject |

矩阵硬性约束：

- `bundled` 永远 read-only（M1 §3.4 + roadmap §6.2）。
- `user` 是 user 拥有的命名空间，agent 永不能改。M2 显式 reject。
- `hub` 是 schema 预留（远端 skill 仓库 fetch 来的副本，未来 milestone 才实装），M2 一律 reject。
- 判定 origin 用 M1 提供的 `SkillsLoader.list_skills_with_shadows()`（`nanobot/agent/skills.py:171`，M1 §4.2 锁定的反 shadow primitive，被 `nanobot/agent/loop.py:872` 在 reconcile 路径使用）——返回的 `SkillEntry` 含 `effective_origin` 与 `shadowed_origins`，能正确识别"一个 name 在多 tier 同时存在时哪个 tier 当前生效"的语义。**不**用 `_infer_origin_from_path`（per-path lexical 推断，对 cross-tier shadow 无感知，会让 edit/patch 在 user 影子 agent 时误判 origin == "agent" 而放行）。
- 如果一个 name 同时存在于多 tier（`shadowed_origins` 非空），任何 `edit/patch/delete` 都 reject—— effective tier 是 user 时不允许动；禁止"改了 agent 但 user 仍生效"这种迷惑写入。
- 决策 Log #49：M2 用 `list_skills_with_shadows()` 作 shadow 检查 single source of truth；这是 M2 → M3 间的稳定接口（§14 表）。

### 4.5 返回 JSON shape

工具向 LLM 返回 dict（保持 nanobot 已有 tool 返回风格，参考 `apply_patch._format_summary`）：

```python
# success
{
    "ok": True,
    "verb": "edit",
    "name": "auto-summarize",
    "path": "skills/agent/auto-summarize/SKILL.md",   # 相对 workspace
    "stats": {"added": 12, "deleted": 5},             # patch / edit 时填，复用 _line_diff_stats
    "patched_by": "agent",                            # 写入的 provenance tag
}

# rejection
{
    "ok": False,
    "verb": "patch",
    "name": "summarize",
    "error": "skill 'summarize' has effective origin 'user'; skill_manage refuses to mutate user-tier skills",
    "error_code": "tier_locked",  # tier_locked | name_exists | name_collision | not_found | search_ambiguous | search_missing | rate_limited | invalid_name | concurrency_timeout | io_error | PATH_ESCAPE | BODY_TOO_LARGE | TOO_MANY_AGENT_SKILLS | DESCRIPTION_TOO_LONG | ATOMIC_WRITE_FAILED
}
```

`error_code` 的取值集是显式枚举，给 M3 Curator 做策略决策时 grep 用。

> **R3 命名规约（YEL-7 freeze）**：M2 引入 `error_code` 枚举为 **additive-extensible** 契约——M3+ 只许追加新 code，**禁止**重命名 / 删除 / 重新编号已存在的 code。混合大小写是历史遗留：M1/M2 早期定义的（`tier_locked` / `name_exists` / `not_found` 等）保持小写下划线；R3 新增的（`PATH_ESCAPE` / `BODY_TOO_LARGE` 等）按 §14.4 命名约定走 SCREAMING_SNAKE。M3 review 若想统一为单一风格须扩 telemetry/tool schema_version 而非改本枚举。决策 Log #54。

### 4.6 Name validation（防越权）

`_validate_skill_name(name)` 必须拒绝：

- 含 `/`、`\`、`..`、空白、控制字符的 name（防路径注入）。
- 长度 0 或 > 64。
- **以 `.` 开头**（YEL-10）—— 拒 `.lock`、`.gitignore`、`.DS_Store` 等隐藏文件名；明确防止 skill 名与 §8.1 锁文件 / git 元文件 / OS 元文件碰撞。
- 不匹配 `^[a-z0-9][a-z0-9-]*$`，编译时**必须**带 `re.ASCII` 标志（YEL-6）—— Unicode confusables 例如 Cyrillic `а` (U+0430) vs Latin `a` (U+0061) 在不带 `re.ASCII` 时正则可能放行，造成"看着同名但磁盘是两个 skill"的脏污状态。所有 M2 引入的 regex（name + §3.5 task_id）都按这条统一处理。
- 保留名集合：`{"agent", "user", "builtin", "hub"}`——origin tier 命名空间，避免与 M1 §10.1 风险表第 5 行"user 把 origin 名当 skill 名"反向触发，并预留未来 `hub` tier。`.lock` 已被上面的"以 `.` 开头"规则拒掉，无需单列。

校验失败 → `error_code = "invalid_name"`，不写盘、不 bump。

### 4.6.1 路径逃逸防御（R3 fix RED-4）

§4.6 拦截了"name 长得像路径"的攻击，但**预先放置的 symlink** 仍可能让一个合法 name `foo` 在 `<workspace>/skills/agent/foo` 处存在一条指向 `/etc/passwd` 的 symlink。M2 必须显式防御：

- 所有 path 解析统一走 `Path(target).resolve(strict=True)` → `is_relative_to(skills_agent_root.resolve(strict=True))`。
- POSIX 上 read 路径 `os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)`；write 路径的 atomic-write tmp 文件创建在 `skills_agent_root` 内，最终 `os.replace` 之前对目标路径再做一次 `O_NOFOLLOW` `os.open` 验证（拿到 fd 之后才允许后续 `os.replace`）。
- **跨平台兼容（R4 fix YEL-4 — Feasibility Y2）**：Windows 缺少 `os.O_NOFOLLOW` / `os.O_CLOEXEC`，直接 `os.O_NOFOLLOW` 引用会 `AttributeError`。实施合同：
  - flag 计算用 `flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)`（缺失即 0，按位或不影响其他 flag）。
  - 当 `O_NOFOLLOW` 不可用时（Windows 等）：在 `os.open` 之前**显式**做 `Path(path).is_symlink()` 预检 → 若为 symlink 直接 reject `PATH_ESCAPE`；其后再做 `Path(path).resolve(strict=True).is_relative_to(skills_agent_root.resolve(strict=True))`，把"resolve 后路径必须仍在 root 内"作为兜底守护。
  - 这与 `nanobot/agent/skills_telemetry.py:89` 既有的 `if sys.platform != "win32"` POSIX-only fsync(parent_dir) gating 模式一致；M2 的 atomic-write 在 §8.5 也沿用同款 platform gate。
- 解析后路径任一段是 symlink 且 target 落在 `skills_agent_root` 之外 → reject `error_code = "PATH_ESCAPE"`，不写盘、不 bump。
- 复用 M1 现有 `nanobot/agent/tools/path_utils.py:resolve_workspace_path`（被 `_FsTool._resolve` 在 `nanobot/agent/tools/filesystem.py:82-88` 使用）作为同款边界检查原语，确保 M2 路径合同与 M1 文件系统工具一致。
- 决策 Log #53。

### 4.7 Idempotency 不承诺

M2 不承诺幂等：连续两次 `create` 同名是 `name_exists` reject，不是 no-op；连续两次相同 `edit` 仍各 bump 一次 `patches`（counter 是事件计数器，不是状态机）。这是有意的——Curator 看到"同一 skill 短时间两次 patch" 反映真实"再加工"行为，幂等屏蔽会让信号失真。

## 5. 触发规则（Trigger）

### 5.1 自动触发：**没有**

M2 **不**实装任何代码层的"看到 X 自动调 skill_manage"启发式。LLM 自行根据：

- 工具 description 文本（§4.2）；
- builtin `skill-creator` skill 的现有 prompt（`nanobot/skills/skill-creator/SKILL.md`）；
- Dream template (`nanobot/templates/agent/dream.md`) 在 §6 更新后的提示语，

决定何时调用。这是有意的边界——telemetry 驱动的自动建议属于 M3 Curator 的"`skill_manage` 触发规则"那一段，M2 只交付机制不交付策略。

### 5.2 Runaway-edit 频次保护（机制层，非策略层）

**唯一**的代码层 trigger 限制：rate-cap。

- 默认值：每 turn 内最多 **5 次成功** `skill_manage` 写动作（任意 verb 计入同一计数器）。
- 配置 key：`agents.defaults.skillManage.maxMutationsPerTurn`，camelCase（与 M1 `auxiliary.modelPreset` 同款风格），别名 Python 侧 `max_mutations_per_turn`。Schema 位置：新增 `SkillManageConfig(Base)` 嵌入 `AgentDefaults`。命名约定见 §14.4：tool name = snake (`skill_manage`)，config key = camel (`skillManage`)，error_code = SCREAMING_SNAKE。
- 超限行为：`error_code = "rate_limited"`，**不**落盘、**不**bump telemetry。

为什么 rate-cap 是 mechanism 而非 policy：runaway 的判定阈值（5/turn vs 10/turn）允许 user 调；但是否要"超限自动 archive 该 skill" / "通知 Curator 复审"——那是 M3 的责任。M2 仅在物理层防"agent 一 turn 内 patch 50 次同一 skill"这种灾难场景。

#### §5.2.1 rate-cap 状态机（R3 fix RED-1）

**counter 形态（R4 fix YEL-10 + Coherence YEL-2）**：

```python
RuntimeState._runtime_vars["skill_manage.mutations_this_turn"]: int  # 起始 0
```

**简化为单一 int**。R3 设计为 4-桶 dict 但**M2 内无消费者**——只有 M3 Curator 可能想区分 create-spam vs delete-spam，那时再切换数据结构（M3 spec 自己宣布扩展）。M2 选最小数据结构以减少 §10.6 测试网与实施复杂度。原 §5.2 prose"同一计数器"现与本 §5.2.1 数据形态一致。

> **R6 注脚（RED-2 fix）**：§5.2.1 本节文本即为单一 int counter 的权威 spec；M3 review 读本节 + §12 carried-forward debt，不读 §13 row #55（该行仅作 R3→R4 演进史保留，已迁至 §13.A superseded decisions）。

**namespace 锁定**（YEL-3 fix）：`_runtime_vars` key 命名空间 `skill_manage.*` 由 M2 独占预留。`SelfTool.set_context` (`nanobot/agent/tools/self.py:340-349`) 写 `_runtime_vars` 时**禁止**使用 `skill_manage.` 前缀（M2 plan 阶段 fc-architect 必须在 SelfTool prompt schema 里加注释提醒）。

**计数器位置 + 注入路径**：`SkillManageTool` 在 `set_context(ctx)` 时拿到 `runtime_state` 引用——与 `SelfTool` 同款注入路径；`runtime_state` 由 `AgentRunner` 在每个 turn 入口注入到 `RequestContext` 或 ToolContext（具体注入点 plan 阶段定，本 spec 锁数据结构不锁行号，因为 runner.py 仍在演化）。

**reset 点（精确，R4 fix YEL-2 + YEL-3）**：

> **R4 修订**：原 R3 文本写"reset 发生在 `AgentRunner.run()` 入口"，与 §5.2.1 自身"turn = 一次 LLM inference + 后续 tool 调用"定义不一致——`AgentRunner.run()` 包裹 `_run_core` 的整个 for-loop（默认 `max_iterations=10-20`，参见 `runner.py:343`），一次 `run()` 调用包含**多个**LLM-inference iteration。原方案下 agent 每条 inbound message 可拿 `max_iterations × maxMutationsPerTurn = 100+` 次写动作，违反 5/turn 承诺。

**采纳协议**：reset 与 §5.2.1 turn 定义对齐——绑定到 `_run_core` 的 **per-iteration 边界**（`runner.py:343` `for iteration in range(spec.max_iterations)`），每进一次 iteration 顶部即重置计数器为 `0`。该位置与现有 `workspace_violation_counts`（`runner.py:337`）、`empty_content_retries`（`runner.py:338`）等 per-turn 状态在同一作用域，模式一致。

- "turn" = 一个 `_run_core` for-loop iteration（一次 LLM inference + 该 inference 触发的所有 tool 调用）。
- 一次 `AgentRunner.run()` 多 iteration → 每 iteration 起点计数器重置 → 每 iteration 独立 5 次额度。
- 同一 iteration 内的多个 tool_call（含 subagent spawn 后 child 在同一 iteration 内多次调用）共享同一 int counter。

**RuntimeState 归属澄清（YEL-3）**：`RuntimeState` 由 `AgentLoop` 持有（`nanobot/agent/loop.py:506`、`:621`、`:1174`），**不**属于 `AgentRunner`。`AgentRunner` 是**单实例**（`SubagentManager.runner = AgentRunner(provider)` at `nanobot/agent/subagent.py:116`，被父-子复用 at `subagent.py:248`）；freshness 不来自"独立 Runner 实例"也不来自"独立 RuntimeState 实例"，而来自上述**per-iteration dict reset**。

**subagent 配额继承表**（R4 fix YEL-2 + YEL-3）：

| 场景 | 配额行为 |
|---|---|
| 父 agent iteration 内 → spawn subagent tool call | `Tool` 内部触发的 subagent invocation 也走 `_run_core` for-loop；subagent 第一个 iteration 顶部 reset → 独立满额 5 |
| subagent 同一 iteration 内 → 多次 tool 调用 | 共享同一 `_runtime_vars["skill_manage.mutations_this_turn"]` int → 共享 5 次额度 |
| subagent 多 iteration | 每 iteration 顶部 reset → 各独立 5 次 |
| subagent 返回 → 父 agent 下一 iteration | 父进入下一 iteration 顶部 reset → 父独立 5 次 |

**Dream 共享与否**：**不共享**。Dream 走 `MemoryStore.build_dream_tools()` 注册的独立 ephemeral `AgentRunner.run()`，独立进入 `_run_core` for-loop → 独立 per-iteration reset → 与主 agent 的额度物理隔离。

**聚合 fork-bomb 上限（YEL-8 → §11 out-of-scope）**：N 个嵌套 subagent 各自每 iteration 拿 5 次额度，理论上仍有 N×5 上限的"消防漏洞"。M2 不引入跨 subagent 的 aggregate cap；详见 §11 item 10 + Decision Log #64。

**计数器形态（R4 fix YEL-10）**：M2 选**单一 int**（参见上方"counter 形态"）。原 R3 4-桶 dict 设计在 M2 没有消费者（只有 M3 Curator 才会用 per-verb 信号），M2 只需"any-verb total ≥ N → reject"语义；切到单一 int 简化测试与实施。M3 想加 per-verb sub-cap 时改为 dict 即可——参见 §12 carried-forward。决策 Log #55 改写：M2 锁单 int，M3 拓展时升级为 dict + bump `SkillManageConfig` schema 字段。

**Increment-and-check 同步性（R4 fix YEL-14 — Data-integrity YEL-E）**：rate-cap 的 read+check+increment 必须作为**同步临界段**执行——三个动作之间不能有 `await` 点。asyncio 协程调度在 `await` 点 yield，两个并行 tool call 都看到 counter==4 → 都增 → 实际 count=6（绕过 cap 一次）。**实施合同**：在异步 tool handler 内调用一个**普通 def 函数** `_increment_mutation_counter_or_reject(runtime_state) -> bool`；该函数体内做 `current = state["..."]; if current >= cap: return False; state["..."] = current + 1; return True`，全程无 await。asyncio 协作调度本身**不**保证此原子性，必须靠"同步函数中无 await 点"的物理事实。

#### §5.2.2 `_run_core` runtime_state 注入路径（R5 fix YEL-R5-3 — Feasibility A3）

§5.2.1 reset 点锁定在 `_run_core` 每 iteration 顶部（`runner.py:343` `for iteration in range(spec.max_iterations)`），但 `AgentRunner` 当前**零** `runtime_state` 引用——`RuntimeState` 仅由 `AgentLoop` 持有（`loop.py:506, 621, 1174`）。reset 要在 runner 端发生，runner 必须能访问 RuntimeState；spec 必须为 plan-author 命名候选注入路径，避免重新发明。

**三个候选 wiring approach**（plan-author 选其一并写入 plan §2 file-map section）：

- **Option W1（推荐 — `AgentRunSpec` 字段）**：
  - 在 `AgentRunSpec` dataclass 上加 `runtime_state: RuntimeState | None = None` 字段（带默认值 `None` 保证向后兼容现有 caller）。
  - `AgentLoop` 在构造 `AgentRunSpec` 时把自己持有的 `RuntimeState` 引用填入（`loop.py:506`/`:621`/`:1174` 三个构造点都已经持有该引用）。
  - `_run_core` (`runner.py:343`) 进入 for-loop 顶部 `if spec.runtime_state is not None: spec.runtime_state._runtime_vars["skill_manage.mutations_this_turn"] = 0`。
  - **优点**：与现有 `AgentRunSpec` 已有字段风格一致；`AgentRunner` 实例不存状态；与 single-instance runner（`SubagentManager.runner = AgentRunner(provider)`）哲学一致。**建议默认选这条**。

- **Option W2（rejected）**：`AgentRunner.__init__` 加 `runtime_state` 参数。**拒绝**：runner 是 single-instance（`subagent.py:116, 248` 父-子复用），构造期绑定 RuntimeState 引用会让 subagent 与父 agent 生命周期耦合，破坏单实例假设。

- **Option W3（备选）**：`AgentRunSpec` 加 `reset_per_iteration: Callable[[], None] | None` 字段，runner 完全不感知 RuntimeState 字段语义。**仅当 W1 被否决时再考虑**——多一层 callback 间接，未来加更多 per-iteration 操作时回调列表会膨胀。

**spec 不锁行号**：`runner.py:343` 是当前 mainline 的 for-loop 行号，runner.py 仍在演化；plan-author 落地时按当时实际 for-loop 入口为准。**spec 锁的是数据结构 + 注入语义**：reset 必须发生在每 iteration 顶部、必须与现有 `workspace_violation_counts` (`runner.py:337`) 同作用域。Plan-author MUST document the chosen wiring option (W1/W2/W3) in plan §2 (file-map section), with one-sentence justification for any non-W1 choice. This selection is contractual for implementation and is checked in M2 drift-check Phase 5.

决策 Log #67（R5）见 §13.B（plan-author choice point，非 active decision）；wiring 三个候选 W1/W2/W3 已命名，W1 推荐；最终选择由 plan-author 在 plan §2 file-map 决定。

### 5.3 失败计数？不算

只有**成功**的写动作计 turn 内 mutation 次数（与 §7.1 telemetry bump 同源）。rejected 调用（任何 `error_code`）不抬计数——否则 LLM 因不合法名字反复试错就会撞墙；这与 M1 telemetry §4.4 "reconcile 不动 counters" 的同款"事件流不混抽象层"哲学一致。

## 6. Dream 整合点

### 6.1 工具注册（核心改动）

在 `nanobot/agent/memory.py:470` 起的 `MemoryStore.build_dream_tools()` 内追加：

```python
# 现有：ReadFileTool / EditFileTool / ApplyPatchTool / WriteFileTool 不动
tools.register(SkillManageTool(
    workspace=workspace,
    telemetry=self.telemetry,           # 复用主进程注入的 telemetry（M1 §11 接口契约）
    provenance_tag="dream",             # 让所有 created_by / patched_by 落 "dream"
))
```

注册顺序：无关紧要。`ToolRegistry.get_definitions()`（`nanobot/agent/tools/registry.py:67-90`）在 line 87 对 builtins 按 `_schema_name` 字母排序，意味着 LLM prompt 里的工具呈现顺序由 `Tool.name` 字典序决定，注册先后不影响顺序。`SkillManageTool` 与 `WriteFileTool` 的 `Tool.name` 不同（`skill_manage` vs `write_file`）→ registry 不会发生 name 覆盖；放在 `WriteFileTool(skills_dir)` 之前或之后都行，本 spec 不强制。

`MemoryStore` 当前不持有 `SkillTelemetry`；M2 需要让 `MemoryStore.__init__` 多接受一个 `telemetry: SkillTelemetry | None = None` 关键字参数（与 M1 §7 决策 #23 keyword-only 风格对齐），caller 在构造 `MemoryStore` 时显式注入主进程 telemetry。

### 6.2 模板更新

`nanobot/templates/agent/dream.md` "Skill discovery & creation" 段（当前文件 line 92-99）增加一行：

```markdown
For [SKILL] entries:
- **Prefer the `skill_manage` tool over manual file writes** for create/edit/patch/delete; it enforces tier safety, writes provenance frontmatter, and counts toward telemetry. The legacy WriteFileTool path remains for emergency-only fallback.
- Create `skills/<name>/SKILL.md`; reference `{{ skill_creator_path }}` for format
- ...（其余保留）
```

### 6.3 Dream 自身流程不动

Dream 的两阶段 consolidation flow（`MemoryStore.dream_run_completed` / `consolidator_archive.md` 配套）M2 不修改。M2 只往 Dream 工具笼里塞一把新工具 + 改 template 文字。

### 6.4 旧工具不撤（明确决策）

- `WriteFileTool(allowed_dir=skills_dir)` —— **保留**。
- `EditFileTool(extra_allowed_dirs=[..., skills_dir])` —— **保留**。
- `ApplyPatchTool(extra_allowed_dirs=[..., skills_dir])` —— **保留**。

撤旧的代价：Dream 失去 escape hatch，一旦 `skill_manage` 抛 bug，Dream 就完全无法操作 skill 文件。M2 接受冗余以换可恢复性；正式撤是 M3 cleanup 任务（见 §11）。

### 6.5 MemoryStore prod call-site audit（R3 fix RED-2）

`MemoryStore.build_dream_tools()` 是 §6.1 注入 `SkillManageTool(provenance_tag="dream")` 的唯一入口。所有 prod caller 必须**经过**这个工厂方法构造 Dream tool registry，**不能**绕路；M2 实施 plan 必须验证以下三个 caller 的注入路径正常：

| call site | 文件 + 行号 | 备注 |
|---|---|---|
| ContextBuilder（构造 `MemoryStore`） | `nanobot/agent/context.py:73` 与同文件 `:110` | ContextBuilder 自己持有 `MemoryStore`，但 ContextBuilder.build 不直接调 `build_dream_tools`——这是验证 `MemoryStore` 实例链路的源头 |
| CLI 入口 | `nanobot/cli/commands.py:1103` | 直接调 `store.build_dream_tools()` 注册到 Dream runner |
| 内置命令 dispatch | `nanobot/command/builtin.py:338` | 同上 |

`MemoryStore.__init__` 在 §6.1 已要求加 `telemetry: SkillTelemetry | None = None` 关键字参数。三个 caller 必须显式注入主进程 telemetry 单例：ContextBuilder 处由 AgentLoop 创建 ContextBuilder 时把 telemetry 透传给 MemoryStore；CLI / builtin 处由各自的入口函数获取 telemetry 句柄（M1 §11 接口契约已确立 telemetry 单例可由 AgentLoop 暴露）。任一 caller 漏传则该 store 的 Dream tool 链路 telemetry=None → SkillManageTool bump 路径会拿到 None 而 fail-fast（NPE）。M2 测试网必须覆盖三个 caller。

### 6.6 Dream 写出的 skill 字段语义（R4 fix YEL-9 — Scope Y1；R3 fix YEL-2 sub）

§3.2 规定 Dream 调 `skill_manage create` / `edit` / `patch` 时把 `created_by` / `patched_by` 写为 `"dream"`。

**M2 锁定的合同（hard rule）**：
- `created_by` / `patched_by` 字段值在 Dream 路径下**必须**为字面量 `"dream"`（与 §3.2 enum 一致）。
- Dream 写盘走与主 agent 同一 `SkillManageTool` 工具表面，遵循同一 §3.7 配额、§4.4 矩阵、§4.6 name 校验、§5.2 rate-cap、§8.5 atomic-write、§8.6 锁序——所有 M2 防御对 Dream 同样生效。
- 这两条是 M2 → M3 的**字段契约**，不可破。

**给 M3 Curator 的建议（recommendation, not binding）**：
- 当 M3 spec 设计 Curator 的 prune / archive 决策模型时，**可以考虑**把 `patched_by="dream"` / `created_by="dream"` 当作降低优先级的 prior——Dream 在不完全 conversation context 下做 consolidation，比主 agent 在 in-flight tool loop 里的 edit 信噪比低。
- 若同一 skill 后续被主 agent (`patched_by="agent"`) 重新背书，prior 可被洗掉。
- **是否采用这条 prior、用什么权重、如何与"使用频次 / view-use 比"等其他特征加权——M2 spec 不做规定**，由 M3 spec 自行决定。M2 仅承诺字段会被准确写出。

决策 Log #56 改写：M2 锁定 `created_by` / `patched_by` 字段在 Dream 路径下值为 `"dream"`；M3 Curator **可**用此字段作为 pruning prior；M2 不绑定 M3 的权重 / 决策模型。

## 7. Telemetry

### 7.1 计数器与 bump 时机

| 事件 | 触发 bump？ | bump kind |
|---|---|---|
| `create` 成功 | **不**直接 bump | M1 reconcile 在下次启动 / 下次 turn 起始处发现新 skill 后写零计数条目（M1 §4.4 "新出现的 skill"分支） |
| `edit` 成功 | bump | `"patch"`（M1 已实现的 kind，M2 是首位调用方） |
| `patch` 成功 | bump | `"patch"` |
| `delete` 成功 | bump（**R4 fix YEL-17**） | `"delete"`（tombstone marker；新 kind，详见 §4.3 delete step 5.5）。M1 reconcile 仍是 entry 物理 deleter（M1 invariant 4 不破），tombstone 只是给 reconcile 的"reuse 时清零 counter"提示 |
| 任何失败（reject / rate_limit / lock timeout / validation） | **不** bump | 见 §7.3 |

`edit` 与 `patch` 共用 `bump(name, "patch")` —— 即"这是一次对 skill 内容的修改事件"。M1 §1.1 item 3 的 "patch kind M1 不调用" 在 M2 被首次落实。

> **术语辨析（Y7）**：`bump(name, kind="patch")` 调用形式中的 `kind` 是动词式参数（描述"这次事件是哪类"），值为字符串 `"patch"`；它递增的、写入 `<workspace>/skills/.telemetry.json` 的 on-disk 计数器键名是 `<entry>.patches`（复数名词）。两者拼写不同、用途不同，都正确，**不要混为一谈**。`edit` 与 `patch` verb 都走 `kind="patch"`，都把 `entry.patches` 加 1。

### 7.2 `create` / `delete` 依赖 M1 reconcile（R3 fix RED-10 — bump vs reconcile 严格切分）

M1 retro `docs/hermes-evolution/retros/m1-foundations.md` follow-up #49 已显式区分两类"orphan"语义；M2 严格沿用，**禁止合并**：

#### Case A — In-memory ghost（`bump` 写盘前 skill 已被删）

`bump(name, kind)` 在内存中 RMW telemetry dict；如果 skill 文件在 bump 调用与 flush 之间被另一调用方 delete，bump 写出的 entry 是个 in-memory ghost——M1 设计为**不**立刻消除，让 reader 看到一条 `pending decay` 状态的 entry。延迟 reconcile 修正（writer-tag 哲学）。**这是合法状态**，不需要 M2 干预。

#### Case B — On-disk orphan（telemetry 持有的 entry 对应 skill 文件不存在）

启动期 / 周期性 `reconcile()`（M1 §4.4）扫盘比对：磁盘有 entry 而 skill 文件不存在 → reconcile 删除该 entry。**reconcile 是 on-disk orphan 的唯一 deleter**（M1 invariant 4）。M2 **绝对不能**在 `delete` verb 路径里加并行的 telemetry-entry 清理，否则破 M1 invariant 4。

M2 在 `create` 路径调用 `reconcile()` 注册零计数 entry；`delete` 路径仅 bump tombstone marker，**不**删 entry：

1. `create` 路径：物理写盘 SKILL.md 成功后，**在 layer-2 `<name>/.lock` 持有期内**调用 `telemetry.reconcile(known_entries)` 注册新 entry（`origin="agent"` / `views=uses=patches=0`）。reconcile 内部取 layer 3 + 4，对外保持 ascending acquisition (2→3→4) 不破死锁不变量。**Errata 1**（见 §6 carry-forward 3）：spec 早期版本（§7.2 step 1 旧文）假设 M1 `bump()` 对未知 name 懒初始化；实际 M1 `_rmw_merge(writer="bump")` 在 `disk_entry is None` 时 `continue`（M1 invariant 3 / 决策 #31）——懒初始化路径从未通过端到端。M2 在 `do_create` 显式 reconcile 是修复"首次 patch 计数永久丢失"的最小变更，保留 M1 invariant 3 不动。
2. `delete` 路径：物理删目录 + bump `kind="delete"` tombstone（R4 YEL-17）→ 下次 reconcile 物理删孤儿 entry；**或**若同 name 在 reconcile 前被 reuse，reconcile 看到 tombstone 后清零 counter（防止旧统计窜入新 skill）。
3. **M2 仅在 `create` 路径**做 create-time reconcile；`delete` 路径**不**做 delete-time 立刻 reconcile（沿用 M1 "reconcile 是启动 / 显式触发事件"的语义；tombstone bump 走标准 `bump()` 路径，不抢 `_flush_lock` 之外的锁）。

> **Carried-forward 1（已知延迟一致性）**：`delete` 与下次 reconcile 之间，若另一进程对该 name bump 一次（例如 list_skills 已返回旧条目，agent 立刻 use），telemetry 多一行 `origin="unknown"` 孤儿；下次 reconcile 修复。M2 接受；M3 若需要立即一致，自己加路径。
>
> **Carried-forward 2（YEL-9 — bump-flush crash window）**：M1 已知有 ≤200ms 的 in-memory bump 未 flush 窗口；如果进程在该窗口内 crash，bump 事件丢失。M2 **继承**此窗口，不引入新的耐久性保证。和 §8.5 / §7.3 的 atomic-write 合同不冲突——文件写盘与 telemetry bump 是两条耐久性独立路径，bump 丢失不影响 skill 文件本身已落盘的事实。Cross-ref M1 spec §4.3。
>
> **Carried-forward 3（Errata 1 — M1 lazy-bump-init 假设错误）**：spec §7.2 早期版本假设"M1 §4.2 `bump()` 对未知 name 已支持懒初始化"，并据此在 §7.2 step 3 写下"M2 不引入 create-time 立刻 reconcile"。t-10 多进程并发 patch 测试设计 surfaced 一个隐藏的端到端 bug——`do_create` 不 bump → 下次 `flush(writer="bump")` 内 `_rmw_merge` 在 `disk_entry is None` 时 `continue`（决策 #31 / M1 invariant 3）→ flush phase 3 仍把 `_last_synced_counts[name]` 推进到内存计数器值 → 即使下一次 `reconcile()` 把 entry 落盘成零计数，后续 RMW delta 永远算成 `0`，**新 skill 的第一个 patch 计数永久丢失**。修复（commit `feature/m2-skill-manage-fix-bump-on-create`）：`do_create` 在 layer-2 `fd_file_lock` 持有期内、`atomic_write` 之后、释放锁之前调用 `telemetry.reconcile(known_entries)`。这保留 M1 invariant 3（reconcile 仍然是 entry 的唯一创建者），仅扩大了 reconcile 的触发时机（启动期 + create-time）。`delete` 路径**不**改——tombstone bump 仍走标准 `bump()`。

### 7.3 失败路径的 telemetry 静默（决策 #39）

**任何**失败都不 bump。具体清单：

- `_validate_skill_name` 失败 → 不 bump。
- §4.4 矩阵 reject → 不 bump。
- filelock 超时（§8.1）→ 不 bump，向 LLM 返回 `error_code="concurrency_timeout"`。
- §5.2 rate_limit → 不 bump。
- IO 异常（磁盘满、权限错误）→ 不 bump，warn-throttle 记 log（沿用 M1 §4.3 节流策略，新增 `failure_kind = "skill_manage_io_error"`）。
- patch 的 search 找不到 / 多次出现 → 不 bump。

M1 §4.3 telemetry "bump 永远 O(1) 不触磁盘" 的不变量在 M2 仍然成立——M2 写盘动作发生在 telemetry bump **之前**，bump 只在写盘 atomic_replace 成功之后被调用。`delete` 的 tombstone bump（§4.3 step 5.5）也遵循"先物理删 → 再 bump tombstone"序，遵循同款"事件 bump 在副作用落盘后"原则。

### 7.4 不引入新 schema_version

新增 frontmatter 字段 (`last_patched_at` / `patched_by` / `created_by`) **只**落地在 `SKILL.md` 的 YAML frontmatter，**不**写入 `<workspace>/skills/.telemetry.json`。

**Tombstone 字段（R4 fix YEL-17）—— additive-only**：M2 给 telemetry entry 增加可选字段 `tombstone: bool`（默认 absent / false），由 `bump(kind="delete")` 写入。该字段对老 reader 透明（`.get("tombstone", False)` 自然返回 False），符合 M1 §4.1 forward-compat schema 演进规则——M1 telemetry schema_version 保持 `1`，无 bump，无迁移。M3 reconcile 升级时识别该字段做 reuse 清零；M3 自身决定是否需要 schema_version=2。

## 8. 并发与 Subagent 语义

### 8.1 两层锁（与 M1 telemetry 同款思路）

| 层 | 工具 | 保护对象 | 粒度 |
|---|---|---|---|
| 内存层 | per-process dict `_skill_inproc_locks: dict[str, threading.Lock]` 维护在 `SkillManageTool` 类作用域 | 同进程内多协程 / 多线程对**同一 name** 的写动作 | name 维度，懒创建 |
| 进程间层 | `fd_file_lock(<workspace>/skills/agent/<name>/.lock, timeout=1.0)`（helper from `nanobot/agent/_atomic_io.py`，内部 `os.open(O_NOFOLLOW \| O_CREAT \| O_CLOEXEC, 0o600)` + `fcntl.flock(fd, LOCK_EX)`，详见 §3.7.1 step 5） | 跨进程的 read-modify-write of `SKILL.md` | name 维度 |

获取顺序：先 in-proc lock，后 filelock；释放反序。两层独立，与 M1 telemetry `_lock` / `filelock` 物理上不共享对象（不要复用 telemetry 的 `_flush_lock`，那把锁有自己的合同）。

#### 失败降级

- `fd_file_lock` 等不到（默认 timeout 1.0 秒，比 telemetry 的 0.2s 长——skill 文件远小于 telemetry RMW 量级，但 LLM 调用本身不期望次秒级）：返回 `error_code = "concurrency_timeout"`，不 bump，不重试（让 LLM 决定下一步）。
- in-proc lock 100% 等到（同进程拿不到只意味着另一协程在写，等就行）。

#### Stale `.lock` 文件（Y3）

`<name>/.lock` 文件在进程 crash 后会留在磁盘上——这是预期且无害的。M2 per-skill lock 实现见 §3.7.1 step 5：底层是 `os.open(<name>/.lock, O_NOFOLLOW | O_CREAT | O_CLOEXEC, 0o600)` 取 fd + `fcntl.flock(fd, LOCK_EX)`（不再依赖 `filelock` 库，参见决策 #69 amended）。**锁状态由内核 fd 持有，进程退出时由 OS 自动释放**；磁盘上的 `.lock` 文件只是一个稳定的命名句柄，不是锁状态本身。下次启动时新进程通过 `fd_file_lock` 拿到的是一把全新的 advisory lock。M1 启动期 reconcile 不触碰任何 `.lock` 文件（M1 §4.4 reconcile 只看 `SKILL.md` 存在性 + `.telemetry.json` 条目），无需特殊清理逻辑。

#### last-writer-wins 的语义

并发两次 `patch` 同一 skill，filelock 串行后：

- 都成功 → 都 bump `patches`（计数 +2）。
- 第二个 `patch` 的 `search` 在第一个写完后可能找不到（被改没了）→ 第二个 reject `search_missing`，不 bump。

这与 M1 telemetry 的"counter 单调累计"一致：**每次成功的写**都贡献一次 bump，正确反映"有 N 次真实修改事件"。

> 备注：本节其余文字偶尔以 "filelock" 作为通用名称指代"per-skill 进程间锁"概念；具体实现已在 §3.7.1 step 5 锁定为 `fd_file_lock` helper（非 `filelock` 库）。**仅** §8.6 lock-order layer 3 / layer 4 与本 spec 一些 telemetry 上下文中的 `filelock.FileLock(...)` 字面引用仍指 M1 telemetry 直接使用的 `filelock` 库（详见 §8.6 layer-4 telemetry 范围说明）。

### 8.2 Cache 阻塞？没有

M2 不实装 "REJECT if writer in flight" 这种乐观锁——那是 M3 策略层的事（"如果有 Curator 正在审议这个 skill，agent 此刻不许 edit"）。M2 只做悲观串行：filelock 串行 + 各自 last-writer-wins。

### 8.3 Subagent 共用 + 血缘标签（决策 #40）

- **物理路径**：subagent 与主 agent 共用 `<workspace>/skills/agent/`。**不**给 subagent 单独开 `<workspace>/skills/agent/subagent_<task_id>/` 子目录——那会污染 SkillsLoader 的"agent-source"扫描，逻辑复杂度暴涨。
- **血缘记录**（R1 fix — 走 registry-build 时构造注入，不扩 RequestContext）：
  - `RequestContext`（`nanobot/agent/tools/context.py:14-21`）只承载 `channel/chat_id/message_id/session_key/metadata` 五字段，**没有** `task_id`。M2 不扩 `RequestContext`。
  - 取而代之：`SkillManageTool.__init__` 接受 keyword `provenance_tag: str = "agent"`，存为实例属性 `self._provenance_tag_`；写盘路径在落 `created_by` / `patched_by` 时直接读这个实例属性。
  - 主 agent 路径：注册时不传 `provenance_tag`，默认 `"agent"`。
  - Subagent 路径：`SubagentManager._build_tools`（`nanobot/agent/subagent.py:130-149`）在拿到本次 spawn 的 `task_id`（`subagent.py:168` 处生成）后，把它闭包进 registry 构造路径，注册 `SkillManageTool(workspace=root, telemetry=self.telemetry, provenance_tag=f"subagent:{task_id}")`。具体改法是给 `_build_tools` 加一个 `task_id` 参数；caller 在 `_run_subagent`（line 233 `tools = self._build_tools(...)`）的位置把外层闭包的 `task_id` 传进去。
  - Dream 路径：`MemoryStore.build_dream_tools()` 显式构造 `SkillManageTool(..., provenance_tag="dream")`（§6.1）。
  - 这与 M1 §6.1 决定的 `provenance_tag="dream"` 写法**完全同款**，对称、零新基础设施。**不**走 `RequestContext.metadata["subagent_task_id"]` 这条路径——虽然 `_announce_result` payload（`subagent.py:322-327`）里的 metadata 已有 `subagent_task_id` 键，但那是 inbound 注入用的，与 tool 构造无关。
- **Telemetry**：subagent 复用主进程注入的 `SkillTelemetry`（M1 §11 接口契约第 5 行"subagent 复用主 telemetry 单例"已确立）。M2 不为 subagent 单独构造 telemetry。
- **并发**：subagent 与主 agent 同进程时走同一 in-proc lock dict；跨进程时由 filelock 兜底。

这意味着主 agent 与 subagent 可同时 `edit` 不同 skill（不同 name → 不同 lock），但同 skill 串行。这是预期行为。

### 8.4 SubagentManager 不动

M1 retro item 4 的"父 telemetry 转发到 subagent 的 SubagentManager 行为"M2 直接复用，不修改任何 SubagentManager 代码。`SkillManageTool` 在 subagent 里被注入时，从 manager 已经传下来的 ctx 拿 telemetry 引用即可。

### 8.5 Durability 合同（R3 fix RED-7 —— 与 telemetry 同款原语）

所有 skill 文件写入（含 frontmatter + body）必须走与 `nanobot/agent/skills_telemetry.py:78-94` `_atomic_write` **形状一致**的原子写。**R7 fix YEL-SEC-1 / 决策 #71：mode 锁定 0o600 + 强制 cleanup-on-error**：

```python
# tmp 与最终路径同目录；nonce 用 CSPRNG（参见下方 nonce randomness 合同）
tmp = path.with_name(path.name + ".tmp." + os.urandom(8).hex())
fd = os.open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0o600)
replaced = False
try:
    try:
        os.write(fd, payload_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)            # 原子 rename
    replaced = True
finally:
    if not replaced:
        # write/fsync/replace 任一步失败 → 必须 unlink tmp，禁止留下 leftover 文件
        # 防御：partial-write 的 SKILL.md.tmp 若残留，可能含 LLM-generated 内容（agent context / operational
        # instructions），world-readable 0o644 会让本地 adversary 读取（§4.6.1 威胁模型已含 local adversary）。
        # 0o600 + 强制 unlink 双重防御。
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass  # tmp 可能已被 replace 移走或从未创建
if sys.platform != "win32":
    dir_fd = os.open(parent_dir, O_RDONLY)
    try: os.fsync(dir_fd)
    finally: os.close(dir_fd)
```

**最终 SKILL.md mode（R7 fix 决策 #71）**：tmp 文件以 `0o600` 创建；`os.replace` 不改 destination 的 inode 权限位（destination 直接 inherit tmp 的 mode）→ 持久 SKILL.md 落盘后即 `0o600`。Justification：nanobot agent workspace 是单用户场景，SKILL.md 仅由 agent 进程（同一 uid）读取，`0o600` 充分；`0o644` 让本地 adversary（§4.6.1 威胁模型已包括）可读 LLM-generated operational instructions / agent context，不必要的暴露。决策 Log #71。

**R9 fix YEL-DI-C — M1 `.telemetry.json` mode 0o644→0o600 silent transition**：M1 既有 `.telemetry.json` 文件 mode 在 lift 后由 0o644 收紧为 0o600。nanobot agent workspace 单 uid 模型下 (`~/.nanobot/...`)，无外部 reader 影响。`os.replace` 是 `rename(2)` 语义——新 inode 携带 0o600 mode 替换旧 inode 的 directory entry，故 mode 收紧透明传递到现有 `.telemetry.json` 实例（首次 lift 后写盘即生效）。如果 ops 监控脚本以异 uid 直接读 `.telemetry.json`（不经 nanobot agent 进程），需迁移到同 uid 或通过 nanobot API 读取。无 RFC 级行为变更，仅运维影响。该收紧透传到 telemetry 是 Decision #71 在 lift 路径上的必然推论；M2 不为此引入新决策，亦不在 spec 文本中保留 0o644 作为活跃 mandate（§12 carried-forward 仅作历史记录交叉引用）。

**R10 fix YEL-SEC-R9 — DI-C transition-window 精确化**：mode 收紧是**首次 lift 后写盘生效**，而非部署即生效——M2 部署到 nanobot agent 进程首次 telemetry flush 之间的窗口内，旧 `.telemetry.json` inode 仍保留 M1 写下的 0o644 mode（未被 `os.replace` 覆盖即不变）。窗口上限由首次 agent 活动决定（活跃 agent 通常 < 几秒；空闲 agent 则等到首次 telemetry 事件触发 flush）。窗口期内本地异 uid 攻击者能读到的 telemetry 内容与 M2 部署前完全一致（pre-M2 暴露），不引入新的暴露面，仅延迟 0o600 收紧的生效时机。M2 plan 不需要为该窗口引入显式迁移步骤（首次 flush 即自然收紧）。

**R4 fix YEL-11（Data-integrity YEL-A）—— flag 不一致显式化**：M1 既有 `nanobot/agent/skills_telemetry.py:78-94` `_atomic_write` 用的 flag 集是 `O_WRONLY | O_CREAT | O_TRUNC`（**未含** `O_NOFOLLOW` / `O_CLOEXEC`），与本 §8.5 要求不一致。"lift 为公共 utility"必须显式说明 lift 时是否升级 flag。

实现选项（**R6 修订（YEL-COH-1）—— Option A 锁定为 M2 路径**）：

- **Option A（M2-MANDATED — lift-and-upgrade）**：把 `_atomic_write` 从 `skills_telemetry.py` lift 到 `nanobot/agent/_atomic_io.py` 公共 utility，**同时**把 flag 升级为 `O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC`（按 §4.6.1 跨平台兼容协议用 `getattr` 兜底）。M1 telemetry 路径 `inherit` 升级后的 flag——对 telemetry 是无害收紧（telemetry tmp 文件本就在 telemetry root 内、本就不该是 symlink 也不该跨 fork 泄漏 fd）。**M2 plan MUST 选 Option A** 并满足 R5 三条 sub-conditions 作为 §10.6 acceptance gates 硬性要求。

  **`_atomic_io.py` 顶部 import 模式**：lift 后的 `_atomic_io.py` 必须把 `import fcntl` 包在 `try / except ImportError: fcntl = None` 守卫里（precedent: `nanobot/channels/msteams.py:29-32`）；`atomic_write` 不依赖 `fcntl`（Windows 可用），`fd_file_lock` 在 `fcntl is None` 时 raise `RuntimeError("fd_file_lock is POSIX-only; ...")`。完整规范见 §3.7.1 step 5 "Windows import guard" 段落与决策 #73；本节仅引用，不重复。

  **R6 锁定理由（YEL-COH-1）**：M1 telemetry 在 `skills_telemetry.py:454` 已使用 `_atomic_write`，并被 4 条现有测试 monkeypatched (`tests/agent/test_skills_telemetry.py:121, 130, 327, 337`)。选择 Option B 会让 M2 要么 (a) 与 M1 atomic-write helper 出现两份实现 drift，要么 (b) 重写这 4 条 M1 测试——两者都比 Option A 三条 back-compat sub-conditions 更糟。Option B 在 spec 文本中**仅作历史 alternative 保留**，M2 plan **不得**选择。

  **R5 fix YEL-R5-2 — back-compat shim 必备合同**：现有 M1 测试 `tests/agent/test_skills_telemetry.py:121, 130` 用 `from nanobot.agent.skills_telemetry import _atomic_write` 导入；`:327, 337` 用 `monkeypatch.setattr(st, "_atomic_write", slow_write)` 替身。Option A 必须**保留**这两条 hook，否则 M1 telemetry 测试套件会**静默断裂**（import 失败 + monkeypatch no-op）。实施合同（plan-author 必守，all three required）：

  1. **Re-export 留 module 顶层名**：`nanobot/agent/skills_telemetry.py` 顶部加 `from nanobot.agent._atomic_io import atomic_write as _atomic_write`，原 `_atomic_write` 名字继续 `from nanobot.agent.skills_telemetry import _atomic_write` 可用（`tests/agent/test_skills_telemetry.py:121, 130` 不需改）。
  2. **monkeypatch 链路保留**：`SkillTelemetry` 类内部所有写盘点 **不能**直接闭包 `_atomic_write` 为局部名（`_local = _atomic_write` + `_local(...)`），那样 `monkeypatch.setattr(st, "_atomic_write", slow_write)` 替不掉调用点。两条选 一即可：
     - **Option A.1**（推荐）：通过 module 属性间接调用 —— `from nanobot.agent import skills_telemetry as _self_module; _self_module._atomic_write(...)`；monkeypatch 改 `_self_module._atomic_write` 即生效。
     - **Option A.2**：把写盘动作抽成实例方法 `def _atomic_write(self, ...): from . import skills_telemetry as st; st._atomic_write(...)`；monkeypatch `st._atomic_write` 同样穿透。
  3. **M2 acceptance gate**：`pytest tests/agent/test_skills_telemetry.py` 在 lift 之后**全套通过**，**不**修改任何测试代码。这是 M2 的硬性 acceptance 条件——参见 §10 R5 增补"Option A acceptance: 完整 M1 telemetry 测试套件 lift 后无需改动通过"。

- **Option B（NOT endorsed for M2 — historical alternative only）**：保留 M1 telemetry 既有 bare flag 不动，`skill_manage.py` 用独立的强化版本；产生两份 atomic-write 实现 drift。**R6（YEL-COH-1）明确不接受为 M2 路径**——保留在文档中仅作 R3→R6 演进史与 alternative-considered 记录。M2 plan 选择 Option B 即为破契约，drift-check 必报错。

Option A 要求：

- `O_NOFOLLOW`（与 §4.6.1 路径逃逸防御呼应；Windows fallback 见 §4.6.1）。
- fsync(fd) → os.replace → fsync(parent_dir)（POSIX 上）。
- **同目录 tmp**：tmp 文件 `path.with_name(path.name + ".tmp.<pid>.<nonce>")` 强制与最终路径**同目录**，避免跨 fs 让 `os.replace` 退化为非原子（Data-integrity YEL-B：cross-fs `os.replace` 不原子）。`<pid> + <nonce>` 即使在同一 per-name filelock 持有期内也防御 `multiprocessing.spawn` 测试场景的偶发名碰撞。
- **Nonce randomness（R5 fix YEL-R5-6 — Security B；R6 YEL-SCO-4 修订）**：`<nonce>` **必须**用 cryptographically unpredictable source (CSPRNG)。可接受实现：`secrets.token_hex(8)` 或 `os.urandom(8).hex()`（均产生 16 hex chars）。**禁止**任何可预测来源：`time.monotonic_ns` / `time.time_ns` / `random.randint` / 进程内序列计数器（`itertools.count`）一律 forbidden。理由：Windows 缺 `O_NOFOLLOW`、§4.6.1 走 `is_symlink` 预检 + resolve 兜底——预检与 `os.open` 之间存在 TOCTOU window；攻击者若能预测 tmp 文件名，可在 window 内于该路径预放 symlink 把 tmp 写入重定向到外部目标。CSPRNG 让 tmp 名不可预测，关闭这条预测路径。
  - 静态扫描 / code review gate：实现源码必须使用 CSPRNG（`secrets.token_hex` 或 `os.urandom(...).hex()`）；`grep -E "random\.|time\.(monotonic|time)_ns|itertools\.count" <atomic_write_module>` 在 nonce 取数行附近不应命中（M2 plan acceptance gate）。不强制单一符号。
  - §10.6 既有 atomic-write tmp-uniqueness 测试增补 R5 nonce-quality assert：连续 100 次调用 atomic-write，收集所有 nonce → assert 全 distinct + 不可解释为序列递增（详见 §10.6 R5 增补 "Atomic-write nonce 强随机"）。
- **跨 tier 不承诺事务性**：skill body 在 `<workspace>/skills/agent/<name>/SKILL.md`，telemetry 在 `<workspace>/skills/.telemetry.json`——两路径在不同子树下；若 user 用 mount 把 `<workspace>/skills/agent/` 挂到不同 fs，两个文件各自的 atomic-write 仍成立，但**不**承诺"skill body + telemetry 一起原子可见"。M1 reconcile 在重启路径自愈不一致。
- EBUSY / EACCES / ENOSPC / EIO 等任意 IO 错误 → `error_code = "ATOMIC_WRITE_FAILED"`，**禁止**部分写盘后 fall-through。
- 失败路径不 bump telemetry（§7.3）。

**契约边界（R6 fix YEL-DI-3）**：lifted `_atomic_io.atomic_write` 必须在 helper 内部执行 `fsync(parent_dir)`（POSIX；Windows 跳过）；调用方 MUST NOT 把这一步外部化。重新实现的 caller 走任何替代路径都构成 §10.6 acceptance gate 失败——helper 必须 own 完整 durability sequence (`fsync(fd) → os.replace → fsync(parent_dir)`)，把任何一步外移即破合同。

决策 Log #57 + 决策 Log #65（R6 改判：Option A 锁定为 M2 必选；详见 §13.A superseded notes）。

### 8.6 锁顺序合同（R3 fix YEL-4）

进程内可能同时有 telemetry 写盘 + skill_manage 写盘的代码路径（例如：skill_manage 持 `_skill_inproc_locks[name]` 期间，自己 bump telemetry → telemetry 内部取 `_flush_lock`）。为避免任何死锁，**全项目**强制锁获取顺序：

0. **skill_manage workspace create-lock**（`<workspace>/skills/agent/.create.lock`，skill filelock — 实现见 §3.7.1 step 5 `fd_file_lock`；**仅** `create` verb 取，§3.7 R4 RED-1 fix）
1. **skill_manage in-proc lock**（`_skill_inproc_locks[name]: threading.Lock`）
2. **skill_manage filelock**（`<workspace>/skills/agent/<name>/.lock`，skill filelock — 实现见 §3.7.1 step 5 `fd_file_lock`）
3. **telemetry `_flush_lock`**（`threading.Lock`，M1 §4.3）
4. **telemetry filelock**（`<workspace>/skills/.telemetry.json.lock`，M1 §4.3 — **直接使用 `filelock.FileLock` 库**，详见下方 layer-4 范围说明）

释放反序。skill_manage 持 1+2 期间允许同步调 telemetry bump（telemetry 内部按 3+4 序进出，与 1+2 不冲突）。`create` 路径同时持 0+1+2 是合法序；非 create verb（edit/patch/delete）**禁止**取 0。

绝对禁止：

- skill_manage 持 1+2 时主动 acquire 4 之外的另一把 telemetry lock（不存在的反向取序）。
- telemetry 内部主动 acquire 0 / 1 / 2（telemetry 不感知 skill_manage 存在）。
- 非 create verb 取 0（破坏顺序的"create 是 0 的唯一 acquirer"前提；edit/patch/delete 路径不需要 workspace-级互斥）。

决策 Log #58（M1）+ Log #60（R4 加入第 0 层）。

#### Layer-4 telemetry filelock 范围说明（R8 fix YEL-DI-1）

Layer 4（telemetry filelock）继续直接使用 `filelock.FileLock` 库（M1 强度，未做 fd-mode lock 加固）；其 lock-path symlink 攻击防御差距是 M1 遗留债务，**不在 M2 范围内**。M2 `fd_file_lock` 强制要求只覆盖 Layer 0（workspace `.create.lock`）和 Layer 2（per-skill `<name>/.lock`），**不回头加固 telemetry 层**。后续若决定加固，统一在 M3 Curator 工作中处理（届时若 Curator 引入新的 telemetry 写入路径，重新评估）。

### 8.7 ContextBuilder cache 边界（R3 fix YEL-5 —— mid-turn 写不污染 prompt cache）

`ContextBuilder.build_system_prompt()`（`nanobot/agent/context.py:80-...`）在每个 turn 起点**重新**调用 `self.skills.load_skills_for_context(...)` + `self.skills.build_skills_summary(...)` 重建 system prompt 各段。`SkillsLoader` 本身**无内部 caching**——每次 list_skills / load_skills_for_context 都是 fresh 目录扫描 + frontmatter 解析。

合同：

- mid-turn 调 `skill_manage create/edit/patch/delete` → 磁盘已变 → 当前 turn 已在 LLM 处理中的 prompt segment **不重建**（不 invalidate 当前 cache）。这是 §9.1 "MUST NOT poke into in-flight prompt cache" 的具体落地。
- 下一个 turn 起点 ContextBuilder 重新跑 → 自然吃到新 skill 内容。
- M2 **不**给 ContextBuilder 加任何 mid-turn 重建钩子；M3 若发现需要"create skill 后立即出现在当前 turn"的体验，自己加钩子（且要重新评估 prompt cache key 一致性）。

测试网（§10.4）覆盖：构造 turn-in-progress；mid-turn create；assert build_skills_summary 在当前 turn 内不重新读盘（mock 文件读取调用次数 == turn 起点的 1 次）。

### 8.8 Ghost-dir 重建语义（R3 fix YEL-12 + R5 fix YEL-R5-1）

如果 `<workspace>/skills/agent/` 被外部进程 rmdir 后再被某 verb 触发重建（mkdir-on-first-create）：

- **mkdir-on-first-create 覆盖两层**（R5 修订澄清 YEL-R5-1）：
  - **workspace-level**：`<workspace>/skills/agent/` 父目录在 `create` verb 的 §3.7 step 1.5 通过 `os.makedirs(..., exist_ok=True)` 重建（race-safe，幂等）。这是 `<workspace>/skills/agent/.create.lock` 能被 `fd_file_lock(...)` 内部 `os.open(O_CREAT)` 成功创建的前提（§3.7.1 step 5；helper from `nanobot/agent/_atomic_io.py`）。
  - **per-name**：`<name>/` 子目录在 `create` 持 per-name 锁内的 mkdir 段重建（§4.3 verb 表 `os.makedirs(<workspace>/skills/agent/<name>/, exist_ok=True)`）。
  - 两层都用 `exist_ok=True` 保证多进程并发首次 create 时全部安全：最先完成的进程真建目录，后续 no-op。
- in-proc `_skill_inproc_locks` dict 可能仍持有旧 name 的 `threading.Lock` 对象。**这不会引发问题**：旧锁仅锁 string-key，外部路径变化与锁状态正交；下次 acquire 该 name 时旧锁正常工作。
- M1 SkillsLoader 不缓存 list_skills 结果（每次扫盘）；ContextBuilder 下一个 turn 起点自然看到新目录状态。
- M2 **不**实装 directory-watch / 主动同步逻辑；外部强制重建是 ops-level 行为，由 ContextBuilder 下次 build 自愈。
- 决策 Log #59（YEL-12）。

## 9. Cache 不变量（**关键防御**）

### 9.1 §9 不变量（决策 #41，逐字提案）

> **`skill_manage` MUST NOT poke into in-flight prompt cache; the only state mutated mid-turn is disk + telemetry counters.**

具体含义展开：

1. **磁盘**：`skill_manage` 调用结束后，`<workspace>/skills/agent/<name>/SKILL.md` 立即反映新内容（atomic write 已 fsync）。
2. **当前 turn 的 prompt segment 不变**：`ContextBuilder` 在 `nanobot/agent/context.py:104-112` 已经把 `load_skills_for_context()` 与 `build_skills_summary()` 的输出装填进当前 turn 的 prompt segment；M2 **不**回头改这两个 segment——LLM 在本 turn 看到的 skill 内容可能已"过时"，但这是 prompt cache 完整性的代价。
3. **下一 turn 自动看到**：下一次 `ContextBuilder.build()` 调用会重新走 `load_skills_for_context` → 读文件 → 注入新内容。M1 §1.1 item 6 的"WebUI 不污染计数 + 函数体内 hook"设计天然支持这一点（无 stale cache）。
4. **Dream 自然合规**：Dream 是独立 ephemeral turn——它本 turn 调 `skill_manage` 写盘后，Dream 自己也走完 turn 退出；下一次主 agent turn 自然吃到新内容；不存在"Dream mid-turn 看自己改的 skill"需求。

### 9.2 为什么这个不变量值得显式写下来

跨 milestone 共同硬性约束 #1 是 "永不打破 prompt cache"（roadmap §6.2）。M2 是第一个会 mid-turn 改文件的 milestone；不写明就会有人写出"create skill 后顺手把新内容追加到当前 turn segment"的方便代码——那会让本 turn 的 prompt segment 与 cache key 不一致，cache miss 直接成本爆炸。

### 9.3 测试断言（向 §10 引用）

- 构造 turn-in-progress 状态；mid-turn 调一次 `skill_manage create`；assert `build_skills_summary()` 返回的 string 在该 turn 内不变；assert 下次新 turn 调用返回 string 含新 skill 名。

### 9.4 turn 边界对 §5.2 rate-cap 的影响

rate-cap 计数器在每 turn 起点重置：与 cache 不变量同源——既然每 turn 是一个独立 prompt assembly 单位，跨 turn 共享计数器既不必要也违反"turn-local state per turn"的项目惯例。

## 10. 测试策略

> 本节是分类摘要，不是测试代码清单。具体 test cases 在实施 plan 阶段拆。

### 10.1 单元（unit）

- 每 verb × 每 provenance tier 的 reject/allow 矩阵全覆盖（§4.4 矩阵 4×4 = 16 case；其中 allow 只有 3 个，其余 13 个都是 reject）。
- `_validate_skill_name`：路径注入、长度边界、保留名 `agent` 拒绝、kebab-case 正则。
- `create` 写出的 SKILL.md frontmatter 包含 `origin / created_at / created_by`，body 与传入完全相等（含 trailing newline 处理）。
- `edit` 全量重写后 frontmatter 含 `last_patched_at / patched_by`；旧的 `created_at` / `created_by` 保留不变。
- `patch` 找不到 / 多次出现的 search 都 reject `search_missing` / `search_ambiguous`，不写盘、不 bump。
- `delete` 后目录消失；下次 SkillsLoader.list_skills() 不再返回该 name。
- 失败路径不 bump（构造 mock telemetry 验证 `bump` 调用次数）。
- rate-cap：第 6 次 mutation 收到 `rate_limited`；前 5 次成功 bump 5 次。

### 10.2 并发（concurrency）

- **同进程多线程**：5 个 thread 并发 `patch` 同一 skill（互不重叠的 search/replace），最终文件包含全部 5 处修改，`patches` counter 增 5。
- **多进程跨 filelock**：`multiprocessing.spawn` 起 2 个 worker 并发 `patch`，最终文件正确合并、counter 正确。worker 必须 top-level fn + 显式接收 workspace 路径（与 M1 §8.1 多进程测试同款约束）。
- **filelock 超时降级**：mock filelock 始终超时，调用返回 `concurrency_timeout`，文件不变。

### 10.3 集成（integration）

- **闭环 1**：`create("foo", body="...")` → SkillsLoader.list_skills() 含 "foo" → `edit("foo", body="...")` → 文件内容变更 + `last_patched_at` 写入 → `delete("foo")` → SkillsLoader 不再列出。
- **闭环 2 (reconcile 衔接)**：`create("bar")` → 主 agent turn end flush telemetry → 下次进程启动 reconcile 看到新 skill → 写零计数条目 + `origin="agent"`。
- **闭环 3 (orphan 清理)**：`create("baz")` → reconcile 写条目 → `delete("baz")` → 下次 reconcile 把条目移除。

### 10.4 Cache 稳定性（cache invariance）

- 模拟 turn-in-progress：构造 ContextBuilder + 已装填 skills_summary；mid-turn 调 `skill_manage create("new-skill")`；assert `build_skills_summary()` 在本 turn 内 segment 不变（or 不重新调用）；下个 turn 起点重新 build 后含新 skill。

### 10.5 Dream 端到端（dream e2e）

- Mock provider；触发 Dream 周期；Dream 调 `skill_manage create`；落盘的 SKILL.md frontmatter `created_by == "dream"`；telemetry view/use bump 不被该 dream turn 触发（Dream 走自己 ToolRegistry，无 ContextBuilder.build_skills_summary 路径）。

### 10.6 R3 新增测试网（R3 fix YEL-8）

针对 R3 引入的防御措施补齐 test gates，每条独立验证。本节 R5-2 / R5-5 / R5-6 gates 全部假设 §8.5 Option A 已锁定为 M2 路径（见 YEL-COH-1 决议；R6 起 Option A 为 M2-mandated，R5 conditional 全部退化为 unconditional gates）。

#### 路径逃逸防御（RED-4）

- 在 `<workspace>/skills/agent/foo` 预先放 symlink → `/etc/passwd`；调 `edit("foo", body=...)` → reject `error_code == "PATH_ESCAPE"`，目标 symlink 不被改动。
- name 含 `..` / `/` → §4.6 `invalid_name`（symlink 测试不替代 name 校验测试）。
- 解析后路径中间节点是 symlink 但 target 仍在 `skills_agent_root` 内 → allow（合法的内部组织）。

#### case-fold 唯一性（RED-5）

- 先 `create("foo", ...)` 成功；再 `create("Foo", ...)` → reject `error_code == "name_collision"`；磁盘上仍只有 `foo/`（macOS / Linux 行为对称）。
- agent `create("Foo")` 时 user 层已有 `<workspace>/skills/foo/` → reject `name_collision`。

#### 配额（RED-9）

- body 65537 字节 `create` → reject `BODY_TOO_LARGE`，磁盘无残留。
- workspace 已有 200 agent skills → 第 201 次 `create` → reject `TOO_MANY_AGENT_SKILLS`。
- description 281 字符 → reject `DESCRIPTION_TOO_LONG`。
- 每条 reject 路径 assert telemetry **未** bump。

#### rate-cap（R4 fix YEL-10 — 单 int 实现）

- 一个 turn 内连续 5 次 `create`（不同 name） → 第 6 次 `create` 返回 `rate_limited`（任意 verb 之和 ≥ 5）。
- 一个 turn 内 3 次 `create` + 2 次 `edit` → 第 6 次任意 verb → `rate_limited`；assert `_runtime_vars["skill_manage.mutations_this_turn"] == 5`。
- 下一 iteration 顶部计数器重置为 0；前 iteration 用满后下 iteration 仍可 5 次。
- **同步性测试**：构造两个并行 asyncio task 同 iteration 各调 `skill_manage create`，初始 counter=4；assert 必有恰好一个收到 `rate_limited`、另一个成功（不能两个都成功）。

#### subagent budget 隔离（YEL-11）

- 父 agent turn 内已 mutate 4 次 → spawn subagent → subagent turn 内成功 5 次（独立配额） → 父 agent 后续 turn 配额仍是 reset 后的 5 次。
- 嵌套 subagent：父 → child → grandchild，三层各独立 5 次配额。

#### task_id 校验（RED-6）

- 构造 `provenance_tag = "subagent:abc-123"` → 工具构造成功。
- 构造 `provenance_tag = "subagent:\n---\nfoo: bar"` → `__init__` 抛 `ValueError`（工具不允许构造）。
- 构造 `provenance_tag = "subagent:" + "x" * 65` → `ValueError`。

#### atomic-write 失败路径（RED-7；R7 SEC-1 强化）

- mock `os.replace` 抛 OSError → tool 返回 `ATOMIC_WRITE_FAILED`；assert 磁盘 `SKILL.md` 内容**未变**（前一次成功的状态被保留），且 **`SKILL.md.tmp.*` 已被 unlink**（不留 leftover；R7 强制）。
- mock `os.fsync` 抛 OSError → 同上。
- mock `os.write` 在写出部分字节后抛 → assert tmp 已 unlink（防 partial-write 内容残留磁盘）。
- assert 持久 SKILL.md 文件 stat mode 为 `0o600`（R7 决策 #71：tmp 0o600 → replace inherit → final 0o600）。

#### dot-leading 名（YEL-10）

- `create(".lock", ...)` / `create(".gitignore", ...)` / `create(".DS_Store", ...)` → reject `invalid_name`。

#### shadow primitive（RED-11）

- workspace 同时有 user 层 `foo` + agent 层 `foo`（M1 collision warning）→ `edit("foo", ...)` → reject `tier_locked`（effective_origin == "user"）；assert 走的是 `list_skills_with_shadows()` 路径（mock 调用次数）。
- 仅 agent 层 `foo`（无 shadow）→ `edit("foo", ...)` → allow。

#### lock-ordering 死锁回归（YEL-4）

- 单 process 双线程：thread A 走 skill_manage 持锁后 bump telemetry；thread B 走 telemetry-only 路径 bump 同一 entry。assert 两线程各自完成（无死锁），最终文件与 telemetry 状态一致。

#### Cache 不变量（YEL-5）

- 构造 turn-in-progress 状态：调 `ContextBuilder.build_system_prompt()` 拿到 prompt P1；不结束 turn，立即调 `skill_manage create("new-skill")`；assert 同 turn 内不重新 build；下一个 turn 调 build → P2 内容含 "new-skill"，P1 ≠ P2。

#### workspace create-lock quota 一致性（R4 RED-1 — Security RED-1 + Data-integrity YEL-D）

- workspace 已有 199 agent skills；并发 2 个进程各调 `create("a")` / `create("b")`：第一个 acquire create-lock 成功落盘后释放；第二个看到 count=200 → reject `TOO_MANY_AGENT_SKILLS`。最终目录恰好 200 个 skill，**不**为 201。
- create-lock 持锁中 acquire per-name lock 不死锁（§8.6 锁序 0→1→2 verify）。
- delete / edit / patch verb 不触 create-lock（mock create-lock acquire；assert 这三 verb 不调用之）。

#### delete tombstone 重用清零（R4 YEL-17 — Data-integrity YEL-H）

- `create("foo")` → bump `view`/`use` 让 `entry.uses=3` → `delete("foo")` → reconcile 之前立即 `create("foo")`（同名 reuse）→ reconcile 后 `entry.uses == 0`、`entry_created_at` 是新时间戳。
- `create("bar")` → `delete("bar")` → reconcile（无 reuse）→ entry 物理消失（保持 M1 invariant 4 不破）。
- bump `kind="delete"` 后 entry `tombstone == True`；老 reader `.get("tombstone", False)` 不报错。

#### YAML round-trip 合同（R4 YEL-13）

- frontmatter 含人工注释 `# pinned by ops` → `edit` 后注释丢失（acceptable for agent-tier）。
- frontmatter 单引号字符串值 → `edit` 后双引号或反之（解析等价 but text drift），assert `yaml.safe_load(new) == yaml.safe_load(old) + mutation`。

#### atomic-write tmp 文件名（R4 YEL-11）

- 同进程内并行两次 atomic-write（mock per-name lock 让两次都进入临界）→ assert 两个 tmp 文件名不冲突（`pid + nonce` 区分）。
- tmp 文件目录与最终路径同目录（assert `os.path.dirname(tmp) == os.path.dirname(path)`）。

#### Increment-and-check 同步性（R4 YEL-14）

- 两个并行 asyncio task 同 iteration 各调 `skill_manage create`，初始 counter=4：assert 必有恰好一个收到 `rate_limited`、另一个成功（不能两个都成功）。
- assert rate-cap 函数体内无 `await`（静态扫描或 manual code review gate）。

#### `_atomic_write` lift back-compat（R5 YEL-R5-2 — Option A acceptance gate）

- 若 plan-author 选择 §8.5 Option A（lift-and-upgrade），完整 M1 telemetry 测试套件 `tests/agent/test_skills_telemetry.py` 必须**无需修改**通过。具体 assert：
  - `from nanobot.agent.skills_telemetry import _atomic_write` 解析成功（re-export 在位）。
  - `monkeypatch.setattr(st, "_atomic_write", slow_write)` 在 `tests/agent/test_skills_telemetry.py:327, 337` 现有用法下仍能拦截 `SkillTelemetry` 类内部写盘动作（实例方法或 module-attribute 间接调用 hook 在位）。
  - 完整套件 `pytest tests/agent/test_skills_telemetry.py -v` exit code 0。
- R6 注：Option B 已被 §8.5 / YEL-COH-1 明确禁止为 M2 路径，故本 gate 在 R6 起为 unconditional 硬性要求。

#### Lock-path symlink defense（R5 YEL-R5-5 — Security A）

- 在 `<workspace>/skills/agent/.create.lock` 路径上预置 symlink → `/tmp/attacker_target` → 调 `create("foo", ...)` → reject `error_code == "PATH_ESCAPE"`，filelock 未被 acquire，攻击目标文件未被触碰。
- 在 `<workspace>/skills/agent/<name>/.lock` 路径上预置 symlink → 调 `edit("<name>", ...)` → reject `PATH_ESCAPE`。
- 合法路径（无 symlink）→ acquire 成功、verb 正常完成。

#### `fd_file_lock` 异常路径与 fd-lifecycle（R7 YEL-FEAS-4 + YEL-DI-1）

- raise inside `with fd_file_lock(path) as fd:` 块 → exit 后 assert：(a) lock 已释放（开新子进程对同 path 调 `fcntl.flock(fd2, LOCK_EX | LOCK_NB)` 立即成功，无 BlockingIOError）；(b) fd 已 close（Linux 上 `os.path.exists(f"/proc/self/fd/{fd}")` 返回 False；跨平台兜底：尝试 `os.fstat(fd)` 抛 `OSError(EBADF)`）。
- 嵌套 `with fd_file_lock(create_lock) as fd1: with fd_file_lock(name_lock) as fd2:` 内层抛异常 → 退出顺序 LIFO：assert 内层 lock 先释放、内层 fd 先 close，然后外层；两层最终都释放干净。
- per-name lock-fd open 时并发删除 `<name>/` 触发 ENOENT → `fd_file_lock` raise 让上层（`edit/patch/delete`）按 §3.7.1 step 6 errno map 译为 `error_code == "not_found"`（不是 `ATOMIC_WRITE_FAILED`）。
- `fcntl.flock` retry-loop 超时（构造长持锁的另一进程压住）→ `error_code == "concurrency_timeout"`，fd 已 close，无 fd 泄漏。

#### Per-verb errno 映射（R7 YEL-FEAS-3）

- mock `os.open(<name>/.lock)` 抛 `OSError(errno.ENOENT)` 在 `edit/patch/delete` 路径 → `error_code == "not_found"`。
- mock `os.open(<name>/.lock)` 抛 `OSError(errno.EACCES)` → `error_code == "ATOMIC_WRITE_FAILED"`。
- mock `os.open(<name>/.lock)` 抛 `OSError(errno.ELOOP)` → `error_code == "PATH_ESCAPE"`（symlink defense 兜底）。

#### Atomic-write nonce 强随机（R5 YEL-R5-6 — Security B；R6 YEL-SCO-4 修订）

- 连续调 atomic-write 100 次（mock 同一 target path，无锁阻塞）→ 收集 100 个 tmp 文件名 → assert 100 个 nonce 全部 distinct。
- 取相邻两次 nonce → assert 不可解释为顺序递增（`int(nonce_n+1, 16) - int(nonce_n, 16) != 1`）。
- nonce 来源 MUST 是 cryptographically unpredictable (CSPRNG)；可接受实现包括 `secrets.token_hex(8)` 或 `os.urandom(8).hex()`。Code-review gate 检查不使用 `time.time()` / `time.monotonic_ns()` / `random.*` / 序列计数器（`itertools.count`）；不强制单一符号。

#### `_atomic_io.py` Windows import guard（R8-1 fix YEL-FEAS-NEW-1 — 决策 #73）

- **R8-1**：`python -c "import nanobot.agent._atomic_io"` 在 Windows CI 或本地 Windows 容器上必须成功（不抛 `ImportError`）。验证 `import fcntl` 走 try/except 守卫且 `atomic_write` 不依赖 `fcntl`，Windows nanobot 启动路径（`skills_telemetry.py` 顶部 `from nanobot.agent._atomic_io import atomic_write as _atomic_write`）在无 `fcntl` 平台仍可 import。
- **R8-1b**（R9 fix YEL-DI-D — `atomic_write` Windows e2e）：Windows 上调用 `from nanobot.agent._atomic_io import atomic_write; atomic_write(tmp_path / "t.json", b'{"k":"v"}')` 必须成功（文件落盘且内容可解析），不抛任何异常。覆盖 "`atomic_write` 函数体内不含未守卫的 `fcntl.*` 调用" 这一隐式合同。R8-1 检查 import 不抛 `ImportError`；R8-1b 检查首次实际调用不抛 `AttributeError`（`fcntl is None` 误用）；两者必须**同时**通过。
- **R8-2**：在 Windows 上 `from nanobot.agent._atomic_io import fd_file_lock; fd_file_lock(p)` 必须 raise `RuntimeError("fd_file_lock is POSIX-only; Windows must take a different path")`（不是 `AttributeError: 'NoneType' object has no attribute 'flock'` 一类隐式错误）。
- **R9-1**（R9 fix YEL-SEC-C — telemetry tmp cleanup gate post-lift）：模拟 telemetry flush 写失败 — monkeypatch `os.replace` 在写 `.telemetry.json` 时抛 `OSError`；调用一次 telemetry flush；断言 `.telemetry.json.tmp.*` 残留**不存在**（cleanup-on-error 的 `unlink(tmp)` 已经透过 §8.5 lift 后的 re-export 链路传播到 M1 telemetry caller）。覆盖 §8.5 + 决策 #71 的 "mandatory unlink-on-error" 合同对 lift 后的 telemetry 写路径同样有效——防止 partial-write tmp（含 LLM-generated payload）以 0o600 残留但仍占用 inode / 跨重启泄漏。
- **验证机制（R9 fix YEL-FEAS-R8-3；R10 fix YEL-FEAS-R9-1 修订）**：本仓库 `.github/workflows/ci.yml:23` 已含 `windows-latest` runner，R8-1 / R8-1b / R8-2 通过 `pytest.mark.skipif(sys.platform != "win32", reason="Windows-only guard")` 装饰的单元测试块**自动**执行（无需本地 Windows VM 手动验证；亦无需扩展 CI matrix）。R9-1 为 POSIX-only 测试，使用 `monkeypatch` 注入 `os.replace` 失败，可在 `ubuntu-latest` runner 直接跑过。M2 不引入新的 Windows CI runner，沿用既有 matrix。
- 实现见 §3.7.1 step 5 "Windows import guard" 段落；precedent reference：`nanobot/channels/msteams.py:29-32`。

## 11. M2 不做（明确留给 M3+）

按"机制-策略"切分，下面所有项都是**策略层**，被有意推迟：

1. **Curator 确定性状态机**（active / stale / archive 三态判定）。
2. **Curator 合并启发式**（"两个 skill 内容相近，合并？"）。
3. **`skill_manage --dry-run`**——M3 dry-run 是 Curator 级别的"全套审议但不落盘"，与 M2 单 verb 的 dry 不是同一概念。
4. **`/curator` slash 命令** + WebUI 入口。
5. **Protect-list / pin / cooldown** 配置项（防止 Curator 删 user 钉住的 skill）。
6. **Aux-model 审议**（用 M1 §6 引入的 auxiliary provider 在 Curator Phase 2 跑 LLM-as-judge 决定保留/归档）。
7. **Telemetry 驱动的 `skill_manage` 自动建议**（"看到 N 次 view 但 0 次 use → 建议 archive 该 skill"）。
8. **Dream 中 `WriteFileTool(skills_dir)` / `EditFileTool` / `ApplyPatchTool` 对 `skills_dir` 的写权限下线**——M2 保留为 escape hatch；M3 在 `skill_manage` 稳定后撤旧。
9. **agent → user skill 的提升机制**（"这个 agent skill 用得很好，要不要 promote 到 user 层"）。
10. **跨 subagent 的 aggregate mutation 上限**（R4 fix YEL-8 — Security YEL-3）：M2 的 `maxMutationsPerTurn=5` 是 per-iteration、per-runner-turn-context 的；N 层嵌套 subagent 总额可达 N×5。**M2 接受**这一漏洞：
    - subagent spawn 速率本身受 `nanobot/agent/subagent.py` `SubagentManager` 治理（独立子系统），属于另一层防御。
    - 在跨 subagent 共享一个 `maxMutationsPerInboundMessage` 计数器需要重新设计 inbound-message 生命周期到 RuntimeState 的绑定，M2 的 RuntimeState 模型尚未为此而设计。
    - M3 拿到 M2 实跑数据后若发现 fork-bomb-via-subagent 真实出现，可加 `maxMutationsPerInboundMessage` 配置，挂在 `AgentLoop.runtime_state` 的 `skill_manage.mutations_this_message` namespace（与 M2 `skill_manage.mutations_this_turn` 平级，不破现有契约）。
    - 决策 Log #64。

> 任何上述项混入 M2 实施 plan 都视为 scope creep；plan-reviewer 必须 reject。

## 12. Carried-forward debt（M2 显式留给 M3+ 的债务）

- **`create` 后 reconcile 之前的 telemetry origin "unknown" 窗口**：详见 §7.2 第 1 段。下次 reconcile 修正。M3 若需要 immediate consistency，自己加路径。
- **`delete` 后 reconcile 之前的 stale entry 窗口**：详见 §7.2 末段 carried-forward block。
- **`MemoryStore.__init__` 新加 `telemetry` keyword 参数**：是 minimal 改动；M3 如果让 MemoryStore 走更深的 SkillsLoader 注入路径（例如 Dream 也走 ContextBuilder.build_skills_summary 计 view），可能要再扩 init 签名。
- **`SkillManageConfig` schema 字段单一**（仅 `maxMutationsPerTurn`）：M3 极可能要加 `protectList: list[str]`、`cooldownSeconds: int` 等字段；扩字段时复用 §5.2 同款 camelCase alias 风格，不破 schema_version。
- **`patches` 计数器同时承载 `edit` 与 `patch` 两 verb**：决策 #37 解释了 trade-off。如果 M3 Curator 发现两 verb 频次需要分开看，必须扩 telemetry schema_version 而不是在 M2 拆 counter。
- **subagent task_id 上限调优**（R4 fix RED-2 — 早期 R3 spec 误称"未限制"；实际 §3.5 已硬限 64 字符）：M2 通过正则 `^[A-Za-z0-9_-]{1,64}$` 强制 task_id ≤ 64 字符；当前 SubagentManager 实际生成 8-hex (UUID 前缀)，远低于上限。M3 拿到真实 telemetry 后可决定收紧（≤ 32 字符更紧凑）或放宽（≤ 128 适配深嵌套 task_id 链路）；本字段是 future tunable，不是 unbounded 漏洞。
- **rate-cap 阈值 fixed default = 5**：未基于 telemetry 数据验证。M3 拿到 M2 实跑数据后可调整 default 或加自适应。
- **本 spec 不写代码 / 不锁数据流的边界条件**：例如 LLM 一次 tool_call 同时含 `verb=create` + `verb=edit` 的 batched 调用 schema —— M2 单次 tool_call 仅一个 verb；如果 M3 要求 batch，加新 verb `batch` 而不是改本 spec。
- **bump-flush crash window（YEL-9）**：M1 telemetry 已知 ≤200ms 的 in-memory bump 未 flush 窗口；M2 不引入新的耐久性保证。skill 文件本身的 atomic-write（§8.5）独立于 telemetry，bump 丢失不影响 skill 文件已落盘的事实。M3 若需要更强 RPO，自己加 sync-bump 路径。
- **`task_id` 字符串长度未限制**（已被 R3 §3.5 部分缓解）：M2 校验 ≤ 64 字符；frontmatter `created_by = "subagent:<8-hex>"` 当前实际是 17 字符，远低于上限。M3 引入 deep-nested subagent / 累积 task_id 时再考虑 hash 化。
- **配额阈值**未基于 telemetry 数据验证：`maxBodyBytes=64KiB` / `maxAgentSkills=200` / `maxDescriptionLen=280` 都是基于直觉的初值。M3 拿到 M2 实跑数据后可调整 default 或加自适应。
- **tombstone marker 是 lower-bound, not exactly-once**（R6 fix YEL-DI-2）：§4.3 step 5.5 承诺"防止 delete 后 reuse 同 name → 旧 telemetry counter 被新 skill 误继承"，但该承诺受限于 M1 已记录的 bump-flush ≤200ms 崩溃窗口（继承 YEL-9 / YEL-G）。若 process A bump `kind=delete` 后崩溃于 flush 前，tombstone 标记丢失，process B reuse-create 不会触发 reconcile zero。M3 reconcile 必须把 reuse-create 上的 counter 继承当作 known imprecision 处理（不能 alarm），M3 Curator 设计阶段评估是否值得为 delete-bump 路径单独同步 fsync。
- **Windows lock-path symlink defense**（R7 fix YEL-FEAS-2 — Security YEL）：M2 lock-path symlink defense（§3.7.1）是 **POSIX-only**。Windows 缺 `os.O_NOFOLLOW` + 无 `fcntl`，`filelock.WindowsFileLock` 用 `msvcrt.locking` 接收 path string 仍 follows symlinks；M2 Windows 路径仅用 `is_symlink` precheck + `Path.resolve(strict=True).is_relative_to(...)` 兜底，TOCTOU window 仍存在。Justification：nanobot 主部署目标为 POSIX，Windows multiprocess + symlink combined attack 在单用户开发者场景非现实威胁。M3 Curator 可用 Windows-specific `CreateFile(FILE_FLAG_OPEN_REPARSE_POINT)`-equivalent 子类（或重新评估 `WindowsFileLock` 子类化）关闭。
- **Telemetry layer-4 filelock 符号链接防御**（R8 fix YEL-DI-1）：§8.6 layer 4 telemetry filelock 继续直接使用 `filelock.FileLock` 库（M1 强度），未做 fd-mode lock 加固。Lock-path symlink 攻击对 telemetry 仍开放——M1 遗留债务，M2 不回填（M2 `fd_file_lock` 仅覆盖 layer 0 / layer 2 skill 锁）。若 M3 Curator 引入新的 telemetry 写入路径（增加攻击面或 telemetry 文件成为更高价值目标），重新评估并在 M3 范围内决定是否把 telemetry 锁切到 `fd_file_lock`。
- **edit/patch crash window between atomic-replace and telemetry bump**（R4 fix YEL-16 — Data-integrity YEL-G）：§4.4 step 5（atomic-replace 已完成）与 step 6（telemetry bump）之间若进程 crash，文件已显示新状态但 `entry.patches` counter **不会**增加这一次。frontmatter `last_patched_at` 仍提供"该事件曾发生"的证据。M3 Curator **必须**把 `entry.patches` counter 视为**下界 (LOWER-BOUND)**而非精确事件计数；不得用"`patches < N` 判定 skill 静止"这种依赖精确性的启发式。与 §7.2 carried-forward 2（bump-flush window）是不同的 crash window：YEL-G 是文件已落盘但 bump 调用未执行；7.2 是 bump 调用已执行但 in-memory 计数器未 flush。两类窗口都让 telemetry 成为 lower-bound 信号。

## 13. 决策日志

| # | 日期 | 决策 | 选项 | 理由（简） |
|---|---|---|---|---|
| 37 | 2026-06-11 | `edit` 与 `patch` 两 verb 共存，**不**合并为单 patch + 空 search | A: 共存（采纳）/ B: 合并 | 失败模式语义错位 + telemetry 信号清洁 + LLM 表意（详见 §4.3） |
| 38 | 2026-06-11 | 单文件 `nanobot/agent/tools/skill_manage.py` 容纳所有 verb | A: 单文件（采纳）/ B: 4 文件分 verb | tool registry 一个入口；prompt cache 友好；~400 LOC 可控 |
| 39 | 2026-06-11 | 失败路径**全部**不 bump telemetry（含 validation / reject / lock timeout / rate_limit / IO error） | A: 静默（采纳）/ B: 记 `failed_attempts` 计数 | M1 telemetry 是"事件流计数器"，失败不构成事件；记失败留给 M3 操作日志 |
| 40 | 2026-06-11 | subagent 与主 agent 共用 `<workspace>/skills/agent/`，单一 namespace；血缘记录在 `created_by = "subagent:<task_id>"` | A: 共用 + 血缘标签（采纳）/ B: subagent 单独子目录 | 不污染 SkillsLoader scan；血缘可追溯；M1 §11 接口契约已锁 telemetry 单例复用 |
| 40a | 2026-06-11 (round 2) | subagent 的 `provenance_tag` 在 **registry-build 时**通过 `SkillManageTool` 构造参数注入（参见 §8.3），**不**扩 `RequestContext` | A: 构造时注入（采纳，与 Dream 路径同款）/ B: 扩 `RequestContext.metadata["subagent_task_id"]` 由工具读取 | 与 §6.1 Dream `provenance_tag="dream"` 写法对称；零基础设施改动；`RequestContext` 保持 5 字段 frozen dataclass 不动 |
| 41 | 2026-06-11 | `skill_manage` MUST NOT poke into in-flight prompt cache | A: 不动 cache（采纳）/ B: 写完顺手刷 cache | 跨 milestone 硬性约束 #1（roadmap §6.2）；下次 turn 重 build 已自然刷新 |
| 42 | 2026-06-11 | runaway-edit 保护用 rate-cap，default 5/turn，配置 `agents.defaults.skillManage.maxMutationsPerTurn` | A: rate-cap（采纳）/ B: 不限制 / C: telemetry-driven | 机制层保护，策略阈值由 user 调；不限制会让 LLM 一 turn 内可能 patch 50 次 |
| 43 | 2026-06-11 | Dream 工具笼**追加** `SkillManageTool`，**保留** `WriteFileTool / EditFileTool / ApplyPatchTool` 作 escape hatch | A: 追加保留（采纳）/ B: 替换 | M2 不撤旧；撤旧是 M3 cleanup（§11 item 8） |
| 44 | 2026-06-11 | 新增 frontmatter 字段 `last_patched_at` / `patched_by` / `created_by` 全部 optional；不 bump telemetry schema_version | A: 全 optional（采纳）/ B: 强制 / C: 改 telemetry schema | 与 M1 §4.1 forward-compat 透传规则一致；写入侧 M2 永远填，读取侧 M3+ 用 `.get(key)` |
| 45 | 2026-06-11 | `provenance.origin` 仍只能写 `"agent"`；不引入新 origin 值（如 `"dream"`） | A: origin=agent + created_by=dream（采纳）/ B: origin=dream | M1 origin 三值 `user/agent/builtin` 已锁；新增 origin 值会破 M1 §3.1 enum |
| 46 | 2026-06-11 (R3) | `provenance_tag` 通过 `ToolContext.provenance_tag` 字段注入，不走 closure / RuntimeState | A: 扩 ToolContext（采纳） / B: post-load registry.replace / C: RuntimeState 每次读 | ToolLoader entry_points 路径无 closure 钩子；扩 ToolContext 是最小破坏（带默认值，向后兼容）；详见 §4.2 |
| 47 | 2026-06-11 (R3) | `task_id` 在 `SkillManageTool.__init__` 校验（`^[A-Za-z0-9_-]{1,64}$` + `re.ASCII`），不在 YAML 序列化期校验 | A: 工具表面（采纳） / B: serialize 时转义 | 信任边界设在工具表面；防御未来代码改动绕过 yaml.safe_dump |
| 48 | 2026-06-11 (R3) | `edit` 实现层是 in-memory 重组 + atomic 整体替换，禁止 in-place mutate | A: in-memory full（采纳） / B: in-place sed | crash-mid-write 不留 partial 文件；与 patch 共享同一 pipeline |
| 49 | 2026-06-11 (R3) | shadow 检查走 M1 提供的 `list_skills_with_shadows()`，不走 `_infer_origin_from_path` | A: list_skills_with_shadows（采纳）/ B: per-path lexical | 后者对 cross-tier shadow 无感知，会让 user 影子 agent 时误放行 edit |
| 50 | 2026-06-11 (R3) | delete 协议改为全程持双锁、单点释放 | A: full-hold（采纳）/ B: R2 mid-flow release | 消除 step 5-6 之间 `.lock` race；`.lock` 留下来无害 |
| 51 | 2026-06-11 (R3) | name case-fold 跨 tier 唯一性必须在 create 时校验 | A: 全 tier casefold（采纳）/ B: 仅 agent tier | 防 macOS/NTFS case-insensitive FS 上 `Foo` shadow `foo` 的 spooky-action |
| 52 | 2026-06-11 (R3) | 硬性配额（body / count / description）在锁路径之前 cheap reject | A: 早 reject（采纳）/ B: 锁内校验 | LLM 不能用 quota 探测做 timing 攻击；早 reject 不抢 lock |
| 53 | 2026-06-11 (R3) | 路径解析 `O_NOFOLLOW` + `Path.resolve(strict=True)` + `is_relative_to` 三合一 | A: 三合一（采纳）/ B: 仅 resolve | 单纯 resolve 不防预置 symlink；O_NOFOLLOW 是 syscall 级守护 |
| 54 | 2026-06-11 (R3) | `error_code` 枚举为 additive-extensible 契约 | A: freeze（采纳）/ B: 允许 M3 重命名 | M3 Curator 已基于现有 code 编程；改名等于破契约 |
| 56 | 2026-06-11 (R3) | Dream 写出的 skill 标记为 best-effort non-authoritative tier | A: 显式 prior（采纳）/ B: 与主 agent 等价 | Dream context 信噪比低；M3 Curator 应优先 prune Dream-only skill |
| 57 | 2026-06-11 (R3) | atomic write 用 `_atomic_write` 同款合同（fsync(fd)→replace→fsync(parent_dir)） | A: 复用合同（采纳）/ B: 简化为 write+rename | 与 telemetry 单一 durability 合同对齐；防 crash-mid-write 半截 SKILL.md |
| 58 | 2026-06-11 (R3) | 全项目锁顺序：skill in-proc → skill filelock → telemetry _flush_lock → telemetry filelock | A: 固定序（采纳）/ B: 各自独立 | 防死锁；skill_manage bump telemetry 是合法路径，必须有全局序 |
| 59 | 2026-06-11 (R3) | ghost-dir 重建不加 directory-watch，由 ContextBuilder 下次 build 自愈 | A: passive（采纳）/ B: 主动 watch | M2 不引入新基础设施；in-proc lock dict 对 string-key 仍安全 |
| 60 | 2026-06-11 (R4) | `maxAgentSkills` 用 workspace-level filelock `<workspace>/skills/agent/.create.lock` 保证 cap | A: workspace create-lock（采纳）/ B: per-name lock 内 re-check / C: soft cap | per-name lock 物理上无法约束全局上限；B 让 LLM 通过 fail 调用探测 cap；C 违背安全初衷 |
| 61 | 2026-06-11 (R4) | rate-cap reset 点是 `_run_core` 每 iteration 顶部，不是 `AgentRunner.run()` 入口 | A: per-iteration（采纳）/ B: per-run | per-run 让一次 inbound message 拿 max_iterations × 5 ≈ 100+ 次额度，违反 5/turn 承诺；§5.2.1 turn 定义即 1 iteration |
| 62 | 2026-06-11 (R4) | 跨 tier `name_collision` error code 接受 case-variant 探测 side-channel，不统一为 `name_exists` | A: 保留 collision 区分（采纳）/ B: 统一为 name_exists | agent 已通过 list_skills_with_shadows 看到 user-tier name；side-channel 不暴露新信息 |
| 63 | 2026-06-11 (R4) | `provenance_tag` write-once-at-construction：`SkillManageTool.create` 内仅一次读 `ToolContext.provenance_tag` 存为 `self._provenance_tag_` | A: write-once（采纳）/ B: freeze 整个 ToolContext / C: 每次写盘读 ctx | B 破坏其他 tool 对 mutable ctx 的依赖；C 让 SubagentManager 设的 tag 可被静默升级为 "agent" |
| 64 | 2026-06-11 (R4) | 跨 subagent aggregate mutation cap 留 §11 out-of-scope | A: 推迟到 M3（采纳）/ B: 加 maxMutationsPerInboundMessage | 跨 subagent 共享 counter 需要重新设计 inbound-message 生命周期到 RuntimeState 绑定，超 M2 范围 |
| 66 | 2026-06-11 (R4) | delete 路径 bump `kind="delete"` tombstone marker；reconcile 看到 tombstone 后 reuse 时清零 counter | A: tombstone（采纳）/ B: 接受 ghost telemetry inheritance | counter 错误归因危害大；tombstone 是 schema-additive 字段，不破 M1 invariant 4 / schema_version |
| 67-A | 2026-06-11 (R5; R6 amended) | filelock 路径自身（`<workspace>/skills/agent/.create.lock` 与 `<name>/.lock`）的 symlink-defense | A: `is_symlink` precheck + `os.open(O_NOFOLLOW)` fd-mode lock（R6 采纳） / B: 信任 filelock 内部 fd 路径处理（R5 误判，R6 拒绝） | 攻击者预置的 lock-path symlink 让 advisory lock 落到 workspace 之外，跨进程互斥失效；预检（fast-path）+ 内核 `O_NOFOLLOW`（syscall-level final guard）构成真 defense-in-depth。R6 修订：`filelock.UnixFileLock` 实测 follows symlinks，R5 关于 filelock 内部 O_NOFOLLOW 的描述错误；M2 plan 必须自行 `os.open(O_NOFOLLOW)` 取 fd 后委托（详见 §3.7.1）|
| 68 | 2026-06-11 (R6) | §8.5 atomic-write helper Option A 锁定为 M2 必选；Option B 不再作为 plan-author 选择项 | A: lift-and-upgrade（M2-mandated） / B: duplicate（拒绝，仅作历史 alternative 文档保留） | M1 telemetry 已使用 `_atomic_write` 并被 4 条现有测试 monkeypatched；Option B 要么产生 drift，要么强迫重写 M1 测试，两者都比 Option A 三条 back-compat sub-conditions 更糟（详见 §8.5 R6 修订与 YEL-COH-1） |
| 69 | 2026-06-11 (R6; R7 amended) | lock-path defense 必须自 `os.open(O_NOFOLLOW \| O_CREAT \| O_CLOEXEC)` 取 fd，**直接** `fcntl.flock(fd, LOCK_EX)` —— **R7 fix YEL-FEAS-1：删除"或委托给 filelock"分支**（dead-letter） | A: fd-mode lock via `fcntl.flock` 直接走 fd（R7 mandated） / ~~B: 委托给 filelock 库的 fd 路径~~（R7 拒绝：filelock 3.19.1 `BaseFileLock.__init__` 不接受 fd 参数；`UnixFileLock._acquire` 自身 `os.open(path)`，无公开钩子注入预开 fd；subclass-and-override 会在 filelock 版本 bump 时静默断裂） | `filelock.UnixFileLock` 实测 `open(path, "a")` follows symlinks；TOCTOU 必须在 syscall 层关闭；filelock pinned `>=3.25.2` 无 fd-mode 构造器 → 唯一 POSIX-correct 路径是直接 `fcntl.flock(fd)` |
| 70 | 2026-06-11 (R7) | Windows lock-path symlink defense 范围限定 POSIX-only；Windows 用 `is_symlink` precheck-only fallback + `resolve(strict=True).is_relative_to(...)` 兜底，TOCTOU window 列入 §12 carried-forward | A: POSIX-only + carried-forward（采纳） / B: Windows-specific `msvcrt.locking` + 后置 `os.fstat` symlink-detect（拒绝：超 M2 范围，且 Windows multiprocess + symlink 非现实威胁） | nanobot 主部署目标 POSIX；Windows multiprocess + symlink attack 在单用户开发者场景非现实威胁；M3 Curator 可用 Windows-specific `CreateFile(FILE_FLAG_OPEN_REPARSE_POINT)`-equivalent 关闭 |
| 71 | 2026-06-11 (R7) | atomic-write tmp 与最终 SKILL.md mode 锁定 `0o600`；写盘失败路径 mandatory `unlink(tmp)`，禁止"保留 leftover" 选项 | A: 0o600 + mandatory unlink（采纳） / B: 0o644 + cleanup deferred to plan（拒绝：world-readable partial-write 含 LLM-generated operational instructions，§4.6.1 已含 local adversary 威胁模型） | nanobot agent workspace 单用户；SKILL.md 仅同 uid 进程读取，0o600 充分；防 partial-write 内容残留 |
| 72 | 2026-06-11 (R7) | `nanobot/agent/_atomic_io.py` 必须提供 `fd_file_lock(path, *, timeout=1.0)` context manager；所有 lock-path 用法（§3.7 / §8.1）**必须**走该 helper；禁止 verb 实现里手写 `os.open + fcntl.flock + try/finally` | A: `fd_file_lock` helper（采纳） / B: 散布手写 `try/finally` block（拒绝：fd-leak / 释放顺序错误风险高） | 嵌套 `with` 自动 LIFO 释放；fd lifecycle / lock release / close 顺序统一封装；异常路径正确性可测（参见 §10.6 R7 acceptance gates） |
| 73 | 2026-06-11 (R8) | `nanobot/agent/_atomic_io.py` 顶部 `import fcntl` 必须包在 `try / except ImportError: fcntl = None` 守卫；`atomic_write` Windows 可用，`fd_file_lock` 在 `fcntl is None` 时 raise `RuntimeError("fd_file_lock is POSIX-only; Windows must take a different path")` | A: try/except 守卫 + RuntimeError 显式 fail-loud（采纳）/ B: 顶部 unconditional `import fcntl`（拒绝：Windows nanobot 启动直接 ImportError，全套 telemetry 路径瘫痪） / C: silent no-op on Windows（拒绝：fd_file_lock 应严格 POSIX-only，silent fallback 让 Windows 调用者误以为已加锁） | precedent: `nanobot/channels/msteams.py:29-32`；与决策 #70 Windows POSIX-only 范围一致；让 `skills_telemetry.py` 顶部 `from nanobot.agent._atomic_io import atomic_write as _atomic_write` 在 Windows 不崩，仅真正调 `fd_file_lock` 的 M2 verb 路径撞 RuntimeError；§10.6 acceptance gates R8-1 / R8-2 覆盖 |

### 13.A Superseded decisions（archaeology only — do NOT reference as M2 contract）

下表条目仅作设计演进史保留；M3 review 与 plan-author 不应将其视为 active M2 合同。权威 spec 文本以正文段落为准。

| # | 日期 | 历史决策 | 处置（R6） |
|---|---|---|---|
| 55 | 2026-06-11 (R3 → R4 superseded → R6 archived) | rate-cap counter 形态从 R3 4-桶 dict 简化为 R4 单一 int；R3 motivation（per-verb 信号给 M3 Curator）保留为 §12 carried-forward | 权威 spec 文本在 §5.2.1；本行仅作 R3→R4 演进史保留。M3 review 看 §5.2.1 + §12 carried-forward，不读本行 |
| 65 | 2026-06-11 (R4 → R6 superseded by #68) | `_atomic_write` lift-vs-duplicate 取舍权曾交 plan-author（spec 仅锁 flag 集） | R6 改判：Option A 锁定为 M2 必选（决策 #68），plan-author 不再有选择空间；本行存档 |

### 13.B Plan-author choice points（non-decisions; deferred to plan §2 file-map）

下列条目不是 M2 spec 做出的决策，而是 spec 委托给 plan-author 在 plan §2 file-map section 选择并文档化的实施细节。M2 drift-check Phase 5 验证 plan 已记录选择。

| # | 议题 | 选项空间 | 推荐 |
|---|---|---|---|
| 67 | `_run_core` per-iteration reset 的 RuntimeState 注入路径（§5.2.2） | W1: `AgentRunSpec.runtime_state` 字段 / W2: `AgentRunner.__init__` 参数（拒绝—破坏 single-instance runner） / W3: reset callable through spec（备选） | W1。W2/W3 详见 §5.2.2；plan-author 选 W2/W3 必须给一句话 justification |

## 14. 与下游 milestone 的接口契约（M3+ 不可破）

### 14.1 稳定接口表

| 接口 | 消费者 | 稳定形式 |
|---|---|---|
| `SkillManageTool` 的 verb dispatch 表 (`create / edit / patch / delete`) | M3 Curator（要在工具表面之上加 dry-run / protect-list） | 4 个 verb 名稳定；M3 加新 verb 必须复用现有 tool name，扩 enum 而不是 fork tool |
| Frontmatter 字段 `last_patched_at` / `patched_by` / `created_by` | M3 Curator | 字段路径 `metadata.nanobot.provenance.{...}` 稳定；读取仍走 M1 §5 的 `_get_skill_meta(name).get("provenance", {})` |
| Telemetry `patches` counter 由 `edit` + `patch` 共同 bump | M3 Curator | M3 解读时按"修改事件总频次"使用；要拆分时改 telemetry schema_version |
| `error_code` 枚举（§4.5） | M3 Curator 策略决策 | additive-extensible：M3 加新 code 必须追加而非重命名 / 删除（决策 #54） |
| `agents.defaults.skillManage.maxMutationsPerTurn` + `maxBodyBytes` + `maxAgentSkills` + `maxDescriptionLen` 配置 key | user / M3 | camelCase + Python `_` 双向 alias；M3 加同 namespace 字段不破现有 |
| `SkillsLoader.list_skills_with_shadows()`（M1 提供，M2 是首位 shadow-check 消费者） | M2 / M3 | 返回 `SkillEntry`（含 `effective_origin` / `shadowed_origins`）；M3 Curator 也用同一 primitive 做 dry-run / protect 判定 |
| Atomic write 合同（fsync(fd) → os.replace → fsync(parent_dir)，§8.5） | telemetry / skill_manage / 未来 M3+ 模块 | 形状一致；任何新写盘模块必须 align（决策 #57）；R7 锁定 tmp/final mode `0o600` + 失败路径 mandatory `unlink(tmp)`（决策 #71） |
| `fd_file_lock(path, *, timeout)` context manager（§3.7.1 step 5，`nanobot/agent/_atomic_io.py`） | skill_manage 所有 verb / M3+ 任何 workspace lock 用法 | 必须走 helper，禁止散布手写 `os.open + fcntl.flock`；POSIX-mandated，Windows fallback POSIX-only 范围（决策 #70 / #72）；module 顶部 `import fcntl` 走 try/except 守卫（决策 #73），`atomic_write` Windows 可用，`fd_file_lock` 在 Windows raise `RuntimeError` |
| 全局锁序（§8.6） | telemetry / skill_manage / 未来嵌套写路径 | 0) skill workspace create-lock（仅 create verb，决策 #60）→ 1) skill in-proc → 2) skill filelock → 3) telemetry _flush_lock → 4) telemetry filelock；释放反序（决策 #58） |
| Telemetry `tombstone: bool` 字段（决策 #66） | M3 reconcile / Curator | 可选 schema-additive 字段；M1 reader 透明；reuse 时 reconcile 清零 counter |
| `ToolContext.provenance_tag` 字段（§4.2） | 主 agent / Subagent / Dream | 默认 `"agent"`；扩字段不破现有 caller（决策 #46） |
| `MemoryStore.__init__` 签名（§6.1, §6.5） | ContextBuilder / CLI / 内置命令 dispatch | `def __init__(self, ..., telemetry: SkillTelemetry \| None = None)`；M3 必须保持向后兼容；三个 prod caller 路径（`context.py:73,110`, `cli/commands.py:1103`, `command/builtin.py:338`）显式注入 telemetry，新增 caller 必须显式注入（R6 YEL-COH-5） |

### 14.4 命名约定（R3 fix RED-13）

| 类别 | 风格 | 示例 |
|---|---|---|
| Tool name（Python 标识符 + tool registry 主键） | snake_case | `skill_manage` |
| 配置 key（JSON / Pydantic alias） | camelCase | `skillManage`, `maxMutationsPerTurn`, `maxBodyBytes` |
| Python 字段 / 变量 / 函数（与命名规约 §3 中的 user 全局规则） | snake_case + 类成员尾下划线 | `provenance_tag`, `_provenance_tag_`, `_skill_inproc_locks` |
| `error_code` 枚举值 | M1/M2 早期遗留小写下划线 / R3 新增 SCREAMING_SNAKE | `tier_locked`（早）/ `BODY_TOO_LARGE`（R3） |
| Frontmatter YAML key | snake_case | `created_by`, `last_patched_at`, `patched_by` |
| 内置 origin tier 名 | 单词小写 | `user`, `agent`, `builtin`, `hub` |

混合大小写源于 (a) Python 项目命名规约 vs (b) JSON config camelCase 历史，刻意保留两套词汇互不污染。M3 review 不得"统一"任一类别，统一即破契约。

## 15. 完工后该追加到 roadmap 的内容

完成 M2 时需在 [`docs/hermes-evolution/roadmap.md`](../roadmap.md) 做：

1. § 3 表格 M2 状态 → "已完成"，填 plan 路径与 retro 路径；
2. § 5 回顾段落 M2 项追加 200–500 字回顾（实际偏差、坑、对 M3 的影响——尤其是 rate-cap default 是否需要调）；
3. § 7 "当前位置" 勾选第 4 项的 M2 半（保留 M4 仍在并行项）。

并在 `docs/hermes-evolution/specs/` 与本 spec 同级新增（或 M3 spec 启动时）跨引用：M3 spec 必须 §1 显式声明依赖 M2 落地。
