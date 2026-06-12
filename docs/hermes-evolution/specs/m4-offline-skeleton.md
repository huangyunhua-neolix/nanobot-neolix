# M4 · 离线骨架（Offline Skeleton）设计 Spec

> **Milestone**：M4（离线进化骨架）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第四阶段。
>
> **状态**：草稿中（2026-06-12，C-rev16 §6 fix-round close-out：闭合 C-rev15 reviewer round 7 条 inline RF —— RF-1 time-box CF-C-rev15-5 close criterion（user adjudication / Arch path-b time-box）+ RF-2/3 dual-filter（`__module__` prefix + `inspect.isabstract`）on `Gate._subclasses` orphan assertion + RF-4 ABC docstring import-ordering & ABC metadata accumulation forward-note + RF-5 `GATE_TIMEOUT_MS_HARD` location forward-marker（M5 gate-4 触发即迁 `_constants.py`）+ RF-6 derivation cross-link comment + RF-7 #122 vs #104 cross-ref distinguisher；新增 1 条 §12.6 entry（CF-C-rev16-1，CF-C-rev15-1 "Round H" trigger 软度，由 RF-1 deadline 一并兜底）；C-rev15 Scope-5 self-aware-non-executing 折叠入 CF-C-rev15-5 / RF-1 hard deadline 不另起 entry；决策 #122 inline-amended（per 决策 #108 amend pattern）。§12 未关闭 ≈ 14 → ≈ 15。§0 决策已锁定，§0–§5 已 4-reviewer 收敛 PASS，body §6 已 7-subsection drafted + C-rev14/15/16 reviewer-fix 三轮落地，§6 仍待 4-reviewer C-rev16 收敛验收，§7+ 待 Round E 起草。前轮 C-rev15 闭合 3 must-fix YELLOW（C-Y1/2/3）+ 6 advisory CF（CF-C-rev15-1..6）+ 决策 #122；C-rev14 闭合 4 RED + 12 must-fix YELLOW（决策 #115–#121）；C-rev13 §6 7-subsection draft（决策 #109–#114）；C-rev11 闭合 1 RED + 6 YELLOW + 2 tighten（决策 #107 / #108 + CF-C-rev11-1/2）。
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
| 82 | CLI 退出码全表（0=ok / 1=generic / 2=config / 3=extra-missing / 4=privacy / 5=JudgeError / 6=fs-or-not-found / 7=harness-invariant / 8=apply-precondition）；gate fail 不映射到非零 | §4.6 | CI / 自动化脚本需可分流不同失败模式（特别是「重试 provider」vs「报 bug」）；gate fail 是业务判定不是 CLI 错误。原 decision #82 of C-rev 只到 exit 7；C-rev2 增设 exit 8（见 #85） |
| 83 | Default judge pool 选 3 家不同 provider（Anthropic Claude 3.5 Sonnet / OpenAI GPT-4o / Google Gemini 1.5 Pro），不重 provider | §4.5 | 同 provider 模型 bias 高度相关；跨 provider 最大化解耦 |
| 84 | `RubricWeights` 为 canonical 权重类型；`EvolveDefaults.rubric_weights` 由 `dict[str, float]` 改为 `RubricWeights`；`RubricWeights` 加入 `__all__`（数 17）；求和不变量由 `RubricWeights._sum_to_one` 单一来源校验，`EvolveDefaults._weights_sum_to_one` 删除 | §3.3 / §4.5 / §5.4.6 | C-rev-3 揭示 Round C-rev 的 `_sum_to_one` 是空 stub（silent no-op），`_validate_aggregate` 也是 stub；统一类型 + 单一 validator 消除 dead code、提升类型安全 |
| 85 [SUPERSEDED-IN-PART-BY #88] | Exit code 8 保留给 `apply` 子命令的前置失败 terminal（`final_status != promoted_to_pr` / `FileExistsError` without `--force`）；exit 5 唯一保留给 `JudgeError`（瞬时可重试） | §4.6 / §4.4.3 / §5.3 | C-rev2 发现 exit 5 同时被瞬时 provider 抖动 + apply 前置失败共用，导致 CI 按 "exit 5 → 重试" 策略对 terminal 失败无限循环；拆分后语义清晰。**被决策 #88 部分 supersede（FileExistsError 移至 exit 6）** |
| 86 | `JudgePool` 重构：`min_quorum: int \| None = None`（哨兵）+ `effective_min_quorum` computed_field 供 runtime 消费；`frozen=True` 与 `RunManifest` / `EvolveDefaults` 对齐；删除 `object.__setattr__` 绕道 | §3.3 / §5.1 retry contract | Round C-rev3 揭示三处结构性问题：`min_quorum=0` 既是「未设」哨兵又是合法值（无法区分 default vs explicit-0）；`object.__setattr__` 在 frozen=False 类上是误导性"future-proof"；非 frozen 类允许运行时偷改 quorum 放宽 §5.1 contract。`int \| None` + `Field(ge=1)` + `@computed_field` 三件套一次性解决 |
| 87 | `RubricWeights` + `RubricScore` 迁出 `judges/rubric.py` → 新模块 `nanobot/evolve/schemas.py`（零-extra-deps：仅 import pydantic + stdlib）。删除 `nanobot/config/_evolve_types.py` + `_import_rubric_weights()` lazy shim；`nanobot.config.schema` 改为直接 `from nanobot.evolve.schemas import RubricWeights`。新增 `tests/evolve/test_probe_no_extra.py` subprocess 探针锁定无-extra import cascade（**C-rev4 RED-1 扩展**：探针 body 增加 `from nanobot.config.schema import NanobotConfig` + `NanobotConfig.model_json_schema()`，强制走 schemas.py 链路；详见 §5.4.5 step 6）。**替代方案考量**：另一种布局是 `nanobot/config/evolve_schemas.py`，让 `nanobot.evolve.judges.rubric` 反向 `from nanobot.config.evolve_schemas import RubricWeights, RubricScore`，依赖箭头按惯例从 optional-extra 指向 core，省去子进程探针。未采纳的理由：M5 阶段预计 `RubricWeights` / `RubricScore` 的扩展消费者将 80% 落在 evolve 侧（per-judge weight override、rubric calibration、judge consensus tuning），核心 config 仅在 `EvolveDefaults.rubric_weights` 一处持有引用；把规范源放在主要消费者所在的包里，避免 M5 时反向再迁回 `nanobot.evolve.*`。子进程探针的成本（一次 fork + 一个 import 链路 assert）远小于届时跨包重命名的代价 | §2.1 / §3.3 / §4.5 / §5.4.5 step 6 | 原方案让 config 加载触发 evolve 子包惰性 import（即便只 import 一行），部分破坏 §3.5.1 「no-extra 探针」契约；schemas.py 是 zero-dep 共享模块，让 `nanobot.config` → `nanobot.evolve.schemas` 单向 import 无副作用。同时消除 `model_rebuild()` / forward-ref 需求 |
| 88 [SUPERSEDES-PART-OF #85] [SUPERSEDED-IN-PART-BY #96] | Exit code 8 narrows to **apply 业务终态 only**（`manifest.final_status != promoted_to_pr`）。`FileExistsError`（`--output-dir` 冲突）移至 exit 6（filesystem family，与 `FileNotFoundError` 同族；调用方可纠正后重试）。**Supersedes 决策 #85 的 FileExistsError 归属**。**C-rev5 (YELLOW-Y1) 注**：tightened `--force` 到真原子 via staging + `os.rename` swap，详见 §4.4.2「`--force` 真原子语义」block。**`--force` atomicity 部分 [SUPERSEDED-BY #96]**（C-rev6 升级为 `renameat2(RENAME_EXCHANGE)` + pre-flight sweep + parent-writable precondition；exit code 归属不变，仅 swap 内部机制升级） | §4.6 / §4.4.3 / §5.3 | CI 分流需要：exit 6 = "filesystem 前置可纠正，调用方可重试"，exit 8 = "业务终态，重跑无意义"。原 #85 把这两类合并 exit 8 后，CI 对 `--output-dir` 冲突按 "terminal" 处理 → 误判，本应只需 `--force` 重试 |
| 89 | Promoted `JudgeConfig` to `__all__`（count 17→18，再叠 #90 → 19）。Kept `EvolveBase` inheritance（不 downgrade `@dataclass`）以吸收 M5 per-judge fields（`timeout_s` / `weight` / `temperature_override`）而无须 ctor migration。同时在 `OfflineHarness.run()` 的 `judge_pool` kwarg 上接受 `list[str] \| JudgePool \| None` union（YELLOW-Y3） | §3.3 / §5.1 / §5.4.6 | C-rev4 收敛：`JudgePool.judges` 元素类型必须 importable；M5 扩展 per-judge 字段在即，dataclass 化会触发 ctor 二进制兼容破坏 |
| 90 | 引入专属异常 `ApplyTerminalError(ValueError)` 替代 `apply()` 中裸 `ValueError → exit 8` 的映射。和 `pydantic.ValidationError`（亦 `ValueError` 子类）解耦，CLI handler isinstance 顺序不再 load-bearing。加入 `__all__`（count 18→19）。**C-rev5 注**：(a) YELLOW-Y2 添加 `test_cli_handler_order.py` 机械化强制 isinstance 顺序 —— 见 §5.3 dispatch-order subsection。(b) YELLOW-Y8 具体消费者：§4.6 CI dispatch 规则使用 `case ApplyTerminalError` / `case ConfigError` / `case ValueError` 风格分派 exit code（详见 §5.3 dispatch-order subsection 与 YELLOW-Y2 引入的 `test_cli_handler_order.py` 强制契约）；这两个具体消费者就在 M4 落地，不是 M5 furniture | §3.5 / §5.1 / §5.3 / §4.6 | C-rev4 YELLOW-Y5：`pydantic.ValidationError` 与 `apply` 业务终态共用 `ValueError` 基类时，CLI handler 的 `isinstance` 顺序决定 exit 2 vs exit 8，未文档化即 load-bearing；专属异常彻底消歧 |
| 91 | M4 plan 期落地 `tests/evolve/test_base_config_frozen.py` 快照测试：锁定 `EvolveBase.model_config` 与 `JudgePool` / `RubricWeights` 的 `frozen` override。任何修改要求同步更新 EXPECTED_* dict + §0.3 新 Decision + roadmap entry。**C-rev5 注 (YELLOW-Y9) 累积成本**：C-rev5 时 M4 已有 5 个 contract/snapshot 测试（`test_no_extra_in_init.py` / `test_probe_no_extra.py` / `test_decoupling.py` / `test_apply_contract.py` / `test_base_config_frozen.py`）。CI 维护成本在可接受范围（合计 < 200 行测试代码 + < 5s 运行时间）；M5 引入新 contract 测试前需评估是否合并到现有文件而非新增 | §3.0 / §5.4.5 | C-rev4 YELLOW-Y4：§3.0 EvolveBase 稳定性公约缺机械化绑定，纯 prose 不可强制；快照测试把 covenant 从文档承诺升级为 CI 拦截 |
| 92 [SUPERSEDED-IN-PART-BY #95] | 通用化 `tests/evolve/test_decoupling.py` 中的 kwargs-only 强制 AST scanner 为 registry pattern（`STRUCTURED_KWARGS`，COH-001 / C-rev7 / Z8 修正：C-rev5 草拟时使用 `STRUCTURED_EXC_KWARGS`，C-rev6 落地时实际命名为 `STRUCTURED_KWARGS`，本表 entry 同步统一）。C-rev3 引入时仅硬编码 `ManifestPrivacyViolation` 一类；C-rev4 引入 `ApplyTerminalError` 同样使用 kwargs-only 构造但无对应强制 → 层间不一致。C-rev5 把扫描器升级为按 registry 驱动；M5 新增结构化-kwargs 异常（如 `GateRejected` / `JudgeQuorumFailure`）需同步登记。**[SUPERSEDED-IN-PART-BY #95]**（C-rev6 把 registry 从测试侧 dict 迁至生产侧 `ClassVar[frozenset[str]]` introspection；测试不再硬编码异常列表；#92 的"AST scanner 通用化为 registry pattern"原始决策范围保留为 #95 范围之外的有效记录） | §5.3 | RED-1 C-rev5：两个同形异常只有一个机械化强制，是层间一致性裂缝；registry 化让"哪些异常是结构化-kwargs"成为单一事实之源 |
| 93 | 抽取 `_assert_odd_pool_size` helper 至 `nanobot/evolve/schemas.py`。`JudgePool._odd_pool_only` 与 `EvolveDefaults._odd_pool_size` 两个 validator 都改为薄 delegate；消除双重错误信息漂移风险。任何关于奇数池规则的改动（M5 若允许 even=2 用于 A/B 测试）只需修改 helper 一处。**Forward-looking（C-rev6 / Y-arch-5）**：若 M5（或任意后续 milestone）引入**第二个**跨模型 validator helper（例如 weight-bounds checker / tier-name normalizer），**必须**同时抽取两个 helper 到新模块 `nanobot/evolve/validators.py`。单 helper 留在 `schemas.py` 是 YAGNI 阈值之内的合理放置；引入第二个 helper 即触发提取，避免 `schemas.py` 长期混入"数据类 + 跨模型规则"两类关注点。Import 调整：相应 validator 调用点改为 module-top `from nanobot.evolve.validators import _assert_odd_pool_size`，与 C-rev6 Y-corr-3 闭合同步落地 | §3.3 / §4.5 | YELLOW-Y4 C-rev5：两个 validator 独立实现同一 parity 规则 + 同形错误消息 = SoT 漂移风险；helper 化让单一事实之源从文档断言（"两处校验语义一致"）升级为代码 delegate |
| 94 [SUPERSEDED-IN-PART-BY #95] | 添加 contract 机械化强制 evolve CLI dispatch 中 `except ApplyTerminalError` 必须在 `except ValueError` / `except ConfigError` 之前。`MUST_PRECEDE` registry 与决策 #95 共同迁至**生产侧 introspection**（C-rev6 / 决策 #95）：M5 新结构化异常入栏时只需在异常类自身声明 `MUST_PRECEDE` ClassVar；测试合并到 `tests/evolve/test_decoupling.py`（不再单独 `test_cli_handler_order.py` 文件） | §5.3 | YELLOW-Y2 C-rev5：决策 #90 让 `ApplyTerminalError` 与 `pydantic.ValidationError` 解耦，但 isinstance 顺序仍 load-bearing（`ApplyTerminalError` 是 `ValueError` 子类）；handler 顺序写反会让 apply 业务终态被静默回归 exit 2，需 CI 拦截。**C-rev6 [SUPERSEDED-IN-PART-BY #95]**（测试侧 `HANDLER_ORDER_RULES` dict + 独立测试文件部分被 #95 替换为生产侧 introspection；contract 本身保留有效，是 #95 范围之外的 #94 残留有效部分） |
| 95 [SUPERSEDES-PART-OF #92] [SUPERSEDES-PART-OF #94] [AMENDED-BY #99] [AMENDED-INLINE C-rev8 / W2] | **生产侧结构化-异常 + handler-order registries（introspection，非测试侧 dict）**：`STRUCTURED_KWARGS` 与 `MUST_PRECEDE` 作为 `ClassVar[frozenset[str]]` 直接声明在异常类自身（`nanobot/evolve/exceptions.py`）。测试 (`tests/evolve/test_decoupling.py`) 通过 `inspect.getmembers` 遍历 `nanobot.evolve.exceptions` 模块，自动发现所有声明 `STRUCTURED_KWARGS` 的类并对其 raise 点做 AST 断言；handler-order 测试同样合并到 `test_decoupling.py`（不再单独文件）。AST scanner 同时改进：(i) 支持 `ast.Attribute` 形态（`raise pkg.mod.Foo(...)`），(ii) 排除 `.venv` / `__pycache__` / `node_modules` / `dist` / `build` / `.tox` / `.nox` / `.mypy_cache` / `.ruff_cache` / `.pytest_cache` 目录，(iii) 增加 `nanobot/evolve/cli/*.py` 的 bare-except 禁令扫描。**C-rev7 / Z2 澄清**：discovery helper 必须用 `cls.__dict__.get("STRUCTURED_KWARGS")` / `cls.__dict__.get("MUST_PRECEDE")`（**非** `getattr`），避免 MRO 继承导致子类被误识为声明者（基类 ClassVar 通过 MRO 渗透 → 子类被错误地加入 raise-point AST 断言集合）；同步增加 `test_must_precede_acyclic` 防止 registry 形成环 | §5.3 / §5.4.2 | C-rev6 闭合：Y-arch-1（registries 测试侧 → 生产侧 SoT 迁移）+ Y-arch-2（misleading "wraps" 注释 + `HANDLER_ORDER_RULES` 命名 → `MUST_PRECEDE_RULES` 重命名）+ Y-scope-2（避免单独 test 文件膨胀，合并到 `test_decoupling.py`）+ Y-corr-1（Attribute-form raises）+ Y-corr-4（bare-except 禁令）+ Y-corr-5（excluded dirs）。**C-rev7 闭合追加**：Y-corr-rev6-3（MRO 渗透 → `cls.__dict__.get()` 修正）+ Y-corr-rev6-4（cycle detection）。**C-rev8 闭合追加 (W2)**：扩展 "RuntimeError-tree MUST_PRECEDE 通用规则"（§5.3 末尾点 7b）—— 任何继承自 stdlib base type 的 evolve 异常**必须**在 `MUST_PRECEDE` 中声明该 base type 名；M4 给 `EvolveEnvironmentError` / `JudgeError` / `ManifestPrivacyViolation` 三类补齐 `MUST_PRECEDE = frozenset({"RuntimeError"})`，闭合 Y-c7-corr-1 |
| 96 [SUPERSEDES-PART-OF #88] [AMENDED-BY #98] [AMENDED-BY #100] [AMENDED-BY #102] [AMENDED-INLINE C-rev8 / W4] | **`--force` 真原子语义升级：`renameat2(RENAME_EXCHANGE)` + pre-flight sweep + parent-writable precondition**。Pre-step 0a: assert `output_dir.parent` writable（**C-rev7 / Z4 强化**：用 `R_OK \| W_OK \| X_OK` access check，并对 iterdir 包 try/except OSError），否则 exit 2。Pre-step 0b: rmtree 任何 `<output_dir>.old-*` / `<output_dir>.staging-*` 残留（前次 crash debris），失败 → exit 2 提示手动清理。Atomic swap: 优先用 `os.rename2(staging, output_dir, flags=RENAME_EXCHANGE)`（Linux ≥ 3.15 + ext4/btrfs/xfs）单 syscall 完成；不支持的平台（macOS、旧内核、tmpfs 等）回退至两步 `os.rename` 并在文档中显式标注 SIGKILL 窗口；下次 `--force` 由 pre-flight sweep 恢复。`shutil.rmtree(<output_dir>.old-*)` 包 try/except 仅 WARN（swap 已成功，残留是 cosmetic）。**C-rev7 / Z1 [AMENDED-BY #98]**：ctypes/libc 探测机制本身提取至 `nanobot/evolve/_atomic_swap.py` helper module（spec 描述合约，不内嵌 ctypes 验证代码）| §4.4.2 / §5.1 `apply` | C-rev6 闭合：Y-corr-2（SIGKILL 窗口）+ Y-arch-3（parent-dir-writable precondition 缺）+ Y-arch-4（`.old-*` silent leak）。决策 #88 / §4.4.2 / §5.1 `apply` 的 atomicity 部分 **[SUPERSEDED-BY #96]**。**C-rev7 闭合追加**：Y-c6-arch-1 + Y-corr-rev6-1 + Y-corr-rev6-2 + Y-corr-rev6-8 + R-impl-1（spec 内嵌 ctypes 代码 → helper module 抽取 #98）+ Y-corr-rev6-7（access mode 强化） |
| 97 | **决策日志 grooming 约定**：见 §0.3.1。superseded 项以 `[SUPERSEDED-BY #N]` 后缀标记保留（不删；audit trail）；milestone 滚动 ≥ 3 个 milestone 才考虑收集到"历史决策"附录；编号 monotonic 不重排；rationale ≤ 5 行 | §0.3.1 | C-rev6 闭合：Y-arch-6（决策日志膨胀治理） |
| 98 [AMENDS #96] [AMENDED-BY #101] [AMENDED-INLINE C-rev8 / W1] [AMENDED-INLINE C-rev9 / W5] [AMENDED-INLINE C-rev11 / RED-1+YELLOW-4] | **`_atomic_swap` helper module 抽取**：所有 `renameat2(RENAME_EXCHANGE)` 探测 + fallback 调度逻辑落在 `nanobot/evolve/_atomic_swap.py`（单文件 helper，使用 `ctypes.util.find_library("c")` 跨平台 libc 解析、`os.fsencode()` 处理 surrogateescape 路径、Linux `RENAME_EXCHANGE = 2` 常量），暴露 `try_atomic_swap(staging: Path, target: Path) -> Literal["renameat2", "fallback"]` 单一入口。Spec §4.4.2 仅描述 helper 合约（输入 / 返回值 / 错误传播 / SIGKILL 窗口标注），**不**内嵌 ctypes 验证片段。Helper module **不**引入新异常类 —— 环境性失败（libc 未找到、syscall ENOSYS 等）走决策 #100 的 `EvolveEnvironmentError`；fs 错误透传裸 `OSError` 由 §4.6 dispatch 表统一处理。**C-rev9 闭合追加 (W5)**：§4.4.2 (c) Test contract 新增两条机械化 test（`test_atomic_swap_postcondition` / `test_atomic_swap_preconditions`），把 contract clause 4 / 6 从"spec 描述层"提升至"CI 拦截层"，闭合 Y-c7-corr-4 | §4.4.2 / §5.1 | C-rev7 闭合：R-impl-1（spec 文本不应包含可执行 ctypes 代码）+ Y-c6-arch-1（mechanism vs contract 边界混淆）+ Y-corr-rev6-1（surrogateescape）+ Y-corr-rev6-2（libc 解析跨平台）+ Y-corr-rev6-8（platform-conditional 测试）。**C-rev9 闭合追加**：Y-c7-corr-4（W5 helper test contract 缺失 → §4.4.2 (c) 新增两条 contract test 锁定 clause 4/6 可观测 outcome） |
| 99 [AMENDS #95] [AMENDED-BY #104] [AMENDED-INLINE C-rev9 / W3 + W10] [AMENDED-INLINE C-rev10 / W1] | **`MUST_PRECEDE` acyclic invariant + `STRUCTURED_KWARGS` no-MRO discovery**：见决策 #95 amend。Discovery 走 `cls.__dict__.get(...)`，DFS cycle detection 在 `test_must_precede_acyclic` 中机械化（含 self-loop + 长环情形）；非完整 contract 名（`raise self.X()` / `raise cls.X()`）由 `_resolve_raised_class_name` 直接拒绝，不进入 raise-point 集合（避免 NoneType 漏判）。**C-rev9 闭合追加 (W3)**：`test_no_self_raises_in_evolve` 升级为 transitive Attribute-chain peel（递归 peel `ast.Attribute.value` 直到 `ast.Name`，根 id ∈ `{"self","cls"}` 即拒），闭合 C-rev7 仅匹配 depth-1 漏放任意深度 `raise self.module.ExcClass(...)` 的盲点；**并新增运行时 backstop** —— 新增基类 `EvolveError` mixin，其 `__init_subclass__` 在导入期校验任何声明 `STRUCTURED_KWARGS` 的子类的 `STRUCTURED_KWARGS` **子集于**其 `__init__` keyword-only 参数集合（必填字段必须声明；可选诊断 kwargs 允许超集；C-rev11 / RED-1 / 决策 #107 amend，前 C-rev9/C-rev10 草拟"严格等于"语义会与 `ManifestPrivacyViolation` 的"必填一项 + 可选两项"设计冲突），截获 AST 不可解析的局部别名形态（`cls_ref = self.exc_cls; raise cls_ref(...)`）。AST 静态 + 运行时双层守卫为 declaration ↔ ctor signature 漂移 defense in depth。新增基类 `EvolveError` mixin **并加入 `__all__`** 作为外部 CI/telemetry `isinstance(exc, nanobot.evolve.EvolveError)` 的稳定 union-type 锚点（见 §5.4.6 line 2553 消费者说明）。**C-rev10 闭合追加 (W1 / Coh-Y2 + Corr-2)**：(a) `expected_all` set in §5.4.5 step 6 添加 `'EvolveError'` 条目（之前漏列会让 two-way equality probe `test_probe_no_extra.py` 在 import 时直接 fail）；(b) `__init_subclass__` backstop 扩展为对子类继承层亦强制 redeclaration —— 若任一基类（`cls.__mro__[1:]` 中、非 `EvolveError` 自身）已声明 `STRUCTURED_KWARGS`，子类的 `cls.__dict__.get("STRUCTURED_KWARGS")` 必须**显式存在**且非 `None`；缺失即 import 期 `TypeError`，与 #95 同条 "no-MRO inheritance" 原则对齐。**C-rev9 闭合追加 (W10)**：`test_must_precede_acyclic` 在 M4 阶段结构上不可能 fail（所有 `MUST_PRECEDE` 目标均为 stdlib base type，evolve-internal 多节点环不存在）；保留作为 M5+ forward-looking 零成本前瞻护栏（M5 计划引入 `GateRejected` / `JudgeQuorumFailure` 等结构化异常将引入 evolve-internal 多节点 edges），不是 dead code | §5.3 | C-rev7 闭合：Y-corr-rev6-3（MRO 渗透 false-positive）+ Y-corr-rev6-4（registry 环检测缺失）+ Y-corr-rev6-6（self/cls raise 解析 silent-pass）。**C-rev9 闭合追加**：Y-c7-corr-2（W3 self-raise transitive chain + 运行时 backstop）+ Y-cycle-test（W10 cycle-test forward-looking framing） |
| 100 [AMENDS #96] [AMENDED-INLINE C-rev8 / W6] | **`EvolveCliError` → `EvolveEnvironmentError` rename + drop `exit_code` 字段（Option A / Z5）**：library 层异常类**不**携带 CLI exit code 字段；exit code 归属由 §4.6 dispatch 表 + §5.3 异常→exit code 映射表是 SoT 决定（本类 → exit 2）。类身份（`isinstance(exc, EvolveEnvironmentError)`）是稳定 anchor，与 `ConfigError` / `ApplyTerminalError` / `JudgeError` 一致 layering。**Alternative B/C 未采纳**：(B) 保留 `exit_code` 字段让 CLI handler 直接消费 → library 层污染 CLI 语义、违反单一职责；(C) 引入 `CliExitCodeMixin` → 过度抽象（M4 仅 1 个 environmental error 类）。Option A 最低增量、最清晰 layering | §4.4.2 / §5.1 / §5.3 / §5.4.6 | C-rev7 闭合：Y-c6-arch-2（exit_code 字段是 CLI 语义泄漏到 library 层）+ Y-c6-arch-3（`EvolveCliError` 命名误导：暗示"CLI 通用错误" 实际仅环境前置）+ Y-corr-rev6-5（dispatch 表 SoT 未明确）。**C-rev8 闭合追加 (W6)**：同 layering 原则的 inline 扩展 —— `OfflineHarness.__init__` 的 ctor-参数校验失败（`workspace.is_dir()` 不通过）从声明抛裸 `ValueError`（落 exit 1 catch-all）改为 `ConfigError`（exit 2），与 `EvolveDefaults` / `JudgePool` ctor 校验同族；library 层 ctor 参数错误 → `ConfigError` 是 §5.3 dispatch 表 SoT 的自然延伸，闭合 Y-c7-corr-5 |
| 101 [AMENDS #98] | **Helper contract vs implementation guidance separation (W1 / C-rev8)**：`_atomic_swap` helper 的 spec §4.4.2 段落明确分为 **(a) Helper contract** 与 **(b) Implementation guidance — known regression guards** 两个清晰小节。(a) 仅描述 caller 可依赖的外部 outcome（portability、path safety、fallback semantics、preconditions、postconditions、return value 共 6 条），用 RFC 2119 MUST / MUST NOT 语气。(b) 列出基于历轮 review 抓到的实现 hint（libc lookup hardening、`os.fsencode` 路径编码、errno 集合等），并冠以"以下细节**不是**契约的一部分"的明示。理由：C-rev6 Z1 / C-rev7 仅把 ctypes 代码块从 spec 抽走，机制 prose 仍渗入"helper 契约"小节 → 一个满足外部行为但实现不同的版本会被误判违约。本决策让 spec 在描述层面与决策 #98 在文件抽取层面**对齐** —— 都以 outcome 而非 mechanism 为契约 anchor | §4.4.2 | C-rev8 闭合：R-impl-1-residue / Y-c7-corr-1（"helper 契约"小节仍混入 mechanism prose） |
| 102 [AMENDS #96] [AMENDED-BY #105] | **并发 `--force` race protection via parent-dir lockfile (W4 / C-rev8 / Option α)**：在 §4.4.2 引入 pre-step 0c 显式锁 —— POSIX `fcntl.flock(LOCK_EX \| LOCK_NB)` on `<output_dir>.lock` sentinel；contention → 立即 raise `EvolveEnvironmentError` → exit 2，不阻塞调用方。锁顺序：0a → 0b → 0c → 主流程；锁持至 step e（cosmetic cleanup）完成。**Alternative β 未采纳**：把 `.staging-*` 命名收紧到含 lock 元数据（如 `.staging-<run_id>-<pid>`）+ 让 0b sweep 只清"无活进程持锁"的目录 —— 复杂度更高、跨平台 PID-liveness 检查易出错（PID 重用 / Docker namespace 隔离 / 容器内 PID 1 永远活）；β 把"锁判活"与"垃圾回收"耦合到同一路径，破坏了 0b sweep 的简单语义（0b 仍按"前次未完结流程的残留即可清"原则）。Windows 用 best-effort PID-stamped `.lock` 文件 + 启动期 PID 活检（有 race window，但 M4 CI 仅 Linux）。**并发契约与 `OfflineHarness.run` 非可重入正交**：后者讲单实例内 `run()` 不可重入；本决策讲跨进程 `apply --force` 写盘序列化（CLI 路径走 `OfflineHarness.apply`，Python API 同共用） | §4.4.2 / §5.1 `apply` | C-rev8 闭合：Y-c7-corr-3（pre-step 0b sweep 在多 `apply --force` 并发下会扫掉同 parent 上另一调用的 in-flight `.staging-*`） |
| 103 [AMENDED-BY #108] | **§0.3.1 marker vocabulary 形式化枚举（Coh-RED1 + Coh-Y3）**：§0.3.1 grooming 约定追加点 6 与点 7，形式化定义 `[SUPERSEDED-BY]` / `[SUPERSEDES-PART-OF]` ↔ `[SUPERSEDED-IN-PART-BY]` / `[AMENDS]` ↔ `[AMENDED-BY]` / `[AMENDED-INLINE C-rev<N> / W<bucket>]` 五种 marker 形态及其 RFC 2119 语义；并明确 W-bucket 命名是**轮内**离散闭合分组（每轮重置、非独立决策 ID、引用必须 `C-rev<N>/W<bucket>` 全限定）。所有双向 marker MUST 在两端点决策同时出现。理由：C-rev9 之前 marker 形态在表中累积演进未文档化，新贡献者无法判定「`[AMENDS]` 与 `[AMENDED-INLINE]` 何时该用哪一个」/「`SUPERSEDED-IN-PART-BY` 是否需要对偶项」/「`W2` 在不同轮次是否同语义」；形式化枚举把"约定"升级为"契约"，PR review 可机械化拒绝缺对偶端的 marker | §0.3.1 | C-rev10 闭合：Coh-RED1（marker vocabulary 未枚举即 ad-hoc）+ Coh-Y3（W-bucket 命名约定未文档化） |
| 104 [AMENDS #99] [AMENDED-BY #107] | **`__init_subclass__` backstop 扩展强制子类 redeclaration（Corr-2）**：`EvolveError.__init_subclass__` 除原 W3 校验（声明 `STRUCTURED_KWARGS` 的子类其 `STRUCTURED_KWARGS` **子集于** `__init__` keyword-only 参数集合，C-rev11 / 决策 #107 把原"严格等于"语义放宽为"子集"，让必填项强制 + 可选诊断 kwargs 允许）外，**新增**：若任一基类（`cls.__mro__[1:]` 中、不含 `EvolveError` 自身）**已声明** `STRUCTURED_KWARGS`，则当前 `cls.__dict__.get("STRUCTURED_KWARGS")` MUST 显式存在且非 `None`；否则导入期 `TypeError`。理由：与决策 #95 / #99 的 "no-MRO inheritance" 原则对齐 —— 既然 discovery helper 用 `cls.__dict__.get(...)`（不沿 MRO 继承），那么"子类继承自一个 STRUCTURED_KWARGS-declaring 父类但自身未 redeclare"必然让子类被排除出 AST 契约扫描，是 silent gap。本扩展把"必须 redeclare"从隐性约定升级为 import-time fail-loud 契约 | §5.3 | C-rev10 闭合：Corr-2（W3 backstop 未覆盖子类层 silent gap） |
| 105 [AMENDS #102] | **Lockfile OSError wrap + NFS 不支持显式声明（Corr-3）**：§4.4.2 pre-step 0c 中 `os.open(lock_path, O_CREAT \| O_RDWR, 0o600)` MUST 包 `try/except OSError → re-raise as EvolveEnvironmentError(f"lockfile create failed: {e}") from e`；与既有 `fcntl.flock` 的 BlockingIOError 包装对齐，避免裸 `OSError` fallthrough 落 unmapped exit 6（破坏 "pre-step 失败 → exit 2" 契约）。同时显式声明：M4 仅支持本地 POSIX 文件系统；**NFS / 网络文件系统在 M4 阶段 unsupported** —— Linux NFS pre-2.6.12 上 `fcntl.flock` 退化为 per-fd 本地锁，无法跨进程互斥；M5 计划用 lockd / fcntl(F_OFD_SETLK) 加固。理由：决策 #102 仅包了 `fcntl.flock` 的 contention 异常；`os.open` 自身的 OSError（路径权限 / parent dir 失踪 / EROFS / ENOSPC）会绕过 dispatch 表落 catch-all。同时未声明 NFS 限制让用户在共享 workspace 场景静默踩坑 | §4.4.2 | C-rev10 闭合：Corr-3（lockfile create 路径 OSError 未映射 + NFS limitation 静默） |
| 106 | **§12 carry-forward register 格式 established by C-rev10（CF-1/CF-2/CF-3）**：§12 carry-forward 章节首批 3 条 entry 落地 —— 由用户 sanctioned 的 Lite + carry-forward 路线（不全 fix 即 RED-block）建立 register 格式：每条 entry 含 `source` (reviewer 名 + bucket-id)、`confidence`（reviewer 自报 % 或定性 "advisory"）、`conflict`（Arch / Corr / Coh / Scope reviewers 之间的判定差）、`defer reason`（为何不在本轮 fix）、`future close criterion`（具体可观测的关闭条件）。CF entries 不是决策 —— 它们是"已意识到但**故意**延后处理"的 reviewer-finding 转储，与 §0.3 决策表语义正交。M5+ 启动时 retro 必须 review 全部未关闭 CF entries；满足 close criterion 的从 §12 移除并在 retro 中记录关闭原因 | §12 | C-rev10 闭合：format establishment for the 3 Scope-reviewer advisories sanctioned for carry-forward by user (CF-C-rev10-1/2/3) |
| 107 [AMENDS #104] | **`__init_subclass__` STRUCTURED_KWARGS 检查放宽：strict-equality → subset semantics（C-rev11 / RED-1）**：`EvolveError.__init_subclass__` 把"`STRUCTURED_KWARGS` 集合**严格等于** `__init__` keyword-only 参数集合"放宽为"`STRUCTURED_KWARGS` **子集于** keyword-only 参数集合"。理由：`ManifestPrivacyViolation` 设计为 `STRUCTURED_KWARGS = frozenset({"violated_invariant"})` 且 `__init__` 含三个 kw-only 参数（`violated_invariant` / `offending_path` / `offending_fields`，后两者是可选诊断字段，故意不进 registry），strict-equality 会让本类在导入期 `TypeError` → 阻断整个 evolve 子系统加载（hard blocker：4-reviewer convergence pass C-rev10 抓出的 RED-1）。Subset 语义保留"必填字段 MUST 出现在 ctor"的 fail-loud 守护（缺失 → import 期 `TypeError` 命名缺失成员），同时允许 ctor 含额外可选 kw-only 参数。Decision #104 的"子类 redeclare"约束保留不变，仅本条 equality vs subset 语义改写。新增 `test_init_subclass_accepts_optional_diagnostic_kwargs` 机械化两端：positive case（subset OK）+ negative case（成员缺失 fail）。**Alternative 未采纳**：(B) 把 `offending_path` / `offending_fields` 加入 `STRUCTURED_KWARGS` 让 strict-equality 通过 → 违反 registry 设计意图（"必填字段"语义被稀释，AST 契约扫描会强制 raise 点全填可选诊断 kwarg）；(C) 在 ctor 上把可选字段从 kw-only 转 positional → 破坏调用站点的命名清晰度，且与 `ManifestPrivacyViolation` 已有调用约定不兼容 | §5.3 / §0.3 | C-rev11 闭合：RED-1（C-rev9 草拟的 strict-equality 与 `ManifestPrivacyViolation` 设计冲突 → 整个 evolve 子系统 import-time crash） |
| 108 [AMENDS #103] | **Marker placement convention + W-bucket 简写禁令（C-rev11 / Tighten-2 + YELLOW-1）**：§0.3.1 enumeration 追加两条 normative rule —— (a) **Placement convention**：`[SUPERSEDED-*]` / `[AMENDED-BY]` MUST 出现在被替代/修订的（旧）决策标题行；`[SUPERSEDES-*]` / `[AMENDS]` MUST 出现在做出替代/修订的（新）决策标题行；任何只有一端 marker 的 PR commit SHOULD 在 review 中被拒。(b) **W-bucket 简写禁令**：早期轮次曾用 `[AMENDED-BY #N via W<bucket> <description>]` 的内联简写 → 跨轮次 W-bucket 编号重用造成歧义；C-rev11 起强制（i）若新决策 #N 已独立存在 → 标题行只写 `[AMENDED-BY #N]`，W-bucket 归属由 #N 自身 narrative 承载；（ii）若编辑幅度仅就地（无新决策）→ 加 `[AMENDED-INLINE C-rev<N> / W<bucket>]` 单端 marker；两形态可叠加（如 #98 同时含 `[AMENDED-BY #101] [AMENDED-INLINE C-rev8 / W1]`）。本轮一并对齐：#96 markers `[AMENDED-BY #102] [AMENDED-INLINE C-rev8 / W4]`；#98 markers `[AMENDED-BY #101] [AMENDED-INLINE C-rev8 / W1] [AMENDED-INLINE C-rev9 / W5] [AMENDED-INLINE C-rev11 / RED-1+YELLOW-4]`。**Alternative 未采纳**：保留 `via W<bucket>` 简写形式 + 在 §0.3.1 增补一段释义 → 释义无法消除跨轮次歧义（同 W2 在 C-rev8 / C-rev9 / C-rev10 各轮次都出现过），形式简洁但语义不稳；强制 `C-rev<N> / W<bucket>` 全限定形式让 marker 单调可解析 | §0.3.1 / §0.3 | C-rev11 闭合：Tighten-2（marker placement convention 缺）+ YELLOW-1（W-bucket 引用未规范化为 C-rev<N>/W<bucket> 全限定形式） |
| 109 | **Gate 顺序 1 → 2 → 3 优先 metrics 完整性 over CI wall-clock**：`GATES = [TestPassGate, SizeGate, CacheCompatGate]` 而非 cheap-first（3 → 2 → 1）。理由（§6.4.1）：(a) GEPA 优化器需要在 reject 候选上拿到完整 fitness signal（含 test outcome）才能学习"什么样的候选会过 gate"；cheap-first 让 size/cache 先 reject 时 GEPA 看不到 test signal，下一轮 mutation 仍重蹈覆辙；(b) report.md reviewer 拿 `gate-rejected-at: 3-cache-compat` 时同时看 test_rate / size_delta 上下文比"前面就 reject 了无 test 数据"更可观测；(c) GEPA-layer early termination（候选 fitness < `FITNESS_GATE_FLOOR=0.3` 跳过 gate 链）部分缓解 wall-clock cost。同时锁定 §6.0 point 3：gate 内部异常 → `verdict='fail'` + `failure_reason='gate-internal-error:...'`（**不**冒泡为 `EvolveError`），traceback 落 `<run_id>/gates/<N>-<name>.error.txt` 供 CI 监控扫描。**Alternative 未采纳**：(a) cheap-first 顺序（3→2→1）—— 牺牲 metrics 可观测性换 wall-clock，GEPA 收敛速度损失高于 wall-clock 节省；(b) 全 gate 跑完不短路（仅记 verdicts）—— 浪费明显 reject 候选的 size/cache 检查 cost，且模糊"短路是首-fail-fast" 的 §3.6 既有契约 | §6.0 / §6.4 | C-rev13 W1：gate 顺序未定 + gate-internal-error 落库未规范 |
| 110 | **Gate 1 输入数据集 = Tier C all-pass + Tier A rate floor**：gate 1 仅在 Tier A（synthetic, rate floor `0.80`）+ Tier C（curated golden, strict 100%）上评测；Tier B（SessionDB）opt-in 默认 false → gate 不能依赖默认 disabled 数据源（trivially-pass）；Tier D（task self-eval）M4 仅 collect、不 gate-on（同 run collect+gate-on 形成 chicken-and-egg），M5 引入 cross-run consumption（§14 下游契约）。Tier C 阈值为 `1.0`（strict-pass-rate）锚定 §1.1 line 370 既有"≥5 core golden = gate 1 lower bound"；Tier A 阈值 `0.80` 反映 Tier A statistical 性质（synthetic 噪声允许小比例失败）。**Alternative 未采纳**：(A) Tier A+C 同 strict-pass —— synthetic 数据集 strict 100% 等于把 GEPA 优化目标限定到"过拟合 Tier A"，与 Tier A 是 statistical 噪声补充的设计意图冲突；(C) Tier A+C+D 含 D bootstrap 规则 —— bootstrap 规则（首 run D 空 → trivially-pass）让 gate 在最关键的"首次进化"路径上失效，反 gate 设计意图 | §6.1.1 | C-rev13 W2：gate 1 数据集范围未明 + Tier B/D 是否参与未规范 |
| 111 | **Gate 阈值 spec-locked，不通过 EvolveDefaults 暴露**：`TIER_A_PASS_RATE_FLOOR=0.80` / `TIER_C_PASS_RATE_FLOOR=1.0` / `SKILL_LINE_HARD_CAP=400` / `SKILL_LINE_DELTA_CAP=150` / `PER_RECORD_TIMEOUT_S=30` / `GATE_TIMEOUT_MS_HARD=600_000` / `FITNESS_GATE_FLOOR=0.3` 全部为 module-level constants（在各 gate 实现文件 / `harness.py`），**不**经 `EvolveDefaults` / config 暴露给 user。理由：gate 阈值是路线图 §6 五条约束的硬实现；config 暴露 = 给 user "lowering 阈值 silently bypass gate"的口子，破坏 hard-gate 性质。M5 retro 视实测调阈值，但不放开"运行时调"路径。**Alternative 未采纳**：(A) 全部经 `EvolveDefaults` 暴露 —— 提高 user flexibility，但破坏 hard-gate 路线图约束；(B) 部分暴露（仅 timeout 类）—— 边界划分主观，timeout vs rate-floor 与"绕开 gate" 的距离差异微妙，最简单、最稳的策略是统一 spec-locked | §6.1.1 / §6.2.2 | C-rev13 W3：gate 阈值是否 user-tunable 未规范，存在 silent bypass 风险 |
| 112 | **Gate 内 partial-failure 全跑、跨 gate 短路（区分两层语义）**：gate 1 内部对 Tier A∪C 全部 record 跑完才计 `tier_*_rate`（单条 record subprocess crash / timeout 不终止 gate）；这与 §3.6 line 826 "首个 fail 即 short-circuit" 的**跨 gate**短路不冲突 —— 短路是 gate 之间，gate 1 内部全跑。理由：partial metrics 让 GEPA-iteration loop 拿到稳定 fitness（gate 1 内部短路 = metrics 缺失 → 后续 GEPA round 无 signal）。Per-record timeout `PER_RECORD_TIMEOUT_S=30s`（SIGTERM → 5s → SIGKILL），单 record outcome 失败但 gate 不终止。**Alternative 未采纳**：(A) gate 内首 record fail 即终止 —— wall-clock 略省但破坏 GEPA 学习 signal；(B) 跨 gate 不短路（全 gate 跑完）—— 浪费明显坏候选 cost 且与 §3.6 既定 short-circuit 契约冲突，不可改 | §6.1.2 / §6.4.2 | C-rev13 W4：gate 内 vs gate 间 short-circuit 语义未区分 |
| 113 | **Gate 2 度量 = `lines`（不是 tokens、不是 bytes）**：候选 SKILL.md 行数硬上限 `SKILL_LINE_HARD_CAP=400` + delta 上限 `SKILL_LINE_DELTA_CAP=+150`，两条同时校验。理由：(a) deterministic（§6.0 point 1）—— tokens 需 tokenizer 选择跨 provider/版本不稳定违反 deterministic gate；bytes 受 BOM/CRLF/编码影响（同语义文件 byte 数可不同）；lines 仅 `\n` 计数；(b) human-grain —— M4 进化目标仅 SKILL.md（人类编辑文件），lines 是人类直觉单位；(c) zero-extra-deps —— 不强迫 tiktoken / anthropic-tokenizer 在 gate 路径 install。M4 **无** exemption 机制（frontmatter override / config bypass 都不引入），bypass 在 M4 等于把硬 gate 退化为 advisory。**Alternative 未采纳**：(A) tokens（cl100k 估算）—— tokenizer 版本绑定违反 deterministic；(B) bytes —— 编码污染敏感；(C) 含 frontmatter 例外机制 —— 给 silent bypass 留口子，与决策 #111 同源 spec-lock 哲学冲突 | §6.2.1 / §6.2.3 | C-rev13 W5：size gate 度量单位 + 是否 user-tunable + 是否 exemptable 三处未规范 |
| 114 [SUPERSEDED-IN-PART-BY #116] | **Gate 3 hash 串放 `failure_reason`、`metrics` 仅放 boolean-shaped float（schema 边界承认）**：`GateResult.metrics: dict[str, float]`（§3.6 line 794 锁定）只接受 float，hex hash 字符串无法直接放入。Gate 3 设计：candidate/baseline cache_key (hex) 串入 `failure_reason`（pass 时 None），`metrics` 仅放 `byte_diff_present ∈ {0.0, 1.0}` 之类 boolean-shaped float。这是 §3.6 schema 当前刚性约束的承认，**不**改 §3.6 schema —— 跨章节改 schema 风险高于 gate 3 内部解决。M5 若引入更多 hash-shaped gate（如 ast-equivalence），考虑把 `GateResult.metrics` 放宽为 `dict[str, float \| str]`，届时 §14 下游契约统一处理。**Alternative 未采纳**：(A) 把 `metrics` schema 改为 `dict[str, float \| str]` —— 破坏 §3.6 已锁 schema，影响 manifest 序列化（json schema validators 需同步），M4 范围内得不偿失；(B) hex hash 转 float（取前 8 hex chars 转 int 转 float）—— 损失精度且与 hex 字符串语义不直观，调试体验差。**[SUPERSEDED-IN-PART-BY #116 / C-rev14 / B-Y6]**：原决策的"hex 走 failure_reason、pass 时丢失 hash audit"分支被替代为新增 sibling `evidence: dict[str, str] \| None` 字段（pass / fail 路径同时承载 hash），`failure_reason` 退回纯人读 message 角色 | §3.6 / §6.3.3 | C-rev13 W6：gate 3 hash 字符串如何嵌入 `metrics: dict[str, float]` 未规范 |
| 115 | **决策表 rationale "5 行"语义澄清（C-rev14 / A-RED-1 adjudication）**：§0.3.1 sub-rule 4 中"≤ 5 行散文"在 C-rev13 引发 Coh 与 Scope reviewer 直接判定冲突 —— Coh 视渲染后段落为"行"判定 #109–#114 全部超限，Scope 视 markdown 物理 line（每 cell 1 line）判定全部合规。本决策固化度量 SoT 为**渲染后逻辑断句单元数**（按句号 / 分号 / "Alternative 未采纳" 标志 / `(a)(b)(c)` 子项切分）≤ 8 单元（rationale 主体 ≤ 5 + alternative block ≤ 3），并叠加硬字符上限 1500 chars。理由：表格 cell 不允许换行 → "物理行数"度量本身不可达；逻辑单元数 + 字符上限组合让"≤5 行" intent（avoid 论文级长 rationale）保持但跨 reviewer 可机械化复核。C-rev13 引入 #109–#114 经本规则重新核计全部合规。**Alternative 未采纳**：(A) 严格逐"句号"切分 → 中文标点混用让切分不稳；(B) 行数取 markdown 渲染后段落数 → reviewer 间渲染器差异（GitHub vs IDE preview）会再生分歧；(C) 仅字符数 → 失去"段段连贯"的散文 intent，长 run-on sentence 可绕开 | §0.3.1 | C-rev14 闭合 A-RED-1：Coh-vs-Scope 度量分歧的单一 SoT 澄清 |
| 116 [SUPERSEDES-PART-OF #114] | **`GateResult.evidence: dict[str, str] \| None = None` sibling 字段（C-rev14 / B-Y6）**：§3.6 `GateResult` schema 新增 sibling 字段 `evidence: dict[str, str] \| None = None`，承载 gate 内部需保留但**非数值**的 audit-trail 标识（hex hash、文件路径、external job-id 等）。`metrics: dict[str, float]` 类型签名**不**改动；`evidence` 与 `metrics` 是正交角色 —— `metrics` 仅承载可参与 fitness aggregation / report 数值聚合的浮点量，`evidence` 仅承载只读字符串标识。Gate 3 改为 `verdict=='pass'` 时也写 `evidence={'candidate_cache_key': ..., 'baseline_cache_key': ...}`（修复决策 #114 的 pass-path audit gap，cache key 在 promoted candidate manifest 中可被外部 audit）。`failure_reason` 退回纯人读 message。**Alternative 未采纳**：(i) 把 `metrics` 类型放宽为 `dict[str, float \| str]` —— Pydantic union 在 JSON 序列化 / 反序列化时类型推断不稳（"100" 可能被回读为 int 100 或 str），破坏 manifest 跨版本稳定性；(iii) 在 `failure_reason` 字段上 overload 把 hex hash 串入 pass 路径 → 命名误导（pass 时无 failure），且字符串解析回 hex 不利程序消费 | §3.6 / §6.3.3 / §6.0 | C-rev14 闭合 B-Y6：`metrics: dict[str, float]` 刚性 schema vs hex hash 承载的二选一困境用 sibling 解 |
| 117 | **`Gate.NONDETERMINISTIC: ClassVar[bool] = False` opt-out（C-rev14 / B-Y11 forward-looking）**：§6.0 point 1 "deterministic + offline" 硬约束在 M5 引入 gate 4（LLM judge）/ gate 5（human-PR async）时不可成立。预先在 `Gate` ABC 引入 `ClassVar[bool] = False` 默认 opt-out 形态：基类默认 `False`（M4 三 gate 全部继承默认值），违反 deterministic 的 future gate **必须**显式声明 `class SomeGate(Gate): NONDETERMINISTIC: ClassVar[bool] = True` + docstring 说明非确定性来源。Harness 双跑等价检查（§10 不变量待起草）仅对 `NONDETERMINISTIC=False` gate 触发；`NONDETERMINISTIC=True` gate 跳过等价 assert（运行时仍记录两次输出供 audit）。模式同决策 #95 `STRUCTURED_KWARGS` ClassVar 形态（registry-via-introspection），不引入 decorator / 注册表副作用。**Alternative 未采纳**：(B) M5 时再加字段 → M4 不变量起草后再 retrofit 会破坏 invariant SoT；(C) 单独 ABC 子类 `NondeterministicGate(Gate)` → 双 ABC 复杂度高于 ClassVar opt-out，且 gate 列表 `GATES` 同质性破坏 | §6.0 / §6.6.1 | C-rev14 闭合 B-Y11：M5 LLM-judge gate 与 M4 deterministic 硬约束的前瞻调和 |
| 118 | **Env hardening: deny-list (secrets) 替代 allow-list（C-rev14 / B-Y3 + B-Y4）**：§6.0 point 2 子进程 env 由 allow-list 改为 deny-list。Allow-list 形态下 pytest 等 CI 工具因 `PYTEST_CURRENT_TEST` / `CI` / `GITHUB_*` / `XDG_*` / `TMPDIR` 等 platform env 被 strip 而 break。Deny-list 范围（glob match）：`*_API_KEY` / `*_TOKEN` / `*_SECRET` / `AWS_*` / `GOOGLE_APPLICATION_CREDENTIALS` / `OPENAI_*` / `ANTHROPIC_*` / `AZURE_*` / `GH_TOKEN` / `GITHUB_TOKEN`。保留：`HOME` / `USER` / `LOGNAME` / `PATH` / `PYTHONPATH` / `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` / `DYLD_FALLBACK_LIBRARY_PATH` / `SSL_CERT_FILE` / `SSL_CERT_DIR` / `XDG_CACHE_HOME` / `LANG` / `LC_*` / `TMPDIR` / `TZ`。Goal 重新定义为"**block secret leak to candidate 进程**"（cooperative threat model），**不**是"isolate from host platform"。Proxy hardening 同时加固：`HTTP_PROXY=HTTPS_PROXY=http://127.0.0.1:1` 加 lowercase 变体 `http_proxy=https_proxy=http://127.0.0.1:1`（curl/requests 各派系），并 clear `NO_PROXY=no_proxy=''`（防 host bypass list 漏出）。**Alternative 未采纳**：(A) 保留 allow-list + 逐项追加 platform env → list 永远不全，platform-specific env 会持续踩坑；(C) seccomp / network namespace 隔离 → §6.0 point 2 已显式声明 cooperative sandbox；adversarial threat model 留 M5 third-party Darwinian Evolver | §6.0 | C-rev14 闭合 B-Y3 + B-Y4：env-strip allow-list 破 CI + proxy hardening 不全 |
| 119 | **Helper module location: `nanobot/evolve/_skill_sandbox.py`（C-rev14 / B-Y10）**：§6.1.2 用到的 `_invoke_skill_in_sandbox(record)` + env-strip subprocess wrapper helper 落在 **`nanobot/evolve/_skill_sandbox.py`** 单文件 helper（与 `_atomic_swap.py` / `_cache_key.py` 并列；下划线前缀 internal namespace）。Gate 1 (`gates/test_pass.py`) 通过 `from nanobot.evolve._skill_sandbox import invoke_skill_in_sandbox` 引用。本决策同步触发**决策 #93 forward-looking trigger 满足条件检查**：`_skill_sandbox.py` 是 evolve 子系统第二个跨模块 helper（除 `_atomic_swap.py` 外），但 #93 forward-looking 触发条件是"第二个**跨模型 validator helper**"（schema validator，如 weight-bounds checker）—— `_skill_sandbox.py` 是 runtime helper 而非 validator，**不**触发抽取至 `validators.py`。`_skill_sandbox.py` 自己作为独立 helper module 存在，与 #93 forward-looking 范围正交。**Alternative 未采纳**：(A) gate-private（落在 `gates/test_pass.py` 内）→ 未来 gate 4 LLM-judge 也需 isolated subprocess invocation 时无法复用；(C) 落 `nanobot/evolve/validators.py` → 误用 #93 forward-looking 触发条件，validator 与 sandbox 是两类关注点 | §6.1.2 / §0.3 (#93 trigger 检查) | C-rev14 闭合 B-Y10：helper 模块归属 ambiguity |
| 120 | **`tier_*_total == 0` 触发 fail（C-rev14 / A-RED-4）**：§6.1.4 中 "total=0 → rate=1.0" 除零 convention 在 fixture loader 回归（Tier C 数据集为空）时让 gate 1 trivially-pass，defeats §1.1 "≥5 core golden = gate 1 lower bound"。修复：`tier_c_total == 0 OR tier_a_total == 0 → verdict='fail'` + `failure_reason='tier-{a,c}-empty: gate-1 requires ≥1 record'`。同时把 §1.1 narrative 中"≥5 core golden"从 prose 提升为 §6.1.2 runtime precondition assert：gate 1 进入 evaluate body 第一步 `if len(tier_c_records) < 5: raise GateInternalError('tier-c-below-floor')`（gate-internal-error → §6.0 point 3 path → `verdict='fail'`），让 fixture 回归 fail-loud 而非 silent vacuous-pass。**Alternative 未采纳**：(B) 保留 `total=0 → rate=1.0` 但加 warn-log → log-only 不阻断，pipeline 仍 promoted_to_pr，破坏 hard gate 性质；(C) 把 floor 5 移到 `EvolveDefaults` 暴露为 user-tunable → 与决策 #111 spec-locked 哲学冲突 | §6.1.2 / §6.1.4 | C-rev14 闭合 A-RED-4：tier-c-empty silent vacuous-pass |
| 121 | **Gate 1 hard timeout 机制：post-hoc warning + per-record deadline（C-rev14 / A-RED-3）**：§6.0 point 5 原"`duration_ms > GATE_TIMEOUT_MS_HARD` 由 harness 主动 cancel"在 sync `evaluate()` + thread-executor 模型下不可实现（`Future.cancel()` for running thread is no-op；threads 不可强 kill；check after return → cancel 无效）。修复：(a) Hard timeout 由 **gate 内部** per-record deadline 累加 + 显式 budget check 实现 —— gate 1 在每条 record 完成后 `if time.perf_counter() - gate_start_ns/1e9 > GATE_TIMEOUT_MS_HARD/1000: break loop, set verdict='fail', failure_reason='timeout-hard:<elapsed>ms'`；剩余 record 跳过但已跑 record 的 metrics 保留（partial signal 给 GEPA）；(b) Gate 2/3 是 O(1)，timeout 不适用；(c) Harness `_run_gates` 仍记 wall-clock `duration_ms`，但**不**再尝试 cancel —— 仅在 gate 返回 verdict 后 post-hoc 写 warn 日志（"gate exceeded soft 5min"），不改 verdict。SIGTERM/SIGKILL 仅作用于**单 record subprocess**（§6.1.2 step 5 既有），不作用于整 gate。**Alternative 未采纳**：(b) 把 long-running gate 全部改 subprocess（让 harness `os.kill()` 可达）→ 引入 multiprocessing IPC 复杂度 + pickle 限制，M4 仅 1 个 long-running gate 不值得；(c) 用 POSIX `signal.alarm` → not thread-safe（harness 跑在 asyncio loop + executor thread 上，signal 仅 main thread 可达），跨平台 Windows 不支持 | §6.0 / §6.1.2 | C-rev14 闭合 A-RED-3：thread-cancel impossible → 重新定义 hard-timeout SoT |
| 122 [NEW C-rev15 / RF-2] [AMENDED-INLINE C-rev16 / RF-2+RF-3] | **`Gate.__init_subclass__` 子类注册表（C-rev15 / C-Y2）**：§3.6 `Gate` ABC 增加 `_subclasses: ClassVar[list[type["Gate"]]] = []` + `__init_subclass__` hook，每个具体 `Gate` 子类在 class-body 执行时自动 append 到 `_subclasses`。`tests/evolve/test_gates_registry.py::test_no_orphan_gate_subclass` 改用 `assert {type(g) for g in GATES} >= set(Gate._subclasses)` 闭合 B-Y9 covering hole —— 原 `inspect.getmembers(nanobot.evolve.gates, ...)` 仅遍历 package object 上 re-export 的属性，新增 `gates/foo.py` 但忘 `__init__.py` re-export 的 orphan 子类逃出检测。**Alternative 未采纳**：(a) 用 `pkgutil.iter_modules(...) + importlib.import_module(...)` 在测试中递归加载每个 submodule 后再 `getmembers` → 引入 import 副作用 / 顺序敏感（依 importlib cache 状态）；(b) 改用 entry-point 注册（pyproject.toml `[project.entry-points]`） → 跨进程发现机制对 `Gate` 这种 in-process registry 过重。形态对齐决策 #117 `NONDETERMINISTIC` ClassVar + #95 `STRUCTURED_KWARGS` ClassVar，无 import-time 副作用，与 `GATES` explicit ordered list 角色正交（`GATES` 是 ordered execution；`_subclasses` 是 declaration registry）。**[AMENDED-INLINE C-rev16 / RF-2+RF-3]** contract test 改用 dual-filter（`__module__` prefix 排除 fixture 污染 Corr-1 + `inspect.isabstract` 排除 M5 abstract intermediate Corr-2/Arch-2）；distinct from #104（§3.6 docstring forward-notes 详） | §3.6 / §6.4.1 | C-rev15 闭合 C-Y2：B-Y9 scope 不全；C-rev16 RF-2+RF-3 inline-amend：dual-filter |
| *待 §7+ 起追加* | | | |

### 0.3.1 决策日志约定（C-rev6 / 决策 #97 / YELLOW-Y8 / Y-arch-6）

为防止 §0.3 决策表在 M5+ 不断膨胀至不可读，本节锁定决策日志的写作与维护约定：

1. **Superseded-by 标记**：当后续决策（如 #96）替代了早期决策（如 #88）的某一部分时，在早期决策标题行末尾追加 `[SUPERSEDED-BY #N]` 标签，并保留早期决策**完整文本**（不要删除）。理由：决策表是 audit trail，记录的是"为什么从 X 改到 Y"的演化轨迹，删除等于销毁证据。示例：本轮 C-rev6 中，决策 #88 的 `--force` atomicity 部分被 #96 替代，故 #88 的相关段标 `[SUPERSEDED-BY #96]` 而保留原文。

2. **Milestone 滚动 grooming 规则**：每个 milestone 收尾时，所有 `[SUPERSEDED-BY #N]` 且 superseding 决策本身已存在 ≥ 3 个 milestone（即跨过 ≥ 3 个稳定 release window）的旧决策，**可**被收集到一个 "Historical decisions" 附录（仅保留标题 + supersede 指针 + git ref）。完整文本仍保留在 git history。M4 不会触发本规则（M4 自身是首 milestone 引入 evolve）；本规则用于 M5+ 的预防性治理。

3. **决策编号**：M1 至今 monotonic 递增，跨 milestone 不重置（已落地实践）。**永不**因为决策被 supersede 而重新编号 —— 编号是稳定的 issue tracker 锚点，下游 PR / commit message / spec 注释会用 `决策 #N` 引用，重编号会让所有引用失效。

4. **Rationale 长度上限**：每条决策的 rationale 字段 ≤ 5 行散文。更长的讨论应放在当轮 reviewer-fix-brief 评论或对应 round 的 progress doc（如 `docs/hermes-evolution/retros/m4-offline-skeleton.md` 草稿）中；决策表保留浓缩理由。**Grandfather 条款（C-rev7 / Z7 / Y-c6-arch-5）**：本规则**仅**适用于 C-rev6 及以后新增 / 修订的决策（即 #95 起）。Pre-C-rev6 已落地的决策（含决策 #87 ~12 行的"替代方案考量"块）保留原始 rationale 长度 —— 决策日志的 audit-trail 稳定性高于本规则的格式统一；不为格式统一而追溯性修改已 committed 的 rationale 文本。**"5 行"语义澄清（C-rev14 / A-RED-1 / 决策 #115）**：因 §0.3 决策表使用 markdown 表格形态，每条 rationale 在源文本中占 1 物理 line（cell 内不允许换行）；"≤ 5 行散文"规则的 SoT 度量是**渲染后逻辑断句单元数**而非源文本物理行数。具体规则：(a) 把 rationale 按句号 / 分号 / 全角句号（。）/ "**Alternative 未采纳**:" 标志切分为逻辑句段；(b) 每个 `(a)/(b)/(c)` 子项 + 每个独立 sentence 算 1 单元；(c) 单元总数 ≤ 8（含 alternative-rejection block；rationale 主体 ≤ 5 单元，alternatives 额外 ≤ 3 单元）。同时引入硬字符上限：rationale 字段总长度 ≤ 1500 GB-style chars（含 markdown 标记）。本澄清适用于 #95 及以后所有新增 / 修订决策；C-rev13 引入的决策 #109–#114 经 C-rev14 重新核计**全部合规**（最长 #109 ≈ 7 单元 + 1100 chars，#114 ≈ 6 单元 + 1080 chars）。Coh 与 Scope reviewer 间 C-rev13 关于"行数"度量的语义分歧由本澄清单一标准统一关闭。

5. **更新触发要求**：任何同时修改 §0.3 表与其它 spec 章节（§1–§14 / §0.2）的 PR，commit message 中必须分行列出涉及的决策编号；reviewer 检查时把"决策表 row" 视为契约 anchor。

6. **Marker vocabulary enumeration（C-rev10 / 决策 #103 / Coh-RED1）**：本节正式枚举 §0.3 表中可用的全部 marker 形态及其 RFC 2119 语义。任何新 marker 形态必须先在本表追加再使用。

   | Marker | RFC 2119 语义 |
   |---|---|
   | `[SUPERSEDED-BY #N]` | 被标记决策**完全**被决策 #N 替代；旧决策保留为 audit trail，但**不再有效**。 |
   | `[SUPERSEDES-PART-OF #M]` / `[SUPERSEDED-IN-PART-BY #N]` | 部分替代关系（双向对偶必备）：决策 #N 替代 #M 的某一具体方面；两决策**均仍然有效**，各自管辖**不重叠**的范围。决策正文必须明确划清各自范围。 |
   | `[AMENDS #M]` / `[AMENDED-BY #N]` | 双向对偶必备：决策 #N 修订（但**不**替代）决策 #M；两者均完全有效，#N 的修订内容附加于 #M 之上。语义上是 #M 的**增强**，非冲突替代。 |
   | `[AMENDED-INLINE C-rev<N> / W<bucket>]` | 在轮次 C-rev<N> 闭合 W<bucket> 评审发现期间**就地编辑**了某条决策的文本，未单独开新决策（编辑幅度小、未引入新决策面）。本 marker 仅在被编辑决策的标题行使用，无对偶项。 |

   **对偶完整性强制要求**：所有双向 marker（`SUPERSEDED-BY` ↔ `SUPERSEDES`、`SUPERSEDES-PART-OF` ↔ `SUPERSEDED-IN-PART-BY`、`AMENDS` ↔ `AMENDED-BY`）**必须**同时出现在两个端点决策的标题行；缺失任一端即破坏 audit trail，PR review 应拒绝合入。

   **Marker placement convention（C-rev11 / Tighten-2 / 决策 #108）**：对偶 marker 的左右两端有固定方向语义。`[SUPERSEDED-*]` / `[AMENDED-BY]` marker 出现在**被**替代 / 修订的（旧、历史）决策标题行；`[SUPERSEDES-*]` / `[AMENDS]` marker 出现在**做出**替代 / 修订的（新）决策标题行。两端 marker MUST 同时存在；任何只有一端 marker 的 PR commit SHOULD 在 review 中被拒（grep `SUPERSEDED-IN-PART-BY #N` ↔ `SUPERSEDES-PART-OF #M`、`AMENDED-BY #N` ↔ `AMENDS #M` 的双向匹配可机械化加入 PR check）。`[AMENDED-INLINE C-rev<N> / W<bucket>]` 是单端 marker，无对偶项 —— 仅放在被就地编辑的决策标题行。

7. **W-bucket 标记约定（C-rev10 / 决策 #103 / Coh-Y3 + C-rev11 / 决策 #108）**：`W1` / `W2` / ... 等 W-bucket 标记指代**单一** C-rev<N> 轮次内离散的 reviewer-finding 闭合分组；编号**每轮重置**，对应轮次的 commit message body 中记录每个 bucket 的具体 finding-id 列表。W-bucket 标记**不是**独立的决策 ID，仅为轮次内闭合追踪所用 —— 决策日志中引用形式恒为 `C-rev<N> / W<bucket>` 全限定（以避免跨轮次误识）。**禁止简写形式 `via W<bucket>`**（C-rev11 / YELLOW-1 / 决策 #108）：早期轮次曾在 marker 中使用如 `[AMENDED-BY #N via W<bucket> <description>]` 这类内联简写，因省略轮次号 → 跨轮次重用同一 W-bucket 编号时引发歧义。修复约定：(a) 若新决策 #N 已经独立存在，标题行只写 `[AMENDED-BY #N]`，W-bucket 归属由 #N 自身的 narrative / metadata 承载；(b) 若编辑幅度仅触及该决策的就地文本（无新决策），加 `[AMENDED-INLINE C-rev<N> / W<bucket>]` 单端 marker。两种形态可同时叠加（如决策 #98 同时含 `[AMENDED-BY #101] [AMENDED-INLINE C-rev8 / W1]`，表示 #101 这条新决策是在 C-rev8 W1 闭合中创建并就地修订了 #98）。

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
│   │   ├── _base.py                     # EvolveBase 共形基类（§3.0）
│   │   ├── schemas.py                   # NEW（决策 #87）：零-extra-deps 的共享数据 schema
│   │   │                                # 含 RubricWeights / RubricScore；仅 import pydantic + stdlib
│   │   │                                # 让 nanobot.config.schema 可直接 import RubricWeights 而不
│   │   │                                # 触发 evolve extra 加载；取代旧的 nanobot/config/_evolve_types.py shim
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
│   │   ├── _atomic_swap.py              # 决策 #98 / W1 — atomic_swap() helper（§4.4.2）
│   │   └── exceptions.py                # 完整列表见 §5.3 + __all__（§5.4.6）
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

### 3.0 `EvolveBase` 共享基类（数据模型 house style）

§5 中的 config 模型（`EvolvePrivacyConfig` / `EvolveDefaults`）继承自 `nanobot.config.schema.Base`（已包含 `alias_generator=to_camel, populate_by_name=True`）。本节 §3.1–§3.7 的所有**运行时数据模型**统一继承自专属基类 `EvolveBase`，与 config 模型并列但独立：

```python
# nanobot/evolve/_base.py
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

class EvolveBase(BaseModel):
    """M4 evolve 包内所有运行时数据模型的共形基类。

    与 nanobot.config.schema.Base 解耦：config 模型是 load-once 配置对象，
    数据模型是 pipeline 内频繁构造的 runtime 对象。两条继承链分开，
    以便未来 evolve runtime 与 nanobot config 子系统独立演进。

    rationale:
      - extra='forbid': 任何拼写错误 / 漂移字段在构造期失败，避免 manifest
        悄悄多带未定义字段（§3.7.1 「无 PII」不变量的机械化护栏之一）。
      - alias_generator=to_camel + populate_by_name=True: manifest.json /
        judge_log.jsonl 等磁盘产物的 key 走 camelCase，便于跨语言 / JS 工具
        消费；Python 侧仍以 snake_case 访问字段。
      - frozen=False: 数据对象需在 harness 内增量构造（如 GateResult 列表
        逐 gate append），不像 config 那样需要 frozen；不变量由 §10 显式
        保证而非靠类型系统。
    """
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        frozen=False,
    )
```

§3.1–§3.7 下文每个数据类的代码块中，`class X(BaseModel):` 行均替换为 `class X(EvolveBase):`，并 import 改为 `from nanobot.evolve._base import EvolveBase`。本节专门列示 base，下游代码块只展示业务字段，不重复 `model_config`。**例外**：`RunManifest`（§3.7）与 `JudgePool`（§3.3）显式 override 为 `frozen=True`（详见 §3.7.1 / §3.3），以机械化锁定写出后不可 mutate。

> **EvolveBase 稳定性公约（M4 → M5）**：（**provisional — 待 §6–§14 审定通过后确认**）以下 EvolveBase / RubricWeights / JudgePool 的 `model_config` 字段稳定性承诺，是基于 C-rev4 时 §0–§5 的 M4 数据模型设计制定的。如果 §6–§14（Gate detail / Judge calibration / PR-only deploy / Privacy / Invariants）审定过程中暴露需调整 `model_config` 的事实，承诺以最终 spec 审定版为准。M5 启动前若有 §6–§14 引入的 model_config 修改，必须同时刷新本承诺。
>
> `nanobot/evolve/_base.py`（以及决策 #87 下迁入 `nanobot/evolve/schemas.py` 的 `RubricWeights` / `RubricScore`）是 `__all__`-private 的内部模块，但其 `model_config`（`extra="forbid"`、`alias_generator=to_camel`、`populate_by_name=True`、`frozen=False`）是 M4 的稳定契约：M5 对 `EvolveBase.model_config` 的**任何**改动必须在 `docs/hermes-evolution/roadmap.md` §2 决策日志中新增一条 entry，**不可**就地编辑 `_base.py`。子类（`RunManifest` / `JudgePool` 等）**允许**单独 override 某些 key（如 `frozen=True`），前提是仍与 base 的语义兼容（不能放宽 `extra` 或拆掉 alias generator）。**机械化执行**（YELLOW-Y4 / 决策 #91）：本公约由 `tests/evolve/test_base_config_frozen.py` 快照测试在 CI 拦截（定义见 §5.4.5 步骤 7）；改 `model_config` 的 PR 不更新 EXPECTED dict + 同 commit 追加 Decision，测试 fail。**并列公约（§5.4.5 lazy-import 纪律）**：`nanobot/evolve/__init__.py` 等 `__init__.py` 模块的 lazy-import 行为同样是 M4 → M5 的硬契约，任何打破 `tests/evolve/test_no_extra_in_init.py` / `tests/evolve/test_probe_no_extra.py` 探针的改动必须经过 roadmap 决策日志。

### 3.1 4-tier 评测数据 schema

每条评测样本（无论 tier）落地为 jsonl 中的一行 record（`EvalRecord`），存储位置见 §2.1 / §2.2，tier 间字段共形 + 语义层差。

#### 3.1.1 共形 base record

```python
# nanobot/evolve/data/__init__.py
from typing import Literal, Optional
from pydantic import Field
from datetime import datetime
from nanobot.evolve._base import EvolveBase

class EvalRecord(EvolveBase):
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
from datetime import datetime
from nanobot.evolve._base import EvolveBase

class SkillFrontmatter(EvolveBase):
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

class SkillContent(EvolveBase):
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

**Cluster 放置（YELLOW-Y10 / C-rev4）**：本节涉及类的模块放置（`nanobot.evolve.judges.rubric` 承载 `JudgeConfig` / `JudgePool` / `JudgeResult` / `JudgeConsensus`；`nanobot.evolve.schemas` 承载 `RubricWeights` / `RubricScore`）遵循决策 #87（zero-extra-deps schema 与 judge backend 解耦）与决策 #89（`JudgeConfig` 作为 `JudgePool.judges` 元素类型的公共暴露）；详见 §0.3 决策表对反向布局（`nanobot/config/evolve_schemas.py`）的替代考量与未采纳理由。

**模块归属（决策 #87）**：`RubricScore` 与 `RubricWeights` 已从 `nanobot/evolve/judges/rubric.py` 迁出到 `nanobot/evolve/schemas.py`（零-extra-deps 共享 schema 模块，仅 import `pydantic` + stdlib，绝不 import `dspy/gepa/litellm/optuna`）。`judges/rubric.py` 内的 judge prompt / scoring helper 通过 `from ..schemas import RubricScore, RubricWeights` 引用。这是为了让 `nanobot.config.schema` 可以直接 `from nanobot.evolve.schemas import RubricWeights` 而无需触发 evolve extra 加载，断掉旧 `nanobot/config/_evolve_types.py` lazy shim 引入的反向耦合（YELLOW-Y2）。`JudgeResult` / `JudgeConsensus` / `JudgePool` 仍住 `judges/rubric.py`（这些类被 judge backend 直接消费）；**模块文件路径**与 `__all__` re-export 名字解耦，下游应通过 `from nanobot.evolve import RubricWeights, JudgePool` 引用，不依赖具体文件位置。

```python
# nanobot/evolve/schemas.py（决策 #87；RubricScore + RubricWeights 居住地）
from pydantic import Field, model_validator
from nanobot.evolve._base import EvolveBase

class RubricScore(EvolveBase):
    """3 维度独立 0–1 浮点 + 加权聚合。"""

    process: float = Field(ge=0.0, le=1.0)         # 流程合规
    output: float = Field(ge=0.0, le=1.0)          # 输出正确
    token: float = Field(ge=0.0, le=1.0)           # token 经济
    aggregate: float = Field(ge=0.0, le=1.0)       # 加权聚合（默认 0.4 / 0.4 / 0.2）
    # 注：`aggregate` 区间由 Field(ge=0.0, le=1.0) 已机械校验；
    # 加权一致性（aggregate ≈ process*w_p + output*w_o + token*w_t，容差 1e-6）
    # 在 harness 的 `_score_record()` 调用点 assert，**不**加 model_validator
    # —— 因 RubricWeights 是 RubricScore 的外部输入，无法在该类内验证。
    # 删除 Round C-rev 的 _validate_aggregate 空 stub（YELLOW-11 / C-rev-6）。

class RubricWeights(EvolveBase):
    """RubricScore.aggregate 的权重；通过 config 可调（§4.4）。

    canonical 类型：`EvolveDefaults.rubric_weights` 字段类型为 `RubricWeights`
    （非 `dict[str, float]`），保证求和不变量由本类的 `_sum_to_one` 一处校验
    （决策 #84）。模块归属：`nanobot/evolve/schemas.py`（决策 #87）。
    """

    process: float = Field(default=0.4, ge=0.0, le=1.0)
    output: float = Field(default=0.4, ge=0.0, le=1.0)
    token: float = Field(default=0.2, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "RubricWeights":
        s = self.process + self.output + self.token
        if abs(s - 1.0) > 1e-6:
            raise ValueError(
                f"RubricWeights must sum to 1.0 (got {s:.6f}); "
                f"process={self.process}, output={self.output}, token={self.token}"
            )
        return self


# Parity SoT helper（YELLOW-Y4 / 决策 #93）
def _assert_odd_pool_size(n: int, *, context: str) -> None:
    """Single source of truth for the odd-judge-pool parity invariant (决策 #81).

    Both `JudgePool._odd_pool_only` (§3.3) and `EvolveDefaults._odd_pool_size`
    (§4.5) delegate to this helper; do not re-implement the parity rule elsewhere.

    Args:
        n: pool size to validate
        context: caller-side context string for disambiguation in error reports
                 (e.g., "JudgePool.judges" / "EvolveDefaults.default_judge_pool")

    Raises:
        ValueError: if n == 0 or n is even. Message includes context for
                    upstream report attribution.
    """
    if n == 0 or n % 2 == 0:
        raise ValueError(
            f"{context}: judge pool size must be odd and >= 1 (got {n}); "
            f"even sizes break median consensus per 决策 #81."
        )
```

```python
# nanobot/evolve/judges/rubric.py（judge backend；保留 JudgeResult / Consensus / Pool）
from typing import Literal
from pydantic import ConfigDict, Field, computed_field, field_validator, model_validator
from datetime import datetime
from nanobot.evolve._base import EvolveBase
from nanobot.evolve.schemas import (  # 决策 #87 单向依赖 + Y-corr-3 / C-rev6 module-top import
    RubricScore,
    RubricWeights,
    _assert_odd_pool_size,
)

class JudgeConfig(EvolveBase):
    """单个 judge 的最小描述（provider/model + 可选权重 override）。

    M4 ships 仅含 `model`（字符串形如 `"anthropic/claude-3-5-sonnet"`），权重等
    扩展字段留给 M5；保留独立类型以便 `JudgePool.judges` 类型推断稳定。

    **公共类型理由（YELLOW-Y1）**：`JudgeConfig` 是 `JudgePool.judges` 的元素
    类型，而 `JudgePool` 已在 `__all__`，外部消费者（M5 plugins、test fixtures、
    `OfflineHarness.run(judge_pool=JudgePool(...))` 直传）若要程序化构造
    `JudgePool` 必须能 import 一个稳定命名的元素类型，否则只能反向触达
    `nanobot.evolve.judges.rubric` 私有路径。因此 C-rev4 把 `JudgeConfig` 提到
    `__all__`（详见 §5.4.6 单一事实之源；演化轨迹经 决策 #89 / #90 / #96 多次
    扩展，精确名称集合由 `tests/evolve/test_probe_no_extra.py::expected_all`
    锁定 — Y-arch-7 / C-rev6 起取消硬编码 count narrative），与 `JudgePool`
    配对暴露。

    **保留 `EvolveBase` 继承的理由（YELLOW-Y1）**：当前仅 `model: str` 单字段，
    但根据 §3.0 EvolveBase 稳定性公约，M5 将扩展 `timeout_s` / `weight` /
    `temperature_override` 等 per-judge 字段以支持 calibration。保留 Pydantic +
    `alias_generator=to_camel`（来自 EvolveBase）让 M5 新增字段时无需迁
    `@dataclass` → `BaseModel`，更无需破坏构造器 positional args 的二进制兼容
    （JSON 路径走 alias、Python 路径走 snake_case 字段名）。downgrade 到
    `@dataclass` 看似当下省 80 bytes，会在 M5 触发 ctor 迁移痛。

    **CLI ↔ JudgePool 转换**：CLI `--judge-pool` 传 CSV 字符串
    （`anthropic/claude-3-5-sonnet,openai/gpt-4o,...`），`EvolveDefaults.default_judge_pool`
    也是 `list[str]`。`OfflineHarness.run()` 入口把字符串列表映射为
    `JudgePool(judges=[JudgeConfig(model=s) for s in pool])`（详细规则见
    §5.1 `run()` 的 `judge_pool` kwarg union 文档）。CLI 表面始终是
    `list[str]`；`JudgeConfig` 是 evolve 内部 runtime 类型，但公开供 API 直传
    `JudgePool` 时构造 element 用。
    """
    model: str

class JudgeResult(EvolveBase):
    """单 judge × 单 record 的评分。"""

    eval_record_id: str                            # 引用 EvalRecord.record_id
    judge_model: str                               # 如 "anthropic/claude-3-5-sonnet"
    score: RubricScore
    reasoning: str                                 # judge 的自然语言说明（人审用）
    timestamp: datetime
    prompt_template_version: str                   # judge prompt 模板版本（§7）

class JudgeConsensus(EvolveBase):
    """跨 judge pool 的一致性聚合；当 pool 仅 1 judge 时退化为单结果。"""

    eval_record_id: str
    judges: list[JudgeResult]                      # len ≥ 1；len ≥ 3 时启用 §7.4 协议
    median_score: RubricScore                      # 三维度逐维取中位
    inter_judge_variance: dict[str, float]         # {"process": σ², "output": σ², "token": σ²}
    consensus_verdict: Literal["agree", "split", "single"]
    # split = 任一维 σ > 0.2；single = pool size == 1

class JudgePool(EvolveBase):
    """Judge pool 配置；M4 推荐 size ≥ 3（决策 #81）。

    `min_quorum` 语义（决策 #86）：用户输入字段，`None`（默认）→ 由
    `effective_min_quorum` computed property 解析为多数派
    `(len(judges) // 2) + 1`；显式传 `int >= 1` 时按值生效（上限 `len(judges)`，
    超出在 `_validate_quorum_bounds` 抛 `ValueError`）。**`None` 与显式 `0` 不
    再混淆**：旧设计用 `0` 双关「未设 → 应用默认」与「合法用户值」，结构性歧义。
    新方案以 `None` 充当未设哨兵，`Field(ge=1)` 让 `0` 直接被 Pydantic 拒绝。

    **`frozen=True` override（决策 #86）**：与 `RunManifest` / `EvolveDefaults`
    保持一致；不再允许运行时 mutate `min_quorum` 偷偷放宽 §5.1 retry contract。
    旧设计的 `object.__setattr__` 绕道（伪 future-proof）一并删除：computed_field
    本就不 mutate 字段，无须绕开 frozen。

    **运行时消费规则**：所有 retry / quorum 判定**必须**读 `effective_min_quorum`，
    禁止直接读 `min_quorum`（可能为 `None`）。§5.1 retry contract 已同步更新。

    **API 直传路径（YELLOW-Y3 / 决策 #89）**：`OfflineHarness.run()` 的
    `judge_pool` kwarg 类型为 `list[str] | JudgePool | None`；传 `JudgePool`
    实例时 verbatim pass-through，**不**做任何字段合并或重构造，调用方因此
    可以在 `EvolveDefaults`（`frozen=True`）配置下 override `min_quorum` 而无须
    先写盘 config。详见 §5.1 `run()` 的 `judge_pool` 文档。
    """
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=EvolveBase.model_config["alias_generator"],
        populate_by_name=True,
        frozen=True,
    )

    judges: list[JudgeConfig] = Field(..., min_length=1)
    weights: RubricWeights = Field(default_factory=RubricWeights)
    require_consensus: bool = False                # True 时 split → JudgeError 致整 record fail
    min_quorum: int | None = Field(
        default=None,
        ge=1,
        description=(
            "User-supplied quorum threshold. None = resolve to majority "
            "(len(judges)//2 + 1) via effective_min_quorum. "
            "Explicit integer >= 1 honored verbatim (upper bound: len(judges))."
        ),
    )

    @model_validator(mode="after")
    def _validate_quorum_bounds(self) -> "JudgePool":
        # judges min_length=1 由 Field 强制；此处仅校验显式 min_quorum 的上界。
        if self.min_quorum is not None and self.min_quorum > len(self.judges):
            raise ValueError(
                f"JudgePool.min_quorum={self.min_quorum} exceeds "
                f"len(judges)={len(self.judges)}"
            )
        return self

    @field_validator("judges")
    @classmethod
    def _odd_pool_only(cls, v: list[JudgeConfig]) -> list[JudgeConfig]:
        """Belt-and-suspenders 强制奇数池（决策 #81 / YELLOW-Y8 C-rev4 / YELLOW-Y4 C-rev5）。

        `EvolveDefaults._odd_pool_size` 在 config 层校验
        `default_judge_pool: list[str]`；但 `JudgePool(judges=[a, b])`
        直接构造（test fixture / M5 plugin / `OfflineHarness.run(judge_pool=...)`
        直传）会绕过 config 层，得到 `effective_min_quorum=2`（即偶数池上的
        unanimous-on-even-pool，破坏 §3.3 中位 consensus 语义）。

        **Parity SoT delegate（决策 #93 / YELLOW-Y4 C-rev5；Y-corr-3 / C-rev6 module-top import）**：
        本 validator 调用 `_assert_odd_pool_size`（已在模块顶部 import，避免每次
        validation 触发 in-function import 开销 + 让依赖关系在 import 段显式可见）；
        该 helper 是奇数池规则的单一事实之源，与 `EvolveDefaults._odd_pool_size`
        共用同一规则函数。
        """
        _assert_odd_pool_size(len(v), context="JudgePool.judges")
        return v

    @computed_field  # type: ignore[misc]
    @property
    def effective_min_quorum(self) -> int:
        """运行时 quorum 阈值：min_quorum 或多数派（n//2 + 1）。

        n=1 → 1；n=3 → 2；n=5 → 3。单 judge 场景自动退化为「judge 不可用即中断」，
        无须特殊分支。
        """
        if self.min_quorum is not None:
            return self.min_quorum
        return (len(self.judges) // 2) + 1
```

**新决策 #81（追加于 §0.3）**：判官池默认 size 为 3（pool of 3 distinct provider/model），单 judge 模式仅在 dev / unit-test 启用，通过 `--judge-pool <single-model-name>`（长度 1 即合法奇数）触发。理由：Hermes 调研指出单 judge 易引入 model bias；3 已是"最小奇数 + 可中位"。可在 config 调到 5，但不允许 2 或 4（避免无中位）。

**奇数池单一事实之源（YELLOW-Y8 / C-rev4 → YELLOW-Y4 / C-rev5 重构）**：奇数池不变量的**单一事实之源**是 `nanobot/evolve/schemas.py` 中的模块级 helper `_assert_odd_pool_size(n, *, context)`。`JudgePool._odd_pool_only` field_validator（运行时构造防线，覆盖任何 `JudgePool` 直构造路径）与 `EvolveDefaults._odd_pool_size` field_validator（config 层防线，让 config 错误尽早 fail 在 load 阶段）**都是该 helper 的薄 delegate** —— 各自只负责把字段值（`list[JudgeConfig]` 或 `list[str]`）的长度传入 helper，再附上 context 字符串供错误归因。任何关于「奇数 / 是否允许 0」的规则修改**只**需要修改 helper 一处；两个 validator 自动跟随。M5 若放宽（如允许 even=2 用于 A/B 测试）也只在 helper 内开口子，避免双 validator 错误信息漂移。

**`effective_min_quorum` 语义（决策 #86）**：默认（`min_quorum=None`）→ `(len(judges) // 2) + 1`（多数派；3→2, 5→3, 1→1），保留中位聚合的统计意义；任一 record 评分时若 `len(available_judges) < effective_min_quorum` → 抛 `JudgeError`，附 `degraded_below_quorum=True` flag。单 judge 模式（`len(judges) == 1`）按决策 #81 仅 dev 用，此时 `effective_min_quorum == 1` 退化为「judge 不可用即中断」。显式传 `min_quorum > len(judges)` 在构造期即抛 `ValueError`（`_validate_quorum_bounds`），显式传 `min_quorum < 1` 由 `Field(ge=1)` 在 Pydantic 字段层即拒绝。

**无 Pydantic forward ref（决策 #87）**：§3.x 全部数据模型的字段类型注解均在 module-load 期解析完成，**不**依赖 `model_rebuild()` / `from __future__ import annotations`。决策 #87 把 `RubricWeights` 迁到 `nanobot/evolve/schemas.py`（零-extra-deps）后，`nanobot.config.schema` 可直接 `from nanobot.evolve.schemas import RubricWeights`，旧的 `"RubricWeights"` 字符串前向引用 + `_import_rubric_weights()` lazy helper 一并删除。下游 evolve 类（`JudgeResult.score` 等）也均使用具名 import，不留 forward-ref 字符串。

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
# 完整定义（含 EvolveError mixin + 运行时 backstop）见 §5.3；以下仅复述 lazy-guard 引用的最小切面。
class EvolveExtraNotInstalled(EvolveError, ImportError):
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
from typing import ClassVar, Literal, Optional
from datetime import datetime
from nanobot.evolve._base import EvolveBase

class GateResult(EvolveBase):
    """单 gate × 单 candidate 的判定结果。"""

    gate_name: str                                 # 与 Gate.name 同
    candidate_hash: str                            # 引用 Candidate.content_hash
    baseline_hash: str                             # 引用 Baseline.content_hash
    verdict: Literal["pass", "fail"]
    metrics: dict[str, float]                      # gate-specific 量化指标（仅浮点）
    evidence: Optional[dict[str, str]] = None      # 决策 #116 / C-rev14 / B-Y6：
                                                   # 非数值 audit-trail 标识（hex hash /
                                                   # 路径 / external job-id 等）。pass / fail
                                                   # 路径同时承载；与 metrics 角色正交。
    failure_reason: Optional[str] = None           # verdict == "fail" 时必填（人读 message）
    timestamp: datetime
    duration_ms: int

class Gate(ABC):
    """Gate registry 元素。所有具体 gate 必须实现 name + evaluate。"""

    # 决策 #117 / C-rev14 / B-Y11：默认 deterministic（双跑等价 assert 适用）；
    # 未来 LLM-judge / human-PR async gate 显式 override 为 True 跳过等价检查。
    NONDETERMINISTIC: ClassVar[bool] = False

    # 决策 #122 / C-rev15 / C-Y2：subclass declaration registry。
    # 任何 `class FooGate(Gate)` 在 class-body 执行时自动追加到 `_subclasses`，
    # 让 §6.4.1 contract test 不依赖 `nanobot.evolve.gates` 包对象上的 re-export
    # （即使新增 `gates/foo.py` 但忘 `__init__.py` re-export，orphan 也被捕获）。
    # 与 `GATES` ordered execution list 角色正交：`GATES` 是顺序执行清单；
    # `_subclasses` 是 declaration-time registry（不影响 evaluate 调用顺序）。
    #
    # ── C-rev16 / RF-2 + RF-3 + RF-4 + RF-7 forward-notes ──
    # 1) Test-fixture isolation（RF-2 / Corr-1 70%）：测试代码 MUST NOT 直接
    #    subclass `Gate`（class-level mutable `_subclasses` list 会被 fixture
    #    持久化污染，破坏后续 assertion）。改用 `unittest.mock.Mock(spec=Gate)`
    #    或 duck-typed double。§6.4.1 contract test 通过 `__module__` prefix
    #    filter（仅保留 `nanobot.evolve.gates.*` 子类）作为 defense-in-depth
    #    容忍 accidental 违规，但 canonical 规则仍是"`tests/` 不 subclass Gate"。
    # 2) Abstract-intermediate forward-compat（RF-3 / Corr-2 + Arch-2 60%）：
    #    M5+ 引入的 abstract intermediate（如 `class JudgedGate(Gate, ABC):
    #    ...` 承载 LLM-judge gate 4 的共享逻辑）会落入 `_subclasses` 但因
    #    abstract 无法实例化进 `GATES`。§6.4.1 contract test 用
    #    `inspect.isabstract` filter 排除此类 case，避免 false-fail。仅
    #    concrete production 子类必须出现在 `GATES`。
    # 3) Import-ordering invariant（RF-4 / Scope-2 75%）：任何 declare `Gate`
    #    子类的模块 MUST 在 `nanobot.evolve.gates.Gate` 自身 import 之后被
    #    import。production 代码通过 `gates/__init__.py` 的 `from .test_pass
    #    import TestPassGate` (etc.) 自然满足；M5 plugin 作者必须确保 gate
    #    模块走 `nanobot.evolve.gates` 命名空间被加载，**不**通过 deferred /
    #    lazy loader 绕过 package init —— 否则 `__init_subclass__` hook 不会
    #    触发，子类不进 `_subclasses` registry。
    # 4) ABC metadata accumulation forward-marker（RF-4 / Arch-4 YELLOW）：
    #    `Gate` ABC 当前承载两个 harness-introspection ClassVar
    #    （`NONDETERMINISTIC` 来自 #117，`_subclasses` 来自 #122，
    #    `__init_subclass__` 是 #122 的 hook）。若 M5+ 再增第三个 such hook
    #    （e.g. `IS_ASYNC: ClassVar[bool]` per §6.6.1 forward-note for gate-5
    #    human-PR async 路径），则需拆分为：(i) `Gate`（business contract：
    #    `evaluate()` 签名）+ (ii) `_GateHarnessMetadata` mixin 或 sidecar
    #    模块承载 introspection ClassVar。M5 spec 起草时 acknowledge 此
    #    splitting trigger；若推迟过 M5 gate-5 引入则在 §12 carry-forward
    #    新登记 entry 跟踪。
    # 5) Distinct from #104（RF-7 / Arch-5 informational）：决策 #104 的
    #    `__init_subclass__` enforces 字段 redeclaration（缺失即 raise
    #    `TypeError`）；本决策 #122 的 hook 是 collection-only（registry
    #    append，**不** validate）。两 pattern 共享 Python idiom 但解决不同
    #    问题，cosmetic similarity 不构成语义重叠。
    _subclasses: ClassVar[list[type["Gate"]]] = []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        Gate._subclasses.append(cls)

    @property
    @abstractmethod
    def name(self) -> str:
        """形如 '1-test-pass' / '2-size-cap' / '3-cache-compat'；序号即 GATES 中位置。"""

    @abstractmethod
    def evaluate(self, candidate: "Candidate", baseline: "Baseline") -> GateResult:
        """同步评估；不允许调网络（gate 级要求 deterministic 当 NONDETERMINISTIC=False）。"""

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
from pydantic import ConfigDict
from datetime import datetime
from nanobot.evolve._base import EvolveBase

class JudgeSummary(EvolveBase):
    """跨 record 的 judge 评分汇总（manifest 用，不含原始 reasoning）。"""

    record_count: int
    median_aggregate: float
    median_process: float
    median_output: float
    median_token: float
    consensus_split_count: int                     # JudgeConsensus.consensus_verdict == "split" 计数

class RunManifest(EvolveBase):
    """<workspace>/evals/runs/<run_id>/manifest.json 的根对象。

    `frozen=True` override（YELLOW-8）：manifest 一经构造即不可变；任何下游
    （`pr_writer`、`apply` 子命令）只读消费。这是 §3.7.1 「无 PII」不变量的
    第二道机械护栏（第一道是 `extra='forbid'`，从 `EvolveBase` 继承）：
    构造后再 mutate 字段会抛 `pydantic.ValidationError`，无法静默偷加 PII。
    """
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=EvolveBase.model_config["alias_generator"],
        populate_by_name=True,
        frozen=True,
    )

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

**机械护栏（三层防御）**：

1. **构造期**：`EvolveBase` 的 `extra="forbid"`（§3.0）让任何未声明字段在 Pydantic 构造时即 raise `ValidationError`，杜绝"悄悄多带一个 `raw_input` 字段"。
2. **写出期**：`RunManifest` 自身 `frozen=True`（见上）让 manifest 构造后无法 mutate；任何后写改字段抛 `ValidationError`。
3. **PR 生成期**：`pr_writer` 在生成 `pr_body.md` 时**额外**校验：扫描 manifest jsonify 后内容，若任一字符串字段长度 > 256 chars 或含 high-entropy substring（用 zxcvbn-style heuristic）即抛 `ManifestPrivacyViolation`，阻断 PR 生成。

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

**CLI dispatch（YELLOW-2）**：CLI handler 直接调 `nanobot.evolve.init_workspace(workspace)` 模块级函数，**不**实例化 `OfflineHarness`。bootstrap 不依赖 config / lazy import / extra；保持与主 pipeline 解耦（详见 §5.1 模块级函数定义）。

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

落实路线图 §6 约束 4 + §0.4 行「4. 离线层 PR-only」；详细模板见 §8.3。

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
| `--force` | flag | False | 允许覆盖已存在的 output-dir（默认报错 **exit 6**，`FileExistsError` 归 filesystem 可纠正前置；决策 #88）。**真原子语义（C-rev6 / 决策 #96）**：详见下方契约 —— Linux ≥ 3.15 + ext4/btrfs/xfs 走 `renameat2(RENAME_EXCHANGE)` 单 syscall swap；其它平台回退两步 `os.rename` 并显式标注 SIGKILL 窗口。`output_dir.parent` 必须 writable（pre-step 0a 检查）。Pre-step 0b 一律先 sweep `<output_dir>.old-*` / `<output_dir>.staging-*` 残留（前次 crash debris），无残留即 no-op。失败映射：pre-step 0a/0b 失败 → exit 2；staging build / swap 失败 → exit 6 |

**`--force` 真原子语义（C-rev6 / 决策 #96；supersedes C-rev5 staging+os.rename two-step）**：

**Pre-step 0a — parent-dir access 前置（Y-arch-3 + Y-corr-rev6-7 / Z4）**：

```python
parent = output_dir.parent
# Z4 / Y-corr-rev6-7：必须同时具备 R_OK | W_OK | X_OK；缺 R_OK 或 X_OK 时
# pre-step 0b 的 iterdir() 会抛 PermissionError → 落 unmapped OSError → exit 6,
# 破坏"pre-step → exit 2"契约。
if not os.access(parent, os.R_OK | os.W_OK | os.X_OK):
    raise EvolveEnvironmentError(
        f"parent of {output_dir} not accessible (need R|W|X): {parent}; "
        f"--force needs sibling staging slot + iterdir sweep"
    )
```

`--force` 要求在 `output_dir.parent` 内构造 sibling staging 目录；parent 不可读 / 不可写 / 不可执行 直接 fail，不进入后续 swap 流程。

**Pre-step 0b — pre-flight sweep `.old-*` / `.staging-*` 残留（Y-arch-4 / Y-corr-2 recovery）**：

```python
# Z4 belt-and-suspenders：iterdir 自身亦可能抛 PermissionError / OSError；
# pre-step 0a 已对 R|W|X 做硬前置，但 race（permissions 在两步之间变更）/
# bind-mount 边界等仍可能让 iterdir 失败，统一映射到 exit 2 而非 unmapped exit 6.
try:
    siblings = list(output_dir.parent.iterdir())
except OSError as e:
    raise EvolveEnvironmentError(
        f"cannot iterdir {output_dir.parent} for sweep: {e}; "
        f"check parent permissions (R|W|X required)"
    ) from e

for sibling in siblings:
    if sibling.name.startswith(f"{output_dir.name}.old-") or \
       sibling.name.startswith(f"{output_dir.name}.staging-"):
        try:
            shutil.rmtree(sibling, ignore_errors=False)
            logger.info("pre-flight sweep removed stale debris: %s", sibling)
        except OSError as e:
            raise EvolveEnvironmentError(
                f"stale debris at {sibling} blocks --force; clean manually: {e}"
            ) from e
```

此 sweep 同时承担 (a) 清理 C-rev5 SIGKILL 窗口遗留的 `.old-*`（即下方 step 4 提到的 fallback 路径上、step c→d 之间 crash 后的恢复），(b) 清理任何前次失败的 `.staging-*` 半成品。无残留时 `iterdir` 返回 0 个匹配项，no-op。

**Pre-step 0c — 并发 `--force` 序列化锁（W4 / 决策 #102 / Option α）**：

```python
# POSIX：fcntl.flock(LOCK_EX | LOCK_NB) on <output_dir>.lock sentinel
# 锁文件路径：<output_dir>.lock（与 output_dir 同 parent，便于 0a 的 access 前置覆盖）
lock_path = output_dir.parent / f"{output_dir.name}.lock"
# C-rev10 / Corr-3 / 决策 #105：os.open 自身的 OSError MUST 被映射为
# EvolveEnvironmentError → exit 2，与 fcntl.flock 的 BlockingIOError
# 包装对齐。否则 EROFS / ENOSPC / EACCES / parent dir 失踪等错误会
# 绕过 dispatch 表落 unmapped exit 6，破坏 "pre-step 失败 → exit 2" 契约。
try:
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
except OSError as e:
    raise EvolveEnvironmentError(
        f"lockfile create failed at {lock_path}: {e}; "
        f"check parent permissions / disk space / readonly-fs"
    ) from e
try:
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError as e:
    os.close(lock_fd)
    raise EvolveEnvironmentError(
        f"another --force in progress on {output_dir}; "
        f"lock held at {lock_path}. Wait for prior invocation to finish."
    ) from e
# 持锁直至 step e（cosmetic cleanup）完成；finally 段 fcntl.flock(LOCK_UN) + os.close
# + best-effort os.unlink(lock_path)（unlink 失败 WARN，不影响 exit code）。
```

**Windows fallback**：`fcntl` 不可用时，best-effort 写一个含当前 PID 的 `.lock` 文件 + 启动时检查（PID 仍活则 raise `EvolveEnvironmentError`）。Windows 路径有 race window（PID 检查与文件创建非原子），spec 显式 acknowledge 此 caveat；M4 CI 仅 Linux，Windows 由 M5+ 视需要加固（或改用 `msvcrt.locking`）。

**NFS / 网络文件系统 caveat（C-rev10 / Corr-3 / 决策 #105）**：M4 仅支持本地 POSIX 文件系统（ext4 / btrfs / xfs / tmpfs）的 `--force` 流程。**NFS / 网络文件系统在 M4 阶段 unsupported** —— Linux NFS pre-2.6.12 上 `fcntl.flock` 退化为 per-fd 本地锁，跨进程互斥失效；NFSv4 lockd 行为亦受 mount 选项（`local_lock=`）影响。共享 workspace（团队 NFS / SMB）场景请改用本地 staging dir 或等 M5 加固（计划用 `fcntl.fcntl(F_OFD_SETLK)` + lockd 探测）。共享 fs 上跑 `--force` 在并发场景下会 silently 让两个 invocation 同时进入主流程，破坏决策 #102 的串行化契约。

**并发契约（W4 / 决策 #102）**：

- 同一 `output_dir` 上的并发 `apply --force` 调用**被显式序列化**：第二调用立即收到 `EvolveEnvironmentError` → exit 2（用户应等待或重试）。
- 不同 `output_dir` 的并发 `apply --force` 调用**互相独立**，无锁冲突。
- 此并发契约**与** §5.1 「`OfflineHarness.run` is not reentrant」**正交**：后者讲单 `OfflineHarness` 实例内 `run()` 不可重入；本契约讲跨进程的 `apply --force` 写盘序列化。Python API 与 CLI 路径共用同一锁实现（CLI 走 `OfflineHarness.apply`）。

Sweep 与 lock 的顺序：0a → 0b → 0c → 主流程。0b 先 sweep 残留是因为残留的 `.staging-*` 不一定带活 lock（前次 crash 可能在 release lock 前发生但 lock 文件已被 unlink）；0c 紧接其后确保后续 staging build 与 swap 期间独占 parent。

**主流程**：

1. 若 `output_dir` 不存在 → 行为同 `force=False`，直接构建到 `output_dir`（无须 swap）。
2. 若 `output_dir` 存在，按以下步骤执行：
   a. 把新 bundle 构建到 sibling staging 目录 `<output_dir>.staging-<run_id_short>`
      （同 parent 目录确保 rename 在同一 mount）。
   b. 若 staging 构建失败（磁盘满 / `OSError` / `KeyboardInterrupt`）→ cleanup
      时 rmtree staging 目录、保留旧 `output_dir` 不变、向上 raise。
   c. **Atomic swap**（契约层；实现细节移至 `nanobot/evolve/_atomic_swap.py` helper —— 决策 #98 / Z1）：
      在 Linux ≥ 3.15 配合 ext4 / btrfs / xfs 时，swap 通过 `renameat2(RENAME_EXCHANGE)`
      单 syscall 完成 staging 与 output_dir 的原子互换 —— crash 在 syscall 之前或
      之后均为合法状态，**无中间窗口**。在不支持的平台（macOS、Alpine/musl、*BSD、
      pre-3.15 Linux、tmpfs 等）上自动回退到两步 `os.rename`，回退路径的 SIGKILL
      窗口由下次 `--force` 调用的 pre-step 0b sweep 透明恢复。swap 后 staging 路径
      指向旧 bundle 内容，命名为 `<output_dir>.old-<run_id_short>` 准备 cleanup。

      **Helper 模块契约（`nanobot/evolve/_atomic_swap.py`，决策 #98 / Z1；W1 / C-rev8 重构）**

      本段拆分为 **(a) Helper contract** 与 **(b) Implementation guidance — known regression guards** 两个清晰分离的小节。契约只描述外部可依赖的 outcome；mechanism 细节降级为非绑定 guidance（决策 #101 / W1）。

      **(a) Helper contract** — `atomic_swap(src: Path, dst: Path) -> bool`：

      1. **Portability**：MUST 跨平台解析系统 C 库 / atomic-swap syscall，不得硬编码 libc 文件名；在 glibc Linux、musl Alpine、*BSD、macOS 上均不能因 libc lookup 失败而 crash（lookup 失败应自动 fallback 而非 raise）。
      2. **Path safety**：MUST 处理 surrogateescape 文件名（无法用 `PYTHONIOENCODING` 表达的 bytes），调用方传 `Path` 含此类字节不得抛 `UnicodeError`。
      3. **Fallback semantics**：MUST 在内核报告 atomic-swap syscall 在当前 platform / filesystem 上不支持时，且**仅在**此时，回退到两步 `os.rename`；其它 syscall 错误以未修改的 `OSError` 透传给 caller。
      4. **Preconditions**：`src` 与 `dst` MUST 同时存在；MUST 同 mount。
      5. **Postconditions**：返回（无论 `bool` 值），`src` 与 `dst` 路径各自指向对方调用前的 inode（atomic-swap 语义）。
      6. **Return value**：`True` iff 单 syscall 成功；`False` iff 两步 fallback 完成。`False` **永不**在 swap 未完成的情况下返回。

      **(b) Implementation guidance — known regression guards**（**非**契约的一部分）：

      > 以下细节是基于历轮 review 抓到的回归 bug 给出的实现建议；它们**不是**契约的一部分 —— 一个满足上方 (a) contract 但未采用以下选择的实现也是正确的。

      - **libc 解析**：用 `ctypes.util.find_library("c")` 而**非**硬编码 `libc.so.6`，避免 C-rev6 macOS / Alpine crash（闭合 Y-corr-rev6-2）。
      - **lookup 错误防御**：把 `ctypes.CDLL(...)` 与 `libc.renameat2` 符号查找包在 `try/except (OSError, AttributeError)` 中；任一失败即 fallback。
      - **fallback 触发 errno 集合**：`{errno.EINVAL, errno.ENOSYS, errno.ENOTSUP, errno.EOPNOTSUPP}`（闭合 Y-corr-rev6-1）；其它 errno 透传裸 `OSError` 由 §4.6 dispatch 落 exit 6。
      - **路径编码**：以 `os.fsencode(path)` 处理 src / dst（**不**用 `str(path).encode()`，闭合 Y-corr-rev6-8）。
      - **平台覆盖矩阵**：glibc Linux ≥ 3.15 + ext4/btrfs/xfs → preferred path（`renameat2(RENAME_EXCHANGE)` 单 syscall）；macOS / Alpine musl / *BSD / pre-3.15 Linux / tmpfs → fallback path（两步 `os.rename`）。
      - **跨 mount 前置**：caller MUST 保证 src 与 dst 同 mount；当前 `--force` 流程通过"sibling 同 parent dir"已天然满足，helper 内不必重复校验。

      **(c) Test contract（W5 / C-rev9 / 决策 #98 amend；C-rev10 / Corr-4/5/6 强化）**：M4 plan 期在
      `tests/evolve/test_atomic_swap.py` 落地以下两条 contract test，机械化锁定
      上方 (a) clause 4–6 的可观测 outcome（与 ctypes 实现细节解耦；任何满足
      contract 的替代实现也应通过这两条 test）：

      - **`test_atomic_swap_call_dispatch`**（C-rev10 / Corr-4 + Corr-5；C-rev11 / YELLOW-4 拆分自原 `test_atomic_swap_postcondition`，仅保留 mocked call-count 断言；inode-identity 后置移至下方独立 real-fs test）：

        **Monkeypatch scope（C-rev10 / Corr-4）**：MUST 用 module-scoped
        `monkeypatch.setattr` 形态精确替换 helper 模块内部解析的符号引用，
        **不**是 patch 全局 `os.rename` —— 否则 pytest 收集期 / 其它 fixture
        的 rename 调用也会被计入，导致计数断言假阳/假阴：
        ```python
        monkeypatch.setattr("nanobot.evolve._atomic_swap.os.rename", mock_rename)
        monkeypatch.setattr(
            "nanobot.evolve._atomic_swap.libc.renameat2",  # 或等价的 helper-内符号
            mock_renameat2,
        )
        ```
        Spec 强制要求："MUST patch the helper-module-scoped reference, not the
        global `os.rename`, to avoid mis-counting unrelated test-fixture rename
        calls."

        **Parametrization（C-rev10 / Corr-5）**：MUST 用 pytest 双分支
        parametrize（或等价的二测试拆分），让两条互斥分支各自独立运行：
        ```python
        @pytest.mark.parametrize("simulate_renameat2_success", [True, False])
        def test_atomic_swap_call_dispatch(simulate_renameat2_success, ...): ...
        ```
        Spec 强制要求："MUST be parametrized over both branches; a single
        non-parametrized test that asserts both clauses cannot exercise both
        code paths."

        **Branch assertions（call-count only — inode-identity 不在本 test 内）**：

        * 若 helper 返回 `True`（`simulate_renameat2_success=True`）：观察到
          **exactly 1** 次成功的 `renameat2` 调用 AND **0** 次 `os.rename`
          调用。
        * 若 helper 返回 `False`（`simulate_renameat2_success=False`，
          fallback 触发 errno 在 mock 中以 `OSError(EINVAL)` 等模拟）：观察
          到 **0** 次成功的 `renameat2` 调用 AND **exactly 2** 次 `os.rename`
          调用（fallback path 的 staged two-step swap）。

        此 test 是对 contract clause 6（"`False` 永不在 swap 未完成情况下返回"）
        的可观测断言：通过观察 `os.rename` 次数严格 == 2，排除"helper 提前
        return `False` 但只完成一次 rename" 的中间态 leakage。**注意**：因
        mocks 不真正完成 inode-swap 物理动作，本 test **不**断言 inode 后置；
        contract clause 5（inode-identity postcondition）由下方独立 real-fs
        test 在非 mocked 路径下机械化。

      - **`test_atomic_swap_inode_swap`**（C-rev11 / YELLOW-4 / Corr-6 拆分得来的 real-fs test）：非 mocked；用真实 `tmp_path` / 两个真实文件，调用 `atomic_swap(src, dst)` **一次**，断言 contract clause 5（inode-identity postcondition）：

        ```python
        @pytest.mark.skipif(
            sys.platform != "linux",
            reason="renameat2 is Linux-only; fallback path covered separately",
        )
        def test_atomic_swap_inode_swap(tmp_path):
            src = tmp_path / "a"; src.write_bytes(b"A")
            dst = tmp_path / "b"; dst.write_bytes(b"B")
            src_ino_before = os.stat(src).st_ino
            dst_ino_before = os.stat(dst).st_ino
            atomic_swap(src, dst)
            assert os.stat(src).st_ino == dst_ino_before
            assert os.stat(dst).st_ino == src_ino_before
            assert src.read_bytes() == b"B"
            assert dst.read_bytes() == b"A"
        ```

        理由（C-rev11 / YELLOW-4 闭合）：合并版 test 让 mocks 同时承担"call-count
        计数"与"完成真实 inode-swap"两个互相冲突的角色 —— 让 mock 真正完成 swap
        会把测试 fixture 复杂化（mock 必须有 side effect 执行真 rename），违反
        mock 的 surface 限定原则。拆分让 mocked test 专注 call dispatch，real-fs
        test 专注 postcondition observable；后者用 `@pytest.mark.skipif` 排除
        无 `renameat2` 的平台（macOS / Windows / 旧内核），fallback 路径由
        `test_atomic_swap_call_dispatch` 的 `simulate_renameat2_success=False`
        分支已在 mock 层覆盖。

      - **`test_atomic_swap_preconditions`**：构造 `src` 不存在或 `dst` 不存在
        两种 fixture，调用 `atomic_swap(src, dst)` MUST 抛 `FileNotFoundError`
        （非裸 `OSError`、非 silent `False`）—— 闭合 contract clause 4
        ("`src` 与 `dst` MUST 同时存在") 的可观测断言。

      三组 assertion（call-count 计数 × 2 分支 mocked + inode-identity real-fs
      Linux-only + precondition raise）共同把 W1 重构产物从 "spec 描述层契约"
      提升为 "CI 拦截层契约"，防止后续实现重构破坏 contract clause 4 / 5 / 6 而
      spec 文本无 fail-loud 通道。C-rev11 / YELLOW-4 拆分让 mocked 与 real-fs
      关注点解耦：前者验证 dispatch 逻辑、后者验证 inode-swap 物理后置。

      **(d) Lockfile-release test contract（C-rev10 / Arch-1 / 决策 #102 amend）**：
      并行于上方 atomic-swap test，M4 plan 期在 `tests/evolve/test_apply_lockfile.py`
      落地 `test_force_lock_released_on_exception` —— 机械化锁定 pre-step 0c
      lockfile 的 release 不变量（`fcntl.flock(LOCK_UN)` + `os.close` + `os.unlink`
      在所有退出路径都 fire）。三个 fixture 覆盖 finally-correctness 全谱：

      * **Fixture A — 异常路径（staging build OSError）**：在 step 2a（staging
        构建）阶段 inject `OSError`（如 mock `Path.mkdir` 抛 ENOSPC）。
        Assertion（C-rev11 / YELLOW-5 重表述）：异常向上 propagate 后，**第二个**
        子进程对相同 `<output_dir>.lock` 路径执行 `flock(LOCK_EX | LOCK_NB)`
        **MUST succeed without `BlockingIOError`** —— 前次持锁者已释放即第二个
        非阻塞 flock 立即返回；若锁仍被持，`LOCK_NB` 直接 raise `BlockingIOError`，
        本断言便 fail。`flock(LOCK_EX | LOCK_NB)` 是 O(syscall) 的内核原语，**不
        受 wall-clock 抖动影响**。fixture 用 `multiprocessing.Event` 在子进程
        起步时 set，确保 fixture 主线在调度第二个 flock 之前确认子进程已 fully
        running（消除 spawn-latency 假阴）。**100ms 软时限是 CI smoke-test 的
        wall-clock 上界**（覆盖 subprocess spawn + Event handshake 的调度抖动），
        非 lock-acquire 原语的语义保证；超时即视为 CI 调度异常 / fixture
        infrastructure bug，非 lock contract 失败。

      * **Fixture B — 中断路径（staging build KeyboardInterrupt）**：同 A 但
        inject 改为 `KeyboardInterrupt`（模拟 user Ctrl-C）。Assertion 同 A
        —— Python `try/finally` 对 KeyboardInterrupt 必须正确 unwind。

      * **Fixture C — 成功路径**：正常完成 step 2e（cosmetic cleanup）。
        Assertion 同 A —— 成功路径同样必须 release lock。

      三 fixture 共同覆盖 "exit on exception / exit on Ctrl-C / exit on success"
      三种 finally 触发场景，闭合决策 #102 引入的 lockfile contract 在 CI 层的
      验证空缺；与 W5 的 atomic-swap test contract 形成"pre-step 0c lock + step
      c swap" 双 helper 各自独立的 mechanical-enforcement pair。
   d. **Fallback path 契约**（caller-visible 行为）：当 `atomic_swap` 返回 `False`
      （fallback engaged），保证 staging 与 output_dir 的"位置交换"语义不变，唯一
      差异是中间存在 SIGKILL 窗口 —— crash 留下 `output_dir` 缺失而 `.old-*` 存在
      的中间状态。该状态由**下次 `--force` 调用的 pre-step 0b sweep** 透明恢复
      （把 `.old-*` 视为 debris 清掉，然后正常 build 到 `output_dir`）。除此之外，
      SIGKILL 窗口不会让 bundle 内容损坏（旧内容仍在 `.old-*` 内，新内容仍在
      staging 内或已就位）。
   e. `shutil.rmtree(<output_dir>.old-<run_id_short>)` —— 包 try/except 仅 WARN，
      不 raise（swap 已成功，残留是 cosmetic；下次 `--force` 的 pre-step 0b 会再清）：
      ```python
      try:
          shutil.rmtree(f"{output_dir}.old-{run_id_short}", ignore_errors=False)
      except OSError as e:
          logger.warning("cosmetic cleanup of .old- sibling failed: %s", e)
      ```
3. 退出码映射：
   - pre-step 0a/0b 失败 → exit 2（用户应纠正环境后重试）
   - staging build 任一步 `OSError`、step c/d swap 失败 → exit 6（filesystem
     家族，调用方可纠正后以 `--force` 重试）
   - step e cleanup 失败 → WARN log，不影响 exit code（swap 已成功，bundle 正确）
4. **唯一**非原子窗口（仅 fallback 路径）：见 step d caveat。preferred 路径（renameat2）
   不存在该窗口；下次调用的 pre-step 0b sweep 是 fallback 路径的安全网。
5. 术语严格化：本节中「原子」**仅**指 step c 的 `renameat2(RENAME_EXCHANGE)` 单
   syscall，或 fallback 中夹在两个 `os.rename` 之间的 swap 整体（非中间瞬间）；
   pre-flight sweep 与 step e cleanup 用「best-effort / 可恢复」描述。这与 §3.7 /
   §4.1.1 的 `os.replace`-based atomic write 保持术语一致。

> 注：M4 删除了 `--format json` 标志。`apply` 始终输出标准多文件目录；目录本身就是 machine-readable（CI 直接读 `pr_body.md` / `diff.patch` / `manifest.json`），无需再封一层 JSON。

#### 4.4.3 前置校验

| 检查 | 失败时 |
|---|---|
| run-id 前缀长度 / 唯一性（§4.3.1 算法） | exit 2（长度 < 4 或歧义）；exit 6（无匹配） |
| `<run-id>/manifest.json` 可解析 | exit 6（fs/state） |
| `manifest.final_status == "promoted_to_pr"` | **exit 8**（apply 业务终态，narrowed；决策 #88） |
| `manifest` 通过 §3.7.1 「无 PII」不变量（`pr_writer` 二次扫描） | exit 4（`ManifestPrivacyViolation`） |
| `--output-dir` 已存在且 `--force=False` | **exit 6**（`FileExistsError`；filesystem 可纠正前置；决策 #88，原 8 → 6） |

#### 4.4.4 退出码

成功返回 `0`；失败分类详见 §4.6 全表。本子命令**永不**触发 `BaselineMismatch`（exit 7）或 `JudgeError`（exit 5），那两类异常只可能在 `evolve run` 中出现。本子命令的失败码（决策 #88）：exit 8（apply 业务终态：`final_status != promoted_to_pr`）+ exit 6（filesystem / 可纠正前置：`FileExistsError` + `FileNotFoundError`）+ exit 4（隐私）+ exit 2（参数错）。

### 4.5 Config 字段（`agents.defaults.evolve.*`）

落实 §0.2 #75 / #76 / #79；新增字段定义在 `nanobot/config/schema.py`，挂于现有 `AgentDefaults` 模型下的新 `EvolveDefaults` 子模型。

```python
# nanobot/config/schema.py（M4 plan 期落地的 delta）
# Base、ConfigDict、Field、field_validator、model_validator 由本文件 §schema preamble 已导入。
from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
# 决策 #87：直接 import RubricWeights（来自零-extra-deps 的 nanobot.evolve.schemas，
# 仅依赖 pydantic + stdlib）；旧 lazy helper `_import_rubric_weights` 与
# `nanobot/config/_evolve_types.py` shim 一并删除，断掉 config→evolve 反向耦合的
# 隐式路径。schemas.py 不 import dspy/gepa/litellm/optuna，故此 import 对未装
# `[evolve]` extra 的用户无副作用（探针测试见 §5.4.5 step 6）。
# Y-corr-3 / C-rev6：`_assert_odd_pool_size` 同样 module-top import（避免每次
# field_validator 触发 in-function import 开销 + 让依赖在 import 段显式可见）。
from nanobot.evolve.schemas import RubricWeights, _assert_odd_pool_size

# Base 来自本文件 §schema preamble；EvolvePrivacyConfig / EvolveDefaults 须继承 Base 而非 BaseModel，
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

    rubric_weights: RubricWeights = Field(default_factory=RubricWeights)
    """`RubricScore.aggregate` 加权（决策 #84，类型由 dict 改为 RubricWeights）；
    三维度和必须 == 1.0（容差 1e-6），由 `RubricWeights._sum_to_one` model_validator
    一处校验，本类**不**重复校验（YELLOW-7 / RED-6 Option A）。

    模块归属（决策 #87）：`RubricWeights` 居住 `nanobot/evolve/schemas.py`（零-extra-deps
    共享 schema）；本字段直接 import 该类，**无** forward-ref / lazy shim。
    JSON 配置中的字段形态仍是 `{"process": 0.4, "output": 0.4, "token": 0.2}`，
    通过 Pydantic 自动 coerce 到 `RubricWeights`（alias_generator 已设 camelCase
    则 key 为 `rubricWeights`）。
    """

    privacy: EvolvePrivacyConfig = Field(default_factory=EvolvePrivacyConfig)
    """脱敏管线配置；详见 §9。"""

    @field_validator("default_judge_pool")
    @classmethod
    def _odd_pool_size(cls, v: list[str]) -> list[str]:
        """Config 层奇数池校验（YELLOW-Y4 / 决策 #93 delegate；Y-corr-3 / C-rev6
        module-top import）。

        与 `JudgePool._odd_pool_only` 同样调用 `_assert_odd_pool_size` helper
        作为单一事实之源；helper 同时拒绝 0 与偶数（含 0%2==0 边界）。helper
        已在本模块顶部 import（见上方 import 段），无 in-function 开销。
        """
        _assert_odd_pool_size(len(v), context="EvolveDefaults.default_judge_pool")
        return v

    # 注：`_weights_sum_to_one` model_validator 已删除（RED-6 Option A / 决策 #84）。
    # `rubric_weights` 类型由 `dict[str, float]` 改为 `RubricWeights`，求和校验
    # 由 `RubricWeights._sum_to_one` 在子模型构造期一处完成；本类内重复校验
    # 既冗余又会在子模型 ValidationError 之后被错误覆盖。

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
| `rubric_weights` | `RubricWeights` | `RubricWeights()` (=0.4/0.4/0.2) | 求和 == 1.0 (由 `RubricWeights._sum_to_one` 单一来源校验，决策 #84) | §3.3 / §0.2 #79 |
| `privacy.allowed_url_hosts` | list[str] | `[]` | — | §9 |

CLI 标志 → config 优先级（从高到低）：CLI flag > `--config` 指定文件 > `~/.nanobot/config.json` > `EvolveDefaults` 内置默认值。

### 4.6 退出码全表（**新决策 #82 + #85**）

为让 CI / 自动化脚本可分流处理不同失败模式，M4 锁定退出码语义：

| Code | 含义 | 触发场景 | 可重试? |
|---|---|---|---|
| `0` | 成功（含业务判定为 reject 的 run） | run/init/report/apply 正常完成；gate fail 不映射到非零 | — |
| `1` | 通用错误（兜底） | 未分类的 Python 异常（不属于 2/3/4/5/6/7/8 任一类） | 否（traceback 入日志） |
| `2` | Harness 配置错误 | `rubric_weights` 不合规 / `judge_pool` 偶数 / `iterations < 1` / run-id 前缀长度 < 4 / 前缀歧义 | 否（需改 invocation） |
| `3` | `EvolveExtraNotInstalled` | 未装 `nanobot[evolve]`，`evolve run` 调用 | 否（需 `pip install`） |
| `4` | 隐私 / 安全 gate 违例 | `ManifestPrivacyViolation`（manifest 含 §3.7.1 禁字段 / `record_self_eval` 缺 `.gitignore` precondition） | 否（需修代码） |
| `5` | **`JudgeError` only**（瞬时 provider 失败） | `evolve run` 中 `JudgeError`（aux provider 调用 3 次重试后仍失败、`min_quorum` 跌穿、或 `require_consensus=True` 时 split） | **是**（指数退避，max 3 次） |
| `6` | Filesystem / 资源未找到 / 可纠正前置 | `init` 无法 mkdir / `.gitignore` 无法写入 / run-id 前缀无匹配（`FileNotFoundError`） / `<run-id>/manifest.json` 不可解析 / **`apply --output-dir` 已存在且 `--force=False`（`FileExistsError`，决策 #88）** | 调用方纠正后可重试（如 `--force`、改 `--output-dir`、修 run-id） |
| `7` | Harness invariant 违反 | `BaselineMismatch`（候选 `parent_baseline_hash` ≠ baseline `content_hash`，§3.2 invariant #1）。本码意味着 harness 自身契约破裂 | **绝不**（抓 trace 报 bug） |
| `8` | **Apply 业务终态**（narrowed，决策 #88） | `evolve apply` 时 `manifest.final_status != 'promoted_to_pr'`（候选未被 promoted，run 无可发布 artifact） | 否（重跑无意义，run 本身已 terminal） |

**异常 → 退出码的完整映射表见 §5.3**。

**新决策 #82 + #84 已追加 §0.3**。CI 分流原则：

- **exit 5 → 唯一可重试码**：仅 `JudgeError`，可指数退避（max 3 次，2s/4s/8s）。任何非 `JudgeError` 不会落到 exit 5（决策 #85）。
- **exit 6 → filesystem / 可纠正前置（决策 #88）**：run-id 不存在 / manifest 不存在 / `--output-dir` 冲突。调用方可纠正后重试（修 run-id / `--force` / 换 `--output-dir`）；纯 `FileNotFoundError` 子类（如 run-id 不存在）仍然 terminal。
- **exit 7 → harness invariant 破裂**：必须停止重试并向 maintainer 报 bug。
- **exit 8 → apply 业务终态（narrowed，决策 #88）**：仅 `manifest.final_status != 'promoted_to_pr'`，run 本身已终态；重跑相同 run-id 结果不变（需重新触发 `evolve run` 产新 run）。
- **exit 2 → 调用方参数错**：需修改 invocation 再重跑。
- **exit 1 → 未分类异常**：traceback 应入 CI 日志，按 bug 处理。

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
            ConfigError: workspace 路径不是目录（W6 / C-rev8 / 决策 #100 amend：
                原本签名声明抛裸 `ValueError`，会被 §4.6 dispatch 落到 exit 1
                catch-all 而非 exit 2（config / 参数错误）—— 与 `EvolveDefaults` /
                `JudgePool` 等 ctor 校验失败的 exit code 不一致，违反 §5.3
                "异常→exit code 映射" SoT。改为 `ConfigError` 让 ctor 参数校验失败
                与其它 config 类错误同族（exit 2），便于 CI 分流。

        注意：`__init__` **永不**触发实际 config 文件加载（即不抛
        `pydantic.ValidationError` / `EvolveExtraNotInstalled` —— 这些留给惰性
        `_ensure_config()`）；本处的 `ConfigError` 仅来自 ctor 自身参数校验
        （`workspace.is_dir()` 检查）。在没有 `~/.nanobot/config.json` 的全新
        机器上 bootstrap（`init_workspace`）必须成功 —— bootstrap 按定义不依赖
        运行时 config，且**不**经 `OfflineHarness` 实例（见下方模块级函数）。
        """

    def run(
        self,
        skill_name: str,
        *,
        tiers: Optional[list[str]] = None,            # 默认 ["A", "C"]
        iterations: Optional[int] = None,              # 默认 config.default_iterations
        seed: Optional[int] = None,                    # None → harness 自动生成
        judge_pool: "list[str] | JudgePool | None" = None,  # 决策 #89 / YELLOW-Y3
        rubric_weights: Optional[dict[str, float]] = None,
        dry_run: bool = True,                          # 默认 dry-run（与 CLI 一致）
    ) -> "RunManifest":
        """跑一次完整离线进化。等价于 CLI `nanobot evolve run`。

        **`judge_pool` 转换契约（YELLOW-Y3 / 决策 #89）**：
          - `None` → 使用 `config.evolve.default_judge_pool`（构造
            `JudgePool(judges=[JudgeConfig(model=s) for s in cfg], min_quorum=None)`
            → `effective_min_quorum` 解析为多数派 = `(n // 2) + 1`，严格中位
            consensus 语义）。
          - `list[str]`（CLI-shaped）→ 字符串列表，包装为
            `JudgePool(judges=[JudgeConfig(model=s) for s in pool])`，使用默认
            `min_quorum=None`。CLI 路径走这条。
          - `JudgePool` 实例 → **verbatim pass-through**，不做任何转换或合并；
            调用方已选定 `min_quorum`，harness 直接消费 `effective_min_quorum`。
            该路径让 Python API 调用方在 `frozen=True` config 下也能 override
            `min_quorum` 而不必先写盘 config。**具体消费者**：pytest fixtures +
            M5 judge-plugin callers（详见 §3.3 `JudgePool` 类定义 / 决策 #86
            `frozen=True` rationale）；CLI 路径按构造永不走 `JudgePool` 分支
            （CLI 始终通过 `--judge-pool` csv flag 传 `list[str]`）。

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
                  - 可用 judges 数 < `JudgePool.effective_min_quorum`
                    （决策 #86：runtime 必须读 computed property `effective_min_quorum`，
                    禁止直接读 `min_quorum`——后者可能为 `None`）
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

        `force` 语义（C-rev6 / 决策 #96；supersedes C-rev5 staging+os.rename two-step；
        决策 #88 提供 exit-code 归属）：
          - `force=False`（默认）：output_dir 已存在 → `FileExistsError` → exit 6
          - `force=True`：preferred path 用 `renameat2(RENAME_EXCHANGE)` 单 syscall
            原子互换（Linux ≥ 3.15 + ext4/btrfs/xfs）；其它平台回退两步 `os.rename`
            并由下次调用的 pre-flight sweep 恢复任何 SIGKILL 窗口残留。详细契约
            见 §4.4.2「`--force` 真原子语义」block；本 docstring 仅摘录退出码：
              * pre-step 0a parent-dir-writable 失败 → exit 2
              * pre-step 0b sweep 失败（残留无法清理）→ exit 2
              * staging 构建期 `OSError` → exit 6（filesystem）
              * step c/d swap 失败 → exit 6
              * step e cosmetic cleanup 失败 → WARN log，不影响 exit code
              * `KeyboardInterrupt` 期间：cleanup staging 目录后向上 propagate
                （无 exit code，CLI handler 自行决定）
            「原子」一词仅指 `renameat2` 单 syscall 或 fallback 两个 `os.rename`
            整体；pre-flight sweep / step e cleanup 走 best-effort，不抢占「原子」
            语义。

        Returns:
            Path: bundle 目录绝对路径（含 pr_body.md / diff.patch / report.md 拷贝）

        Raises:
            ConfigError: run-id 前缀长度 < 4 或前缀歧义（exit 2）
            FileNotFoundError: run-id 前缀无匹配（exit 6）
            ApplyTerminalError: manifest.final_status != 'promoted_to_pr'（**exit 8**，apply 业务终态；决策 #88 / #90 YELLOW-Y5）。专属异常与 `pydantic.ValidationError`（亦 `ValueError` 子类）解耦
            ManifestPrivacyViolation: manifest 含 §3.7.1 禁字段（exit 4）
            FileExistsError: output_dir 已存在且 force=False（**exit 6**，filesystem 可纠正前置；决策 #88，原 8 → 6）
            EvolveEnvironmentError: `--force` 时 pre-step 0a parent-dir access 失败 / pre-step 0b iterdir 或 sweep 残留无法清理（C-rev6 / 决策 #96；C-rev7 / 决策 #100 重命名自 `EvolveCliError`，drop `exit_code` 字段 — 类身份是 SoT，exit 2 由 §4.6 CLI dispatch 隐式归属）；用户应纠正环境后重试
            OSError: `--force` 时 staging 构建或 swap (`renameat2` / fallback `os.rename`) 失败（**exit 6**，C-rev6 / 决策 #96）；调用方可纠正后重试
            KeyboardInterrupt: `--force` staging 阶段中断 → cleanup staging 目录后 propagate；不映射到固定 exit code
        """


# === module-level — OUTSIDE class OfflineHarness ===
# bootstrap 函数；CLI `nanobot evolve init` 直接 dispatch 到此函数，**不**经
# OfflineHarness 类实例。理由：bootstrap 不需要 harness 对象、不需要 config、
# 不需要 lazy import — 与主 pipeline 解耦更清晰。CLI 调用形态见 §4.1。
def init_workspace(workspace: Path) -> None:
    """落地 §4.1 的 bootstrap：创建目录骨架 + .gitignore + README。

    幂等；等价于 CLI `nanobot evolve init`。模块级函数，签名独立于
    `OfflineHarness`，可在 `~/.nanobot/config.json` 缺失时调用。

    Args:
        workspace: workspace 根目录绝对路径

    Raises:
        OSError: 文件系统 I/O 错误（exit 6）
    """
```

**实例语义**：

1. 一个 `OfflineHarness` 实例对应一个 workspace + config 组合；可重复调 `run()`（产生独立 `run_id`）。
2. 不持有跨 `run()` 调用的状态（无 cache、无连接池）；每 `run()` 重新 lazy-import dspy/gepa、重建 provider client。
3. 不重入 / 不并发：构造便宜，并发场景请独立实例化（每实例独立 `run_id`，文件互不冲突）。
4. **`config` 参数的合法调用者**：仅 (a) pytest fixtures，(b) CLI thin wrapper（`nanobot/cli/commands.py`）。生产代码应当传 `config=None` 并依赖惰性加载；显式注入仅为测试与命令分发服务。
5. **`frozen=True` config + CLI override 路径（YELLOW-10）**：CLI 标志覆盖**必须**作为 `OfflineHarness.run()` 的 kwargs 传入（参见 §5.1 `run` 签名 `tiers` / `iterations` / `seed` / `judge_pool` / `rubric_weights` / `dry_run`），**禁止**通过 mutate `EvolveDefaults` 实例（§4.5 `frozen=True`）实现 override —— 直接给字段赋值会触发 `pydantic.ValidationError`。需在内部派生新 config 时使用 `model_copy`：

   ```python
   from nanobot.config.loader import load_config
   from nanobot.evolve.schemas import RubricWeights

   cfg = load_config()
   # 例 1：仅改 default_iterations。`model_copy(update=...)` 触发字段层
   # re-validation（这里 `default_iterations` 的 `ge=1, le=50` 重跑），不会触发
   # 任何 model_validator —— 因为本类 `EvolveDefaults` 上没有任何 model_validator
   # （决策 #84 删除了 `_weights_sum_to_one`，仅余 `_odd_pool_size` 是
   # `field_validator` 且只在 `default_judge_pool` 字段被更新时触发）。
   derived_iter = cfg.agents.defaults.evolve.model_copy(
       update={"default_iterations": 10}
   )
   # 例 2：换 rubric_weights → 间接触发 RubricWeights._sum_to_one model_validator
   # 重跑（在新 RubricWeights 构造期），保证派生 config 的求和不变量仍成立。
   derived_weights = cfg.agents.defaults.evolve.model_copy(
       update={"rubric_weights": RubricWeights(process=0.5, output=0.3, token=0.2)}
   )
   # 例 3：换 default_judge_pool → 触发 `_odd_pool_size` field_validator 重跑。
   derived_pool = cfg.agents.defaults.evolve.model_copy(
       update={"default_judge_pool": ["anthropic/claude-3-5-sonnet"]}  # 长度 1 = 合法奇数
   )
   # 三例均产生新 EvolveDefaults 实例；原 cfg.agents.defaults.evolve 不变。
   ```

   §4.5 配置优先级（CLI flag > --config > ~/.nanobot/config.json > 内置默认）由 `OfflineHarness.run()` 在入口处合并：harness 用 `model_copy(update=cli_overrides)` 派生一份本次 run 专用的 `EvolveDefaults`，原 config 对象保持 immutable。

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

    Entry sequence (strict order, YELLOW-Y6):
        1. **Disabled fast-path**（**禁止任何 fs syscall**）：先读 config，若
           `self_eval_enabled is False` 立即 `_log_once(...)` + `return None`。
           这一步**不**触发 `.gitignore` 探针，保证决策 #80 锁定的「低开销静默
           no-op」语义；测试断言见下方 Test contract。
        2. **Gitignore precondition guard**（仅当上一步未短路时执行）：见下方
           Precondition guard 章节；缺 `.gitignore` 或缺 `evals/self/` 行立即抛
           `ManifestPrivacyViolation`。
        3. **Directory creation + atomic write**（仅当 precondition 通过）。

        **测试契约（Z9 / Y-prod-2 — 实现住 `tests/evolve/test_record_self_eval.py::test_disabled_no_fs_probe`，spec 仅约束契约）**：disabled fast-path **不得**触发任何文件系统 syscall。测试以 monkeypatch 把以下 7 个 syscall 挂为 `pytest.fail`，调用 `record_self_eval(..., config.evolve.self_eval_enabled=False)`，任一被命中即 fast-path 契约破裂：

        - `os.stat`
        - `os.open`
        - `os.mkdir`
        - `os.listdir`
        - `os.scandir`
        - `pathlib.Path.mkdir`（belt-and-suspenders；底层走 `os.stat` 但单独捕获防 patch 顺序漏检）
        - `pathlib.Path.exists`（同上）

        相比 C-rev3 仅 patch `os.stat` 的窄覆盖，本 7-syscall 集合阻止未来贡献者用 `os.mkdir(...)` / `Path.exists()` 等绕过。

        **POSIX 限定（YELLOW-Y3 / C-rev5）**：上述 7 个 syscall 覆盖 Linux/macOS CI 的 `builtins.open` 走 `os.open` 内部路径。Windows 走 `_winapi.CreateFile` 不在本测试覆盖范围；当前 CI 仅 Linux，Windows CI 若 M5 引入需补 `_winapi.CreateFile` monkeypatch 或改用 `pyfakefs` 重写。

    Atomicity & concurrency contract:
        - 三个文件（`input.json` / `output.json` / `verdict.json`）各自走
          `<path>.tmp` → `os.fsync(fd)` → `os.replace(<path>.tmp, <path>)` →
          **directory fsync**（YELLOW-6）：
            ```python
            dir_fd = os.open(target_dir, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            ```
          原子落盘（沿用 `nanobot/agent/memory.py` 模式 + 显式 directory fsync）。
        - **directory fsync 是 atomicity 契约的一部分**（POSIX crash-safe rename
          要求）：`nanobot/agent/memory.py` 可能未做或正在改做 directory fsync，
          `record_self_eval` **不依赖**上游模块的实现，必须**自己**显式调用 —— 避免
          静默继承未来 memory.py 的潜在 gap。Windows 平台 `O_DIRECTORY` 不存在，
          此步 best-effort skip（POSIX-only 保证）。
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

    Precondition guard (RED-3):
        函数入口先做 `.gitignore` 校验，两条件**任一**命中即拒绝写入：
          (a) `<workspace>/.gitignore` **不存在** → 抛 `ManifestPrivacyViolation`；
              理由：缺少 .gitignore 意味着 `evals/self/` 必然未被忽略，首次写入
              即把 PII 引入 git 工作树。Round C-rev 的旧文案漏了此分支，导致
              全新 workspace + `self_eval_enabled=True` 的组合会静默写 PII。
          (b) `<workspace>/.gitignore` 存在但**不**包含 `evals/self/`（按 §4.1.1
              步骤 4 的行匹配算法精确匹配）→ 同样抛 `ManifestPrivacyViolation`。
        错误消息（两条件统一文案）：
          `ManifestPrivacyViolation(
              "Tier D enabled but evals/self/ is not gitignored; "
              "run `nanobot evolve init` first to bootstrap workspace",
              violated_invariant="§5.2 .gitignore precondition",
              offending_path=<workspace>/.gitignore,
              offending_fields=["evals/self/"],
          )`
        cross-ref §4.1.1 init step 4：init 子命令的 `.gitignore` 写入是
        Tier D 启用的硬前置；该校验确保 init 与 self-eval 之间的契约对齐。

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
import inspect
from typing import TYPE_CHECKING, ClassVar

# C-rev10 / Corr-1（C-rev11 / Tighten-1 收紧）：`manifest_path: "Path"` 与
# `offending_path: "Path | None"` 是 string-literal 前向引用，让静态类型检查器
# （mypy / pyright）解析 `manifest_path` / `offending_path` 字段类型。本模块的
# 运行时 introspection helper（如 `EvolveError.__init_subclass__`）使用
# `inspect.signature(cls.__init__)` 读取参数 `kind`（KEYWORD_ONLY），**不**
# eval 字符串注解，故 `Path` 不需要进入运行时 module globals。若未来引入
# 任何使用 `inspect.signature(..., eval_str=True)` 或 `typing.get_type_hints(
# cls.__init__)` 的 introspection helper，**必须**显式向 eval 时的 `globalns`
# 字典注入 `Path`（`get_type_hints(cls, globalns={"Path": Path})` 或等价做法）;
# `if TYPE_CHECKING:` 块下的 import 不会被运行时看到。pathlib 是 stdlib，故
# import 本身对 "no-extra" 探针无影响（不在依赖闭包内）。
if TYPE_CHECKING:
    from pathlib import Path


class EvolveError:
    """M4 evolve 异常族 mixin（W3 / C-rev9 / 决策 #99 amend）。

    本 mixin **不**承担运行时行为（既非 `Exception` 子类，亦不重写 `__init__`），
    仅承担两个 invariant 角色：

      1. **统一身份标签**：所有 evolve 自定义异常（无论实际基类是 `ImportError` /
         `ValueError` / `RuntimeError`）都 mix in 本类；外部 telemetry / CI 可用
         `isinstance(exc, EvolveError)` 一次性判定"是否来自 evolve 子系统"。
      2. **`STRUCTURED_KWARGS` 运行时 backstop**：`__init_subclass__` 在导入期对
         任何声明 `STRUCTURED_KWARGS: ClassVar[frozenset[str]]` 的子类校验
         **`STRUCTURED_KWARGS` 必须是其 `__init__` 的 keyword-only 参数集合的
         子集**（必填字段必须声明；额外的 keyword-only 参数允许，作为可选诊断
         字段）；任何 `STRUCTURED_KWARGS` 成员未出现在 ctor kw-only 参数中
         即 `TypeError` 阻断导入。C-rev11 / RED-1 / 决策 #107：旧"严格等于"
         语义会让 `ManifestPrivacyViolation`（`STRUCTURED_KWARGS = {"violated_invariant"}`，
         `__init__` 含三个 kw-only 参数 `violated_invariant` / `offending_path` /
         `offending_fields`）在导入期 `TypeError`，与本异常的设计意图（必填
         一项 + 两项可选诊断字段）矛盾；改为子集语义后两类合法形态（"严格相等"
         与"必填子集 + 可选超集"）均通过，缺失必填项仍 fail-loud。

    `__init_subclass__` 是对 §5.3 末尾 `test_no_self_raises_in_evolve` AST 静态
    检查的 **defense in depth** —— AST scan 无法解析的本地别名形态（如
    `cls_ref = self.exc_cls; raise cls_ref(...)`）在导入期被本 hook 直接拦截。
    AST + 运行时双层守卫共同闭合 `STRUCTURED_KWARGS` 注册表的"声明 vs ctor 真实
    签名"漂移窗口。

    继承约定：所有 STRUCTURED_KWARGS-declaring evolve 异常 MUST 把本类放在 MRO
    中（多继承形态 `class Foo(EvolveError, ValueError):`），且 **`EvolveError`
    必须是第一个 base**（C-rev10 / Arch-2）。该位置由 `test_evolve_error_first_in_mro`
    机械化执行：对每个 mix in `EvolveError` 的具体异常类断言
    `cls.__bases__[0].__name__ == 'EvolveError'`，防止 silent MRO drift（如
    `class Foo(RuntimeError, EvolveError):` —— 仍能通过 `isinstance` 检查，
    但 super().__init__ 解析顺序变化 + cooperative MRO 行为漂移）。本测试
    实现 ≈5 LoC，跟随 §5.3 末尾 registry-driven introspection 的同款风格
    （遍历 `nanobot.evolve.exceptions` 模块 + `inspect.isclass` 过滤）。

    **M5 forward-compat note（C-rev11 / YELLOW-6）**：任何后续 milestone 引入
    的、继承自既有 M4 结构化异常的子类（如 M5 计划中的
    `class GateRejected(ApplyTerminalError):`）**必须**采用显式双 base 形态
    `class GateRejected(EvolveError, ApplyTerminalError):` 以保持
    `cls.__bases__[0] is EvolveError` 这一 invariant；同时 cooperative
    `super().__init__(...)` 链 MUST 在 calibration test（M5 plan 期落地的
    `test_gaterejected_init_kwargs_propagate` 或等价 test）中走过，确保中间
    base 的 ctor 被正确串接。**Alternatively**（M5 设计期可选项）M5 spec
    若评估直 base 形态 `class GateRejected(ApplyTerminalError):`（不重复
    `EvolveError`）实现负担更低，可选择把 `test_evolve_error_first_in_mro`
    的断言**放宽**为 `EvolveError in cls.__mro__[: cls.__mro__.index(BaseException)]`
    （检查 `EvolveError` 出现在 `BaseException` 之前的 MRO 段，而非严格
    `__bases__[0]`）；本选择留给 M5 design round 决定，M4 不预判。
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # 仅校验本类自身声明的 STRUCTURED_KWARGS（不走 MRO，对齐 §5.3
        # `_discover_structured_kwargs` 的 `cls.__dict__.get(...)` 语义）。
        declared = cls.__dict__.get("STRUCTURED_KWARGS")

        # C-rev10 / Corr-2 / 决策 #104：subclass redeclaration enforcement。
        # 若任一基类（不含本 mixin 自身）已声明 STRUCTURED_KWARGS,
        # 则当前 cls MUST 在自身 __dict__ 中显式 redeclare；否则 AST 契约
        # 扫描会因 cls.__dict__.get(...) 返回 None 而把本子类排除出
        # raise-point 集合，silent gap。
        if declared is None:
            for base in cls.__mro__[1:]:
                if base is EvolveError:
                    continue
                if "STRUCTURED_KWARGS" in base.__dict__:
                    raise TypeError(
                        f"{cls.__name__}: parent {base.__name__} declares "
                        f"STRUCTURED_KWARGS={base.__dict__['STRUCTURED_KWARGS']!r}; "
                        f"subclasses MUST redeclare their own STRUCTURED_KWARGS "
                        f"(no-MRO inheritance; 决策 #95 / #104)."
                    )
            return
        if not isinstance(declared, frozenset):
            raise TypeError(
                f"{cls.__name__}.STRUCTURED_KWARGS must be frozenset[str], "
                f"got {type(declared).__name__}"
            )
        # 解析 __init__ keyword-only 参数集合（不含 self / *args / **kwargs / 位置参数）。
        sig = inspect.signature(cls.__init__)
        kw_only = {
            name
            for name, p in sig.parameters.items()
            if p.kind is inspect.Parameter.KEYWORD_ONLY
        }
        # C-rev11 / RED-1 / 决策 #107：subset semantics — STRUCTURED_KWARGS
        # 必须是 ctor kw-only 参数集合的子集（必填字段必须声明），但 ctor 允许
        # 含额外 kw-only 参数作为可选诊断字段（如 `ManifestPrivacyViolation` 的
        # `offending_path` / `offending_fields`）。
        if not set(declared).issubset(kw_only):
            missing = set(declared) - kw_only
            raise TypeError(
                f"{cls.__name__}: STRUCTURED_KWARGS={set(declared)!r} contains "
                f"members {missing!r} not present in __init__ keyword-only "
                f"params={kw_only!r}; STRUCTURED_KWARGS MUST be a subset of "
                f"kw-only params (declared kwargs are required; additional "
                f"kw-only params are permitted as optional diagnostic fields) "
                f"(W3 / C-rev9 / 决策 #99 + C-rev11 / RED-1 / 决策 #107 amend)."
            )


class EvolveExtraNotInstalled(EvolveError, ImportError):
    """未装 `pip install nanobot[evolve]`，DSPy / GEPA 不可用。"""
    INSTALL_HINT = "pip install nanobot[evolve]"

class BaselineMismatch(EvolveError, ValueError):
    """Candidate.parent_baseline_hash != Baseline.content_hash
    （§3.2 配对不变量 #1）。M4 映射到 CLI exit 7（harness invariant 违反）。"""

class ApplyTerminalError(EvolveError, ValueError):
    """`OfflineHarness.apply()` 检测到 `manifest.final_status != 'promoted_to_pr'`
    （决策 #88 / #90，YELLOW-Y5 C-rev4）。

    `ApplyTerminalError` **是** `ValueError` 的具体子类（不是"wraps"或"被包装"
    任何东西）。该子类关系本身让 `except ValueError:` 子句**会**捕获本异常,
    这就是 handler-order 契约存在的原因 —— 若 CLI dispatch 把 `except ValueError:`
    写在 `except ApplyTerminalError:` 之前，本异常会被静默归到 exit 2 而非 exit 8。
    `pydantic.ValidationError` 同为 `ValueError` 子类；CLI 已通过 wrap 转 `ConfigError`
    路径处理（详见本节末尾「异常 → CLI 退出码映射」表 + `pydantic.ValidationError`
    包装详解段；COH-002 / Z8 — 正式 anchor 替代旧 "§5.3 dispatch 表" 简写）。

    构造参数:
      message:       人读说明
      final_status:  manifest 实际的 final_status 值（如 'rejected_by_gate' /
                     'no_improvement' / 'harness_error'），供上层日志 / CI
                     metric 分流
      manifest_path: 触发判定的 manifest.json 绝对路径

    **生产侧 registry（C-rev6 / 决策 #95）**：
      - `STRUCTURED_KWARGS`：本异常构造期必填的关键字参数集合（由
        `tests/evolve/test_decoupling.py` introspection 读取，无须测试侧
        硬编码 dict）。
      - `MUST_PRECEDE`：CLI dispatch try/except 中**必须**在以下任一 `except <X>:`
        子句之**前**捕获本异常，否则触发隐式 isinstance 屏蔽（机械化执行 test
        见 §5.3 末尾 `test_cli_handler_order_in_evolve_dispatch` 契约段 + 异常 →
        CLI 退出码映射表；COH-002 / Z8 — 正式 anchor 替代旧 "§5.3 dispatch-order
        contract" 简写）。
    """
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"final_status", "manifest_path"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"ValueError", "ConfigError"})

    def __init__(self, message: str, *, final_status: str, manifest_path: "Path") -> None:
        super().__init__(message)
        self.final_status = final_status
        self.manifest_path = manifest_path

# 注：M4 **不**引入 `GateRejected` 异常类。M4 的设计是「gate 业务判定走 RunManifest
# 返回值」（`final_status == 'rejected_by_gate'`），不抛异常。`strict_gates=True`
# 扩展点（让 `run()` 在 gate fail 时抛 `GateRejected`）**延后到 M5**：M5 在引入
# `gate 4 / gate 5` 时同步加该异常类，避免 M4 留死代码。

class JudgeError(EvolveError, RuntimeError):
    """Judge pool 调用失败（provider error，3 次重试后仍失败 → 详见 §5.1
    retry contract）或 `JudgePool.require_consensus=True` 时 consensus split。

    **生产侧 registry（W2 / C-rev8 / 决策 #95 amend）**：
      `MUST_PRECEDE` 声明本异常**必须**在 `except RuntimeError:` 之前被捕获，
      否则 CLI dispatch 中宽 `except RuntimeError:` 会静默截胡 → 落到 exit 1
      catch-all 而非 exit 5（provider 抖动可重试）。详见 §5.3 末尾 "RuntimeError-tree
      MUST_PRECEDE 通用规则" + W2 闭合段。
    """
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

class ManifestPrivacyViolation(EvolveError, RuntimeError):
    """Manifest 或 self-eval 写入触发 §3.7.1 「无 PII」不变量 / §5.2 .gitignore
    前置失败时抛出；阻断 PR 生成（§4.4 / §8）或拒绝写盘（§5.2）。

    构造参数（YELLOW-12 / C-rev-7）：
      message: 人读说明
      violated_invariant: 命中的不变量锚点，如 "§3.7.1 no PII" /
                          "§5.2 .gitignore precondition"
      offending_path: 触发违例的路径（manifest.json / .gitignore），可为 None
      offending_fields: manifest 字段名列表 / .gitignore 缺失的 pattern 列表

    **生产侧 registry（C-rev6 / 决策 #95）**：
      `STRUCTURED_KWARGS` 声明本异常的必填关键字（`violated_invariant`）；
      `offending_path` / `offending_fields` 是可选附加诊断字段，不进 registry。

    **生产侧 registry（W2 / C-rev8 / 决策 #95 amend）**：
      `MUST_PRECEDE` 声明本异常**必须**在 `except RuntimeError:` 之前被捕获，
      否则宽 catch 会让隐私违例（exit 4，永不重试）被静默归到 exit 1，CI 失去
      privacy-violation 分流信号。详见 §5.3 末尾 "RuntimeError-tree MUST_PRECEDE
      通用规则"。
    """
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset({"violated_invariant"})
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

    def __init__(
        self,
        message: str,
        *,
        violated_invariant: str,
        offending_path: "Path | None" = None,
        offending_fields: "list[str] | None" = None,
    ) -> None:
        super().__init__(message)
        self.violated_invariant = violated_invariant
        self.offending_path = offending_path
        self.offending_fields = offending_fields or []

class EvolveEnvironmentError(EvolveError, RuntimeError):
    """CLI 前置环境失败（C-rev6 / 决策 #96；C-rev7 / 决策 #100 重命名自
    `EvolveCliError` + drop `exit_code` 字段 / Z5）。专用于 `--force` 的
    pre-step 0a parent-dir access 与 pre-step 0b stale-debris sweep 等
    "环境不就绪"错误，与 `ConfigError`（参数错误）和裸 `OSError`（运行时
    fs 错）区分。

    **Layering 决策（决策 #100 Option A / Z5）**：本类位于 `nanobot/evolve/exceptions.py`
    library 层；CLI 退出码归属由 §4.6 dispatch 表 + §5.3 异常→exit code 映射
    表是 SoT 决定（本类 → exit 2）。本类**不**携带 `exit_code` 字段 —— 类
    身份本身即是 exit-code 的稳定 anchor，外部 CI 通过
    `isinstance(exc, EvolveEnvironmentError)` 捕获并按表查 exit code（与
    `ConfigError` / `ApplyTerminalError` / `JudgeError` 一致的 layering）。

    构造参数:
      message:    人读说明

    **生产侧 registry（W2 / C-rev8 / 决策 #95 amend）**：
      `MUST_PRECEDE` 声明本异常**必须**在 `except RuntimeError:` 之前被捕获，
      否则环境前置失败（exit 2，用户应修复后重试）会被宽 catch 静默归到 exit 1
      catch-all，让 `apply --force` 的 0a/0b/0c pre-step 失败丢失专属退出码语义。
      详见 §5.3 末尾 "RuntimeError-tree MUST_PRECEDE 通用规则"。
    """
    STRUCTURED_KWARGS: ClassVar[frozenset[str]] = frozenset()
    MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"RuntimeError"})

class ConfigError(EvolveError, ValueError):
    """`EvolveDefaults` / `RubricWeights` / `JudgePool` / CLI 参数互斥违反等；CLI exit 2。

    raise 触发点（M4 ships）：
      - `EvolveDefaults._odd_pool_size` field_validator
      - `RubricWeights._sum_to_one` model_validator（canonical 求和校验位置；
        决策 #84 删除了 `EvolveDefaults._weights_sum_to_one`）
      - `JudgePool` 构造失败：
          * malformed CLI `--judge-pool` payload（JSON 解析失败 / 缺字段）
          * `min_quorum > len(judges)`（`_validate_quorum_bounds`）
          * `min_quorum < 1`（Pydantic `Field(ge=1)` 字段层拒绝）
          * 嵌套 `RubricWeights._sum_to_one` 失败（CLI `--judge-pool` 覆盖
            weights 时）
      - `OfflineHarness._resolve_run_id` 前缀长度 < 4 / 前缀歧义
      - `OfflineHarness.run()` 入口处 `tiers` / `iterations` / `judge_pool` 检查
      - `OfflineHarness.__init__` 的 `workspace.is_dir()` 失败（W6 / C-rev8 /
        决策 #100 amend：ctor 参数校验失败统一走 `ConfigError` → exit 2，
        与 `EvolveDefaults` ctor 校验同族；原签名声明的裸 `ValueError` 会落
        exit 1 catch-all，破坏 dispatch SoT）

    **`pydantic.ValidationError` 包装规则**：CLI handler 在 config / CLI 参数
    解析期捕获**任何** `pydantic.ValidationError`，re-raise 为
    `ConfigError(message=str(ve), ...)` 以统一 CLI exit 2 语义。这覆盖
    `RubricWeights._sum_to_one` / `JudgePool._validate_quorum_bounds` /
    `JudgePool.min_quorum` 字段层拒绝等所有嵌套场景。
    """
```

所有 `raise ManifestPrivacyViolation` 调用点（`pr_writer.py` 在 §3.7.1 manifest 扫描 / `record_self_eval` 在 §5.2 precondition）**必须**使用结构化构造函数，最少填 `violated_invariant`，按场景填 `offending_path` / `offending_fields`。CLI handler 捕获后将这些字段写入 stderr（机器可读 + 人读），便于 CI 分流。

**M4 期程序化消费者（YELLOW-Y4）**：结构化字段的存在通过下列 M4-plan-期落地的测试用例机械化锁定，避免「字段存在但无人读」的 YAGNI 漂移：

```python
# tests/evolve/test_apply_contract.py::test_pr_writer_no_pii
def test_pr_writer_no_pii(manifest_with_pii):
    with pytest.raises(ManifestPrivacyViolation) as exc_info:
        pr_writer(manifest_with_pii)
    assert exc_info.value.violated_invariant == "§3.7.1 no PII"
    assert "raw_prompt" in exc_info.value.offending_fields
```

```python
# tests/evolve/test_record_self_eval.py::test_precondition_missing_gitignore
def test_precondition_missing_gitignore(tmp_path):
    # 故意不创建 .gitignore
    config.evolve.self_eval_enabled = True
    with pytest.raises(ManifestPrivacyViolation) as exc_info:
        record_self_eval(
            task_id="t1", input={}, output={}, verdict={"passed": True},
            workspace=tmp_path,
        )
    assert exc_info.value.violated_invariant == "§5.2 .gitignore precondition"
    assert exc_info.value.offending_path == tmp_path / ".gitignore"
```

```python
# tests/evolve/test_record_self_eval.py::test_precondition_incomplete_gitignore
def test_precondition_incomplete_gitignore(tmp_path):
    (tmp_path / ".gitignore").write_text("# unrelated\nnode_modules/\n")
    config.evolve.self_eval_enabled = True
    with pytest.raises(ManifestPrivacyViolation) as exc_info:
        record_self_eval(
            task_id="t1", input={}, output={}, verdict={"passed": True},
            workspace=tmp_path,
        )
    assert exc_info.value.violated_invariant == "§5.2 .gitignore precondition"
    assert "evals/self/" in exc_info.value.offending_fields
```

**结构化-kwargs + handler-order 异常 contract tests**（`tests/evolve/test_decoupling.py` 的 step 7–9，扩展 §5.4.2 步骤集合；C-rev3 引入；**C-rev6 / 决策 #95 升级为生产侧 introspection registry**，独立的 `test_cli_handler_order.py` 文件并入 `test_decoupling.py`）。

**生产侧 registry 设计（C-rev6 / 决策 #95 / 闭合 Y-arch-1 + Y-arch-2 + Y-scope-2）**：

`STRUCTURED_KWARGS` 与 `MUST_PRECEDE` 不再以测试侧硬编码 dict 形式存在；它们是每个异常类自身的 `ClassVar[frozenset[str]]` 属性（详见 §5.3 异常定义）。测试通过 `inspect.getmembers(nanobot.evolve.exceptions, inspect.isclass)` 在导入时自动发现所有声明这两个属性的异常类。M5 引入新结构化异常（如 `GateRejected` / `JudgeQuorumFailure`），只需在异常类上声明 `STRUCTURED_KWARGS` / `MUST_PRECEDE`，**无须**改测试 —— registry 由生产侧 SoT 驱动。

**Test contract（Z9 / Y-prod-1 — 实现见 `tests/evolve/test_decoupling.py`，spec 仅约束契约 + helper 签名）**：

测试模块（canonical 实现路径 `tests/evolve/test_decoupling.py`）由以下 5 个独立断言构成；spec 仅锁定每条契约的语义与 helper API 签名，verbatim test bodies / fixtures / assert 语句以代码 SoT 为准（避免 spec 与 test code 双向漂移）：

1. `test_structured_exc_kwargs_present` —— 扫描 `nanobot/` + `tests/`，对每个 `raise X(...)` / `raise mod.X(...)`（不含 self/cls 间接），如 `X.__dict__` 含 `STRUCTURED_KWARGS: frozenset[str]`，则 `**kwargs` spread 不允许，且 missing kwargs ⊆ 空集。
2. `test_cli_handler_order_in_evolve_dispatch` —— 扫描 `nanobot/cli/commands.py` 内所有 `try` 块，按 `MUST_PRECEDE` 关系断言 `except <specific>` 出现 index 严格小于 `except <ancestor>` 出现 index。
3. `test_no_bare_except_in_evolve_cli` —— 拒绝 `nanobot/evolve/cli/*.py`（fallback `nanobot/cli/`）下任何 `except:` / `except BaseException:` / 含 `BaseException` 的 tuple handler。
4. `test_no_self_raises_in_evolve` —— 拒绝 `nanobot/evolve/**/*.py` 下任何 `raise self.X(...)` / `raise cls.X(...)`。
5. `test_must_precede_acyclic` —— 对 `_discover_must_precede()` 返回的图做 DFS 环检测，循环即 fail 并打印 cycle path。
6. `test_must_precede_acyclic_detects_cycle` —— C-rev10 / Corr-7 sibling positive-coverage：用 deliberately cyclic `_FakeCyclicException` fixture 强制走 cycle-detector fail path，给 DFS 实现自身正面覆盖（避免 `test_must_precede_acyclic` 在 M4 阶段结构上不可能 fail 时把 untested DFS 留到 M5 才暴露 bug）。详见点 7 末尾 fixture 草稿。
7. `test_evolve_error_first_in_mro` —— C-rev10 / Arch-2：遍历 `nanobot.evolve.exceptions` 模块所有 mix in `EvolveError` 的具体异常类，断言 `cls.__bases__[0].__name__ == 'EvolveError'`，防止 silent MRO drift。
8. `test_init_subclass_accepts_optional_diagnostic_kwargs` —— C-rev11 / RED-1 / 决策 #107：在测试模块内动态构造两类 fixture 子类，覆盖 subset 语义两端：(a) 一个 `STRUCTURED_KWARGS = frozenset({"required"})` 的子类，其 `__init__(*, required, optional)` 含一个超出 frozenset 的 kw-only 参数 → MUST 通过 import（subset 满足，不 raise）；(b) 一个 `STRUCTURED_KWARGS = frozenset({"required", "missing"})` 的子类，其 `__init__(*, required)` 缺一个 frozenset 成员 → MUST 在子类定义期 `TypeError`（subset 违反）。锁定 RED-1 的设计意图（`ManifestPrivacyViolation` 必填一项 + 可选两项）不被未来 contributor 误退回到 C-rev9 草拟的"严格等于"语义。

**Helper API 签名（spec-locked，实现住 test module）**：

```python
# tests/evolve/test_decoupling.py — API surface only

import ast
import inspect
from pathlib import Path
from typing import ClassVar, Iterator

import nanobot.evolve.exceptions as _evolve_exc

class _ScannerConfig:
    """AST scan 排除目录集合；frozenset ClassVar 让 M5 contributor 可发现并扩展。
    保留在 spec 是因为此集合是测试契约的一部分（决定扫描覆盖范围）。"""
    EXCLUDED_DIRS: ClassVar[frozenset[str]] = frozenset({
        ".venv", "venv",
        "__pycache__",
        "node_modules",
        "dist", "build",
        ".tox", ".nox",
        ".mypy_cache", ".ruff_cache", ".pytest_cache",
    })


def _iter_py_files(root: Path) -> Iterator[Path]:
    """Walk root.rglob('*.py') skipping EXCLUDED_DIRS at any depth."""


def _discover_structured_kwargs() -> dict[str, frozenset[str]]:
    """Build {cls_name: STRUCTURED_KWARGS frozenset} from production exception
    module via introspection. **MUST use `cls.__dict__.get(...)` (NOT
    `getattr(cls, ...)`)** — ClassVar registries are NOT inherited via MRO
    (Z2 / Y-corr-rev6-4 / 决策 #99): a subclass with a different `__init__`
    signature would silently inherit a parent frozenset that doesn't match its
    own ctor kwargs, defeating the AST contract. Each exception subclass MUST
    redeclare its own frozenset."""


def _discover_must_precede() -> dict[str, frozenset[str]]:
    """Build {cls_name: MUST_PRECEDE frozenset} via introspection. Same
    `cls.__dict__.get(...)` semantics as `_discover_structured_kwargs` —
    no MRO inheritance allowed."""


def _resolve_raised_class_name(call: ast.Call) -> str | None:
    """Extract class name from `raise <expr>(...)` AST Call. Handles
    `ast.Name` (`raise Foo(...)`) and `ast.Attribute` (`raise mod.Foo(...)`).
    Returns None for `self.X(...)` / `cls.X(...)` forms (Z3 / Y-corr-rev6-5):
    AST cannot resolve runtime attribute routing — companion test
    `test_no_self_raises_in_evolve` rejects such forms outright."""


def _walk_raise_sites(tree: ast.AST) -> Iterator[ast.Raise]:
    """Yield every `raise X(...)` (ast.Raise with .exc being ast.Call)."""


def _enclosing_try_handlers(tree: ast.AST) -> Iterator[ast.Try]:
    """Yield every ast.Try node (for handler-order scan)."""


# ─── Test functions (canonical bodies live in tests/evolve/test_decoupling.py) ───

def test_structured_exc_kwargs_present(): ...
# Contract: walks _iter_py_files(REPO/"nanobot") + REPO/"tests"; for every
# raise site where the resolved class name has a STRUCTURED_KWARGS frozenset,
# assert `**kwargs` spread is absent AND required kwargs ⊆ actual kwargs.
# Asserts registry non-empty to catch silent introspection failure.

def test_cli_handler_order_in_evolve_dispatch(): ...
# Contract: walks every ast.Try in nanobot/cli/commands.py; for each MUST_PRECEDE
# entry (specific → {ancestors}), asserts specific's handler index < every present
# ancestor's index. Asserts rules non-empty (silent-failure guard).

def test_no_bare_except_in_evolve_cli(): ...
# Contract (Y-corr-4 / Z3 / Y-corr-rev6-6): in nanobot/evolve/cli/*.py
# (fallback nanobot/cli/), reject any ExceptHandler with type=None,
# type=ast.Name(id="BaseException"), or type=ast.Tuple containing
# Name(id="BaseException"). All three swallow KeyboardInterrupt/SystemExit
# equivalently — same exit-code-stratification harm.

def test_no_self_raises_in_evolve(): ...
# Contract (Z3 / Y-corr-rev6-5 / **W3 / C-rev9 transitive extension**): walks
# nanobot/evolve/**/*.py raise sites; reject any `raise <expr>(...)` whose `.exc.func`,
# when peeled through any chain of `ast.Attribute` nodes, ultimately roots at
# `ast.Name(id in {"self","cls"})`. C-rev7 only matched the **direct**
# `Attribute(value=Name(id="self"))` case (`raise self.Foo(...)`) and missed
# nested forms `raise self.module.ExcClass(...)` / `raise self.a.b.c.Foo(...)`
# where the Name(id="self") sits at the **innermost** value, not at depth 1.
# Reject helper: `_root_name_is_self_or_cls(attr_or_name)` recursively peels
# `ast.Attribute` until reaching `ast.Name` (or non-Name terminal). Companion
# runtime backstop: `EvolveError.__init_subclass__` (defense in depth — catches
# AST-unresolvable local-alias forms `cls_ref = self.exc_cls; raise cls_ref(...)`
# at import time).

def test_must_precede_acyclic_detects_cycle(): ...
# Contract (C-rev10 / Corr-7 / 决策 #99 amend): positive coverage for cycle
# detector. Inject `_FakeCyclicException` fixture (two fake exception classes
# whose MUST_PRECEDE reference each other), call the same DFS helper used by
# `test_must_precede_acyclic`, assert AssertionError raised. Without this the
# cycle detector itself is untested logic in M4 (real graph cannot cycle yet),
# so any latent off-by-one / missed-self-loop / missing visited-mark bug only
# surfaces in M5+ when the first evolve-internal MUST_PRECEDE edge lands.

def test_evolve_error_first_in_mro(): ...
# Contract (C-rev10 / Arch-2): iterate concrete exception classes in
# nanobot.evolve.exceptions that mix in EvolveError; assert
# `cls.__bases__[0].__name__ == "EvolveError"`. Prevents silent MRO drift
# such as `class Foo(RuntimeError, EvolveError):` (still passes isinstance
# checks but reorders super().__init__ resolution / breaks cooperative MRO
# expectations).
# M5 forward-compat (C-rev11 / YELLOW-6): subclasses of M4 structured
# exceptions (e.g. M5's `class GateRejected(ApplyTerminalError):`) MUST
# adopt explicit dual-base form `class GateRejected(EvolveError,
# ApplyTerminalError):` to preserve `__bases__[0] is EvolveError`;
# cooperative `super().__init__` chains exercised in M5's
# `test_gaterejected_init_kwargs_propagate` (or equivalent). Alternative
# relaxation `EvolveError in cls.__mro__[: cls.__mro__.index(BaseException)]`
# deferred to M5 design.

def test_init_subclass_accepts_optional_diagnostic_kwargs(): ...
# Contract (C-rev11 / RED-1 / 决策 #107): subset-semantics enforcement for
# STRUCTURED_KWARGS-vs-ctor-kw-only check. Two fixture cases:
#   (a) Positive: dynamically declare
#       `class _OkSubset(EvolveError, ValueError):
#            STRUCTURED_KWARGS = frozenset({"required"})
#            def __init__(self, msg, *, required, optional=None): ...`
#       — MUST NOT raise (subset {required} ⊆ {required, optional}); ctor extra
#       kw-only params are permitted as optional diagnostic fields per
#       `ManifestPrivacyViolation`-pattern intent.
#   (b) Negative: dynamically declare
#       `class _BadMissing(EvolveError, ValueError):
#            STRUCTURED_KWARGS = frozenset({"required", "missing"})
#            def __init__(self, msg, *, required): ...`
#       — MUST raise TypeError at class-creation time (frozenset member
#       "missing" not in ctor kw-only params); the TypeError MUST cite the
#       offending member name to aid debugging.
# Locks RED-1 closure mechanically; prevents silent regression to the
# C-rev9 draft's strict-equality semantics that would have broken
# `ManifestPrivacyViolation` import.

def test_must_precede_acyclic(): ...
# Contract (Z2 / Y-corr-rev6-3 / 决策 #99; W10 / C-rev9 framing): DFS
# cycle-check on _discover_must_precede() graph at module-load time. Cycle →
# AssertionError naming the offending path. Catches the impossibility-to-satisfy
# condition independently of CLI dispatch site (which only surfaces it when
# both offending classes appear in same try-block). NOTE (W10 / C-rev9): in
# M4 the registry holds zero evolve-internal multi-node edges (all
# `MUST_PRECEDE` targets are stdlib base types like `ValueError` /
# `RuntimeError`); cycle is structurally impossible. Retained as a zero-cost
# forward-looking guard for M5+ where `GateRejected` / `JudgeQuorumFailure` /
# etc. will introduce evolve-internal edges and make cycles a real risk. Cost
# ~12 LoC + sub-millisecond DFS at module load.
```

实现要点：

1. **生产侧 SoT（C-rev6 / 决策 #95）**：`STRUCTURED_KWARGS` 与 `MUST_PRECEDE` 是异常类自身的 `ClassVar[frozenset[str]]`。测试 introspection 自动发现，**无须**测试侧硬编码 dict。M5 增异常 → 只在异常类上声明属性即可。**ClassVar 不经 MRO 继承（Z2 / Y-corr-rev6-4 / 决策 #99）**：discovery helper 使用 `cls.__dict__.get(...)`（而非 `getattr(cls, ...)`）—— 每个异常子类**必须**重新声明自己的 `STRUCTURED_KWARGS` / `MUST_PRECEDE` frozenset。若依赖 MRO 继承，子类与父类 `__init__` 签名不一致时会静默漂移（父类的 frozenset 不匹配子类自己的 ctor kwargs），破坏 AST 契约。
2. **`MUST_PRECEDE_RULES` 命名（Y-arch-2）**：旧 `HANDLER_ORDER_RULES` 命名误导（暗示"规则集"）；新命名 `MUST_PRECEDE_RULES`（dict，由 `_discover_must_precede()` 返回，测试中按惯例命名 `rules` 局部变量；COH-004 / Z8 澄清）/ `MUST_PRECEDE`（ClassVar）反映实际语义"X 必须在 Y 之前被捕获"。
3. **Attribute-form raises（Y-corr-1）**：`_resolve_raised_class_name` 同时处理 `ast.Name`（`raise Foo(...)`）与 `ast.Attribute`（`raise pkg.mod.Foo(...)`）。C-rev5 scanner 仅处理前者，会漏掉合法但少见的全限定形态。
4. **EXCLUDED_DIRS（Y-corr-5）**：扫描跳过 `.venv` / `__pycache__` / `node_modules` / `dist` / `build` / `.tox` / `.nox` / `.mypy_cache` / `.ruff_cache` / `.pytest_cache`。集合作为 `ClassVar[frozenset[str]]` 暴露在 `_ScannerConfig` 上，扩展时可发现。
5. **Bare-except 禁令（Y-corr-4）+ BaseException 等价禁令（Z3 / Y-corr-rev6-6）**：独立 test 用 `ast.ExceptHandler` walk 拒绝 `nanobot/evolve/cli/*.py`（或 fallback `nanobot/cli/`）下的 `except:` 裸捕获，**以及** `except BaseException:` / 含 `BaseException` 的 tuple —— 三种形式都吞 `KeyboardInterrupt` / `SystemExit`，对 exit-code 分流的破坏度等价，故统一同条 test 处理。
6. **`raise self.X(...)` / `raise cls.X(...)` 禁令（Z3 / Y-corr-rev6-5；W3 / C-rev9 transitive 扩展 + 运行时 backstop）**：独立 test `test_no_self_raises_in_evolve` 拒绝 evolve 代码中通过 `self` / `cls` 属性间接 raise 的形态 —— AST 无法解析运行时属性路由的类身份，使 `STRUCTURED_KWARGS` AST 契约被绕过。强制要求 `raise X(...)` 或 `raise mod.X(...)` 两种可静态解析的形态，与 bare-except / BaseException 禁令同源（都为保护 exit-code 分层契约）。**Defense in depth（W3 / C-rev9 / 决策 #99 amend）**：(a) AST scan 升级为**递归剥皮** `ast.Attribute` 链，命中嵌套形态 `raise self.module.ExcClass(...)` / `raise self.a.b.c.Foo(...)`（C-rev7 仅匹配 depth-1 `Attribute(value=Name(id="self"))`，漏放任意深度 attribute chain）。`_root_name_is_self_or_cls(node)` 递归向内 peel `value` 直到 `ast.Name`，根 id 命中 `{"self","cls"}` 即拒。(b) 运行时 backstop：基类 `EvolveError.__init_subclass__`（见 §5.3 源码头部）在导入期对每个声明 `STRUCTURED_KWARGS` 的子类校验 `STRUCTURED_KWARGS` **子集于** `__init__` keyword-only 参数集合（必填字段必须声明；ctor 允许含额外 kw-only 参数作为可选诊断字段，C-rev11 / RED-1 / 决策 #107 把原 C-rev9 草拟的"严格等于"语义放宽，闭合 `ManifestPrivacyViolation` 设计冲突），不一致即 `TypeError` 阻断导入 —— 截获 AST 不可解析的局部别名形态（如 `cls_ref = self.exc_cls; raise cls_ref(...)`）。AST 静态 + 运行时双层守卫共同闭合 declaration ↔ ctor signature 漂移窗口。**(c) Subclass redeclaration enforcement（C-rev10 / Corr-2 / 决策 #104 amend）**：`__init_subclass__` 同时对继承层强制 redeclaration —— 若任一基类（`cls.__mro__[1:]` 中、不含 `EvolveError` mixin 自身）已声明 `STRUCTURED_KWARGS`，则当前子类的 `cls.__dict__.get("STRUCTURED_KWARGS")` MUST 显式存在且非 `None`；缺失即 import-time `TypeError`。这与 `_discover_structured_kwargs` 的 `cls.__dict__.get(...)`（不沿 MRO 继承）语义对齐 —— 子类若依赖 MRO 继承父类 frozenset，会被 discovery 排除出 raise-point 集合，silent gap；本规则把 "MUST redeclare" 从隐性约定升级为 import-time fail-loud 契约。
7. **MUST_PRECEDE 无环（Z2 / Y-corr-rev6-3 / 决策 #99；W10 / C-rev9 forward-looking framing；C-rev10 / Corr-7 fixture coverage）**：独立 test `test_must_precede_acyclic` 在模块加载期对 `_discover_must_precede()` 返回的图做 DFS / 拓扑序检查；环（如 `A.MUST_PRECEDE={"B"}` + `B.MUST_PRECEDE={"A"}`）即逻辑上不可满足，无须等 CLI dispatch 测试触发才暴露 —— 提前在 unit 层 fail-loud 并附 cycle path。

   **C-rev10 / Corr-7 — Companion test `test_must_precede_acyclic_detects_cycle`**：仅
   `test_must_precede_acyclic`（针对生产 registry）在 M4 阶段结构上不可能 fail（详见
   下方 forward-looking 段），其 DFS 实现本身**也未被任何 fixture 走过**，是 untested
   logic。M4 plan 期 MUST 同时落地一条 sibling positive-coverage test，用 deliberately
   cyclic 的 `_FakeCyclicException` fixture 强制走 cycle-detector 的 fail path：
   ```python
   def test_must_precede_acyclic_detects_cycle():
       """Positive coverage for the cycle detector (Corr-7 / 决策 #99 amend)."""
       class _FakeCyclicA:
           MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"_FakeCyclicB"})
       class _FakeCyclicB:
           MUST_PRECEDE: ClassVar[frozenset[str]] = frozenset({"_FakeCyclicA"})
       fake_graph = {"_FakeCyclicA": frozenset({"_FakeCyclicB"}),
                     "_FakeCyclicB": frozenset({"_FakeCyclicA"})}
       with pytest.raises(AssertionError, match=r"cycle"):
           _check_acyclic(fake_graph)  # 同一 DFS helper, public-for-test API
   ```
   Spec 强制要求：cycle 检测器 SoT helper（如 `_check_acyclic(graph)`）MUST 是可独立
   调用的纯函数，让生产侧 introspection（无环 → pass）与 fixture 注入（含环 → fail）
   两条 codepath 都被 CI 走过。否则 W10 forward-looking 留置（保留 cycle-test 防 M5
   引入 evolve-internal edges）将基于一段未被任何 fixture 验证过的 DFS 实现 —— 当
   M5 真正引入第一条多节点 edge 时，cycle-detector 自身的潜在 bug（off-by-one /
   错过 self-loop / 漏 visited 标记）才会被发现，错过本来该在 M4 就关闭的窗口。

   **Forward-looking scope 框架（W10 / C-rev9 / 决策 #99 amend）**：当前 M4 `MUST_PRECEDE` registry 中，C-rev7 仅 `ApplyTerminalError.MUST_PRECEDE = {"ValueError","ConfigError"}` 一个 evolve-internal 节点（`ValueError` / `ConfigError` 是被指向的目标但本身不持有 `MUST_PRECEDE`）；C-rev8 W2 之后 `EvolveEnvironmentError` / `JudgeError` / `ManifestPrivacyViolation` 也各自声明 `MUST_PRECEDE = {"RuntimeError"}`，但目标全是 stdlib base type，**仍无任何 evolve-internal 多节点环可能**。本 test 在 M4 阶段**结构上不可能 fail**，按 YAGNI 严格解读可删；**故意保留**作为 M5+ 的零成本前瞻护栏 —— M5 计划引入 `GateRejected` / `JudgeQuorumFailure` 等新结构化异常，届时 evolve-internal `MUST_PRECEDE` 图将出现多节点关系（如 `JudgeQuorumFailure.MUST_PRECEDE ⊇ {"JudgeError"}`），环成为真实可能。成本：~12 LoC + 模块加载期一次 DFS（< 1ms）；收益：M5 增异常时漏环立刻被 CI fail-loud。这是显式的 forward-looking 留置，不是 dead code。
7b. **RuntimeError-tree MUST_PRECEDE 通用规则（W2 / C-rev8 / 决策 #95 amend）**：任何继承自 stdlib base type（`RuntimeError` / `ValueError` / `OSError` / ...）的 evolve 异常类，若其 base type **有可能**出现在同一 CLI try/except 链中，**必须**在 `MUST_PRECEDE` 中声明该 base type 名。M4 ships 三类此模式：`EvolveEnvironmentError` / `JudgeError` / `ManifestPrivacyViolation` 均 `MUST_PRECEDE ⊇ {"RuntimeError"}`；`ApplyTerminalError` 已 `MUST_PRECEDE ⊇ {"ValueError"}`。规则适用范围：本规则**不**要求声明 evolve sibling 之间的优先级（如 `EvolveEnvironmentError` vs `JudgeError`），因为它们各自有独立 exit code、`isinstance` 检查互斥（同一 try/except 中以何种顺序排列不影响分流）；仅当 sibling 间有真实的"X 是 Y 子类、子类必须先于基类"关系时才需声明 inter-sibling `MUST_PRECEDE`。M5 引入新继承自 stdlib base 的 evolve 异常时，按本规则添加 `MUST_PRECEDE`，由 `test_cli_handler_order_in_evolve_dispatch` 与 `test_must_precede_acyclic` 自动机械化执行。
8. **覆盖范围**：structured-kwargs scan 覆盖 `nanobot/` + `tests/`；handler-order scan 仅 `nanobot/cli/commands.py`；bare-except / BaseException / self-raise scan 限 evolve（CLI 目录 + `nanobot/evolve/**`），避免无关 try/except 噪声。
9. **合并旧 `test_cli_handler_order.py`（Y-scope-2 / C-rev6）**：~6 个 assertion 不值新文件；并入 `test_decoupling.py` 让"decoupling/dispatch 契约"集中维护。
10. **registry 非空断言**：`assert registry, ...` / `assert rules, ...` 防止 introspection 静默返回空 dict（如生产侧 import 失败 / 属性命名漂移）让所有断言被跳过。

历史：C-rev3 窄扫描（仅 `ManifestPrivacyViolation`）→ C-rev5 测试侧 registry dict generalize → C-rev6 生产侧 introspection。每次升级都让"漏注册即失保护"的窗口更窄：测试侧 dict 时漏改测试即失保护；生产侧 ClassVar 时漏在异常类上声明即失保护（更接近 declaration-site，与 PR diff 同位）。

异常 → CLI 退出码映射（与 §4.6 一一对应）：

| 异常 | CLI exit code | 子命令 | 重试建议 |
|---|---|---|---|
| `EvolveExtraNotInstalled` | 3 | `run` | 不重试，需 `pip install nanobot[evolve]` |
| `ConfigError` | 2 | 任意 | 不重试，需修改 invocation / config |
| `pydantic.ValidationError`（config / `JudgePool` / `RubricWeights` 构造期，被 CLI handler wrap 为 `ConfigError`） | 2 | 任意 | 不重试，需修改 invocation / config（YELLOW-Y8） |
| `JudgeError` | **5（唯一）** | `run` | **可重试**（指数退避；详见 §5.1 retry contract） |
| `FileNotFoundError`（run-id 前缀无匹配 / manifest.json 缺失） | 6 | `report` / `apply` | 不重试，run 真的不存在 |
| `FileExistsError`（`apply` 时 `--output-dir` 已存在且 `--force=False`） | **6（决策 #88，原 8 → 6）** | `apply` | 不重试，传 `--force` 或换 `--output-dir` |
| `ManifestPrivacyViolation` | 4 | `run` / `apply` / `record_self_eval` | 不重试，需修复 manifest 生成代码或 bootstrap .gitignore |
| `BaselineMismatch` | 7 | `run` | **绝不重试**，harness invariant 破裂，报 bug |
| `ApplyTerminalError`（`apply` 时 `manifest.final_status != promoted_to_pr`；决策 #90 YELLOW-Y5） | **8（决策 #88：apply 业务终态，narrowed）** | `apply` | 不重试，候选未通过 gate；专属异常与 `pydantic.ValidationError` 解耦 |
| `EvolveEnvironmentError`（`apply --force` 时 pre-step 0a parent-dir access 失败 / pre-step 0b iterdir 或 sweep 失败；决策 #96 + #100 / C-rev7 / Z5） | **2** | `apply` | 用户应纠正环境（权限 / 残留）后重试 |
| `OSError` | 6 | `init` / 任意 | 视情况（磁盘满 / 权限）人工处理 |

未在表中列出的 Python 异常 → 兜底 exit 1（CLI traceback 入日志）。

**`pydantic.ValidationError` 包装详解（YELLOW-Y8）**：CLI handler（`nanobot/cli/commands.py` 内的 `evolve` 子命令 dispatch 层）在以下入口处用统一 `try/except pydantic.ValidationError as ve:` 包装：
  1. `--judge-pool` payload 解析（构造 `JudgePool(...)` 时）
  2. `--rubric-weights`（如果未来恢复）/ `--config` 文件 load → `EvolveDefaults(...)` 构造
  3. 任何嵌套 `RubricWeights` 求和失败（CLI 覆盖 `judge-pool.weights` 时）

`ValidationError` 一律被 wrap 为 `ConfigError(message=f"invalid {what}: {ve}", trigger=<source>)` 并 raise，使 CLI exit 码统一落到 2 而非泄漏出 traceback。Wrap 模式由 §10 不变量在 plan 期补充强制（M4 plan 期落地 unit test：`tests/evolve/test_config_error_wrap.py`）。

### 5.4 与 nanobot 现有 API 的关系（解耦边界）

落实 §1.3 解耦原则。M4 离线 lane 与 nanobot 运行时 lane 严格分离：

#### 5.4.1 M4 **依赖**的 nanobot 模块（白名单）

| 模块 | 允许的 import 形态（**精确**） | 用途 | 调用形态 |
|---|---|---|---|
| `nanobot.config.loader` | `from nanobot.config.loader import load_config` | 加载 `~/.nanobot/config.json` → `NanobotConfig` | `OfflineHarness.__init__` 内调 `load_config()` |
| `nanobot.config.schema` | `from nanobot.config.schema import Base, NanobotConfig` | `EvolveDefaults` / `EvolvePrivacyConfig` 字段挂载 | M4 plan 期添加新 Pydantic 模型 |
| `nanobot.providers.factory` | `from nanobot.providers.factory import create_provider` （**仅** `create_provider` 一个符号） | 实例化 judge model client（aux provider） | `judges.llm_judge.LLMJudge.__init__` 内调 `create_provider(model_str)` |
| `nanobot.skills` | `from nanobot.skills import SkillsLoader` （**仅** `SkillsLoader` 一个符号） | 加载 baseline `<workspace>/skills/agent/<name>/SKILL.md` + 解析 frontmatter | `harness._load_baseline()` 内调 |
| `nanobot.session.redactor` (M4 plan 期新增 facade) | `from nanobot.session.redactor import read_redacted_records` （**仅** `read_redacted_records` 一个符号） | Tier B 抽样脱敏：唯一被允许从 evolve 包 import 的 `nanobot.session.*` 入口 | `privacy/redactor.py` 内调 |

**`read_redacted_records` 签名锁定（YELLOW-5）**：

```python
# nanobot/session/redactor.py（M4 plan 期落地的 facade module）
from datetime import datetime
from typing import Iterator, TypedDict, Literal

class RedactedEvalRecord(TypedDict, total=True):
    """脱敏后的 session 抽样 record；keys 集合是 invariant，禁加任何
    `raw_*` / `original_*` / `user_*` 字段。任何字段值长度 > 256 chars
    在 facade 出口处被截断 + 加 `<TRUNCATED>` 后缀。"""
    task_id: str                       # ULID / UUIDv7；不可还原至 SessionDB 主键
    provider: str                      # 如 "anthropic"
    model: str                         # 如 "claude-3-5-sonnet"
    prompt_redacted: str               # 已去 PII 的 prompt 摘录
    response_redacted: str             # 已去 PII 的 response 摘录
    timestamp_utc: str                 # ISO 8601 UTC
    latency_ms: int
    token_usage: dict[Literal["input", "output"], int]
    # NO: user_id / session_id / channel_id / raw_prompt / raw_response /
    #     ip / email / phone / file_path / etc.

def read_redacted_records(
    *,
    since: datetime,
    skill_name: str | None = None,
    limit: int = 1000,
) -> Iterator[RedactedEvalRecord]:
    """读取 SessionDB 抽样并按 §9 脱敏规则 redact 后产出。

    Args:
        since: UTC 时间，仅返回 timestamp >= since 的 record
        skill_name: 可选过滤；None = 不限
        limit: 上限 record 数；防止 facade 一次性返回过大数据

    Yields:
        RedactedEvalRecord: TypedDict，keys 集合即 schema 边界
    """
```

facade 是离线 lane 触达 SessionDB 的**唯一**入口；其签名 + TypedDict keys 集合由
`tests/evolve/test_decoupling.py` 第 5 步 AST 断言锁定。`raw_*` / `user_*` /
`*_id`（除 `task_id`）任一字段在 RedactedEvalRecord 中出现即 test fail。

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
2. **遍历范围**（YELLOW-3 — 路径锚定 + YELLOW-Y7 命名文件存在性校验）：
   ```python
   import pathlib
   EVOLVE_PKG_ROOT = (
       pathlib.Path(__file__).resolve().parent.parent.parent / "nanobot" / "evolve"
   )
   assert EVOLVE_PKG_ROOT.is_dir(), (
       f"EVOLVE_PKG_ROOT not a directory: {EVOLVE_PKG_ROOT}"
   )
   # 稳定不变量（YELLOW-Y7）：harness.py 是 evolve 包的脊柱（§2.1 / §5.1），
   # 缺失即意味着「CWD drift（EVOLVE_PKG_ROOT 算错）」或「包尚未构建」。两种
   # 情况都应 fail loudly；用命名文件存在性替代脆弱的文件计数阈值。
   HARNESS_PY = EVOLVE_PKG_ROOT / "harness.py"
   assert HARNESS_PY.is_file(), (
       f"harness.py missing at {HARNESS_PY}; "
       f"either CWD drift (EVOLVE_PKG_ROOT computed wrong) or package not yet built"
   )
   py_files = list(EVOLVE_PKG_ROOT.rglob("*.py"))
   # **不**对 len(py_files) 做下限断言：增量开发中文件数可变，硬阈值会在
   # 实现期产生误导性失败（提示 "CWD drift?" 但实际只是 gates/ 还没填）。
   ```
   **禁止**使用 `pathlib.Path('nanobot/evolve').rglob('*.py')`（CWD-relative，pytest
   工作目录漂移会让 rglob 返回零文件 → 测试"通过"但什么都没扫，silent false negative）。
   `__file__`-anchored 解析 + 命名文件（`harness.py`）存在性 assert 是必须的双保险。
3. **传递闭包检查**：构建 import 图后做 transitive closure。若 `nanobot/evolve/foo.py` import `nanobot.evolve.bar`，而 `bar.py` 顶层 import 黑名单（如 `nanobot.agent.loop`），则 `foo.py` 与 `bar.py` **都**报 fail。
4. **动态 import 检测**：通过 AST 字符串字面量分析检测 `importlib.import_module("nanobot.X")` 与 `__import__("nanobot.X")` 调用；这两种形式同样落入黑名单匹配。
5. **R7 facade 单符号断言 + 白名单符号锁定（YELLOW-1）**：对 §5.4.1 表中**每一行**白名单模块，单独 assert 其唯一合法 import 形态。每条规则机械化，与表逐行对应：

   ```python
   ALLOWED_IMPORTS = {
       # module FQN -> set of allowed (kind, names) tuples
       # kind: "from" => "from X import Y[,Z...]"; "import" => "import X"
       "nanobot.config.loader":       {("from", frozenset({"load_config"}))},
       "nanobot.config.schema":       {("from", frozenset({"Base", "NanobotConfig"}))},
       "nanobot.providers.factory":   {("from", frozenset({"create_provider"}))},
       "nanobot.skills":              {("from", frozenset({"SkillsLoader"}))},
       "nanobot.session.redactor":    {("from", frozenset({"read_redacted_records"}))},
   }
   # 任何 evolve 包内文件出现 `from nanobot.providers.factory import X` 且
   # X != "create_provider"，或 `from nanobot.skills import Y` 且 Y != "SkillsLoader"，
   # 或 `import nanobot.providers.factory`（裸 import 形态），均 fail。
   # 任何 `nanobot.session.<X>` 不等于 "nanobot.session.redactor" 即 fail（黑名单 §5.4.2）。
   ```

   > **M5 维护契约（YELLOW-Y9）**：`ALLOWED_IMPORTS` 是 `nanobot/evolve/**` 合法
   > 跨包 import 的**唯一**事实之源。M5 若需新增白名单 entry（预期可能添加
   > `nanobot.session.goal_state` / 额外 provider import），**必须同步更新**
   > 两处：(a) §5.4.1 白名单表（spec 文档），(b) `tests/evolve/test_decoupling.py`
   > 的 `ALLOWED_IMPORTS` dict。漏改 (b) 会让新 import 在 CI 即 fail（机械化
   > 提醒）；漏改 (a) 会让 spec 与实现漂移，由 §10 不变量 + spec ↔ implementation
   > 双向校验 protocol 在 reviewer 期捕获。CI 要求：任何触及
   > `nanobot/evolve/**` 或 `nanobot/session/**` 的 PR 都必须 run
   > `test_decoupling.py`。

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
6. **Probe cascade integration**（`tests/evolve/test_probe_no_extra.py`，YELLOW-Y2 / 决策 #87；RED-1 C-rev4 扩展）：
   - 起 subprocess，在**不**安装 `[evolve]` extra 的 venv 内运行：
     ```python
     python -c "
     import nanobot.evolve
     from nanobot.evolve import *
     # SoT for __all__ — see §5.4.6. Two-way equality below catches both missing
     # AND extraneous entries. PR adding new entry must update both this set AND
     # add a Decision in §0.3 (per §5.4.6 narrative).
     expected_all = {
         'OfflineHarness', 'init_workspace', 'record_self_eval',
         'RunManifest', 'Candidate', 'Baseline',
         'RubricScore', 'RubricWeights',
         'JudgeConfig', 'JudgeResult', 'JudgeConsensus', 'JudgePool',
         'GateResult',
         'EvolveError',  # C-rev10 / Coh-Y2 / 决策 #99 amend — union-type anchor for isinstance(exc, EvolveError)
         'EvolveExtraNotInstalled', 'BaselineMismatch',
         'JudgeError', 'ManifestPrivacyViolation', 'ConfigError',
         'ApplyTerminalError',
         'EvolveEnvironmentError',  # C-rev7 / 决策 #100 — renamed from EvolveCliError
     }
     # YELLOW-Y7 (C-rev5): two-way equality on __all__ — catches both missing
     # and extraneous entries. Old subset check (expected - actual) silently
     # allowed adding a 20th name without updating the narrative count below.
     actual_all = set(getattr(nanobot.evolve, '__all__'))
     extra   = actual_all - expected_all
     missing = expected_all - actual_all
     assert not extra and not missing, (
         f'__all__ drift detected — only-in-actual={extra}, '
         f'only-in-expected={missing}. Update the expected set, §5.4.6 narrative '
         f'count, AND §0.3 Decision in the same PR.'
     )

     # RED-1 (C-rev4): the whole point of 决策 #87 — that nanobot.config.schema
     # can be imported without the [evolve] extra installed — is only
     # enforced if the probe ACTUALLY exercises that import chain. Importing
     # nanobot.evolve alone does not trigger the schemas.py cascade; we must
     # also import config.schema (which has a top-level `from nanobot.evolve.schemas
     # import RubricWeights`) and force resolution of every typed field
     # including EvolveDefaults.rubric_weights: RubricWeights via model_json_schema().
     from nanobot.config.schema import NanobotConfig, AgentDefaults
     NanobotConfig.model_json_schema()
     "
     ```
   - 子进程**必须**退出码 0；**不得**抛 `ImportError` 提及 `dspy` / `gepa` /
     `litellm` / `optuna`（用 stderr 文本断言）。stderr 断言覆盖**两条** import
     链路：`import nanobot.evolve` 自身、以及 `from nanobot.config.schema import
     NanobotConfig` 间接触发的 `from nanobot.evolve.schemas import RubricWeights`。
     这是 RED-1 (C-rev4) 闭合：若未来贡献者在 `nanobot/evolve/__init__.py` 加
     `import dspy`，仅靠 evolve 自身 import 的探针无法捕获（dspy 加载会被
     evolve `__init__` 吞，但 schemas.py 链路无关），现在两条链路同时断言即可
     兜住。
   - 测试框架建议用 `uv venv` + `uv pip install -e . --no-extras` 准备 throwaway
     env；CI 上若 `uv` 缺失则 `@pytest.mark.requires_uv` skip。
   - 此测试同时锁定决策 #87（`RubricWeights` 移 `nanobot/evolve/schemas.py` 后,
     `from nanobot.evolve.schemas import RubricWeights` 在 `nanobot.config.schema`
     顶层 import 链路上不触发 evolve extra 加载）。

7. **EvolveBase model_config 快照测试**（`tests/evolve/test_base_config_frozen.py`，
   YELLOW-Y4 / 决策 #91）：机械化锁定 §3.0 EvolveBase 稳定性公约。本测试如失败
   是 deliberate ——任何 `EvolveBase.model_config`（或 `RubricWeights` /
   `JudgePool` 的 override）改动**必须**在同一 commit 内：(a) 更新本测试的
   `EXPECTED_*` dict，(b) §0.3 追加新 Decision，(c) `docs/hermes-evolution/roadmap.md`
   §2 决策日志同步。

   ```python
   """Snapshot test for EvolveBase / RubricWeights / JudgePool model_config.

   If you change EvolveBase.model_config (or RubricWeights / JudgePool overrides),
   this test will fail. That is intentional — the change must be paired with a
   new Decision in docs/hermes-evolution/specs/m4-offline-skeleton.md §0.3 AND
   a roadmap update. Update the EXPECTED_* dicts below in the same commit.
   """
   from nanobot.evolve._base import EvolveBase
   from nanobot.evolve.schemas import RubricWeights
   from nanobot.evolve.judges.rubric import JudgePool

   EXPECTED_EVOLVE_BASE = {
       "extra": "forbid",
       "alias_generator": "to_camel",   # compared by qualname
       "populate_by_name": True,
       "frozen": False,
   }

   EXPECTED_JUDGE_POOL_OVERRIDES = {"frozen": True}
   # RubricWeights 当前继承 EvolveBase 默认（frozen=False，详见 §3.3 schemas.py 段）；
   # 如未来 §3.3 决定也 frozen，本 EXPECTED 与测试一并升级。
   EXPECTED_RUBRIC_WEIGHTS_OVERRIDES: dict[str, object] = {}

   def test_evolve_base_config_locked():
       cfg = EvolveBase.model_config
       assert cfg["extra"] == EXPECTED_EVOLVE_BASE["extra"]
       assert cfg["alias_generator"].__qualname__ == EXPECTED_EVOLVE_BASE["alias_generator"]
       assert cfg["populate_by_name"] == EXPECTED_EVOLVE_BASE["populate_by_name"]
       assert cfg.get("frozen", False) == EXPECTED_EVOLVE_BASE["frozen"]

   def test_judge_pool_overrides():
       assert JudgePool.model_config.get("frozen") is True
       # alias_generator 不允许被 override（必须仍来自 EvolveBase）
       assert JudgePool.model_config["alias_generator"] is EvolveBase.model_config["alias_generator"]
       # extra 仍 forbid（不可放宽）
       assert JudgePool.model_config.get("extra", "forbid") == "forbid"

   def test_rubric_weights_overrides():
       # 当前预期：未 override frozen（继承 EvolveBase 默认 False）。若 §3.3 决定
       # frozen=True，请同时改 EXPECTED 与本断言。
       assert RubricWeights.model_config.get("frozen", False) is EXPECTED_RUBRIC_WEIGHTS_OVERRIDES.get(
           "frozen", False
       )
   ```

   §3.0 EvolveBase 稳定性公约段落已在 §3.0 内 cross-ref 此测试为机械化执行点。

   **Provisional 状态（YELLOW-Y5 C-rev5）**：`EvolveBase` / `RubricWeights` /
   `JudgePool` 的 `model_config` 在 C-rev5 时是 **provisional 锁定**状态（per §3.0
   stability covenant 中的 `(provisional — 待 §6–§14 审定通过后确认)` 标签）。本
   快照测试是该 provisional 公约的机械化承载：
   - **正常 PR**：触发本测试失败说明无意识漂移，应回退或补 Decision + roadmap 更新。
   - **§6–§14 specwork 期 PR**：可能合法地需要调整 `model_config`（例如 Gate 详细
     定义引入新字段类型 / Judge calibration 协议引入新 frozen 字段 / PR-only deploy
     契约需要 lock 新 manifest 字段）。这种 PR **必须在 SAME COMMIT 同时**更新：
     (a) `EXPECTED_EVOLVE_BASE` / `EXPECTED_JUDGE_POOL_OVERRIDES` /
         `EXPECTED_RUBRIC_WEIGHTS_OVERRIDES` dict；
     (b) §0.3 新增 Decision 解释为什么调整；
     (c) §3.0 covenant 文字相应更新（包括是否摘掉 `(provisional)` 标签）。
   - **§6–§14 全部审定后**：摘掉 §3.0 的 `(provisional)` 标签，covenant 升级为 hard
     contract，本测试 docstring 同步更新（删去 provisional 框架，改为简单的「公约破坏
     提示」措辞）。

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
    "RubricWeights",
    "JudgeConfig",
    "JudgeResult",
    "JudgeConsensus",
    "JudgePool",
    "GateResult",
    "EvolveError",
    "EvolveExtraNotInstalled",
    "BaselineMismatch",
    "JudgeError",
    "ApplyTerminalError",
    "ManifestPrivacyViolation",
    "ConfigError",
    "EvolveEnvironmentError",
]
```

**`__all__` 公共表面（Y-arch-7 / C-rev6 — 取消硬编码 magic-number narrative；Z6 / Y-c6-arch-4 SoT 澄清）**：
公共表面的精确名称集合是 `tests/evolve/test_probe_no_extra.py` 中的 `expected_all` 集合（详见 §5.4.5 step 6 探针；C-rev7 起包括 `EvolveEnvironmentError` 替代 `EvolveCliError`，决策 #100 / Z5）—— 该 fixture 是**审查侧**的稳定锚点，**不是**生产侧 `__all__` 运行时 SoT。`expected_all` 与 `nanobot.evolve.__all__`（生产侧 SoT）两侧维持 two-way equality 断言（YELLOW-Y7 C-rev5 引入），目的是让任何 `__all__` 的增删都必须**同步**编辑 expected_all —— 这样生产侧改动在 PR diff 中必然附带 test diff 与 §0.3 决策 entry，reviewer 能从 diff 直接看出公共表面变化。生产侧 `__all__` 仍是 import-time SoT；`expected_all` 是 review snapshot peer（同决策 #91 `EXPECTED_*` dict 同源的"双向锁"模式）。本段不再陈述精确 count，避免数字漂移。

迁移说明 — C-rev7 起 `__all__` 包含 `EvolveEnvironmentError`（C-rev6 → C-rev7 重命名自 `EvolveCliError`，决策 #100 / Z5）：`EvolveEnvironmentError`（决策 #96 + #100）是 `apply --force` pre-step 0a/0b 失败 / 任何 CLI 前置环境失败的稳定异常类；外部 CI / 测试通过 `isinstance(exc, EvolveEnvironmentError)` 精确捕获，exit code 归属由 §4.6 dispatch 表统一管理（→ exit 2）—— 类自身**不**携带 `exit_code` 字段（C-rev7 layering 修复：library 异常不持有 CLI-层语义）。

**`init_workspace` 在 `__all__` 的理由（YELLOW-13）**：pytest fixtures 与外部脚本（如 M5 docs 中的 `evolve_quickstart` 示例）会直接调此函数，**不**先实例化 `OfflineHarness`。这是 deliberate 公开 API，不是误进。append-only 稳定性契约同样适用 —— rename / 改签名都需走 deprecation cycle（一个 minor 版本周期保留旧符号 + DeprecationWarning）。

**`RubricWeights` 在 `__all__` 的理由（决策 #84）**：决策 #84 把 `EvolveDefaults.rubric_weights` 类型从 `dict[str, float]` 改为 `RubricWeights`，外部脚本若要构造自定义权重需直接 import 该类（`from nanobot.evolve import RubricWeights; cfg.evolve = ...model_copy(update={"rubric_weights": RubricWeights(process=0.5, output=0.3, token=0.2)})`），因此必须进公共表面。

**`JudgeConfig` 在 `__all__` 的理由（决策 #89 / YELLOW-Y1 C-rev4）**：`JudgePool.judges: list[JudgeConfig]` 已是公共字段（`JudgePool` 在 `__all__`），外部程序化构造 `JudgePool` 必须能 import 一个稳定命名的元素类型 —— 否则只能反向触达 `nanobot.evolve.judges.rubric` 私有子模块路径，等同于把私有路径锁成公共表面。把 `JudgeConfig` 也提到 `__all__` 让 `JudgePool` / `JudgeConfig` 两者作为对偶整体暴露。

**`ApplyTerminalError` 在 `__all__` 的理由（决策 #90 / YELLOW-Y5 C-rev4）**：CLI handler 的 exit-code 分流 isinstance 判定需要稳定的公共类名 —— 不能依赖私有 `nanobot.evolve.exceptions.ApplyTerminalError` 触达。外部 CI 自动化脚本（按 exit 8 重试还是放弃）也需要直接 `except nanobot.evolve.ApplyTerminalError` 精确捕获，与裸 `except ValueError`（会误捕 `pydantic.ValidationError`）解耦。

**`EvolveError` 在 `__all__` 的理由（W3 / C-rev9 / 决策 #99 amend）**：`EvolveError` 是 §5.3 引入的 evolve 异常族统一身份标签（mixin），所有 evolve 自定义异常（`EvolveExtraNotInstalled` / `BaselineMismatch` / `ApplyTerminalError` / `JudgeError` / `ManifestPrivacyViolation` / `EvolveEnvironmentError` / `ConfigError`）均 mix in 本类。外部 telemetry / CI 通过 `isinstance(exc, nanobot.evolve.EvolveError)` 一次性判定异常是否来自 evolve 子系统（不必逐个 import 七个具体类做 `isinstance` 链）；同时 `__init_subclass__` 是 `STRUCTURED_KWARGS` 的运行时 backstop（W3 defense in depth），属于稳定 contract anchor，**不**得移出公共表面。

未在 `__all__` 列出的模块（`gepa.runner` / `judges.calibration` / `privacy.redactor` 内部细节 / `deploy.pr_writer`）视为 internal，可在 minor 版本变更签名；M5 仅可在 `__all__` 列表上**追加**新名字（如 `GateRejected`、`SemanticFidelityGate`、`HumanReviewGate`），不可删除或改签名（落实 §14 下游契约）。

---

> §4–§5 完。新增决策 #82（CLI exit code 全表）已追加 §0.3。下一节 §6 Gate 详细定义。

## 6. Gate 详细定义

§3.6 已锁定 `Gate` ABC、`GateResult` schema、`GATES` ordered list、首-fail-short-circuit、`<run_id>/gates/<N>-<name>.json` 落盘约定。**本章承担逐 gate 业务语义** —— 每个 gate 的输入边界、判定算法、metrics 字段语义、失败归因、env hardening。本章**不**重述 §3.6 已经锁定的 ABC 形状（避免 §3.6 ↔ §6 双源漂移）。

> **Gate 顺序**（locked §3.6 line 816–820）：`1-test-pass` → `2-size-cap` → `3-cache-compat`。短路行为：首个 `verdict == "fail"` 终止剩余 gate（决策 #109 解释为何选这个顺序）。

### 6.0 Gate ABC 与执行契约（§3.6 cross-ref + §6 补完）

§3.6 落地的 ABC + executor 是数据形状层的硬约束。本节追加 §3.6 未文档化的**业务执行契约**：

1. **同步 + deterministic + offline**（§3.6 line 809 强化）：每个 `Gate.evaluate` MUST：
   - **同步**：`evaluate` 不是 coroutine（无 `async def`），不在 `evaluate` 内部 `asyncio.run` 子循环。理由：harness `_run_gates` 在 `OfflineHarness.run` 已建立的 asyncio 上下文中以 `loop.run_in_executor(None, gate.evaluate, ...)` 形式串行调度，gate 自身 sync 让线程模型可预测。
   - **deterministic**（**当 `NONDETERMINISTIC=False`**，决策 #117 / C-rev14 / B-Y11）：相同 `(candidate.content_hash, baseline.content_hash, GATES_VERSION)` 三元组下 `verdict` + `failure_reason` + `evidence` MUST 比特一致；`metrics` 浮点字段允许 ±1e-9 ULP 抖动（来自 numpy / hashlib 内部）。CI 通过 §10 不变量 #X（待 §10 起草时新增）落地双跑断言。M4 三 gate 全部 `NONDETERMINISTIC=False`（默认值）；M5 LLM-judge gate 4 / human-PR gate 5 必须显式 `NONDETERMINISTIC: ClassVar[bool] = True` opt-out，harness 双跑等价 assert 仅作用于 `NONDETERMINISTIC=False` gate。
   - **offline**：`evaluate` MUST 不发起任何网络 syscall；env hardening 在 §6.0 「Env hardening 公约」一段统一描述。
2. **Env hardening 公约**（适用于所有 gate；决策 #118 / C-rev14 / B-Y3 + B-Y4）：harness 在调 `Gate.evaluate` 前 sets per-gate env。**Goal**：block secret leak to candidate 进程（cooperative threat model），**不**是 isolate from host platform。
   - **Proxy 硬连**（防意外 outbound）：上下大小写两套 + clear 任何 NO_PROXY 白名单 ——
     - `HTTP_PROXY = HTTPS_PROXY = http://127.0.0.1:1`
     - `http_proxy = https_proxy = http://127.0.0.1:1`（curl / requests 各派系 lowercase 形态）
     - `NO_PROXY = no_proxy = ''`（防 host bypass list 漏出）
     - DNS-resolvable but no listener → requests-style client 立即 ECONNREFUSED
   - **子进程 env strip 改 deny-list**（C-rev13 之前的 allow-list 形态在 CI 下破 pytest，因 `PYTEST_CURRENT_TEST` / `CI` / `GITHUB_*` / `XDG_*` 等 platform env 被误 strip）：以下 glob 模式 **MUST** strip：`*_API_KEY` / `*_TOKEN` / `*_SECRET` / `AWS_*` / `GOOGLE_APPLICATION_CREDENTIALS` / `OPENAI_*` / `ANTHROPIC_*` / `AZURE_*` / `GH_TOKEN` / `GITHUB_TOKEN`。其余 env 透传（含 platform CI / locale / fs / lib loader env）：`HOME` / `USER` / `LOGNAME` / `PATH` / `PYTHONPATH` / `LD_LIBRARY_PATH` / `DYLD_LIBRARY_PATH` / `DYLD_FALLBACK_LIBRARY_PATH` / `SSL_CERT_FILE` / `SSL_CERT_DIR` / `XDG_CACHE_HOME` / `LANG` / `LC_*` / `TMPDIR` / `TZ`。理由：cooperative threat model 下"保护 secret 不外泄"是真目标；"isolate from platform" 是 adversarial-sandbox 目标，M4 范围外。
   - fs scope：仅 `<run_id>/gates/sandbox/<gate-name>/` 目录可写；其余路径 read-only via `chdir` + 工作目录 sandbox（**非** seccomp / chroot——M4 仅 cooperative sandbox，恶意 candidate 不在威胁模型，见 §9 隐私边界）。
   - 网络 hardening 是 **cooperative leak prevention**：proxy block 仅防止"诚实 skill 在执行 toolcall 时**意外**触达真实 endpoint"；candidate skill 若主动 import socket 仍可绕过 —— M4 spec 不防御 adversarial candidate（all candidates 均由 GEPA 在我方 prompt 模板控制下生成，trust boundary 在 GEPA 而非 gate）。M5 若引入 third-party-evolved candidate（外部 Darwinian Evolver subprocess）需重新评估威胁模型。
3. **Failure mode 分类**：`evaluate` 抛任何 `Exception` 子类（**不**含 `BaseException` 直系如 `KeyboardInterrupt` / `SystemExit` / `asyncio.CancelledError`，这些 MUST 透传至 harness top-level 并由 `OfflineHarness.run()` 顶层 try/except 捕获后映射为 `final_status='harness_error'` + 上抛供 CLI handler 转 SIGINT/exit 130 / 标准退出语义；harness 内 `_run_gates` 不得 swallow 这三类）→ harness 把该 gate 视为 `verdict="fail"`，`failure_reason = f"gate-internal-error: {type(exc).__name__}: {str(exc)[:200]}"`，traceback 写到 **`<run_id>/gates/<candidate-hash-prefix>/<N>-<name>.error.txt`**（决策 #116 / B-Y5；与 §6.4.4 既有 per-candidate sub-dir `*.json` 路径对齐，避免同 run 多 candidate gate 失败的 traceback 互相覆盖）。Cleanup policy: 文件持久至 run 全程结束，由 `nanobot evolve report <run-id>` 输出 "internal-error candidates" appendix 表列举。Gate 内部异常**不**冒泡为 `EvolveError` —— gate 的对外语义只有 `pass` / `fail`，不区分"业务 fail"与"实现 bug"。CI 监控可通过扫描 `*.error.txt` 文件检测实现 bug 累积（决策 #109）。
4. **`metrics` / `evidence` 字段稳定性公约**：每个 gate 的 `metrics: dict[str, float]` 含一个**契约**键集（必填，schema 锁定）+ 任意**诊断**键（可选，自由扩展）；新增 `evidence: Optional[dict[str, str]]`（决策 #116）承载非数值 audit-trail 标识，亦区分契约键 vs 诊断键。两 dict 角色正交：`metrics` 仅承载可参与 fitness aggregation / report 数值聚合的浮点量，`evidence` 仅承载只读字符串标识（hex hash / 路径 / external job-id）。契约键集是 SoT —— 跨 milestone 对外 contract 仅承诺契约键的语义稳定性。M4 三 gate 的契约键集见 §6.1.4 / §6.2.4 / §6.3.4。
5. **Gate execution telemetry + hard timeout**（决策 #121 / C-rev14 / A-RED-3）：harness 在调用 `evaluate` 前后记 `time.perf_counter_ns()`，差值 / 1e6 写入 `GateResult.duration_ms`（int）。**Hard timeout 的 SoT 在 gate 内部** —— sync `evaluate()` 在 thread executor 中无法被 harness 强 cancel（`Future.cancel()` 对已开跑的 thread 是 no-op；threads 不可强 kill）。**常量定义位置**（C-rev15 / C-Y1 / RF-1）：`GATE_TIMEOUT_MS_HARD: int = 600_000`（10 分钟），module-level constant 落在 `nanobot/evolve/gates/test_pass.py`，与 `PER_RECORD_TIMEOUT_S = 30` 同位放置（§6.1.2 line ~2945）。Sourcing rationale：5 records × 30s `PER_RECORD_TIMEOUT_S` × ~4× slack ≈ 10min — 与原决策 #121 hard timeout intent 一致（GEPA 单候选 gate-1 不应吞噬 CI runner 半小时以上）。Gate 2/3 不需要此常量（O(1) 操作）。**Layering forward-marker**（C-rev16 / RF-5 / Arch-3 YELLOW）：此常量概念上是**跨 gate** 的（任何 long-running gate 的 hard wall-clock）；M4 co-locate 在 gate 1 模块内可接受（M4 仅 1 long-running gate + harness post-hoc warn 是唯一 second consumer）。一旦 M5 引入 gate-4（LLM-judge）或其他 long-running gate，MUST 把常量迁至 `nanobot/evolve/_constants.py`（与 `_atomic_swap.py` / `_cache_key.py` / `_skill_sandbox.py` 并列 internal namespace），原 `gates/test_pass.py` 路径保留 deprecation re-export 一个 milestone 后删除。若迁移推迟过 M5 gate-4 引入，新登记 §12 carry-forward entry 跟踪。约定：
   - **Gate 1 (long-running)** MUST 在每条 record 完成后 budget-check：`if (time.perf_counter() - gate_start) * 1000 > GATE_TIMEOUT_MS_HARD: break loop, set verdict='fail', failure_reason='timeout-hard:<elapsed>ms'`；剩余 record 跳过但已跑 record 的 metrics 保留（partial signal 给 GEPA）。
   - **Gate 2/3 (O(1))**：timeout 不适用（hash compare / int compare 永远 < ms 级）；budget-check 省略。
   - **Harness 端**：`_run_gates` 仍记 wall-clock `duration_ms`，但**不**再尝试 cancel；仅在 gate 返回 verdict 后 post-hoc：若 `duration_ms > GATE_TIMEOUT_MS_HARD`（同 SoT 常量，import from `nanobot.evolve.gates.test_pass`）但 verdict 已 pass / fail（gate 内部 budget-check 未触发即收尾），写 warn-log "gate exceeded hard timeout but completed (suspicious)"；不改 verdict。
   - SIGTERM / SIGKILL 仅作用于 §6.1.2 step 5 的**单 record subprocess**（per-record 30s deadline），不作用于整 gate。
   - Per-gate soft timeout（warn 但不 cancel）见各 gate 子节。

### 6.1 Gate 1 — `1-test-pass`（Tier C all-pass + Tier A rate floor）

**目的**：候选 skill 在 §3.1 的 Tier C 全部 record 上 strict-pass、Tier A 上 loose-match-rate ≥ 阈值。这是"功能未回归"的 lower bound，对应路线图 §6 隐式约束（任何进化产物**必须**保留 baseline 的核心能力）。

#### 6.1.1 输入数据集

| Tier | 是否参与 gate 1 | 阈值 | 理由 |
|---|---|---|---|
| **A**（synthetic） | **是** | loose-match-rate ≥ `TIER_A_PASS_RATE_FLOOR`（默认 `0.80`） | §3.1 line 350+ 已锁定 Tier A 是 statistical（synthetic 噪声允许小比例失败）；rate 而非 all-pass。 |
| **B**（SessionDB anonymized） | **否** | — | 用户级 opt-in（§1.1 #4 默认 `false`）；gate 不能依赖默认 disabled 数据源——会让 default 配置下 gate trivially-pass，破坏 §6 路线图约束意图。 |
| **C**（curated golden） | **是** | strict-pass-rate == `1.0` | §1.1 line 370 锚定"≥5 core golden = gate 1 lower bound"；curated golden 是回归基线，单条失败即视为功能丢失。 |
| **D**（task self-eval） | **否** | — | M4 仅 collect Tier D（不 gate-on）；run 内同期 collect + gate-on 形成 chicken-and-egg（首 run 时 D 为空 → trivially-pass）。M5 计划引入"上一 run 的 Tier D → 本 run gate"的 cross-run consumption（§14 下游契约）。决策 #110 选择 Option B（spec 立项期 dispatch 选项中的 B）。 |

**阈值 sourcing**：`TIER_A_PASS_RATE_FLOOR` 为 module-level constant `nanobot/evolve/gates/test_pass.py::TIER_A_PASS_RATE_FLOOR_BPS = 80`（**整数 basis points**，决策 #115 + B-Y1 fix；FP `0.80` 在 `tier_a_pass_count / tier_a_total >= 0.80` 比较中存在 FP 精度抖动 —— 改用整数 cross-multiplication：`tier_a_pass_count * 100 >= TIER_A_PASS_RATE_FLOOR_BPS * tier_a_total`），**不**通过 `EvolveDefaults` 暴露给 user config（M4 范围决策 #111：gate 阈值是 spec-locked 不可调，避免 user 通过 lowering 阈值 silently bypass gate；M5 若有真实需求再 hoist 至 config）。`TIER_C_PASS_RATE_FLOOR_BPS = 100` 类似（strict 100% pass）。

#### 6.1.2 判定算法

**Helper 模块归属**（决策 #119 / C-rev14 / B-Y10）：`_invoke_skill_in_sandbox` + env-strip subprocess wrapper 落在 **`nanobot/evolve/_skill_sandbox.py`**（与 `_atomic_swap.py` / `_cache_key.py` 并列 internal helper 命名空间）。`gates/test_pass.py` 通过 `from nanobot.evolve._skill_sandbox import invoke_skill_in_sandbox` 引用。本 helper 是 runtime sandbox 不是 schema validator，与决策 #93 forward-looking 触发条件（"第二个跨模型 validator helper"）正交 —— 不触发抽取至 `validators.py`。

**Precondition assert**（决策 #120 / C-rev14 / A-RED-4）：gate 1 进入 `evaluate` body 第一步 MUST：

```
tier_c_records = load_tier_c()
tier_a_records = load_tier_a()
if len(tier_c_records) == 0 or len(tier_a_records) == 0:
    raise GateInternalError(f"tier-{'c' if not tier_c_records else 'a'}-empty: gate-1 requires ≥1 record")
if len(tier_c_records) < 5:
    raise GateInternalError("tier-c-below-floor: §1.1 invariant requires ≥5 core golden")
```

`GateInternalError` 走 §6.0 point 3 path → `verdict='fail'` + traceback 落 `<run_id>/gates/<candidate-hash-prefix>/1-test-pass.error.txt`。让 fixture loader 回归（Tier C 数据集失踪 / 空）fail-loud 而非 silent vacuous-pass。

**Loop 主体**：

```
for each record in (Tier C ∪ Tier A):
    1. spawn isolated subprocess via invoke_skill_in_sandbox（per §6.0 env hardening；
       SIGTERM → 5s → SIGKILL deadline = PER_RECORD_TIMEOUT_S = 30s）
    2. inside subprocess: load candidate SKILL.md → invoke skill harness
       (helper contract: returns Optional[str] output or raises)
    3. compute per-record outcome:
       - Tier C: outcome = (output == record.expected) under match_mode
                          == 'strict' (§3.1)
       - Tier A: outcome = loose_match(output, record.expected)
                          per record.match_mode (§3.1, default 'loose')
    4. record per-record telemetry into metrics["records"][record_id]
       (诊断键，非契约键)
    5. budget-check (决策 #121 / hard-timeout SoT；常量定义 §6.0 point 5 + 本节末 module-level)：
       if (time.perf_counter() - gate_start) * 1000 > GATE_TIMEOUT_MS_HARD:
           break loop, set verdict='fail',
           failure_reason='timeout-hard:<elapsed>ms (records done: N/M)'

aggregate (整数比较，规避 FP wobble；决策 #115 / B-Y1)：
    tier_c_pass_count, tier_c_total
    tier_a_pass_count, tier_a_total

verdict:
    if tier_c_pass_count * 100 < TIER_C_PASS_RATE_FLOOR_BPS * tier_c_total: fail (path 1)
    elif tier_a_pass_count * 100 < TIER_A_PASS_RATE_FLOOR_BPS * tier_a_total: fail (path 2)
    else:                                                                     pass
```

**Per-record 失败隔离**：单条 record 的 subprocess crash / timeout / exception → 该条记 `outcome=False`，gate 不因单条 outcome 终止 —— 全部 record 跑完才计 `tier_*_rate`。理由：partial metrics 才让 GEPA-iteration loop 拿到稳定 fitness（gate 1 短路全停 → metrics 缺失 → 后续 GEPA round 无 signal）。这与 §3.6 line 825 "首个 fail 即 short-circuit" 的**跨 gate** 短路不冲突 —— 短路是 gate 之间，gate 1 内部全跑（决策 #112）。

**Per-record timeout**：`PER_RECORD_TIMEOUT_S = 30`（module-level constant，与 6.1.1 阈值同放置 reasoning）。subprocess 超过 30s 即 SIGTERM → 5s 后 SIGKILL → 该条 `outcome=False`，写诊断键 `metrics["timeouts"][record_id] = duration_ms`。

**Hard-timeout 常量同位声明**（C-rev15 / C-Y1 / RF-1）：`GATE_TIMEOUT_MS_HARD: int = 600_000` 同放 `nanobot/evolve/gates/test_pass.py` module top（紧邻 `PER_RECORD_TIMEOUT_S` / `TIER_*_PASS_RATE_FLOOR_BPS`）；`from nanobot.evolve.gates.test_pass import GATE_TIMEOUT_MS_HARD` 是 §6.0 point 5 harness post-hoc warn-check 的 import 来源。Sourcing：5 records × 30s × ~4× slack ≈ 10min，与决策 #121 hard timeout intent 一致。

```python
# nanobot/evolve/gates/test_pass.py
PER_RECORD_TIMEOUT_S: int = 30
TIER_A_PASS_RATE_FLOOR_BPS: int = 80
TIER_C_PASS_RATE_FLOOR_BPS: int = 100
# Layering note: this constant is conceptually cross-gate (any long-running gate's hard wall-clock).
# M4 co-locates with PER_RECORD_TIMEOUT_S (single consumer = gate-1 + harness post-hoc warn).
# At M5 gate-4 (LLM-judge) introduction, migrate to `nanobot/evolve/_constants.py` and keep this
# import path as a deprecation re-export. See CF-C-rev16-? if migration is deferred past M5 gate-4.
# Derivation (RF-6 / Scope-4): = ceil(TIER_C_FLOOR=5) * PER_RECORD_TIMEOUT_S=30 * SLACK_FACTOR≈4
#                                ≈ 600_000 ms (10 min). Revisit at M5 if either input invariant changes.
GATE_TIMEOUT_MS_HARD: int = 600_000
```

**Forward-markers**（C-rev16 / RF-5 / Arch-3 + RF-6 / Scope-4 lifted-from-advisory）：
- **Layering**：此常量当前 co-locate 在 `gates/test_pass.py` 是 M4 唯一 long-running gate + harness post-hoc warn 的 sole-consumer 妥协；M5 gate-4 (LLM-judge) 引入即触发迁至 `nanobot/evolve/_constants.py`，原路径保留一个 milestone 的 deprecation re-export。
- **Derivation cross-link**：`600_000 = ceil(TIER_C_FLOOR=5) × PER_RECORD_TIMEOUT_S=30 × SLACK_FACTOR≈4`；三个输入分别由 §1.1（Tier C floor，决策 #120 precondition assert）/ 本节 `PER_RECORD_TIMEOUT_S` / Sourcing 段 slack rationale 锚定。任一输入变更需同步重新计算并在 M5 retro 评估 SLACK_FACTOR 是否仍合理。

#### 6.1.3 失败归因（`failure_reason`）

verdict=`fail` 时 `failure_reason` 形如：

- `"tier-c-rate-floor: 4/5 (0.80) < 1.0"` —— Tier C 未全过（path 1）
- `"tier-a-rate-floor: 17/25 (0.68) < 0.80"` —— Tier C 全过但 Tier A rate 不达标（path 2，仅在 path 1 通过后评估）
- `"gate-internal-error: <ExcName>: <msg>"` —— gate.evaluate 自身抛异常（§6.0 point 3）

#### 6.1.4 `metrics` 契约键

| Key | 类型 | 语义 |
|---|---|---|
| `tier_c_pass_count` | float（int 兼容） | Tier C strict-pass record 数 |
| `tier_c_total` | float | Tier C record 总数 |
| `tier_c_rate` | float ∈ [0, 1] | `tier_c_pass_count / tier_c_total`。**`tier_c_total == 0` 不在此键计算路径中**：决策 #120 / C-rev14 / A-RED-4 已在 §6.1.2 precondition 把 empty fixture 升级为 fail-loud `GateInternalError` → gate 1 永不达到 aggregate 计算时 `tier_c_total == 0` 状态。本字段在 metrics 中仅在 verdict 已确定（pass / non-precondition-fail 路径）时存在 |
| `tier_a_pass_count` | float | 同上 Tier A |
| `tier_a_total` | float | 同上 Tier A |
| `tier_a_rate` | float ∈ [0, 1] | 同上 Tier A；`tier_a_total == 0` 同样由 §6.1.2 precondition 拦截 |

诊断键（非契约，跨 milestone 可加可减）：`records` per-record outcome map、`timeouts`、`subprocess_errors` 等。下游消费者（§4.4 `apply` / report.md generator）**只**消费契约键。

**Pre-C-rev14 silent-vacuous-pass risk 注**：原 "total=0 → rate=1.0 conventional" 在 fixture loader 回归（如 Tier C 子目录被误删、glob pattern 漂移）时让 gate 1 trivially-pass，破坏 §1.1 line 370 "≥5 core golden = gate 1 lower bound"。决策 #120 把"零 record 时如何聚合"问题彻底前置到 precondition assert，避免 aggregate path 内的 div-by-zero 处理（避免规则散布两处）。

### 6.2 Gate 2 — `2-size-cap`（per-skill SKILL.md 行数硬上限）

**目的**：候选 skill 文件不得无限制膨胀。GEPA 优化压力倾向于增加 prompt 长度以挤性能；不设硬上限，几轮迭代后 skill 文件会失控（一手观察：上游 Hermes 实测 GEPA 跑 30 轮后无 size cap 的 skill 从 80 行涨到 600+ 行）。

#### 6.2.1 度量选择：lines（不是 tokens、不是 bytes）

§3.2 line 415 `size_metrics: dict[str, int]` 已含 `chars` / `tokens_est` / `lines` 三个度量。Gate 2 主度量选 **`lines`**（决策 #113），理由：

- **deterministic**（§6.0 point 1 硬约束）：tokens 需要 tokenizer 选择（cl100k / o200k / claude-tokenizer 各异），跨 provider / 跨 tokenizer 版本不稳定 → 违反 deterministic gate；bytes 受 BOM / CRLF / 编码影响（同语义文件 byte 数可不同）；lines 在 normalize 后仅依赖 `\n` 计数。
- **human-grain**：M4 范围 §1.1 #5 锁定进化目标仅 `SKILL.md`（人类编辑文件），lines 是人类直觉单位 —— review 一份 600 行 markdown 与 200 行 markdown 的认知负担差异，lines 比 token-count 更符合 reviewer 心智。
- **无 tokenizer extra 依赖**：gate 实现 zero extra import（与 `nanobot/evolve/schemas.py` 的 zero-extra-deps 哲学一致；不强迫 tiktoken / anthropic-tokenizer 在 gate 路径 install）。

**`lines` 度量精确定义**（C-rev14 / B-Y2）：

```python
def count_lines(content: str) -> int:
    # CRLF / CR 统一规范化为 LF，再 splitlines
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return len(normalized.splitlines())
```

`splitlines()` 语义：trailing-newline-only 文件计为 N 而**非** N+1（与 reviewer "看一眼这文件多少行"直觉对齐）；空文件计为 0；末尾无 `\n` 的文件按内容行数计。Git autocrlf 跨平台问题在 SKILL.md 进入 §3.2 `SkillContent.body_md` 前已 normalize（M4 invariant required-before-merge：`.gitattributes` MUST 把 `*.md` 标 `text eol=lf`，由 §10 不变量章节起草时锁定；本节 fallback：即便 gitattributes 漂移，`count_lines` 内部 normalize 仍保证 gate 2 度量稳定）。

#### 6.2.2 阈值

| Constant | 默认 | 来源 |
|---|---|---|
| `SKILL_LINE_HARD_CAP` | `400` | 经验阈值；上游 Hermes 现行 skill 中位 ~120 行，Q3 ~ 200 行；400 行给 GEPA 留 ~3x 头部。M5 retro 视实测调。 |
| `SKILL_LINE_DELTA_CAP` | `+150` | 候选相对 baseline 增量上限；防止 baseline 已 350 行时候选窜到 480 还过 hard cap。两条同时校验。 |

阈值同 §6.1：module-level constant，**不**经 `EvolveDefaults` 暴露（决策 #111 同源）。

#### 6.2.3 判定算法

```
candidate_lines = candidate.size_metrics["lines"]
baseline_lines  = baseline.size_metrics["lines"]
delta           = candidate_lines - baseline_lines

verdict:
    if candidate_lines > SKILL_LINE_HARD_CAP:        fail (path 1)
    elif delta > SKILL_LINE_DELTA_CAP:               fail (path 2)
    else:                                             pass
```

**Exemption mechanism**：M4 **无** —— 任何候选触发任一 cap 即 fail，无 frontmatter override / config bypass。理由：gate 是路线图 §6 五条约束之一，bypass 机制在 M4 等于把硬 gate 退化为 advisory；若用户真有正当理由生成超大 skill，应在 GEPA prompt 模板里体现意图（让模型自身受约束），而不是事后 bypass gate。M5 若引入"large skill 例外"（如 self-modifying meta-skill）需在 §14 下游契约中显式 carve-out。

#### 6.2.4 `metrics` 契约键

| Key | 类型 | 语义 |
|---|---|---|
| `candidate_lines` | float | 候选 SKILL.md 行数 |
| `baseline_lines` | float | baseline SKILL.md 行数 |
| `delta_lines` | float | `candidate_lines - baseline_lines`（可负） |
| `hard_cap` | float | `SKILL_LINE_HARD_CAP`（写入便于 report.md 直接读，不 spec 跨调用） |
| `delta_cap` | float | `SKILL_LINE_DELTA_CAP` |

`failure_reason` 形如：
- `"hard-cap-exceeded: 480 > 400 lines"`
- `"delta-cap-exceeded: +180 > +150 lines (480 vs 300 baseline)"`

### 6.3 Gate 3 — `3-cache-compat`（prompt cache stable 段 hash 等价）

**目的**：路线图 §6 约束 1（"永不打破 prompt cache"）的硬实现。`Candidate.cache_key_hash`（§3.2 line 414，`sha256-12` of stable 段）必须 ≡ `Baseline.cache_key_hash`；任何不等即 fail，候选立即出局。

#### 6.3.1 "stable 段" 定义（与 §3.2 cache_key_hash 计算同源）

**SoT**：`nanobot/evolve/_cache_key.py::compute_cache_key_hash(skill_md_content: str) -> str`，§3.2 计算 `cache_key_hash` 与本 gate 校验**走同一函数**（避免 §3.2 计算路径与 §6.3 校验路径双源漂移）。

stable 段定义（M4 锁定，M5 不可更改否则破坏 §10 不变量 #1 → §14 下游契约）：

1. SKILL.md 解析为 `(frontmatter, body_md)`（§3.2 `SkillContent.frontmatter` / `body_md`）。
2. **frontmatter 中**：`name`、`description`、`origin`、`created_by` 四字段进入 stable 段（M2 已锁定的 frontmatter contract）；`evolved_from_run` / `evolved_at` / `parent_skill_hash` / `created_at` **不**进入（这些 evolution-specific 字段每 run 都变，进 stable 段会让 cache 永远 miss）。
3. **body_md 中**：完整 markdown 文本（不含 frontmatter）按 byte 串入 stable 段。`body_md` 是 prompt cache 命中的 critical path —— body 任何字符变化都让 Anthropic prompt cache miss，这正是 gate 要捕获的。
4. stable 段拼接：`f"{name}\0{description}\0{origin}\0{created_by}\0{body_md}"`，sha256-12（前 12 hex chars of sha256 hex digest）。

**关键观察**：gate 3 的"等价"不是"语义等价"也不是"AST 等价" —— 是 **byte-level 等价**。GEPA 即使做"等价改写"（reorder bullet 顺序、改 markdown emphasis）也会被 gate 3 reject。这是**有意为之**：

- Anthropic prompt cache 是 byte-prefix-based（cache key = exact byte prefix），任何 byte diff 即 miss → 路线图约束 1 直接消费 byte 等价语义；
- "语义等价改写"是 GEPA 优化空间内**没有 fitness 信号**的修改（fitness 已用 RubricScore 衡量正确性，byte-equivalent rewrite 不改 RubricScore 但消耗 cache）—— 用 hard gate 让 GEPA 优化器学到"不要做无信号的 byte 重排"，这是设计意图。

#### 6.3.2 判定算法

```
candidate_key = candidate.cache_key_hash   # 已在 §3.2 时计算并锁
baseline_key  = baseline.cache_key_hash

verdict:
    if candidate_key == baseline_key:  pass
    else:                              fail
```

单 hash 比较，O(1)；no fs / network IO；no false-positive mitigation（hash 等价是定义本身，false-positive 来自 hash 函数 collision，sha256-12 collision 概率忽略）。

**False-positive 注**：sha256 截断到 12 hex chars (~48 bits)，collision 期望 ~2^24 ≈ 16M 候选 — 远超 M4 单 run 候选量（GEPA 默认 ≤ 32 iterations × ≤ 8 candidates/iter ≈ 256）。M5 若候选量级跨数量级提升（≥ 1M / run），需 hoist 到 sha256-16 或全 hash；本 spec § 14 下游契约 carry-forward。

#### 6.3.3 `metrics` 契约键 + `evidence` 契约键

**`metrics`** 仅一个 boolean-shaped float key（数值聚合 / fitness signal 角色）：

| Key | 类型 | 语义 |
|---|---|---|
| `byte_diff_present` | float ∈ {0.0, 1.0} | `0.0 == identical, 1.0 == differ`（gate verdict 同义量化） |

**`evidence`** 契约键（决策 #116 / C-rev14 / B-Y6；新 sibling 字段，承载非数值 audit-trail 标识；pass / fail 路径**同时**写入）：

| Key | 类型 | 语义 |
|---|---|---|
| `candidate_cache_key` | str (hex sha256-12) | 候选 SKILL.md stable 段 hash；与 §3.2 `Candidate.cache_key_hash` 同源 |
| `baseline_cache_key` | str (hex sha256-12) | baseline 同源 hash |

`failure_reason` 退回纯人读 message 角色，形如：
- `"cache-key-mismatch: candidate=a3f8c211ab4d != baseline=12bc97ee5f08"`

`verdict='pass'` 时 `failure_reason=None`，但 `evidence` 字段**仍**写两个 cache_key —— 这是决策 #116 修复决策 #114 的关键 audit gap：原设计在 pass path 丢失 hash 标识（仅 `byte_diff_present=0.0` 不足以追溯具体 hash 值），promoted candidate 的 manifest 无法被外部 audit 工具反向定位 cache key。

**Schema 边界更新注**（决策 #116 supersedes 决策 #114 的"hex 走 failure_reason"分支）：决策 #114 选择"`metrics` 不动 schema，hex 走 `failure_reason`"是为了避免改 §3.6；决策 #116 引入新 sibling `evidence: dict[str, str] \| None` 是更干净的 layering（`metrics` 角色仍为浮点聚合，`evidence` 是只读字符串 audit）。这是**字段新增**而非类型放宽，对 manifest JSON schema validators 是 backward-compatible（旧 manifest 的 `evidence` 默认 `null`）。M5 若引入更多 hash-shaped gate（ast-equivalence 等）直接复用 `evidence` 即可，不需再次改 schema。

### 6.4 Gate ordering、聚合与短路语义

#### 6.4.1 顺序（§3.6 line 816–820 cross-ref）

`GATES = [TestPassGate(), SizeGate(), CacheCompatGate()]` —— 顺序由列表位置决定（§3.6 locked），名字前缀 `1-` / `2-` / `3-` 与位置同步。

**Registry contract test**（C-rev14 / B-Y9）：手动维护的 `GATES` list 与"name 前缀按位置对齐"约定靠 `tests/evolve/test_gates_registry.py` 强制：

- `test_gates_ordering_matches_name_prefix`：MUST 断言 `for i, gate in enumerate(GATES): assert gate.name.startswith(f"{i+1}-")`，防止 list 位置与 name 前缀漂移。
- `test_no_orphan_gate_subclass`（C-rev15 / 决策 #122 / C-Y2 / RF-2；C-rev16 / RF-2+RF-3 dual-filter）：MUST 用**双 filter** 后断言 —— `production_subclasses = {c for c in Gate._subclasses if c.__module__.startswith("nanobot.evolve.gates.") and not inspect.isabstract(c)}` → `assert production_subclasses <= {type(g) for g in GATES}`（§3.6 `Gate._subclasses` registry 经 `__init_subclass__` 在 class-body 执行时自动 populate）。两 filter 的角色：
  - **`__module__` prefix filter（RF-2 / Corr-1 70%）**：tolerate 测试 fixture 误用（如 `class MockGate(Gate): ...` 在 `tests/` 内 declared）—— fixture 子类持久化进 class-level mutable list 会污染后续 assertion；prefix filter 将其排除。Canonical 规则仍是"测试代码 MUST NOT subclass `Gate`"（用 `unittest.mock.Mock(spec=Gate)` 或 duck-typed double 替代），filter 是 defense-in-depth 而非许可门。
  - **`inspect.isabstract` filter（RF-3 / Corr-2 + Arch-2 60%）**：forward-compat 容许 M5 abstract intermediate（如 `class JudgedGate(Gate, ABC): ...`）落入 `_subclasses` 而**不**进 `GATES`（abstract base 无法实例化）；isabstract filter 确保此类 forward-compat case 不 false-fail。仅 concrete production 子类必须出现在 `GATES`。

  原 C-rev14 草稿 `inspect.getmembers(nanobot.evolve.gates, ...)` 仅遍历 package object 上的 re-export 属性 —— 新增 `gates/foo.py` 但忘 `__init__.py` re-export 的 orphan 子类逃出检测；`_subclasses` registry + dual-filter 共同闭合该 covering hole（B-Y9 + Corr-1 + Corr-2/Arch-2 真正闭合）。测试需在 `from nanobot.evolve.gates import *` 之后断言（确保所有 submodule 在 `__init__.py` 已被 import 一次，触发各 submodule 的 class-body → `__init_subclass__` 副作用）。

  **示例形态**：
  ```python
  import inspect
  production_subclasses = {
      c for c in Gate._subclasses
      if c.__module__.startswith("nanobot.evolve.gates.")
      and not inspect.isabstract(c)
  }
  assert production_subclasses <= {type(g) for g in GATES}, (
      f"orphan production gate subclass(es): {production_subclasses - {type(g) for g in GATES}}"
  )
  ```

理由：introspection-derived `GATES`（自动按 name 前缀排序）虽更"自动"但破坏 `GATES` 作为 explicit ordered list 的可读性 + 让"加 gate 4 时显式 append"的 audit trail 模糊；contract test 是更轻量级的执行（决策 #104 enforcement 精神镜像 —— 让规则机械化但不引入 introspection 副作用）。M5 加 gate 4 / gate 5 时这两条测试自动覆盖。

**为何 1 → 2 → 3 而不是 3 → 2 → 1（最便宜先）？**（决策 #109）

- **直觉反例**：cache-compat gate 是 O(1) 哈希比较；size gate 是 O(1) int 比较；test gate 跑 subprocess × 数十 record，是 O(秒级)。最便宜先（3 → 2 → 1）让"明显坏候选"快速 reject，省 CI 时间。
- **Spec 选择 1 → 2 → 3 的反向理由**：候选**总数**在 GEPA 单轮 ≤ 8 ~ 32（DSPy 默认），单候选 gate 1 cost ~30s × 5–25 records ≈ 数分钟级；gate 2/3 ~ms 级。从 wall-clock 看，gate 1 cost dominates 任意候选 —— 把它放第一位的代价：所有 candidate 跑过 gate 1 才能被 size/cache reject。**关键 trade-off**：metrics 完整性 vs CI 时间。
  - **完整 metrics 必要性**：GEPA 优化器需要在 reject 候选上拿到完整 fitness signal（包括 test outcome）才能学习"什么样的候选会过 gate"；若 size/cache 先 reject，GEPA 看不到 test signal，下一轮 mutation 仍会重蹈覆辙（短路把 test signal 信息掩埋）。
  - **路线图 §6 约束 1 优先级**：cache-compat 是路线图明文约束，结构上**必须**让候选携带 test 完整 metrics 走到 cache 校验时仍可被定位（reasoning：reviewer 拿 report.md 看 `gate-rejected-at: 3-cache-compat` 时同时看到 test_rate 与 size_delta 上下文，比"前面就 reject 了，无 test 数据"信息更丰富）。

- **结论**：1 → 2 → 3 顺序优先 metrics 完整性 + 故障可观测性 over wall-clock 节省。CI 时间 cost 由 §6.4.3 GEPA 层面 early termination（候选 fitness 太低跳过 gate）部分缓解。Decision #109 grounding。

#### 6.4.2 短路（locked §3.6 line 826）

跨 gate 首-fail 短路：`gate i.verdict == "fail"` → `gate i+1, i+2, ...` 不执行。`<run_id>/gates/<N>-<name>.json` 仅前 i 个文件存在。`Candidate` 标记 `gate_rejected_at: <gate_name>`（in-memory；不入 Candidate schema —— 仅 harness 内部记号，落盘体现为 manifest `gate_verdicts` list 的最后一项 `verdict=='fail'`）。

#### 6.4.3 GEPA-layer early termination（与 gate 短路正交）

GEPA 优化器内部有"低 fitness 候选不进 gate"机制：候选若 `judge_consensus.aggregate < FITNESS_GATE_FLOOR`（默认 `0.3`，spec-locked），harness `_run_gates` 不调；该候选的 `gate_verdicts: []`（空 list），manifest 记 `final_status="no_improvement"` 候选侧分支。

这避免 obviously-bad 候选浪费 gate-1 subprocess 时间。**与 gate 链短路区分**：

| 维度 | Gate 链短路 | GEPA-layer early termination |
|---|---|---|
| 触发 | 上一个 gate `fail` | 候选 fitness < `FITNESS_GATE_FLOOR` |
| 跳过的 gate | `i+1, i+2, ...` | 全部 gate（候选根本不入 gate 链） |
| `gate_verdicts` 长度 | `1 ≤ len ≤ 3` | `0` |
| manifest 结果 | `final_status=rejected_by_gate` | `final_status=no_improvement` |

#### 6.4.4 全 candidate 失败下的 `gate_verdicts` 选取

§3.7 line 875–876 已锁定：`RunManifest.gate_verdicts` 只记**一个** candidate 的 trace —— promoted candidate（若有）；全员 reject 时记 fitness 最高者的 trace。本节 normative 重申：harness 选取规则是 stable-sort by `judge_consensus.aggregate desc, candidate.gepa_iteration asc`，取 top-1 写入 `gate_verdicts`。**`gepa_iteration` cross-link**（C-rev14 / B-Y7；C-rev15 / C-Y3 / RF-3：line-number cite 删除，改 stable anchor）：本字段定义在 §3.2 `Candidate` schema（`gepa_iteration: int  # GEPA 迭代序号（≥1）`）；本节 tiebreak 规则的 SoT 即 §3.2 该字段，确保 reviewer / 实现者能 trace 到字段定义。原 C-rev14 落地的 `§3.2 line 434` 行号引用在 §3.2 schema 内字段排序变更时即漂移（line 434 实际是 `Baseline.loaded_from`），改用章节锚点避免 in-spec cross-ref 行号刚性绑定。其余候选 trace 仍落 per-candidate `<run_id>/gates/<candidate-hash-prefix>/*.json`（每候选一组 sub-dir，从 §2.2 line 250 既有目录约定派生；与 §6.0 point 3 traceback 落库路径同前缀对齐）。

### 6.5 Gate 输出 → `final_status` 映射

`final_status` 是 §3.7 RunManifest 字段，CLI exit code（§4.6）由 § dispatch 表从异常类型映射，**不**从 `final_status` 派生（决策 #82 / #88 已锁定 gate fail 不映射非零 exit code）。

#### 6.5.1 计算位置

**SoT**：`OfflineHarness._compute_final_status(promoted: Optional[Candidate], all_candidates: list[Candidate], baseline: Baseline) -> Literal[...]`，被 `OfflineHarness.run()` 在 GEPA loop 完成后调用一次，写入即将构造的 `RunManifest`。`apply` 子命令是**只读消费者**（§3.7 frozen=True manifest），不重算 `final_status`。

#### 6.5.2 决策树

```
def _compute_final_status(promoted, all_candidates, baseline):
    # 1. harness_error 由顶层 try/except 在 OfflineHarness.run 包装；
    #    本函数只在 happy path 之后调用，不会返回 'harness_error'
    if promoted is not None:
        return "promoted_to_pr"   # 全 gate pass + fitness > baseline_fitness

    if any_candidate_failed_gate(all_candidates):
        return "rejected_by_gate"  # 至少一候选有 gate fail trace

    # 全 gate pass 但无 promoted —— 即所有候选 fitness ≤ baseline
    return "no_improvement"
```

`promoted` 由 `_select_promoted` 选出：候选必须满足 `len(gate_verdicts) == len(GATES) and all(v.verdict == "pass" for v in gate_verdicts) and judge_consensus.aggregate > baseline_judge_consensus.aggregate`。否则 `promoted = None`。

**Tied-score semantics 显式声明**（C-rev14 / B-Y8）：上述 `>` 是**严格大于**，不加 epsilon。`judge_consensus.aggregate == baseline.aggregate`（含 FP wobble 偶现的精确相等，跨 round 概率 < 1%）按 "no_improvement" 处理 —— promoted = None，final_status = `'no_improvement'`，不进 PR。理由：(a) 加 epsilon 引入新 magic constant（应取多大？1e-9 / 1e-6 / 1e-3 各有 trade-off），M4 范围内不值得 calibration 成本；(b) FP wobble 偶现的 tie 并非 GEPA 对 baseline 的 "真正提升"，按 no_improvement 拒绝是 conservative 默认；(c) 若 GEPA 真生成了 byte-equivalent semantics 改写（cache 兼容、aggregate 相同），gate 3 也会让其 cache_key 等价 → 实际是 baseline 的同质重复，pass-through 无价值。M5 若发现 tied-score 频次显著（≥ 5% promoted candidates），可在 M5 retro 评估是否引入 epsilon convention 或 tiebreak 规则（如 `delta_lines < 0` 优先即"更精简的 tied 候选"upgrade）。

`harness_error` 是顶层 `try/except` 边界产物（`EvolveError` 子类 escape 到 `OfflineHarness.run` 的 outer try），不由 `_compute_final_status` 返回。

#### 6.5.3 下游消费者

| 消费者 | 读取 `final_status` 的方式 | 行为 |
|---|---|---|
| `nanobot evolve report <run-id>` | 直接读 manifest，渲染 report.md | 模板分支：`promoted_to_pr` / `rejected_by_gate` / `no_improvement` 三种 markdown header + 不同 metrics 表格 |
| `nanobot evolve apply <run-id>` | 决策 #88 / #90：`final_status != 'promoted_to_pr'` 抛 `ApplyTerminalError` → exit 8 | 即 apply 仅在 `promoted_to_pr` 时产 PR artifact |
| `OfflineHarness.run()` 调用方（Python API） | 读返回的 `RunManifest.final_status` 字段 | §5.1 docstring (line 1668–1669) 已锁定：返回而非异常；调用方分流 |
| CI 自动化脚本 | exit code（§4.6）+ optionally manifest.json grep | exit 0 + final_status 决定下一步（merge / log / 重跑） |

### 6.6 Forward to M5（gates 4–5 与不变量）

§14 下游契约（待 Round I 起草）将正式锁定本节内容；本节先列出对 M5 的硬约束。

#### 6.6.1 M5 必须**保留**的 M4 表面（不可破坏）

1. **`Gate` ABC + `GateResult` schema**（§3.6）：M4 锁定，M5 **不**得修改 `name` / `evaluate` 签名、`GateResult` 字段集合（含 C-rev14 新增的 `evidence` sibling）、`verdict: Literal["pass", "fail"]` 二值（不可加 `INSUFFICIENT_DATA` 或其他三值，§3.7 manifest 字段都按二值假设构造）。**Forward-looking 注 (C-rev14 / B-Y12)**：若 M5 引入 async / human-in-loop gate（gate 5 human-PR 的"pending"语义不可映射到 pass / fail 二值），有两条 spec-stable 路径：(a) 在 `Gate` ABC 加 `evaluate_async()` sibling 方法 + `IS_ASYNC: ClassVar[bool] = False` opt-in（同决策 #117 `NONDETERMINISTIC` 形态）；(b) 把"pending"作为 `final_status` 新值（如 `awaiting_human_review`），gate 自身仍同步返回 `verdict='pass'` + `evidence={'pr_url': ...}` 而 final_status reflect waiting。两路径均**不**改 `verdict` 二值，符合本节硬约束 —— acknowledged 为 M5 carry-forward decision，**不**是 M4 lock breach。
2. **`GATES` ordered list 扩展方式**（§3.6 line 828）：`GATES.append(SemanticFidelityGate(), HumanReviewGate())` —— 仅 append，不 insert / 不 reorder。新 gate name 必须 `4-*` / `5-*` 前缀。
3. **gate 1–3 业务语义**：阈值常量（`TIER_C_PASS_RATE_FLOOR_BPS` / `SKILL_LINE_HARD_CAP` / `SKILL_LINE_DELTA_CAP` / etc.）在 M5 可调，但**不可降级**到 advisory（即不能让"硬 gate"变"warn"）。
4. **`final_status` enum 四值锁定**（C-rev14 / C-Adv-1 narrowing）：M5 **不**得在 `final_status` enum 上 remove / rename 任一既有值（`promoted_to_pr` / `rejected_by_gate` / `no_improvement` / `harness_error`）；新增值（如 `awaiting_human_review` for gate 5）允许。本约束仅锁 enum 名集合稳定性，**不**预先规定 M5 如何在 enum 之外承载 gate-4 / gate-5 细分语义（`rejection_subtype` 诊断字段、新 final_status 值、其他 schema 扩展均为 M5 自由 design space）。
5. **CLI exit code 不变**（§4.6）：gate fail 仍不映射非零 exit；apply 业务终态仍 exit 8（决策 #88）。

#### 6.6.2 M5 自由扩展面（无需 spec 修订）

1. **新 gate 实现**：`nanobot/evolve/gates/semantic_fidelity.py` + `human_review.py`，append 到 `GATES`；
2. **gate 阈值调整**（M4 spec-locked constants → M5 retro 后重新定义，但需在 M5 spec §0.3 显式 decision），允许放宽或收紧。
3. **新 metrics 诊断键**（非契约键）：随时加，无 spec 修订负担。
4. **新 failure_reason 格式**：自由，无对外 contract。

#### 6.6.3 跨 milestone 不变量（hardline）

| 不变量 | M4 落地 | M5+ 强制 |
|---|---|---|
| 任何 evolution 产物前都过 `GATES` 全链（除 GEPA early termination） | §6.4 | M5 不得绕开 `_run_gates` 直接调 `pr_writer` |
| `final_status == 'promoted_to_pr'` ⇒ `len(gate_verdicts) == len(GATES) and all(pass)` | §6.5.2 `_select_promoted` | M5 加 gate 4–5 时 `len(GATES)=5`，`promoted_to_pr` 自动要求 5-pass |
| Gate 实现 deterministic + offline | §6.0 point 1 | M5 `SemanticFidelityGate` 调 LLM judge → 非 deterministic → 例外条款必须在 §14 显式 carve-out（gate 4 是计划中第一个例外，M5 spec 必须正面处理） |

> §6 Gate 详细定义完。本章 C-rev13 引入决策 #109–#114（6 条），C-rev14 闭合 4 RED + 12 must-fix YELLOW 后追加决策 #115–#121（7 条），4 条 advisory YELLOW 至 §12.4（CF-C-rev13-1..4）。C-rev15 闭合 3 条 ≥60% confidence must-fix YELLOW（C-Y1 `GATE_TIMEOUT_MS_HARD` 常量定义 / C-Y2 `_subclasses` 注册表 / C-Y3 `gepa_iteration` stable anchor）后追加决策 #122（1 条，承载 RF-2 `__init_subclass__` 选项），6 条 advisory YELLOW 至 §12.5（CF-C-rev15-1..6）。**C-rev16** 闭合 C-rev15 reviewer round 7 条 inline RF（RF-1 time-box CF-C-rev15-5 per user adjudication / RF-2+RF-3 `Gate._subclasses` orphan assertion dual-filter / RF-4 §3.6 ABC docstring import-ordering & metadata accumulation forward-note / RF-5 `GATE_TIMEOUT_MS_HARD` location forward-marker / RF-6 derivation cross-link comment / RF-7 #122 vs #104 distinguisher），决策 #122 inline-amended（per #108 amend pattern），1 条 advisory at §12.6（CF-C-rev16-1）；C-rev15 Scope-5 fold 入 CF-C-rev15-5 不另起 entry。下一节 §7 Judge rubric 与 calibration。

## 7. Judge rubric 与 calibration

*（待 Round E 起草）*

## 8. PR-only deploy 契约

*（待 §7 approve 后填入）*

## 9. 隐私与脱敏 pipeline

*（待 §8 approve 后填入）*

## 10. 不变量

*（待 §9 approve 后填入）*

## 11. 非范围（out-of-scope，留给 M5+）

*（主体待 §10 approve 后起草。C-rev14 / C-Adv-3：以下 §6 已隐式声明 M5+ 内容必须在本节最终化时显式列入，避免 §11 起草时漏项）*

**TODO (Round H drafter cross-check list)**：

- Gate 4（语义保真 / SemanticFidelityGate，LLM-judge）+ gate 5（人审 / HumanReviewGate，async）—— 见 §6.6.1 forward-looking 注（B-Y12）
- 恶意 candidate 威胁模型 / adversarial sandbox（seccomp / network namespace / chroot）—— 见 §6.0 point 2 cooperative threat model 声明
- GEPA 驱动的动态阈值（runtime 调 `*_BPS` / `SKILL_LINE_HARD_CAP`）—— 见 §6.1.1 阈值 sourcing 段（决策 #111 spec-locked 哲学）
- NFS / 共享文件系统 workspace 支持 —— 见决策 #105 NFS unsupported 声明
- M5 gate-3 fail rate 实测 retro：若 ≥ 40% GEPA candidates fail gate-3，重新评估 1→2→3 顺序（见 §12.4 CF-C-rev13-4）
- `GateResult.metrics` 类型放宽至 `dict[str, float | str]`（决策 #114 / #116 forward-looking）— 仅在 M5 引入第三个 hash-shaped gate 后评估

## 12. Carry-forward debt

*（§6–§11 主体待后续 round 填入；本节 §12 register 格式 established by C-rev10 / 决策 #106）*

### 12.1 Register 格式约定（C-rev10 / 决策 #106）

`§12 carry-forward debt` 章节用于显式登记 reviewer 抓到、本轮**不 fix** 但**已意识到**的 finding。与 §0.3 决策表语义正交（决策表记的是"已采用的设计"，此处记的是"已知未关闭的 finding"）。每条 entry MUST 包含五个字段：

1. **Source**：抓到 finding 的 reviewer 名 + bucket-id（如 `Scope-W2`、`Coh-Y3`）
2. **Confidence**：reviewer 自报的 confidence 级别（"50%" / "advisory" / "high" 等定性或定量）
3. **Conflict**：与本轮其它 reviewer 判定的差异（如 "Arch-GREEN'd same round"、"Corr-RED but offset by Scope-LOW"）
4. **Defer reason**：为何本轮**不**升级到 must-fix（为 advisory / 零运行时成本 / 未达 YAGNI 阈值 / 等待真实 trigger 等）
5. **Future close criterion**：可观测的关闭条件（不是"等待 review again"这类自循环条件）

M5+ 启动 retro 时 MUST review §12 全部未关闭 entry；满足 close criterion 的从本节移除并在 retro 中记录关闭原因。**永不**因为"看起来不再相关"而**静默**删除 entry —— audit trail 与 §0.3 决策表同等严格。

### 12.2 C-rev10 user-sanctioned carry-forward entries

本批次 3 条 entry 均来自 C-rev10 4-reviewer 收敛中 Scope reviewer 提交的 advisory 观察，与 Arch reviewer 的 GREEN 判定冲突；用户在 close-out 时 sanctioned "Lite + carry-forward"，让 Arch GREEN 保留落地、Scope advisory 进 register 等待真实 trigger 验证。

#### CF-C-rev10-1 — `MUST_PRECEDE = {"RuntimeError"}` 三类异常的"未来不必要"风险（Scope-W2）

- **Source**: Scope reviewer / W2 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（决策 #95 amend 落地"RuntimeError-tree MUST_PRECEDE 通用规则"，§5.3 末尾点 7b）；Corr GREEN on Y-c7-corr-1 closure（W2 让 dispatch 表 + try/except 顺序在 CI 层 fail-loud）
- **Defer reason**: `MUST_PRECEDE = frozenset({"RuntimeError"})` 在三类异常（`EvolveEnvironmentError` / `JudgeError` / `ManifestPrivacyViolation`）上各自 ~1 LoC 声明，**零运行时成本**，由现有 `test_cli_handler_order_in_evolve_dispatch` infrastructure 自动机械化；保护**未来**贡献者添加 `except RuntimeError:` catch-all 时不会让三类的 exit code 语义被静默截胡。属 defense-in-depth 性质 advisory，未达"必须删"YAGNI 阈值
- **Future close criterion**: 若 M5 dispatch 表实现稳定后（≥ 3 milestone window）demonstrably 未引入任何 `except RuntimeError:` clause **AND** 没有其它 evolve sibling exception 需要相同 base-type 优先级 ordering，可在 M8+ retro 复评是否删除三处声明（保留 `ApplyTerminalError.MUST_PRECEDE = {"ValueError","ConfigError"}` —— 该声明有真实 isinstance 子类化关系驱动）

#### CF-C-rev10-2 — `EvolveError.__init_subclass__` runtime backstop 复杂度（Scope-W3）

- **Source**: Scope reviewer / W3 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（well-factored mixin，identity-tag role 已有外部 CI/telemetry 消费者 —— `isinstance(exc, nanobot.evolve.EvolveError)` 在 §5.4.6 line 2553 documented）
- **Defer reason**: identity-tag role（`EvolveError` mixin 作为 `isinstance` 锚点）单独已经足够 justify `EvolveError` 进 `__all__`；`__init_subclass__` runtime backstop 在此基础上**多花 ~20 LoC** 提供 import-time defense-in-depth，截获 AST 不可解析的 `cls_ref = self.exc_cls; raise cls_ref(...)` 两步 indirection。Scope 视角认为 W3 W10 均 forward-looking guard，contract 重叠（AST + runtime 双层守卫覆盖同一漂移窗口）。属 advisory，**未上升为 must-fix** 因 W3 backstop 已落地（C-rev9）+ 决策 #104 (C-rev10) 已让其更严格（subclass redeclaration enforcement）—— 删除会让 Corr-2 closure 同时回退
- **Future close criterion**: 若 M5+ 累计 ≥ 3 个 milestone 内（Round-by-round 计），无任何 contributor 写出 AST-evading raise 模式（`cls_ref = ...; raise cls_ref(...)` / `raise getattr(self, "exc_cls")(...)` 等），且 CI 历史未触发过 `__init_subclass__` 的 `TypeError`，可在 M8+ retro 复评是否把 `EvolveError` 降级为纯 marker mixin（保留 identity-tag role + `__all__` 锚点，删 backstop 逻辑），同时确保 `_discover_structured_kwargs` 的 AST 静态扫描覆盖率不下降

#### CF-C-rev10-3 — `test_must_precede_acyclic` 在 M4 结构性不可 fail（Scope-W10）

- **Source**: Scope reviewer / W10 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（narrowly bounded forward-looking，§5.3 点 7 已显式标记"M5+ 触发"+ 明确 named trigger 是 `GateRejected` / `JudgeQuorumFailure` 引入 evolve-internal MUST_PRECEDE edges）
- **Defer reason**: `test_must_precede_acyclic` 成本 ~12 LoC + 模块加载期亚毫秒级 DFS；M5 plan 已确认即将引入 `GateRejected` / `JudgeQuorumFailure` 等结构化异常，届时 evolve-internal 多节点 `MUST_PRECEDE` 图将出现真实环风险（如 `JudgeQuorumFailure.MUST_PRECEDE ⊇ {"JudgeError"}`）。Scope 视角认为 M4 阶段保留是 forward-looking 留置；C-rev10 / Corr-7 已 follow-up 加 sibling positive-coverage test (`test_must_precede_acyclic_detects_cycle`) 让 DFS 实现本身被 fixture 走过，部分缓解"留 untested logic 到 M5"的顾虑
- **Future close criterion**: 若 M5 ships **未** 引入任何 evolve-internal `MUST_PRECEDE` edge（即所有新结构化异常的 `MUST_PRECEDE` 仍仅指向 stdlib base type，与 M4 现状同质），可在 M5 retro 中评估是否删除 `test_must_precede_acyclic`（保留 sibling `test_must_precede_acyclic_detects_cycle` 作为 regression guard）；若 M5 真引入 evolve-internal edges，本 entry 自动闭合 —— forward-looking 假设 met

### 12.3 C-rev11 user-sanctioned carry-forward entries

本批次 2 条 entry 来自 C-rev11 4-reviewer 收敛中 Scope reviewer 提交的 advisory 观察，与 Arch reviewer 的 GREEN 判定冲突；用户在 close-out 时延续 C-rev10 sanctioned 路线（"Lite + carry-forward"），让 Arch GREEN 保留落地、Scope advisory 进 register 等待真实 trigger 验证。

#### CF-C-rev11-1 — §12 register trajectory close criterion（Scope-W*）

- **Source**: Scope reviewer / C-rev10 round（C-rev11 收敛期 carry forward），advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd C-rev10 round on §12 register at 3 entries（format established by 决策 #106；register 格式 right-sized）；C-rev11 后总 entry 数升至 5（CF-C-rev10-1/2/3 + CF-C-rev11-1/2），仍在可读阈值内。Scope 顾虑是**轨迹**而非现状 —— 若每轮稳态新增 ≥ 2 条且无关闭，§12 将在 M5 / M6 内走向"deferred-decision accumulation" 而非"transparent debt acknowledgment"
- **Defer reason**: 当前 5 条 entry 远未达可读阈值；§12 review 协议（M5+ 启动 retro MUST review 全量未关闭 entry）已嵌在 §12.1 / 决策 #106 文本中，触发机制天然存在。把"轨迹治理"提前到 M4 收敛期会让 spec workflow 增一层无 trigger 的元规则；按"YAGNI 直到真实拥塞"原则延后
- **Future close criterion**: 任一情形触发评估：(a) §12 累计 ≥ 10 条**未关闭** entry（hard threshold），(b) M5 retro 发现 §12 已成"deferred-decision accumulation"性质（即 entry 描述的是"想做但还没决定怎么做"而非"已决定不做但保留 trigger"）。届时评估两路选项：(i) 把 §12 抽离为独立 tracking 文件 `docs/hermes-evolution/carry-forward-debt.md`（spec 内仅留 cross-link）、(ii) 迁移至 GitHub Issues 用 `carry-forward` label 管理（让 PR review 与 issue tracking 重合）。两路保留 audit trail 不删除 entries

#### CF-C-rev11-2 — `_FakeCyclicException` 层叠 scaffolding（Scope-Corr-7）

- **Source**: Scope reviewer / C-rev10 round（C-rev11 收敛期 carry forward），advisory 观察
- **Confidence**: 50%
- **Conflict**: Corr-GREEN'd C-rev10 round（C-rev10 / Corr-7 / 决策 #99 amend，sibling test `test_must_precede_acyclic_detects_cycle` 让 DFS 实现自身被 fixture 走过，闭合"untested logic 留到 M5 才暴露"窗口）。Scope 视角认为 fixture-on-fixture 模式（fake exception class 模拟生产 registry 形态）若被未来轮次重复使用 → spec 测试结构 fragility 上升
- **Defer reason**: ~6 LoC fixture cost 是 genuinely trivial；sibling test 给一段否则在 M4 阶段不会被任何 codepath 走过的 DFS 实现提供 positive coverage，单独看是清晰收益。仅当本"layered scaffolding"模式被未来轮次反复使用（即多个 forward-looking test 都需注入 deliberately-broken fixture 来给"M5+ 才会真触发"的 helper 提供 coverage）时才上升为 systemic concern；当前是单点
- **Future close criterion**: 若 M5 milestone 完成时 `test_must_precede_acyclic` 自身未 fire 过任何一次（即 M5 未引入任何 evolve-internal `MUST_PRECEDE` edge → 多节点环不可能），评估同时删除 `test_must_precede_acyclic` AND `test_must_precede_acyclic_detects_cycle`，把"环检测"留待 M5+ 真实引入第一条 evolve-internal edge 时再补（届时直接给 production registry 写实测，而非走 fake fixture）。若 M5 引入了 edge → 两 test 自动转为有效 regression guard，本 entry 闭合

### 12.4 C-rev13 user-sanctioned carry-forward entries (C-rev14 round close-out)

本批次 4 条 entry 均来自 C-rev13 §6 起草后 4-reviewer Round D 中 50% confidence advisory 观察；C-rev14 fix pass 中按用户 pre-sanctioned 路线（"全部修复，多轮直到没有 red/yellow；advisory YELLOW (50% confidence) 可走 sanctioned carry-forward 至 §12 per established C-rev10/11 precedent"）保留为 register entries，等待真实 trigger 验证后再决定关闭或上升为 must-fix。

#### CF-C-rev13-1 — 决策 #114 schema 边界承认 vs schema 实际放宽（Scope-route）

- **Source**: Scope-route at 75% conviction (Round D)，consolidated with Arch-Y3 + Coh-banner observation —— 已在 C-rev14 升级为 must-fix 并由决策 #116 / B-Y6 闭合（新增 `evidence: dict[str, str] | None` sibling）
- **Confidence**: N/A（已闭合，本条仅作为 audit trail 保留 round trace）
- **Status**: **CLOSED in C-rev14**（决策 #116 落地；§3.6 schema 新增 sibling 字段；§6.3.3 改用 `evidence` 字段；决策 #114 加 `[SUPERSEDED-IN-PART-BY #116]` marker）。本 entry 保留为关闭轨迹，下一次 milestone retro 可移除
- **Future close criterion**: N/A（已闭合）

#### CF-C-rev13-2 — `rejection_subtype` 预设 prescriptive narrowing（Scope-50%）

- **Source**: Scope reviewer / Round D advisory 观察（C-Adv-1）
- **Confidence**: 50%
- **Conflict**: Coh / Corr / Arch GREEN on §6.6.1 既有 forward-looking 形态；Scope 顾虑是 §6.6.1 point 4 在 C-rev13 草稿中"M5 加诊断字段 `rejection_subtype`，**不**扩 enum"是对 M5 实现路径的过度规定（prescriptive over-reach）—— M5 design space 应只锁住"enum 不删 / 不 rename"的对外约束，不规定如何承载新语义
- **Defer reason**: C-rev14 已在 §6.6.1 point 4 narrowing：去除"加诊断字段 `rejection_subtype`"的 prescriptive language，仅保留"enum 不删 / 不 rename + 允许新增"硬约束，并显式声明 M5 自由 design space（`rejection_subtype` 诊断字段、新 final_status 值、其他 schema 扩展均为 M5 自由）。本 entry **partially closed**（prescriptive language 已删），但保留 carry-forward 作为 M5 retro 验证 anchor —— M5 实施 gate-4 / gate-5 时是否真按 §6.6.1 抽象约束实现，还是会发现需要进一步 carve-out（如 final_status 新值导致下游 report.md template 跨章节级联改动）
- **Future close criterion**: M5 retro 中 review §6.6.1 point 4，确认 (a) 既有 4 enum 值未被 remove / rename，**且** (b) M5 实际选用的语义承载方案（无论 `rejection_subtype` / 新 enum 值 / 其他）不被 §6.6.1 文本暗示 over-narrow。若 (a) 成立而 (b) 触发了 §6.6.1 文本调整，本 entry 关闭并在 M5 retro 记录调整原因

#### CF-C-rev13-3 — GEPA fitness-signal 顺序理由依赖 multi-round GEPA 实操（Scope-50%）

- **Source**: Scope reviewer / Round D advisory 观察（C-Adv-2）
- **Confidence**: 50%
- **Conflict**: Coh / Arch GREEN on §6.4.1 既有 1→2→3 ordering rationale（决策 #109）；Scope 顾虑是 GEPA fitness-signal 完整性的核心 justification（"GEPA 优化器需要在 reject 候选上拿到完整 fitness signal"）若 M4 实际只 ship 单轮 / stub-level GEPA（DSPy `BootstrapFewShot` 或类似 1-shot 形态），多轮 mutation 学习的论证会弱化 → ordering rationale 部分悬空
- **Defer reason**: M4 GEPA 实际形态目前规划为 multi-round（DSPy 默认 ≥ 8 iter × ≤ 8 candidates），但 implementation phase 可能因 dependency / scope 压力降级为 single-shot baseline。即便 GEPA 降级为 1-shot，§6.4.1 点 (b) 的 "report.md reviewer 拿 `gate-rejected-at: 3-cache-compat` 时同时看 test_rate / size_delta 上下文" 人审可观测性论证仍成立，ordering rationale 不全部悬空。Scope 视角的弱化是局部而非全部；按 advisory 处理
- **Future close criterion**: M4 收尾 retro 验证 GEPA 实际是否 ships multi-round。若 ships multi-round → 本 entry 自动闭合（核心 fitness-signal justification 兑现）。若降级为 single-shot → 在 M4 retro 中 amend §6.4.1 ordering rationale，把 "GEPA fitness signal" 论证降级为 "human-reviewer observability + GEPA forward-compatibility" 双论证，并新增决策记 amend；本 entry 关闭

#### CF-C-rev13-4 — Gate ordering 1→2→3 vs 3→1→2 wall-clock retro（Arch-Y6）

- **Source**: Arch reviewer / Round D / Y6 bucket（advisory observation；50% confidence）
- **Confidence**: 50%
- **Conflict**: Coh / Corr / Scope GREEN on 决策 #109 既有 1→2→3 ordering（metrics 完整性优先 over wall-clock）；Arch-Y6 顾虑是"gate-3 fails for free（O(1) hash compare），花 gate-1 数分钟 subprocess 时间在 cache-broken candidates 上是浪费"在 §6.4.1 既有 trade-off 分析中未被显式承认 —— 论证只覆盖了 metrics 完整性但未列出 wall-clock 浪费的具体量级
- **Defer reason**: 决策 #109 既有 trade-off 分析在质性层面覆盖了 wall-clock cost（§6.4.3 GEPA-layer early termination 部分缓解），但未给定量数据 —— 实际 GEPA candidate 中 cache-key-broken 比例需 M5 实测才知。若实测 ≥ 40% candidates fail gate-3，"花 gate-1 时间在必然 reject 的 candidate 上"成本显著，可能 outweigh metrics 完整性收益；若 ≤ 5%，cost 可忽略。M4 阶段无实测数据 → 按 advisory 保留 trade-off 决策不变
- **Future close criterion**: M5 retro 检视 M4 完整 run 的 gate-3 fail rate。若 ≥ 40% → re-evaluate ordering 至 3→1→2（即 cheap-first），即便牺牲部分 partial-test-metrics 给 GEPA；同步新增 M5 决策 amend 决策 #109，把 ordering 改为 conditional（基于实测 fail rate）。若 < 40% → 本 entry 闭合，决策 #109 ordering 保留。Decision close criterion 是可观测的实测百分比阈值，非自循环

### 12.5 C-rev14 user-sanctioned carry-forward entries (C-rev15 round close-out)

本批次 6 条 entry 来自 C-rev14 §6 reviewer round 中 50–55% confidence advisory 观察。C-rev15 fix pass 中按 C-rev10/11/13 sanctioned 路线（"全部修复，多轮直到没有 red/yellow；advisory YELLOW (50–55% confidence) 走 sanctioned carry-forward 至 §12 per established precedent"）保留为 register entries，等待真实 trigger 验证后再决定关闭或上升为 must-fix。**本批次触发 CF-C-rev11-1 hard threshold**（§12 register 累计未关闭 entry 数：12.2 (3) + 12.3 (2) + 12.4 (3 active；CF-C-rev13-1 已 CLOSED) + 12.5 (6) ≈ 14，跨过 ≥10 评估线），见 CF-C-rev15-5。

#### CF-C-rev15-1 — 决策 #117 forward-looking semantics gap（cluster: A-Y1 + C-Y5 + Scope-Y1）

- **Source**: C-rev14 reviewer round / Arch-Y1 + Corr-Y5 + Scope-Y1（cluster collapse；3 reviewer 同源观察）
- **Confidence**: 50%
- **Conflict**: §6.0 point 1 + 决策 #117 GREEN-on-form（ClassVar opt-out 形态对齐 #95 `STRUCTURED_KWARGS`）；advisory 顾虑是 forward-looking 实施细节 —— (i) discovery semantics 未声明（`getattr(gate, "NONDETERMINISTIC")` MRO inheritance vs `cls.__dict__.get("NONDETERMINISTIC")` strict-own），spec 未文档化 inheritance-via-MRO 是 intended（默认 `False` 经 MRO 继承到子类，与 STRUCTURED_KWARGS strict-own registry 语义有意区分）；(ii) double-run assertion 推迟到 §10 不变量章节，C-rev15 期 `NONDETERMINISTIC` ClassVar 仍是纯 declarative（无运行时消费者）；(iii) §10 stub 当前未交叉引用决策 #117，drafter 起草时漏 conditional `NONDETERMINISTIC=False` guard 风险存在
- **Defer reason**: 三个 sub-finding 均为 forward-looking 实施细节，须在 §10 实际起草（Round H）时解决；C-rev15 round 是 §6 fix pass，§10 仍 stub 未起草，提前规定 §10 内部结构是 over-prescriptive。M4 落地时 `NONDETERMINISTIC=False` 默认值在三 gate 全继承（无 override），无 active 行为分歧
- **Future close criterion**: §10 (Round H) drafter MUST 满足三条全部：(a) 显式引用决策 #117 与 inheritance-via-MRO discovery 形式（推荐 `getattr` w/ default `False`）；(b) 编码 harness 双跑等价 assert 的 conditional `if not gate.NONDETERMINISTIC:` guard；(c) 与 STRUCTURED_KWARGS / MUST_PRECEDE registry 语义对比释明（避免新贡献者误解为同质 strict-own registry）。三条任一缺失 → 本 CF reopen 为 RED，需在 §10 round 内闭合

#### CF-C-rev15-2 — 决策 #117 × GEPA fitness-signal 交互未规定（A-Y2）

- **Source**: C-rev14 reviewer round / Arch-Y2
- **Confidence**: 50%
- **Conflict**: §6.0 point 1 GREEN on `NONDETERMINISTIC=True` opt-out 路径；advisory 顾虑是当 M5 gate 4 (`SemanticFidelityGate` LLM-judge) 引入 `NONDETERMINISTIC=True` 时，gate 的 `metrics: dict[str, float]` 可能携带 noisy / 跨调用 unreproducible 的浮点值（如 LLM judge score 受 sampling 抖动影响）。GEPA fitness aggregation 若直接消费这些 metrics → 单候选跨 GEPA round 的 fitness 时序信号被 LLM 噪声污染，优化方向漂移。C-rev15 spec 未声明 nondeterministic gate metrics 是否参与 fitness aggregation
- **Defer reason**: M4 三 gate 全部 `NONDETERMINISTIC=False`，M4 范围内 fitness aggregation 不会触及该 case；属 M5 gate 4 落地时的 design space。提前在 M4 spec 锁定"nondeterministic metrics 是否参与 fitness"会过度规定 M5 调和方案（averaging / seeded / 独立通道等多个候选，需实测 LLM judge 噪声分布后再选）
- **Future close criterion**: M5 gate 4 spec 起草（`m5-darwinian-evolver.md` §gate-4 章节）MUST 显式 carve-out `NONDETERMINISTIC=True` gate metrics 的 fitness aggregation 政策。默认 proposal：从 GEPA fitness aggregation **排除** `NONDETERMINISTIC=True` 的 gate metrics（仅作为 audit / report-only 信号）；若选择**包含**则 MUST 指定 averaging / seeding / variance-bounding 策略并跨链 CF-C-rev13-3（GEPA fitness-signal 顺序理由）。两路任一落地，本 CF 关闭

#### CF-C-rev15-3 — Gate ABC budget-check 义务在 ABC 外文档化（A-Y3）

- **Source**: C-rev14 reviewer round / Arch-Y3
- **Confidence**: 50%
- **Conflict**: §6.0 point 5 GREEN on hard timeout SoT 重定义（决策 #121）；advisory 顾虑是 §3.6 `Gate` ABC docstring（line ~830 `"同步评估；不允许调网络"`）只描述 sync + offline 两条，不提 `GATE_TIMEOUT_MS_HARD` budget-check 义务。Hard-timeout SoT 实际生活在 §6.0 point 5 散文中 —— 抽象层泄漏：M5 LLM-judge gate 4 实现者必须读 §6.0 prose 才能发现 budget-check 责任，单看 ABC 签名 / docstring 无法推导
- **Defer reason**: M4 仅 1 个 long-running gate（gate 1），budget-check 义务在 §6.1.2 主体已显式编码 + §6.0 point 5 跨 gate 公约描述清楚。M5 gate 4 是真实 trigger（首个新 long-running gate），届时再决定是否将义务上提到 ABC 形态。提前 over-engineering 风险：(i) 在 ABC 加 docstring 段易被忽略；(ii) 引入 `LONG_RUNNING: ClassVar[bool]` 多此一举（gate 2/3 是 O(1) 已天然不需 budget-check）；(iii) cross-ref 形态 vs ClassVar 形态选择本身有 trade-off，需结合 M5 实际经验决策
- **Future close criterion**: 至 M5 spec-writing（gate 4 章节起草）或更早，三选一闭合：(a) 在 §3.6 `Gate.evaluate` docstring 加一行 "若 gate 是 long-running，MUST 在每条 record 后 budget-check `GATE_TIMEOUT_MS_HARD`，跨 §6.0 point 5"；(b) 引入 `LONG_RUNNING: ClassVar[bool] = False` 形态（同决策 #117 `NONDETERMINISTIC` 形）+ harness `_run_gates` 在 invoke 前 conditional 注入 `gate_start = time.perf_counter()` 的协议；(c) 加一行 §3.6 → §6.0 point 5 cross-ref。三条任一落地本 CF 关闭；advisory 不阻塞 M4 实现

#### CF-C-rev15-4 — 决策 #115 self-application + #115/#121 own-cell overage（cluster: A-Y4-a + Coh-Y1）

- **Source**: C-rev14 reviewer round / Arch-Y4-a + Coh-Y1（cluster collapse；同源观察）
- **Confidence**: 50%
- **Conflict**: §0.3.1 sub-rule 4（决策 #115）GREEN on form （度量 SoT 单一化）；advisory 顾虑是 (i) "≤ 8 逻辑单元 + 1500-char 硬上限" 是 spec 文本约定，无 CI lint 强制 —— `scripts/lint_decision_log.py` 不存在，rule 静默漂移风险存在；(ii) 决策 #115 自身 rationale 按 alternative-block 边界严格切分约 9 单元（超过它定义的 8 单元 cap by 1）；决策 #121 rationale 长度 ≥ 1500 chars 临界。两条决策都是 *规则定义自身* 与规则冲突
- **Defer reason**: rule 定义本身的 self-application 是程序化合规问题，不影响读者对决策内容的理解（决策 #115 / #121 文本含义清晰）；提前在 C-rev15 强制 grandfather marker 或 lint 脚本会让 §0.3 改写量超出 RF 三条修复 scope。属 advisory governance hygiene
- **Future close criterion**: 至下一次决策日志 grooming round（或 M5 spec start retro），二选一闭合：(i) 落地 `scripts/lint_decision_log.py` 作为 M5 in-scope 任务（CI 上 enforce ≤8 单元 + ≤1500 char）；(ii) 在决策 #115 / #121 标题行追加 `[GRANDFATHERED PRE-RULE-FINALIZATION]` marker（保留 audit 可见）。任一落地本 CF 关闭

#### CF-C-rev15-5 — §12 register threshold trip + sub-section proliferation（cluster: A-Y4-b + Scope-Y2 + CF-C-rev11-1 trigger；C-rev16 / RF-1 time-boxed per user adjudication）

- **Source**: C-rev14 reviewer round / Arch-Y4-b + Scope-Y2（cluster collapse；同时是 CF-C-rev11-1 hard threshold trip）。**Responding to**（C-rev16 fold-in）：C-rev15 Scope-5（§12 proliferation self-aware-but-non-executing pattern）—— 本 entry 自身是 CF-C-rev11-1 hard-threshold 触发的 register entry，再以 §12 entry 形态承接 close-path 即"自我感知但不执行"governance recursion 的具体形态；fold 入本条而**不**另起 §12.6 entry，使该 pattern 一并受 RF-1 hard deadline 约束
- **Confidence**: 50%
- **Conflict**: §12.1 / 决策 #106 GREEN on register format；CF-C-rev11-1 已声明 ≥10 未关闭 entry 是 hard threshold；C-rev15 后实际计数：§12.2 (3) + §12.3 (2) + §12.4 (3 active；CF-C-rev13-1 已 CLOSED) + §12.5 (6) ≈ **14 未关闭 entry**（含本 CF 自身），跨过阈值。同时 sub-section 形态（§12.2 / 12.3 / 12.4 / 12.5 per-round）对决策 #106 强制的 `Source` 字段（已承载轮次 chronology）冗余，导航开销上升。**Governance recursion finding**（C-rev15 Arch-1 FIX）：将 CF-C-rev11-1 的 hard-threshold 触发再登记成新 §12 register entry（且该 entry 自身 count 入 threshold），构成 close-path 的延迟通道 —— meta-rule 的 hard-threshold 构造原意是 force close-path execution，再 defer 即 debt-evasion
- **Defer reason**: C-rev15 是 §6 fix pass，scope 仅限 RF-1/2/3 + CF 登记。§12 整章重组（CF-C-rev11-1 闭合方案）属 spec 结构化重排，会跨章节大量 churn，不应在 C-rev15 round 内执行；同时也是 CF-C-rev11-1 自身的 future close criterion 触发。**deferral 在 RF-1 hard deadline 处终止**（不 open-ended），见下条
- **Future close criterion** **[AMENDED-INLINE C-rev16 / RF-1 / user adjudication 2026-06-12, Arch path-b time-box]**: MUST 执行 CF-C-rev11-1 close-path **(a)** 抽离 `docs/hermes-evolution/specs/m4-carry-forward.md` 独立 tracking 文件 —— 按 chronological list（保留 Source 字段承载轮次归属），spec 内仅留 cross-link 占位 §12，废弃 per-round sub-sections；**OR** close-path **(b)** 迁移 active CFs 至 GitHub Issues（labels: `m4` / `carry-forward` / `confidence-50`），spec 内 §12 仅保留 closed entry audit trail 与 link template。**Hard deadline**：在 **C-rev17 4-reviewer 收敛 PASS** **OR** **§10（Round H）4-reviewer 收敛 PASS** 二者**先到者**之前必须执行 close-path —— 不允许再 defer。本 CF entry 的存在已经代表 governance recursion 可接受的最大深度（user adjudication 2026-06-12, Arch path-b "time-box deadline preserves meta-rule integrity via hard deadline"）。逾期未执行 ⇒ 下一轮 reviewer 自动将本 CF promote 至 RED。任一 close-path 落地后本 CF + CF-C-rev11-1 共同闭合，同时 CF-C-rev16-1（CF-C-rev15-1 trigger 软度）依附于此 deadline 一并 housekeep

#### CF-C-rev15-6 — SIGINT → exit 130 mapping ambiguity（C-Y4）

- **Source**: C-rev14 reviewer round / Corr-Y4
- **Confidence**: 55%
- **Conflict**: §4.6 dispatch table 当前**无** KeyboardInterrupt / exit 130 行；§5.3 line ~1772 表达 "SIGINT 不映射到固定 exit code"；§6.0 point 3 line ~2872 表达 "CLI handler 转 SIGINT/exit 130 / 标准退出语义"。两处 phrasing 留下两种合理读法：(i) harness 不显式 map，让 Python interpreter SIGINT 默认 handler 透传产生 130；(ii) CLI handler 显式 map exit 130。实现者分歧风险存在
- **Defer reason**: M4 单元测试与 §6.0 point 3 traceback 落库路径已定义，KeyboardInterrupt 在 `_run_gates` 内不被 swallow（透传至 harness top-level）这一点 §6.0 point 3 已锁；上层 mapping ambiguity 仅影响 CLI 表面 exit code 一致性，不影响 gate / harness 数据完整性。属 §4-§5 dispatch 章节的小 cleanup，留待下一次 §4-§5 fix round 一并处理更高效
- **Future close criterion**: 下一次 §4-§5 fix round（Round F 或更晚），二选一闭合：(a) §4.6 dispatch 表追加行 `130 | KeyboardInterrupt 透传 / SIGINT 默认行为 | 用户 Ctrl-C | 是` + §10 不变量章节为 KeyboardInterrupt 添加 carve-out（不参与"任何异常都被 dispatch 表覆盖"普遍量化）；(b) 改写 §6.0 point 3 句式为 "CLI handler 让 KeyboardInterrupt 透传至 Python 默认 SIGINT 处理（exit 130 由 interpreter 默认提供，harness 不显式 map）"。任一落地本 CF 关闭；不允许 M4 ship 仍同时存在两 phrasings

### 12.6 C-rev15 user-sanctioned carry-forward entries (C-rev16 round close-out)

本批次 1 条 entry 来自 C-rev15 §6 reviewer round 中 50% confidence advisory 观察。C-rev16 fix-round 中按 C-rev10/11/13/15 sanctioned 路线保留为 register entry，等待真实 trigger 验证后再决定关闭或上升为 must-fix。**注**：C-rev15 reviewer round 的 RF-grade headline finding（governance recursion / Arch-1 FIX）经 user adjudication 2026-06-12 决定走 Arch path-b time-box（不另起 entry，inline-amend CF-C-rev15-5 close criterion + hard deadline，见 §12.5 RF-1 amendment）；C-rev15 Scope-5（§12 proliferation self-aware-but-non-executing pattern）已 fold 入 CF-C-rev15-5 body 作为 "Responding to" 交叉链接，不另起 entry。本批次仅 CF-C-rev16-1 一条新 entry。

#### CF-C-rev16-1 — CF-C-rev15-1 "Round H" trigger 软度（Scope-3）

- **Source**: C-rev15 reviewer round / Scope reviewer focus area 6（advisory 50%）
- **Confidence**: 50%
- **Conflict**: CF-C-rev15-1 的 "Future close criterion" 引用 "§10（Round H）drafter MUST 满足三条全部" —— "Round H" 是内部 orchestration phase 标签，若 CF 跨 M4 ship 仍未关闭，phase 标签会失去稳定语义。§10 章节引用本身稳定，但 trigger noun（"drafter"）是 round-specific 的瞬态语义
- **Defer reason**: 现在处理需要再触动 CF-C-rev15-1，而 CF-C-rev15-1 自身已被 RF-1 hard deadline（C-rev17 4-reviewer 收敛 PASS OR §10 Round H 4-reviewer 收敛 PASS 二者先到者）兜底；trigger 语言收紧自然 fold 入 RF-1 mandate 的同一 housekeeping pass，分开做属重复 churn
- **Future close criterion**: 当 CF-C-rev15-5 的 hard deadline 触发（C-rev17 OR §10 Round H 4-reviewer PASS），CF-C-rev15-1 的 trigger 语言 MUST 在同一 housekeeping pass 中由 "Round H drafter" 改写为 "§10 4-reviewer 收敛 PASS"（消除 phase-label 依赖）。本 CF 与 CF-C-rev15-5 共同闭合

## 13. 决策日志

*（合并至 §0.3，body 完工时回填全部新决策）*

## 14. 下游契约（to M5）

*（待 §13 approve 后填入）*
