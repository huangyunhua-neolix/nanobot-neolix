# Hermes 风格自我进化能力 —— 总路线图

> **文档性质**：5-milestone 路线图 / 决策记录。本身**不是单个 spec**，而是把"全都要"这一个超大需求拆成可独立 spec→plan→implementation 的多周期总览。每个 milestone 自己有 spec、plan、progress 文档，本文负责导航和锁顺序。
>
> **状态**：路线图已锁定（2026-06-11）。**M1 已完成（2026-06-11，PR #1 + #2）**。**M2 已完成（2026-06-12，PR #4）**。**M4 离线骨架已完成并合入 main（2026-06-12，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6）**。**M3 Curator 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10，merge commit `52393d3d`）**：runtime `/curator` command、default dry-run、forced dry-run guard、deterministic proposals、protect-list、aux guardrails、safe M2 delete apply path 均已落地并通过全量测试。**M5 Darwinian Evolver 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/12）**，tool / prompt-template evolution 转为后续独立 milestone。**M6 Semantic Judge v2 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/14，merge commit `b8b5efa6`）**。**M7/M8 safety substrate 已完成并合入 main（2026-06-15）**。**M9 Runtime + Offline Integration 已完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/19，merge commit `1fe10e65`）**。**M10b-1 Slash Command Split 已完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`）**。**M10b-2 CLI Command Split 已完成并合入 main（2026-06-17，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`）**，后续继续 M10 技术债稳定。
>
> **目录约定**：本系列所有文档入库于 `docs/hermes-evolution/`，与 `docs/superpowers/`（本地、gitignore）区分。
>
> ```
> docs/hermes-evolution/
> ├── roadmap.md         # 本文：总路线图与决策记录
> ├── specs/             # 每个 milestone 的设计 spec
> ├── plans/             # 每个 milestone 的实施 plan 与 progress
> └── retros/            # 每个 milestone 完成后的回顾（可选）
> ```

## 1. 背景

调研依据：[`docs/hermes-self-evolution.md`](../hermes-self-evolution.md)。

目标：把 Nous Research **Hermes Agent** 的自我进化机制（运行时学习回路 + 离线进化管线）系统性地引入 nanobot，让 agent 在长期使用中自动沉淀技能、修剪冗余、并支持离线针对性优化。**两层全要**。

## 2. 决策记录

| 日期 | 决策 | 备注 |
|---|---|---|
| 2026-06-10 | 接受调研报告 §5 的两个澄清点：(1) 运行时回路 + 离线管线都做；(2) 进入 brainstorming + writing-plans 流程 | 由用户在 chat 中确认 |
| 2026-06-11 | 锁定 5-milestone 拆解（M1→M5），M2 与 M4 在 M1 完成后可并行 | 用户选项 A |
| 2026-06-11 | **M1 完成并合入 main**（PR #1 33-task plan + 4 follow-ups + 2 YELLOW 修复；PR #2 `.agent/memory/` 记忆固化） | 见 `retros/m1-foundations.md` |
| 2026-06-12 | **M2 完成并合入 main**（PR #4 15-task plan + 4 轮 reviewer fix + 1 处 spec erratum；37 commits / 36 files / +7110 −37） | 见 `retros/m2-skill-manage.md` |
| 2026-06-12 | **M4 离线骨架完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6，HEAD `f8a496bf`；`nanobot/evolve/` skeleton + `nanobot evolve` CLI surface） | 真正 GEPA/Darwinian Evolver 延后到 M5；apply/report CLI 接口在 finish pass 中补齐（见下行） |
| 2026-06-13 | **M4 finish pass 完成**（branch `feature/finish-m4-offline`）：`evolve init`、`evolve report --manifest`、reduced-surface `evolve apply --manifest` 已全部落地并通过测试 | §4.4 full bundle export / atomic swap / `--force`、真正 GEPA/Darwinian Evolver 仍留 M5；finish pass 不改变 M4 CLI 公开接口，不绕过 §9 redaction 边界 |
| 2026-06-14 | **M3 Curator 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10，merge commit `52393d3d`）：runtime `/curator` command、default dry-run、forced dry-run guard、deterministic proposals、protect-list、aux guardrails、safe M2 delete apply path 均已落地，160 tests pass | spec: `specs/m3-curator.md`；实现包含 `nanobot/curator/`、`nanobot/command/builtin.py`（curator handler）、`nanobot/config/schema.py`（CuratorConfig）|
| 2026-06-14 | **M5 Darwinian Evolver 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/12，merge commit `104d0e43`）：skills-only 五道闸门、subprocess optimizer 隔离、PR-only artifacts、ReviewReadiness gate-5 修复均已落地 | spec: `specs/m5-darwinian-evolver.md` + `specs/m5-complete-design.md`；plan: `plans/m5-complete.md`；retro: `retros/m5-complete.md` |
| 2026-06-14 | **M6 Semantic Judge v2 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/14，merge commit `b8b5efa6`）：Gate 4 semantic judge evidence、provider identity / corpus calibration key、per-axis κ floor、`judge_evidence.jsonl`、manifest/report/PR body review surface 均已落地 | spec: `specs/m6-semantic-judge-v2.md`；plan: `plans/m6-semantic-judge-v2.md`；retro: `retros/m6-semantic-judge-v2.md` |
| 2026-06-16 | **M9 Runtime + Offline Integration 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/19，merge commit `1fe10e65`）：manual / Curator / Dream runtime signals now create redacted offline evolution proposals, optional runs go through `OfflineHarness`, and artifacts record runtime provenance while preserving PR-only review | runtime 只提出候选；不修改 live skill/tool/prompt；不 push / merge / 自动创建 PR |
| 2026-06-16 | **M10b-1 Slash Command Split 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`）：Dream handlers moved to `dream_command.py`, Curator/Evolve handlers moved to `evolution_command.py`, `register_builtin_commands()` remains centralized, and boundary tests prevent handler re-export drift | M10b-2 继续拆分 `nanobot/cli/commands.py`；剩余 history/session/system slash commands 可后续再切片 |
| 2026-06-17 | **M10b-2 CLI Command Split 完成并合入 main**（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`）：shared CLI infrastructure moved to `nanobot/cli/shared.py`, provider OAuth commands moved to `provider_commands.py`, gateway/API commands moved to `gateway_commands.py`, and `nanobot.cli.commands.app` remains the public Typer entry point | `commands.py` 从约 2,086 行降至 983 行；后续 M10b-3 可继续拆分 interactive `agent()` / channels / plugins surface |

## 3. Milestone 总览

```
M1 Foundations  ──┬──> M2 skill_manage ──> M3 Curator
                  │
                  └──> M4 离线骨架 ──────> M5 Darwinian Evolver
```

| ID | 范围 | 依赖 | 当前状态 | spec | plan | progress |
|---|---|---|---|---|---|---|
| **M1** | provenance 字段 + skill 目录分层 + telemetry 计数 + auxiliary provider 配置形态 | — | ✅ 已完成 (2026-06-11, PR #1+#2) | [`specs/m1-foundations.md`](specs/m1-foundations.md) | [`plans/m1-foundations.md`](plans/m1-foundations.md) | [`retros/m1-foundations.md`](retros/m1-foundations.md) |
| **M2** | `skill_manage` 工具(create/patch/edit/delete) + 触发规则 + Dream 整合点 | M1 | ✅ 已完成 (2026-06-12, PR #4) | [`specs/m2-skill-manage.md`](specs/m2-skill-manage.md) | [`plans/m2-skill-manage.md`](plans/m2-skill-manage.md) | [`retros/m2-skill-manage.md`](retros/m2-skill-manage.md) |
| **M3** | Curator Phase 1(确定性状态机) + Phase 2(aux-model 审议) + dry-run + `/curator` 命令 + protect-list | M2 | ✅ 已完成并合入 main (2026-06-14, PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10, merge commit `52393d3d`) | [`specs/m3-curator.md`](specs/m3-curator.md) | `plans/m3-curator.md` | — |
| **M4** | 离线进化骨架：`nanobot/evolve/` skeleton（shared Pydantic base、评测数据模型、rubric/judge pool 类型、3 道 deterministic gate、OfflineHarness、redaction pipeline、PR-only deploy helpers）+ `nanobot evolve` CLI surface（init/report/apply） | M1 | ✅ 已完成 (2026-06-12, PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6, HEAD f8a496bf) | [`specs/m4-offline-skeleton.md`](specs/m4-offline-skeleton.md) | [`plans/m4-offline-skeleton.md`](plans/m4-offline-skeleton.md) | [`retros/m4-offline-skeleton.md`](retros/m4-offline-skeleton.md) |
| **M5** | 接入外部 Darwinian Evolver CLI + AGPL 许可隔离 + PR-only 部署 + 完整 5 道闸门（skills-only） | M4 | ✅ 已完成并合入 main (2026-06-14, PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/12) | `specs/m5-darwinian-evolver.md` + `specs/m5-complete-design.md` | `plans/m5-complete.md` | `retros/m5-complete.md` |

依赖与并行：

- **M1 是地基**。后面所有自进化能力都依赖它的三样东西：(a) provenance 让 Curator 知道哪些 skill 永不可动；(b) telemetry 是 Curator Phase 1 的唯一数据源；(c) auxiliary provider 让审议/评估不污染主对话 cache。
- **M2 与 M4 在 M1 完成后可并行**。运行时链条（M2→M3）和离线链条（M4→M5）耦合点很少，分两个团队/分支推进无冲突。
- **M3 必须晚于 M2**。Curator 的"删/合并"动作必须建立在足够的 telemetry 样本之上；M2 跑一段时间是 M3 安全启动的前置条件。
- **M5 必须晚于 M4**。Darwinian Evolver 涉及代码进化和 AGPL 合规问题，必须在离线骨架稳定后再接。

## 4. 每个 Milestone 的产出物清单

每个 milestone 走完会沉淀（按生成顺序）：

1. **设计 spec**：`docs/hermes-evolution/specs/m{N}-<topic>.md`
2. **实施 plan**：`docs/hermes-evolution/plans/m{N}-<topic>.md`（writing-plans skill 产出）
3. **执行 progress**：`docs/hermes-evolution/plans/m{N}-<topic>-progress.md`（实施过程中追加，对应 Planning-with-Files 规范）
4. **回顾笔记**：完成后追加到本 roadmap 的"5. 回顾与教训"段落，或独立写入 `docs/hermes-evolution/retros/m{N}-<topic>.md`

## 5. 回顾与教训

*（每个 milestone 完成后，在此追加 200–500 字回顾：实际落地与设计的偏差、遇到的坑、对后续 milestone 的影响。）*

- M1: ✅ 已完成 — 详见 [`retros/m1-foundations.md`](retros/m1-foundations.md)
- M2: ✅ 已完成 — 详见 [`retros/m2-skill-manage.md`](retros/m2-skill-manage.md)
- M3: ✅ 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10，merge commit `52393d3d`）— M3 Curator complete: runtime `/curator` command, default dry-run, forced dry-run guard, deterministic proposals, protect-list, aux guardrails, and safe M2 delete apply path.
- M4: ✅ 骨架已完成，finish pass 补齐 `evolve init` / `report` / reduced `apply`（完整 §4.4 bundle export / atomic swap / `--force` 留 M5） — 详见 [`retros/m4-offline-skeleton.md`](retros/m4-offline-skeleton.md)
- M5: ✅ 已完成并合入 main（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/12）— M5 now provides a skills-only five-gate offline evolution lane: subprocess optimizer boundary, candidate validation, gates 1-3, semantic-fidelity gate 4, local ReviewReadiness-backed human-review readiness gate 5, real diff stats, and explicit PR-only artifacts that require external human approval before merge. Tool and prompt/template evolution are intentionally split into future milestones because they need separate safety and cache designs.
- M6: ✅ 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/14，merge commit `b8b5efa6`）— 详见 [`retros/m6-semantic-judge-v2.md`](retros/m6-semantic-judge-v2.md)。M6 hardens Gate 4 with optional auxiliary judge evidence, provider/corpus calibration identity, per-axis κ floor, `judge_evidence.jsonl`, manifest/report/PR review surfaces, and preserves the invariant that judge metrics never become optimizer fitness.
- M9: ✅ 已完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/19，merge commit `1fe10e65`）— M9 connects runtime learning signals to offline evolution without crossing the safety line: manual proposals, Curator patch/merge candidates, and completed Dream runs can create redacted proposal records under `evals/proposals/`; users can list/show/create/run proposals via CLI or `/evolve`; unset optimizer config falls back to deterministic `nanobot.evolve.noop_optimizer`; `OfflineHarness.run()` records inert proposal provenance in manifest/report/PR artifacts while still never changing live skills, pushing, merging, or creating PRs automatically. Review hardening added proposal status locks, approved-sender checks for `/evolve create/run`, and skill immutability regression coverage.
- M10b-1: ✅ 已完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`）— Slash command split moved Dream commands into `nanobot/command/dream_command.py` and Curator/Evolve commands into `nanobot/command/evolution_command.py`; `builtin.py` now keeps metadata, help/simple commands, and centralized registration only. Boundary tests assert moved handlers are not re-exported from `builtin.py`. Follow-ups: split remaining history/session/system commands, document handler visibility convention, and consider extracting `_evolve_sender_allowed()` into a shared auth gate.
- M10b-2: ✅ 已完成并合入 main（2026-06-17，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`）— CLI command split introduced `nanobot/cli/shared.py`, `nanobot/cli/provider_commands.py`, and `nanobot/cli/gateway_commands.py`; root `nanobot.cli.commands.app` remains the public Typer entry point, root `serve` / `gateway` / hidden `desktop-gateway` command behavior and provider OAuth subcommands are preserved, and structural boundary tests prevent moved internals from leaking back through `commands.py`. Follow-ups: split interactive `agent()` into a future `agent_commands.py`, normalize CLI-internal helper naming, and centralize Loguru handler reconfiguration.

## 6. 跨 Milestone 的硬性约束

所有 milestone 必须共同遵守，不可在某个 milestone 内单独放弃：

1. **永不打破 prompt cache**：任何注入主 prompt 的新字段必须放在 volatile 段或独立段；不动 stable 段。
2. **provenance 是一等概念**：bundled / user / agent / hub 四类来源必须在数据模型里显式区分，不可推断。
3. **dry-run 是 Curator 的默认值**：M3 上线后第一周强制 dry-run，靠 `--apply` 显式打开。
4. **离线层 PR-only**：M4/M5 永远不直接 push 到主分支，永远经人审。
5. **隐私边界**：M4 用 SessionDB 当评测数据前，必须有用户级开关 + 数据脱敏管线。

## 7. 当前位置

- [x] 0. 调研完成（[hermes-self-evolution.md](../../hermes-self-evolution.md)）
- [x] 1. 范围拆解 + milestone 顺序锁定（本文档）
- [x] 2. M1 brainstorming
- [x] 3. M1 spec → plan → 实施（2026-06-11 合入 main）
- [x] 4. M2 spec → plan → 实施（2026-06-12 合入 main，PR #4）
- [x] 5. **M4 离线骨架完成并合入 main（2026-06-12，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6）**
- [x] 6. **M3 Curator 完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10，merge commit `52393d3d`）**
- [x] 7. **M5 Darwinian Evolver 完成（skills-only 五道闸门；tool / prompt-template evolution 转为后续独立 milestone）**
- [x] 8. **M6 Semantic Judge v2 完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/14，merge commit `b8b5efa6`；Gate 4 evidence / calibration hardening / report + PR review surface）**
- [x] 9. **M9 Runtime + Offline Integration 完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/19，merge commit `1fe10e65`）**
- [x] 10. **M10b-1 Slash Command Split 完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`）**
- [x] 11. **M10b-2 CLI Command Split 完成并合入 main（2026-06-17，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`）**

## 8. 后续 Milestone 规划（Post-M5）

M1-M5 已建立 runtime skill 管理、Curator、安全离线骨架与 skills-only Darwinian Evolver。后续不再把 tool / prompt-template evolution 视为 M5 未完成项，而是按更高安全等级拆成独立 milestone。

### 8.1 推荐顺序

```
M3 closure（已完成：PR #10 已合入，本轮修正 roadmap 状态）
  ↓
M6 Semantic Judge v2 / Evaluation Hardening
  ↓
M7 Tool Evolution Safety Substrate
  ↓
M8 Prompt / Template Evolution Safety Substrate
  ↓
M9 Runtime + Offline Integration
  ↓
M10 Technical Debt Stabilization
```

### 8.2 Milestone 候选清单

| ID | 范围 | 依赖 | 状态 | 关键边界 |
|---|---|---|---|---|
| **M3 收尾** | Curator 分支已通过 PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/10 合入 main；本轮仅修正 roadmap 旧状态 | M2 | ✅ 已闭环 | 不新增 Curator 范围；只做合并闭环、测试与文档状态更新 |
| **M6** | Semantic Judge v2 / Evaluation Hardening：可配置 auxiliary LLM judge、校准数据集、多维 rubric、judge evidence / confidence / disagreement 报告 | M5 | ✅ 已完成并合入 main（2026-06-14，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/14，merge commit `b8b5efa6`；spec: [`specs/m6-semantic-judge-v2.md`](specs/m6-semantic-judge-v2.md)，plan: [`plans/m6-semantic-judge-v2.md`](plans/m6-semantic-judge-v2.md)，retro: [`retros/m6-semantic-judge-v2.md`](retros/m6-semantic-judge-v2.md)） | judge 结果不进入 optimizer fitness；无 provider 时保留 deterministic fallback；不自动部署 |
| **M7** | Tool Evolution Safety Substrate：tool contract / metadata / description / schema 的离线候选与审查框架 | M6 | ✅ 已完成并合入 main（2026-06-15，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/16，merge commit `45ad83e8`；spec: [`specs/m7-tool-evolution-safety-substrate.md`](specs/m7-tool-evolution-safety-substrate.md)，plan: [`plans/m7-tool-evolution-safety-substrate.md`](plans/m7-tool-evolution-safety-substrate.md)，retro: [`retros/m7-tool-evolution-safety-substrate.md`](retros/m7-tool-evolution-safety-substrate.md)） | 不自动修改 `nanobot/agent/tools/` 源码；不绕过现有权限、sandbox、tool registry 边界；metadata candidate 只作为 review artifact |
| **M8** | Prompt / Template Evolution Safety Substrate：cache-safe prompt mutation rules、prompt candidate validator、prompt regression eval、PR-only prompt diff artifact | M6 | ✅ 已完成并合入 main（2026-06-15，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/17，merge commit `a1e365a9`；spec: [`specs/m8-prompt-template-evolution-safety-substrate.md`](specs/m8-prompt-template-evolution-safety-substrate.md)，plan: [`plans/m8-prompt-template-evolution-safety-substrate.md`](plans/m8-prompt-template-evolution-safety-substrate.md)，retro: [`retros/m8-prompt-template-evolution-safety-substrate.md`](retros/m8-prompt-template-evolution-safety-substrate.md)） | 不直接修改 stable prompt cache 段；不在线热替换系统 prompt；不削弱 tool permission / safety wording |
| **M9** | Runtime + Offline Integration：manual / Curator / Dream runtime signals create offline evolution proposals; users can optionally run a proposal through the local offline harness and get PR-only review artifacts with runtime provenance | M3 + M6 | ✅ 已完成并合入 main（2026-06-16，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/19，merge commit `1fe10e65`；runtime proposal store、no-op optimizer fallback、CLI + `/evolve` slash surface、Curator/Dream triggers、manifest/report/PR provenance） | runtime 只提出候选，不修改 live skill；offline harness 不 push / merge；仍然 PR-only |
| **M10** | Technical Debt Stabilization：分批治理 SettingsView、CLI commands、AgentLoop 构造、WebSocket/WebUI 耦合等高风险维护债 | 可并行 | 进行中（M10b-1 PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21 + M10b-2 PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25 已完成并合入 main） | 拆成 M10a/M10b/M10c/M10d；M10b command-surface split 已完成 slash + CLI 两片，后续可继续拆 `agent()` / channels / plugins；避免和 evolution surface 扩展混在同一个 PR |

### 8.3 M6 初始设计方向

M6 应先增强 M5 的 Gate 4，而不是立刻扩大 mutation surface。原因是 tool / prompt evolution 的风险高于 skill evolution；在扩大进化对象前，需要更可信的 semantic / safety regression 判断。

M6 的建议目标：

1. 为 `JudgePool.score()` 增加可配置 auxiliary LLM judge 后端，同时保留当前 deterministic local fallback。
2. 建立 calibration 数据与报告，使 judge 行为可回归、可解释。
3. 扩展 rubric 维度：intent preservation、safety regression、instruction compatibility、output quality。
4. 在 manifest / report / PR body 中展示 judge evidence、confidence、disagreement。
5. 保持 M5 的安全边界：judge metrics 只作为 gate evidence，不返回 optimizer，也不作为自动合并信号。

### 8.4 M7 / M8 安全拆分原则

Tool 与 prompt-template evolution 都不能直接沿用 skills-only pipeline 扩展 mutation surface。二者必须先建立各自 substrate：

- **M7 先做 tool contract evolution**：允许候选改进 tool metadata / description / schema 的审查材料，但不自动改 tool Python 源码。
- **M8 先做 prompt cache-safe evolution**：允许候选生成 prompt/template diff artifact，但必须显式报告 cache impact，并禁止修改 stable prompt 段。

### 8.5 技术债路线

M10 不是 Hermes evolution 的功能扩展，而是为了降低继续扩展 evolution surface 的维护风险。建议拆成：

- **M10a WebUI SettingsView split**：拆分超大 `SettingsView.tsx`。
- **M10b command-surface split**：分片治理命令面；M10b-1 已完成并合入 main（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`），已拆分 `nanobot/command/builtin.py` 的 Dream / Curator / Evolve slash command handlers；M10b-2 已完成并合入 main（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`），已拆分 `nanobot/cli/commands.py` 的 shared / provider OAuth / gateway+API command modules。后续可继续 M10b-3 拆 interactive `agent()`、channels、plugins surface。
- **M10c AgentLoop constructor cleanup**：降低构造参数与状态耦合。
- **M10d WebSocketChannel / WebUI decoupling**：明确 gateway protocol contract，减少前后端隐式耦合。
