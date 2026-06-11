# M2 · skill_manage 工具 设计 Spec

> **Milestone**：M2（运行时回路第一段）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第二阶段。
>
> **状态**：设计已锁定（2026-06-11，Q1–Q13 决策全部 approved；R3 patch 已合入：14 RED + 12 YELLOW 全部 resolved）。
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
- 决策 Log #51。

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
3. 配额（§3.7 本节，按上面三行顺序）
4. 进入 §8.1 锁路径 → 写盘 → bump

每一道闸都直接返回对应 `error_code`，**不**进锁，**不**写盘，**不**触 telemetry。
决策 Log #52。

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
    `created_by` / `patched_by` frontmatter. Resolution priority (R3 §4.2):
      1. `__init__` keyword `provenance_tag` (used by Dream path which
         bypasses ToolLoader and registers directly).
      2. `ToolContext.provenance_tag` injected via `set_context(ctx)`
         (used by main agent + Subagent paths via ToolLoader).
      3. Default `"agent"`.

    Each scope's registry-builder sets the tag explicitly:
      - main agent → `ToolContext(provenance_tag="agent")` (default)
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

**Option A（采纳）—— 扩 `ToolContext`，从 `ctx` 读 `provenance_tag`**

- `nanobot/agent/tools/context.py` `ToolContext` dataclass（line 47-60）追加 `provenance_tag: str = "agent"` 字段（带默认值，向后兼容所有现有 caller）。
- `SkillManageTool.__init__` 不再接受 `provenance_tag` 关键字，改为在 `set_context(ctx)` 或构造时从 `ctx.provenance_tag` 读取并存为 `self._provenance_tag_`（蛇形 + 尾下划线，遵循项目命名规约）。
- 三个 scope 的 registry-builder 显式构造不同 `ToolContext`：
  - **主 agent**：默认 `ToolContext(provenance_tag="agent", ...)`（无须显式传，吃默认值）。
  - **Subagent**：`SubagentManager._build_tools`（`nanobot/agent/subagent.py:130-149`）构造 `ToolContext(provenance_tag=f"subagent:{task_id}", ...)`。`_build_tools` 签名追加 `task_id: str` 参数，由 `_run_subagent`（line 233 调用点）把外层 `task_id` 闭包传入。
  - **Dream**：`MemoryStore.build_dream_tools()` 不走 `ToolLoader`，直接 `tools.register(SkillManageTool(...))`；构造时把 `provenance_tag="dream"` 通过显式 `set_context(...)` 或 `__init__` 关键字注入（Dream 注册路径不经过 ToolContext 装载机制，所以这里需要保留 `__init__` 的 keyword-only `provenance_tag` 兜底参数；优先级：`__init__` 显式参数 > `ctx.provenance_tag` > 默认 `"agent"`）。

**拒绝的备选：**

- **Option B（post-load registry.replace）**——`ToolLoader().load(...)` 之后再做 `registry.replace(name="skill_manage", new_instance=SkillManageTool(provenance_tag=...))`。被拒：`ToolRegistry` 没有 `replace` 原语（要新增 API），且 mutate-after-load 破坏 loader 的 single-source-of-truth 语义。
- **Option C（每次 tool 调用从 RuntimeState 读 tag）**——被拒：失去构造期不可变保证，每次调用必查 + 每个 verb 都要写防御代码；命名空间还要与 §5.2 rate-cap counter 共享 `_runtime_vars`，平添冲撞风险。

> M2 不引入 ToolLoader scope-filter 机制。哪个 scope 装载本工具，由该 scope 的 registry-builder 通过 `ToolContext.provenance_tag` 显式决定。决策 Log #46。

### 4.3 verb 语义详表

| verb | 必填参数 | 选填 | 副作用 | 失败模式（节选） |
|---|---|---|---|---|
| `create` | `name`, `body`, `description` | `requires` | mkdir 父目录 + 写 `SKILL.md`（含 frontmatter）；写 `created_at = now()`、`created_by` | name 已存在于任何 tier（agent/user/builtin/hub） → reject；name 不合规 → reject |
| `edit` | `name`, `body` | `description` | 全量重写 agent-tier skill body + frontmatter；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent → reject |
| `patch` | `name`, `search`, `replace` | — | 在 agent-tier body 内做一次 search/replace（要求 `search` 在文件中**唯一**出现）；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent / `search` 找不到或多次出现 → reject |
| `delete` | `name` | — | 删除 `<workspace>/skills/agent/<name>/` 整个目录（详细协议见下） | name 不存在 / origin ≠ agent → reject |

#### `delete` 顺序协议（R3 fix RED-12 — 全程持锁，禁止 mid-flow 释放）

R2 提案在 step 5 释放 filelock 后做 step 6 unlink `.lock`，存在 race：step 5 之后、step 6 之前，并发 `create` 拿到锁建新 SKILL.md，被 step 6/7 误删。R3 修订为**全程持双锁**，单点释放：

1. 取进程内 `_skill_inproc_locks[name]: threading.Lock`（懒创建；锁顺序：先 in-proc 后 filelock，与 telemetry 同款，详见 §8.6）。
2. 取 `FileLock(<workspace>/skills/agent/<name>/.lock)`（默认 timeout 1.0s；超时 → `concurrency_timeout`）。
3. **持锁中** 重新检查 `SKILL.md` 是否仍存在；若已不存在（被并发 delete 抢先），按幂等返回 `not_found`，**跳到第 7 步释放双锁**。
4. **持锁中** `unlink SKILL.md`。
5. **持锁中** `rmdir <name>/`——此时目录除 `.lock` 之外应已空（M2 不创建其他文件）；若有意外残留（`.DS_Store` / 用户手动放入），记 WARN log，**保留 `<name>/` 目录不强制 rm**（让运维介入），跳到第 7 步。
6. **持锁中** 尝试 `unlink <name>/.lock`——若 EBUSY / EACCES（罕见，仅当其他平台对持锁文件加排他保护），WARN log 继续；`.lock` 是 advisory，留下来无害（内核 fd 持有的锁状态早已随我们的 `FileLock.release` 释放）。
7. 释放 `FileLock`，再释放 `threading.Lock`（与第 1-2 步反序）。
8. 返回成功 `{"ok": True, "verb": "delete", ...}`。

**核心修订点**：原 R2 step 5（"退出 filelock 后再 unlink `.lock`"）被合并进持锁段。`.lock` 文件 unlink 即使失败也是无害的（advisory，会被新进程覆写）；保留 `.lock` 比中途释放锁制造 race window 更稳。

**正确性论证**：从第 1 步取双锁开始，到第 7 步双锁全部释放为止，任何并发 acquirer（被第 2 步阻塞的请求）只能在第 7 步之后才拿到锁；它们 pipeline 第一步是"读 SKILL.md"，看到文件不存在 → §4.5 返回 `not_found`，安全 no-op。`.lock` 即使被并发 acquirer 在我们 step 7 之后重建也无所谓——`filelock` 用的是内核 `flock`/`fcntl` advisory lock，**锁状态由内核 fd 持有，文件只是稳定句柄**。

决策 Log #50：double-lock single-release 协议替代 R2 mid-flow release。

> **拒绝的备选**：把锁放到 workspace 顶层独立 `locks/` 目录，避开"删自己锁"问题。被拒理由：破坏 M1 "skill 是 self-contained 单目录" 的属性，给 reconcile / list_skills 引入新外部依赖路径。维持 per-skill `.lock`。

#### `edit` verb 实现协议（R3 fix RED-8 — 全量重写必须真正"全量+原子"）

`edit` 在概念上是"全量重写"，但在实现上**禁止**就地 mutate 文件。所有四个 verb（含 patch / edit）都走同一 in-memory 重组 + atomic replace pipeline：

1. **持锁后** 把 `<name>/SKILL.md` 全量读入 string `current`。
2. 解析 `current` 的 YAML frontmatter（`yaml.safe_load`），dict 是 `meta`；把 frontmatter 后的部分作为 `body_str`。
3. **In-memory 变换**：
   - `edit`：`new_body = caller_body`；`new_meta` 在 `meta` 上覆盖 `description`（若传）+ 写 `last_patched_at` / `patched_by`。
   - `patch`：`new_body = body_str.replace(search, replace, 1)`（要求 `search` 在 `body_str` 出现且仅出现 1 次，否则前置 reject）；`new_meta` 同 edit 写 `last_patched_at` / `patched_by`。
4. **In-memory 重组**：`new_content = "---\n" + yaml.safe_dump(new_meta, sort_keys=False, allow_unicode=True) + "---\n" + new_body`。
5. **Atomic replace**：走 §8.5 atomic-write helper 一次性整体替换文件。
6. 释放锁，返回。

**禁止**任何"先 truncate 文件再 append"或"in-place sed"路径——这两种写法都会让 crash-mid-write 留下半截 SKILL.md，后续 `yaml.safe_load` 抛异常，skill 整体失活。

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

**counter 形态**：

```python
RuntimeState._runtime_vars["skill_manage.mutations_this_turn"]: dict[str, int]
# {"create": 0, "patch": 0, "edit": 0, "delete": 0}
```

按 verb 分桶（YEL-1 fix —— 与单一全局 counter 比较：分桶让 Curator 能区分 create-spam 与 delete-spam，调试性更好；总额仍由所有桶之和与 `maxMutationsPerTurn` 比对得出）。

**namespace 锁定**（YEL-3 fix）：`_runtime_vars` key 命名空间 `skill_manage.*` 由 M2 独占预留。`SelfTool.set_context` (`nanobot/agent/tools/self.py:340-349`) 写 `_runtime_vars` 时**禁止**使用 `skill_manage.` 前缀（M2 plan 阶段 fc-architect 必须在 SelfTool prompt schema 里加注释提醒）。

**计数器位置 + 注入路径**：`SkillManageTool` 在 `set_context(ctx)` 时拿到 `runtime_state` 引用——与 `SelfTool` 同款注入路径；`runtime_state` 由 `AgentRunner` 在每个 turn 入口注入到 `RequestContext` 或 ToolContext（具体注入点 plan 阶段定，本 spec 锁数据结构不锁行号，因为 runner.py 仍在演化）。

**reset 点（精确）**：`AgentRunner.run()`（`nanobot/agent/runner.py:275`）进入 `_run_core` 之前、每个新 turn 起点重置 dict 为 `{"create":0,"patch":0,"edit":0,"delete":0}`。注意：

- "turn" 是 LLM 一次完整 inference + 后续 tool 调用周期，不是 message 边界（subagent 内部多轮 tool 调用算同一 turn）。
- reset 发生在每个 `AgentRunner.run()` 调用入口；同一进程多 turn 之间天然隔离。

**subagent 配额继承表**（YEL-11 fix）：

| 场景 | 配额行为 |
|---|---|
| 父 agent → 首次 spawn subagent | subagent 起独立 `AgentRunner.run()`（独立 `RuntimeState` 实例） → 拿全新满额 `maxMutationsPerTurn` |
| subagent turn 内 → 多次 tool 调用 | 共享同一 `_runtime_vars` dict → 共享同一 turn 配额 |
| subagent → spawn 嵌套 subagent | 嵌套子也起独立 `AgentRunner.run()` → 全新满额 |
| subagent 返回 → 父 agent 后续 turn | 父配额**不受影响**（父 `_runtime_vars` 是独立 dict，subagent 改不到） |

**Dream 共享与否**：**不共享**。Dream 走 `MemoryStore.build_dream_tools()` 构造的独立 ephemeral `AgentRunner`（M1 §6 已锁），该 runner 拥有自己的 `RuntimeState`/`_runtime_vars`。Dream 一 turn 内最多还是 default 5 次，但与主 agent 的 5 次额度物理隔离。这正是 §5.2.1 整套"通过 RuntimeState 实例隔离"模型的副产物。

**单一计数器 vs 多桶 counter（YEL-1）**：M2 选 4-桶 dict（`{create, patch, edit, delete}`）。理由：(a) 给 M3 Curator "agent 在频繁 delete vs 频繁 create 是不同信号"的可读性；(b) 实现复杂度仅多 3 个 dict-init key；(c) 总额闸（任意桶之和 ≥ `maxMutationsPerTurn` → reject）逻辑等价于单一全局 counter。如果 M3 想加 per-verb sub-cap 例如 `maxCreatePerTurn=3`，本数据结构无需改。决策 Log #55。

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

### 6.6 Dream 写出的 skill 是 best-effort（R3 fix YEL-2）

§3.2 规定 Dream 调 `skill_manage create` / `edit` / `patch` 时把 `created_by` / `patched_by` 写为 `"dream"`。M3 Curator 必须把"由 Dream 写出 / 修改的 agent skill"视为 **best-effort non-authoritative tier**：

- Curator 决定是否 prune / archive 时，"曾被 Dream 修改"是降低优先级的信号——Dream 在不完全的 conversation context 下做 consolidation，比主 agent 在 in-flight tool loop 里的 edit 信噪比低。
- 这不是 hard rule，仅作 prior：如果同一 skill 后续被主 agent (`patched_by="agent"`) 重新背书，prior 应被洗掉。
- 实现细节属 M3 Curator 决策模型，本 spec 仅锁定 frontmatter 字段语义合同，不锁 Curator 实现。
- 决策 Log #56：M3 spec 必须在其 §1 显式 claim 这条 prior，并把"Dream 修改频次 / 主 agent 复确频次"作为输入特征。

## 7. Telemetry

### 7.1 计数器与 bump 时机

| 事件 | 触发 bump？ | bump kind |
|---|---|---|
| `create` 成功 | **不**直接 bump | M1 reconcile 在下次启动 / 下次 turn 起始处发现新 skill 后写零计数条目（M1 §4.4 "新出现的 skill"分支） |
| `edit` 成功 | bump | `"patch"`（M1 已实现的 kind，M2 是首位调用方） |
| `patch` 成功 | bump | `"patch"` |
| `delete` 成功 | **不**直接 bump | M1 reconcile 在下次 reconcile 时把孤儿条目删除（M1 §4.4 "磁盘已不存在"分支） |
| 任何失败（reject / rate_limit / lock timeout / validation） | **不** bump | 见 §7.3 |

`edit` 与 `patch` 共用 `bump(name, "patch")` —— 即"这是一次对 skill 内容的修改事件"。M1 §1.1 item 3 的 "patch kind M1 不调用" 在 M2 被首次落实。

> **术语辨析（Y7）**：`bump(name, kind="patch")` 调用形式中的 `kind` 是动词式参数（描述"这次事件是哪类"），值为字符串 `"patch"`；它递增的、写入 `<workspace>/skills/.telemetry.json` 的 on-disk 计数器键名是 `<entry>.patches`（复数名词）。两者拼写不同、用途不同，都正确，**不要混为一谈**。`edit` 与 `patch` verb 都走 `kind="patch"`，都把 `entry.patches` 加 1。

### 7.2 `create` / `delete` 依赖 M1 reconcile（R3 fix RED-10 — bump vs reconcile 严格切分）

M1 retro `docs/hermes-evolution/retros/m1-foundations.md` follow-up #49 已显式区分两类"orphan"语义；M2 严格沿用，**禁止合并**：

#### Case A — In-memory ghost（`bump` 写盘前 skill 已被删）

`bump(name, kind)` 在内存中 RMW telemetry dict；如果 skill 文件在 bump 调用与 flush 之间被另一调用方 delete，bump 写出的 entry 是个 in-memory ghost——M1 设计为**不**立刻消除，让 reader 看到一条 `pending decay` 状态的 entry。延迟 reconcile 修正（writer-tag 哲学）。**这是合法状态**，不需要 M2 干预。

#### Case B — On-disk orphan（telemetry 持有的 entry 对应 skill 文件不存在）

启动期 / 周期性 `reconcile()`（M1 §4.4）扫盘比对：磁盘有 entry 而 skill 文件不存在 → reconcile 删除该 entry。**reconcile 是 on-disk orphan 的唯一 deleter**（M1 invariant 4）。M2 **绝对不能**在 `delete` verb 路径里加并行的 telemetry-entry 清理，否则破 M1 invariant 4。

M2 在 `create` / `delete` 路径**不直接** mutate telemetry：

1. `create` 路径：M1 §4.2 `bump()` 对未知 name 已支持懒初始化；新 skill 立刻被 LLM use → view/use bump 顺路建条目；启动期 `reconcile()` 把 `origin: "unknown"` 修正为 `"agent"`。
2. `delete` 路径：物理删目录 → 下次 reconcile 删孤儿 entry。
3. M2 不引入"create-time 立刻 reconcile" / "delete-time 立刻 reconcile"，避免与 `bump()` 抢 `_flush_lock` 与 M1 "reconcile 是启动 / 显式触发事件"的语义。

> **Carried-forward 1（已知延迟一致性）**：`delete` 与下次 reconcile 之间，若另一进程对该 name bump 一次（例如 list_skills 已返回旧条目，agent 立刻 use），telemetry 多一行 `origin="unknown"` 孤儿；下次 reconcile 修复。M2 接受；M3 若需要立即一致，自己加路径。
>
> **Carried-forward 2（YEL-9 — bump-flush crash window）**：M1 已知有 ≤200ms 的 in-memory bump 未 flush 窗口；如果进程在该窗口内 crash，bump 事件丢失。M2 **继承**此窗口，不引入新的耐久性保证。和 §8.5 / §7.3 的 atomic-write 合同不冲突——文件写盘与 telemetry bump 是两条耐久性独立路径，bump 丢失不影响 skill 文件本身已落盘的事实。Cross-ref M1 spec §4.3。

### 7.3 失败路径的 telemetry 静默（决策 #39）

**任何**失败都不 bump。具体清单：

- `_validate_skill_name` 失败 → 不 bump。
- §4.4 矩阵 reject → 不 bump。
- filelock 超时（§8.1）→ 不 bump，向 LLM 返回 `error_code="concurrency_timeout"`。
- §5.2 rate_limit → 不 bump。
- IO 异常（磁盘满、权限错误）→ 不 bump，warn-throttle 记 log（沿用 M1 §4.3 节流策略，新增 `failure_kind = "skill_manage_io_error"`）。
- patch 的 search 找不到 / 多次出现 → 不 bump。

M1 §4.3 telemetry "bump 永远 O(1) 不触磁盘" 的不变量在 M2 仍然成立——M2 写盘动作发生在 telemetry bump **之前**，bump 只在写盘 atomic_replace 成功之后被调用。

### 7.4 不引入新 schema_version

新增 frontmatter 字段 (`last_patched_at` / `patched_by` / `created_by`) **只**落地在 `SKILL.md` 的 YAML frontmatter，**不**写入 `<workspace>/skills/.telemetry.json`。M1 telemetry schema_version 保持 `1`，无 bump，无迁移。

## 8. 并发与 Subagent 语义

### 8.1 两层锁（与 M1 telemetry 同款思路）

| 层 | 工具 | 保护对象 | 粒度 |
|---|---|---|---|
| 内存层 | per-process dict `_skill_inproc_locks: dict[str, threading.Lock]` 维护在 `SkillManageTool` 类作用域 | 同进程内多协程 / 多线程对**同一 name** 的写动作 | name 维度，懒创建 |
| 进程间层 | `filelock.FileLock(<workspace>/skills/agent/<name>/.lock)` | 跨进程的 read-modify-write of `SKILL.md` | name 维度 |

获取顺序：先 in-proc lock，后 filelock；释放反序。两层独立，与 M1 telemetry `_lock` / `filelock` 物理上不共享对象（不要复用 telemetry 的 `_flush_lock`，那把锁有自己的合同）。

#### 失败降级

- filelock 等不到（默认 timeout 1.0 秒，比 telemetry 的 0.2s 长——skill 文件远小于 telemetry RMW 量级，但 LLM 调用本身不期望次秒级）：返回 `error_code = "concurrency_timeout"`，不 bump，不重试（让 LLM 决定下一步）。
- in-proc lock 100% 等到（同进程拿不到只意味着另一协程在写，等就行）。

#### Stale `.lock` 文件（Y3）

`<name>/.lock` 文件在进程 crash 后会留在磁盘上——这是预期且无害的。`filelock` 库在底层使用内核 `flock`/`fcntl` advisory lock，**锁状态由内核 fd 持有，进程退出时由 OS 自动释放**；磁盘上的 `.lock` 文件只是一个稳定的命名句柄，不是锁状态本身。下次启动时新进程拿到的是一把全新的 advisory lock。M1 启动期 reconcile 不触碰任何 `.lock` 文件（M1 §4.4 reconcile 只看 `SKILL.md` 存在性 + `.telemetry.json` 条目），无需特殊清理逻辑。

#### last-writer-wins 的语义

并发两次 `patch` 同一 skill，filelock 串行后：

- 都成功 → 都 bump `patches`（计数 +2）。
- 第二个 `patch` 的 `search` 在第一个写完后可能找不到（被改没了）→ 第二个 reject `search_missing`，不 bump。

这与 M1 telemetry 的"counter 单调累计"一致：**每次成功的写**都贡献一次 bump，正确反映"有 N 次真实修改事件"。

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

所有 skill 文件写入（含 frontmatter + body）必须走与 `nanobot/agent/skills_telemetry.py:78-94` `_atomic_write` **形状一致**的原子写：

```
tmp = path.with_name(path.name + ".tmp")
fd = os.open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0o644)
try:
    os.write(fd, payload_bytes)
    os.fsync(fd)
finally:
    os.close(fd)
os.replace(tmp, path)            # 原子 rename
if sys.platform != "win32":
    dir_fd = os.open(parent_dir, O_RDONLY)
    try: os.fsync(dir_fd)
    finally: os.close(dir_fd)
```

实现选项（M2 plan 阶段 fc-architect 决定其一）：

- **Option A**：把 `_atomic_write` 从 `skills_telemetry.py` lift 成 `nanobot/agent/_atomic_io.py` 公共 utility，两个模块都 import；推荐（消除重复）。
- **Option B**：`skill_manage.py` 复制同款实现，加注释 cross-ref `skills_telemetry._atomic_write` 是同款合同；保留独立性。

任一选项都要求：

- `O_NOFOLLOW`（与 §4.6.1 路径逃逸防御呼应）。
- fsync(fd) → os.replace → fsync(parent_dir)。
- EBUSY / EACCES / ENOSPC / EIO 等任意 IO 错误 → `error_code = "ATOMIC_WRITE_FAILED"`，**禁止**部分写盘后 fall-through。
- 失败路径不 bump telemetry（§7.3）。

决策 Log #57。

### 8.6 锁顺序合同（R3 fix YEL-4）

进程内可能同时有 telemetry 写盘 + skill_manage 写盘的代码路径（例如：skill_manage 持 `_skill_inproc_locks[name]` 期间，自己 bump telemetry → telemetry 内部取 `_flush_lock`）。为避免任何死锁，**全项目**强制锁获取顺序：

1. **skill_manage in-proc lock**（`_skill_inproc_locks[name]: threading.Lock`）
2. **skill_manage filelock**（`<workspace>/skills/agent/<name>/.lock`）
3. **telemetry `_flush_lock`**（`threading.Lock`，M1 §4.3）
4. **telemetry filelock**（`<workspace>/skills/.telemetry.json.lock`，M1 §4.3）

释放反序。skill_manage 持 1+2 期间允许同步调 telemetry bump（telemetry 内部按 3+4 序进出，与 1+2 不冲突）。

绝对禁止：

- skill_manage 持 1+2 时主动 acquire 4 之外的另一把 telemetry lock（不存在的反向取序）。
- telemetry 内部主动 acquire 1 / 2（telemetry 不感知 skill_manage 存在）。

决策 Log #58。

### 8.7 ContextBuilder cache 边界（R3 fix YEL-5 —— mid-turn 写不污染 prompt cache）

`ContextBuilder.build_system_prompt()`（`nanobot/agent/context.py:80-...`）在每个 turn 起点**重新**调用 `self.skills.load_skills_for_context(...)` + `self.skills.build_skills_summary(...)` 重建 system prompt 各段。`SkillsLoader` 本身**无内部 caching**——每次 list_skills / load_skills_for_context 都是 fresh 目录扫描 + frontmatter 解析。

合同：

- mid-turn 调 `skill_manage create/edit/patch/delete` → 磁盘已变 → 当前 turn 已在 LLM 处理中的 prompt segment **不重建**（不 invalidate 当前 cache）。这是 §9.1 "MUST NOT poke into in-flight prompt cache" 的具体落地。
- 下一个 turn 起点 ContextBuilder 重新跑 → 自然吃到新 skill 内容。
- M2 **不**给 ContextBuilder 加任何 mid-turn 重建钩子；M3 若发现需要"create skill 后立即出现在当前 turn"的体验，自己加钩子（且要重新评估 prompt cache key 一致性）。

测试网（§10.4）覆盖：构造 turn-in-progress；mid-turn create；assert build_skills_summary 在当前 turn 内不重新读盘（mock 文件读取调用次数 == turn 起点的 1 次）。

### 8.8 Ghost-dir 重建语义（R3 fix YEL-12）

如果 `<workspace>/skills/agent/` 被外部进程 rmdir 后再被某 verb 触发重建（M2 §2 的 mkdir-on-first-create）：

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

针对 R3 引入的防御措施补齐 test gates，每条独立验证：

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

#### 多桶 rate-cap（YEL-1）

- 一个 turn 内连续 5 次 `create`（不同 name） → 第 6 次 `create` 还是 `rate_limited`（任意 verb 之和 ≥ 5）。
- 一个 turn 内 3 次 `create` + 2 次 `edit` → 第 6 次任意 verb → `rate_limited`；assert dict 内桶分别为 `{"create":3,"edit":2,"patch":0,"delete":0}`。

#### subagent budget 隔离（YEL-11）

- 父 agent turn 内已 mutate 4 次 → spawn subagent → subagent turn 内成功 5 次（独立配额） → 父 agent 后续 turn 配额仍是 reset 后的 5 次。
- 嵌套 subagent：父 → child → grandchild，三层各独立 5 次配额。

#### task_id 校验（RED-6）

- 构造 `provenance_tag = "subagent:abc-123"` → 工具构造成功。
- 构造 `provenance_tag = "subagent:\n---\nfoo: bar"` → `__init__` 抛 `ValueError`（工具不允许构造）。
- 构造 `provenance_tag = "subagent:" + "x" * 65` → `ValueError`。

#### atomic-write 失败路径（RED-7）

- mock `os.replace` 抛 OSError → tool 返回 `ATOMIC_WRITE_FAILED`；assert 磁盘 `SKILL.md` 内容**未变**（前一次成功的状态被保留），`SKILL.md.tmp` 也已被清理或保留为 leftover（实施 plan 决定）但绝不 partial-replace 真目标。
- mock fsync 抛 OSError → 同上。

#### dot-leading 名（YEL-10）

- `create(".lock", ...)` / `create(".gitignore", ...)` / `create(".DS_Store", ...)` → reject `invalid_name`。

#### shadow primitive（RED-11）

- workspace 同时有 user 层 `foo` + agent 层 `foo`（M1 collision warning）→ `edit("foo", ...)` → reject `tier_locked`（effective_origin == "user"）；assert 走的是 `list_skills_with_shadows()` 路径（mock 调用次数）。
- 仅 agent 层 `foo`（无 shadow）→ `edit("foo", ...)` → allow。

#### lock-ordering 死锁回归（YEL-4）

- 单 process 双线程：thread A 走 skill_manage 持锁后 bump telemetry；thread B 走 telemetry-only 路径 bump 同一 entry。assert 两线程各自完成（无死锁），最终文件与 telemetry 状态一致。

#### Cache 不变量（YEL-5）

- 构造 turn-in-progress 状态：调 `ContextBuilder.build_system_prompt()` 拿到 prompt P1；不结束 turn，立即调 `skill_manage create("new-skill")`；assert 同 turn 内不重新 build；下一个 turn 调 build → P2 内容含 "new-skill"，P1 ≠ P2。

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

> 任何上述项混入 M2 实施 plan 都视为 scope creep；plan-reviewer 必须 reject。

## 12. Carried-forward debt（M2 显式留给 M3+ 的债务）

- **`create` 后 reconcile 之前的 telemetry origin "unknown" 窗口**：详见 §7.2 第 1 段。下次 reconcile 修正。M3 若需要 immediate consistency，自己加路径。
- **`delete` 后 reconcile 之前的 stale entry 窗口**：详见 §7.2 末段 carried-forward block。
- **`MemoryStore.__init__` 新加 `telemetry` keyword 参数**：是 minimal 改动；M3 如果让 MemoryStore 走更深的 SkillsLoader 注入路径（例如 Dream 也走 ContextBuilder.build_skills_summary 计 view），可能要再扩 init 签名。
- **`SkillManageConfig` schema 字段单一**（仅 `maxMutationsPerTurn`）：M3 极可能要加 `protectList: list[str]`、`cooldownSeconds: int` 等字段；扩字段时复用 §5.2 同款 camelCase alias 风格，不破 schema_version。
- **`patches` 计数器同时承载 `edit` 与 `patch` 两 verb**：决策 #37 解释了 trade-off。如果 M3 Curator 发现两 verb 频次需要分开看，必须扩 telemetry schema_version 而不是在 M2 拆 counter。
- **subagent task_id 长度未限制**：理论上 `provenance.created_by = "subagent:<long-string>"` 可能膨胀 frontmatter；M2 接受现状（task_id 由 SubagentManager 生成已自带界限）；M3 如果引入 deep-nested subagent，再考虑 hash 化。
- **rate-cap 阈值 fixed default = 5**：未基于 telemetry 数据验证。M3 拿到 M2 实跑数据后可调整 default 或加自适应。
- **本 spec 不写代码 / 不锁数据流的边界条件**：例如 LLM 一次 tool_call 同时含 `verb=create` + `verb=edit` 的 batched 调用 schema —— M2 单次 tool_call 仅一个 verb；如果 M3 要求 batch，加新 verb `batch` 而不是改本 spec。
- **bump-flush crash window（YEL-9）**：M1 telemetry 已知 ≤200ms 的 in-memory bump 未 flush 窗口；M2 不引入新的耐久性保证。skill 文件本身的 atomic-write（§8.5）独立于 telemetry，bump 丢失不影响 skill 文件已落盘的事实。M3 若需要更强 RPO，自己加 sync-bump 路径。
- **`task_id` 字符串长度未限制**（已被 R3 §3.5 部分缓解）：M2 校验 ≤ 64 字符；frontmatter `created_by = "subagent:<8-hex>"` 当前实际是 17 字符，远低于上限。M3 引入 deep-nested subagent / 累积 task_id 时再考虑 hash 化。
- **配额阈值**未基于 telemetry 数据验证：`maxBodyBytes=64KiB` / `maxAgentSkills=200` / `maxDescriptionLen=280` 都是基于直觉的初值。M3 拿到 M2 实跑数据后可调整 default 或加自适应。

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
| 55 | 2026-06-11 (R3) | rate-cap counter 用 4-桶 dict（per-verb），非单一全局 int | A: 4-桶（采纳）/ B: 单一 int | 给 M3 区分 create-spam / delete-spam 信号；总额闸语义等价 |
| 56 | 2026-06-11 (R3) | Dream 写出的 skill 标记为 best-effort non-authoritative tier | A: 显式 prior（采纳）/ B: 与主 agent 等价 | Dream context 信噪比低；M3 Curator 应优先 prune Dream-only skill |
| 57 | 2026-06-11 (R3) | atomic write 用 `_atomic_write` 同款合同（fsync(fd)→replace→fsync(parent_dir)） | A: 复用合同（采纳）/ B: 简化为 write+rename | 与 telemetry 单一 durability 合同对齐；防 crash-mid-write 半截 SKILL.md |
| 58 | 2026-06-11 (R3) | 全项目锁顺序：skill in-proc → skill filelock → telemetry _flush_lock → telemetry filelock | A: 固定序（采纳）/ B: 各自独立 | 防死锁；skill_manage bump telemetry 是合法路径，必须有全局序 |
| 59 | 2026-06-11 (R3) | ghost-dir 重建不加 directory-watch，由 ContextBuilder 下次 build 自愈 | A: passive（采纳）/ B: 主动 watch | M2 不引入新基础设施；in-proc lock dict 对 string-key 仍安全 |

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
| Atomic write 合同（fsync(fd) → os.replace → fsync(parent_dir)，§8.5） | telemetry / skill_manage / 未来 M3+ 模块 | 形状一致；任何新写盘模块必须 align（决策 #57） |
| 全局锁序（§8.6） | telemetry / skill_manage / 未来嵌套写路径 | 1) skill in-proc → 2) skill filelock → 3) telemetry _flush_lock → 4) telemetry filelock；释放反序（决策 #58） |
| `ToolContext.provenance_tag` 字段（§4.2） | 主 agent / Subagent / Dream | 默认 `"agent"`；扩字段不破现有 caller（决策 #46） |

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
