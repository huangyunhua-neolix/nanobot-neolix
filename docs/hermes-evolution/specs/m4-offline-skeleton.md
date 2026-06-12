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
| 82 | CLI 退出码全表（0=ok / 1=generic / 2=config / 3=extra-missing / 4=privacy / 5=resource-or-provider / 6=fs-or-state / 7=harness-invariant）；gate fail 不映射到非零 | §4.6 | CI / 自动化脚本需可分流不同失败模式（特别是「重试 provider」vs「报 bug」）；gate fail 是业务判定不是 CLI 错误 |
| 83 | Default judge pool 选 3 家不同 provider（Anthropic Claude 3.5 Sonnet / OpenAI GPT-4o / Google Gemini 1.5 Pro），不重 provider | §4.5 | 同 provider 模型 bias 高度相关；跨 provider 最大化解耦 |
| *待 §6+ 起追加* | | | |

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
│   │   └── exceptions.py                # EvolveExtraNotInstalled / BaselineMismatch / JudgeError / ManifestPrivacyViolation / ConfigError
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

**配对不变量（harness 强制）**：编号 #1 / #2 / #3 是 spec 内的稳定 anchor，下游章节（§5.1 docstring、§10 不变量）通过 "§3.2 配对不变量 #N" 引用。

1. **§3.2 #1 — Baseline-candidate hash pairing**：任一 `Candidate.parent_baseline_hash` 必须等于配对 `Baseline.content_hash`；`OfflineHarness` 在 `_pair_candidate(c, b)` 时校验，违反即抛 `BaselineMismatch`（exit 7，harness invariant）。
2. **§3.2 #2 — No cross-baseline comparison**：跨 baseline 比较候选**永不**发生 —— 同一 run 内可有多个 baseline（多 skill 并行进化），但 fitness / gate 评估始终在同一 baseline 的候选集合内 rank。
3. **§3.2 #3 — Provenance writeback equality**：`Candidate.frontmatter.evolved_from_run` 写回时必须等于当次 `run_id`；`parent_skill_hash` 必须等于 `parent_baseline_hash`。

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
    min_quorum: int = 1                            # provider 退化时仍需的最小可用 judge 数；
                                                   # available_judges 数低于此 → JudgeError 中断 run
```

**新决策 #81（追加于 §0.3）**：判官池默认 size 为 3（pool of 3 distinct provider/model），单 judge 模式仅在 dev / unit-test 启用，通过 `--judge-pool <single-model-name>`（长度 1 即合法奇数）触发。理由：Hermes 调研指出单 judge 易引入 model bias；3 已是"最小奇数 + 可中位"。可在 config 调到 5，但不允许 2 或 4（避免无中位）。

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
    judge_pool_health: dict[str, str]              # {model: "ok" | "degraded:<reason>" | "unavailable:<reason>"}；
                                                   # 详见 §5.1 JudgeError retry contract。
                                                   # value 限 256 chars，避免 reasoning 原文泄漏（§3.7.1）。
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

落实 §0.2 #76 的 CLI 暴露面。所有子命令挂在 `nanobot/cli/commands.py` 现有 typer `app` 上，与 `nanobot gateway` / `nanobot serve` 同级，命名空间 `nanobot evolve <subcmd>`。CLI 全部为 Python API（§5）的 thin wrapper —— CLI 不实现业务逻辑，仅做参数解析 + `OfflineHarness` 调用 + 退出码映射。

### 4.0 子命令总览与公共行为

| 子命令 | 作用 | 是否需要 `evolve` extra |
|---|---|---|
| `nanobot evolve init` | 一次性 bootstrap：创建 `evals/synthetic/` + `evals/golden/` + `<workspace>/evals/runs/`、追加 `.gitignore`、写 `evals/README.md` 模板 | **否**（仅 mkdir / write，不 import dspy/gepa） |
| `nanobot evolve run <skill-name>` | 主入口：跑 GEPA 迭代 → judge 评分 → gate 链 → manifest/report/diff 输出 | **是**（未装抛 `EvolveExtraNotInstalled` → exit 3） |
| `nanobot evolve report <run-id>` | 只读：打印某 run 的 `report.md` | **否**（仅文件读写） |
| `nanobot evolve apply <run-id>` | 生成 PR artifact bundle（`pr_body.md` / `diff.patch` / `report.md` 拷贝）至独立目录或 stdout，**不**触碰 git | **否**（仅文件读写 + 模板拼接） |

公共行为（所有子命令）：

1. 共享 typer 全局选项：`--workspace <path>`（默认 CWD）、`--config <path>`（默认 `~/.nanobot/config.json`）、`--verbose / -v`（流输出 DEBUG 日志）、`--quiet / -q`（仅 final 行）。
2. 退出码语义全局一致（详见 §4.6）。
3. 任何子命令首行必须 echo 当前 `nanobot --version` + `evolve_extra_version`（若已装），便于 bug 复盘。
4. `--help` 输出严格遵循 typer 默认渲染；不引入自定义 ASCII art。

### 4.1 `nanobot evolve init`

#### 4.1.1 行为

一次性 bootstrap，在当前 workspace 落盘 M4 必需的目录骨架与 README。**幂等**：重复调用不报错、不覆盖已存在文件，仅补齐缺失项。

落盘行为（按顺序）：

1. `mkdir -p <workspace>/evals/synthetic/` + 写 `.gitkeep`（若不存在）
2. `mkdir -p <workspace>/evals/golden/` + 写 `.gitkeep`（若不存在）
3. `mkdir -p <workspace>/evals/runs/`（不写 `.gitkeep` —— runs/ 整体进 gitignore）
4. 编辑 `<workspace>/.gitignore`：若不存在则创建；按下文算法**同批次**补齐三条必需行：
   - `evals/runs/` — harness 产物（每次 run 写入）
   - `evals/self/` — Tier D self-eval（PII 风险，§5.2 privacy contract #2 / §3.1.5）
   - `evals/sessions/` — Tier B 脱敏会话抽样落地路径（§3.1.3 / §9）
5. 写 `<workspace>/evals/README.md`（仅当不存在时；模板见下）

**`.gitignore` 行匹配算法**（落实 R2 / Y8 / Y7 的共享前提）：

1. 读 `.gitignore` 全文，按 `\n` / `\r\n` 切行，每行 strip 首尾空白。
2. 对每条必需 pattern（`evals/runs/` / `evals/self/` / `evals/sessions/`），检查是否存在一条 strip-后**完全相等**、且非空、非以 `#` 开头的行。
3. **不接受语义等价但字面不同的匹配**：`evals/runs`、`/evals/runs/`、`evals/runs/*` 都**不**视为覆盖了 `evals/runs/`。理由：确定性 + 可幂等检测 > 灵活匹配。
4. 缺失的 pattern 一次性 append 到文件末尾，每条独占一行末尾带 `\n`。写入策略：
   - 读旧内容 → 构造新内容（旧内容 + 缺失行）→ 写 `<path>.tmp` → `os.fsync` → `os.replace(.tmp, .gitignore)`（沿用 `nanobot/agent/memory.py` 的 atomic-write 模式）。
5. **幂等性**：若三条 pattern 已全部满足分支 #2 的匹配，函数早返，**不**重写文件、**不**改 mtime。

`evals/README.md` 模板（约 40 行）覆盖：

- 目录语义说明（`synthetic/` = Tier A、`golden/` = Tier C，cross-ref §3.1.2 / §3.1.4）
- 添加新 record 的流程（手写 `input.jsonl` + `expected.jsonl`，两文件 `record_id` 对齐）
- 与 `tests/eval/` 的差异提示（数据 ≠ 测试代码，pytest 不 collect）
- 链接到本 spec 锚点 `docs/hermes-evolution/specs/m4-offline-skeleton.md#31-4-tier-评测数据-schema`

#### 4.1.2 标志

无必填标志。可用全局 `--workspace` / `--config`。

#### 4.1.3 输出与退出码

```
$ nanobot evolve init
nanobot 0.x.y · evolve extra: 2.5.3 / 0.3.1
[init] created  evals/synthetic/.gitkeep
[init] created  evals/golden/.gitkeep
[init] created  evals/runs/
[init] updated  .gitignore (+3 lines: evals/runs/, evals/self/, evals/sessions/)
[init] created  evals/README.md
done.
```

幂等再跑（全部已存在）：

```
$ nanobot evolve init
nanobot 0.x.y · evolve extra: not installed
[init] skip     evals/synthetic/.gitkeep (exists)
[init] skip     evals/golden/.gitkeep (exists)
[init] skip     evals/runs/ (exists)
[init] skip     .gitignore (already contains evals/runs/, evals/self/, evals/sessions/)
[init] skip     evals/README.md (exists)
done.
```

退出码：`0` = 成功或全幂等命中；`>0` = filesystem error（详见 §4.6 表）。

### 4.2 `nanobot evolve run <skill-name>`

#### 4.2.1 行为

主进化入口。流程：

1. 解析 `<skill-name>`，从 `<workspace>/skills/agent/<skill-name>/SKILL.md` 加载 `Baseline`（§3.2）
2. 加载 `--tiers` 指定的评测数据（§3.1）
3. 跑 `--iterations` 轮 GEPA 优化，每轮产生若干 `Candidate`
4. 对每个 candidate 跑 §3.3 judge pool → `JudgeConsensus`，聚合得 fitness
5. 顺序执行 `GATES`（§3.6），首个 fail 即 short-circuit
6. 选出 fitness 最高且全 gate pass 的 `promoted_candidate`
7. 写 `<workspace>/evals/runs/<run_id>/manifest.json` + `report.md` + `judge_log.jsonl` + `gates/*.json`
8. 若 `--no-dry-run` 且 `final_status == "promoted_to_pr"` → 调 `pr_writer` 生成 `diff.patch` + `pr_body.md` 到 `<run-id>/pr/`；否则 dry-run（默认）仅输出 manifest/report，**不**生成 PR artifact

#### 4.2.2 标志

| 标志 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `<skill-name>` | positional | — | 必填；目标 agent-tier skill 名（必须存在于 `<workspace>/skills/agent/`） |
| `--tiers` | csv string | `A,C` | 启用 tier 列表；私有 tier（B、D）必须**显式**列出。值集 `{A,B,C,D}` |
| `--iterations` | int | 5 | GEPA 迭代轮数（≥1） |
| `--seed` | int | None（自动） | 随机种子；省略时 harness 生成并写入 manifest 的 `gepa_seed` 字段供复现 |
| `--judge-pool` | csv string | `agents.defaults.evolve.default_judge_pool` | 形如 `anthropic/claude-3-5-sonnet,openai/gpt-4o,google/gemini-1.5-pro`；**长度必须为奇数**（决策 #81），偶数 → exit 2。如需单 judge dev 模式，传单个名字（如 `--judge-pool anthropic/claude-3-5-sonnet`，长度 1 是合法的奇数） |
| `--dry-run` / `--no-dry-run` | bool flag | `--dry-run`（即 True） | 控制是否生成 PR artifact；默认 `--dry-run`（仅写 manifest/report）；`--no-dry-run` 触发 `pr_writer` 生成 `diff.patch` + `pr_body.md`，但**绝不**自动 commit / push / merge（§8） |

互斥矩阵：M4 CLI 不再设置任何二元 flag 互斥对。`--dry-run` / `--no-dry-run` 是 typer 内置的 boolean flag pair（同名两个 flag 中 typer 仅取最后出现者，无歧义）。

> 注 1：M4 取消了 `--apply` / `--single-judge` / `--rubric-weights` / `--no-cache-compat-gate` 这四个 flag。
> - `--apply` 与 `--no-dry-run` 同语义重复 → 仅保留后者。
> - `--single-judge` 与 `--judge-pool` 同语义重复（单 judge = `--judge-pool <single-name>`，长度 1 合法）→ 删除。
> - `--rubric-weights` 是稳定调参参数，归 `EvolveDefaults.rubric_weights`；实验者改 config，不改 CLI。
> - `--no-cache-compat-gate` 是危险的 dev 后门（与 `--no-dry-run` 同启会让未审产物进 PR）→ 删除。需本地临时跳过 gate 3 的开发者，在 `nanobot/evolve/gates/__init__.py` 中注释掉 `CacheCompatGate()` 一行（grep-able 改动，PR 时显眼），CLI 不开此口子。

#### 4.2.3 输出

stdout 流式输出（`--quiet` 时仅 final 行）：

```
$ nanobot evolve run refactor-helper --tiers A,C --iterations 5 --no-dry-run
nanobot 0.x.y · evolve extra: 2.5.3 / 0.3.1
[run] skill=refactor-helper baseline_hash=7f3a9e2b1c4d
[run] tiers=[A, C]  records: A=30  C=8  total=38
[run] judge_pool=[anthropic/claude-3-5-sonnet, openai/gpt-4o, google/gemini-1.5-pro] (size=3)
[run] seed=auto:42139871

[iter 1/5] candidates=4  best_fitness=0.612  baseline_fitness=0.581
[iter 2/5] candidates=4  best_fitness=0.674  baseline_fitness=0.581
[iter 3/5] candidates=4  best_fitness=0.701  baseline_fitness=0.581
[iter 4/5] candidates=4  best_fitness=0.703  baseline_fitness=0.581
[iter 5/5] candidates=4  best_fitness=0.711  baseline_fitness=0.581

[gate 1-test-pass]      pass    (golden 8/8 strict, synthetic 30/30 judge_only)
[gate 2-size-cap]       pass    (chars Δ=+312 / +4.1%, tokens_est Δ=+87 / +5.0%)
[gate 3-cache-compat]   pass    (stable_hash unchanged: a1b2c3d4e5f6)

[summary]
  final_status:        promoted_to_pr
  promoted_candidate:  9e8d7c6b5a4f
  fitness_delta:       +0.130 (+22.4%)
  median_aggregate:    0.711 (process=0.78, output=0.74, token=0.62)
  consensus_split:     2 / 38 records
  pr_artifact:         <workspace>/evals/runs/2026-06-12T08:30:00Z-a1b2c3d4/pr/

manifest: <workspace>/evals/runs/2026-06-12T08:30:00Z-a1b2c3d4/manifest.json
```

dry-run（默认）行尾差异：`pr_artifact: (skipped: dry-run; pass --no-dry-run to generate)`。

#### 4.2.4 退出码

`0` = run 完成（任意 `final_status`，含 `rejected_by_gate` / `no_improvement`）；其余见 §4.6。**重要**：gate fail 不是 CLI error —— gate 是业务判定，run 本身成功；用户应读 manifest 的 `final_status` 字段判分流。

### 4.3 `nanobot evolve report <run-id>`

#### 4.3.1 行为

只读子命令：打印 `<workspace>/evals/runs/<run-id>/report.md` 至 stdout。

**Run-id 解析规则**（`report` / `apply` 共用，统一在 `nanobot/evolve/harness.py:_resolve_run_id()` 中实现）：

1. 位置参数可以是 (a) 完整 `<UTC ISO>-<8-hex>` 字符串，或 (b) 8-hex 后缀的任意长度 ≥ 4 的 hex 前缀。
2. CLI 通过扫描 `<workspace>/evals/runs/` 子目录名解析前缀。
3. **前缀长度 < 4**：exit 2（`ConfigError`），提示 "run-id prefix must be ≥ 4 hex chars to disambiguate"。
4. **前缀匹配 ≥ 2 个 run 目录**：exit 2（`ConfigError`），错误消息列出所有匹配 run-id。
5. **前缀无匹配**：exit 6（fs/state，`FileNotFoundError` 映射），错误消息列出 `<workspace>/evals/runs/` 路径。
6. 完整 8-hex 后缀（构造时由 ULID-suffix 随机区分）保证全局无碰撞，不会进入分支 #4。

#### 4.3.2 标志

| 标志 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `<run-id>` | positional | — | 与 `--latest` 互斥之一必填 |
| `--latest` | flag | False | 跳过 `<run-id>` 解析，自动选 `<workspace>/evals/runs/` 下 `started_at` 最新者 |

> 注：M4 删除了 `--format json` 标志。`report` 始终 cat `report.md`；调用方需 JSON 时直接 `cat <run-id>/manifest.json` 即可。当出现具体 CI consumer 需要单接口同时拿到 report 文本 + manifest 字段时再加 JSON 渲染。

#### 4.3.3 退出码

`0` = 找到并打印；`2` = run-id 前缀长度 < 4 或前缀歧义；`6` = run-id 前缀无匹配（§4.6 / §4.3.1）。

### 4.4 `nanobot evolve apply <run-id>`

#### 4.4.1 行为（**关键安全契约**）

生成 PR artifact bundle 到独立目录，**完全不触碰 git / 网络 / 子进程**。

**负契约（hard ban，由 `tests/evolve/test_apply_contract.py` AST 检查 `nanobot/evolve/deploy/**/*.py` 强制）**：

- **禁止网络 I/O**：禁止顶层或函数内 import `requests` / `httpx` / `urllib.request` / `urllib3` / `aiohttp` / `socket`（顶层）/ 任何 GitHub SDK / 任何 HTTP client。AST 检测 + ruff 自定义规则（如可用）。
- **禁止进程生成**：禁止 import / 调用 `subprocess` / `os.system` / `os.execvp` / `pty.spawn` / `multiprocessing.Process`。
- **禁止 git 工具调用**：上一条已覆盖 `subprocess`，但同时白名单层面也 ban `git` / `gh` / 任何 VCS CLI 字符串。
- **禁止改 SKILL.md**：`<workspace>/skills/agent/<name>/SKILL.md` 路径在 `nanobot/evolve/deploy/**` 内的 write/append/replace 操作全部禁止。
- **禁止调 GitHub API**：不创建 branch、不 push、不开 PR、不打 label。

**正契约（唯一允许的副作用）**：

- 仅做：读 `<run-id>/manifest.json` → 模板拼接 `pr_body.md` → 拷贝 `report.md` + `diff.patch` 到 `--output-dir`。
- `apply` **仅**允许通过 `pathlib.Path.write_text` / `write_bytes` / `mkdir` / `shutil.copytree` 在 `--output-dir` 子树内写文件。任何指向 `--output-dir` 之外的写路径均 fail。

测试模块文件路径硬锁 `tests/evolve/test_apply_contract.py`。

落实路线图 §6 约束 4 + §0.4 第 4 行；详细模板见 §8.3。

唯一作用：把已生成的 artifact 重新输出为可手动使用的 PR 包（CI 流水线可拉走 → 调外部 PR-creation 工具，但此命令本身**不参与**）。

调用结束打印明确 hint：

```
to merge: open PR manually using <output-dir>/pr_body.md
nanobot evolve apply DOES NOT touch git, branches, or remotes by design.
```

#### 4.4.2 标志

| 标志 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `<run-id>` | positional | — | 必填；与 `evolve report` 同 prefix 解析规则 |
| `--output-dir` | path | `<workspace>/evals/runs/<run-id>/pr.bundle/` | bundle 输出目录；不存在则创建。**注意**与 `evolve run --no-dry-run` 写入的 `<run-id>/pr/` 是**不同**目录：`pr/` 是 run 进程内写的就地 artifact，`pr.bundle/` 是 `apply` 子命令导出的独立打包目录（供下游 CI / 手工 PR 拉走）。两路径分离避免 `apply` 与 `run --no-dry-run` 之间的写冲突 |
| `--force` | flag | False | 允许覆盖已存在的 output-dir（默认报错 exit 5） |

> 注：M4 删除了 `--format json` 标志。`apply` 始终输出标准多文件目录；目录本身就是 machine-readable（CI 直接读 `pr_body.md` / `diff.patch` / `manifest.json`），无需再封一层 JSON。

#### 4.4.3 前置校验

| 检查 | 失败时 |
|---|---|
| run-id 前缀长度 / 唯一性（§4.3.1 算法） | exit 2（长度 < 4 或歧义）；exit 6（无匹配） |
| `<run-id>/manifest.json` 可解析 | exit 6（fs/state） |
| `manifest.final_status == "promoted_to_pr"` | exit 5（非 promoted） |
| `manifest` 通过 §3.7.1 「无 PII」不变量（`pr_writer` 二次扫描） | exit 4（`ManifestPrivacyViolation`） |
| `--output-dir` 已存在且 `--force=False` | exit 5（`FileExistsError`） |

#### 4.4.4 退出码

成功返回 `0`；失败分类详见 §4.6 全表。本子命令**永不**触发 `BaselineMismatch`（exit 7）或 `JudgeError`（exit 5），那两类异常只可能在 `evolve run` 中出现。

### 4.5 Config 字段（`agents.defaults.evolve.*`）

落实 §0.2 #75 / #76 / #79；新增字段定义在 `nanobot/config/schema.py`，挂于现有 `AgentDefaults` 模型下的新 `EvolveDefaults` 子模型。

```python
# nanobot/config/schema.py（M4 plan 期落地的 delta）
# Base、ConfigDict、Field、field_validator、model_validator 由本文件 §schema preamble 已导入。
from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
# Base 来自本文件第 21 行；EvolvePrivacyConfig / EvolveDefaults 须继承 Base 而非 BaseModel，
# 以继承 `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)`，
# 保证 JSON 配置中的驼峰别名（sessionDbEnabled / selfEvalEnabled / defaultJudgePool /
# rubricWeights / allowedUrlHosts）能被正确接受。

class EvolvePrivacyConfig(Base):
    """Tier B 脱敏管线的可调项；落实 §9。"""

    # frozen=True：构造后字段不可变，避免运行时被悄悄改写；
    # 与 Base 的 alias_generator / populate_by_name 合并写在同一 ConfigDict。
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )

    allowed_url_hosts: list[str] = Field(default_factory=list)
    """白名单 host 列表；URL host 不在此 → §9 redactor 改写为 [REDACTED:URL]。"""

    # M4 删除 `custom_redactor` 字段：YAGNI。M4 ships 的内置 PII 规则（§9）已覆盖全部
    # 已知场景；插件 hook 在出现真实用户请求时再引入。

class EvolveDefaults(Base):
    """`agents.defaults.evolve.*`；M4 新增。所有字段默认值保守，禁开私有 tier。"""

    # frozen=True：rubric_weights / default_judge_pool 等是稳定调参参数，
    # 一经 load 不应被运行时代码 mutate；想 override 必须调
    # `EvolveDefaults.model_copy(update={...})` 重新构造 + 触发 validator。
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=True,
    )

    session_db_enabled: bool = False
    """Tier B 总开关（决策 #75）；默认 False = 离线 lane 不读 SessionDB。"""

    self_eval_enabled: bool = False
    """Tier D 总开关；默认 False = `record_self_eval` API 调用变 no-op + warn log。"""

    default_iterations: int = Field(default=5, ge=1, le=50)
    """`evolve run --iterations` 默认值；上限 50 防失控。"""

    default_judge_pool: list[str] = Field(default_factory=lambda: [
        "anthropic/claude-3-5-sonnet",
        "openai/gpt-4o",
        "google/gemini-1.5-pro",
    ])
    """`evolve run --judge-pool` 默认值；长度必须为奇数（决策 #81）。
    选 3 家不同 provider 是为最大化模型 bias 解耦（同家族模型间相关性更高）。"""

    rubric_weights: dict[str, float] = Field(default_factory=lambda: {
        "process": 0.4,
        "output": 0.4,
        "token": 0.2,
    })
    """`RubricScore.aggregate` 加权；和必须 == 1.0（容差 1e-6），key 必须是 {process,output,token}。"""

    privacy: EvolvePrivacyConfig = Field(default_factory=EvolvePrivacyConfig)
    """脱敏管线配置；详见 §9。"""

    @field_validator("default_judge_pool")
    @classmethod
    def _odd_pool_size(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("default_judge_pool must have ≥1 entry")
        if len(v) % 2 == 0:
            raise ValueError(
                f"default_judge_pool size must be odd (got {len(v)}); "
                "even sizes break median consensus per decision #81"
            )
        return v

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "EvolveDefaults":
        keys = set(self.rubric_weights.keys())
        if keys != {"process", "output", "token"}:
            raise ValueError(
                f"rubric_weights keys must be exactly {{process,output,token}}; got {keys}"
            )
        total = sum(self.rubric_weights.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"rubric_weights must sum to 1.0; got {total}")
        return self

# 挂载点：nanobot/config/schema.py 现有的 AgentDefaults 类（M4 不重定义，仅追加字段）
# class AgentDefaults(Base):  # 既有定义，不在此重复
#     ...（已有字段不动）
#     evolve: EvolveDefaults = Field(default_factory=EvolveDefaults)
# M4 plan 期：在 schema.py 内**编辑** AgentDefaults 类追加 `evolve` 字段；
# 本 spec **不**重定义 AgentDefaults（避免与既有 schema 类同名冲突）。
```

字段速查表：

| 字段 | 类型 | 默认 | Validator | Cross-ref |
|---|---|---|---|---|
| `session_db_enabled` | bool | `false` | — | §3.1.3 / §9 / §0.4 #5 |
| `self_eval_enabled` | bool | `false` | — | §3.1.5 / §5.2 |
| `default_iterations` | int | 5 | `1 ≤ n ≤ 50` | §4.2.2 |
| `default_judge_pool` | list[str] | 3 家不同 provider | 长度奇数 | §3.3 / 决策 #81 |
| `rubric_weights` | dict | `{0.4,0.4,0.2}` | 键集 + 求和 == 1.0 | §3.3 / §0.2 #79 |
| `privacy.allowed_url_hosts` | list[str] | `[]` | — | §9 |

CLI 标志 → config 优先级（从高到低）：CLI flag > `--config` 指定文件 > `~/.nanobot/config.json` > `EvolveDefaults` 内置默认值。

### 4.6 退出码全表（**新决策 #82**）

为让 CI / 自动化脚本可分流处理不同失败模式，M4 锁定退出码语义：

| Code | 含义 | 触发场景 |
|---|---|---|
| `0` | 成功（含业务判定为 reject 的 run） | run/init/report/apply 正常完成；gate fail 不映射到非零 |
| `1` | 通用错误（兜底） | 未分类的 Python 异常（不属于 2/3/4/5/6/7 任一类） |
| `2` | Harness 配置错误 | `rubric_weights` 不合规 / `judge_pool` 偶数 / `iterations < 1` / run-id 前缀长度 < 4 / 前缀歧义 |
| `3` | `EvolveExtraNotInstalled` | 未装 `nanobot[evolve]`，`evolve run` 调用 |
| `4` | 隐私 / 安全 gate 违例 | `ManifestPrivacyViolation` |
| `5` | 资源未找到 / 外部 provider 失败 | run-id 前缀无匹配（FileNotFoundError）/ `final_status != promoted_to_pr` 时 `apply` / `JudgeError`（aux provider 调用失败） |
| `6` | Filesystem / 状态错误 | `init` 无法 mkdir / `.gitignore` 无法写入 / `<workspace>/evals/runs/` 不存在 |
| `7` | Harness invariant 违反 | `BaselineMismatch`（候选 `parent_baseline_hash` ≠ baseline `content_hash`，§3.2 invariant #1）。本码意味着 harness 自身契约破裂，**不**重试，应当抓 trace 报 bug |

**异常 → 退出码的完整映射表见 §5.3**。

**新决策 #82 已追加 §0.3**。CI 分流原则：

- exit 5 → 可能是临时性 provider 抖动，可重试（指数退避）。
- exit 7 → harness invariant 破裂，必须停止重试并向 maintainer 报 bug。
- exit 2 → 调用方参数错，需修改 invocation 再重跑。
- exit 1 → 未分类异常，traceback 应入 CI 日志。

退出码契约同时由 §10 不变量 #6 强制（任何业务路径不得使用未在此表列出的退出码）。

---

## 5. Python API 表面

落实 §0.2 #76 的 API 暴露面；CLI（§4）是其 thin wrapper。所有 public 类 / 函数均从 `nanobot.evolve` 顶层 re-export，`__all__` 列表锁定 stable 表面，未列出的内部模块（`gepa.runner`、`judges.calibration` 等）不视为 public API。

### 5.1 `OfflineHarness` 类

```python
# nanobot/evolve/harness.py
from pathlib import Path
from typing import Optional
from nanobot.config.schema import NanobotConfig

class OfflineHarness:
    """M4 离线进化 pipeline 主入口。

    线程安全：**否**。一个实例对应一次进化运行；并发请实例化多个。
    生命周期：构造廉价，仅做 config 解析；`run()` / `init()` / `apply()`
    分别可独立调用，无隐式状态机。

    与 nanobot 运行时 lane 关系：本类**不**调用 AgentLoop / AgentRunner / 任何
    channel；仅依赖 nanobot.config.loader、nanobot.providers.factory（取 judge model）、
    nanobot.skills.SkillsLoader（读 baseline）。详见 §5.4。
    """

    def __init__(
        self,
        workspace: Path,
        config: Optional[NanobotConfig] = None,
    ) -> None:
        """构造 harness。**廉价**：不读 config 文件、不 import dspy/gepa、不触网络。

        Args:
            workspace: workspace 根目录绝对路径；`evals/` / `evals/runs/` /
                `skills/agent/` 均相对此路径解析。仅检查 `workspace.is_dir()`，
                **不**校验 `~/.nanobot/config.json` 是否存在。
            config: 已加载的 NanobotConfig；省略时在**首次需要 config 的方法**
                （`run()` / `report()` / `apply()`）调用时**惰性**调
                `loader.load_config()`，缓存到 `self._config`。

        Raises:
            ValueError: workspace 路径不是目录

        注意：`__init__` **永不**抛 `ConfigError`。在没有
        `~/.nanobot/config.json` 的全新机器上 `OfflineHarness(workspace).init()`
        必须成功——`init` 是 bootstrap 命令，按定义不依赖运行时 config。
        """

    # 与 `OfflineHarness` 解耦的模块级 bootstrap 函数；CLI `nanobot evolve init`
    # 直接 dispatch 到此函数，**不**经 harness 类。理由：bootstrap 不需要
    # harness 对象、不需要 config、不需要 lazy import — 与主 pipeline 解耦更清晰。
    def init_workspace(workspace: Path) -> None:
        """落地 §4.1 的 bootstrap：创建目录骨架 + .gitignore + README。

        幂等；等价于 CLI `nanobot evolve init`。模块级函数，签名独立于
        `OfflineHarness`，可在 `~/.nanobot/config.json` 缺失时调用。

        Args:
            workspace: workspace 根目录绝对路径

        Raises:
            OSError: 文件系统 I/O 错误（exit 6）
        """

    def run(
        self,
        skill_name: str,
        *,
        tiers: Optional[list[str]] = None,            # 默认 ["A", "C"]
        iterations: Optional[int] = None,              # 默认 config.default_iterations
        seed: Optional[int] = None,                    # None → harness 自动生成
        judge_pool: Optional[list[str]] = None,        # 默认 config.default_judge_pool
        rubric_weights: Optional[dict[str, float]] = None,
        dry_run: bool = True,                          # 默认 dry-run（与 CLI 一致）
    ) -> "RunManifest":
        """跑一次完整离线进化。等价于 CLI `nanobot evolve run`。

        Returns:
            RunManifest: §3.7 定义；含 final_status 字段供调用方分流。
            注意：即使 final_status == 'rejected_by_gate'，本方法**返回**而非
            抛错；调用方需读字段判分流。例外见 Raises。

        Raises:
            EvolveExtraNotInstalled: 未装 `nanobot[evolve]`（lazy import 触发）
            BaselineMismatch: 候选 `parent_baseline_hash` ≠ 配对 `Baseline.content_hash`
                （§3.2 「配对不变量」#1：`Candidate.parent_baseline_hash == Baseline.content_hash`）
            JudgeError: provider 失败到 quorum 不足或 require_consensus=True 时 split。
                **Retry contract**：每个 judge 调用使用 tenacity-style 指数退避，最多
                3 次尝试，2s / 4s / 8s 延迟；重试触发条件：
                  - `httpx.HTTPStatusError`，status ∈ {429, 500, 502, 503, 504}
                  - `httpx.ReadTimeout`
                  - `httpx.ConnectError`
                3 次仍失败 → 该 judge **标记为本 run 不可用**（不立刻抛），加入
                `RunManifest.judge_pool_health[<model>] = "unavailable:<reason>"`。
                run 继续以缩减的 pool 评分；如此后任一 record 评分时
                  - `len(available_judges) < 1`，或
                  - 可用 judges 数 < `JudgePool.min_quorum`
                即抛 `JudgeError`，附 per-judge 尝试日志。否则降级运行直到 run 完成，
                `judge_pool_health` 保留退化轨迹供事后分析。
                映射到 CLI exit 5（外部 provider 失败，可重试）。
            ManifestPrivacyViolation: manifest 含 §3.7.1 禁字段
            ConfigError: tier 列表含未知值 / iterations < 1 / pool 偶数等
        """

    def report(self, run_id: str) -> str:
        """读取并返回某 run 的 `report.md` 文本。等价于 CLI `nanobot evolve report`。

        Args:
            run_id: 完整 ID 或 8-hex 后缀的 ≥4-hex 前缀（前缀唯一即可，
                详细解析规则见 §4.3.1）

        Returns:
            报告文本（unicode str）

        Raises:
            ConfigError: run-id 前缀长度 < 4 或前缀歧义（exit 2）
            FileNotFoundError: run-id 前缀无匹配（exit 6）
        """

    def apply(
        self,
        run_id: str,
        *,
        output_dir: Optional[Path] = None,             # 默认 <run_id>/pr.bundle/（与 run --no-dry-run 写的 <run_id>/pr/ 解耦，避免冲突）
        force: bool = False,
    ) -> Path:
        """生成 PR artifact bundle 到独立目录。**绝不**触碰 git。

        等价于 CLI `nanobot evolve apply`；详细契约见 §4.4 / §8。

        Returns:
            Path: bundle 目录绝对路径（含 pr_body.md / diff.patch / report.md 拷贝）

        Raises:
            ConfigError: run-id 前缀长度 < 4 或前缀歧义（exit 2）
            FileNotFoundError: run-id 前缀无匹配（exit 6）
            ValueError: manifest.final_status != 'promoted_to_pr'（exit 5）
            ManifestPrivacyViolation: manifest 含 §3.7.1 禁字段（exit 4）
            FileExistsError: output_dir 已存在且 force=False（exit 5）
        """
```

**实例语义**：

1. 一个 `OfflineHarness` 实例对应一个 workspace + config 组合；可重复调 `run()`（产生独立 `run_id`）。
2. 不持有跨 `run()` 调用的状态（无 cache、无连接池）；每 `run()` 重新 lazy-import dspy/gepa、重建 provider client。
3. 不重入 / 不并发：构造便宜，并发场景请独立实例化（每实例独立 `run_id`，文件互不冲突）。
4. **`config` 参数的合法调用者**：仅 (a) pytest fixtures，(b) CLI thin wrapper（`nanobot/cli/commands.py`）。生产代码应当传 `config=None` 并依赖惰性加载；显式注入仅为测试与命令分发服务。

### 5.2 `record_self_eval` 工具函数

Tier D（§3.1.5）的写入入口；典型用法：在集成测试 / agent task 代码内调用，落盘 `<workspace>/evals/self/<task_id>/{input,output,verdict}.json`。

```python
# nanobot/evolve/__init__.py
from pathlib import Path
from typing import Optional

def record_self_eval(
    task_id: str,
    input: dict,
    output: dict,
    verdict: dict,
    *,
    workspace: Optional[Path] = None,
) -> None:
    """记录一条 Tier D self-eval 样本。

    Args:
        task_id: 任务唯一 ID（调用方自定，建议 ULID 或 UUIDv7）
        input: skill 入参 payload；落 `input.json`
        output: skill 实际输出；落 `output.json`
        verdict: 自评结论；**必须**含 `passed: bool` 字段（§3.1.5 binary_verdict）
        workspace: 落盘根目录；省略时按
            `<CWD>/evals/self/` → `~/.nanobot/evals/self/` 优先级解析

    Behavior when self_eval_enabled = False:
        若 config 的 `agents.defaults.evolve.self_eval_enabled == False`（默认）→
        本函数变为 no-op（仅 log 一条 warning），**不**落盘。理由：避免在用户未
        知情时累积 task 现场 PII。要启用必须显式开 config flag。
        Warning 通过 `logging.getLogger("nanobot.evolve.self_eval")` 发出，
        **每进程最多一次**（模块级 `_warned: bool` 标志位防 spam）。

    Atomicity & concurrency contract:
        - 三个文件（`input.json` / `output.json` / `verdict.json`）各自走
          `<path>.tmp` → `os.fsync(fd)` → `os.replace(<path>.tmp, <path>)`
          原子落盘（沿用 `nanobot/agent/memory.py` 模式）。
        - **跨文件原子性不保证**：同一 `task_id` 的并发调用 reader 可能观测到
          run N 的 `verdict.json` 与 run N+1 的 `input.json` 共存。契约要求调用方
          **每次调用使用全新 `task_id`**（建议 `ulid.new()` 或 `uuid.uuid7()`），
          复用 `task_id` 时三文件 last-writer-wins **per file**，无锁。
          锁定会破坏 `self_eval_enabled=False` 静默 no-op 路径的低开销特性。

    Directory creation:
        当 `self_eval_enabled=True` 且 `<workspace>/evals/self/<task_id>/` 不存在 →
        函数在三文件 atomic-write 之前调
        `target_dir.mkdir(parents=True, exist_ok=True)`。这是为了处理用户开 Tier D
        但未跑 `evolve init` 的边角场景（`evals/self/` 父目录缺失）。
        **重要**：自动 `mkdir` 不是 `evolve init` 的替代——init 还写 `.gitignore` 条目；
        缺少 init 的 Tier D 启用会让 `evals/self/` **未** gitignore，**有 PII 进库风险**。

    Precondition guard:
        函数入口先做 `.gitignore` 校验：若 `<workspace>/.gitignore` 存在但**不**
        包含 `evals/self/`（按 §4.1.1 行匹配算法精确匹配）→ 抛
        `ManifestPrivacyViolation("Tier D enabled but evals/self/ is not gitignored; "
        "run `nanobot evolve init` first")`，**不**落盘。

    Raises:
        ValueError: verdict 缺 'passed' 字段或非 bool 类型
        ManifestPrivacyViolation: `.gitignore` 缺 `evals/self/` 行（precondition）
        OSError: 文件系统错误
    """
```

**隐私契约（§9 落实）**：

1. `input` / `output` / `verdict` **永不**进 `evals/runs/` 任何 manifest（§3.7.1 不变量）；harness 加载 Tier D 时仅传 `record_id` 给 judge / gate。
2. `<workspace>/evals/self/` 路径必须**已**在 §4.1 init 时由 harness 加入 `.gitignore`（具体行：`evals/self/`，与 `evals/runs/` / `evals/sessions/` 同批次写入，§4.1.1 步骤 4）。`record_self_eval` 在入口处对此做精确-行匹配检查，缺失 → `ManifestPrivacyViolation`（详见 §5.2 Precondition guard）。
3. config flag 默认关 → API 静默 no-op，避免无意识 PII 累积。

### 5.3 异常族（`nanobot/evolve/exceptions.py` 完整列表）

所有 M4 自定义异常集中在此模块；继承自标准库语义最近的基类，以便调用方既能用 `try/except` 精确捕获，也可用 `ImportError` / `ValueError` 等基类兜底。

```python
# nanobot/evolve/exceptions.py
class EvolveExtraNotInstalled(ImportError):
    """未装 `pip install nanobot[evolve]`，DSPy / GEPA 不可用。"""
    INSTALL_HINT = "pip install nanobot[evolve]"

class BaselineMismatch(ValueError):
    """Candidate.parent_baseline_hash != Baseline.content_hash
    （§3.2 配对不变量 #1）。M4 映射到 CLI exit 7（harness invariant 违反）。"""

# 注：M4 **不**引入 `GateRejected` 异常类。M4 的设计是「gate 业务判定走 RunManifest
# 返回值」（`final_status == 'rejected_by_gate'`），不抛异常。`strict_gates=True`
# 扩展点（让 `run()` 在 gate fail 时抛 `GateRejected`）**延后到 M5**：M5 在引入
# `gate 4 / gate 5` 时同步加该异常类，避免 M4 留死代码。

class JudgeError(RuntimeError):
    """Judge pool 调用失败（provider error，3 次重试后仍失败 → 详见 §5.1
    retry contract）或 `JudgePool.require_consensus=True` 时 consensus split。"""

class ManifestPrivacyViolation(RuntimeError):
    """manifest 内出现 §3.7.1 禁字段；阻断 PR 生成（§4.4 / §8）。"""

class ConfigError(ValueError):
    """`EvolveDefaults` / `RubricWeights` / CLI 参数互斥违反等。"""
```

异常 → CLI 退出码映射（与 §4.6 一一对应）：

| 异常 | CLI exit code | 子命令 | 重试建议 |
|---|---|---|---|
| `EvolveExtraNotInstalled` | 3 | `run` | 不重试，需 `pip install nanobot[evolve]` |
| `ConfigError` | 2 | 任意 | 不重试，需修改 invocation / config |
| `JudgeError` | 5 | `run` | **可重试**（指数退避；详见 §5.1 retry contract） |
| `FileNotFoundError`（run-id 前缀无匹配） | 6 | `report` / `apply` | 不重试，run 真的不存在 |
| `ManifestPrivacyViolation` | 4 | `run` / `apply` | 不重试，需修复 manifest 生成代码 |
| `BaselineMismatch` | 7 | `run` | **绝不重试**，harness invariant 破裂，报 bug |
| `OSError` | 6 | `init` / 任意 | 视情况（磁盘满 / 权限）人工处理 |

未在表中列出的 Python 异常 → 兜底 exit 1（CLI traceback 入日志）。

### 5.4 与 nanobot 现有 API 的关系（解耦边界）

落实 §1.3 解耦原则。M4 离线 lane 与 nanobot 运行时 lane 严格分离：

#### 5.4.1 M4 **依赖**的 nanobot 模块（白名单）

| 模块 | 用途 | 调用形态 |
|---|---|---|
| `nanobot.config.loader` | 加载 `~/.nanobot/config.json` → `NanobotConfig` | `OfflineHarness.__init__` 内调 `load_config()` |
| `nanobot.config.schema` | `EvolveDefaults` / `EvolvePrivacyConfig` 字段挂载 | M4 plan 期添加新 Pydantic 模型 |
| `nanobot.providers.factory` | 实例化 judge model client（aux provider） | `judges.llm_judge.LLMJudge.__init__` 内调 `get_provider(model_str)` |
| `nanobot.skills.SkillsLoader` | 加载 baseline `<workspace>/skills/agent/<name>/SKILL.md` + 解析 frontmatter | `harness._load_baseline()` 内调 |
| `nanobot.session.redactor`（M4 plan 期新增的 facade module） | Tier B 抽样脱敏：唯一被允许从 evolve 包 import 的 `nanobot.session.*` 入口 | `privacy/redactor.py` 内 `from nanobot.session.redactor import read_redacted_records` |

#### 5.4.2 M4 **绝不**依赖的 nanobot 模块（黑名单）

| 模块 | 黑名单理由 |
|---|---|
| `nanobot.agent.loop.AgentLoop` | 运行时 lane 入口；M4 不跑 agent turn |
| `nanobot.agent.runner.AgentRunner` | 同上；M4 不跑 LLM 多轮对话 |
| `nanobot.agent.tools.*` | M4 不执行工具（judge 与 gate 都是 deterministic Python） |
| `nanobot.channels.*` | 离线 lane 无 channel 概念 |
| `nanobot.bus.queue.MessageBus` | M4 同步 pipeline，无消息总线 |
| `nanobot.session.*`（包括所有子模块） | SessionDB 触达**仅**通过新增的 facade `nanobot.session.redactor.read_redacted_records(filters) -> Iterator[dict]`（M4 plan 期落地）；任何 `nanobot.session.<其它>` 一律禁止 import |
| `nanobot.command.*` | 离线 lane 无 slash 命令 |
| `nanobot.api.server` | M4 不暴露 HTTP 接口（路线图明确不引入 HTTP API） |

依赖白/黑名单由 §10 不变量强制。M4 plan 期落地的测试模块：`tests/evolve/test_decoupling.py`，规则如下：

1. **Import 形态覆盖**：测试通过 `ast.parse` 遍历每个 `.py` 的 AST，识别以下全部形态：
   - `import X`（`ast.Import` 节点）
   - `from X import Y`（`ast.ImportFrom` 节点）
   - `from X.A import B`（同上，`module="X.A"`）
   - `import X as Z`（`ast.Import` 节点，`alias.asname` 不为 None）
2. **遍历范围**：`pathlib.Path('nanobot/evolve').rglob('*.py')` —— 包内所有 `.py` 文件无遗漏。
3. **传递闭包检查**：构建 import 图后做 transitive closure。若 `nanobot/evolve/foo.py` import `nanobot.evolve.bar`，而 `bar.py` 顶层 import 黑名单（如 `nanobot.agent.loop`），则 `foo.py` 与 `bar.py` **都**报 fail。
4. **动态 import 检测**：通过 AST 字符串字面量分析检测 `importlib.import_module("nanobot.X")` 与 `__import__("nanobot.X")` 调用；这两种形式同样落入黑名单匹配。
5. **R7 facade 单符号断言**：单独 assert "在 `nanobot/evolve/**/*.py` 任一文件中，`nanobot.session.*` 的 import 唯一合法形态是 `from nanobot.session.redactor import read_redacted_records`"（精确匹配 `module == "nanobot.session.redactor"` 且 names 仅含 `read_redacted_records`）；其它 `nanobot.session.<X>` 任意形态均 fail。
6. **fixture / 文件锚点**：测试模块文件路径硬锁 `tests/evolve/test_decoupling.py`；M5 加 gate 时**不可**改路径。

#### 5.4.3 与 M2 `skill_manage` 的契约

M4 与 M2 共享 `created_by` enum（§3.4.1）：

- M4 仅**追加**新值 `dspy:gepa`；不改 `agent` / `subagent:<id>` / `dream` / `bundled` / `user` 任一已有语义。
- M4 写回的 candidate frontmatter 落盘路径完全等同于 M2（`<workspace>/skills/agent/<name>/SKILL.md`），但**永不**直接写 —— 只通过 `diff.patch` 让人审 merge 触达。
- `<workspace>/skills/agent/<name>/.lock`（M2 落地）：M4 不写 SKILL.md，故不取该锁；未来 M5 若实现自动 commit 必须取锁，本 spec 不涉及。

#### 5.4.4 与 M3 Curator 的契约

M3 / M4 是两条独立 lane（§1.3）：

- M4 不读 M3 的 Curator 状态（如归档标记）；冲突场景由人工 reviewer 在 PR 阶段处理。
- M4 不写 telemetry（M1 落地的 `<workspace>/.nanobot/telemetry.json`）；可读用于 candidate 排序，但本 spec 暂不启用（留给 M5 fitness 加权）。

#### 5.4.5 子模块 `__init__.py` 的 lazy-import 纪律

为让「未装 `evolve` extra 仍可 `import nanobot.evolve` 探针」契约（§3.5.1）逐层成立，下列规则强制：

1. `nanobot/evolve/__init__.py` 顶层**禁止** import `dspy` / `gepa` / `litellm` / `optuna` 或任何 `evolve` extra 内的模块。`OfflineHarness` 类身体内的方法可以 lazy-import。
2. `nanobot/evolve/judges/__init__.py` 同上 — 仅暴露符号（`from .rubric import RubricScore`），重符号在被首次实例化时 lazy-import 重依赖。
3. `nanobot/evolve/gates/__init__.py` 同上 — 仅声明 `GATES: list[Gate]`，其元素的依赖通过子模块按需 import。
4. `nanobot/evolve/deploy/__init__.py` 同上 — 仅做模块 export，业务逻辑在 `pr_writer.py` 内 lazy-import。
5. M4 plan 期落地测试 `tests/evolve/test_no_extra_in_init.py`：用 AST 遍历每个 `__init__.py`，断言 module-level `ast.Import` / `ast.ImportFrom` 节点不出现 `{"dspy", "gepa", "litellm", "optuna"}` 任一名称（或其子模块）。

#### 5.4.6 `__all__` 公共表面

```python
# nanobot/evolve/__init__.py
__all__ = [
    "OfflineHarness",
    "init_workspace",
    "record_self_eval",
    "RunManifest",
    "Candidate",
    "Baseline",
    "RubricScore",
    "JudgeResult",
    "JudgeConsensus",
    "JudgePool",
    "GateResult",
    "EvolveExtraNotInstalled",
    "BaselineMismatch",
    "JudgeError",
    "ManifestPrivacyViolation",
    "ConfigError",
]
```

**`__all__` 名称数：16**（精确计数 — R9 删除 `GateRejected`、R10 新增 `JudgePool`、R8 新增模块级 `init_workspace`）。

未在 `__all__` 列出的模块（`gepa.runner` / `judges.calibration` / `privacy.redactor` 内部细节 / `deploy.pr_writer`）视为 internal，可在 minor 版本变更签名；M5 仅可在 `__all__` 列表上**追加**新名字（如 `GateRejected`、`SemanticFidelityGate`、`HumanReviewGate`），不可删除或改签名（落实 §14 下游契约）。

---

> §4–§5 完。新增决策 #82（CLI exit code 全表）已追加 §0.3。下一节 §6 Gate 详细定义。

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
