# Technical Debt Audit — 2026-06-13

> Automated scan of the nanobot-neolix repository.
> Status: REVIEWED — architect review appended (see §7).

---

## 1. Critical (Fix ASAP)

### 1.1 SettingsView.tsx — 6,016 lines

- **File**: `webui/src/components/settings/SettingsView.tsx`
- **Problem**: Monolithic React component; unreviewable, untestable at this size.
- **Recommendation**: Split into sub-components per settings section (General, Providers, Channels, MCP, Skills, etc.). Extract shared form logic into hooks.

### ~~1.2 API Server — Zero Test Coverage~~ [CORRECTED by architect review]

- **File**: `nanobot/api/server.py`
- **Original claim**: Zero test coverage.
- **Correction**: Actually has ~1,294 lines of tests across 3 files (`test_openai_api.py`, `test_api_stream.py`, `test_api_attachment.py`). Coverage exists but may have gaps in auth-guard edge cases and error paths.
- **Revised recommendation**: Audit existing tests for auth/error coverage, not greenfield test writing.

### 1.3 CLI commands.py — 2,076 lines

- **File**: `nanobot/cli/commands.py`
- **Problem**: Single-file CLI entry point. Hard to navigate, test in isolation, or extend.
- **Recommendation**: Split by subcommand group (gateway, config, channel, skill, etc.) into `cli/cmd_*.py` modules.

### 1.4 openai Dependency Unpinned Upper Bound

- **File**: `pyproject.toml` — `openai>=2.8.0`
- **Problem**: Core LLM provider dependency with no upper bound. A future major version bump could silently break the provider layer.
- **Recommendation**: Pin to `openai>=2.8.0,<5.0.0` (or next known compatible major).

---

## 2. High Priority

### 2.1 Bare Exception Handling (30+ files)

- **Locations**: `agent/runner.py`, `agent/loop.py`, all channel implementations, webui handlers.
- **Problem**: Overly broad `except Exception:` makes it impossible to distinguish expected failures from bugs. Errors may be silently swallowed.
- **Recommendation**: Narrow to specific exception types; at minimum `log.warning()` in catch blocks. Prioritize runner.py and loop.py first (core path).

### 2.2 M5-Blocking TODOs (2 items)

| Location | Description |
|----------|-------------|
| `nanobot/evolve/judges/calibration.py:69` | `TODO(m4-followup CF-cc-a)`: Wire real `JudgePool.score` entry point |
| `nanobot/evolve/deploy.py:294-296` | `TODO(M5)`: Replace stub diff stats with real +/- counts from candidate diff |

### 2.3 Schema Circular Dependency Workaround

- **File**: `nanobot/config/schema.py:555-579`
- **Problem**: Uses `sys.modules[__name__]` dynamic injection + `model_rebuild()` to work around circular dependency between schema and tool configs.
- **Recommendation**: Decouple by introducing a `nanobot/config/tool_configs.py` module that both schema and tools can import without cycles.

### 2.4 Untested Large Modules

| Module | Lines | Test Coverage |
|--------|-------|---------------|
| `nanobot/apps/cli/service.py` | 1,263 | 0% |
| `nanobot/audio/transcription.py` | ~300 | 0% |
| `nanobot/api/server.py` | ~400 | 0% |

### 2.5 Silent Exception Suppression

- **File**: `nanobot/agent/tools/skill_manage_ops.py` (lines 287-294, 698-707)
- **Problem**: `except OSError: pass` on file unlink/rmdir. Can mask permissions issues, disk-full, or race conditions.
- **Recommendation**: Log at `debug` level minimum; consider `contextlib.suppress(FileNotFoundError)` for the specific case.

---

## 3. Medium Priority

### 3.1 Large Python Files (15 files > 1,200 lines)

```
2,076  cli/commands.py
1,984  channels/feishu.py
1,864  webui/transcript.py
1,802  agent/loop.py
1,699  providers/image_generation.py
1,586  channels/weixin.py
1,554  agent/runner.py
1,482  providers/openai_compat_provider.py
1,472  channels/telegram.py
1,434  webui/settings_api.py
1,402  channels/signal.py
1,385  cli/onboard.py
1,318  webui/mcp_presets_api.py
1,263  apps/cli/service.py
1,178  channels/websocket.py
```

**Strategy**: Prioritize splitting files that are frequently edited (high churn = high merge-conflict risk). Use `git log --format='' --name-only -- <file> | wc -l` to measure.

### 3.2 Large Frontend Files

| File | Lines |
|------|-------|
| `webui/src/components/settings/SettingsView.tsx` | 6,016 |
| `webui/src/components/thread/ThreadComposer.tsx` | 2,514 |
| `webui/src/components/thread/AgentActivityCluster.tsx` | 1,878 |
| `webui/src/App.tsx` | 1,591 |
| `webui/src/hooks/useNanobotStream.ts` | 1,111 |

### 3.3 Type Ignore Pragmas (29 occurrences, 20 files)

- Most are legitimate (Pydantic model_rebuild, dynamic dispatch).
- Worth auditing: `evolve/pipeline.py`, `evolve/judges/rubric.py`, `webui/mcp_presets_api.py`.
- Some may be resolvable by improving type stubs or using `cast()`.

### 3.4 Deprecated Config Fields Still Present

- **File**: `nanobot/config/schema.py`
- Fields: `DreamConfig.max_batch_size`, `DreamConfig.max_iterations`, `DreamConfig.annotate_line_ages`, `ChannelsConfig.transcription_provider`, `ChannelsConfig.transcription_language`
- **Status**: Marked deprecated but not removed. Need migration path + removal timeline.

### 3.5 Legacy Session Migration Code

- **File**: `nanobot/session/manager.py` (lines 401, 413-415)
- **Problem**: `get_legacy_sessions_dir()` / `_get_legacy_session_path()` backward compat layer for old global `~/.nanobot/sessions/` location.
- **Question**: How many users are still on the old layout? Can we set a removal date?

---

## 4. Low Priority / Known & Tracked

### 4.1 Carry-Forward Debt Register (10+ entries)

- **File**: `docs/hermes-evolution/specs/m4-carry-forward.md`
- Well-structured with close criteria. No action needed beyond continuing the practice.

### 4.2 Bridge Pre-release Dependency

- `@whiskeysockets/baileys@7.0.0-rc.9` — WhatsApp bridge uses a release candidate.
- Low risk (bridge is optional), but monitor for stable release.

### 4.3 Hardcoded Magic Numbers

- Skill quotas: `max_mutations_per_turn=5`, `max_body_bytes=65536`, `max_agent_skills=200`
- Workspace state limit: `_MAX_STATE_FILE_BYTES = 128 * 1024`
- Image provider aspect ratios (StepFun)
- **Note**: Most have sensible defaults; consider making configurable only if users request it.

---

## 5. Positive Findings (Keep Doing)

- Formal carry-forward debt tracking with objective close criteria
- Strong test coverage for core modules (agent: 70+, channels: 39, providers: 42 test files)
- No vendored code — proper dependency management
- Modern Python patterns (`__future__ annotations`, Pydantic v2, asyncio throughout)
- `TYPE_CHECKING` guards prevent runtime circular imports
- Shell tool has complete sandbox + deny-list security boundary
- No `%`-style formatting, no `import *`, no deprecated stdlib usage

---

## 6. Suggested Prioritization

| Sprint | Items | Estimated Effort |
|--------|-------|-----------------|
| Next | Pin openai upper bound (1.4) | 5 min |
| Next | Add api/server.py smoke tests (1.2) | 1-2 days |
| Next | Narrow top-5 bare exception handlers (2.1) | 1 day |
| Soon | Split SettingsView.tsx (1.1) | 2-3 days |
| Soon | Split cli/commands.py (1.3) | 1 day |
| Soon | Resolve M5 TODOs (2.2) | part of M5 work |
| Backlog | Decouple schema circular dep (2.3) | 0.5 day |
| Backlog | Remove deprecated config fields (3.4) | 0.5 day |
| Backlog | Audit type:ignore pragmas (3.3) | 0.5 day |

---

---

## 7. Architect Review (2026-06-13)

> Reviewer: fc-architect (consultation mode)
> Verdict: Audit is directionally correct but has one factual error and misses the 3 most architecturally dangerous debts.

### 7.1 Corrections to Original Audit

| Item | Issue |
|------|-------|
| **1.2** API server "zero coverage" | **Factually wrong.** 3 test files exist (~1,294 lines). Revised in §1.2 above. |
| **2.1** "Silently swallowed" exceptions | **Overstated.** Most bare `except Exception` in runner.py/loop.py are followed by `logger.exception()`. Real concern: they catch too broadly (masks specific failure modes), not that they're silent. |

### 7.2 Critical Missing Items (not in original scan)

#### A. WebSocketChannel ↔ WebUI Bidirectional Coupling (CRITICAL)

- **File**: `nanobot/channels/websocket.py` (1,178 lines)
- **Problem**: Imports **9 different** `nanobot.webui.*` modules directly. This channel is NOT a thin transport — it's a God Object orchestrating HTTP routing, forking, transcript recording, media handling, MCP presets, and workspace controls.
- **Coupling loop**: `channels.websocket → webui.* → agent.* → channels.base`
- **Risk**: Every WebUI feature request touches this channel. Without decoupling, feature velocity drops or regressions spike. Extracting WebUI to a separate process becomes impossible.
- **6-month prognosis**: Worst cascading-failure risk in the codebase. New WebUI features (workspace management, collaboration) will add more imports, calcifying the coupling.

**Refactoring strategy:**
```
WebSocketChannel (thin transport, ~300 lines)
  → GatewayMessageRouter (frame routing)
    → GatewayServices (already exists, underused)
      → Individual service modules
```

#### B. AgentLoop Constructor Sprawl (HIGH)

- **File**: `nanobot/agent/loop.py`
- **Problem**: `AgentLoop.__init__` takes **30+ parameters** — session mgmt, provider lifecycle, tool loading, MCP connections, cron service, image gen config, model presets, event publishing, workspace policies.
- **Risk**: Untestable without mocking everything. Each new capability (M5 evolve, new tools, new session modes) grows the constructor further.

**Refactoring strategy:**
```python
@dataclass(frozen=True)
class AgentLoopConfig:
    """Immutable configuration snapshot."""
    max_iterations: int
    context_window_tokens: int
    # ... scalars only

@dataclass
class AgentLoopDeps:
    """Runtime service dependencies (injected)."""
    bus: MessageBus
    provider: LLMProvider
    session_manager: SessionManager
    tools_config: ToolsConfig
    # ... services, not primitives

class AgentLoop:
    def __init__(self, config: AgentLoopConfig, deps: AgentLoopDeps): ...
```

#### C. MessageBus Has No Backpressure (MEDIUM-HIGH)

- **File**: `nanobot/bus/queue.py`
- **Problem**: Bare `asyncio.Queue` with no backpressure, dead-letter handling, TTL, or observability.
- **Risk**: Under multi-channel load (chatty Feishu groups + Telegram + WebUI), memory grows unbounded. Single `AgentLoop` processes one turn at a time; a message spike can OOM a small VPS.

### 7.3 Revised Priority Ranking

| Rank | Item | Rationale |
|------|------|-----------|
| 1 | Pin openai upper bound (original 1.4) | 5 min, prevents silent breakage |
| 2 | **Split WebSocketChannel from WebUI (new A)** | Critical path coupling, highest cascading risk |
| 3 | Narrow exception handlers in runner/loop (2.1) | Core path observability |
| 4 | **Extract AgentLoop deps (new B)** | Unblocks testability of core |
| 5 | Split SettingsView.tsx (1.1) | Frontend-only, lower blast radius |
| 6 | Split cli/commands.py (1.3) | Developer velocity |
| 7 | Split image_generation.py (new D) | Blocks clean provider addition |
| 8 | Add MessageBus backpressure (new C) | Production stability under load |

### 7.4 Six-Month Risk Assessment

| Debt | Risk Level | If Left 6 More Months |
|------|-----------|----------------------|
| WebSocketChannel coupling | **CRITICAL** | Every WebUI feature becomes a cross-layer surgery. New features ship slower, regressions multiply. |
| AgentLoop 30-param constructor | **HIGH** | Constructor grows to 40+. Testing becomes "mock everything or test nothing." New devs can't onboard to the core. |
| MessageBus unbounded | **MEDIUM-HIGH** | OOM under real multi-channel load. No signal to rate-limit upstream. |
| openai unpinned | **MEDIUM** | A single `pip install --upgrade` on fresh deploy breaks all OpenAI-compat providers. Low probability, total blast radius. |
| image_generation.py monolith | **MEDIUM** | 15+ providers by year-end at current growth rate. File becomes unmaintainable, merge conflicts constant. |

### 7.5 image_generation.py Recommended Split

```
nanobot/providers/image_generation/
  __init__.py          # re-exports ABC + factory
  base.py             # ImageGenerationProvider ABC
  openrouter.py       # OpenRouterImageGenerationClient
  aihubmix.py        # AIHubMixImageGenerationClient
  ollama.py          # OllamaImageGenerationClient
  gemini.py          # GeminiImageGenerationClient
  minimax.py         # MiniMaxImageGenerationClient
  openai.py          # OpenAIImageGenerationClient
  custom.py          # CustomImageGenerationClient
  codex.py           # CodexImageGenerationClient
  stepfun.py         # StepFunImageGenerationClient
  zhipu.py           # ZhipuImageGenerationClient
  factory.py         # Registry + instantiation
```

Same treatment for `transcription.py` (6 providers, 827 lines) in follow-up.

---

## Methodology

- Scan date: 2026-06-13
- Tools: ripgrep pattern search, file line counts, dependency analysis, test directory mapping
- Scope: Full repository (`nanobot/` Python package + `webui/` TypeScript SPA + `bridge/`)
- Exclusions: `node_modules/`, `.git/`, `dist/`, `build/`, `__pycache__/`
- Architect review: file-level validation of 6 claims, codebase exploration for missing architectural debts
