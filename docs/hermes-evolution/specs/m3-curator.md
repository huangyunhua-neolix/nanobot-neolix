# M3 · Curator 设计 Spec

> **Milestone**：M3（运行时整理层）。属于 [Hermes 风格自我进化能力路线图](../roadmap.md) 的第三阶段。
>
> **状态**：设计已锁定（2026-06-13，brainstorming 通过；review 修订已合入本文）。
>
> **依赖**：M1 Foundations 与 M2 `skill_manage` 均已完成并合入 `main`。
>
> **非依赖**：M4/M5 离线进化不阻塞 M3；M3 不实现离线 GEPA/Darwinian Evolver。

## 0. 调研与决策出处

- 总体研究：[`docs/hermes-self-evolution.md`](../../hermes-self-evolution.md)
- 总路线图：[`roadmap.md`](../roadmap.md)，§3 表格 M3 行
- 上游 spec：[`m1-foundations.md`](./m1-foundations.md)、[`m2-skill-manage.md`](./m2-skill-manage.md)
- 本 spec 的 reviewed draft 曾写在本地 `docs/superpowers/specs/2026-06-13-m3-curator-design.md`；本文是入库 canonical 版本。

## 1. 目的

M3 增加一个运行时 Curator：读取 skill telemetry，生成可解释的 cleanup / consolidation proposal，并通过 `/curator` slash command 展示。第一版必须保守、可审计、默认 dry-run：只有显式 `--apply` 才能做真实变更，且真实变更只允许走 M2 已验证的 agent-tier 安全删除路径。

Curator 不是离线优化器，也不是自动重写技能的大模型 agent。它是 M1 telemetry 与 M2 `skill_manage` 之上的策略层。

## 2. 范围与非范围

### 2.1 M3 做（in-scope）

1. **Curator domain module**：新增 `nanobot/curator/`，拆分 telemetry adapter、确定性 policy、protect-list、aux deliberation、report formatting、apply orchestration。顶层包布局仿照 `nanobot/evolve/`：Curator 是横跨 agent runtime / command / config 的功能域，放在 `nanobot/curator/` 可避免 `policy.py` 反向依赖 `AgentLoop`。
2. **Telemetry snapshot read API**：使用并固定 `SkillTelemetry.snapshot() -> TelemetrySnapshot` 作为 Curator 唯一读取 telemetry 的 public API；如果当前实现已存在该方法，M3 负责把它纳入公开契约并补齐测试，不重复创建；raw `.telemetry.json` 文件读取只允许封装在 `SkillTelemetry` 内部。
3. **Phase 1 确定性状态机**：把 visible skills 分类为 `keep` / `protect` / `delete_candidate` / `merge_candidate` / `patch_candidate`。
4. **Dry-run 默认 + 首周强制 dry-run**：`/curator` 默认只打印 report；`/curator --apply` 才尝试 mutation；新配置默认进入自动首周强制 dry-run。
5. **Protect-list**：支持显式名称、简单 glob pattern、always-on metadata、非 agent origin、近期有效使用等保护规则。
6. **Aux-model 审议边界**：可选地用 M1 auxiliary provider 对高风险 proposal 给二次意见；aux 只能降低 confidence 或添加 warning，不能提升 apply eligibility。
7. **`/curator` slash command**：加入 help/palette，支持 dry-run/apply/json/include-protected，使用现有 command parser 风格。
8. **M3 apply 子集**：只允许 high-confidence agent-tier `delete_candidate` 被 apply；merge/patch proposal 在 M3 只 report，不自动执行。
9. **测试覆盖**：policy、telemetry snapshot、report、service apply、command registration/config/security boundary。

### 2.2 M3 不做（out-of-scope）

| 排除项 | 留给 |
|---|---|
| GEPA/Darwinian Evolver 接入 | M5 |
| 离线 eval datasets / judge pools / benchmark gates | M4/M5 |
| 自动后台定时 Curator | 后续 milestone |
| user-tier / builtin-tier / future hub-tier mutation | M3 永不做 |
| agent skill promote 到 user tier | 后续 milestone |
| LLM 自动重写 skill body | 后续 milestone 或 M5 |
| Dream fs tools 的最终下线 | Curator 安全性验证后的后续 milestone |
| WebUI Curator 页面 | 后续 UI milestone |

## 3. 复用的 M1/M2 基础

### 3.1 Skill origins and shadowing

`SkillsLoader.list_skills_with_shadows()` 是 M3 的权威 skill inventory，返回每个 visible skill 的：

- `name`
- `effective_origin` (`user` / `agent` / `builtin`)
- `shadowed_origins`
- `path`

M3 不重复用 raw path 推断 origin。所有 origin 判断都来自 `list_skills_with_shadows()`，apply 前还必须通过 M2 delete path 重新检查 tier。

### 3.2 Telemetry snapshot

`SkillTelemetry` 当前管理 `<workspace>/skills/.telemetry.json`，M3 使用并固定 read-only API（已存在则补齐契约与测试）：

```python
def snapshot(self) -> TelemetrySnapshot:
    """Return a read-only telemetry snapshot for Curator/reporting callers."""
```

契约：

- 获取与 `flush()` / `reconcile()` 兼容的一致视图；
- snapshot 包含当前进程内尚未 flush 的 dirty in-memory entries；调用者不需要先 `flush()` 才能得到最新 bump；
- 返回 schema version 与 entries；
- missing telemetry file 返回 empty snapshot，不产生 warning；
- corrupt telemetry 复用现有 `_safe_read_json()` 行为（备份 `.corrupted.<ts>` 并返回 empty snapshot），`/curator` report 增加 warning；
- entry `origin` 可能是 `user` / `agent` / `builtin` / `unknown`；`unknown` 必须按 non-agent 处理（protected/skip）；
- snapshot 是只读数据结构；Curator 不直接写 telemetry。

Telemetry entry 字段沿用 M1：

- `views`
- `uses`
- `patches`
- `entry_created_at`
- `last_view`
- `last_use`
- `origin`
- `shadowed`
- optional `tombstone`

### 3.3 Safe mutation path

M3 apply 必须复用 M2 安全路径，首选直接依赖：

```python
nanobot.agent.tools.skill_manage_ops.do_delete
```

M3 不直接 unlink `SKILL.md`。删除必须保持：

- agent-tier-only mutation；
- per-name / cross-process lock；
- path-escape defense；
- telemetry tombstone；
- structured reject。

`SkillTelemetry.bump(name, kind="delete")` 是 tombstone 分支：设置 entry 的 `tombstone: true`，不递增 counter；不存在 `deletes` counter。

## 4. 用户可见行为

### 4.1 `/curator` command grammar

支持：

```text
/curator
/curator --dry-run
/curator --apply
/curator --json
/curator --apply --json
/curator --include-protected
```

规则：

- 不接受 free-form instruction string；
- unknown flag 返回 usage；
- `--dry-run` 和 `--apply` 互斥；
- 无 flag 等价于 `--dry-run`，输出必须完全一致；
- `--dry-run` 是默认模式的显式写法，合法但可省略；
- `--json` 返回 deterministic JSON，供测试和未来 UI 使用；
- text mode 用 chat-readable report。

Parser 采用现有 built-in command 风格：对 `ctx.args.strip().split()` 做小型手写解析，不引入 `argparse`。

### 4.2 Command registration

必须按现有 `builtin.py` ritual 注册：

1. 在 `BUILTIN_COMMAND_SPECS` 增加：

   ```python
   BuiltinCommandSpec(
       "/curator",
       "Review skills",
       "Review skill telemetry and propose safe cleanup actions.",
       "scissors",
       "[--dry-run|--apply] [--json] [--include-protected]",
   )
   ```

2. 在 `register_builtin_commands()` 同时注册 exact 和 prefix：

   ```python
   router.exact("/curator", cmd_curator)
   router.prefix("/curator ", cmd_curator)
   ```

否则 `/curator --apply` 不会 dispatch。

### 4.3 Text report

Text report 使用模板化原因，禁止嵌入 skill body 或 description 原文。

Dry-run header：

```text
Curator report (dry-run)
Skills scanned: 12
Protected: 4
Proposals: 3
```

Apply header：

```text
Curator report (apply)
Skills scanned: 12
Protected: 4
Proposals: 3
```

Forced dry-run refusal header：

```text
Apply refused: curator is in forced dry-run window until 2026-06-20T00:00:00Z.
Curator report (dry-run)
```

Proposal item example：

```text
- delete_candidate old-debug-helper
  origin: agent
  confidence: high
  reason: zero_uses_after_views views=30 uses=0
  reason: stale_since_last_use days=45
  apply: eligible with /curator --apply
```

### 4.4 JSON report

JSON mode returns one object:

```json
{
  "mode": "dry_run",
  "skills_scanned": 12,
  "protected": 4,
  "proposals": [
    {
      "name": "old-debug-helper",
      "origin": "agent",
      "action": "delete_candidate",
      "confidence": "high",
      "reasons": [
        {"code": "zero_uses_after_views", "views": 30, "uses": 0},
        {"code": "stale_since_last_use", "days": 45}
      ],
      "protected": false,
      "apply_status": "eligible"
    }
  ],
  "warnings": []
}
```

`mode` values：

- `dry_run`
- `apply`
- `forced_dry_run`

`action` values：

- `keep`
- `protect`
- `delete_candidate`
- `merge_candidate`
- `patch_candidate`

`apply_status` values：

- `not_requested`
- `not_applicable`
- `eligible`
- `deleted`
- `skipped_protected`
- `skipped_non_agent`
- `skipped_unknown_origin`
- `skipped_missing`
- `skipped_low_confidence`
- `skipped_unsupported_action`
- `refused_forced_dry_run`
- `failed`

`reasons` 必须使用 closed template set（`code` + numeric/string parameters），不得包含 skill body、description 原文、chat snippet、file content excerpt 或 aux free-form rationale。Aux free-form rationale 只允许进入 `warnings` 的 sanitized summary，不能进入 per-proposal reason list。

Text mode metadata 使用 `render_as: "text"`。JSON mode 若现有 channel 没有 JSON render convention，则使用 `render_as: "text"` 并输出 pretty JSON fenced block；实现不得发明 channel-specific UI metadata。

## 5. Config schema

新增：

```python
class CuratorConfig(Base):
    enabled: bool = True
    forced_dry_run_until: str | Literal["auto"] = "auto"
    protect_list: list[str] = Field(default_factory=list)
    protect_patterns: list[str] = Field(default_factory=list)
    min_views_for_delete: int = 30
    max_uses_for_delete: int = 0
    stale_days: int = 30
    low_use_ratio: float = 0.02
    apply_delete_mode: Literal["auto_high", "manual_only"] = "auto_high"
    aux_deliberation: bool = False
```

并在 `AgentDefaults` 增加：

```python
curator: CuratorConfig = Field(default_factory=CuratorConfig)
```

Schema 规则：

- `CuratorConfig` 必须继承项目现有 `Base`，不要直接继承 `BaseModel`；
- camelCase alias 由 `Base.alias_generator=to_camel` 自动提供；不要给上述字段手写 `Field(alias=...)`；
- `forced_dry_run_until` 的 `"auto"` vs ISO-8601 UTC 判定由 `CuratorConfig` field validator 负责，不放到 service 层临时解析；
- `forced_dry_run_until == "auto"` 表示第一次运行 Curator 时进入 `now + 7 days` 的强制 dry-run window；实现可在 runtime 计算并在 report 中显示，也可在配置持久化机制存在后落盘；
- 非 `auto` 值必须是 ISO-8601 UTC 字符串，格式等价于 `YYYY-MM-DDTHH:MM:SSZ`；
- naive datetime、空字符串、非 UTC offset 全部 config validation error；
- parse failure 时 `/curator --apply` 必须拒绝 apply，并在 report warnings 中说明 config invalid；
- `aux_deliberation` 默认 `False`，避免默认无 `auxiliary.modelPreset` 时每次 command 都 warning；
- 当 `aux_deliberation=True` 但 `auxiliary.modelPreset is None`，静默跳过 aux，不 warning；只有配置了 preset 但 provider resolution/call 失败才 warning。

## 6. Deterministic proposal policy

### 6.1 Inputs

Policy receives:

- visible skills from `SkillsLoader.list_skills_with_shadows()`;
- telemetry from `SkillTelemetry.snapshot()`;
- current UTC `now` passed explicitly;
- `CuratorConfig`;
- frontmatter metadata from `SkillsLoader.get_skill_metadata(name)`.

Policy is pure: no file writes, no provider calls, no command imports.

### 6.2 Protection policy

A skill is protected when any condition is true:

1. `effective_origin != "agent"`；
2. telemetry origin is `unknown`；
3. skill name appears in `curator.protectList`；
4. skill name matches `curator.protectPatterns` (`fnmatch`, not regex)；
5. metadata marks it always-on (`always: true` or `metadata.nanobot.always: true`)；
6. `uses > max_uses_for_delete`；
7. `last_use` is newer than `stale_days`。

Protected skills produce `protect` or `keep` only, never mutation proposals.

### 6.3 Delete candidate rule

A skill may become `delete_candidate` only when all are true:

1. effective origin is `agent`；
2. telemetry origin is `agent`；
3. not protected；
4. telemetry has at least `min_views_for_delete` views；
5. uses are `<= max_uses_for_delete`；
6. `entry_created_at` exists and `now - entry_created_at >= stale_days`；
7. `last_use` is absent or older than `stale_days`；
8. patch evidence is safe:
   - if `patches == 0` → pass；
   - if `patches > 0` and frontmatter `last_patched_at` parses and is older than `stale_days` → pass but max confidence is `medium`；
   - if `patches > 0` and `last_patched_at` is missing/malformed → max confidence is `medium`；
   - if `last_patched_at` is newer than `stale_days` → no delete candidate；
9. if `shadowed_origins` is non-empty, deletion would unmask lower-tier content; downgrade max confidence to `medium` in M3 rather than auto-delete.

Confidence:

- `high` only when all delete conditions pass, `uses == 0`, `patches == 0`, no `shadowed_origins`, and stale age passes threshold；
- `medium` for delete candidates with patch history or shadow-unmasking；
- `low` for weak signals; low delete candidates are report-only。

Only high-confidence delete candidates are eligible for M3 apply when `apply_delete_mode == "auto_high"`.

### 6.4 Merge candidate rule

A skill may become `merge_candidate` when:

- effective origin is `agent`；
- not protected；
- another visible non-protected skill has Jaccard similarity >= 0.6 over lowercased tokens from skill name + description；
- neither candidate is high-confidence delete；
- deletion would not be safer than merge.

M3 reports merge proposals only. It does not auto-merge. Merge/patch reasons may include numeric similarity scores and boolean flags, but must not include token lists or description-derived strings.

### 6.5 Patch candidate rule

A skill may become `patch_candidate` when:

- effective origin is `agent`；
- not protected；
- telemetry `patches >= 3`；
- `uses == 0` or `uses / max(views, 1) < low_use_ratio`；
- frontmatter has `last_patched_at` or telemetry has patch count evidence.

M3 reports patch proposals only. It does not auto-rewrite skill bodies.

## 7. Apply semantics

### 7.1 Dry-run invariant

`/curator` without `--apply` must not mutate files or telemetry.

Tests must prove:

- no files removed in default mode；
- no telemetry tombstone added in default mode；
- default and `--dry-run` produce identical report mode；
- `--apply` is refused while forced dry-run is active。

### 7.2 Apply status mapping

| Proposal state | Dry-run status | Apply status |
|---|---|---|
| protected skill | `not_applicable` | `skipped_protected` |
| non-agent origin | `not_applicable` | `skipped_non_agent` |
| unknown origin | `not_applicable` | `skipped_unknown_origin` |
| missing skill at apply time | — | `skipped_missing` |
| high-confidence delete candidate | `eligible` | `deleted` or `failed` |
| medium/low delete candidate | `not_requested` | `skipped_low_confidence` |
| merge candidate | `not_requested` | `skipped_unsupported_action` |
| patch candidate | `not_requested` | `skipped_unsupported_action` |
| forced dry-run active | `refused_forced_dry_run` | `refused_forced_dry_run` |

### 7.3 Applyable actions in M3

M3 apply supports only high-confidence `delete_candidate` for agent-tier skills.

Before each delete apply:

1. re-read visible skill entry；
2. re-check effective origin is still `agent`；
3. call `skill_manage_ops.do_delete(...)`；
4. map structured reject to `apply_status`。

Race note：proposal generation and apply are separated by time. If origin changed between them, apply must abort with `skipped_non_agent` / `skipped_unknown_origin` / `skipped_missing` as appropriate. The M2 delete path performs its own tier check under its lock; M3 must not treat stale proposal state as authority. If `do_delete` reports success, Curator records `deleted`; M2 treats telemetry tombstone bump failure as operational warning, not failed delete, so Curator should surface that warning when available but must not reclassify the deletion as failed.

### 7.4 Partial failure

Apply is best-effort per proposal：

- one failed delete does not stop later proposals；
- failure appears in warnings and per-proposal `apply_status`；
- command returns a report, not raw exception text。

## 8. Aux-model deliberation

### 8.1 Purpose

Aux deliberation is a second opinion for risky proposals. It cannot create proposals and cannot raise apply eligibility.

### 8.2 Invocation boundary

Invoke aux only when all are true:

- `curator.auxDeliberation` is true；
- `agents.defaults.auxiliary.modelPreset` resolves to a configured model preset；
- proposal action is `delete_candidate` / `merge_candidate` / `patch_candidate`；
- deterministic policy already allowed the proposal to exist。

Aux call must use a fresh provider client resolved from auxiliary config. It must not enter main session history, main provider cache, or the active user turn's message list.

If `aux_deliberation=True` but `modelPreset is None`，skip aux silently. If preset exists but provider construction/call fails, keep deterministic proposal and add warning.

### 8.3 Aux invocation contract

M3 adds a small helper, e.g.:

```python
async def deliberate_proposal(
    *,
    provider_factory: AuxiliaryProviderFactory,
    proposal: CuratorProposal,
    timeout_s: float = 30.0,
) -> AuxDeliberationResult:
    ...
```

Implementation plan must choose the exact factory symbol after checking provider factory patterns, but the contract is fixed:

- one-shot request；
- hard timeout default 30s；
- no tool calls；
- max output small enough for strict JSON；
- provider error / timeout becomes warning and leaves deterministic proposal unchanged。

### 8.4 Untrusted skill-body framing

Skill body, description, and telemetry rationale are data, not instructions.

Aux prompt must:

1. use an explicit system message that says only the JSON payload is data to analyze；
2. wrap any skill body excerpt in `<UNTRUSTED_SKILL_BODY>...</UNTRUSTED_SKILL_BODY>`；
3. strip or escape `<system>`, `</system>`, `<assistant>`, `</assistant>`, `<user>`, `</user>` and similar role-like tags before sending, including provider-specific delimiters used by the selected aux preset such as `<|im_start|>`, `<|system|>`, `[INST]`, and `[/INST]`；
4. never include full skill body unless necessary; prefer name/metadata/telemetry only；
5. include tests where injected text like `IGNORE PREVIOUS INSTRUCTIONS` cannot flip a deterministic delete candidate to keep or high-confidence apply。

### 8.5 Aux output contract

Aux output must parse through a strict Pydantic model with `extra="forbid"`:

```python
class AuxDeliberationResult(BaseModel):
    verdict: Literal["support", "caution", "reject"]
    rationale: str = Field(max_length=500)
    confidence_delta: Literal["same", "decrease"]
```

No `increase` value exists. Deterministic confidence is the apply ceiling. Aux may only：

- leave confidence unchanged；
- decrease confidence；
- add sanitized warning/rationale；
- mark proposal as caution/reject for reporting。

Invalid aux JSON becomes warning and leaves deterministic confidence unchanged.

## 9. Architecture

### 9.1 Files to add or modify

```text
nanobot/curator/__init__.py
nanobot/curator/models.py
nanobot/curator/telemetry.py
nanobot/curator/policy.py
nanobot/curator/deliberation.py
nanobot/curator/report.py
nanobot/curator/service.py
nanobot/agent/skills_telemetry.py
nanobot/config/schema.py
nanobot/command/builtin.py
tests/curator/test_policy.py
tests/curator/test_report.py
tests/curator/test_service_apply.py
tests/curator/test_telemetry_snapshot.py
tests/curator/test_deliberation.py
tests/command/test_curator_command.py
```

No separate `nanobot/curator/config.py` is required unless implementation discovers the schema file becomes too large; config lives in `nanobot/config/schema.py` with other agent defaults.

### 9.2 File responsibilities

- `models.py`：`CuratorProposal`、`CuratorReport`、`CuratorWarning`、reason enum/template models、apply status enums。
- `telemetry.py`：adapter from `SkillTelemetry.snapshot()` to policy inputs；no raw file writes。
- `policy.py`：deterministic proposal engine；pure code。
- `deliberation.py`：aux provider adapter + strict output parsing + prompt injection hardening。
- `report.py`：deterministic text/JSON formatting。
- `service.py`：orchestration: load inputs, policy, optional deliberation, optional apply。
- `skills_telemetry.py`：add read-only `snapshot()` API。
- `schema.py`：add `CuratorConfig` and `AgentDefaults.curator`。
- `command/builtin.py`：parse `/curator` args, register command, return `OutboundMessage`。

### 9.3 Dependency direction

```text
command/builtin.py
  -> curator/service.py
      -> curator/policy.py
      -> curator/report.py
      -> curator/deliberation.py
      -> curator/telemetry.py
      -> SkillTelemetry.snapshot / SkillsLoader / skill_manage_ops.do_delete
```

`policy.py` must not import command code, provider code, or filesystem write helpers.

## 10. Prompt-cache / privacy / security constraints

- Curator reports are command responses, not stable system-prompt additions。
- No new stable prompt section is added in M3。
- Warnings belong in command output or volatile runtime context only。
- Skill body / description / telemetry are local workspace data, not trusted instructions。
- Report `reasons` use closed templates; no skill body/description snippets。
- JSON report is safe to log: no file content, no chat snippets, no aux raw prompt/output。
- Protect-list config is local configuration, not model output。
- Model output cannot override tier/provenance gates。
- Aux call uses auxiliary provider only, not main turn history/cache。

## 11. Testing plan

### 11.1 Policy tests

Cover：

- user/builtin/unknown origins become protected and never delete candidates；
- agent skill with high views, zero uses, stale `entry_created_at`, stale/missing `last_use`, zero patches becomes high-confidence delete candidate；
- fresh skill with high views and zero uses is not delete candidate；
- recent use prevents deletion；
- protect-list and glob patterns prevent deletion；
- always-on metadata prevents deletion；
- patch count with missing/malformed `last_patched_at` caps confidence at medium；
- `shadowed_origins` caps confidence at medium；
- merge candidate Jaccard threshold works；
- patch churn candidate is report-only。

### 11.2 Telemetry snapshot tests

Cover：

- missing telemetry file returns empty snapshot；
- corrupt telemetry becomes empty snapshot + warning path；
- origin `unknown` is preserved in snapshot and treated protected by policy；
- snapshot includes in-memory dirty entries after bump without requiring callers to flush first。

### 11.3 Report tests

Cover：

- text output deterministic；
- JSON output stable keys and enum values；
- no reason includes description/body snippets；
- forced dry-run header and `mode` are stable；
- warnings included；
- default and `--dry-run` modes match。

### 11.4 Service/apply tests

Cover：

- dry-run does not mutate files or telemetry；
- forced dry-run refuses apply；
- high-confidence agent delete calls injected delete operation；
- medium delete skips as `skipped_low_confidence`；
- merge/patch skip as `skipped_unsupported_action`；
- missing skill maps to `skipped_missing`；
- origin change between proposal and apply is rechecked and skipped；
- failed delete records warning and continues。

### 11.5 Deliberation tests

Cover：

- `aux_deliberation=False` makes no provider call；
- `modelPreset=None` skips silently；
- provider timeout/failure adds warning and keeps deterministic proposal；
- aux cannot increase confidence；
- invalid/extra-field JSON rejected；
- injected `IGNORE PREVIOUS INSTRUCTIONS` / fake `<system>` tags do not alter deterministic apply eligibility；
- skill body/description not emitted in report reasons。

### 11.6 Command/config tests

Cover：

- `/curator` exact and `/curator --apply` prefix dispatch；
- `BUILTIN_COMMAND_SPECS` and help/palette include `/curator`；
- unknown flags return usage；
- `--dry-run` and `--apply` conflict；
- command output uses `render_as: text`；
- `CuratorConfig` camelCase aliases work via `Base` without explicit aliases；
- `forcedDryRunUntil` validates ISO-8601 UTC and rejects naive timestamps。

## 12. Acceptance criteria

M3 is complete when：

1. `SkillTelemetry.snapshot()` exists and Curator uses it as the only telemetry read API。
2. `/curator` exists, is registered exact+prefix, and defaults to dry-run。
3. First-week forced dry-run is represented by `forced_dry_run_until="auto"` semantics and refuses apply while active。
4. Curator report lists scanned skill count, protected count, proposals, safe template reasons, warnings, and apply eligibility。
5. Deterministic policy never proposes mutation for user/builtin/unknown origins。
6. Protect-list, recent use, fresh `entry_created_at`, always-on metadata, patch churn, and shadow-unmasking prevent or downgrade delete eligibility as specified。
7. `--apply` can delete only high-confidence agent-tier delete candidates。
8. Delete apply preserves M2 tombstone semantics by reusing `skill_manage_ops.do_delete` or an equivalent shared safe path。
9. Apply rechecks origin at mutation time and maps missing/changed skills to structured `apply_status`。
10. Merge/patch candidates are visible but not automatically applied。
11. Aux deliberation is optional, uses auxiliary provider isolation, treats skill content as untrusted data, and cannot increase apply eligibility。
12. Reports do not include skill body, description snippets, chat snippets, or raw aux output。
13. Tests cover policy, telemetry snapshot, report, service apply, aux deliberation, command registration, and config behavior。
14. Roadmap is updated to show M3 completion only after implementation and review, not at spec time。

## 13. 实施计划提示

- 先做 models + pure policy，再接 service/apply，再接 command。
- `SkillTelemetry.snapshot()` 需要先设计 dirty in-memory entries 与 on-disk entries 的合并语义；不要让 Curator 直接读 private fields。
- `forced_dry_run_until="auto"` 的持久化可以后置；M3 只需保证默认不会允许首周 apply。
- Aux deliberation 可以先接一个 adapter seam + tests；如果 provider factory 需要较大改动，plan 应拆成单独任务。
- 不要在 M3 引入后台调度或 WebUI。
