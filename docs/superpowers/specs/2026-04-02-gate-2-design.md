# Vizier Pro-Max — Gate 2 Design Spec: "Works While I Sleep"

**Date:** 2026-04-02
**Author:** Khairul / Premier Marketing
**Status:** Draft v3 — architect review fixes applied
**Parent spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md` (Sections 2, 7, 8, 12)
**Gate 1 plan:** `docs/superpowers/plans/2026-04-01-gate-1-implementation.md`
**Hermes version:** v0.6.0 at ~/hermes-agent/

---

## 1. Gate 2 Objective

Gate 1 delivered "It Works" — one content workflow, manual sessions, human-prompted only.

Gate 2 delivers "Works While I Sleep":
- Mid-session toolset switching (Hermes patch)
- All workflow toolsets active (visual, research, audio, document-full, delivery; code + knowledge deferred to Gate 3)
- Parallel sessions via delegate_task + DeerFlow patterns
- Unattended sessions via Hermes cron scheduler
- OpenSpace skill evolution (CAPTURED/FIXED/DERIVED + MCP server)
- Dream-skill memory consolidation (Qwen 3.5 9B enhanced)
- Template cloning loop (vision → HTML → render → delta → iterate)
- Quality gate layers 3-6 (visual QA, content quality, delivery, feedback)
- Telegram/WhatsApp delivery channels

---

## 2. Chunk Structure

Gate 2 is organized into 4 dependency-ordered chunks:

```
Chunk 1: Hermes patch (switch_toolset)
  └→ Chunk 2: All workflow toolsets (manifests + scripts)
       ├→ Chunk 3: Parallel + unattended sessions + channels
       └→ Chunk 4: OpenSpace + dream-skill + template cloning + quality gates 3-6
```

Each chunk is independently testable. Chunk N depends on Chunk N-1.

---

## 3. Chunk 1 — Hermes Patch: Generic Agent-Level Tool Extension

### 3.1 Problem

`self.tools` is set at `AIAgent.__init__` (line 925 of run_agent.py). Tool handlers dispatched via `registry.dispatch()` have no access to the agent instance. No mechanism exists to change tools mid-session.

### 3.2 Solution: Approach C — Generic Extension Point

Instead of hardcoding `switch_toolset` in Hermes (like delegate_task), add a generic extension mechanism that any project can use. Zero vizier-specific code in Hermes.

### 3.3 Hermes Changes (18 lines, 2 files)

**File: `~/hermes-agent/hermes_cli/plugins.py`** — 1 line

Add `"on_agent_ready"` to `VALID_HOOKS` (line 52). This hook fires after `AIAgent.__init__` completes and passes `agent=self` to registered callbacks.

**File: `~/hermes-agent/run_agent.py`** — 17 lines across 4 locations

**Location 1: `__init__` (line ~652), after `self.enabled_toolsets`:**

```python
self._custom_agent_tools: dict[str, Callable[[dict, Any], str]] = {}
self._pending_toolsets_rebuild: list[str] | None = None
```

**Location 2: End of `__init__` (after all setup):**

```python
try:
    from hermes_cli.plugins import invoke_hook as _invoke_hook
    _invoke_hook("on_agent_ready", agent=self)
except Exception as exc:
    logger.warning("on_agent_ready hook failed: %s", exc)
```

**Location 3: `_invoke_tool`, after the `delegate_task` elif (line ~5323), before the `else` clause (line ~5324):**

Context anchor: the new elif goes immediately after `return _delegate_task(...)` and before the `else: return handle_function_call(...)` fallback.

```python
elif function_name in self._custom_agent_tools:
    return self._custom_agent_tools[function_name](function_args, self)
```

**Location 4: Main loop, after `_save_session_log`, before `continue` — inside the `if assistant_message.tool_calls:` branch, after the context compression block:**

Context anchor: find the sequence `self._session_messages = messages` → `self._save_session_log(messages)` → `continue` that follows the context compression block (`if self.compression_enabled and _compressor.should_compress`). The new code goes between `_save_session_log(messages)` and `continue`. There are multiple `_save_session_log` call sites — this is the one inside the main tool-processing branch of `run_conversation()`.

```python
if self._pending_toolsets_rebuild is not None:
    self.enabled_toolsets = self._pending_toolsets_rebuild
    self._pending_toolsets_rebuild = None
    self.tools = get_tool_definitions(
        enabled_toolsets=self.enabled_toolsets,
        disabled_toolsets=self.disabled_toolsets,
        quiet_mode=True,
    )
    self.valid_tool_names = {
        tool["function"]["name"] for tool in self.tools
    } if self.tools else set()
    if not self.quiet_mode:
        self._safe_print(f"🔄 Tool surface rebuilt ({len(self.tools)} tools)")
```

### 3.4 Why These Specific Insertion Points

- **`_invoke_tool` elif (Location 3):** Agent-level tools (todo, memory, clarify, delegate_task) are dispatched here with `self` access. Registry-dispatched tools go through `handle_function_call()` which has no agent reference. This elif chain is the proven pattern.
- **Main loop check (Location 4):** Tool surface must not change mid-turn (would invalidate current API call's schemas). The flag approach ensures rebuild happens between turns. Same pattern as `_interrupt_requested` (line 6307) and Honcho rebuild (line 2380).
- **`_pending_toolsets_rebuild` stores the full list, not just a toolset name:** The handler computes which toolsets to keep vs swap — Hermes just applies the list. Zero domain knowledge in Hermes.

### 3.5 Vizier Plugin: `plugins/switch_toolset.py`

```python
"""Hermes plugin: registers switch_toolset as an agent-level tool."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

VIZIER_WORKFLOW_TOOLSETS = frozenset({
    "vizier-content", "vizier-document", "vizier-visual",
    "vizier-research", "vizier-audio", "vizier-delivery",
    "vizier-fallback",
    # vizier-code and vizier-knowledge deferred to Gate 3
    # (no manifests/scripts exist yet — switching to empty toolset is silent failure)
})

SWITCH_TOOLSET_SCHEMA = {
    "type": "object",
    "properties": {
        "toolset_name": {
            "type": "string",
            "description": "Target workflow toolset to switch to",
            "enum": sorted(VIZIER_WORKFLOW_TOOLSETS),
        },
    },
    "required": ["toolset_name"],
}


def _handle_switch_toolset(args: dict[str, Any], agent: Any) -> str:
    """Set the pending rebuild — main loop applies it between turns."""
    new_ts = args.get("toolset_name", "")
    if new_ts not in VIZIER_WORKFLOW_TOOLSETS:
        return json.dumps({"error": f"Unknown toolset: {new_ts}"})

    base = [t for t in agent.enabled_toolsets if t not in VIZIER_WORKFLOW_TOOLSETS]
    agent._pending_toolsets_rebuild = base + [new_ts]

    return json.dumps({
        "status": "pending",
        "switching_to": new_ts,
        "keeping": base,
        "message": f"Switching to '{new_ts}' after this turn completes.",
    })


def register(ctx):
    """Called by Hermes plugin loader."""
    # Dual registration: schema goes to registry (model sees it), but
    # execution is intercepted by _custom_agent_tools in _invoke_tool.
    # The registry handler is a fallback that only runs if on_agent_ready
    # failed to inject the real handler (e.g., plugin load order issue).
    def _fallback_handler(args, **kw):
        logger.warning("switch_toolset: agent-level handler not injected — on_agent_ready may have failed")
        return '{"error": "switch_toolset not available — plugin initialization failed"}'

    ctx.register_tool(
        name="switch_toolset",
        toolset="vizier-core",
        schema=SWITCH_TOOLSET_SCHEMA,
        handler=_fallback_handler,
        check_fn=lambda: True,
        description="Switch the active workflow toolset mid-session",
    )

    def on_agent_ready(agent, **kwargs):
        agent._custom_agent_tools["switch_toolset"] = _handle_switch_toolset
        logger.info("switch_toolset registered as agent-level tool")

    ctx.register_hook("on_agent_ready", on_agent_ready)
```

### 3.6 Flow

```
1. Hermes starts → loads plugins → register() runs
   → schema in registry (model sees it in vizier-core)
   → on_agent_ready hook registered

2. AIAgent.__init__ completes → fires on_agent_ready
   → plugin injects handler into agent._custom_agent_tools

3. Model calls switch_toolset(toolset_name="vizier-visual")
   → _invoke_tool hits elif → handler runs
   → computes base = ["vizier-core", "code_execution", "delegation"]
   → sets agent._pending_toolsets_rebuild = base + ["vizier-visual"]
   → returns status JSON to model

4. All tool calls complete → main loop reaches rebuild check
   → self.enabled_toolsets updated
   → self.tools rebuilt via get_tool_definitions()
   → self.valid_tool_names updated
   → next API call includes new tool schemas
```

### 3.7 Edge Cases

| Case | Handling |
|------|----------|
| Two switch_toolset calls in one turn | Last one wins (overwrites _pending_toolsets_rebuild) |
| switch_toolset + other tools in same batch | Other tools execute normally. Switch applied after all complete. |
| Switch to already-active toolset | No-op rebuild. Harmless. |
| Switch to vizier-fallback | All workflow toolsets removed from base, fallback added. ~54KB. |
| Plugin not loaded | _custom_agent_tools empty, falls through to registry → harmless error |
| Cron/delegate child agents | on_agent_ready fires for them too. Children can switch if parent allows. |
| Concurrent tool execution batch | Flag is simple attribute write. Consumed only after _execute_tool_calls returns. Safe under GIL. |

### 3.8 Files

| File | Type | Lines |
|------|------|-------|
| `~/hermes-agent/hermes_cli/plugins.py` | Modify | +1 |
| `~/hermes-agent/run_agent.py` | Modify | +17 |
| `~/vizier-pro-max/plugins/switch_toolset.py` | New | ~60 |
| `~/vizier-pro-max/tests/plugins/test_switch_toolset.py` | New | ~80 |

---

## 4. Chunk 2 — All Workflow Toolsets Active

### 4.1 Overview

Gate 1 built 2 toolsets with 4 tools total. Gate 2 activates 4 more toolsets with 9 new tools, plus expands vizier-document with 2 new tools.

### 4.2 vizier-visual (3 tools)

| Tool | Manifest | Script | Library |
|------|----------|--------|---------|
| `playwright_screenshot` | `manifests/visual/playwright_screenshot.yaml` | `scripts/visual/screenshot_html.py` | playwright |
| `pillow_process` | `manifests/visual/pillow_process.yaml` | `scripts/visual/process_image.py` | pillow |
| `fal_generate` | `manifests/visual/fal_generate.yaml` | `scripts/visual/generate_image.py` | fal.ai (httpx) |

**playwright_screenshot:** Takes HTML string or file path, renders via Playwright, returns PNG path. Supports viewport size, device emulation, wait-for-selector.

**pillow_process:** Resize, crop, rotate, watermark, composite, color adjust. Takes operation name + params. Returns output image path.

**fal_generate:** AI image generation via fal.ai API. Takes prompt + model + dimensions. Returns image URL + downloaded path.

### 4.3 vizier-research (2 tools)

| Tool | Manifest | Script | Library |
|------|----------|--------|---------|
| `pandas_analyze` | `manifests/research/pandas_analyze.yaml` | `scripts/research/analyze_data.py` | pandas |
| `matplotlib_chart` | `manifests/research/matplotlib_chart.yaml` | `scripts/research/render_chart.py` | matplotlib |

**pandas_analyze:** Load CSV/JSON/Excel, run analysis operations (describe, groupby, pivot, filter, merge). Returns JSON summary + optional CSV output.

**matplotlib_chart:** Generate charts (bar, line, pie, scatter, heatmap). Takes data dict + chart config. Returns PNG path.

### 4.4 vizier-audio (2 tools)

| Tool | Manifest | Script | Library |
|------|----------|--------|---------|
| `ffmpeg_process` | `manifests/audio/ffmpeg_process.yaml` | `scripts/audio/process_media.py` | ffmpeg CLI |
| `edge_tts_speak` | `manifests/audio/edge_tts_speak.yaml` | `scripts/audio/speak_text.py` | edge-tts |

**ffmpeg_process:** Audio/video processing — trim, concat, convert format, normalize volume, extract audio. CLI wrapper.

**edge_tts_speak:** Text-to-speech via Microsoft Edge TTS (free, no API key). Takes text + voice + output path. Supports Malay and English voices.

### 4.5 vizier-document expanded (2 new tools)

| Tool | Manifest | Script | Library |
|------|----------|--------|---------|
| `typst_render` | exists (Gate 1) | exists | typst CLI |
| `pandoc_convert` | `manifests/document/pandoc_convert.yaml` | `scripts/document/convert_format.py` | pandoc CLI |
| `pypdf_merge` | `manifests/document/pypdf_merge.yaml` | `scripts/document/merge_pdfs.py` | pypdf |

**pandoc_convert:** Convert between markdown, HTML, DOCX, PDF, LaTeX, RST. CLI wrapper with format detection.

**pypdf_merge:** Merge multiple PDFs, extract pages, rotate, add watermarks. Uses pypdf (already installed).

### 4.6 Pipeline Stubs

| Pipeline | Toolset | Description |
|----------|---------|-------------|
| `clone_converge.py` | visual | Template cloning (fully built in Chunk 4) |
| `poster_batch.py` | visual | CSV + template → batch posters via Jinja2 + Playwright |
| `competitive_analysis.py` | research | Market scan → analysis → chart → report |
| `tts_generate.py` | audio | Text → edge-tts → ffmpeg normalize → output |

Pipeline stubs return hardcoded output initially, replaced with real logic as Chunk 4 builds out.

### 4.7 New Dependencies

```toml
# pyproject.toml additions
playwright = ">=1.40"
pandas = ">=2.0"
matplotlib = ">=3.8"
edge-tts = ">=6.1"
# fal.ai uses httpx (already installed)
# ffmpeg, pandoc, typst are CLI tools (system install)
```

### 4.8 Files

- 9 new manifests (YAML, ~30 lines each = ~270 lines)
- 9 new scripts (Python, ~40-80 lines each = ~540 lines)
- 4 pipeline stubs (~40 lines each = ~160 lines)
- 9 test files (~50 lines each = ~450 lines)
- Update `pipelines/_registry.yaml` with 4 new entries

---

## 5. Chunk 3 — Parallel Sessions, Unattended Sessions, Channels

### 5.1 Parallel Sessions (DeerFlow Patterns)

Three modules in `augments/deerflow/` provide orchestration patterns for Hermes's built-in `delegate_task`. `decompose_task` and `merge_results` are registered as agent-level tools (via the same `on_agent_ready` hook as `switch_toolset`) so the model calls them directly — no fragile `execute_code` import path.

**Critical: Hermes `delegate_task` supports batch mode.** When called with `tasks=[{goal, context, toolsets}, ...]`, children run **in parallel** via `ThreadPoolExecutor(max_workers=3)` (delegate_tool.py line 508). Single-goal mode runs one child sequentially. The decompose → delegate flow MUST use batch mode for true parallelism.

**`augments/deerflow/task_decomposer.py` (~120 lines)**

- Input: task description string (available toolsets auto-detected from `agent.enabled_toolsets`)
- Output: list of sub-task specs compatible with `delegate_task(tasks=...)` batch format: `[{goal, context, toolsets}]`
- Logic: Rule-based keyword → toolset mapping:
  - `"research|analyze|data|market|trend"` → `["vizier-research"]`
  - `"poster|image|design|visual|screenshot"` → `["vizier-visual"]`
  - `"copy|content|write|social|caption"` → `["vizier-content"]`
  - `"pdf|report|invoice|document|convert"` → `["vizier-document"]`
  - `"audio|voice|tts|podcast|sound"` → `["vizier-audio"]`
- Cap: max 3 sub-tasks (Hermes `MAX_CONCURRENT_CHILDREN` constraint)
- Fallback: if no pattern matches, single task with `["vizier-fallback"]`

**`decompose_task` tool schema:**

```python
DECOMPOSE_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": "The complex task to decompose into parallel sub-tasks",
        },
    },
    "required": ["task_description"],
}
```

Returns JSON: `{"tasks": [{goal, context, toolsets}, ...], "summary": "..."}`. The `tasks` array is directly passable to `delegate_task(tasks=...)`.

**`augments/deerflow/result_synthesizer.py` (~100 lines)**

- Input: list of child results (strings returned by delegate_task batch mode)
- Output: merged deliverable dict with section headers, deduplicated file paths, collected artifacts
- Logic: Order-preserving dedup via `dict.fromkeys()` (DeerFlow pattern). Concatenation with workflow-type headers.

**`merge_results` tool schema:**

```python
MERGE_RESULTS_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Child task results from delegate_task to merge",
        },
        "output_format": {
            "type": "string",
            "enum": ["summary", "report", "campaign_package"],
            "description": "How to structure the merged output",
        },
    },
    "required": ["results"],
}
```

**`augments/deerflow/shared_memory.py` (~80 lines)**

- Thread-safe debounced write queue for cross-agent observations
- DeerFlow pattern: `threading.Timer` with 30s debounce window
- Storage: JSON file at `tmp/shared_memory_{session_id}.json`
- Parent reads after children complete. Children write observations during execution.
- Simple file-based IPC — no distributed systems.
- Cleanup: parent deletes shared memory file after synthesis. health_check cron reaps stale files >24h old.
- Session IDs are UUIDs (Hermes built-in) — no collision risk.

**Registration:** The `plugins/deerflow_orchestration.py` plugin registers `decompose_task` and `merge_results` as agent-level tools via `on_agent_ready`, following the same pattern as `switch_toolset`. Both are registered in the `vizier-core` toolset (always available to parent sessions).

**SOUL.md additions for parallel orchestration:**

```markdown
When you receive a complex multi-workflow task:
1. Call decompose_task with the task description
   → returns {tasks: [{goal, context, toolsets}, ...]}
2. Call delegate_task with tasks=<the returned tasks array>
   → children run IN PARALLEL via ThreadPoolExecutor (max 3)
   → delegate_task returns combined results
3. Call merge_results with the child outputs
4. Deliver final output via appropriate channel

IMPORTANT: Use delegate_task(tasks=[...]) batch mode for parallelism.
Do NOT call delegate_task separately per child — that runs sequentially.
```

### 5.2 Unattended Sessions (Hermes Cron)

Hermes cron scheduler (`cron/scheduler.py`) creates `AIAgent` per job. Gate 2 adds:

**3 cron configs in `config/cron/`:**

| Config | Schedule | Toolsets | Purpose |
|--------|----------|----------|---------|
| `content_calendar.yaml` | Weekdays 8 AM | vizier-core, vizier-content | Generate scheduled social posts |
| `quality_review.yaml` | Monday 9 AM | vizier-core, vizier-research | Audit last week's quality scores |
| `health_check.yaml` | Daily 7 AM | vizier-core | System status, token usage, error rates |

**Deferred to Gate 3:** Event-driven triggers (Islamic calendar via adhan-python, client milestone deadlines, data-driven CSV upload). Gate 2 covers cron-based scheduling only. Event-driven triggers require webhook infrastructure not yet built.

Each config specifies: `id`, `schedule` (cron expression), `prompt`, `toolsets`, `max_iterations`, `token_budget`, `quality_threshold`.

**`middleware/cron_guard.py` (~60 lines)**

Safety layer for unattended sessions:
- Check that all tools in the job's toolsets have corresponding test files passing (via `test_parser.find_test_file()` for each script referenced by the toolset's manifests). Jobs using untested tools are blocked.
- Enforce token budget cap (terminate session if exceeded)
- Hold delivery if quality score < threshold (default: 7/10)
- Log full trace via structlog for post-mortem review

**`bridge/cron_loader.py` (~40 lines)**

- Read `config/cron/*.yaml`, validate against schema
- Register with Hermes cron scheduler via its job registration API
- Called during bridge/watcher.py sync cycle

### 5.3 Telegram Channel

Hermes gateway already supports Telegram. Vizier adds delivery tools:

**`manifests/delivery/send_telegram.yaml`** + **`scripts/delivery/send_telegram.py` (~40 lines)**

- Uses python-telegram-bot (already installed)
- Send text, files, images to configured chat_id (from `config/clients/{client_id}.yaml`)
- Returns delivery status + message_id

### 5.4 WhatsApp Channel (Delivery Only)

**`manifests/delivery/send_whatsapp.yaml`** + **`scripts/delivery/send_whatsapp.py` (~60 lines)**

- WhatsApp Business API via httpx
- Send text, files, images
- Requires: `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_ID` env vars
- Gate 2: delivery only (outbound). Receiving WhatsApp messages (inbound webhook) deferred to Gate 3.

### 5.5 Files

| Component | Files | Lines |
|-----------|-------|-------|
| task_decomposer.py + test | 2 | ~170 |
| result_synthesizer.py + test | 2 | ~150 |
| shared_memory.py + test | 2 | ~120 |
| cron configs (3 YAML) | 3 | ~60 |
| cron_guard.py + test | 2 | ~100 |
| cron_loader.py + test | 2 | ~70 |
| send_telegram manifest + script + test | 3 | ~100 |
| send_whatsapp manifest + script + test | 3 | ~120 |

---

## 6. Chunk 4 — OpenSpace, Dream-skill, Template Cloning, Quality Gates 3-6

### 6.1 OpenSpace Skill Evolution

Three evolution modes ported from HKUDS/OpenSpace as Hermes plugins. Simplified from the original 6000+ line implementation to ~610 lines by extracting core algorithms and reimplementing against Hermes primitives.

**Modules in `augments/openspace/`:**

| File | Lines | Purpose |
|------|-------|---------|
| `capturer.py` | ~200 | Scan structlog traces → detect repeating tool chains (≥5 occurrences) → extract chain as pipeline template |
| `generator.py` | ~100 | Generate SKILL.md + pipeline draft in `pipelines/_drafts/` from extracted chain template (uses GPT-5.4-mini for description) |
| `fixer.py` | ~120 | Scan error logs → find broken skills/pipelines → GPT-5.4-mini generates patch → new version, archive old |
| `deriver.py` | ~120 | Compare quality scores across skill variants → GPT-5.4-mini generates enhanced version → new directory |
| `version_dag.py` | ~80 | SQLite store: `skill_records` + `skill_lineage_parents` tables. Logical deactivation (`is_active` flag). Rollback via reactivation. |
| `safety.py` | ~40 | `check_skill_safety()` — validate skill before load (no shell injection, no network calls, size limits) |
| `pruner.py` | ~50 | Skills not invoked in N sessions → `~/.hermes/skills/_archived/`. Recoverable. |
| `server.py` | ~50 | FastMCP server exposing 4 tools |

**Data model:**

```python
@dataclass
class SkillRecord:
    skill_id: str           # "{name}__v{gen}_{uuid8}"
    name: str
    path: Path
    is_active: bool
    origin: str             # IMPORTED | CAPTURED | FIXED | DERIVED
    generation: int         # 0 for root
    parent_ids: list[str]   # [] for IMPORTED/CAPTURED
    change_summary: str
    total_selections: int
    total_completions: int
```

**CAPTURED mode (capturer.py):**
1. Read structlog traces from prompt_logger (Gate 1)
2. Detect tool call chains that repeat ≥5 times (configurable in `config/openspace.yaml`)
3. Extract the chain as a pipeline template
4. Generate SKILL.md describing the pattern
5. Write pipeline draft to `pipelines/_drafts/`
6. Quality gate validates draft before promotion
7. `manifest_syncer` picks up new pipeline on next bridge sync

**FIXED mode (fixer.py):**
1. Scan structlog for pipeline/skill errors
2. Identify the broken skill by error context
3. GPT-5.4-mini generates a fix (prompted with error + original skill content)
4. Apply fix: new SkillRecord (is_active=1), old deactivated (is_active=0)
5. Atomic SQLite transaction (same as OpenSpace's `atomic_insert_with_deactivation`)

**DERIVED mode (deriver.py):**
1. Compare quality scores for skill variants serving similar tasks
2. If a variant consistently scores higher, GPT-5.4-mini generates an enhanced version
3. New directory: `{name}__v{gen+1}_{uuid8}/`
4. Parent remains active (not deactivated — coexists)

**MCP server (server.py):**
4 FastMCP tools for Claude Code interaction:
- `execute_evolution(mode, target_skill_id)` — trigger CAPTURED/FIXED/DERIVED manually
- `search_skills(query, limit)` — BM25 search over skill index
- `fix_skill(skill_id, error_context)` — trigger FIXED for a specific skill
- `get_lineage(skill_id)` — return version DAG for a skill

**MCP server lifecycle:**
- Transport: stdio (standard for Claude Code MCP servers)
- Launch: configured in `.claude/settings.json` under `mcpServers`
- Config: `{"command": "python", "args": ["-m", "augments.openspace.server"], "cwd": "~/vizier-pro-max"}`
- Starts on-demand when Claude Code invokes any OpenSpace tool
- No persistent daemon — Claude Code manages the process

**Simplifications vs. original OpenSpace:**
- No embedding-based skill ranking (BM25-only). Embedding re-rank deferred to Gate 3.
- No ToolQualityManager (Triggers 2-3 deferred). Gate 2 only has Trigger 1 (post-execution analysis).
- No recording system. Reads structlog traces from prompt_logger instead.
- LLM calls use GPT-5.4-mini via Hermes (not separate OpenAI client).

### 6.2 Dream-skill Memory Consolidation (Qwen-Enhanced)

4-phase model ported from grandamenium/dream-skill, enhanced with Qwen 3.5 9B for smarter consolidation.

**Modules in `augments/dreamskill/`:**

| File | Lines | Purpose |
|------|-------|---------|
| `consolidator.py` | ~180 | 4-phase model: DECIDE → GATHER → CONSOLIDATE → PRUNE |
| `signals.py` | ~40 | Extract signals from structlog traces |
| `pruner.py` | ~30 | MEMORY.md size management |

**Phase 1: DECIDE (~10ms)**
- Check `.last-dream` timestamp
- If <24h since last run, skip
- Pure Python, no LLM

**Phase 2: GATHER SIGNAL**
- Scan structlog traces from prompt_logger SQLite (not Claude Code JSONL)
- Regex patterns for: corrections, preferences, decisions, recurring patterns
- Extract surrounding context for each match
- Record: fact, date, confidence (high/medium), contradictions

**Phase 3: CONSOLIDATE (Qwen-enhanced)**
- Send signals + existing MEMORY.md to Qwen 3.5 9B via Ollama (`http://localhost:11434/api/generate`)
- Qwen resolves contradictions (which fact supersedes)
- Qwen generates concise summaries (compresses verbose observations)
- Qwen detects implicit patterns (infers unstated preferences from behavior)
- Date normalization is rule-based (no LLM needed)

**Qwen consolidation prompt structure:**

```
System: You are a memory consolidation engine. You receive new signals
extracted from recent agent sessions and the current MEMORY.md content.
Your job: merge new signals into memory, resolve contradictions, and
compress verbose observations. Output ONLY valid markdown.

Rules:
- When a new signal contradicts an existing entry, the newer one wins.
  Mark the old entry as superseded: "(Updated YYYY-MM-DD, previously: X)"
- Compress verbose observations into single-line facts
- Detect implicit patterns: if 3+ signals suggest a preference not
  explicitly stated, add it with confidence: medium
- Never invent facts not supported by the signals
- Output max 50 lines of consolidated entries

Input format:
EXISTING MEMORY:
{memory_content}

NEW SIGNALS:
{signals_json}

Output format (markdown list):
- [YYYY-MM-DD] Fact. (source: session, confidence: high|medium)
```

**Guardrails:** Output capped at 4096 tokens. Response validated: must be parseable as markdown list items. If Qwen returns unparseable output, fall back to rule-based merging. If Ollama is unreachable (connection refused), fall back silently with a structlog warning.

**Phase 4: PRUNE & INDEX**
- Rebuild MEMORY.md as lean index (<200 lines)
- Entries >90 days old without recent references → `archive.md`
- Topic file organization: preferences.md, decisions.md, corrections.md, patterns.md, facts.md

**Trigger:** Hermes `on_session_end` plugin hook. Runs as fire-and-forget background task.

**Qwen dependency:** `ollama pull qwen3.5:9b` must be available. Consolidator falls back to rule-based merging (dream-skill original behavior) if Ollama is unreachable.

### 6.3 Template Cloning Loop

Vision → HTML/CSS → Playwright render → multi-signal delta → iterate → Jinja2 parameterize. From v6.2 spec Section 24.

**Files:**

| File | Lines | Purpose |
|------|-------|---------|
| `pipelines/clone_converge.py` | ~120 | Pipeline orchestrator (the convergence loop) |
| `scripts/visual/calculate_delta.py` | ~100 | Multi-signal comparison (shared with quality gate layer 3) |
| `scripts/visual/parameterize_template.py` | ~80 | Replace content with Jinja2 placeholders |

**The convergence loop:**

```
1. Input: target image (PNG/JPG)
2. GPT-5.4-mini (vision): "Describe exact HTML/CSS to reproduce this layout"
   → HTML/CSS code
3. playwright_screenshot(html) → rendered PNG
4. calculate_delta(target, rendered) → composite score:
   - SSIM (scikit-image, 30% weight)
   - Pixel diff (pixelmatch, 25%)
   - Color palette ΔE (Pillow+numpy, 20%)
   - Layout position (opencv contour matching, 15%)
   - Text content (pytesseract OCR + difflib, 10%)
5. If composite score < threshold AND iterations < 5:
   Feed delta details to LLM → adjusted HTML/CSS → goto 3
6. Replace specific content with Jinja2 placeholders
7. Save template to template library
```

**Convergence thresholds:**

| Signal | Good enough | Publish-ready |
|--------|------------|---------------|
| SSIM | > 0.80 | > 0.92 |
| Pixel diff (% mismatched) | < 15% | < 5% |
| Perceptual hash distance | < 8 bits | < 3 bits |
| Color palette delta (avg ΔE) | < 10 | < 3 |
| Text content match | > 90% | > 99% |

**Economics:** Each iteration ~3,000 tokens + ~1s render + ~50ms delta. Full 5-iteration convergence: ~15,000 tokens, ~10 seconds. After convergence: zero tokens (Jinja2 is pure Python).

**New dependencies:** scikit-image, pixelmatch, opencv-python-headless, pytesseract

### 6.4 Quality Gate Layers 3-6

Extending `middleware/quality_gate.py` from ~110 lines (Gate 1, layers 1-2) to ~250 lines.

| Layer | Gate | What it checks | Implementation |
|-------|------|---------------|----------------|
| 1. Input validation | 1 (exists) | Brief schema, required fields | pydantic |
| 2. Output verification | 1 (exists) | Output matches expected schema | pydantic |
| 3. Visual QA | 2 (new) | Rendered images match expectations | `calculate_delta.py` (shared with template cloning) |
| 4. Content quality | 2 (new) | Language, tone, register | lingua-py detection + keyword tone checker |
| 5. Delivery verification | 2 (new) | Delivery API response status | httpx status check |
| 6. Feedback loop | 2 (new) | Quality scores → OpenSpace | structlog structured fields |

**Layer 3 (Visual QA):** Called only for template-based renders (clone_converge, poster_batch) where a reference image or template exists. Uses `calculate_delta.py` to compare rendered output against the template's expected layout. NOT called for free-form image generation (fal_generate) — there's no reference to compare against. For template renders, the converged template itself is the reference; for batch renders, the template + expected dimensions serve as reference. Configurable thresholds per client.

**Layer 4 (Content quality):** lingua-py detects language (Malay/English expected for Malaysian SME context). Tone checker validates against client config (`clients/{client_id}.yaml` specifies `tone: formal|casual|mixed`). Flags content that doesn't match expected language/tone.

**Layer 5 (Delivery verification):** After `send_telegram` or `send_whatsapp`, checks HTTP response. If delivery failed, flags for retry (max 2 retries) or human review.

**Layer 6 (Feedback loop):** Every quality gate invocation logs structured data via structlog: `{tool_name, layer, score, pass_fail, session_id, timestamp}`. OpenSpace capturer reads these to detect quality patterns and trigger evolution.

**New dependency:** lingua-py

---

## 7. New Dependencies Summary

```toml
# Gate 2 additions to pyproject.toml
playwright = ">=1.40,<2"
pandas = ">=2.0,<3"
matplotlib = ">=3.8,<4"
edge-tts = ">=6.1,<7"
scikit-image = ">=0.22,<1"
pixelmatch = ">=0.3,<1"
opencv-python-headless = ">=4.9,<5"
pytesseract = ">=0.3,<1"
lingua-py = ">=2.0,<3"
mcp = ">=1.0,<2"           # FastMCP for OpenSpace server
```

**System installs (macOS):**
```bash
brew install ffmpeg pandoc tesseract
# Tesseract language data for Malay (required for template cloning OCR)
brew install tesseract-lang  # includes msa (Malay)
# Playwright browsers
python -m playwright install chromium
```

**Local model:**
```bash
ollama pull qwen3.5:9b
```

**Package structure:** All new directories (`augments/openspace/`, `augments/dreamskill/`, `augments/deerflow/`, `tests/augments/`, `tests/plugins/`, `scripts/visual/`, `scripts/research/`, `scripts/audio/`, `scripts/delivery/`) require `__init__.py` files. These are included in the task count but not listed individually in the file map.

**pyproject.toml update required:** Add `"augments*"` and `"config*"` to `[tool.setuptools.packages.find] include` list. Without this, `python -m augments.openspace.server` and imports from `augments.deerflow.*` will fail.

---

## 8. File Map (All New/Modified Files)

### Chunk 1 — Hermes Patch
| File | Type | Lines |
|------|------|-------|
| `~/hermes-agent/hermes_cli/plugins.py` | Modify | +1 |
| `~/hermes-agent/run_agent.py` | Modify | +17 |
| `plugins/switch_toolset.py` | New | ~60 |
| `tests/plugins/test_switch_toolset.py` | New | ~80 |
| `tests/test_integration_chunk1.py` | New | ~60 |

### Chunk 2 — Workflow Toolsets
| File | Type | Lines |
|------|------|-------|
| `manifests/visual/playwright_screenshot.yaml` | New | ~30 |
| `manifests/visual/pillow_process.yaml` | New | ~30 |
| `manifests/visual/fal_generate.yaml` | New | ~30 |
| `manifests/research/pandas_analyze.yaml` | New | ~30 |
| `manifests/research/matplotlib_chart.yaml` | New | ~30 |
| `manifests/audio/ffmpeg_process.yaml` | New | ~30 |
| `manifests/audio/edge_tts_speak.yaml` | New | ~30 |
| `manifests/document/pandoc_convert.yaml` | New | ~30 |
| `manifests/document/pypdf_merge.yaml` | New | ~30 |
| `scripts/visual/screenshot_html.py` | New | ~60 |
| `scripts/visual/process_image.py` | New | ~80 |
| `scripts/visual/generate_image.py` | New | ~60 |
| `scripts/research/analyze_data.py` | New | ~80 |
| `scripts/research/render_chart.py` | New | ~60 |
| `scripts/audio/process_media.py` | New | ~60 |
| `scripts/audio/speak_text.py` | New | ~40 |
| `scripts/document/convert_format.py` | New | ~50 |
| `scripts/document/merge_pdfs.py` | New | ~50 |
| `pipelines/clone_converge.py` | New (stub) | ~40 |
| `pipelines/poster_batch.py` | New (stub) | ~40 |
| `pipelines/competitive_analysis.py` | New (stub) | ~40 |
| `pipelines/tts_generate.py` | New (stub) | ~40 |
| `pipelines/_registry.yaml` | Modify | +20 |
| `tests/scripts/test_*.py` (9 files) | New | ~450 |
| `tests/pipelines/test_*.py` (4 files) | New | ~200 |
| `pyproject.toml` | Modify | +15 |
| `tests/test_integration_chunk2.py` | New | ~80 |

### Chunk 3 — Sessions + Channels
| File | Type | Lines |
|------|------|-------|
| `augments/deerflow/task_decomposer.py` | New | ~120 |
| `augments/deerflow/result_synthesizer.py` | New | ~100 |
| `augments/deerflow/shared_memory.py` | New | ~80 |
| `config/cron/content_calendar.yaml` | New | ~20 |
| `config/cron/quality_review.yaml` | New | ~20 |
| `config/cron/health_check.yaml` | New | ~20 |
| `middleware/cron_guard.py` | New | ~60 |
| `bridge/cron_loader.py` | New | ~40 |
| `manifests/delivery/send_telegram.yaml` | New | ~30 |
| `manifests/delivery/send_whatsapp.yaml` | New | ~30 |
| `scripts/delivery/send_telegram.py` | New | ~40 |
| `scripts/delivery/send_whatsapp.py` | New | ~60 |
| `config/SOUL.md` | Modify | +20 |
| `tests/augments/test_task_decomposer.py` | New | ~80 |
| `tests/augments/test_result_synthesizer.py` | New | ~60 |
| `tests/augments/test_shared_memory.py` | New | ~60 |
| `tests/middleware/test_cron_guard.py` | New | ~60 |
| `tests/bridge/test_cron_loader.py` | New | ~40 |
| `tests/scripts/test_send_telegram.py` | New | ~40 |
| `tests/scripts/test_send_whatsapp.py` | New | ~50 |
| `plugins/deerflow_orchestration.py` | New | ~50 |
| `tests/test_integration_chunk3.py` | New | ~80 |

### Chunk 4 — Augments + Quality Gates
| File | Type | Lines |
|------|------|-------|
| `augments/openspace/capturer.py` | New | ~200 |
| `augments/openspace/generator.py` | New | ~100 |
| `augments/openspace/fixer.py` | New | ~120 |
| `augments/openspace/deriver.py` | New | ~120 |
| `augments/openspace/version_dag.py` | New | ~80 |
| `augments/openspace/safety.py` | New | ~40 |
| `augments/openspace/pruner.py` | New | ~50 |
| `augments/openspace/server.py` | New | ~50 |
| `augments/dreamskill/consolidator.py` | New | ~180 |
| `augments/dreamskill/signals.py` | New | ~40 |
| `augments/dreamskill/pruner.py` | New | ~30 |
| `pipelines/clone_converge.py` | Replace stub | ~120 |
| `scripts/visual/calculate_delta.py` | New | ~100 |
| `scripts/visual/parameterize_template.py` | New | ~80 |
| `middleware/quality_gate.py` | Modify | +140 |
| `config/openspace.yaml` | New | ~20 |
| `tests/augments/test_capturer.py` | New | ~80 |
| `tests/augments/test_generator.py` | New | ~60 |
| `tests/augments/test_fixer.py` | New | ~80 |
| `tests/augments/test_deriver.py` | New | ~80 |
| `tests/augments/test_version_dag.py` | New | ~60 |
| `tests/augments/test_safety.py` | New | ~40 |
| `tests/augments/test_consolidator.py` | New | ~80 |
| `tests/augments/test_signals.py` | New | ~40 |
| `tests/scripts/test_calculate_delta.py` | New | ~60 |
| `tests/scripts/test_parameterize_template.py` | New | ~50 |
| `tests/middleware/test_quality_gate_extended.py` | New | ~80 |
| `tests/pipelines/test_clone_converge.py` | New | ~60 |
| `tests/test_integration_chunk4.py` | New | ~80 |

---

## 9. Gate 2 Totals

| Chunk | New files | Modified | New lines | Tests |
|-------|-----------|----------|-----------|-------|
| 1. Hermes patch | 3 | 2 | ~180 | ~140 |
| 2. Toolsets | 26 | 2 | ~1,420 | ~730 |
| 3. Sessions + channels | 16 | 1 | ~740 | ~470 |
| 4. Augments + QA | 19 | 2 | ~1,510 | ~850 |
| **Total** | **64** | **7** | **~3,850** | **~2,190** |

Note: Line estimates are conservative. Gate 1 estimated ~1,350 and delivered ~1,640+. Expect 20-30% growth during implementation.

---

## 10. Exit Criteria

- [ ] `switch_toolset` working: model switches from vizier-content to vizier-visual mid-session, tools change on next turn
- [ ] All 6 workflow toolsets registered and accessible (content, document, visual, research, audio, delivery)
- [ ] `delegate_task` executing 2-3 parallel children with scoped toolsets, results synthesized
- [ ] At least 1 cron job executing unattended (content_calendar)
- [ ] Cron guard holding delivery when quality < 7/10
- [ ] OpenSpace CAPTURED detecting a repeating pattern and generating pipeline draft
- [ ] OpenSpace FIXED patching a broken skill
- [ ] Dream-skill consolidator running on session end, Qwen generating consolidated memory
- [ ] Template cloning loop converging on a reference image (SSIM > 0.80 within 5 iterations)
- [ ] Quality gate layers 3-6 active: visual QA, content quality, delivery check, feedback logging
- [ ] `send_telegram` delivering a file to configured chat
- [ ] `send_whatsapp` delivering a message via WhatsApp Business API
- [ ] All tests passing (Gate 1: 134 + Gate 2 target: ~180 new = ~314 total)

---

## 11. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| on_agent_ready hook timing (fires before tools fully loaded?) | switch_toolset unavailable | Test hook fires after get_tool_definitions() completes |
| Qwen 3.5 9B not available on Mac Mini | Dream-skill fails | Fallback to rule-based consolidation (dream-skill original) |
| playwright_screenshot slow in CI (no display) | Test failures | Use `--headless` flag, mock in unit tests, real in integration |
| fal.ai API rate limits | Image generation blocked | Exponential backoff + fallback to placeholder image |
| WhatsApp Business API requires Meta verification | Can't ship WhatsApp | Ship as delivery tool, defer gateway integration to Gate 3 |
| Template cloning doesn't converge in 5 iterations | Poor template quality | Accept "good enough" threshold (SSIM > 0.80) + manual override |
| OpenSpace generates bad pipeline drafts | Pipeline _drafts/ fills with garbage | Quality gate validates before promotion. Pruner archives unused. |
| Cron job token budget exceeded | Runaway cost | cron_guard.py kills session at budget cap |
| pytesseract OCR inaccurate on non-Latin text (Jawi) | Delta calculator wrong | Use language-specific tessdata; accept lower text weight for non-Latin |
