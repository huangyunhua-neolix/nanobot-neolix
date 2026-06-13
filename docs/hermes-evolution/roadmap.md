# Hermes 风格自我进化能力 —— 总路线图

> **文档性质**：5-milestone 路线图 / 决策记录。本身**不是单个 spec**，而是把"全都要"这一个超大需求拆成可独立 spec→plan→implementation 的多周期总览。每个 milestone 自己有 spec、plan、progress 文档，本文负责导航和锁顺序。
>
> **状态**：路线图已锁定（2026-06-11）。**M1 已完成（2026-06-11，PR #1 + #2）**。**M2 已完成（2026-06-12，PR #4）**。**M4 离线骨架已完成并合入 main（2026-06-12，PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6）**。M3 待启动，M5 待 M4 骨架之上继续实现真正离线进化。
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
| **M3** | Curator Phase 1(确定性状态机) + Phase 2(aux-model 审议) + dry-run + `/curator` 命令 + protect-list | M2 | 待启动 | `specs/m3-curator.md` | `plans/m3-curator.md` | — |
| **M4** | 离线进化骨架：`nanobot/evolve/` skeleton（shared Pydantic base、评测数据模型、rubric/judge pool 类型、3 道 deterministic gate、OfflineHarness、redaction pipeline、PR-only deploy helpers）+ `nanobot evolve` CLI surface（init/report/apply） | M1 | ✅ 已完成 (2026-06-12, PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6, HEAD f8a496bf) | [`specs/m4-offline-skeleton.md`](specs/m4-offline-skeleton.md) | [`plans/m4-offline-skeleton.md`](plans/m4-offline-skeleton.md) | [`retros/m4-offline-skeleton.md`](retros/m4-offline-skeleton.md) |
| **M5** | 接入外部 Darwinian Evolver CLI + AGPL 许可隔离 + PR-only 部署 + 完整 5 道闸门 | M4 | 待启动 | `specs/m5-darwinian-evolver.md` | `plans/m5-darwinian-evolver.md` | — |

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
- M3: *待启动*
- M4: ✅ 骨架已完成，finish pass 补齐 `evolve init` / `report` / reduced `apply`（完整 §4.4 bundle export / atomic swap / `--force` 留 M5） — 详见 [`retros/m4-offline-skeleton.md`](retros/m4-offline-skeleton.md)
- M5: *待启动*

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
- [ ] 6. **M3 启动（需要 M2 telemetry 样本积累；独立于 M4/M5）**
- [ ] 7. **M5 Darwinian Evolver（M4 骨架之上接真实 GEPA + 完整闸门）**
