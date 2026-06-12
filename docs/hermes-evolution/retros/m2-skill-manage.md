# M2 skill_manage 回顾

> 完成日期：2026-06-12 · PR #4（15 个 plan task + 4 轮 reviewer fix + 1 处 spec erratum）
> 规模：37 commits / 36 files / +7110 −37 · R4 149 passed / 1 platform-skipped · R5 ruff 0 issue · R6 仅 3 个非 M2 触及文件的 pre-existing failure

## 与设计的偏差

整体落地与 [`specs/m2-skill-manage.md`](../specs/m2-skill-manage.md) 高度一致——四动词模型（create/edit/patch/delete）、5 层锁顺序（workspace `.create.lock` → skill_inproc → skill_filelock → telemetry _flush_lock → telemetry filelock）、Dream `provenance_tag="dream"` 注入、ContextBuilder 单例 telemetry fan-out 都没改。
**真正的偏差有 4 处，全部已在 spec §6 / progress doc 留档**：

- **D1 — `_validate_provenance_tag` 必须接受 `"dream"`**。t-07 实现的 accept sweep 只覆盖 `"agent" | "subagent:<id>"`，与 spec §3.2 enum 不一致；t-12 register Dream tool 时立刻 ValueError。修法是 t-12 顺手补全 enum，并在 reject sweep 测试里固化 `"dream"` 不在黑名单。
- **D2 — Dream scope 的实际字面量是 `"memory"` 不是 `"dream"`**。Plan §t-13 写的是 `"dream"`，但生产代码 (`filesystem.py:164/401/726`、`test_dream_tools.py:11`) 一直用 `"memory"`。t-13 实现选择了与生产对齐的 `"memory"`，scope 集合最终是 `{"core", "subagent", "memory"}`。Plan 词汇而非 spec 词汇——spec 本身没指定字面量。
- **D3 — `SkillManageTool` 没有 `list` verb**。t-14 reviewer 让把 Loop 1 的内部 `_list_with_shadows(workspace)` 替换为公开 verb，但 `SkillManageVerb` 只有 CREATE/EDIT/PATCH/DELETE。fix-implementer 改用 `SkillsLoader.list_skills_with_shadows()`，这才是 production agent loop 真正调用的公开 listing 入口（M1 早就提供，`_list_with_shadows` 自身就是它的 thin wrapper）。
- **Errata 1 — `do_create` 必须在 layer-2 锁内调用 `telemetry.reconcile`**。t-10 review 暴露的 production bug：M1 invariant 3 规定 `_rmw_merge(writer="bump")` 跳过 `disk_entry is None` 的 entry，但 spec §7.2 step 1 假设 lazy-bump-init 会先把 entry 种好。结果第一次 edit/patch 直接把 counter 永久丢在内存里。修法是 `do_create` 物理写盘成功后立刻 reconcile 已知 entries，把 zero-counter entry 落盘——既符合 invariant 3，又在 spec §7.2 step 3 的 "create-time 立刻 reconcile" 禁令上打了一个明确的 erratum 补丁。

## 代码评审里抓到的 4 轮 YELLOW 修复

- **t-08 round-2（8 个 YELLOW）**：security + data-integrity 收紧。最关键的是 `_cleanup_empty_skill_dir` 必须 unlink layer-2 `.lock` sentinel——否则 layer-2 fd_file_lock 总是先创建 `.lock`，rmdir 永远成功不了。
- **t-12 yellows（2 个 YELLOW）**：`test_dream_e2e.py` 的 substring 断言被收紧——frontmatter 检查改用 production parser `_parse_skill`（不是 `"created_by: dream" in text`），callsite chain 检查改用 `ast.parse` + `ast.unparse`（不是 `"store = agent.context.memory" in source`）。
- **t-14 yellows（2 个 YELLOW）**：Loop 2 的 `== {} or all(v == v ...)` 同义反复（`v == v` 永真）替换为严格 `== {}`；Loop 1 改走 D3 提到的公开 listing 入口。
- **t-15 R5（1 ruff I001）**：`nanobot/agent/subagent.py` 的 import-sort 失败实际起源于 M1 commit `c26ba082`，但 M2 t-11 修改这个文件后 ruff 才暴露。t-15 顺手 `ruff --fix`，0 logic change。

## 流程教训

- **多轮收敛不是过度工程**——4 轮 fix 一共改了 8+2+2+1=13 个 YELLOW，全部是 reviewer 帮我们抓到的、单测覆盖不到但生产会出问题的细节。如果只跑一次 review pass，这些都会在 PR review 阶段被外部审查者要求回头改。
- **Spec ↔ implementation 的双向校验关键**——t-10 review 抓出来的 lost-counter bug 是 spec 假设错（lazy-bump-init 不存在），不是实现写错。fix 是「先打 erratum 改 spec，再 patch 代码」而不是「藏起来」。这条流程在 §6 留下 Carried-forward 3 永久档案。
- **多个 fork 的 worktree 隔离机制（`.claude/worktrees/feature+m2-skill-manage-t<N>`）撑住了 7 个并行组**。最复杂的 Group 7 [t-09, t-10, t-11] 三个 worker 并发跑，最后只在 `test_rate_cap.py` 的 `test_subagent_independent_quota` 上撞到一次重名冲突——靠 conflict-resolver subagent 单线程 rename 解掉。没有任何一次 parent worktree 污染。

## 给 M3 的遗产

1. **provenance frontmatter 已是一等公民**。M3 Curator 删 / 合并动作可以直接读 `created_by` / `patched_by` 决定权限——`"bundled"` / `"hub"` 永不可动，`"agent"` / `"subagent:<id>"` / `"dream"` 都是合法 mutate target。
2. **telemetry tombstone bump 已通**。M3 删 skill 后必须先 `bump(name, kind="delete")` 再写盘，reconcile 阶段才会清理 orphan entry。流程在 spec §7.2 + Errata 1 + `do_delete` 完整闭环。
3. **rate-cap 的 per-turn / per-subagent 隔离**。M3 Curator 的 aux-model 审议哪怕 spawn 多个并发判断子任务，也不会和主 agent 共享 mutation 配额——每个 subagent 拿到全新 `_SubagentRuntimeState`。
4. **`SkillsLoader` 仍是无缓存目录扫描**（spec §9.1.2、§10.4）。M3 如果要加 turn-scoped cache，会撞上 `test_cache_invariant.py` 的 `_TurnSkillsCache` 测试 wrapper——届时把 wrapper 替换为 production cache 的契约钉子即可。

## 待 hygienic 跟进

R6 报告里有 3 个 pre-existing failure，全在 M2 没碰过的文件里（已用 `git log <base>..HEAD -- <paths>` 确认 empty）：

- `tests/cli_apps/test_service.py` × 2 ——env failure (`pip` / `uv` not on PATH)
- `tests/webui/test_mcp_presets_api.py` —— `assert False is True`
- `tests/cli/test_commands.py::test_gateway_uses_configured_port_when_cli_flag_is_missing` —— Rich ANSI 颜色码插入断言串

按 plan §t-15「不能 regress」语义这些不阻断 M2 ship，但应作为单独 hygiene PR 处理。
