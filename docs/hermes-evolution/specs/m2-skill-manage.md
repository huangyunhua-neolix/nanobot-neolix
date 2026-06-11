# M2 · skill_manage 工具 设计 Spec

> **Milestone**：M2（运行时回路第一段）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第二阶段。
>
> **状态**：设计已锁定（2026-06-11，Q1–Q13 决策全部 approved）。
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
3. **Frontmatter 字段扩展**：在 `metadata.nanobot.provenance` 命名空间下新增两个**可选**字段 `last_patched_at: ISO8601` 与 `patched_by: string`（`agent` / `subagent:<task_id>` / `dream`）。新字段对 M1 reader (`_get_skill_meta(name).get("provenance", {})`) 自然透传，不需要 M1 改一行代码。
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

## 4. 工具表面（`skill_manage`）

### 4.1 物理位置与命名（决策 #38）

- 单文件 `nanobot/agent/tools/skill_manage.py`，仿照 `nanobot/agent/tools/my.py` / `apply_patch.py` 的写法。
- 不拆 `skill_create.py` / `skill_edit.py` 等多文件——`Tool` 注册表里只有一个 `skill_manage` 入口；多文件会让 description 在 registry 里重复 4 份，浪费 prompt cache。
- 估算 LOC：~400 行（verb dispatch + 4 个 helper）。低于项目对单文件大小的隐性阈值（`my.py` 当前 ~600 行已可作上界参考）。

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
    """
    _scopes = {"core", "subagent", "dream"}
```

`_scopes` 三值含义：

- `core` —— 主 agent runtime 启用。
- `subagent` —— `ToolLoader().load(ctx, registry, scope="subagent")` 时启用（subagent 也可调）。
- `dream` —— `MemoryStore.build_dream_tools()` 显式注册（详见 §6）。

### 4.3 verb 语义详表

| verb | 必填参数 | 选填 | 副作用 | 失败模式（节选） |
|---|---|---|---|---|
| `create` | `name`, `body`, `description` | `requires` | mkdir 父目录 + 写 `SKILL.md`（含 frontmatter）；写 `created_at = now()`、`created_by` | name 已存在于任何 tier（agent/user/builtin/hub） → reject；name 不合规 → reject |
| `edit` | `name`, `body` | `description` | 全量重写 agent-tier skill body + frontmatter；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent → reject |
| `patch` | `name`, `search`, `replace` | — | 在 agent-tier body 内做一次 search/replace（要求 `search` 在文件中**唯一**出现）；bump `patches` 计数；写 `last_patched_at` / `patched_by` | name 不存在 / origin ≠ agent / `search` 找不到或多次出现 → reject |
| `delete` | `name` | — | 删除 `<workspace>/skills/agent/<name>/` 整个目录 | name 不存在 / origin ≠ agent → reject |

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
- 判定 origin 用 M1 已有的 `SkillsLoader._infer_origin_from_path(path)`（M1 §3.1 强制规则），**不**自己重写推断逻辑。
- 如果一个 name 同时存在于多 tier（被 M1 collision 检测出来），任何 `edit/patch/delete` 都 reject—— effective tier 是 user，不允许动；agent tier 副本被 user 影子，禁止"改了 agent 但 user 仍生效"这种迷惑写入。

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
    "error_code": "tier_locked",  # tier_locked | name_exists | not_found | search_ambiguous | search_missing | rate_limited | invalid_name | concurrency_timeout
}
```

`error_code` 的取值集是显式枚举，给 M3 Curator 做策略决策时 grep 用。

### 4.6 Name validation（防越权）

`_validate_skill_name(name)` 必须拒绝：

- 含 `/`、`\`、`..`、空白、控制字符的 name（防路径注入）。
- 长度 0 或 > 64。
- 不匹配 `^[a-z0-9][a-z0-9-]*$`（kebab-case，禁用大写与下划线，与现有 `nanobot/skills/*` 命名约定一致）。
- 保留名 `agent` 自身（避免与 M1 §10.1 风险表第 5 行"user 把 agent 当 skill 名"冲突反向触发）。

校验失败 → `error_code = "invalid_name"`，不写盘、不 bump。

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
- 配置 key：`agents.defaults.skill_manage.maxMutationsPerTurn`，camelCase（与 M1 `auxiliary.modelPreset` 同款风格），别名 Python 侧 `max_mutations_per_turn`。Schema 位置：新增 `SkillManageConfig(Base)` 嵌入 `AgentDefaults`。
- 实现位置：`SkillManageTool` 自身在 `set_context` 时拿到 turn 计数器（owner 是 agent loop 的 per-turn state，参照 `RuntimeState` 现有 hook 模式）；每次 verb 成功后 `+= 1`。
- 超限行为：`error_code = "rate_limited"`，**不**落盘、**不**bump telemetry。
- 计数器在每 turn 起点重置（见 §9.4 cache 不变量）。

为什么 rate-cap 是 mechanism 而非 policy：runaway 的判定阈值（5/turn vs 10/turn）允许 user 调；但是否要"超限自动 archive 该 skill" / "通知 Curator 复审"——那是 M3 的责任。M2 仅在物理层防"agent 一 turn 内 patch 50 次同一 skill"这种灾难场景。

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

注册顺序：`SkillManageTool` 应放在 `WriteFileTool(skills_dir)` 之**后**——`Tool.name` 唯一不冲突，但保留旧工具靠后能让 LLM 在 prompt 里**先**看到 `skill_manage`，提高优先选用率。

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

### 7.2 `create` / `delete` 依赖 M1 reconcile

M2 **不**在 `create` 路径里直接 mutate telemetry entries。理由：

1. M1 §4.2 `bump()` 已对未知 name 走"懒初始化"路径；新建 skill 立刻被 LLM 用上，view/use bump 会顺路把 telemetry 条目建出来。
2. 启动期 / `runner.run()` 入口处的 `reconcile()`（M1 §7 决策 #22）会把 `origin` 从 `"unknown"` 修正为 `"agent"`。
3. M2 不引入"create-time 立刻 reconcile"路径，避免与 `bump()` 抢 `_flush_lock`、避免单次 turn 内 reconcile 多次跑（M1 §4.3 假设 reconcile 是启动一次性事件）。

`delete` 同理：物理删目录后，下次 reconcile 自然把孤儿条目移除（M1 §4.3 RMW 表 "writer=reconcile" 分支）；M2 不立即触发 reconcile。

> **Carried-forward**：在 `delete` 与下次 reconcile 之间的窗口里，如果其他进程对该 name bump 一次（例如 list_skills 已经返回旧条目，agent 还来得及 use 一次），会在 telemetry 里多出一行 `origin="unknown"` 的孤儿；下次 reconcile 修复。M2 接受这个延迟；M3 若需要立即一致，再加 "delete 触发即时 reconcile" 路径。

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

#### last-writer-wins 的语义

并发两次 `patch` 同一 skill，filelock 串行后：

- 都成功 → 都 bump `patches`（计数 +2）。
- 第二个 `patch` 的 `search` 在第一个写完后可能找不到（被改没了）→ 第二个 reject `search_missing`，不 bump。

这与 M1 telemetry 的"counter 单调累计"一致：**每次成功的写**都贡献一次 bump，正确反映"有 N 次真实修改事件"。

### 8.2 Cache 阻塞？没有

M2 不实装 "REJECT if writer in flight" 这种乐观锁——那是 M3 策略层的事（"如果有 Curator 正在审议这个 skill，agent 此刻不许 edit"）。M2 只做悲观串行：filelock 串行 + 各自 last-writer-wins。

### 8.3 Subagent 共用 + 血缘标签（决策 #40）

- **物理路径**：subagent 与主 agent 共用 `<workspace>/skills/agent/`。**不**给 subagent 单独开 `<workspace>/skills/agent/subagent_<task_id>/` 子目录——那会污染 SkillsLoader 的"agent-source"扫描，逻辑复杂度暴涨。
- **血缘记录**：`SkillManageTool.set_context(ctx)` 时，从 ctx 抽取 task_id（参考 `nanobot/agent/subagent.py:77` `SubagentManager` + `subagent_announce.md` 现有 task_id 流通路径）；如果 ctx 标记是 subagent，则 `provenance_tag = f"subagent:{task_id}"`；否则 `"agent"`；Dream 路径在工具构造时显式 override 为 `"dream"`（§6.1）。
- **Telemetry**：subagent 复用主进程注入的 `SkillTelemetry`（M1 §11 接口契约第 5 行"subagent 复用主 telemetry 单例"已确立）。M2 不为 subagent 单独构造 telemetry。
- **并发**：subagent 与主 agent 同进程时走同一 in-proc lock dict；跨进程时由 filelock 兜底。

这意味着主 agent 与 subagent 可同时 `edit` 不同 skill（不同 name → 不同 lock），但同 skill 串行。这是预期行为。

### 8.4 SubagentManager 不动

M1 retro item 4 的"父 telemetry 转发到 subagent 的 SubagentManager 行为"M2 直接复用，不修改任何 SubagentManager 代码。`SkillManageTool` 在 subagent 里被注入时，从 manager 已经传下来的 ctx 拿 telemetry 引用即可。

## 9. Cache 不变量（**关键防御**）

### 9.1 §9 不变量（决策 #41，逐字提案）

> **`skill_manage` MUST NOT poke into in-flight prompt cache; the only state mutated mid-turn is disk + telemetry counters.**

具体含义展开：

1. **磁盘**：`skill_manage` 调用结束后，`<workspace>/skills/agent/<name>/SKILL.md` 立即反映新内容（atomic write 已 fsync）。
2. **当前 turn 的 prompt segment 不变**：`ContextBuilder` 在 `nanobot/agent/context.py:106-110` 已经把 `load_skills_for_context()` 与 `build_skills_summary()` 的输出装填进当前 turn 的 prompt segment；M2 **不**回头改这两个 segment——LLM 在本 turn 看到的 skill 内容可能已"过时"，但这是 prompt cache 完整性的代价。
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

## 13. 决策日志

| # | 日期 | 决策 | 选项 | 理由（简） |
|---|---|---|---|---|
| 37 | 2026-06-11 | `edit` 与 `patch` 两 verb 共存，**不**合并为单 patch + 空 search | A: 共存（采纳）/ B: 合并 | 失败模式语义错位 + telemetry 信号清洁 + LLM 表意（详见 §4.3） |
| 38 | 2026-06-11 | 单文件 `nanobot/agent/tools/skill_manage.py` 容纳所有 verb | A: 单文件（采纳）/ B: 4 文件分 verb | tool registry 一个入口；prompt cache 友好；~400 LOC 可控 |
| 39 | 2026-06-11 | 失败路径**全部**不 bump telemetry（含 validation / reject / lock timeout / rate_limit / IO error） | A: 静默（采纳）/ B: 记 `failed_attempts` 计数 | M1 telemetry 是"事件流计数器"，失败不构成事件；记失败留给 M3 操作日志 |
| 40 | 2026-06-11 | subagent 与主 agent 共用 `<workspace>/skills/agent/`，单一 namespace；血缘记录在 `created_by = "subagent:<task_id>"` | A: 共用 + 血缘标签（采纳）/ B: subagent 单独子目录 | 不污染 SkillsLoader scan；血缘可追溯；M1 §11 接口契约已锁 telemetry 单例复用 |
| 41 | 2026-06-11 | `skill_manage` MUST NOT poke into in-flight prompt cache | A: 不动 cache（采纳）/ B: 写完顺手刷 cache | 跨 milestone 硬性约束 #1（roadmap §6.2）；下次 turn 重 build 已自然刷新 |
| 42 | 2026-06-11 | runaway-edit 保护用 rate-cap，default 5/turn，配置 `agents.defaults.skillManage.maxMutationsPerTurn` | A: rate-cap（采纳）/ B: 不限制 / C: telemetry-driven | 机制层保护，策略阈值由 user 调；不限制会让 LLM 一 turn 内可能 patch 50 次 |
| 43 | 2026-06-11 | Dream 工具笼**追加** `SkillManageTool`，**保留** `WriteFileTool / EditFileTool / ApplyPatchTool` 作 escape hatch | A: 追加保留（采纳）/ B: 替换 | M2 不撤旧；撤旧是 M3 cleanup（§11 item 8） |
| 44 | 2026-06-11 | 新增 frontmatter 字段 `last_patched_at` / `patched_by` / `created_by` 全部 optional；不 bump telemetry schema_version | A: 全 optional（采纳）/ B: 强制 / C: 改 telemetry schema | 与 M1 §4.1 forward-compat 透传规则一致；写入侧 M2 永远填，读取侧 M3+ 用 `.get(key)` |
| 45 | 2026-06-11 | `provenance.origin` 仍只能写 `"agent"`；不引入新 origin 值（如 `"dream"`） | A: origin=agent + created_by=dream（采纳）/ B: origin=dream | M1 origin 三值 `user/agent/builtin` 已锁；新增 origin 值会破 M1 §3.1 enum |

## 14. 与下游 milestone 的接口契约（M3+ 不可破）

| 接口 | 消费者 | 稳定形式 |
|---|---|---|
| `SkillManageTool` 的 verb dispatch 表 (`create / edit / patch / delete`) | M3 Curator（要在工具表面之上加 dry-run / protect-list） | 4 个 verb 名稳定；M3 加新 verb 必须复用现有 tool name，扩 enum 而不是 fork tool |
| Frontmatter 字段 `last_patched_at` / `patched_by` / `created_by` | M3 Curator | 字段路径 `metadata.nanobot.provenance.{...}` 稳定；读取仍走 M1 §5 的 `_get_skill_meta(name).get("provenance", {})` |
| Telemetry `patches` counter 由 `edit` + `patch` 共同 bump | M3 Curator | M3 解读时按"修改事件总频次"使用；要拆分时改 telemetry schema_version |
| `error_code` 枚举（§4.5） | M3 Curator 策略决策 | 枚举值稳定；M3 加新 code 必须追加而非重命名 |
| `agents.defaults.skillManage.maxMutationsPerTurn` 配置 key | user / M3 | camelCase + Python `max_mutations_per_turn` 双向 alias；M3 加同 namespace 字段不破现有 |

## 15. 完工后该追加到 roadmap 的内容

完成 M2 时需在 [`docs/hermes-evolution/roadmap.md`](../roadmap.md) 做：

1. § 3 表格 M2 状态 → "已完成"，填 plan 路径与 retro 路径；
2. § 5 回顾段落 M2 项追加 200–500 字回顾（实际偏差、坑、对 M3 的影响——尤其是 rate-cap default 是否需要调）；
3. § 7 "当前位置" 勾选第 4 项的 M2 半（保留 M4 仍在并行项）。

并在 `docs/hermes-evolution/specs/` 与本 spec 同级新增（或 M3 spec 启动时）跨引用：M3 spec 必须 §1 显式声明依赖 M2 落地。
