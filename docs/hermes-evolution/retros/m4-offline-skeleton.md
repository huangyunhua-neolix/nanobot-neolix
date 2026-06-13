# M4 offline skeleton 回顾

> 完成日期：2026-06-12（PR https://github.com/huangyunhua-neolix/nanobot-neolix/pull/6）  
> Finish pass：2026-06-13（`feature/finish-m4-offline`）  
> 范围：离线进化骨架完成；真实 GEPA / Darwinian Evolver 留给 M5。

## 已落地

M4 建立了 `nanobot/evolve/` 离线进化骨架：共享 Pydantic base、评测数据模型、rubric / judge pool 类型、三道 deterministic gate、OfflineHarness skeleton、redaction pipeline、PR-only deploy helpers，以及 `nanobot evolve` CLI surface。

本 finish pass 补齐了 skeleton 使用面的缺口：`evolve init` 可初始化 M4 §4.1.1 workspace skeleton，`evolve report --manifest` 可读 manifest 并输出确定性摘要，`evolve apply --manifest` 可做 reduced-surface PR preview。Tier B/D 保持 M5 私有数据边界，只返回 typed refusal。

## 与原 M4 spec 的偏差

- `apply` 当前是 reduced-surface preflight，不实现 §4.4 full bundle export、`--output-dir`、`--force`、atomic swap、fcntl lock 或 deploy-package AST guard。
- Tier B/D loader 不在 M4 finish pass 中实现，避免绕过 §9 redaction / enablement / no-PII invariant。
- `pipeline.build_pipeline()` 仍是 M5 boundary，不接真实 GEPA optimize loop。

## 给 M5 的遗产

1. 实现真实 GEPA / Darwinian Evolver pipeline。
2. 接入真实 `JudgePool.score` 与 calibration corpus。
3. 实现 gates 4-5，并决定 nondeterministic gate metrics 如何进入 fitness。
4. 补全 §4.4 apply bundle export / atomic swap / `--force` 语义，或正式 amend M4 §4.4。
5. Review `specs/m4-carry-forward.md` 全部未关闭 entry，按各自 close criterion 关闭或升级。

## Carry-forward review

| Entry group | Status | Reason |
|---|---|---|
| `CF-t14-*` / run orchestrator follow-ups | OPEN → M5 | 真实 run orchestration / GEPA wiring 不属于 M4 finish pass。 |
| `CF-t16-*` / CLI/apply advisories | REVIEWED | 本 pass 补齐 `init` / `report` / reduced `apply`；full §4.4 bundle 仍留 M5。 |
| `CF-cc-a` / real `JudgePool.score` | OPEN → M5 | M4 只保留 type surface 与 calibration harness seam。 |
| GEPA fitness-signal / gate-ordering entries | OPEN → M5 | M4 未实现任何 GEPA optimization loop（既无 multi-round 也无 single-shot runtime）。§6.4.1 gate-ordering rationale 的修正条件（close criterion）依赖 M5 选定并实现具体的 GEPA 形态，当前条件不适用；在 M5 落地前无法关闭。 |
