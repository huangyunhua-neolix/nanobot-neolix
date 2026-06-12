# M4 · Carry-forward debt register（sibling file）

> **Scope**：本文件是 [`m4-offline-skeleton.md`](./m4-offline-skeleton.md) §12 章节的物理延伸 —— 自 C-rev18 起，per CF-C-rev15-5 hard-deadline **close-path (a)**，§12 全部内容（active + closed entries）由 M4 spec 抽离至本文件；M4 spec §12 退化为 3-line 稳定指针。Close-path (a) 在 C-rev18 由 user 执行；触发条件为 CF-C-rev15-5 / RF-1（C-rev16 amend）规定的 "C-rev17 4-reviewer 收敛 PASS **OR** §10（Round H）4-reviewer 收敛 PASS 二者**先到者**之前必须执行"，C-rev17 fix-round close-out 即触发该 deadline 的先到分支。
>
> **Lifecycle 约定**：
>
> 1. 每条 CF entry 按其自身的 **Future close criterion** 关闭 —— 满足 criterion 后在 entry header 追加 `[CLOSED C-rev<N>]` marker，body 保留作为 audit trail；**永不**静默删除。
> 2. C-rev18 及之后产生的**新** CF entry 直接登记到本文件（不再回到 M4 spec），并继续按 CF-C-rev11-1 的 hard threshold（≥10 未关闭 entry）计数；新批次以 `### CF-C-rev<N> user-sanctioned carry-forward entries` 节标题追加，保留 chronological 列表组织（不再用 per-round sub-sections，与 close-path (a) 抽离 intent 一致）。
> 3. M5+ milestone retro 启动时 MUST review 本文件全部未关闭 entry；满足 close criterion 的依规则 1 标记 CLOSED 并在 retro doc 中记录关闭事件。
> 4. 本文件与 [`m4-offline-skeleton.md`](./m4-offline-skeleton.md) §0.3 决策表语义正交：决策表记"已采用的设计"，本文件记"已知未关闭的 finding"。

## 1. Register 格式约定（C-rev10 / 决策 #106）

`carry-forward debt` register 用于显式登记 reviewer 抓到、本轮**不 fix** 但**已意识到**的 finding。与 §0.3 决策表语义正交（决策表记的是"已采用的设计"，此处记的是"已知未关闭的 finding"）。每条 entry MUST 包含五个字段：

1. **Source**：抓到 finding 的 reviewer 名 + bucket-id（如 `Scope-W2`、`Coh-Y3`）
2. **Confidence**：reviewer 自报的 confidence 级别（"50%" / "advisory" / "high" 等定性或定量）
3. **Conflict**：与本轮其它 reviewer 判定的差异（如 "Arch-GREEN'd same round"、"Corr-RED but offset by Scope-LOW"）
4. **Defer reason**：为何本轮**不**升级到 must-fix（为 advisory / 零运行时成本 / 未达 YAGNI 阈值 / 等待真实 trigger 等）
5. **Future close criterion**：可观测的关闭条件（不是"等待 review again"这类自循环条件）

M5+ 启动 retro 时 MUST review 本文件全部未关闭 entry；满足 close criterion 的依本文件 Lifecycle 规则 1 标记 CLOSED 并在 retro 中记录关闭原因。**永不**因为"看起来不再相关"而**静默**删除 entry —— audit trail 与 §0.3 决策表同等严格。

## 2. C-rev10 user-sanctioned carry-forward entries

本批次 3 条 entry 均来自 C-rev10 4-reviewer 收敛中 Scope reviewer 提交的 advisory 观察，与 Arch reviewer 的 GREEN 判定冲突；用户在 close-out 时 sanctioned "Lite + carry-forward"，让 Arch GREEN 保留落地、Scope advisory 进 register 等待真实 trigger 验证。

### CF-C-rev10-1 — `MUST_PRECEDE = {"RuntimeError"}` 三类异常的"未来不必要"风险（Scope-W2）

- **Source**: Scope reviewer / W2 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（决策 #95 amend 落地"RuntimeError-tree MUST_PRECEDE 通用规则"，§5.3 末尾点 7b）；Corr GREEN on Y-c7-corr-1 closure（W2 让 dispatch 表 + try/except 顺序在 CI 层 fail-loud）
- **Defer reason**: `MUST_PRECEDE = frozenset({"RuntimeError"})` 在三类异常（`EvolveEnvironmentError` / `JudgeError` / `ManifestPrivacyViolation`）上各自 ~1 LoC 声明，**零运行时成本**，由现有 `test_cli_handler_order_in_evolve_dispatch` infrastructure 自动机械化；保护**未来**贡献者添加 `except RuntimeError:` catch-all 时不会让三类的 exit code 语义被静默截胡。属 defense-in-depth 性质 advisory，未达"必须删"YAGNI 阈值
- **Future close criterion**: 若 M5 dispatch 表实现稳定后（≥ 3 milestone window）demonstrably 未引入任何 `except RuntimeError:` clause **AND** 没有其它 evolve sibling exception 需要相同 base-type 优先级 ordering，可在 M8+ retro 复评是否删除三处声明（保留 `ApplyTerminalError.MUST_PRECEDE = {"ValueError","ConfigError"}` —— 该声明有真实 isinstance 子类化关系驱动）

### CF-C-rev10-2 — `EvolveError.__init_subclass__` runtime backstop 复杂度（Scope-W3）

- **Source**: Scope reviewer / W3 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（well-factored mixin，identity-tag role 已有外部 CI/telemetry 消费者 —— `isinstance(exc, nanobot.evolve.EvolveError)` 在 §5.4.6 line 2553 documented）
- **Defer reason**: identity-tag role（`EvolveError` mixin 作为 `isinstance` 锚点）单独已经足够 justify `EvolveError` 进 `__all__`；`__init_subclass__` runtime backstop 在此基础上**多花 ~20 LoC** 提供 import-time defense-in-depth，截获 AST 不可解析的 `cls_ref = self.exc_cls; raise cls_ref(...)` 两步 indirection。Scope 视角认为 W3 W10 均 forward-looking guard，contract 重叠（AST + runtime 双层守卫覆盖同一漂移窗口）。属 advisory，**未上升为 must-fix** 因 W3 backstop 已落地（C-rev9）+ 决策 #104 (C-rev10) 已让其更严格（subclass redeclaration enforcement）—— 删除会让 Corr-2 closure 同时回退
- **Future close criterion**: 若 M5+ 累计 ≥ 3 个 milestone 内（Round-by-round 计），无任何 contributor 写出 AST-evading raise 模式（`cls_ref = ...; raise cls_ref(...)` / `raise getattr(self, "exc_cls")(...)` 等），且 CI 历史未触发过 `__init_subclass__` 的 `TypeError`，可在 M8+ retro 复评是否把 `EvolveError` 降级为纯 marker mixin（保留 identity-tag role + `__all__` 锚点，删 backstop 逻辑），同时确保 `_discover_structured_kwargs` 的 AST 静态扫描覆盖率不下降

### CF-C-rev10-3 — `test_must_precede_acyclic` 在 M4 结构性不可 fail（Scope-W10）

- **Source**: Scope reviewer / W10 bucket，advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd same round（narrowly bounded forward-looking，§5.3 点 7 已显式标记"M5+ 触发"+ 明确 named trigger 是 `GateRejected` / `JudgeQuorumFailure` 引入 evolve-internal MUST_PRECEDE edges）
- **Defer reason**: `test_must_precede_acyclic` 成本 ~12 LoC + 模块加载期亚毫秒级 DFS；M5 plan 已确认即将引入 `GateRejected` / `JudgeQuorumFailure` 等结构化异常，届时 evolve-internal 多节点 `MUST_PRECEDE` 图将出现真实环风险（如 `JudgeQuorumFailure.MUST_PRECEDE ⊇ {"JudgeError"}`）。Scope 视角认为 M4 阶段保留是 forward-looking 留置；C-rev10 / Corr-7 已 follow-up 加 sibling positive-coverage test (`test_must_precede_acyclic_detects_cycle`) 让 DFS 实现本身被 fixture 走过，部分缓解"留 untested logic 到 M5"的顾虑
- **Future close criterion**: 若 M5 ships **未** 引入任何 evolve-internal `MUST_PRECEDE` edge（即所有新结构化异常的 `MUST_PRECEDE` 仍仅指向 stdlib base type，与 M4 现状同质），可在 M5 retro 中评估是否删除 `test_must_precede_acyclic`（保留 sibling `test_must_precede_acyclic_detects_cycle` 作为 regression guard）；若 M5 真引入 evolve-internal edges，本 entry 自动闭合 —— forward-looking 假设 met

## 3. C-rev11 user-sanctioned carry-forward entries

本批次 2 条 entry 来自 C-rev11 4-reviewer 收敛中 Scope reviewer 提交的 advisory 观察，与 Arch reviewer 的 GREEN 判定冲突；用户在 close-out 时延续 C-rev10 sanctioned 路线（"Lite + carry-forward"），让 Arch GREEN 保留落地、Scope advisory 进 register 等待真实 trigger 验证。

### CF-C-rev11-1 — §12 register trajectory close criterion（Scope-W*）

- **Source**: Scope reviewer / C-rev10 round（C-rev11 收敛期 carry forward），advisory 观察
- **Confidence**: 50%
- **Conflict**: Arch-GREEN'd C-rev10 round on §12 register at 3 entries（format established by 决策 #106；register 格式 right-sized）；C-rev11 后总 entry 数升至 5（CF-C-rev10-1/2/3 + CF-C-rev11-1/2），仍在可读阈值内。Scope 顾虑是**轨迹**而非现状 —— 若每轮稳态新增 ≥ 2 条且无关闭，§12 将在 M5 / M6 内走向"deferred-decision accumulation" 而非"transparent debt acknowledgment"
- **Defer reason**: 当前 5 条 entry 远未达可读阈值；§12 review 协议（M5+ 启动 retro MUST review 全量未关闭 entry）已嵌在 §12.1 / 决策 #106 文本中，触发机制天然存在。把"轨迹治理"提前到 M4 收敛期会让 spec workflow 增一层无 trigger 的元规则；按"YAGNI 直到真实拥塞"原则延后
- **Future close criterion**: 任一情形触发评估：(a) §12 累计 ≥ 10 条**未关闭** entry（hard threshold），(b) M5 retro 发现 §12 已成"deferred-decision accumulation"性质（即 entry 描述的是"想做但还没决定怎么做"而非"已决定不做但保留 trigger"）。届时评估两路选项：(i) 把 §12 抽离为独立 tracking 文件 `docs/hermes-evolution/carry-forward-debt.md`（spec 内仅留 cross-link）、(ii) 迁移至 GitHub Issues 用 `carry-forward` label 管理（让 PR review 与 issue tracking 重合）。两路保留 audit trail 不删除 entries

### CF-C-rev11-2 — `_FakeCyclicException` 层叠 scaffolding（Scope-Corr-7）

- **Source**: Scope reviewer / C-rev10 round（C-rev11 收敛期 carry forward），advisory 观察
- **Confidence**: 50%
- **Conflict**: Corr-GREEN'd C-rev10 round（C-rev10 / Corr-7 / 决策 #99 amend，sibling test `test_must_precede_acyclic_detects_cycle` 让 DFS 实现自身被 fixture 走过，闭合"untested logic 留到 M5 才暴露"窗口）。Scope 视角认为 fixture-on-fixture 模式（fake exception class 模拟生产 registry 形态）若被未来轮次重复使用 → spec 测试结构 fragility 上升
- **Defer reason**: ~6 LoC fixture cost 是 genuinely trivial；sibling test 给一段否则在 M4 阶段不会被任何 codepath 走过的 DFS 实现提供 positive coverage，单独看是清晰收益。仅当本"layered scaffolding"模式被未来轮次反复使用（即多个 forward-looking test 都需注入 deliberately-broken fixture 来给"M5+ 才会真触发"的 helper 提供 coverage）时才上升为 systemic concern；当前是单点
- **Future close criterion**: 若 M5 milestone 完成时 `test_must_precede_acyclic` 自身未 fire 过任何一次（即 M5 未引入任何 evolve-internal `MUST_PRECEDE` edge → 多节点环不可能），评估同时删除 `test_must_precede_acyclic` AND `test_must_precede_acyclic_detects_cycle`，把"环检测"留待 M5+ 真实引入第一条 evolve-internal edge 时再补（届时直接给 production registry 写实测，而非走 fake fixture）。若 M5 引入了 edge → 两 test 自动转为有效 regression guard，本 entry 闭合

## 4. C-rev13 user-sanctioned carry-forward entries (C-rev14 round close-out)

本批次 4 条 entry 均来自 C-rev13 §6 起草后 4-reviewer Round D 中 50% confidence advisory 观察；C-rev14 fix pass 中按用户 pre-sanctioned 路线（"全部修复，多轮直到没有 red/yellow；advisory YELLOW (50% confidence) 可走 sanctioned carry-forward 至 §12 per established C-rev10/11 precedent"）保留为 register entries，等待真实 trigger 验证后再决定关闭或上升为 must-fix。

### CF-C-rev13-1 — 决策 #114 schema 边界承认 vs schema 实际放宽（Scope-route）

- **Source**: Scope-route at 75% conviction (Round D)，consolidated with Arch-Y3 + Coh-banner observation —— 已在 C-rev14 升级为 must-fix 并由决策 #116 / B-Y6 闭合（新增 `evidence: dict[str, str] | None` sibling）
- **Confidence**: N/A（已闭合，本条仅作为 audit trail 保留 round trace）
- **Status**: **CLOSED in C-rev14**（决策 #116 落地；§3.6 schema 新增 sibling 字段；§6.3.3 改用 `evidence` 字段；决策 #114 加 `[SUPERSEDED-IN-PART-BY #116]` marker）。本 entry 保留为关闭轨迹，下一次 milestone retro 可移除
- **Future close criterion**: N/A（已闭合）

### CF-C-rev13-2 — `rejection_subtype` 预设 prescriptive narrowing（Scope-50%）

- **Source**: Scope reviewer / Round D advisory 观察（C-Adv-1）
- **Confidence**: 50%
- **Conflict**: Coh / Corr / Arch GREEN on §6.6.1 既有 forward-looking 形态；Scope 顾虑是 §6.6.1 point 4 在 C-rev13 草稿中"M5 加诊断字段 `rejection_subtype`，**不**扩 enum"是对 M5 实现路径的过度规定（prescriptive over-reach）—— M5 design space 应只锁住"enum 不删 / 不 rename"的对外约束，不规定如何承载新语义
- **Defer reason**: C-rev14 已在 §6.6.1 point 4 narrowing：去除"加诊断字段 `rejection_subtype`"的 prescriptive language，仅保留"enum 不删 / 不 rename + 允许新增"硬约束，并显式声明 M5 自由 design space（`rejection_subtype` 诊断字段、新 final_status 值、其他 schema 扩展均为 M5 自由）。本 entry **partially closed**（prescriptive language 已删），但保留 carry-forward 作为 M5 retro 验证 anchor —— M5 实施 gate-4 / gate-5 时是否真按 §6.6.1 抽象约束实现，还是会发现需要进一步 carve-out（如 final_status 新值导致下游 report.md template 跨章节级联改动）
- **Future close criterion**: M5 retro 中 review §6.6.1 point 4，确认 (a) 既有 4 enum 值未被 remove / rename，**且** (b) M5 实际选用的语义承载方案（无论 `rejection_subtype` / 新 enum 值 / 其他）不被 §6.6.1 文本暗示 over-narrow。若 (a) 成立而 (b) 触发了 §6.6.1 文本调整，本 entry 关闭并在 M5 retro 记录调整原因

### CF-C-rev13-3 — GEPA fitness-signal 顺序理由依赖 multi-round GEPA 实操（Scope-50%）

- **Source**: Scope reviewer / Round D advisory 观察（C-Adv-2）
- **Confidence**: 50%
- **Conflict**: Coh / Arch GREEN on §6.4.1 既有 1→2→3 ordering rationale（决策 #109）；Scope 顾虑是 GEPA fitness-signal 完整性的核心 justification（"GEPA 优化器需要在 reject 候选上拿到完整 fitness signal"）若 M4 实际只 ship 单轮 / stub-level GEPA（DSPy `BootstrapFewShot` 或类似 1-shot 形态），多轮 mutation 学习的论证会弱化 → ordering rationale 部分悬空
- **Defer reason**: M4 GEPA 实际形态目前规划为 multi-round（DSPy 默认 ≥ 8 iter × ≤ 8 candidates），但 implementation phase 可能因 dependency / scope 压力降级为 single-shot baseline。即便 GEPA 降级为 1-shot，§6.4.1 点 (b) 的 "report.md reviewer 拿 `gate-rejected-at: 3-cache-compat` 时同时看 test_rate / size_delta 上下文" 人审可观测性论证仍成立，ordering rationale 不全部悬空。Scope 视角的弱化是局部而非全部；按 advisory 处理
- **Future close criterion**: M4 收尾 retro 验证 GEPA 实际是否 ships multi-round。若 ships multi-round → 本 entry 自动闭合（核心 fitness-signal justification 兑现）。若降级为 single-shot → 在 M4 retro 中 amend §6.4.1 ordering rationale，把 "GEPA fitness signal" 论证降级为 "human-reviewer observability + GEPA forward-compatibility" 双论证，并新增决策记 amend；本 entry 关闭

### CF-C-rev13-4 — Gate ordering 1→2→3 vs 3→1→2 wall-clock retro（Arch-Y6）

- **Source**: Arch reviewer / Round D / Y6 bucket（advisory observation；50% confidence）
- **Confidence**: 50%
- **Conflict**: Coh / Corr / Scope GREEN on 决策 #109 既有 1→2→3 ordering（metrics 完整性优先 over wall-clock）；Arch-Y6 顾虑是"gate-3 fails for free（O(1) hash compare），花 gate-1 数分钟 subprocess 时间在 cache-broken candidates 上是浪费"在 §6.4.1 既有 trade-off 分析中未被显式承认 —— 论证只覆盖了 metrics 完整性但未列出 wall-clock 浪费的具体量级
- **Defer reason**: 决策 #109 既有 trade-off 分析在质性层面覆盖了 wall-clock cost（§6.4.3 GEPA-layer early termination 部分缓解），但未给定量数据 —— 实际 GEPA candidate 中 cache-key-broken 比例需 M5 实测才知。若实测 ≥ 40% candidates fail gate-3，"花 gate-1 时间在必然 reject 的 candidate 上"成本显著，可能 outweigh metrics 完整性收益；若 ≤ 5%，cost 可忽略。M4 阶段无实测数据 → 按 advisory 保留 trade-off 决策不变
- **Future close criterion**: M5 retro 检视 M4 完整 run 的 gate-3 fail rate。若 ≥ 40% → re-evaluate ordering 至 3→1→2（即 cheap-first），即便牺牲部分 partial-test-metrics 给 GEPA；同步新增 M5 决策 amend 决策 #109，把 ordering 改为 conditional（基于实测 fail rate）。若 < 40% → 本 entry 闭合，决策 #109 ordering 保留。Decision close criterion 是可观测的实测百分比阈值，非自循环

## 5. C-rev14 user-sanctioned carry-forward entries (C-rev15 round close-out)

本批次 6 条 entry 来自 C-rev14 §6 reviewer round 中 50–55% confidence advisory 观察。C-rev15 fix pass 中按 C-rev10/11/13 sanctioned 路线（"全部修复，多轮直到没有 red/yellow；advisory YELLOW (50–55% confidence) 走 sanctioned carry-forward 至 §12 per established precedent"）保留为 register entries，等待真实 trigger 验证后再决定关闭或上升为 must-fix。**本批次触发 CF-C-rev11-1 hard threshold**（§12 register 累计未关闭 entry 数：12.2 (3) + 12.3 (2) + 12.4 (3 active；CF-C-rev13-1 已 CLOSED) + 12.5 (6) ≈ 14，跨过 ≥10 评估线），见 CF-C-rev15-5。

### CF-C-rev15-1 — 决策 #117 forward-looking semantics gap（cluster: A-Y1 + C-Y5 + Scope-Y1）

- **Source**: C-rev14 reviewer round / Arch-Y1 + Corr-Y5 + Scope-Y1（cluster collapse；3 reviewer 同源观察）
- **Confidence**: 50%
- **Conflict**: §6.0 point 1 + 决策 #117 GREEN-on-form（ClassVar opt-out 形态对齐 #95 `STRUCTURED_KWARGS`）；advisory 顾虑是 forward-looking 实施细节 —— (i) discovery semantics 未声明（`getattr(gate, "NONDETERMINISTIC")` MRO inheritance vs `cls.__dict__.get("NONDETERMINISTIC")` strict-own），spec 未文档化 inheritance-via-MRO 是 intended（默认 `False` 经 MRO 继承到子类，与 STRUCTURED_KWARGS strict-own registry 语义有意区分）；(ii) double-run assertion 推迟到 §10 不变量章节，C-rev15 期 `NONDETERMINISTIC` ClassVar 仍是纯 declarative（无运行时消费者）；(iii) §10 stub 当前未交叉引用决策 #117，drafter 起草时漏 conditional `NONDETERMINISTIC=False` guard 风险存在
- **Defer reason**: 三个 sub-finding 均为 forward-looking 实施细节，须在 §10 实际起草（Round H）时解决；C-rev15 round 是 §6 fix pass，§10 仍 stub 未起草，提前规定 §10 内部结构是 over-prescriptive。M4 落地时 `NONDETERMINISTIC=False` 默认值在三 gate 全继承（无 override），无 active 行为分歧
- **Future close criterion**: §10 (Round H) drafter MUST 满足三条全部：(a) 显式引用决策 #117 与 inheritance-via-MRO discovery 形式（推荐 `getattr` w/ default `False`）；(b) 编码 harness 双跑等价 assert 的 conditional `if not gate.NONDETERMINISTIC:` guard；(c) 与 STRUCTURED_KWARGS / MUST_PRECEDE registry 语义对比释明（避免新贡献者误解为同质 strict-own registry）。三条任一缺失 → 本 CF reopen 为 RED，需在 §10 round 内闭合

### CF-C-rev15-2 — 决策 #117 × GEPA fitness-signal 交互未规定（A-Y2）

- **Source**: C-rev14 reviewer round / Arch-Y2
- **Confidence**: 50%
- **Conflict**: §6.0 point 1 GREEN on `NONDETERMINISTIC=True` opt-out 路径；advisory 顾虑是当 M5 gate 4 (`SemanticFidelityGate` LLM-judge) 引入 `NONDETERMINISTIC=True` 时，gate 的 `metrics: dict[str, float]` 可能携带 noisy / 跨调用 unreproducible 的浮点值（如 LLM judge score 受 sampling 抖动影响）。GEPA fitness aggregation 若直接消费这些 metrics → 单候选跨 GEPA round 的 fitness 时序信号被 LLM 噪声污染，优化方向漂移。C-rev15 spec 未声明 nondeterministic gate metrics 是否参与 fitness aggregation
- **Defer reason**: M4 三 gate 全部 `NONDETERMINISTIC=False`，M4 范围内 fitness aggregation 不会触及该 case；属 M5 gate 4 落地时的 design space。提前在 M4 spec 锁定"nondeterministic metrics 是否参与 fitness"会过度规定 M5 调和方案（averaging / seeded / 独立通道等多个候选，需实测 LLM judge 噪声分布后再选）
- **Future close criterion**: M5 gate 4 spec 起草（`m5-darwinian-evolver.md` §gate-4 章节）MUST 显式 carve-out `NONDETERMINISTIC=True` gate metrics 的 fitness aggregation 政策。默认 proposal：从 GEPA fitness aggregation **排除** `NONDETERMINISTIC=True` 的 gate metrics（仅作为 audit / report-only 信号）；若选择**包含**则 MUST 指定 averaging / seeding / variance-bounding 策略并跨链 CF-C-rev13-3（GEPA fitness-signal 顺序理由）。两路任一落地，本 CF 关闭

### CF-C-rev15-3 — Gate ABC budget-check 义务在 ABC 外文档化（A-Y3）

- **Source**: C-rev14 reviewer round / Arch-Y3
- **Confidence**: 50%
- **Conflict**: §6.0 point 5 GREEN on hard timeout SoT 重定义（决策 #121）；advisory 顾虑是 §3.6 `Gate` ABC docstring（line ~830 `"同步评估；不允许调网络"`）只描述 sync + offline 两条，不提 `GATE_TIMEOUT_MS_HARD` budget-check 义务。Hard-timeout SoT 实际生活在 §6.0 point 5 散文中 —— 抽象层泄漏：M5 LLM-judge gate 4 实现者必须读 §6.0 prose 才能发现 budget-check 责任，单看 ABC 签名 / docstring 无法推导
- **Defer reason**: M4 仅 1 个 long-running gate（gate 1），budget-check 义务在 §6.1.2 主体已显式编码 + §6.0 point 5 跨 gate 公约描述清楚。M5 gate 4 是真实 trigger（首个新 long-running gate），届时再决定是否将义务上提到 ABC 形态。提前 over-engineering 风险：(i) 在 ABC 加 docstring 段易被忽略；(ii) 引入 `LONG_RUNNING: ClassVar[bool]` 多此一举（gate 2/3 是 O(1) 已天然不需 budget-check）；(iii) cross-ref 形态 vs ClassVar 形态选择本身有 trade-off，需结合 M5 实际经验决策
- **Future close criterion**: 至 M5 spec-writing（gate 4 章节起草）或更早，三选一闭合：(a) 在 §3.6 `Gate.evaluate` docstring 加一行 "若 gate 是 long-running，MUST 在每条 record 后 budget-check `GATE_TIMEOUT_MS_HARD`，跨 §6.0 point 5"；(b) 引入 `LONG_RUNNING: ClassVar[bool] = False` 形态（同决策 #117 `NONDETERMINISTIC` 形）+ harness `_run_gates` 在 invoke 前 conditional 注入 `gate_start = time.perf_counter()` 的协议；(c) 加一行 §3.6 → §6.0 point 5 cross-ref。三条任一落地本 CF 关闭；advisory 不阻塞 M4 实现

### CF-C-rev15-4 — 决策 #115 self-application + #115/#121 own-cell overage（cluster: A-Y4-a + Coh-Y1）

- **Source**: C-rev14 reviewer round / Arch-Y4-a + Coh-Y1（cluster collapse；同源观察）
- **Confidence**: 50%
- **Conflict**: §0.3.1 sub-rule 4（决策 #115）GREEN on form （度量 SoT 单一化）；advisory 顾虑是 (i) "≤ 8 逻辑单元 + 1500-char 硬上限" 是 spec 文本约定，无 CI lint 强制 —— `scripts/lint_decision_log.py` 不存在，rule 静默漂移风险存在；(ii) 决策 #115 自身 rationale 按 alternative-block 边界严格切分约 9 单元（超过它定义的 8 单元 cap by 1）；决策 #121 rationale 长度 ≥ 1500 chars 临界。两条决策都是 *规则定义自身* 与规则冲突
- **Defer reason**: rule 定义本身的 self-application 是程序化合规问题，不影响读者对决策内容的理解（决策 #115 / #121 文本含义清晰）；提前在 C-rev15 强制 grandfather marker 或 lint 脚本会让 §0.3 改写量超出 RF 三条修复 scope。属 advisory governance hygiene
- **Future close criterion**: 至下一次决策日志 grooming round（或 M5 spec start retro），二选一闭合：(i) 落地 `scripts/lint_decision_log.py` 作为 M5 in-scope 任务（CI 上 enforce ≤8 单元 + ≤1500 char）；(ii) 在决策 #115 / #121 标题行追加 `[GRANDFATHERED PRE-RULE-FINALIZATION]` marker（保留 audit 可见）。任一落地本 CF 关闭

### CF-C-rev15-5 — §12 register threshold trip + sub-section proliferation（cluster: A-Y4-b + Scope-Y2 + CF-C-rev11-1 trigger；C-rev16 / RF-1 time-boxed per user adjudication） [CLOSED C-rev18 via close-path (a)]

- **Source**: C-rev14 reviewer round / Arch-Y4-b + Scope-Y2（cluster collapse；同时是 CF-C-rev11-1 hard threshold trip）。**Responding to**（C-rev16 fold-in）：C-rev15 Scope-5（§12 proliferation self-aware-but-non-executing pattern）—— 本 entry 自身是 CF-C-rev11-1 hard-threshold 触发的 register entry，再以 §12 entry 形态承接 close-path 即"自我感知但不执行"governance recursion 的具体形态；fold 入本条而**不**另起 §12.6 entry，使该 pattern 一并受 RF-1 hard deadline 约束
- **Confidence**: 50%
- **Conflict**: §12.1 / 决策 #106 GREEN on register format；CF-C-rev11-1 已声明 ≥10 未关闭 entry 是 hard threshold；C-rev15 后实际计数：§12.2 (3) + §12.3 (2) + §12.4 (3 active；CF-C-rev13-1 已 CLOSED) + §12.5 (6) ≈ **14 未关闭 entry**（含本 CF 自身），跨过阈值。同时 sub-section 形态（§12.2 / 12.3 / 12.4 / 12.5 per-round）对决策 #106 强制的 `Source` 字段（已承载轮次 chronology）冗余，导航开销上升。**Governance recursion finding**（C-rev15 Arch-1 FIX）：将 CF-C-rev11-1 的 hard-threshold 触发再登记成新 §12 register entry（且该 entry 自身 count 入 threshold），构成 close-path 的延迟通道 —— meta-rule 的 hard-threshold 构造原意是 force close-path execution，再 defer 即 debt-evasion
- **Defer reason**: C-rev15 是 §6 fix pass，scope 仅限 RF-1/2/3 + CF 登记。§12 整章重组（CF-C-rev11-1 闭合方案）属 spec 结构化重排，会跨章节大量 churn，不应在 C-rev15 round 内执行；同时也是 CF-C-rev11-1 自身的 future close criterion 触发。**deferral 在 RF-1 hard deadline 处终止**（不 open-ended），见下条
- **Future close criterion** **[AMENDED-INLINE C-rev16 / RF-1 / user adjudication 2026-06-12, Arch path-b time-box]**: MUST 执行 CF-C-rev11-1 close-path **(a)** 抽离 `docs/hermes-evolution/specs/m4-carry-forward.md` 独立 tracking 文件 —— 按 chronological list（保留 Source 字段承载轮次归属），spec 内仅留 cross-link 占位 §12，废弃 per-round sub-sections；**OR** close-path **(b)** 迁移 active CFs 至 GitHub Issues（labels: `m4` / `carry-forward` / `confidence-50`），spec 内 §12 仅保留 closed entry audit trail 与 link template。**Hard deadline**：在 **C-rev17 4-reviewer 收敛 PASS** **OR** **§10（Round H）4-reviewer 收敛 PASS** 二者**先到者**之前必须执行 close-path —— 不允许再 defer。本 CF entry 的存在已经代表 governance recursion 可接受的最大深度（user adjudication 2026-06-12, Arch path-b "time-box deadline preserves meta-rule integrity via hard deadline"）。逾期未执行 ⇒ **下一轮 Arch reviewer（architecture-strategist）MUST 将本 CF auto-promote 为 RF-grade headline RED finding（block-on-fix，非 advisory），并 mandate 在 C-rev<N+1> fix round 内 inline 执行 close-path (a) 或 (b) —— 不再允许进一步 §12 deferral**。任一 close-path 落地后本 CF + CF-C-rev11-1 共同闭合，同时 CF-C-rev16-1（CF-C-rev15-1 trigger 软度）依附于此 deadline 一并 housekeep
- **Closure note (C-rev18)**: Path (a) executed — 本文件 `m4-carry-forward.md` 创建并接收 §12 完整内容；M4 spec §12 退化为 3-line pointer；per-round sub-sections (12.2–12.7) 重组为 chronological numbered sections (§2–§7) in this file，`Source` 字段承载轮次归属保留。CF-C-rev11-1 共同 CLOSED；CF-C-rev16-1 (path-a co-closure clause) CLOSED；CF-C-rev17-1 (path-a co-closure clause, see entry body) CLOSED

### CF-C-rev15-6 — SIGINT → exit 130 mapping ambiguity（C-Y4）

- **Source**: C-rev14 reviewer round / Corr-Y4
- **Confidence**: 55%
- **Conflict**: §4.6 dispatch table 当前**无** KeyboardInterrupt / exit 130 行；§5.3 line ~1772 表达 "SIGINT 不映射到固定 exit code"；§6.0 point 3 line ~2872 表达 "CLI handler 转 SIGINT/exit 130 / 标准退出语义"。两处 phrasing 留下两种合理读法：(i) harness 不显式 map，让 Python interpreter SIGINT 默认 handler 透传产生 130；(ii) CLI handler 显式 map exit 130。实现者分歧风险存在
- **Defer reason**: M4 单元测试与 §6.0 point 3 traceback 落库路径已定义，KeyboardInterrupt 在 `_run_gates` 内不被 swallow（透传至 harness top-level）这一点 §6.0 point 3 已锁；上层 mapping ambiguity 仅影响 CLI 表面 exit code 一致性，不影响 gate / harness 数据完整性。属 §4-§5 dispatch 章节的小 cleanup，留待下一次 §4-§5 fix round 一并处理更高效
- **Future close criterion**: 下一次 §4-§5 fix round（Round F 或更晚），二选一闭合：(a) §4.6 dispatch 表追加行 `130 | KeyboardInterrupt 透传 / SIGINT 默认行为 | 用户 Ctrl-C | 是` + §10 不变量章节为 KeyboardInterrupt 添加 carve-out（不参与"任何异常都被 dispatch 表覆盖"普遍量化）；(b) 改写 §6.0 point 3 句式为 "CLI handler 让 KeyboardInterrupt 透传至 Python 默认 SIGINT 处理（exit 130 由 interpreter 默认提供，harness 不显式 map）"。任一落地本 CF 关闭；不允许 M4 ship 仍同时存在两 phrasings

## 6. C-rev15 user-sanctioned carry-forward entries (C-rev16 round close-out)

本批次 1 条 entry 来自 C-rev15 §6 reviewer round 中 50% confidence advisory 观察。C-rev16 fix-round 中按 C-rev10/11/13/15 sanctioned 路线保留为 register entry，等待真实 trigger 验证后再决定关闭或上升为 must-fix。**注**：C-rev15 reviewer round 的 RF-grade headline finding（governance recursion / Arch-1 FIX）经 user adjudication 2026-06-12 决定走 Arch path-b time-box（不另起 entry，inline-amend CF-C-rev15-5 close criterion + hard deadline，见 §5 RF-1 amendment）；C-rev15 Scope-5（§12 proliferation self-aware-but-non-executing pattern）已 fold 入 CF-C-rev15-5 body 作为 "Responding to" 交叉链接，不另起 entry。本批次仅 CF-C-rev16-1 一条新 entry。

### CF-C-rev16-1 — CF-C-rev15-1 "Round H" trigger 软度（Scope-3） [CLOSED C-rev18 via close-path (a) co-closure clause]

- **Source**: C-rev15 reviewer round / Scope reviewer focus area 6（advisory 50%）
- **Confidence**: 50%
- **Conflict**: CF-C-rev15-1 的 "Future close criterion" 引用 "§10（Round H）drafter MUST 满足三条全部" —— "Round H" 是内部 orchestration phase 标签，若 CF 跨 M4 ship 仍未关闭，phase 标签会失去稳定语义。§10 章节引用本身稳定，但 trigger noun（"drafter"）是 round-specific 的瞬态语义
- **Defer reason**: 现在处理需要再触动 CF-C-rev15-1，而 CF-C-rev15-1 自身已被 RF-1 hard deadline（C-rev17 4-reviewer 收敛 PASS OR §10 Round H 4-reviewer 收敛 PASS 二者先到者）兜底；trigger 语言收紧自然 fold 入 RF-1 mandate 的同一 housekeeping pass，分开做属重复 churn
- **Future close criterion**: 当 CF-C-rev15-5 的 hard deadline 触发（C-rev17 OR §10 Round H 4-reviewer PASS），CF-C-rev15-1 的 trigger 语言 MUST 在同一 housekeeping pass 中由 "Round H drafter" 改写为 "§10 4-reviewer 收敛 PASS"（消除 phase-label 依赖）。本 CF 与 CF-C-rev15-5 共同闭合。**Path-b carve-out（C-rev17 / RF-5 / Arch-6）**：在 path (b)（GitHub Issues migration）下，CF-C-rev16-1 以同样 co-closure 语义作为 sibling issue 一并迁移（issue 在 CF-C-rev15-1 的 Round H wording-tightening 任务被 fold 入 M4 milestone tracker 时关闭）。
- **Closure note (C-rev18)**: CF-C-rev15-5 hard deadline triggered via close-path (a) (C-rev18). Per this entry's own co-closure clause, CF-C-rev16-1 CLOSED. CF-C-rev15-1 "Round H drafter" trigger wording remains pending its own §10-drafting close criterion (entry not auto-closed by §12 relocation; §10 is still a substantive stub awaiting Round H draft)

## 7. C-rev16 user-sanctioned carry-forward entries (C-rev17 round close-out)

本批次 1 条 entry 来自 C-rev16 reviewer round 中 Arch Focus 2（≥60% required-fix landed inline as RF-6）+ Scope Focus 5（50% advisory）成对发现：§3.6 docstring Note 4 是当前 5 条 forward-notes 中**唯一**关于 ABC 自身何时应当 restructure 的 self-referential 元评论；当前状态可接受，但若 M5+ 再追加同类 note，docstring 将逐步 drift 为 meta-discussion 区域。本 CF 配合 RF-6 inline forward-guard 落地，捕获届时的迁移 trigger。

### CF-C-rev17-1 — ABC docstring meta-note governance forward-guard（Arch-2 + Scope-5 paired） [CLOSED C-rev18 via close-path (a) §12-relocation co-closure]

- **Source**: C-rev16 reviewer round / Arch reviewer Focus 2（≥60% required-fix）+ Scope reviewer Focus 5（50% advisory，paired finding）
- **Confidence**: 50%（Scope advisory）+ ≥60%（Arch required-fix landed as RF-6 inline forward-guard at §3.6 Note 4）
- **Conflict**: 现状无冲突；风险为 forward —— `Gate` ABC docstring §3.6 Note 4 是当前 5 条 forward-notes 中**唯一** self-referential 元评论（"关于 ABC 自身何时应当 restructure" 的 forward-trigger）。其余 4 条（Notes 1/2/3/5）均为 `Gate` 消费者 contract（test isolation、abstract intermediate forward-compat、import-ordering invariant、与决策 #104 distinguisher）。M5+ 若不加治理直接追加同类 self-referential note，docstring 会从"`Gate` 消费者契约"slide 为 governance meta-discussion 区域，违反 ABC docstring 单一职责
- **Defer reason**: 当前仅 1 of 5 notes 为 meta-typed，relocate 至专用 module docstring（如 `nanobot/evolve/gates/__init__.py` 或 sidecar `_governance.md`）属 premature optimization；inline RF-6 forward-guard（"M5+ 追加同类 self-referential trigger note 必须先在 §12 register CF entry"）已足够防止 drift。第二条同类 note 抵达即触发 housekeeping pass，提前 relocate 不偿
- **Future close criterion**: 二选一闭合 —— **(a)** M5（或更晚 milestone）追加第二条 self-referential ABC trigger note → housekeeping pass 把所有 meta-typed notes 迁出 §3.6 docstring 至专用 governance 模块（`nanobot/evolve/gates/__init__.py` docstring **或** sidecar `_governance.md` 邻接文件），§3.6 docstring 仅保留 `Gate` 消费者 contract notes；**或** **(b)** CF-C-rev15-5 hard deadline 触发并迁移 §12 整章（path-b GitHub Issues），本 CF 作为 sibling issue 随之迁移（co-closure semantic 同 CF-C-rev16-1 path-b carve-out）
- **Closure note (C-rev18)**: CF-C-rev15-5 触发的是 **close-path (a)**（§12 整章物理迁移至本 sibling file），不是 path (b) GitHub Issues。本 entry 原有 path-(b) co-closure clause 的精神是"§12 整章 relocation event 触发 CF-C-rev17-1 co-closure"；path (a) 等同满足该 forward-trigger（"§12 整章 relocation" 已发生 —— 本 entry 物理从 M4 spec §12.7 迁至本文件 §7，§3.6 docstring meta-note 风险的 governance forward-guard 由 RF-6 inline note 与本文件 sibling status 共同承接）。CF-C-rev17-1 CLOSED；§3.6 docstring Note 4 RF-6 forward-guard 在 M4 spec 中维持不动；若 M5+ 抵达 path-(a) future close criterion（第二条 self-referential note 出现），届时直接执行 docstring relocation（不依赖本 CF entry）
