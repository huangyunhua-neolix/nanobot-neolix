# M1 Foundations 回顾

> 完成日期：2026-06-11 · PR #1（M1 主体 + 4 follow-ups + 2 YELLOW 修复）+ PR #2（`.agent/memory/` 记忆固化）
> 规模：47 commits / 28 files / +6628 −21 · 1183 agent + 4 integration + 1 webui 测试全绿 · ruff clean

## 与设计的偏差

总体落地与 [`specs/m1-foundations.md`](../specs/m1-foundations.md) 高度一致——4 个不变量没改、2 层锁结构（`threading.Lock` + `filelock.FileLock`）没改、WebUI bypass 的 `telemetry=None` 契约没改。
真正的偏差集中在「实施过程中发现 spec 写少了一句话」这一类，4 个 follow-up 全是文档/实现细节补全，**不是设计返工**：

- **#49 — RMW orphan-delete 必须按 writer-tag 分支**。spec 原表把 "entry 仅在 on_disk" 写成一条规则，但 `bump`（保留）和 `reconcile`（删除）的语义完全相反；不分开写会让后续读者把 invariant 4（reconcile 是唯一 orphan deleter）当成可推导出的结论而不是契约。
- **#50 — atexit single-shot 太激进**。最初 `register_atexit` 直接绑 `flush`；如果第一次拿不到 filelock 或 fsync 失败就静默丢数据。改为 `_atexit_flush` 一次重试 + `atexit_flush_skipped` WARN 升级，给运维一个可观测的失败信号。
- **#51 — `MagicMock(spec=True)` 的属性陷阱**。`estimate_prompt_tokens` 不在 `LLMProvider` 抽象上（运行时通过 `getattr(provider, "...", None)` 探测），spec=True 的 mock 会拒绝 `provider.X.return_value = ...`。修法是直接赋 MagicMock 实例，配套 4 个回归测试钉住契约。

## 代码评审里抓到的两个 YELLOW

- **`_failure_counts` 字典迭代竞态**——`_note_failure` 在快路径上无锁写，atexit reader 的 `dict(self._failure_counts)` 会撞上 `RuntimeError: dictionary changed size during iteration`。修法是把快照塞回已有的 `with self._lock:` 块里，零额外锁成本。
- **E3 multiprocess 测试 50 ms 头启动 flaky**——spawn 冷启动要重新 import nanobot + filelock + loguru，CI loaded 时常超过 100 ms，导致 WebUI worker 在 agent 还没写出 `.telemetry.json` 时就开始读，"并发"语义瓦解。改为 5 s 超时 poll `.telemetry.json` 存在 + agent 死亡早退。

## 给 M2 / M3 的遗产

1. **Telemetry 4 invariants 已锁死**。M2 的 `skill_manage` patch/delete 可以直接调 `telemetry.bump(name, "patches")`，无需重新论证语义。
2. **`get_auxiliary_client(config)` 已通**。M3 Curator 的 aux-model 审议有现成插点，不会污染主对话 cache。
3. **`.telemetry.json` schema_version + unknown-field 保留**。M3 加 Curator 元数据（最近一次审议时间、protect-list flag）不需要数据迁移。
4. **SubagentManager 转发父 telemetry**。子代理路径不会生成并行 `.telemetry.json` 文件——M2 复杂工作流安全。

## 流程教训

- **PR 提交本身踩了俩坑**：(a) macOS 钥匙串里 `gh:github.com` 是 go-keyring 包装的 blob 不是 token；(b) `huangyunhua-neolix/nanobot-neolix` 在 GitHub 元数据上是 `HKUDS/nanobot` 的 fork，浏览器 / `gh` 默认 PR base 指向 HKUDS。两个陷阱叠加，已固化为 `AGENTS.md` 铁律 + `.agent/memory/pr_submission_method.md`。
