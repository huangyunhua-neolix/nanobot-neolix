# M4 · 离线骨架（Offline Skeleton）设计 Spec

> **Milestone**：M4（离线进化骨架）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第四阶段。
>
> **状态**：草稿中（2026-06-12，§0 决策已锁定，body 待逐节 approve）。
>
> **依赖**：M1（[`m1-foundations.md`](./m1-foundations.md)）—— 需要 provenance 字段（`origin: agent`、`created_by`、`created_at`）作为离线进化候选的来源标签；不依赖 M2、不依赖 M3（M3 是运行时 lane，M4 是离线 lane，两条 lane 并行无耦合）。
>
> **下游**：M5（[`m5-darwinian-evolver.md`](./m5-darwinian-evolver.md)，待启动）将复用本 spec 的 4-tier 评测数据 schema、`Gate` ABC 与 PR-only 部署契约，新增 gates 4–5（语义保真 + PR 人审）以及代码层进化（Darwinian Evolver CLI）。

## 0. 调研、决策出处与 spec 决策记录

### 0.1 上游文档

- 总体研究：[`docs/hermes-self-evolution.md`](../../hermes-self-evolution.md)，特别是 §2.3（评估与验证）/ §2.5（安全约束）/ §4（对 nanobot 的可借鉴点）
- 总路线图：[`roadmap.md`](../roadmap.md)，§3 表格 M4 行 + §6 跨 milestone 硬性约束
- 上游 spec：[`m1-foundations.md`](./m1-foundations.md)（provenance / SkillsLoader 三源 / aux provider 配置形态）
- 同期 spec（运行时 lane，与 M4 解耦）：[`m2-skill-manage.md`](./m2-skill-manage.md)
- 流程教训：[`retros/m2-skill-manage.md`](../retros/m2-skill-manage.md)（双向校验 spec ↔ 实现 / 多轮收敛 / 单一 spec vs 拆分判断）

### 0.2 决策记录（M4 spec 立项期已锁定，沿用 M1/M2 编号风格，新决策从 #74 起）

下表为 brainstorming Q1–Q6 + 拆分判断的最终结论。所有 body 章节必须按这些决策展开，不得回退。

| # | 维度 | 锁定选项 | 锁定理由 |
|---|---|---|---|
| 74 | DSPy / GEPA 依赖姿态 | **Optional extra**：`pip install nanobot[evolve]`。`pyproject.toml` 新增 `[project.optional-dependencies] evolve = [...]`，运行时所有 `import dspy` / `import gepa` 均通过 lazy-guarded `try/except ImportError` 包裹于 `nanobot/evolve/__init__.py` 的入口函数体内。 | nanobot 主分发体积敏感（路线图 §6 隐含的"运行时与离线层分离"原则）；DSPy 引入 `litellm`、`optuna` 等大依赖树，强行进 `dependencies` 会让 `pip install nanobot-ai` 体积膨胀 ≥3×。Optional extra 是 nanobot 现有 precedent（`api`、`azure`、`matrix`、`pdf` 等 11 个 extras 已落地，参见 `pyproject.toml:68-112`）。版本固定到 §3.5 的兼容矩阵，不放任意上限。 |
| 75 | 评测数据存放位置 | **Hybrid 4-tier**：Tier A（synthetic）+ Tier C（curated golden）**入仓**于 `evals/`（NEW 顶层目录，**不**在 `tests/eval/`）；Tier B（SessionDB anonymized）+ Tier D（task self-eval）**用户本地**，位于 `~/.nanobot/evals/` 或 `<workspace>/evals/`，由用户级开关控制是否启用。 | (a) Tier A/C 是离线进化的 **shared baseline**，必须随仓库版本化、跨 contributor 复现；放 `evals/` 而非 `tests/eval/` 的原因：评测数据不是测试代码，pytest collection 不应扫到，且语义上 `evals/` 与 `nanobot/`、`webui/`、`bridge/` 同级表达"独立子系统"。(b) Tier B 含真实对话，**必须**留在用户机器（路线图 §6 约束 5 隐私边界）；Tier D 由 task 现场生成（如埋 bug 跑 debug skill），有明显 user-context 依赖。Hybrid 是唯一同时满足"可复现"+"隐私边界"的形态。 |
| 76 | Harness 调用面 | **CLI + Python API 双暴露**：CLI 子命令 `nanobot evolve <subcmd>`（与 `nanobot gateway` / `nanobot serve` 同级，挂在 `nanobot/cli/commands.py` 的 typer `app` 上）；Python API `from nanobot.evolve import OfflineHarness` 暴露同等能力，CLI 是 Python API 的 thin wrapper。 | (a) CLI 是终端用户唯一友好的入口（"跑一次进化"应是单命令）；(b) Python API 让 CI / 自动化脚本 / 未来的 fc-architect plan 任务能调用同套 harness 而不开 subprocess。Hermes 上游 `hermes-agent-self-evolution` 也是 CLI + 库双形态。M4 不引入 HTTP API（不需要远程触发），如未来 M5+ 有需求再加。 |
| 77 | Gate enforcement 机制 | **`gate.py` registry**：`class Gate(ABC)` 定义 `evaluate(candidate, baseline) -> GateResult`；模块级 `GATES: list[Gate]` 按声明顺序执行；M4 ships gates 1–3（test pass / size cap / cache compatibility），M5 append gates 4–5（语义保真 / PR 人审）。 | (a) 显式 ordered list 让"5 道闸门"路线图可见、可 audit、可单测；(b) ABC + 单元 list 比 decorator-registration 更易在 CI / report 里序列化；(c) M5 加 gate 只需 `GATES.append(SemanticFidelityGate())`，无任何已落地代码改动——这是最小延展面。Hermes 上游设计也是有序闸门 list（参见 hermes-agent-self-evolution PLAN.md §"5-gate evolution constraints"）。 |
| 78 | M4 进化目标 | **Agent-tier skills only**：仅对 `<workspace>/skills/agent/<name>/SKILL.md`（M1 引入、M2 写入的目录）做 GEPA 优化；tool description 与 system prompt 进化**全部**留给 M5。 | (a) Agent-tier skill 是唯一拥有 provenance frontmatter `origin: agent` 的目标（M1 §1.1 已锁定），离线产物可以直接覆盖回原文件，PR diff 易读；(b) tool description 进化会改 `nanobot/agent/tools/*.py` 源码、绕开 `Tool.description` 的现有静态 docstring，需要新框架支撑；system prompt 进化牵涉 `nanobot/templates/agent/*.md` 多文件级联，必须配合 cache stable 段重测——这两件事都属于 M5 的"代码层进化 + AGPL Darwinian Evolver" 范畴。M4 先把 skill 这条最简单路径打通。 |
| 79 | LLM-as-judge rubric | **3 维度 0–1 评分**：维度 1 process compliance（流程合规）、维度 2 output correctness（输出正确）、维度 3 token economy（token 经济）。每维度独立 0–1 浮点。**Cache compatibility 不进 rubric**——它是 §6 的硬 gate（gate 3，binary pass/fail）。 | 直接采用调研 §2.3 的 Hermes rubric。三维度互不替代：流程合规可能正确而冗长（dim 1 高 / dim 3 低）、输出正确可能流程错（dim 2 高 / dim 1 低）。把 cache 当 binary gate 而非 rubric 维度的理由：cache 兼容是 prompt 结构层面的硬约束（路线图 §6 约束 1），任何打破即 0 分等价于"产物不可用"，不该参与连续 fitness 加权。 |
| 80 | Spec 拆分判断 | **单一 spec**（不拆 M4a/M4b） | 4-tier 数据、3-judge rubric、3-gate registry、CLI/API 双面是**同一个离线进化 pipeline 的不同切面**，强行拆为 M4a-data / M4b-pipeline 会让"数据 schema → judge → gate"的契约链跨 spec 维护，违反 M2 retro §流程教训中"spec ↔ implementation 双向校验"原则（拆分会让 erratum 横跨两个 spec）。Hermes 上游同等范围的 PLAN.md 也是单文件 ~600 行，与本 spec 目标体量同级。 |

### 0.3 决策日志（body 章节中产生的新决策追加于此）

| # | 决策 | 章节 | 备注 |
|---|---|---|---|
| 74–80 | 见上 §0.2 | — | spec 立项期锁定 |
| 81 | Judge pool 默认 size = 3，仅允许奇数（3 或 5），单 judge 仅 dev 用 | §3.3 | 中位聚合需奇数；单 judge 易引入 model bias |
| *待 §4+ 起追加* | | | |

### 0.4 跨 milestone 硬性约束的本 spec 化身

路线图 §6 五条约束在 M4 的具体实现位置：

| 约束 | M4 实现位置 |
|---|---|
| 1. 永不打破 prompt cache | §6 gate 3（cache-compat gate）+ §10 不变量 1：候选产物在 dry-run 期间必须经 `cache_key_diff(baseline, candidate)` 校验，主 prompt stable 段 hash 必须不变 |
| 2. provenance 是一等概念 | §3.2 evolved skill 写回时 frontmatter 必须追加 `created_by: dspy:gepa`（与 M2 已锁定的 `agent` / `subagent:<id>` / `dream` enum **共存**，新值进入 `created_by` enum 集合）+ `evolved_from_run: <run_id>` 字段，便于 M5 追溯 |
| 3. dry-run 是 Curator 默认值 | M4 不直接管 Curator，但本 spec §8 PR-only 部署契约的 `nanobot evolve apply` 子命令**永不**直接覆盖磁盘——仅生成 PR 描述 + diff bundle，由人审 merge |
| 4. 离线层 PR-only | §8 完整章节定义此契约：harness 输出 `<workspace>/evals/runs/<run_id>/{report.md, diff.patch, pr_body.md}`，不 push、不 commit、不动 working tree 之外的任何文件 |
| 5. 隐私边界 | §9 完整章节定义 Tier B 脱敏 pipeline + 用户级开关 `agents.defaults.evolve.session_db_enabled`（默认 `false`），脱敏规则枚举（PII patterns、URL host 白名单、自定义 redactor hook） |

## 1. 范围与非范围

### 1.1 M4 做（in-scope）

1. **离线进化骨架包 `nanobot/evolve/`**（NEW 顶层 Python 包，与 `nanobot/agent/` / `nanobot/session/` 同级）—— 本 spec 锁定其包结构、模块边界、入口函数签名（详见 §2、§5）。包内所有模块在 `evolve` extra 未安装时仅暴露 stub 类，调用任何 entrypoint 立即抛 `EvolveExtraNotInstalled`（一种 `ImportError` 子类）；落实 §0.2 #74。
2. **CLI 子命令树 `nanobot evolve <subcmd>`** —— `init` / `run` / `report` / `apply` 四个子命令，挂在 `nanobot/cli/commands.py` 现有 typer `app` 上（详见 §4）；落实 §0.2 #76 的 CLI 面。
3. **Python API 表面 `nanobot.evolve.OfflineHarness`** —— CLI 是其 thin wrapper，CI / 自动化脚本 / 未来 plan agent 共用同一入口（详见 §5）；落实 §0.2 #76 的 API 面。
4. **4-tier 评测数据 schema 与目录布局** —— Tier A（synthetic）+ Tier C（curated golden）入仓于新顶层 `evals/`；Tier B（SessionDB anonymized）+ Tier D（task self-eval）落 `~/.nanobot/evals/` 或 `<workspace>/evals/`，由用户级开关 `agents.defaults.evolve.session_db_enabled`（默认 `false`）控制（详见 §2.2、§3.1、§9）；落实 §0.2 #75。
5. **进化目标范围**：仅 `<workspace>/skills/agent/<name>/SKILL.md`。tool description / system prompt 进化**全部**留给 M5（详见 §11）；落实 §0.2 #78。
6. **Gate registry**：`nanobot/evolve/gates/` 目录，`Gate` ABC + 模块级 `GATES: list[Gate]` 有序列表，M4 ships gates 1–3（test pass / size cap / cache compatibility）；M5 append gates 4–5（详见 §6、§14）；落实 §0.2 #77。
7. **LLM-as-judge 评分实现**：3 维度 0–1 浮点 rubric（process compliance / output correctness / token economy），prompt 模板与 calibration 协议（详见 §7）；落实 §0.2 #79。
8. **PR-only deploy 契约**：`nanobot evolve apply` 输出 `<workspace>/evals/runs/<run_id>/{report.md, diff.patch, pr_body.md}`，**永不**直接覆盖 `<workspace>/skills/agent/`（详见 §8）；落实路线图 §6 约束 4。
9. **隐私 / 脱敏 pipeline**：Tier B 的 SessionDB 抽样必须经过脱敏管线（PII 正则、URL host 白名单、自定义 redactor hook），开关默认 `false`（详见 §9）；落实路线图 §6 约束 5。
10. **Provenance 落标**：evolved skill 写回时 frontmatter 追加 `created_by: dspy:gepa`（与 M2 已锁定的 `agent` / `subagent:<id>` / `dream` 同 enum）+ `evolved_from_run: <run_id>` 字段（详见 §3.4）；落实路线图 §6 约束 2。
11. **Cache 兼容性硬 gate**：gate 3 在 dry-run 期间运行 `cache_key_diff(baseline, candidate)`，主 prompt stable 段 hash 必须不变；任何 stable 段差异 → gate fail，候选立即出局（详见 §6.3）；落实路线图 §6 约束 1。
12. **测试覆盖**：单元（每 gate 独立）、集成（端到端 `evolve run --dry-run` 在 Tier A + Tier C 上跑通）、契约（PR-only：harness 不能写 `<workspace>/skills/agent/` 之外的任何文件，由 sandbox fs-mock 测试断言）。

### 1.2 M4 不做（out-of-scope，明确留给 M5）

| 排除项 | 留给 |
|---|---|
| Tool description 进化（改 `nanobot/agent/tools/*.py` 源码 / `Tool.description` 静态 docstring） | M5 |
| System prompt 进化（改 `nanobot/templates/agent/*.md` 多文件级联） | M5 |
| Darwinian Evolver CLI 接入（外部 AGPL 子进程 + 许可隔离） | M5 |
| Gate 4 语义保真（baseline-equivalence 双 judge 对比） | M5 |
| Gate 5 PR 人审强制门（GitHub branch protection + CODEOWNERS 集成） | M5 |
| 跨 milestone fitness 对比（M4 run vs M5 run 的回归追踪） | M5 |
| HTTP API 触发面（`POST /evolve/run`） | 无明确 milestone（按需求） |
| `nanobot evolve apply` 直接 commit / push（**永不**做） | 永不 — 见 §8 PR-only 契约 |
| Tier B/D 默认开启 | 永不 — 见 §9 隐私边界 |
| 运行时 lane 任何变更（M2 `skill_manage` / M3 Curator 行为不动一行） | 不做 — M3 / M4 是两条解耦 lane |
| GEPA 之外的优化算法（如 OPRO / TextGrad） | 不做 — §0.2 #74 锁定 DSPy + GEPA 组合 |

### 1.3 与 M3 的解耦边界

M3（Curator）与 M4（离线骨架）共享 M1 的 provenance / telemetry / aux provider 基础，但运行时不交互：

- **M3 lane**：在线、读 telemetry、写 `<workspace>/skills/agent/`、由 cron 触发、aux provider 一次审议。
- **M4 lane**：离线、读 `evals/` 数据 + 候选 skill、写 `<workspace>/evals/runs/<run_id>/`、由 CLI / CI 触发、aux provider 多次 GEPA 迭代。
- **共用 schema**：均读 M1 的 `metadata.nanobot.provenance`；均认 M2 的 `created_by` enum 集合。M4 仅在该 enum 中**追加**新值 `dspy:gepa`，不改 M3 的状态机。
- **冲突场景**：当 M3 把某 skill 标记为 `archive` 时，M4 候选若覆盖该 name，PR 描述必须显式注明（详见 §8.4）；本 milestone **不**实现自动协调（留给 M5 reviewer 人工裁定）。

## 2. 文件系统结构

### 2.1 仓库内新增（入仓、随版本）

M4 引入两个新顶层目录 + 一个新 Python 包，均与 `nanobot/` / `webui/` / `bridge/` 同级：

```
<repo-root>/
├── nanobot/
│   ├── evolve/                          # NEW Python 包；evolve extra gate
│   │   ├── __init__.py                  # lazy guard：未装 extra → 抛 EvolveExtraNotInstalled
│   │   ├── harness.py                   # OfflineHarness 主入口（§5）
│   │   ├── data/                        # 4-tier 数据加载器
│   │   │   ├── __init__.py
│   │   │   ├── tier_a_synthetic.py      # Tier A loader（读 evals/synthetic/）
│   │   │   ├── tier_b_session.py        # Tier B loader（读 ~/.nanobot/evals/sessions/）
│   │   │   ├── tier_c_golden.py         # Tier C loader（读 evals/golden/）
│   │   │   └── tier_d_self_eval.py     # Tier D loader（读 <workspace>/evals/self/）
│   │   ├── judges/
│   │   │   ├── __init__.py
│   │   │   ├── rubric.py                # 3-维度 rubric 数据类（§3.3）
│   │   │   ├── llm_judge.py             # aux-provider judge 调用 + prompt 模板（§7）
│   │   │   └── calibration.py           # 评分校准（inter-judge agreement 协议，§7.4）
│   │   ├── gates/
│   │   │   ├── __init__.py              # GATES: list[Gate] = [TestPassGate(), SizeGate(), CacheCompatGate()]
│   │   │   ├── base.py                  # class Gate(ABC) + GateResult
│   │   │   ├── test_pass.py             # gate 1（§6.1）
│   │   │   ├── size_cap.py              # gate 2（§6.2）
│   │   │   └── cache_compat.py          # gate 3（§6.3）
│   │   ├── gepa/
│   │   │   ├── __init__.py              # DSPy + GEPA bootstrap（lazy import）
│   │   │   └── runner.py                # 单次 GEPA 迭代封装
│   │   ├── privacy/
│   │   │   ├── __init__.py
│   │   │   └── redactor.py              # PII / URL host / custom redactor pipeline（§9）
│   │   ├── deploy/
│   │   │   ├── __init__.py
│   │   │   └── pr_writer.py             # diff.patch + pr_body.md 生成（§8）
│   │   └── exceptions.py                # EvolveExtraNotInstalled / GateRejected / JudgeError 等
│   └── cli/
│       └── commands.py                  # 已有；M4 在此挂 evolve 子命令树（§4）
├── evals/                               # NEW 顶层；Tier A + Tier C 入仓
│   ├── README.md                        # 数据集说明 + 添加新样本流程
│   ├── synthetic/                       # Tier A
│   │   └── <skill-name>/
│   │       ├── input.jsonl              # 合成输入样例
│   │       └── expected.jsonl           # 期望输出（loose match，§3.1）
│   └── golden/                          # Tier C
│       └── <skill-name>/
│           ├── input.jsonl              # 手工 curated 输入
│           └── expected.jsonl           # 期望输出（strict match，§3.1）
└── tests/
    └── evolve/                          # NEW 测试目录；mirror nanobot/evolve/ 结构
        ├── test_harness.py
        ├── data/...
        ├── judges/...
        ├── gates/...
        └── deploy/...
```

约束：

- **`evals/` ≠ `tests/eval/`**：两者必须同时存在且语义不同。`evals/` 是数据资产（不会被 pytest 自动 collect），`tests/evolve/` 是 M4 的单元 / 集成测试代码（pytest 会 collect）。理由：评测数据的版本生命周期与测试代码独立——添加 Tier C golden sample 不该触发 CI 重跑，但改 gate 实现必须重跑。
- **`nanobot/evolve/` extra 隔离**：包顶层 `__init__.py` 必须 lazy guard 所有 `dspy` / `gepa` import；未装 extra 时 `from nanobot.evolve import OfflineHarness` 仍可成功（只是返回的类在 `__init__` 内 raise），保证 `nanobot` 主分发可被 `import nanobot.evolve` 探针检测而不崩。M4 spec 要求该探针写入 `tests/evolve/test_extra_gate.py`。
- **目录创建时机**：`evals/synthetic/` 与 `evals/golden/` 在 `nanobot evolve init` 首次调用时按需 `mkdir -p`；空目录提交一份 `.gitkeep` 占位（M4 init plan task 中列出）。

### 2.2 用户机器（不入仓、用户本地）

```
~/.nanobot/
├── evals/                               # Tier B + Tier D 数据沉淀
│   ├── sessions/                        # Tier B：SessionDB 抽样脱敏后的 jsonl
│   │   └── <YYYY-MM-DD>.jsonl
│   └── self/                            # Tier D：task 现场 self-eval 沉淀
│       └── <task_id>/
│           ├── input.json
│           ├── output.json
│           └── verdict.json
└── config.json                          # 已有；M4 新增 agents.defaults.evolve.* 字段（§4.4）

<workspace>/
├── evals/                               # workspace-scoped Tier B/D（覆盖 ~/.nanobot/）
│   ├── sessions/...
│   └── self/...
└── evals/runs/                          # NEW；harness 输出
    └── <run_id>/                        # run_id = "<UTC ISO>-<8-hex>"
        ├── manifest.json                # run 元数据（baseline hash / candidate hash / gate verdicts）
        ├── report.md                    # 人读总结（§8.2）
        ├── diff.patch                   # 候选 vs baseline 的 unified diff
        ├── pr_body.md                   # PR 描述模板（§8.3）
        ├── judge_log.jsonl              # 每条样本的 3-维度评分原始记录（§7.5）
        └── gates/
            ├── 1-test-pass.json
            ├── 2-size-cap.json
            └── 3-cache-compat.json
```

约束：

- **路径优先级**：harness 加载 Tier B / Tier D 时按 `<workspace>/evals/` → `~/.nanobot/evals/` 顺序查找，**不**合并；workspace-local 优先（与 nanobot 现有 config 覆盖语义一致，参见 `nanobot/config/loader.py`）。
- **`<workspace>/evals/runs/` 入 gitignore**：harness 产物不该入库；spec 要求 M4 plan 在 `init` 子命令中追加 `evals/runs/` 到 workspace `.gitignore`（若该文件不存在则创建）。
- **隐私边界硬约束**：`~/.nanobot/evals/sessions/` 与 `<workspace>/evals/sessions/` 写入路径**仅由** §9 脱敏 pipeline 触达；harness 主流程不允许直接写这两条路径（由 fs-mock 测试断言）。

### 2.3 不动的目录

M4 **不**触碰以下任何路径，违反即视为 spec drift：

- `<workspace>/skills/agent/<name>/SKILL.md` —— 仅 M2 `skill_manage` 工具与未来 M3 Curator 可写；M4 仅**读**（作为 baseline）+ 输出 diff.patch（人审 merge 时才落盘）。
- `nanobot/skills/<name>/`（builtin tier）/ `<workspace>/skills/<name>/`（user tier）—— provenance 不是 `agent`，M4 永不优化。
- `<workspace>/.nanobot/telemetry.json`（M1 落地）—— M4 仅读用于排序候选优先级（M5 territory 留给 fitness 加权），M4 本身**不**写 telemetry。
- `<workspace>/skills/agent/<name>/.lock`（M2 落地的 per-skill filelock）—— M4 不需要写 SKILL.md，故不取该锁。



## 3. 数据模型

本节定义 M4 离线进化 pipeline 的全部一等数据结构。所有 schema 用 Pydantic v2 风格表达（与 `nanobot/config/schema.py` 现有约定一致）；类名、字段名为最终落地名，不在实现期更名。

### 3.1 4-tier 评测数据 schema

每条评测样本（无论 tier）落地为 jsonl 中的一行 record（`EvalRecord`），存储位置见 §2.1 / §2.2，tier 间字段共形 + 语义层差。

#### 3.1.1 共形 base record

```python
# nanobot/evolve/data/__init__.py
from typing import Literal, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class EvalRecord(BaseModel):
    """单条评测样本（input + expected + metadata）；tier-agnostic。"""

    record_id: str                              # ULID 或 UUIDv7；同 jsonl 内唯一
    tier: Literal["A", "B", "C", "D"]
    skill_name: str                             # 目标 skill（agent-tier）
    input: dict                                 # skill 入参 payload
    expected: Optional[dict] = None             # 期望输出；Tier D 可缺省（由 self-eval 给 verdict）
    match_mode: Literal["loose", "strict", "judge_only", "binary_verdict"]
    privacy_class: Literal["public", "private"]
    created_at: datetime
    source: str                                 # tier A: "synthesizer:<seed>"；tier C: "curator:<gh-handle>"
                                                # tier B: "session:<sha256-12>"；tier D: "task:<task_id>"
    tags: list[str] = Field(default_factory=list)
```

每个 tier 子目录的 jsonl 由两条文件分担：`input.jsonl`（仅含 `record_id` + `input` + 元数据）与 `expected.jsonl`（仅含 `record_id` + `expected` + `match_mode`）。理由：Tier D 的 expected 是 task 现场后写的（input 与 expected 时间错位），分文件让"仅 input 已就位"的中间状态合法化。Tier A/C 的两文件由同一脚本一次写出，行序对齐 `record_id` 但读取仍以 `record_id` join，不依赖行号。

#### 3.1.2 Tier A — synthetic（合成数据）

- **存储位置**：`evals/synthetic/<skill-name>/{input,expected}.jsonl`（仓库内，§2.1）
- **生成方式**：M4 内部脚本 `nanobot/evolve/data/tier_a_synthetic.py:synthesize()`，以 aux provider 按种子模板生成；M4 不固化生成器细节，仅锁定 schema。
- **`match_mode`**：`judge_only` —— 因合成数据 expected 本身由 LLM 写出，不做 string equality；fitness 完全由 §3.3 的 `RubricScore` 给。
- **`privacy_class`**：`public`（入仓）。
- **量级目标**（M4 init 时建议）：每 skill ≥ 30 条；plan 期可调，spec 不锁死量级。

#### 3.1.3 Tier B — SessionDB anonymized（脱敏会话抽样）

- **存储位置**：`<workspace>/evals/sessions/<YYYY-MM-DD>.jsonl` 优先，回退 `~/.nanobot/evals/sessions/<YYYY-MM-DD>.jsonl`（§2.2）
- **生成方式**：由 §9 脱敏 pipeline 从 nanobot SessionDB 抽样 + redact 后写入；M4 主流程不直接读 SessionDB，仅读已脱敏的 jsonl。
- **`match_mode`**：`loose` —— 既要 expected 模糊匹配（如 string contains / json subset），又跑 §3.3 judge 评分。组合规则：fitness = (loose_match ? 1.0 : 0.5) × `RubricScore.aggregate`。
- **`privacy_class`**：`private`（**永不**入仓 + harness 输出 manifest 时**永不**包含 `input` / `expected` 原文，仅引用 `record_id`，详见 §3.7 不变量）。
- **开关**：`agents.defaults.evolve.session_db_enabled`，默认 `false`（§4.4 + §0.2 #75）。

#### 3.1.4 Tier C — curated golden（手工 golden）

- **存储位置**：`evals/golden/<skill-name>/{input,expected}.jsonl`（仓库内，§2.1）
- **生成方式**：人工 curated（PR 流程，contributor 手写 + reviewer 审）。
- **`match_mode`**：`strict` —— `expected` 字段中标记为 `key_outputs` 的子键必须 exact equal；其余字段不约束。`expected` schema：`{"key_outputs": {<jsonpath>: <value>}, "free_form": <any>}`，仅 `key_outputs` 进 strict 比对。理由：完全 exact-equal 在自然语言输出上必失败；锁定关键 slot（如返回的 file_path、tool_name、status code）才是 golden 的语义。
- **`privacy_class`**：`public`（入仓）。
- **量级目标**：每 skill ≥ 5 条核心 golden；这是 gate 1（test pass）的下限。

#### 3.1.5 Tier D — task self-eval（任务自评）

- **存储位置**：`<workspace>/evals/self/<task_id>/{input.json, output.json, verdict.json}`（§2.2，不分 jsonl，单 task 一目录）
- **生成方式**：当 task 显式调用 `nanobot.evolve.record_self_eval(task_id, input, output, verdict)`（API 见 §5）时落盘；典型场景如埋 bug 让 debug skill 跑、由 task 自身判断成败。M4 不主动注入此调用，仅暴露 API。
- **`match_mode`**：`binary_verdict` —— 仅看 `verdict.json` 的 `passed: bool`；跳过 judge 评分。fitness 直接 = `1.0 if passed else 0.0`。
- **`privacy_class`**：`private`（含 task 现场 context）。
- **开关**：`agents.defaults.evolve.self_eval_enabled`，默认 `false`（§4.4）。

#### 3.1.6 Tier 选择策略

`OfflineHarness.run()` 的 `tiers` 参数（见 §5）默认 `["A", "C"]`（仅 public）；启用 Tier B/D 须由 CLI 显式 `--tiers A,B,C,D` 或对应 config 开关。harness 内部按 tier 加载后，每条 record 的 fitness 计算路径走 `match_mode` 分派；最终用于 GEPA 优化的 fitness 是 **per-record fitness 的算术平均**，跨 tier 等权。tier 间加权留给 M5（§14）。

### 3.2 Candidate / Baseline 数据结构

GEPA 优化的最小单元是一个 `Candidate`（候选 skill 内容）配一个 `Baseline`（进化前内容）。两者结构同形但语义不同：

```python
# nanobot/evolve/harness.py
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import datetime

class SkillFrontmatter(BaseModel):
    """SKILL.md frontmatter（YAML），跨 M1/M2/M4 的共形结构。"""

    name: str
    description: str
    origin: Literal["bundled", "user", "agent"]   # M1 §1.1 锁定
    created_by: str                                # enum 见 §3.4
    created_at: datetime
    # M4 新增字段（仅 evolved 候选会带）
    evolved_from_run: Optional[str] = None
    evolved_at: Optional[datetime] = None
    parent_skill_hash: Optional[str] = None        # baseline content hash（sha256-12）

class SkillContent(BaseModel):
    """一个 SKILL.md 的完整内容（frontmatter + body）。"""

    skill_name: str
    skill_md_content: str                          # 完整文件 bytes（含 frontmatter + markdown body）
    frontmatter: SkillFrontmatter                  # 解析后的 frontmatter
    body_md: str                                   # frontmatter 之外的 markdown 主体
    cache_key_hash: str                            # 主 prompt stable 段 hash（sha256-12，gate 3 用）
    size_metrics: dict[str, int]                   # {"chars": int, "tokens_est": int, "lines": int}
    content_hash: str                              # 完整文件 sha256-12（manifest 与 parent_skill_hash 引用）

class Baseline(SkillContent):
    """进化前的 skill；从 <workspace>/skills/agent/<name>/SKILL.md 读取。"""

    loaded_from: str                               # 绝对路径
    loaded_at: datetime

class Candidate(SkillContent):
    """GEPA 输出的候选；frontmatter.created_by == 'dspy:gepa' 必须成立。"""

    parent_baseline_hash: str                      # 必须 == 配对 Baseline.content_hash
    gepa_iteration: int                            # GEPA 迭代序号（≥1）
    gepa_seed: Optional[int] = None                # 可复现性
```

**配对不变量（harness 强制）**：

1. 任一 `Candidate.parent_baseline_hash` 必须等于配对 `Baseline.content_hash`；`OfflineHarness` 在 `_pair_candidate(c, b)` 时校验，违反即抛 `BaselineMismatch`。
2. 跨 baseline 比较候选**永不**发生 —— 同一 run 内可有多个 baseline（多 skill 并行进化），但 fitness / gate 评估始终在同一 baseline 的候选集合内 rank。
3. `Candidate.frontmatter.evolved_from_run` 写回时必须等于当次 `run_id`；`parent_skill_hash` 必须等于 `parent_baseline_hash`。

### 3.3 JudgeResult / RubricScore 数据结构

落实 §0.2 #79 的 3 维度 0–1 rubric。score 与 result 分层：单条样本一个 `JudgeResult`，若 §7.4 inter-judge agreement 启用则一条样本可有多个 `JudgeResult`（每 judge 一个），聚合为 `JudgeConsensus`。

```python
# nanobot/evolve/judges/rubric.py
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class RubricScore(BaseModel):
    """3 维度独立 0–1 浮点 + 加权聚合。"""

    process: float = Field(ge=0.0, le=1.0)         # 流程合规
    output: float = Field(ge=0.0, le=1.0)          # 输出正确
    token: float = Field(ge=0.0, le=1.0)           # token 经济
    aggregate: float = Field(ge=0.0, le=1.0)       # 加权聚合（默认 0.4 / 0.4 / 0.2）

    @field_validator("aggregate")
    @classmethod
    def _validate_aggregate(cls, v: float) -> float:
        # 实际加权由 RubricWeights 给；这里仅校验区间。weights 错位由 harness 顶层断言。
        return v

class RubricWeights(BaseModel):
    """RubricScore.aggregate 的权重；通过 config 可调（§4.4）。"""

    process: float = 0.4
    output: float = 0.4
    token: float = 0.2

    @field_validator("token")
    @classmethod
    def _sum_to_one(cls, v: float, info) -> float:
        # 与上两 dim 求和必须 == 1.0（容差 1e-6）；否则 harness raise ConfigError
        return v

class JudgeResult(BaseModel):
    """单 judge × 单 record 的评分。"""

    eval_record_id: str                            # 引用 EvalRecord.record_id
    judge_model: str                               # 如 "anthropic/claude-3-5-sonnet"
    score: RubricScore
    reasoning: str                                 # judge 的自然语言说明（人审用）
    timestamp: datetime
    prompt_template_version: str                   # judge prompt 模板版本（§7）

class JudgeConsensus(BaseModel):
    """跨 judge pool 的一致性聚合；当 pool 仅 1 judge 时退化为单结果。"""

    eval_record_id: str
    judges: list[JudgeResult]                      # len ≥ 1；len ≥ 3 时启用 §7.4 协议
    median_score: RubricScore                      # 三维度逐维取中位
    inter_judge_variance: dict[str, float]         # {"process": σ², "output": σ², "token": σ²}
    consensus_verdict: Literal["agree", "split", "single"]
    # split = 任一维 σ > 0.2；single = pool size == 1

class JudgePool(BaseModel):
    """judge pool 配置；M4 推荐 size ≥ 3（决策 #81）。"""

    judges: list[str]                              # provider/model 列表
    weights: RubricWeights = RubricWeights()
    require_consensus: bool = False                # True 时 split → JudgeError 致整 record fail
```

**新决策 #81（追加于 §0.3）**：判官池默认 size 为 3（pool of 3 distinct provider/model），单 judge 模式仅在 dev / unit-test 启用，CLI `--single-judge` 显式开启。理由：Hermes 调研指出单 judge 易引入 model bias；3 已是"最小奇数 + 可中位"。可在 config 调到 5，但不允许 2 或 4（避免无中位）。

### 3.4 Provenance frontmatter 写回 schema

落实路线图 §6 约束 2 + §0.2 #74 / §0.4。M4 的 `created_by` enum 在 M2 已锁定的集合上**追加**（非破坏）。

#### 3.4.1 `created_by` enum 集合（M4 期）

| 值 | 引入 milestone | 语义 |
|---|---|---|
| `bundled` | M1 | nanobot 主分发自带 skill |
| `user` | M1 | 用户在 `<workspace>/skills/` 手写 |
| `agent` | M2 | agent 通过 `skill_manage` 工具新建 |
| `subagent:<id>` | M2 | subagent 通过 spawn 链新建 |
| `dream` | M2 | Dream 两阶段 memory consolidation 提取 |
| `dspy:gepa` | **M4 新增** | 离线 GEPA pipeline 产出 |

cross-ref：`m2-skill-manage.md` §3.2（M2 spec 锁定原 enum）。M4 仅 append 一项，不改任何已有值的语义；M2 已落地的写入路径不需要任何代码改动。

#### 3.4.2 YAML frontmatter delta（before / after evolution）

进化前（baseline，假设由 M2 agent 创建）：

```yaml
---
name: refactor-helper
description: Help refactoring code by ...
origin: agent
created_by: agent
created_at: 2026-04-01T10:00:00Z
---
# Refactor helper
... markdown body ...
```

进化后（candidate，M4 写回）：

```yaml
---
name: refactor-helper
description: Help refactoring code by ...
origin: agent                                    # 不变
created_by: dspy:gepa                            # ← 改写
created_at: 2026-04-01T10:00:00Z                 # ← 保留原值（首次诞生时间）
evolved_from_run: 2026-06-12T08:30:00Z-a1b2c3d4  # ← 新增
evolved_at: 2026-06-12T08:45:00Z                 # ← 新增
parent_skill_hash: 7f3a9e2b1c4d                  # ← 新增（baseline content_hash 前 12 hex）
---
# Refactor helper (revised)
... 改进后的 markdown body ...
```

写回规则：

1. `origin` **永不**被 M4 改写（仍是 `agent`；M4 不创造新 origin）。
2. `created_at` 保留首次诞生时间；`evolved_at` 是本次进化时间。这与"新创建一个 skill"语义不同 —— 进化是 in-place rewrite，需保留 archaeology trace。
3. `parent_skill_hash` 引用的 hash 算法与 `content_hash` 同（sha256-12，§3.2），可直接 grep `evals/runs/*/manifest.json` 反查 baseline 来源。
4. 若 candidate frontmatter 缺 `evolved_from_run` / `evolved_at` / `parent_skill_hash` 任一项，`pr_writer` 拒绝生成 diff（不变量见 §10）。

### 3.5 DSPy / GEPA 版本兼容矩阵

落实 §0.2 #74。M4 ships 时锁版如下：

| 依赖 | 版本范围 | 性质 | 锁定理由 |
|---|---|---|---|
| `dspy-ai` | `>=2.5.0,<3.0` | 直接（`evolve` extra） | DSPy 在 2.5 开始稳定 `dspy.Module` / `dspy.Predict` API；3.x 计划重构 signature 体系，主版本上限固定避免破坏。 |
| `gepa` | `>=0.3.0,<0.5` | 直接（`evolve` extra） | GEPA PyPI 包（非 git+），0.3 是首个有 `gepa.optimize(metric_fn=...)` 稳定签名的版本；0.5 计划改 metric 协议。 |
| `litellm` | （不显式 pin） | 间接（DSPy 拖入） | DSPy 自身 pin；M4 不引入二次约束以免冲突。 |
| `optuna` | （不显式 pin） | 间接（GEPA 拖入） | 同上。 |

`pyproject.toml` delta（M4 plan 期落地）：

```toml
[project.optional-dependencies]
evolve = [
    "dspy-ai>=2.5.0,<3.0",
    "gepa>=0.3.0,<0.5",
]
```

#### 3.5.1 Lazy-guard 契约

`nanobot/evolve/__init__.py`、`nanobot/evolve/gepa/__init__.py`、`nanobot/evolve/judges/llm_judge.py`（任何 import `dspy` / `gepa` 的模块）必须满足：

1. 模块顶层 **不** 直接 `import dspy` / `import gepa`；改在函数体内 lazy import。
2. lazy import 包裹于 `try/except ImportError`，命中即抛 `EvolveExtraNotInstalled`（`exceptions.py` 定义，继承自 `ImportError`），错误消息含安装提示：`pip install nanobot[evolve]`。
3. `from nanobot.evolve import OfflineHarness` 必须在未装 extra 时**也能成功**（仅在 `OfflineHarness.run()` 等入口函数被实际调用时抛错）；保证 `import nanobot.evolve` 不崩，便于 §2.1 `tests/evolve/test_extra_gate.py` 探针。

```python
# nanobot/evolve/exceptions.py
class EvolveExtraNotInstalled(ImportError):
    """`pip install nanobot[evolve]` 未执行；DSPy / GEPA 不可用。"""
    INSTALL_HINT = "pip install nanobot[evolve]"

# nanobot/evolve/gepa/runner.py
def _lazy_import_gepa():
    try:
        import gepa
        import dspy
    except ImportError as e:
        raise EvolveExtraNotInstalled(
            f"M4 evolve harness needs DSPy + GEPA. {EvolveExtraNotInstalled.INSTALL_HINT}"
        ) from e
    return gepa, dspy
```

### 3.6 Gate ABC + GateResult schema

数据形状定义在此节；逐 gate 业务语义见 §6。

```python
# nanobot/evolve/gates/base.py
from abc import ABC, abstractmethod
from typing import Literal, Optional
from pydantic import BaseModel
from datetime import datetime

class GateResult(BaseModel):
    """单 gate × 单 candidate 的判定结果。"""

    gate_name: str                                 # 与 Gate.name 同
    candidate_hash: str                            # 引用 Candidate.content_hash
    baseline_hash: str                             # 引用 Baseline.content_hash
    verdict: Literal["pass", "fail"]
    metrics: dict[str, float]                      # gate-specific 量化指标
    failure_reason: Optional[str] = None           # verdict == "fail" 时必填
    timestamp: datetime
    duration_ms: int

class Gate(ABC):
    """Gate registry 元素。所有具体 gate 必须实现 name + evaluate。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """形如 '1-test-pass' / '2-size-cap' / '3-cache-compat'；序号即 GATES 中位置。"""

    @abstractmethod
    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        """同步评估；不允许调网络（gate 级要求 deterministic）。"""

# nanobot/evolve/gates/__init__.py
from .test_pass import TestPassGate
from .size_cap import SizeGate
from .cache_compat import CacheCompatGate

GATES: list[Gate] = [
    TestPassGate(),    # gate 1
    SizeGate(),        # gate 2
    CacheCompatGate(), # gate 3
]
```

**执行规则**：

1. `OfflineHarness._run_gates(candidate, baseline)` 按 `GATES` 顺序逐 gate 调 `evaluate`。
2. 首个 `fail` 即 short-circuit：剩余 gate **不**执行；候选标记 `gate_rejected_at: <gate_name>`。
3. 每 gate 的 `GateResult` 落盘 `<run_id>/gates/<N>-<name>.json`（§2.2）；short-circuit 时仅前 N 个 json 存在。
4. M5 通过 `GATES.append(SemanticFidelityGate(), HumanReviewGate())` 扩展 gate 4–5；M4 代码不需任何改动。

### 3.7 Run manifest schema

每次 `evolve run` 输出一个 manifest，是 PR 描述 / report.md 的事实之源。

```python
# nanobot/evolve/harness.py
from typing import Literal
from pydantic import BaseModel
from datetime import datetime

class JudgeSummary(BaseModel):
    """跨 record 的 judge 评分汇总（manifest 用，不含原始 reasoning）。"""

    record_count: int
    median_aggregate: float
    median_process: float
    median_output: float
    median_token: float
    consensus_split_count: int                     # JudgeConsensus.consensus_verdict == "split" 计数

class RunManifest(BaseModel):
    """<workspace>/evals/runs/<run_id>/manifest.json 的根对象。"""

    run_id: str                                    # "<UTC ISO>-<8-hex>"
    started_at: datetime
    finished_at: datetime
    nanobot_version: str
    evolve_extra_version: dict[str, str]           # {"dspy-ai": "2.5.3", "gepa": "0.3.1"}
    skill_name: str
    baseline_hash: str                             # 仅一个；多 skill 并行 → 多 manifest
    candidate_hashes: list[str]                    # GEPA 全部迭代输出
    promoted_candidate_hash: Optional[str]         # 通过全部 gate 且 fitness 改善的赢家；None == 全军覆没
    gate_verdicts: list[GateResult]                # 仅记录最终 promoted candidate 的 gate trace；
                                                   # 全员 reject 时记录 fitness 最高者的 trace
    judge_summary: JudgeSummary                    # 见上，跨 record 聚合
    final_status: Literal[
        "promoted_to_pr",                          # 全 gate pass + fitness > baseline
        "rejected_by_gate",                        # 至少一 gate fail
        "no_improvement",                          # 全 gate pass 但 fitness ≤ baseline
        "harness_error",                           # 异常退出（含 EvolveExtraNotInstalled）
    ]
    tiers_used: list[Literal["A", "B", "C", "D"]]
    record_count_per_tier: dict[str, int]          # 不含 record_id / input / expected 原文
```

#### 3.7.1 「无 PII」不变量

`RunManifest` 内**严禁**出现以下字段（PR-only 部署契约 §8 与隐私边界 §9 的 hard line）：

1. Tier B / Tier D 任一 record 的 `input` / `expected` / `output` / `verdict` 原文；
2. `JudgeResult.reasoning` 原文（reasoning 落 `<run_id>/judge_log.jsonl`，不入 manifest）；
3. SessionDB 主键 / 用户 ID / 渠道 ID；
4. `<workspace>` 绝对路径（manifest 仅引用 run-relative path）。

manifest 仅包含 hash / id / 计数 / 聚合统计 → 可安全 attach 至 PR body（§8.3）。

`pr_writer` 在生成 `pr_body.md` 时**额外**校验：扫描 manifest jsonify 后内容，若任一字符串字段长度 > 256 chars 或含 high-entropy substring（用 zxcvbn-style heuristic）即抛 `ManifestPrivacyViolation`，阻断 PR 生成。

---

> §3 数据模型完。新增决策 #81（judge pool size = 3，奇数仅）已追加 §0.3。下一节 §4 CLI 语法。

## 4. CLI 语法

*（待 §3 approve 后填入）*

## 5. Python API 表面

*（待 §4 approve 后填入）*

## 6. Gate 详细定义

*（待 §5 approve 后填入）*

## 7. Judge rubric 与 calibration

*（待 §6 approve 后填入）*

## 8. PR-only deploy 契约

*（待 §7 approve 后填入）*

## 9. 隐私与脱敏 pipeline

*（待 §8 approve 后填入）*

## 10. 不变量

*（待 §9 approve 后填入）*

## 11. 非范围（out-of-scope，留给 M5+）

*（待 §10 approve 后填入）*

## 12. Carry-forward debt

*（待 §11 approve 后填入）*

## 13. 决策日志

*（合并至 §0.3，body 完工时回填全部新决策）*

## 14. 下游契约（to M5）

*（待 §13 approve 后填入）*
