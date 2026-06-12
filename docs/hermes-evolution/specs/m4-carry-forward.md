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

## 8. C-rev18 user-sanctioned carry-forward entries (C-rev19 round close-out)

本批次 6 条 entry 来自 C-rev18 §7–§14 起草后 4-reviewer round 中 50–60% confidence YELLOW advisory 观察。C-rev19 RED-only fix round 闭合 7 REDs inline（CORR-1..6 + COH-1）；6 YELLOWs 按 sanctioned 路线（"YELLOW 走 carry-forward 至 sibling file per established C-rev10..C-rev17 precedent"）保留为 register entries，等待真实 trigger 验证后再决定关闭或上升为 must-fix。

### CF-C-rev19-1 — GateResult.evidence typing for int seed（Corr Y-7）

- **Source**: C-rev18 Corr reviewer / CORR-7（60% YELLOW advisory）
- **Confidence**: 60% advisory
- **Conflict**: None（与其它 reviewer judgment 无冲突）
- **Defer reason**: §10 不变量 7 提到 nondeterministic gates persist `seed: int` in `GateResult.evidence`，但 `evidence: dict[str, str] | None`（决策 #116）类型签名只接受 str。`str(int)` round-trip 是 operationally safe 的（`int(str(n)) == n`），消费侧 cast 一行即可恢复；type-system precision 是 YAGNI 改进（M4 三 gate 全 deterministic，本字段在 M4 无 active runtime 消费者）
- **Future close criterion**: M5 widens `evidence` 类型至 `dict[str, str | int | float]`（per 决策 #114 forward-look in §11 "GateResult.metrics 类型放宽"）时，把 seed typing 一并 fold 入该 widening；或 M5 gate-4 (LLM-judge) 落地时若发现 `str(int)` round-trip 在 audit log 解析路径上引入 bug → 升级为 must-fix

### CF-C-rev19-2 — Re-calibration trigger 缺 provider-host / API-version（Corr Y-8）

- **Source**: C-rev18 Corr reviewer / CORR-8（55% YELLOW advisory）
- **Confidence**: 55% advisory
- **Conflict**: None
- **Defer reason**: §7.4 re-calibration trigger 列表（5 条）包含 `aux_provider.model` field diff 但不含 `aux_provider.base_url` / `aux_provider.api_version` diff。In-scope 但 not breaking —— user 典型行为是在 `aux_provider` 中声明完整 provider 配置（model + base_url + api_version 同步变），跨 host swap 而 model string 不变的场景在 M4 cooperative threat model 下不常见。下次 §7 housekeeping pass 时一并加入 trigger 列表
- **Future close criterion**: §7.4 trigger 1 扩展为包含 `aux_provider.base_url` 与 `aux_provider.api_version` field diff（spec edit 一行）；**OR** M5 引入 provider-pinning lockfile（每条 calibration run 记录完整 `(provider_name, base_url, api_version, model_id)` quadruple，diff 任一字段触发 re-calibration）

### CF-C-rev19-3 — κ mean 掩盖 single-axis collapse（Corr Y-9）

- **Source**: C-rev18 Corr reviewer / CORR-9（50% YELLOW advisory）
- **Confidence**: 50% advisory
- **Conflict**: None
- **Defer reason**: §7.4 Agreement metric "逐 axis 计算 then mean across axes" 在原 4-axis 设计下存在"单 axis（safety）collapse 到 κ ≈ 0 但 mean 仍 ≥ 0.6"的隐藏风险。C-rev19 / RED-1 fix 后 rubric 收敛至 3-axis (process / output / token)，safety axis collapse pattern 不再适用；风险显著降低但未完全消除（任一 axis κ 单独 collapse 时 3-axis mean 仍可能 ≥ 0.6 if 其它两 axis κ ≈ 0.9）。per-axis floor 仍有 defense-in-depth 价值
- **Future close criterion**: M5 gate-4 SemanticFidelityGate 引入第 4 axis（§11 deferred）→ axis 数增加再评估 collapse 风险；**OR** M4 首月生产 retro 显示任一 single-axis κ < 0.4 → §7.4 引入 κ_min ≥ 0.4 floor 作为 κ_mean ≥ 0.6 的并列约束（两者同时满足才视为 calibration PASS）

### CF-C-rev19-4 — §8.4 gate re-verification CI 过早（Scope Y）

- **Source**: C-rev18 Scope reviewer / §8.4 observation（50% YELLOW advisory）
- **Confidence**: 50% advisory
- **Conflict**: None
- **Defer reason**: §8.4 "Gate re-verification" GitHub Actions 第二次跑 gate 链服务于 §10 不变量 7（gate determinism），独立有价值（catch 本地 vs CI 环境差异引发的 verdict mismatch）。CI 接线细节（Actions workflow 形态 / 触发条件 / 失败处置）可推迟至 M5 5-gate CI 装配时一并起草，避免 M4 时锁定后 M5 改一次的 churn
- **Future close criterion**: M5 plan-writer 决定 (a) 保留 M4 re-verification 独立 workflow，**或** (b) fold 入 M5 5-gate full CI workflow（5 gates 集中 verify，gate 4/5 也走 re-verification）

### CF-C-rev19-5 — CF-C-rev15-1 sub-criteria (a)/(c) 未关闭（Arch Y）

- **Source**: C-rev18 Arch reviewer（60% YELLOW advisory）
- **Confidence**: 60% advisory
- **Conflict**: None
- **Defer reason**: CF-C-rev15-1 future close criterion 包含三条 sub-criteria：(a) §10 显式引用决策 #117 + inheritance-via-MRO discovery 形式、(b) harness 双跑 conditional `NONDETERMINISTIC` guard、(c) 与 STRUCTURED_KWARGS / MUST_PRECEDE registry 语义对比释明。C-rev18 §10 不变量 7 落地后覆盖 sub-criterion (b)；sub-criteria (a) MRO discovery 与 (c) STRUCTURED_KWARGS contrast 仍未显式交叉引用。Low risk because C-rev19 / RED-3 fix 在 §14 显式 clarify "STRUCTURED_KWARGS / MUST_PRECEDE 是 EvolveError 概念，不适用于 Gate subclass"，部分填补 (c) 的 contrast gap
- **Future close criterion**: M4 plan-writer 添加 explicit test `test_gate_nondeterministic_mro_discovery`（验证 `getattr(gate, "NONDETERMINISTIC", False)` 在子类未 override 时返回基类默认 `False`，与 STRUCTURED_KWARGS 的 strict-own `cls.__dict__.get(...)` 形式对比）；**OR** M5 round-A Arch reviewer audit Gate ABC vs EvolveError ClassVar 边界 一次性闭合 (a) + (c)

### CF-C-rev19-6 — §9.3 audit-log retention enforcement（Arch Y）

- **Source**: C-rev18 Arch reviewer（≤60% YELLOW advisory）
- **Confidence**: 60% advisory
- **Conflict**: None
- **Defer reason**: §9.3 "12-week rotation" + "weekly rotated `redaction.log.YYYY-WW`" 是 prose-only 描述，无 enforcement test（rotation logic 实现细节散落 in `nanobot evolve` CLI startup lazy trigger）。Fold 入 CF-C-rev15-4 lint-script umbrella（同为"规则定义 prose-only / 无 CI 强制"的 governance hygiene 类）
- **Future close criterion**: lint script (CF-C-rev15-4 owner = M5 in-scope `scripts/lint_decision_log.py`) 增加 audit-log rotation 检查（验证 `redaction.log.*` 文件 mtime 与命名 week stamp 一致 + 12-week-stale 文件自动 prune）；**OR** housekeeping retro 把 retention 转化为单元测试（`test_redaction_log_rotation_drops_stale`）

## 9. Phase-4 cleanup round-2 review fan-in (Group-4 consolidation commit)

本批次 9 条 entry 来自 M4 Phase-4 实现期的三轨 round-2 reviewer 收敛：t-11 (OfflineHarness gate iteration) round-2、t-13 (judge calibration κ) round-2、cross-cutting holistic sanity sweep (review id `a6fb1801f68b46fe2`)，以及 t-12 (redaction) round-3 fix scoping 推迟项。三轨结论 VERDICT_PASS，9 条 advisory ≤60% confidence 项按 sanctioned 路线登记本 sibling file，等待 t-14 / t-15 pipeline 实施期或 M5 起跑期触发关闭条件。Group-4 consolidation commit 同步落地 `FrozenEvolveBase` 抽象 + `@dataclass` 选择 rationale 注释（C1/C2 in `nanobot/evolve/_base.py` / `harness.py` / `judges/rubric.py` / `privacy/redact.py` / `judges/calibration.py`），spec 同批次新增本 §9。

### CF-t14-a — `_compute_final_status(gate_traces=None)` 默认静默降级 rejected→no_improvement（t-11 R2）

- **Source**: t-11 round-2 reviewer / advisory observation
- **Confidence**: 60%
- **Conflict**: None（t-11 R2 VERDICT_PASS；本项 deferred to t-14）
- **Defer reason**: `OfflineHarness._compute_final_status(gate_traces=None)` 当前默认值在 `promoted is None` 路径下将 `rejected_by_gate` 静默降级为 `no_improvement`，触发条件是 caller 忘记线 trace 参数。M4 round-4 仅 ship skeleton（无 caller 在生产路径触发），t-14 / t-15 pipeline 编写期是首个真实 caller 接入点，届时 default-drop / assert 选择更有上下文
- **Future close criterion**: t-14 实施 `OfflineHarness.run()` orchestrator 时二选一闭合 —— (a) 移除 `gate_traces=None` 默认值，签名改为 keyword-required；(b) 在 `promoted is None` 分支前 assert `gate_traces is not None`（accept default-None 但 fail-loud on caller bug）

### CF-t14-b — 错误文件路径缺 `<run_id>/<N>-<name>` 段（t-11 R2）

- **Source**: t-11 round-2 reviewer / advisory observation
- **Confidence**: 60%
- **Conflict**: §6.0 point 3 / 决策 #109 规定 per-gate error file 路径为 `<workspace>/<run_id>/<N>-<name>.error.txt`；M4 skeleton 当前实现是 `<workspace>/gates/<hash-prefix>/<gate.name>.error.txt`，缺 `run_id` 段且未走 `N-name` 命名
- **Defer reason**: M4 round-4 skeleton 期无 `run_id` 上下文（`OfflineHarness.__init__` 仅持 workspace）；线 `run_id` 进 `_write_gate_error` 需要先在 `run()` orchestrator 建立 run-id allocation，是 t-14 范围
- **Future close criterion**: t-14 实施 `run()` 时 (a) 线 `run_id` 入 harness 实例状态（`self._run_id`），(b) 把 error path 改写为 `<workspace>/<run_id>/<N>-<gate.name>.error.txt`（N 为 0-based gate index in `self._gates`），(c) 同步 `<workspace>/gates/<hash-prefix>/` 旧路径作为 transitional symlink 或直接弃用（视 t-14 review）

### CF-t14-c — 合成 gate-internal-error 的 `GateResult.evidence` 为 None（t-11 R2）

- **Source**: t-11 round-2 reviewer / advisory observation
- **Confidence**: 50%
- **Conflict**: None；属 forward-looking ergonomics
- **Defer reason**: 当前合成 GateResult 的 `evidence=None`（默认）；可以挂 `{"error_file": str(err_path)}` 让下游工具（report.md generator / CI annotation）直接拿到 traceback 路径而无需重新推导 hash-prefix 目录。M4 skeleton 期无下游消费者，零 active 收益
- **Future close criterion**: CF-t14-b 闭合时（path 形态最终确定）一并 fold 进合成 GateResult 的 `evidence={"error_file": str(err_path)}`；或 t-15 report.md generator 首次需要 error file 路径时反推闭合

### CF-t13-a — `compute_cohen_kappa([0.5],[0.5])` (n=1, pe==1) 退化回归测试未补（t-13 R2）

- **Source**: t-13 round-2 reviewer / advisory observation
- **Confidence**: 50%
- **Conflict**: None；属测试覆盖度补强
- **Defer reason**: M4 t-13 ship 的 κ 实现在 n=1 / pe==1 退化路径上数学上正确（返回 NaN-或-定值，视实现 branch），但缺一个 explicit pin test 把行为锁定。M5 calibration 真实 corpus 接入前是 low-active-risk
- **Future close criterion**: M5 calibration corpus 接入或更早 housekeeping pass 中追加 `test_compute_cohen_kappa_degenerate_pe_one`，pin n=1 / pe==1 时的返回值（NaN raise 或固定 sentinel，视实际行为）

### CF-t13-b — `CalibrationReport.model_dump → model_validate` round-trip test 未补（t-13 R2）

- **Source**: t-13 round-2 reviewer / advisory observation
- **Confidence**: 50%
- **Conflict**: None；属 serialisation regression guard
- **Defer reason**: M4 t-13 ship `CalibrationReport` 是 `EvolveBase` 子类，继承 camelCase alias contract；当前测试覆盖了字段语义但未 round-trip serialisation。M4 阶段 CalibrationReport 不进 RunManifest sidecar（calibration 是 pre-flight 独立 artefact），round-trip break 低风险
- **Future close criterion**: M5 calibration artefact 进入持久化路径（写盘 / 上传）时追加 `test_calibration_report_serialisation_round_trip`，pin `CalibrationReport.model_dump(by_alias=True) → model_validate` 等价

### CF-t13-c — `calibrate()` 对全部 record 调用 `pool.score` 在 axis 校验之前（t-13 R2）

- **Source**: t-13 round-2 reviewer / advisory observation
- **Confidence**: 55%
- **Conflict**: None；属 cost-on-error 路径优化
- **Defer reason**: 当前 `calibrate()` 实现先 for-loop 全 `pool.score(record)` 再做 `human_scores` axis 校验；若 axis 缺失，已花费的 judge call 全数浪费在 ValueError 路径上。stub-injected scorer 下零成本，real `JudgePool.score` 接入后每次 ValueError run 浪费一倍 token spend
- **Future close criterion**: t-14（或 wherever real `JudgeRunner.score` 落地）重构 `calibrate()`：先 sweep `record.human_scores.keys() == RUBRIC_AXES`，再启动 scoring loop；fail-fast on missing axes

### CF-cc-a — `_JudgeScorer` Protocol 与 `JudgePool.score` 实接缺位（cross-cutting holistic sweep）

- **Source**: holistic sanity sweep `a6fb1801f68b46fe2` / cross-cutting finding
- **Confidence**: 60%
- **Conflict**: None；属未来接线义务的 audit trail
- **Defer reason**: `_JudgeScorer` Protocol 在 `calibration.py` 引用 `pool.score(record)`，但 `JudgePool` (`judges/rubric.py`) 当前未实现 `score` 方法 —— 只有 stub-injected tests 走通。M4 round-4 skeleton 范围合规（calibration 是独立预-flight 模块，不依赖 judge runtime），但 audit trail 需显式 marker 防止未来 contributor 误以为 production path 已 wired。本 commit 同步在 `calibration.py` `_JudgeScorer.score` docstring 加 `TODO(m4-followup CF-cc-a)` inline marker
- **Future close criterion**: t-14 / t-15 pipeline 落地 `JudgePool.score(record: CalibrationRecord) -> RubricScore` real 实现（调 aux_provider）；inline TODO marker 同步移除，本 CF 闭合

### CF-cc-b — `ManifestPrivacyViolation` 未声明 kwargs 与 `STRUCTURED_KWARGS` 一致性（cross-cutting holistic sweep）

- **Source**: holistic sanity sweep `a6fb1801f68b46fe2` / cross-cutting finding
- **Confidence**: 50%
- **Conflict**: 与 §0.3 决策 #95 `STRUCTURED_KWARGS` registry 形态约定的 governance hygiene；运行时合规（`set(declared).issubset(kw_only)` 允许子集），但未来若有 `**kwargs`-forwarding wrapper（logger / telemetry）会静默丢失 `offending_path` / `offending_fields`
- **Defer reason**: M4 内无 `**kwargs`-forwarding consumer；当前两 kw-only 字段仅在 raise site 与 traceback formatter 间往返，丢失风险为零。决议两选一（扩 `STRUCTURED_KWARGS` 容纳全部 vs 删未用 kwargs）需 M5 评估 ManifestPrivacyViolation 在 evolve telemetry 中的真实消费形态
- **Future close criterion**: M5 evolve telemetry 接线（如 redaction.log structured emission）首次消费 `ManifestPrivacyViolation` 字段时二选一闭合 —— (a) `STRUCTURED_KWARGS = frozenset({"violated_invariant", "offending_path", "offending_fields"})`；(b) 删除 `offending_path` / `offending_fields` kwargs，将信息折入 `violated_invariant` message 字符串

### CF-cc-d — 异常吞咽约定未在 `.agent/design.md` 文档化（cross-cutting holistic sweep）

- **Source**: holistic sanity sweep `a6fb1801f68b46fe2` / cross-cutting finding
- **Confidence**: 50%
- **Conflict**: None；属 governance documentation gap
- **Defer reason**: `_run_gates` (gate-time exception → synthetic fail GateResult) + `_run_stage` (manifest-pipeline exception → ManifestPrivacyViolation) + data-shape validation (raise ValueError) 三套约定在代码层 de-facto 已贯彻，但未写入 `.agent/design.md`。新贡献者读单一文件无法推导跨文件约定
- **Future close criterion**: 下一次 `.agent/design.md` housekeeping pass 中追加 3-line 节："exception handling conventions: data-shape errors → raise ValueError; gate-time exceptions → swallow into GateResult.failure_reason via synthetic fail (§6.0 point 3 / 决策 #109); manifest-pipeline exceptions → raise ManifestPrivacyViolation (§9.4 redaction stage failure invariant)"

### CF-t12-a — 额外 secret-shape 覆盖（API keys 扩展）（t-12 R3 fix scoping）

- **Source**: t-12 round-3 fix scoping / deferred to M5 expansion
- **Confidence**: 50%
- **Conflict**: None；属 redaction surface 增量扩展
- **Defer reason**: M4 t-12 ship 的 redaction 覆盖 Anthropic / OpenAI / GitHub PAT / AWS 四类 + email / phone / 路径 prefix。未覆盖：Google API keys (`AIza...`)、Slack tokens (`xox[bpars]-...`)、Stripe (`sk_live_` / `pk_live_`)、Twilio (`SK[0-9a-f]{32}`)、JWT (`eyJ...`)、PEM private key blocks、`.env`-style `PASSWORD=...` 行。每条是 dev log 例行泄漏向量，但 t-12 R3 fix 收敛在 4 类核心 vendor 即关帧 scope；剩余作为 M5 expansion candidate
- **Future close criterion**: M5 redaction expansion task 落地上述 7 类正则 + 测试 fixture；或 M4 首月生产 retro 显示任一未覆盖类已发生实泄漏 → 升级为 must-fix hot-patch

### CF-t12-b — 网络 / 身份标识 redaction 扩展（t-12 R3 fix scoping）

- **Source**: t-12 round-3 fix scoping / deferred to M5 expansion
- **Confidence**: 50%
- **Conflict**: None；属 redaction surface 增量扩展
- **Defer reason**: 未覆盖 IPv4 / IPv6 地址、MAC 地址、`Authorization: Bearer ...` 头、unicode-homoglyph emails (Cyrillic 'а')、URL-encoded `alice%40example.com`。t-12 R3 scope 同 CF-t12-a 理由收敛
- **Future close criterion**: 与 CF-t12-a 同 M5 expansion pass 合并落地；homoglyph 与 URL-encoded 变体可能需要 NFKC normalization step 预处理，设计待 M5 评估

### CF-t12-c — 幂等性 hypothesis fuzz 测试（t-12 R3 fix scoping）

- **Source**: t-12 round-3 fix scoping / deferred to M5 expansion
- **Confidence**: 50%
- **Conflict**: None；属测试覆盖度补强（property-based）
- **Defer reason**: M4 t-12 R3 已 pin 几条 canonical input 的 `redact(redact(x).text).matches == {}` example-based 测试；hypothesis-driven fuzz 是 high-value 但 high-investment（property strategy 设计 + shrinking budget tuning），M5 redaction expansion pass 是合适落点（fuzz 同时覆盖 CF-t12-a / b 的扩展正则）
- **Future close criterion**: M5 redaction expansion 任务一并 ship `test_redaction_idempotence_property`（hypothesis ≥ 200 examples，shrink budget ≥ 10s），覆盖全部已实施正则的幂等性

### CF-t16-a — `assert_not_main` 仅 case-sensitive exact-match，未 normalise（t-15 R2）

- **Source**: t-15 round-2 reviewer / advisory observation
- **Confidence**: 55%
- **Conflict**: None；属 caller-side normalisation 义务的 audit trail
- **Defer reason**: `assert_not_main(branch)` 当前用 `branch in PROTECTED_BRANCHES` 做完全相等匹配。`"MAIN"` / `" main"` / `"main\n"` / `"refs/heads/main"` 都会 silently bypass 保护。M4 skeleton 期 caller 不存在；t-16 CLI / pipeline 接入是首个真实 caller，届时 caller 侧 normalisation（`git rev-parse --abbrev-ref HEAD` 短名）是更干净的闭合点
- **Future close criterion**: t-16 实施 CLI 落地时二选一闭合 —— (a) caller 全部走 `git rev-parse --abbrev-ref HEAD` 后再传入（推荐，单一 normalisation 点）；(b) 在 `assert_not_main` 入口加 `branch = branch.strip()` + case-insensitive lookup（`branch.lower() in PROTECTED_BRANCHES`），并补 `refs/heads/<name>` prefix 剥离

### CF-m5-a — `assemble_pr_body` Diff stats section 是 deterministic stub（t-15 R2）

- **Source**: t-15 round-2 reviewer / advisory observation
- **Confidence**: 60%
- **Conflict**: None；属 M5 pipeline 接线义务的 audit trail
- **Defer reason**: `assemble_pr_body` 的 Diff stats section 当前硬编码 `files changed: 1 (skill <name> SKILL.md)`，因为 M4 skeleton 期 `RunManifest` 未承载 `Patch` 对象。本 commit 同步在 deploy.py 该 section 上方加 `TODO(M5)` inline marker 防止 stub 变成 load-bearing 数据
- **Future close criterion**: M5 `pipeline.py` 线 `Patch` 入 `RunManifest`（携带真实 +/- counts 与 files-touched 列表）时重写本 section 输出真实 diff stats；inline `TODO(M5)` marker 同步移除，本 CF 闭合

### CF-R3-a — `_compute_final_status` 精度边界未覆盖（R3 holistic sweep）

- **Source**: R3 holistic sweep / testing finding
- **Confidence**: 60%
- **Conflict**: None；M5 run() 接线义务的 audit trail
- **Defer reason**: `_compute_final_status` 三个 precedence corner case 未直接 pinned —— (i) `promoted_candidate_hash` 等于 candidate 且 `gate_traces=None`；(ii) `promoted_candidate_hash` 设了但不在 candidates 列表；(iii) `no-promoted` + 多 candidate 的 mixed pass/fail。M4 skeleton 期 harness 未真正 run，仅 typed-stub 形式被消费
- **Future close criterion**: M5 真正接 `run()` 时一并补 3 个 boundary test 落到 `tests/evolve/test_harness.py::test_compute_final_status_*`

### CF-R3-b — Redact 4-stage direct ordering witnesses 仅 1/3 完整（R3-9 部分覆盖）

- **Source**: R3 holistic sweep / testing finding
- **Confidence**: 60%
- **Conflict**: None；R3-9 已加 APIKEY-before-PATH 一例
- **Defer reason**: R3-9 仅加 APIKEY-before-PATH witness；剩余 PATH-before-CUSTOM 与 PII-before-APIKEY 两个 ordering 边界仍由"all 4 stages exist in module"间接证明
- **Future close criterion**: M5 redaction expansion pass 同 fuzz 测试一起补 `test_stage_order_path_runs_before_custom` 与 `test_stage_order_pii_runs_before_apikey`（与 CF-t12-a/b 同批次）

### CF-R3-c — `Gate._subclasses` 在 `importlib.reload` 下未 exercise（R3-1 后续）

- **Source**: R3 holistic sweep / testing finding
- **Confidence**: 50%
- **Conflict**: None
- **Defer reason**: R3-1 强化了 own-declaration enforcement，但 `__init_subclass__` 的 dedup guard 在 `importlib.reload(nanobot.evolve.gates.test_pass)` 路径下是否仍生效（reload 重新定义类对象 → `cls not in _subclasses` identity check 会判定为新类）未 pinned。M4 期生产路径无 reload；仅开发回环下可能触发
- **Future close criterion**: M5 加 `tests/evolve/test_gates.py::test_subclasses_dedup_survives_reload` —— 用 `importlib.reload` 二次加载 `test_pass` 模块，断言 `_subclasses` 不暴露 stale 类对象 OR `GATES` execution registry 不被重复污染

### CF-R3-d — `EvolveError` diamond-MRO 子类未覆盖（R3 holistic sweep）

- **Source**: R3 holistic sweep / testing finding
- **Confidence**: 50%
- **Conflict**: None；当前 enforcement 用 `cls.__dict__`（不走 MRO）
- **Defer reason**: 现有 enforcement 仅看 `cls.__dict__["STRUCTURED_KWARGS"]`，diamond inheritance（如 `class C(A, B)` 且 A/B 都是 `EvolveError` 子类各自声明）的合并行为未 pinned。M4 期无 diamond case；如真出现，行为可能 surprising
- **Future close criterion**: M5 若新增 diamond exception 子类时补一条 unit test pin 行为；否则 M8+ retro 复评是否值得 pin 一条 mock-diamond test

### CF-R3-e — `assemble_pr_body` cross-process determinism 未 pin（R3 holistic sweep）

- **Source**: R3 holistic sweep / testing finding
- **Confidence**: 50%
- **Conflict**: None；当前 same-process 已 pin byte-equality
- **Defer reason**: `test_assemble_pr_body_is_deterministic` 仅 same-process two-call。若未来引入 `set` / `dict` ordering reliance（如 metrics blob 排序），不同 `PYTHONHASHSEED` 下输出可能 diverge。M4 实现已 sorted() metrics；防御性测试是 high-cost
- **Future close criterion**: M5 加 `test_assemble_pr_body_cross_process_byte_stable` —— `subprocess.run([sys.executable, ...], env={"PYTHONHASHSEED": "random"})` 三次，所有输出字节相等

### CF-R3-f — Backtick / code-fence injection via `gate_name` / `failure_reason`（R3 security）

- **CF-R3-f (security):** Triple-backtick injection in `failure_reason` / `gate_name` is rejected at the input-validation leaf (R3.5 follow-up commit). Richer markdown-injection audit — link spoofing via `[text](javascript:...)`, image refs (`![alt](evil.png)`), HTML comment smuggling, autolink abuse — deferred to M5 when production gate plugins land and an explicit injection threat model is needed.

### CF-R3-g — Regex-DoS 审计未对 PHONE_RE / OPENAI_KEY_RE 做 100KB+ 对抗输入（R3 security）

- **Source**: R3 holistic sweep / security finding
- **Confidence**: 50%
- **Conflict**: None
- **Defer reason**: `PHONE_RE` 用 negative lookbehind/lookahead + 量化 `{7,}` 在 pathological 输入下（长 digit run + interleaved hyphens）可能 catastrophic backtrack；`OPENAI_KEY_RE` 的 `[A-Za-z0-9_\-]{20,}` 同样。M4 redact 输入来自内部 RunManifest（不可控但通常 ≤ 10KB），未达需要 per-stage timeout 阈值
- **Future close criterion**: M5 redaction expansion pass 加 `time.monotonic()` 包装每个 `_run_stage` 调用，若耗时 > 250ms 抛 `ManifestPrivacyViolation(violated_invariant="§9.4 stage timeout")`；同时加 fuzz 测试覆盖 100KB+ 输入

### CF-R3-h — `GATES` 列表 bottom-of-module mutation（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 55%
- **Conflict**: None；模式 work 但 review 时 surprising
- **Defer reason**: `nanobot/evolve/gates/__init__.py` bottom 3 行 `GATES.append(...)` 在 import-side-effect 期 mutate 模块常量，跟 frozenset / EvolveBase frozen 哲学不一致。M4 期 gate 数固定为 3；重构属于 cosmetic
- **Future close criterion**: M5 接 plugin discovery 时改用 `@register_gate` decorator 或 `_register_default_gates()` idempotent helper（确保多次 import 不会重复 append）

### CF-R3-i — `_bin_cutoffs` dual-convention 双语义（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 55%
- **Conflict**: None；R3-7 已 rewrite docstring 描述真实行为
- **Defer reason**: `_bin_cutoffs(bins)` 同时支持 spec-pinned 3-bin (`[0.33, 0.66]` literal) 与 equal-width fallback (`i/bins`)，dual convention 在 R3-7 docstring 中已 prominently warn。生产唯一调用点是 `bins=3`，fallback path 无 prod 消费者
- **Future close criterion**: M5 calibration finalize 时若仍仅用 `bins=3`，drop `bins` 参数 + 内联 `[0.33, 0.66]` 为 module-level constant

### CF-R3-j — `_JudgeScorer` Protocol shim（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 60%
- **Conflict**: None；与 CF-cc-a 同源
- **Defer reason**: `nanobot/evolve/judges/calibration.py::_JudgeScorer` Protocol 是 t-04/t-05 时期为 `calibrate()` 创建的临时 shim —— 真实 `JudgePool.score` 方法在 M4 skeleton 期未落地
- **Future close criterion**: M5 接 CF-cc-a 时 delete Protocol，把 `calibrate(pool: JudgePool)` 直接 type-hint 到 concrete `JudgePool`

### CF-R3-k — `RunManifest` 13 top-level fields surface 偏胖（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 50%
- **Conflict**: None；当前 13 字段全部 spec §11.1 明确要求
- **Defer reason**: M4 skeleton `RunManifest` 已经 13 top-level fields（run_id / started_at / finished_at / nanobot_version / evolve_extra_version / skill_name / baseline_hash / candidate_hashes / promoted_candidate_hash / gate_verdicts / judge_summary / final_status / tiers_used / record_count_per_tier / judge_pool_health），M5 接 pipeline 后可能再 +3。Pydantic frozen 类 14+ 字段开始难导航
- **Future close criterion**: M5 字段数 ≥ 16 时拆 `ManifestProvenance`（version + timestamps）/ `EvalSummary`（gate + judge）/ `TierHealth`（tiers + counts + pool health）三个 sub-models

### CF-R3-l — `redact.py` 4-stage 写法重复（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 50%
- **Conflict**: None
- **Defer reason**: 4 stage 各自 `out = _run_stage("name", lambda: _stage_xxx(out))` 是 boilerplate fold；改成 `@dataclass _Stage(name, fn)` + `for stage in STAGES: out = stage.run(out)` 可压缩，但 M4 期 4 stage 数已封顶，重构收益边际
- **Future close criterion**: M5 redaction expansion 若新增 stage 数 ≥ 5，refactor 为 `_Stage` dataclass + 列表迭代

### CF-R3-m — `harness.py` 文件 pre-emptive split（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 50%
- **Conflict**: None
- **Defer reason**: `nanobot/evolve/harness.py` 当前接近 300 LOC，主要是 Pydantic model 定义（`Baseline` / `Candidate` / `RunManifest` / `JudgeSummary` 等）+ stub `run()` 入口。M5 run() 接线后会 push past 400 LOC（pyproject lint 上限 400 only by convention，不 hard-enforced）
- **Future close criterion**: M5 接 `run()` 前 / 同 commit 拆分 `harness/models.py`（纯 schema）+ `harness/runner.py`（execution wiring）

### CF-R3-n — Lazy-import smoke test 缺失（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 55%
- **Conflict**: None；§3.5.1 lazy-guard claim 当前为 aspirational
- **Defer reason**: spec §3.5.1 声明 `nanobot.evolve.__init__` import 不引入 dspy / gepa 等 extra deps；M4 期靠 hand-audit 而非测试。如果未来误加 `from nanobot.evolve.gepa import ...` 到 `__init__.py`，会让 baseline install 抛 `ImportError`
- **Future close criterion**: M5 加 `tests/evolve/test_lazy_import.py::test_evolve_import_without_extra` —— 在 subprocess 中 `python -c "import nanobot.evolve"` 期 sys.modules 不含 `dspy` / `gepa`

### CF-R3-o — `_lazy_import_gepa` helper 仅一处调用（R3 maintainability）

- **Source**: R3 holistic sweep / maintainability finding
- **Confidence**: 50%
- **Conflict**: None；当前 helper 只为 error-wrapping
- **Defer reason**: `_lazy_import_gepa()` 仅在 `build_pipeline()` 内部调用一次，存在主要是为了把 `ImportError` 重新包装为 `EvolveExtraNotInstalled`。M5 接线 run() 后该 helper 仍单点调用
- **Future close criterion**: M5 `build_pipeline()` 接线落地后 inline helper（保留 error-wrapping try/except）

### CF-R3-p — `EvolveError` STRUCTURED_KWARGS 在 diamond MRO 下未定义行为（R3 correctness）

- **Source**: R3 holistic sweep / correctness finding
- **Confidence**: 50%
- **Conflict**: 与 CF-R3-d 同源（diamond 双角度）
- **Defer reason**: `EvolveError.__init_subclass__` 用 `cls.__dict__.get("STRUCTURED_KWARGS")` 解析当前类的声明（不走 MRO），diamond `class C(A, B)` 行为依赖 MRO 第一个声明者；contract 未文档化
- **Future close criterion**: M5 若出现真实 diamond case，在 spec §5.3 增写 "diamond inheritance: cls.__dict__ takes precedence, MRO 走 left-to-right"，同时补一条 unit test pin

### CF-R4-a — Unicode BiDi / zero-width / no-break-space 未列入 `_FORBIDDEN_BRANCH_CHARS`（R3+R3.5 convergence / security）

- **Source**: R3+R3.5 convergence security reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；M4 sources 为内部 RunManifest
- **Defer reason**: `_FORBIDDEN_BRANCH_CHARS` 不含 BiDi override (U+202E)、zero-width chars (U+200B / U+200C / U+200D)、no-break / BOM (U+00A0 / U+FEFF)。如果 PR title / branch name 的 `run_id` / `skill_name` 未来变成 attacker-controlled，渲染层可被视觉欺骗。M4 期数据源是内部 RunManifest（pipeline 自生成），风险有界
- **Future close criterion**: M5 在 spec §8 增 threat-model 决定后，显式列出 allow-list 或 deny-list（参考 git refname IDN 规则与 Unicode TR36）并补 `_FORBIDDEN_BRANCH_CHARS` 单元测试

### CF-R4-b — `assert_not_main` 在空 / 全空白 branch 上 silently pass（R3+R3.5 convergence / security）

- **Source**: R3+R3.5 convergence security reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；下游 git plumbing 会自然 fail
- **Defer reason**: `assert_not_main(branch)` strip+casefold 后若 `normalized == ""`，函数走 fall-through 返回 None（即"非保护分支，放行"）。Defense-in-depth 视角下应把"strip 后为空"列为 refuse-condition。M4 风险有界 —— 后续 `git push <空>` 会 fail，但 fail-mode 含义不清晰
- **Future close criterion**: M5 hardening pass 在 `assert_not_main` 入口加 `if not normalized: raise ApplyTerminalError(...)`，并补 `test_assert_not_main_raises_on_empty_after_strip` 覆盖 `""` / `"   "` / `"\t\n"` 三种 input

### CF-R4-c — `assemble_pr_body` 接受单行 markdown link / image / HTML-comment 注入（R3+R3.5 convergence / security）

- **Source**: R3+R3.5 convergence security reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；triple-backtick + newline 已 R3.5 闭合
- **Defer reason**: 单行 attacker payload 如 `skill_name="foo](https://evil.com)"` 仍可 sneak through —— 渲染时与上下文文本拼成 markdown link `[run xxx for skill foo](https://evil.com)`。Image refs (`![alt](evil.png)`) 与 HTML comment 注入 (`<!-- -->`) 同样未拦截。M4 sources 内部，但 plugin gate `failure_reason` 是未来 attack surface
- **Future close criterion**: M5 在 `_validate_no_newlines` 旁加 markdown sanitizer —— 要么 schema-based allow-list（仅允许 `[A-Za-z0-9 _\-.,:/]`），要么 escape 所有 `[`, `]`, `(`, `)`, `<`, `>`, `!` 为 HTML entity（与 CF-R3-f 的 link spoofing 一并闭合）

### CF-R4-d — `Gate._subclasses` test-defined 子类永久泄漏到 registry（R3+R3.5 convergence / correctness）

- **Source**: R3+R3.5 convergence correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；目前无 bug，仅形态隐患
- **Defer reason**: `Gate._subclasses` 是 module-level monotonically-growing 全局。测试中定义的子类（如 `_DedupProbe` / `_Collected`）通过 `__init_subclass__` 注册后无 teardown，永久残留。今天无 bug；若未来某 contract test 遍历 `_subclasses` 并断言其 shape，pytest collection order 会变成 load-bearing
- **Future close criterion**: M5 加 fixture-scoped teardown（`@pytest.fixture(autouse=True)` 在退出时 `Gate._subclasses.discard(test_subclass)`）；或让 contract test 用 name-filter（如仅看 `cls.__module__.startswith("nanobot.evolve")`）忽略 test-only 子类

### CF-R4-e — `_KAPPA_EPSILON = 1e-9` 仅施于 `kappa_mean`，per-axis κ 仍裸 FP（R3+R3.5 convergence / correctness）

- **Source**: R3+R3.5 convergence correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；当前 verdict 仅依赖 kappa_mean
- **Defer reason**: `_KAPPA_EPSILON = 1e-9` tolerance 当前仅应用于 `kappa_mean` 与阈值 `0.6`（`CALIBRATION_KAPPA_THRESHOLD`）的比较；per-axis κ（process / output / token / aggregate）若被下游引入"reject if any axis κ < 0.6"判定，会重新引入边界 fragility 而本 tolerance 不会生效
- **Future close criterion**: M5 若加 per-axis floor verdict，抽 `_passes_with_tolerance(value, threshold, *, eps=_KAPPA_EPSILON)` helper 复用于所有 κ-vs-阈值比较点（kappa_mean + per-axis）

### CF-R4-f — `1e-9` epsilon 比实际 FP error floor 宽 ~7 个量级（R3+R3.5 convergence / correctness）

- **Source**: R3+R3.5 convergence correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；为安全 trade-off 而非 bug
- **Defer reason**: `1e-9` 比 IEEE 754 double 实际 FP error floor（~2.22e-16 × 3 / 3 ≈ 几个 ULP）宽 ~7 个量级。设计上是"安全偏宽"（避免本来该过的边界 case 被 false-rejected），但同时也 mask 掉真正 1e-10 跌破阈值的 value。这是设计 trade-off，非 bug
- **Future close criterion**: 若 production 观察到 false-negative（即应该 fail 的 calibration 被边缘 tolerance 救活），revisit；否则保持现状

### CF-R4-g — Redact PII-before-APIKEY ordering 缺 isolated witness（R3+R3.5 convergence / correctness）

- **Source**: R3+R3.5 convergence correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: 与 CF-R3-b 同源（redact ordering 覆盖）
- **Defer reason**: R3-9 加了 APIKEY-before-PATH 的孤立 ordering witness；analogous 的 PII-before-APIKEY witness 当前仅 bundled 在 `test_stage_order_apikey_specificity_preserved` 中（间接证）。若未来 stage 顺序调整误反，此间接覆盖检测不到
- **Future close criterion**: M5 在 `tests/evolve/test_redact.py` 加 `test_stage_order_pii_runs_before_apikey` —— 用 digit-run payload（11 位数字串）若 APIKEY 先跑会被 `[A-Za-z0-9_\-]{20,}` 误匹配；PII 先跑会变成 `[REDACTED:PHONE]` 后 APIKEY 找不到匹配。断言输出仅含 PII sentinel

### CF-R4-h — 多处测试断言耦合到 exception message 字面（R3+R3.5 convergence / testing）

- **Source**: R3+R3.5 convergence testing reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；R4-2 新测试已规避此 anti-pattern
- **Defer reason**: 当前 `tests/evolve/` 多个测试用 `pytest.raises(ValueError, match="@")` / `match=r"contains '\.\.'"` / `match=r"\.lock"` 等正则锚定 exception message 字面（5+ 处类似 `"line-break" in msg` 与 `f"U+{codepoint_hex}" in msg`）。这些断言在 error-message wording 改写时会脆性 fail，掩盖真实的契约变化
- **Future close criterion**: pre-M5 一次 test-quality pass 把 `pytest.raises(X, match=...)` 改为两步式 —— 先 `with pytest.raises(X) as exc_info:`，再用 loose-substring `assert "<keyword>" in str(exc_info.value)`（参考 R4-2 三个新测试）；保留对 ValueError 类型与 component 名称的硬断言

### CF-R4-i — `test_subclasses_registry_dedups_on_repeat_subclass_definition` 依赖 CPython descriptor 内部（R3+R3.5 convergence / testing）

- **Source**: R3+R3.5 convergence testing reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；当前 `__init_subclass__` 实现稳定
- **Defer reason**: 该测试 reach 进 `Gate.__init_subclass__.__func__` 以重新触发 hook —— 这是 CPython descriptor 内部。如果未来 `__init_subclass__` 迁移到 metaclass 或 `@classmethod` 装饰器，`.__func__` 路径会 break for non-behavioral reasons
- **Future close criterion**: M5 rewrite dedup probe 用 `types.new_class("Probe", (Gate,))` 重新声明类（语义等价于 `class Probe(Gate): ...` 的 dynamic 等价物），或在测试顶部加 `pytest.importorskip` guard 检查 `__func__` 存在性

### CF-R4-j — Calibrate κ 边界测试 monkey-patch `compute_cohen_kappa` 隐藏 per-axis 变化（R3+R3.5 convergence / testing）

- **Source**: R3+R3.5 convergence testing reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: 与 CF-R4-e 同源（per-axis κ 缺乏 dedicated test）
- **Defer reason**: `test_calibrate_*_at_kappa_*` boundary tests 在 module scope monkey-patch `compute_cohen_kappa` 返回固定值 —— 这是 intentional（在 isolation 中 probe verdict 分支）但同时也意味着未来若 verdict 改成依赖 per-axis κ 而非 mean，这些测试还会"通过"而不报警
- **Future close criterion**: 当 per-axis verdict logic 落地时（同 CF-R4-e 闭合时机），增补 `test_calibrate_per_axis_floor_*` 类测试，直接 probe per-axis 路径而非 monkey-patch mean 计算

### CF-R4-k — `test_kappa_random_agreement_is_zero_or_negative` 名实不符（R3+R3.5 convergence / testing）

- **Source**: R3+R3.5 convergence testing reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；当前 assertion 行为正确
- **Defer reason**: 测试名 `..._is_zero_or_negative` 暗示宽松断言（κ ≤ 0），但 assertion 实为 `pytest.approx(-1.0, abs=1e-9)`（完全 disagreement = -1.0 精确）。未来维护者可能根据名字把 assertion 弱化为 `assert kappa <= 0`，掩盖真实回归
- **Future close criterion**: 将测试 rename 为 `test_kappa_perfect_disagreement_is_minus_one`，让名字反映真实断言强度；同 commit 检查同模块是否还有其他"名字宽 / assertion 严"的对称问题

### CF-T16-a — `run_run` only checks `workspace.exists()`, not `.is_dir()`（t-16 review / correctness）

- **Source**: t-16 R5 correctness reviewer / YELLOW~55%
- **Confidence**: 55%
- **Conflict**: None；当前 `OfflineHarness.__init__` 对非目录路径会 raise `ConfigError`，CLI 端依赖该 contract
- **Defer reason**: `run_run` 只检查 `workspace.exists()`，不检查 `.is_dir()`，"file-as-workspace" 情形完全依赖 harness `__init__` 的 contract。若 harness contract 在未来 refactor 中弱化（如改为 lazy init），CLI 层会让 file-as-workspace 走出一条不清晰的 exit code 路径。Belt+suspenders 视角下应在 CLI 入口加 `if not workspace.is_dir(): raise ConfigError(...)`
- **Future close criterion**: M5 hardening pass 在 `run_run` 加 `is_dir()` 显式检查，并补 `test_run_run_workspace_is_file_raises_config_error` 覆盖 file-as-workspace boundary；或者通过 CLI-level test 把 harness contract 显式 pin 住

### CF-T16-b — 非 Value/Runtime 异常 escape dispatch, 与 EXIT_RUNTIME=1 碰撞（t-16 review / correctness）

- **Source**: t-16 R5 correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；当前 handler 不抛 OSError/TypeError/KeyError，仅 forward-looking
- **Defer reason**: `dispatch` 仅 catch `ValueError` / `RuntimeError` 及其 evolve subclass。`OSError`（如 workspace 读写失败）/ `TypeError` / `KeyError` 等 escape 后 Python 默认 exit 1，与 `EXIT_RUNTIME=1`（spec §4.6 "受控 RuntimeError fallback"）语义重叠。Operator 无法区分"controlled RuntimeError fallback"与"未捕获 crash"。M4 阶段 handler stub 简单未触发，但 M5 起 init/report/apply 真实实现会扩大表面
- **Future close criterion**: M5 在 dispatch 外层加 `except Exception as exc: _print_err("internal", exc); return EXIT_INTERNAL` —— 新增 EXIT_INTERNAL=8 slot；继续让 `KeyboardInterrupt` / `asyncio.CancelledError` propagate；补 `test_dispatch_unexpected_oserror_maps_to_8` 等 boundary witness

### CF-T16-c — argparse-injected `SystemExit(2)` 与 ConfigError 的 exit 2 重叠（t-16 review / correctness）

- **Source**: t-16 R5 correctness reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；argparse 行为标准化，无运行时 bug
- **Defer reason**: argparse 在 missing required subcommand / `--help` / unknown flag 时 raise `SystemExit(2)` 完全 bypass `dispatch`。该 exit 2 与 `EXIT_CONFIG=2`（spec-pinned `ConfigError` exit）overlap，operator 无法区分"parser 拒收的非法调用"与"typed ConfigError"。Spec §4.6 把 exit 2 锚定到 ConfigError 语义，argparse 的"convention-by-coincidence" exit 2 是 silent collision
- **Future close criterion**: M5 在 typer-shim 捕获 `SystemExit`，把 argparse 的 exit 2 re-map 到新 slot（如 EXIT_PARSER=9），同时 preserve `--help` 的 exit 0；补 `test_typer_shim_argparse_missing_subcommand_uses_parser_slot` 覆盖该路径

### CF-T16-d — `test_validation_error_wrap_preserves_cause` 用 raw try/finally 而非 `pytest.MonkeyPatch`（t-16 review / testing）

- **Source**: t-16 R5 testing reviewer / YELLOW~65%
- **Confidence**: 65%
- **Conflict**: None；纯 style debt，correctness 一致
- **Defer reason**: 该测试用 `original = evolve_cli._print_err; evolve_cli._print_err = capturing_print` 加 try/finally restore，而不是标准的 `monkeypatch.setattr(evolve_cli, "_print_err", capturing_print)`。raw monkey-patch 在 setup 失败时不会自动 restore，pytest fixture 路径更鲁棒。M4 阶段 test 通过，但是 style debt 累计会让后续 contributor 复制错模式
- **Future close criterion**: 下一次 test-quality pass（与 CF-R4-h "exception message 字面耦合"打包处理）改写为 `monkeypatch.setattr(evolve_cli, "_print_err", capturing_print)`，去掉手工 try/finally

### CF-T16-e — 缺 CLI-level 测试探测 `--workspace` 指向 regular file（t-16 review / testing）

- **Source**: t-16 R5 testing reviewer / YELLOW~60%
- **Confidence**: 60%
- **Conflict**: 与 CF-T16-a 同源（CLI 层未独立验证 is_dir）
- **Defer reason**: 当前 `run_run` 测试覆盖 missing workspace + valid dir，但未覆盖 `--workspace` 指向已存在的 regular file 这一 boundary。该路径完全依赖 `OfflineHarness.__init__` raise `ConfigError`，CLI 层没有独立 witness。若 harness contract 改变，无 test 会 fire
- **Future close criterion**: 在为 CF-T16-a 补 belt+suspenders 时同 commit 加 `test_run_run_workspace_is_regular_file_raises_config_error(tmp_path)` —— 创建一个 file，--workspace 指向它，assert exit 2

### CF-T16-f — `Path(args.workspace).expanduser()` 的 tilde-expansion 分支无测试（t-16 review / testing）

- **Source**: t-16 R5 testing reviewer / YELLOW~55%
- **Confidence**: 55%
- **Conflict**: None；当前 `expanduser()` 行为正确
- **Defer reason**: `run_run` 调用 `Path(args.workspace).expanduser()`，若 refactor 中误删该调用，传 `~/some-workspace` 的 user-typed 路径会作为 literal 字面失败（"~/some-workspace does not exist"），但**没有 test 会 fire**。属 silent-regression 风险
- **Future close criterion**: 在 happy-path 的 `test_run_run_valid_workspace_returns_zero` 上加 parametrized variant，构造 `~/<random>` 形态的 path（用 `monkeypatch.setenv("HOME", str(tmp_path))` 让 expanduser 解析到 tmp_path）；assert exit 0

### CF-T16-g — `_print_err` stderr 格式仅通过 mock-call assert，缺 capsys end-to-end pin（t-16 review / testing）

- **Source**: t-16 R5 testing reviewer / YELLOW~50%
- **Confidence**: 50%
- **Conflict**: None；当前 format 行为正确
- **Defer reason**: `_print_err(category, exc)` 输出 `evolve: <category> error: <msg>` 到 stderr，但所有现有测试 assert 的是 mock-call 参数（`captured["category"] == "config"`），没有任何 test 用 capsys 验证实际写到 stderr 的字符串。日志抓取的 operator 若把 wording 当 contract（grep 这个前缀），format string 被静默改写会让监控悄悄断
- **Future close criterion**: 加 `test_print_err_stderr_format_pinned(capsys)` —— 直接 call `_print_err("config", ValueError("bad"))`，capsys 抓取 stderr，assert `"evolve: config error: bad"` literal 出现

> **Meta-note (handler-order pinning)**: 两位 reviewer 初稿都怀疑 dispatch 表的 handler order 缺 documentary pin；trace MRO 后确认 order 已经被 Python 继承链自然 pin（`ApplyTerminalError ISA ValueError`、`JudgeError`/`ManifestPrivacyViolation`/`EvolveEnvironmentError`/`GateInternalError` ISA `RuntimeError`），加之 `EvolveError.MUST_PRECEDE` 已 documented + sibling order test 已 cover，无需额外 CF entry。本节因此为 7 条（a–g）而非 8 条。

### CF-T17-a — substring-extraction invariant for mixed-token `sk-ant-` shapes
**Source**: ce-security-reviewer round 1 on t-17 (`89b6f9ab`)
**Confidence**: 55%
**Conflict**: tested invariant (model-id false-positive) is prefix-boundary;
  substring-extraction (e.g. `noise-claude-3-5-sonnet-sk-ant-<key>`) is a
  different invariant — ANTHROPIC_KEY_RE has no left word-boundary, so it
  correctly extracts the embedded key. A regression pin for this safe
  behavior would catch a future maintainer who adds `\b` "for cleanliness"
  and silently breaks credential-extraction from concatenated tokens.
**Defer reason**: out of scope for §9.2 stage-2 false-positive task; one
  test is cheap but belongs in a `test_redact_substring_extraction.py`
  alongside other regex-boundary pins, not in `test_redact_no_false_positive.py`.
**Future close criterion**: next round that touches `nanobot/evolve/privacy/redact.py`
  regex internals adds the substring-extraction pin in the same commit.
