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

M10 不是 Hermes evolution 的功能扩展，而是为了降低继续扩展 evolution surface 的维护风险。M10b-1 / M10b-2 已完成 command-surface 的第一轮拆分；2026-06-17 复审后，剩余技术债按“先安全暴露面与假安全感，再核心性能地雷，再架构地基，最后 WebUI/长尾维护性”排序。

已完成：

- **M10b-1 Slash command split**：已合入 main（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/21，merge commit `45dafeae`），已拆分 `nanobot/command/builtin.py` 的 Dream / Curator / Evolve slash command handlers。
- **M10b-2 CLI command split**：已合入 main（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/25，merge commit `be8ac227`），已拆分 `nanobot/cli/commands.py` 的 shared / provider OAuth / gateway+API command modules。

后续 M10 任务池见 §9。后续 agent 领任务时应优先选择独立 task id，按 task 的 `目标 / 文件 / 验收标准 / 测试` 完成，避免把多个高风险 task 混进同一个 PR。

## 9. M10 技术债稳定任务池（2026-06-17 复审版）

### 9.1 领任务规则

1. **每个 agent 默认只领一个 task id**，除非该 task 明确标注“可打包”。
2. **所有改动必须从最新 `main` 新建独立 worktree/branch**，PR 目标固定为 `huangyunhua-neolix/nanobot-neolix`。
3. **优先级解释**：
   - **P0**：安全暴露面或核心性能地雷，优先修。
   - **P1**：高风险架构/可靠性/测试假安全感，尽快修。
   - **P2**：中期可伸缩性、维护性和多用户边界。
   - **P3**：长尾清理和体验优化。
4. **代价解释**：S（小修）/ M（单 PR 中等改动）/ L（需要拆阶段）/ XL（必须另写 spec/plan）。
5. **推荐实施方式**：P0/P1 必须 TDD；L/XL 任务先写 spec/plan，不直接大改。
6. **完成标准**：代码、测试、文档/配置同步更新；不能只做重构不加回归测试。

### 9.2 P0：最先处理

| Task ID | 主题 | 代价 | 依赖 | 目标 |
|---|---:|---:|---|---|
| **M10-P0-API-AUTH** | API server 鉴权与非 localhost guard | M | 无 | 避免 `/v1/chat/completions` 在公网/反代下直接暴露 agent 能力 |
| **M10-P0-SESSION-SAVE** | session 保存路径去全量重写/降低写放大 | L | 无 | 降低长会话和并发 turn 的核心延迟与崩溃风险 |
| **M10-P0-WEBUI-THREAD-PAGING** | WebUI thread 真分页 | M/L | 可与 SESSION-SAVE 并行设计 | 分页请求不再服务端全量读取 session 文件并 replay |

#### M10-P0-API-AUTH

- **优先级**：P0
- **代价**：M
- **主要文件**：
  - `nanobot/api/server.py:194-349`
  - `nanobot/config/schema.py:384-390`
  - `tests/test_openai_api.py`
  - `tests/test_api_stream.py`
- **目标**：
  - API server 支持 bearer token / API key 配置。
  - `api.host` 不是 loopback 且未配置鉴权时启动失败。
  - `/v1/chat/completions`、`/v1/models`、streaming 路径都走同一鉴权逻辑。
- **验收标准**：
  - localhost 默认行为保持可用。
  - 非 localhost + 无 token 配置启动失败，错误信息明确。
  - 配置 token 后，无 `Authorization: Bearer ...` 请求返回 401。
  - token 正确时原有 API tests 通过。
- **测试建议**：
  - 增加 host guard 单元测试。
  - 增加 missing/invalid/valid bearer token 测试。
  - 保留 streaming API 回归测试。

#### M10-P0-SESSION-SAVE

- **优先级**：P0
- **代价**：L
- **主要文件**：
  - `nanobot/session/manager.py:555-603`
  - `nanobot/agent/loop.py:581-603`
  - `nanobot/agent/loop.py:1500-1537`
  - `nanobot/agent/loop.py:1667-1670`
  - `tests/agent/test_session_atomic.py`
- **目标**：
  - 短期先减少单 turn 内重复 save、增加保存耗时观测、checkpoint debounce。
  - 中期改为 append-only message log + metadata/checkpoint 独立持久化。
- **验收标准**：
  - 单个 turn 不再无必要多次全量保存同一 session。
  - 现有 atomic session tests 继续通过。
  - 新增 benchmark 或测试证明 100/1000/2000 messages 保存次数和耗时可观测。
- **测试建议**：
  - 增加 fake SessionManager 统计 save 调用次数。
  - 增加 checkpoint debounce 行为测试。
  - 大结构改动前先写 `docs/hermes-evolution/specs/m10-session-storage.md`。

#### M10-P0-WEBUI-THREAD-PAGING

- **优先级**：P0
- **代价**：M/L
- **主要文件**：
  - `nanobot/webui/ws_http.py:364-407`
  - `nanobot/session/manager.py:696-737`
  - `nanobot/webui/transcript.py:1826`
  - WebUI thread/session tests
- **目标**：
  - WebUI thread endpoint 的分页参数真正减少服务端磁盘读取、JSON parse 和 replay 成本。
  - 增加 tail-page reader 或 byte-offset index。
- **验收标准**：
  - 请求最后 N 条消息时，不再读取完整 JSONL 后切片。
  - 长 session 测试覆盖 1000+ event lines。
  - response shape 与现有前端兼容。
- **测试建议**：
  - 用临时 session 文件构造 1000/5000 行 JSONL。
  - mock/spy reader，断言分页读取窗口小于完整文件。

### 9.3 P1：高风险、小中型优先修复

| Task ID | 主题 | 代价 | 依赖 | 目标 |
|---|---:|---:|---|---|
| **M10-P1-API-LOG-REDACTION** | API 日志脱敏 | S | 无 | 不再记录用户 prompt 原文片段 |
| **M10-P1-SHELL-PROCESS-TREE** | shell timeout 杀进程组 | M | 无 | 超时/取消时不遗留后台/孙进程 |
| **M10-P1-SHELL-LOGIN-MODE** | shell 默认非 login shell / 明确配置 | M | SHELL-PROCESS-TREE 可并行 | 降低 profile 注入和 secret 泄露风险 |
| **M10-P1-MCP-TIMEOUT** | MCP streamable HTTP 显式 timeout | S/M | 无 | 防止 MCP 连接/请求无限挂起 |
| **M10-P1-CONFIG-DURABLE-SECRET** | config 原子写 + 0600 权限 | M | 无 | 防止 config 截断和 secret 文件权限过宽 |
| **M10-P1-PYTEST-TIMEOUT** | 修复 timeout mark 假安全感 | S | 无 | 并发/死锁测试真实超时失败 |
| **M10-P1-CI-PYTHON-MATRIX** | CI 覆盖 Python 3.11/3.12 | S/M | 无 | CI 覆盖声明支持版本 |
| **M10-P1-DEPS-UPPER-BOUND** | openai / boto3 upper bound | S | 无 | 降低依赖破坏性升级风险 |
| **M10-P1-CI-FULL-RUFF** | CI lint 对齐 pyproject | S | 无 | CI 覆盖 `E/F/I/N/W` 而非只跑 `F` |
| **M10-P1-MOCHAT-TESTS** | Mochat channel 测试 | M | 无 | 覆盖异步协议、cursor、fallback、发送错误 |
| **M10-P1-PROMPT-MEMORY-CACHE** | system prompt / memory history 缓存 | M | 无 | 降低每 turn 固定 IO/扫描成本 |
| **M10-P1-TOOLCONTEXT-RUNTIME-STATE** | ToolContext 显式 runtime_state | M | 无 | 去掉 subagent 动态挂属性，明确工具依赖 |
| **M10-P1-CONFIG-SCHEMA-SPLIT** | config schema 反向依赖拆分 | L | 建议先做 TOOLCONTEXT | 缩小 import cycle，稳定 provider/tool config 边界 |
| **M10-P1-OPENAI-COMPAT-SPLIT** | OpenAICompatProvider 分层 | L | 无 | 拆 request builder / parser / capability policy |
| **M10-P1-AGENTLOOP-RUNNER-SLIM** | AgentLoop / Runner 窄切片瘦身 | L/XL | 建议先补测试 | 降低核心路径变更回归面 |

#### 可打包的 P1 小 PR

以下 task 可合成一个“小而高收益”的 PR，适合作为第一批 agent 领取：

- `M10-P1-API-LOG-REDACTION`
- `M10-P1-MCP-TIMEOUT`
- `M10-P1-PYTEST-TIMEOUT`
- `M10-P1-DEPS-UPPER-BOUND`
- `M10-P1-CI-FULL-RUFF`

验收标准：每个点都有单独测试或 CI 配置验证；PR 描述中逐项列出行为变化。

#### M10-P1-API-LOG-REDACTION

- **主要文件**：`nanobot/api/server.py:232-235`
- **目标**：日志只记录长度、media 数量、stream flag、状态/耗时，不记录 `text[:80]`。
- **验收标准**：测试或日志 formatter 断言不包含 prompt 内容。

#### M10-P1-SHELL-PROCESS-TREE

- **主要文件**：
  - `nanobot/agent/tools/shell.py:279-286`
  - `nanobot/agent/tools/shell.py:527-539`
  - `nanobot/agent/tools/exec_session.py:54-177`
- **目标**：Unix 用 process group；Windows 用可用的 tree cleanup 机制。
- **验收标准**：`sh -c 'sleep 999 &'` 超时后不遗留 `sleep` 进程。

#### M10-P1-MCP-TIMEOUT

- **主要文件**：`nanobot/agent/tools/mcp.py:668-674`
- **目标**：替换 `timeout=None` 为显式 connect/read/write/pool timeout；stream idle timeout 单独处理。
- **验收标准**：MCP 连接卡住时按配置超时并给出可诊断错误。

#### M10-P1-CONFIG-DURABLE-SECRET

- **主要文件**：
  - `nanobot/config/loader.py:70-85`
  - `nanobot/config/schema.py:308`
- **目标**：`save_config()` 使用 temp file + flush + fsync + replace + directory fsync，新建/保存后权限 0600。
- **验收标准**：写入中断不截断旧 config；保存后的文件 mode 为 0600。

#### M10-P1-PYTEST-TIMEOUT

- **主要文件**：
  - `pyproject.toml:105-112`
  - `pyproject.toml:176-178`
  - `tests/agent/skills/test_lock_order.py:87`
  - `tests/agent/skills/test_concurrency.py:163`
- **目标**：安装并启用 `pytest-timeout`，或把 mark 改成测试内部显式 timeout；unknown marks 应失败。
- **验收标准**：pytest collect 不再有 `PytestUnknownMarkWarning`。

#### M10-P1-CI-PYTHON-MATRIX

- **主要文件**：`.github/workflows/ci.yml`、`pyproject.toml:5-18`
- **目标**：CI 覆盖 3.11/3.12；如果实际只支持 3.13+，则同步收紧 project metadata。
- **验收标准**：CI matrix 与 `requires-python` / classifiers 一致。

#### M10-P1-MOCHAT-TESTS

- **主要文件**：`nanobot/channels/mochat.py`、`tests/channels/test_mochat_channel.py`
- **目标**：补充不依赖真实外部服务的 Mochat channel 测试。
- **验收标准**：覆盖 content normalization、mention/require_mention、buffer flush、cursor load/save、websocket 失败后 polling fallback、send HTTP 错误处理。

### 9.4 P2：中期可伸缩性、合约和多用户边界

| Task ID | 主题 | 代价 | 目标 |
|---|---:|---:|---|
| **M10-P2-API-CONTRACT-DOC** | API OpenAI-compatible subset 文档化 | M | 明确支持/不支持项，避免 contract drift |
| **M10-P2-WEBUI-WS-ACL** | WebSocket per-chat owner/ACL | M/L | 多用户/共享 token 部署下隔离 chat_id |
| **M10-P2-WEBUI-TOKEN-CSRF** | WebUI token scope / CSRF / query token 收敛 | M | state-changing route 迁 POST，减少 query token 暴露 |
| **M10-P2-SIGNED-MEDIA-TTL** | signed media TTL/session 绑定 | M | 签名 URL 泄露后的可访问窗口最小化 |
| **M10-P2-WEBFETCH-BYTE-CAP** | WebFetch 大响应 byte cap | M | text/html/image 下载按解压后大小截断 |
| **M10-P2-CHANNEL-MEDIA-HELPER** | channel inbound media 统一下载 helper | M | Slack/Feishu/DingTalk/WeCom 统一 streaming、size cap、content-type |
| **M10-P2-FILESYSTEM-ATOMIC-WRITE** | filesystem write/edit/apply_patch 原子写 | M | 降低写中断损坏用户文件风险 |
| **M10-P2-FILE-SCAN-BUDGET** | search/find/grep 全局预算 | S/M | max files/max dirs/max wall time/truncated marker |
| **M10-P2-TRANSCRIPT-REDUCER** | transcript replay reducer 拆分 + benchmark | L | 降低 WebUI 长线程 replay 复杂度 |
| **M10-P2-LIVE-FOLD-PARITY** | 前端 live fold 与后端 replay fixture 对齐 | L | 刷新视图与实时视图一致 |
| **M10-P2-WEBUI-MONOLITH-SPLIT** | Settings/Composer/Activity/App 拆分 | L/XL | 降低 bundle、re-render、维护成本 |
| **M10-P2-SESSION-METADATA-SCHEMA** | session metadata keys 集中 schema | M | 减少 metadata key drift |
| **M10-P2-SESSION-LOCK-OWNER** | 明确 session mutation lock owner | M/L | API/WebUI/channel/subagent 统一并发边界 |
| **M10-P2-MEMORY-DURABILITY** | memory history/cursor 原子性与恢复 | M | 崩溃后不漏处理/重复处理 memory history |

### 9.5 P3：长尾清理

| Task ID | 主题 | 代价 | 目标 |
|---|---:|---:|---|
| **M10-P3-TOOL-DISCOVERY-LAZY** | tool discovery lazy import | M | 降低启动成本和插件 import side effects |
| **M10-P3-CHANNEL-DISCOVERY-SMOKE** | channel discovery smoke tests | S/M | 每个 builtin channel 可发现/可加载语义明确 |
| **M10-P3-STATIC-CACHE** | WebUI static ETag/Cache-Control | S | 降低重复静态文件 read bytes |
| **M10-P3-TODO-BARE-EXCEPT-TRIAGE** | TODO/FIXME 与 bare except 清理分级 | M/L | 区分真实债务和历史噪音，减少异常吞噬 |
| **M10-P3-DEPRECATED-CONFIG-REMOVAL** | deprecated config 字段移除计划 | M | 清理 DreamConfig / ChannelsConfig 等历史兼容字段 |

### 9.6 推荐领取顺序

1. **第一批小 PR（最快降风险）**：
   - `M10-P1-API-LOG-REDACTION`
   - `M10-P1-MCP-TIMEOUT`
   - `M10-P1-PYTEST-TIMEOUT`
   - `M10-P1-DEPS-UPPER-BOUND`
   - `M10-P1-CI-FULL-RUFF`
2. **第一批安全 PR**：
   - `M10-P0-API-AUTH`
   - `M10-P1-SHELL-PROCESS-TREE`
   - `M10-P1-CONFIG-DURABLE-SECRET`
3. **第一批性能 PR / spec**：
   - `M10-P0-SESSION-SAVE`
   - `M10-P0-WEBUI-THREAD-PAGING`
   - `M10-P1-PROMPT-MEMORY-CACHE`
4. **第一批架构 PR**：
   - `M10-P1-TOOLCONTEXT-RUNTIME-STATE`
   - `M10-P2-SESSION-METADATA-SCHEMA`
   - `M10-P1-CONFIG-SCHEMA-SPLIT`（先写 spec/plan）
5. **WebUI 后续批次**：
   - `M10-P2-TRANSCRIPT-REDUCER`
   - `M10-P2-LIVE-FOLD-PARITY`
   - `M10-P2-WEBUI-MONOLITH-SPLIT`

### 9.7 不建议现在做的事

- 不建议一次性重写 `AgentLoop` / `AgentRunner`。
- 不建议把 WebUI 大组件拆分和 transcript 协议重构放在同一个 PR。
- 不建议在未完成 API 鉴权和 WebUI token scope 前扩大远程部署面。
- 不建议在未拆 `config.schema` 之前继续把新 provider/tool config 直接塞进 schema 底部。
- 不建议只按文件行数拆分；优先处理安全、性能、import cycle 和核心路径职责扩散。
