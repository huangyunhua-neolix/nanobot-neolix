# M5 完成任务发现记录

## 项目上下文发现

- Roadmap `docs/hermes-evolution/roadmap.md` 标记 M5 当前状态为：M5.1 已实现；完整 M5.x 待续。
- Roadmap 剩余 M5 项：完整 semantic gate 4、PR-human gate 5、tool evolution、prompt/template evolution。
- 现有 `docs/hermes-evolution/specs/m5-darwinian-evolver.md` 是 M5.1 spec，明确 non-goal 包括 tool-description evolution、system-prompt evolution、full gate 4、full gate 5。
- 该 spec 建议后续拆分：M5.2 semantic-fidelity gate 4；M5.3 PR-human gate 5；M5.6 system-prompt/template evolution。

## 代码现状发现

- `main` HEAD `cc7add66` 已合入 `feature/m5-darwinian-evolver`，近期提交包括 optimizer adapter、offline harness、candidate validation、gate timeout、run CLI、M5.1 docs。
- `nanobot/evolve/` 已有 optimizer adapter、schemas、report、harness run path、PR artifacts。
- 仍有 M5 相关 TODO：
  - `nanobot/evolve/judges/calibration.py` real `JudgePool.score` 接入。
  - `nanobot/evolve/deploy.py` PR body diff stats 从 stub 改为真实 +/- counts。
  - `nanobot/evolve/harness.py` Gate 1 pass counts 和 record counts 仍是 synthetic placeholder。
- `docs/hermes-evolution/specs/m4-carry-forward.md` 标记 M5.1 已关闭 subprocess isolation、nondeterministic metric policy、gate ordering observation、gate timeout duty，但 full gate 4/5 仍 deferred。

## 用户澄清

- 2026-06-14：用户选择“完整 M5”：补齐 gate 4、gate 5，并先把演进面限定为 skills；tool/prompt 演进只落安全扩展点和文档，不做自动改工具/系统 prompt。
