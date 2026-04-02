# Vizier Pro-Max — Platform Architecture
## Built on Hermes Agent v0.6.0 | Manifest-Driven, Toolset-Scoped, Self-Evolving

**Document status:** Canonical reference for vizier-pro-max repository. Supersedes Vizier Platform Architecture v6.2 (31 March 2026) for all implementation decisions.
**Date:** 1 April 2026
**Author:** Khairul / Premier Marketing
**System:** Hermes Agent v0.6.0 + 22 YAML-manifest tools + 4 Hermes plugins + 3 absorbed agentic augments + 5 collapsed pipelines + 6-layer quality gate
**Machine:** Mac Mini M4 (16GB unified memory)
**Models:** GPT-5.4-mini (10M tokens/day free) + Qwen 3.5 9B (Ollama local, unlimited)

### Document Purpose

This document mirrors the section structure of Vizier Platform Architecture v6.2 so that every architectural decision can be compared 1:1. Each section states what Pro-Max actually built, what changed from v6.2, and why.

Where v6.2 says "Sections 1-19 unchanged from v6.1", this document reconstructs those sections from v6.2's corrections and the actual codebase. Where v6.2 added Sections 20-27, this document shows which components were adopted, rejected, or redesigned.

---

## TABLE OF CONTENTS

1. System Overview
2. Architecture Principles
3. Core Runtime: Hermes Agent
4. Tool Stack (22 manifest tools, 3 layers)
5. Enhancement Plugins (4 plugins, 4 gates)
6. Token Economics & Model Routing
7. Memory Architecture (3 layers)
8. RAG Architecture
9. Quality Assurance (6 layers)
10. Reliability & Operational Governance
11. Security Architecture
12. Skill Libraries (OpenSpace absorption)
13. Design Intelligence (Template Cloning Loop)
14. Claude Code Integration (Bridge)
15. Platform Layer
16. Service Packages
17. Build Sequence (4 gates)
18. Cost Model
19. Risk Register
20. Ecosystem Adoptions — What Was Actually Adopted
21. Pattern Reference Queue — What Was Actually Studied
22. Rejection Register — What Was Dropped and Why
23. Distillation Pipeline — Redesigned for Gate 4
24. Template Cloning Loop — Implemented as Pipeline
25. Reverse Prompt Engineering — Deferred
26. Front-Loaded Training Sprint — Deferred
27. Prompt Logger Plugin — Implemented as Lifecycle Hook

---

## 1. System Overview

### What Vizier Is (unchanged from v6.2)

Vizier is a general-purpose AI services platform — a single engine that autonomously produces, validates, and delivers work across any domain it has tools and knowledge for. It is not a marketing tool. It is not a chatbot. It is an autonomous production engine with a self-improving knowledge base.

Marketing is the first vertical because that's where Premier Marketing's clients are. The engine is domain-agnostic. Adding a new vertical means adding knowledge cards and skills, not rebuilding the engine.

**One engine, many doors. The engine is the product.**

### What Changed from v6.2

v6.2 described a system with "47 Python tools + 35 enhancement plugins + 7 absorbed pattern sources + 4 skill libraries + 16 ecosystem adoptions." This was an aspirational inventory that conflated tools, libraries, patterns, and runtime components into a single count.

Pro-Max built a smaller, tighter system:

| Metric | v6.2 Claimed | Pro-Max Actual |
|--------|-------------|----------------|
| Tools registered with Hermes | 47 individual wrappers | 22 YAML-manifest tools + 3 custom handler tools |
| Enhancement plugins | 35 plugins | 4 Hermes lifecycle plugins |
| Absorbed pattern sources | 7 sources | 3 augment modules (OpenSpace, DreamSkill, DeerFlow) |
| Skill libraries | 4 libraries | 0 external libraries — skills are SKILL.md files managed by OpenSpace |
| Ecosystem adoptions | 16 components | 3 actually adopted (OpenSpace, DreamSkill patterns, DeerFlow patterns) |
| Lines of production code | Not specified | ~4,800 lines across 65 source files |
| Lines of test code | Not specified | ~73 test files |

**Why smaller is correct:** v6.2 counted every Python library in `requirements.txt` as a "tool" and every configuration option as a "plugin." Pro-Max counts only what Hermes actually registers and invokes. A library like `pillow` is not a tool — `pillow_process` (the manifest + script that wraps it) is the tool. This distinction matters for token cost accounting, because Hermes loads tool schemas into context, not library docs.

---

## 2. Architecture Principles

### v6.2 Principles (P1-P7, reconstructed from corrections)

v6.2 established seven principles, then added P8 (Simplicity) in its corrections section. Pro-Max preserves six and rejects two.

| # | v6.2 Principle | Pro-Max Status | Notes |
|---|----------------|----------------|-------|
| P1 | Hermes is the sole runtime | **Preserved** | No competing runtimes. No LangGraph, CrewAI, OpenAI Agents SDK as runtime. |
| P2 | 7 named agents with role/goal/backstory | **Rejected** | Replaced by superagent model. See §3. |
| P3 | PydanticAI for all tool contracts | **Rejected** | Replaced by YAML manifests. See §4. |
| P4 | Workflow-scoped tool loading | **Preserved and extended** | Toolsets defined in `config/toolsets.py`, loaded at session init. |
| P5 | Revenue gate rule | **Preserved** | Each gate must produce billable output before the next unlocks. |
| P6 | Quality gate on every output | **Preserved** | 6-layer QA in `middleware/quality_gate.py`. |
| P7 | Self-improvement via distillation | **Preserved but redesigned** | DSPy rejected; direct quality-gate evaluation used instead. See §23. |
| P8 | Simplicity (added in v6.2 corrections) | **Elevated to P1** | Most important principle. Drives every rejection decision. |

### Pro-Max Principles (as implemented)

1. **Hermes is the sole runtime.** No competing runtimes installed. Patterns extracted from external projects, runtimes rejected.

2. **Superagent model.** ONE Hermes agent with workflow-scoped toolset loading. No named agent roles. Complex tasks use Hermes's native `delegate_task` for sub-agents.

3. **Manifests as contracts.** YAML manifests define every tool's schema, execution type, timeout, and retry policy. The adapter converts these to Hermes-native OpenAI-format tool dicts. Zero handler code for ~70% of tools.

4. **Scripts as hands.** Stable Python libraries/CLIs are the tool layer. The model never touches raw APIs — scripts encapsulate all execution.

5. **Collapse what repeats.** Deterministic sequences become collapsed pipelines behind `run_pipeline`. Atomic tools exist as fallback. `execute_code` for improvisation. OpenSpace captures new patterns automatically.

6. **Toolsets control token cost.** Tools grouped into named toolsets (~3-6 tools each). Only the relevant toolset loads per task. Gate 1: toolset set at session start. Gate 2: `switch_toolset` enables mid-session changes.

7. **Bridge connects inside and outside.** Claude Code builds on the outside, the bridge informs Vizier on the inside. Bidirectional awareness.

8. **Gate-by-gate revenue rule.** Each gate must produce billable output before the next unlocks.

### Why P2 (Named Agents) Was Rejected

v6.2 inherited a 7-agent roster from the pre-Hermes architecture (OpenClaw/Mastra era): Marketing Strategist, Publisher, Media, Analyst, Coder, Steward, Quality Gate. v6.2's own corrections section acknowledged this was wrong:

> "The 7 named agents were artificial divisions from the pre-Hermes architecture where each agent had fixed tool assignments. With Hermes's native `delegate_task`, workflow-scoped tool loading, and lazy loading on Qwen local, the named agents add routing overhead and token cost without functional benefit."

Pro-Max implemented what v6.2 recommended but never built: a true superagent where workflows replace agent roles and quality gate is middleware, not an agent.

### Why P3 (PydanticAI Tool Contracts) Was Rejected

v6.2 specified PydanticAI `@agent.tool` decorators with `RunContext` dependency injection for every tool wrapper. This meant:

1. **Every tool required Python handler code.** Even simple CLI wrappers needed a decorated function with typed input/output models.
2. **Tool registration was scattered.** Each `~/.hermes/plugins/tools/*.py` file registered its own tools. No central registry.
3. **Schema changes required code changes.** Adding a parameter to a tool meant editing Python, not YAML.

Pro-Max replaced this with YAML manifests:

```yaml
# v6.2 approach: ~40 lines of Python per tool
@agent.tool
async def typst_render(ctx: RunContext, input_path: str, output_path: str) -> str:
    """Compile Typst markup into PDF"""
    # validation, execution, error handling, retry...

# Pro-Max approach: ~15 lines of YAML per tool
name: typst_render
description: "Compile Typst markup into PDF"
toolset: vizier-document
execution:
  type: python_script
  path: scripts/document/render_typst.py
  entrypoint: render_to_pdf
  timeout: 30
input:
  input_path: {type: string, required: true}
  output_path: {type: string, required: true}
```

The adapter (`adapter/loader.py`, 112 lines) converts all manifests to Hermes-native tool dicts in a single pass. The executor (`adapter/executor.py`, 187 lines) handles CLI, python_script, and python_function execution types with uniform timeout, validation, and error handling.

**PydanticAI is still used** — but only inside script implementations for input validation, not for tool registration. Pydantic (not PydanticAI) validates manifest YAML structure via frozen BaseModels in `adapter/schemas.py`.

---

## 3. Core Runtime: Hermes Agent

### v6.2 Description

v6.2 described Hermes as running 7 named agents with role-based routing:

```
7 Named Agents (v6.2)
├── Marketing Strategist → content tools
├── Publisher → document tools
├── Media → visual tools
├── Analyst → research tools
├── Coder → code tools
├── Steward → knowledge tools
└── Quality Gate → QA middleware
```

v6.2's own corrections dissolved this into a superagent but kept referencing "7 agents" throughout the document.

### Pro-Max Implementation

```
ONE Hermes Superagent (Pro-Max)
├── Workflow-scoped toolset loading (3-6 tools per workflow, ~14-18KB)
├── delegate_task for parallel sub-agents (up to 3 concurrent, isolated)
├── Quality gate as middleware (6 layers, every workflow passes through)
├── Qwen 3.5 9B local for routing + tool selection (Gate 2+, free)
└── switch_toolset plugin for mid-session toolset changes (Gate 2+)
```

### Session Model (3 types)

| Session Type | Gate | Trigger | Toolset | Supervision |
|-------------|------|---------|---------|-------------|
| Interactive | 1+ | Human prompt (Telegram, WhatsApp, API) | Set at session start | Human in loop |
| Parallel | 2+ | `delegate_task` decomposition | Each child scoped by parent | Parent synthesizes |
| Unattended | 2+ | Hermes cron, event-driven, data-driven | Fixed per scheduled task | Quality gate only |

### What v6.2 Got Wrong About Sessions

v6.2 described sessions implicitly through the 7-agent model — each "agent" was effectively a session type. Pro-Max made sessions explicit:

- **Interactive sessions** replace what v6.2 called "human-prompted triggers"
- **Parallel sessions** replace what v6.2 called "subagent spawning" — but Pro-Max uses Hermes's native `delegate_task` with toolset intersection, not custom orchestration
- **Unattended sessions** replace what v6.2 described across §10 (reliability) and §17 (build sequence) — Pro-Max has explicit safety constraints: test coverage checks (`middleware/cron_guard.py`), token budget caps, quality threshold holds

### Hermes Patches (Gate 2)

Pro-Max requires two additions to Hermes v0.6.0:

1. **`on_agent_ready` hook** in `plugins.py` (1 line) — allows plugins to modify agent state between turns
2. **`_pending_toolsets_rebuild` field** on `AIAgent` (17 lines) — enables `switch_toolset` plugin to request toolset changes that take effect next turn

These are documented in `docs/superpowers/specs/2026-04-02-gate-2-design.md` (Chunk 1) and implemented in `plugins/switch_toolset.py` (74 lines).

---

## 4. Tool Stack (22 Manifest Tools, 3 Layers)

### v6.2 Description

v6.2 claimed "47 tools across 4 tiers":
- Tier 1: Core tools (always loaded)
- Tier 2: Workflow tools (loaded per workflow)
- Tier 3: Enhancement tools (loaded on demand)
- Tier 4: Experimental tools

Each tool was a PydanticAI-decorated Python function in `~/.hermes/plugins/tools/*.py`.

### Pro-Max Implementation

Pro-Max has **3 layers** (not 4 tiers) and **25 total tools** (22 manifest + 3 custom handlers):

#### Layer 1 — Collapsed Pipelines (Cheapest)

Deterministic sequences registered in `pipelines/_registry.yaml`, executed via `run_pipeline` tool. One LLM call instead of 4-5.

| Pipeline | Status | Lines | What It Does |
|----------|--------|-------|-------------|
| `content_generate` | Working | 148 | Brief → LLM → content → optional PDF via typst |
| `clone_converge` | Partial (LLM vision stub) | 128 | Target image → iterative HTML convergence → Jinja2 template |
| `poster_batch` | Stub | 26 | Template + CSV → batch poster production |
| `competitive_analysis` | Stub | 23 | Topic → market scan → charts → report |
| `tts_generate` | Stub | 24 | Text → edge-tts → ffmpeg normalization |

Token cost: `run_pipeline` schema ~1.5KB + registry summary ~2KB = **~3.5KB baseline**.

#### Layer 2 — Atomic Tools (Moderate)

Individual library/CLI wrappers via YAML manifests. 22 tools across 7 toolsets:

**vizier-core (always loaded, 3 tools):**

| Tool | Type | Source |
|------|------|--------|
| `run_pipeline` | Custom handler (`tools/run_pipeline.py`, 156 lines) | Pipeline dispatcher |
| `query_logs` | Custom handler (`tools/query_logs.py`, 102 lines) | Prompt trace inspection |
| `query_costs` | Custom handler (`tools/query_costs.py`, 217 lines) | Cost ledger inspection |

**vizier-content (3 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `httpx_fetch` | `scripts/content/fetch_url.py` | 81 | httpx (SSRF-protected) |
| `jinja2_render` | `scripts/content/render_template.py` | 25 | Jinja2 (sandboxed) |
| `lightrag_search` | `scripts/content/search_rag.py` | 28 | LightRAG (stub in Gate 1) |

**vizier-document (3 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `typst_render` | `scripts/document/render_typst.py` | 122 | Typst CLI |
| `pandoc_convert` | `scripts/document/convert_format.py` | 73 | Pandoc CLI |
| `pypdf_merge` | `scripts/document/merge_pdfs.py` | 62 | pypdf |

**vizier-visual (3 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `playwright_screenshot` | `scripts/visual/screenshot_html.py` | 63 | Playwright |
| `pillow_process` | `scripts/visual/process_image.py` | 73 | Pillow |
| `fal_generate` | `scripts/visual/generate_image.py` | 71 | fal.ai API |

**vizier-research (2 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `pandas_analyze` | `scripts/research/analyze_data.py` | 140 | pandas |
| `matplotlib_chart` | `scripts/research/render_chart.py` | 76 | matplotlib |

**vizier-audio (2 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `ffmpeg_process` | `scripts/audio/process_media.py` | 143 | ffmpeg CLI |
| `edge_tts_speak` | `scripts/audio/speak_text.py` | 76 | edge-tts |

**vizier-delivery (2 manifest tools):**

| Tool | Script | Lines | Library |
|------|--------|-------|---------|
| `send_telegram` | `scripts/delivery/send_telegram.py` | 66 | python-telegram-bot |
| `send_whatsapp` | `scripts/delivery/send_whatsapp.py` | 56 | WhatsApp Business API |

**vizier-code, vizier-knowledge (deferred):**

Defined in `config/toolsets.py` but no manifests or scripts yet. Gate 3 scope.

**vizier-fallback:**

All ~22 tools loaded simultaneously (~44KB). Used only when current toolset is insufficient.

#### Layer 3 — Improvisation (Expensive)

Hermes's built-in `execute_code` tool (Unix domain socket RPC to sandboxed subprocess). Used unmodified in Gate 1. Gate 2+ adds allowlisted imports and write restrictions.

#### Priority Rule (enforced in `config/SOUL.md`)

```
1. FIRST: Try run_pipeline.
2. IF NO PIPELINE: Use atomic tools from active toolset.
3. IF ATOMIC TOOLS INSUFFICIENT: Use execute_code.
4. NEVER skip layers. Cheaper option first.
```

### What v6.2 Got Wrong About Tools

v6.2 counted 47 tools by listing every Python library as a separate tool. For example, `httpx` was one tool and `beautifulsoup4` was another — but in practice, web scraping uses both together. Pro-Max counts tools as **what Hermes registers and the model can call**, not what's in `pip freeze`.

v6.2's 4-tier model (Core/Workflow/Enhancement/Experimental) was also artificial. Pro-Max's 3-layer model (Pipeline/Atomic/Improvisation) reflects actual token cost and execution patterns:

| v6.2 Tier | Problem | Pro-Max Layer |
|-----------|---------|---------------|
| Tier 1 (Core) | Mixed always-loaded and rarely-used | Layer 1 (Pipelines) — cheapest, always available |
| Tier 2 (Workflow) | Correct concept | Layer 2 (Atomic) — scoped per toolset |
| Tier 3 (Enhancement) | Vague — "loaded on demand" with no mechanism | Collapsed into Layer 2 or Layer 1 |
| Tier 4 (Experimental) | No production use | Removed — experimental tools stay in scripts/, not registered |

### Token Cost Comparison

| Scenario | v6.2 (47 tools) | Pro-Max (toolset-scoped) |
|----------|-----------------|--------------------------|
| Single workflow | ~94KB (all tools in context) | ~14-18KB (core + workflow + pipeline summary) |
| Complex task (parallel) | ~94KB × N children | ~14-18KB per child (scoped) |
| Fallback | N/A (all already loaded) | ~54KB (core + all atomic + pipeline summary) |

---

## 5. Enhancement Plugins (4 Plugins, 4 Gates)

### v6.2 Description

v6.2 claimed "35 enhancement plugins across 4 gates." This count included configuration options, middleware layers, and external tools (DSPy, Promptfoo) as "plugins."

### Pro-Max Implementation

Pro-Max has exactly **4 Hermes lifecycle plugins** — code that hooks into Hermes's `pre_llm_call`, `post_llm_call`, or `on_agent_ready` events:

| Plugin | File | Lines | Hooks | Gate |
|--------|------|-------|-------|------|
| Prompt Logger | `plugins/prompt_logger.py` | 124 | `pre_llm_call`, `post_llm_call` | 1 |
| Switch Toolset | `plugins/switch_toolset.py` | 74 | `on_agent_ready` | 2 |
| Context Injector | `plugins/context_injector.py` | 38 | Child session startup | 2 |
| DeerFlow Orchestration | `plugins/deerflow_orchestration.py` | 88 | `on_agent_ready` | 2 |

Everything else that v6.2 called a "plugin" is either:
- **Middleware** (quality gate, cost ledger, trace exporter, cron guard, deliverable context) — called explicitly by pipeline/executor code, not by Hermes hooks
- **Augments** (OpenSpace, DreamSkill, DeerFlow) — imported by plugins or run independently, not Hermes hooks themselves
- **External tools** (DSPy, Promptfoo) — CLI tools, not Hermes plugins

### Why the Distinction Matters

Hermes has a specific plugin contract: functions named `pre_llm_call`, `post_llm_call`, or registered via `on_agent_ready` that Hermes invokes automatically. Calling everything a "plugin" obscured what actually runs on every LLM call (expensive) versus what runs on explicit invocation (cheap).

Pro-Max's 4 plugins fire on every LLM call or turn boundary. The 6 middleware modules fire only when called by pipeline code. This is a meaningful cost difference.

---

## 6. Token Economics & Model Routing

### v6.2 Description

v6.2 specified a two-tier model:
- GPT-5.4-mini → reasoning/generation (free 10M/day)
- Qwen 3.5 9B → routing + tool selection (Ollama local, free)

With a two-pass routing system: Qwen classifies task → determines toolset → Hermes session starts with that toolset + GPT-5.4-mini.

### Pro-Max Implementation

**Gate 1:** GPT-5.4-mini only. Single model. No Qwen routing.

Qwen-based routing is deferred to Gate 2 because:
1. Gate 1 is human-prompted only — the human specifies the workflow
2. Two-pass routing adds latency (~500ms for Qwen classification) with no benefit when the human already knows what they want
3. The Qwen routing layer needs training data from Gate 1 production runs to classify accurately

**Gate 2+:** Two-tier as v6.2 specified.

**Gate 4:** Progressive distillation — GPT-5.4-mini recipes migrated to Qwen 3.5 9B for steps where quality delta < 0.5. See §23.

### Token Budget

```
Daily budget:     10,000,000 tokens (GPT-5.4-mini free tier)
Avg tokens/call:  ~3,676 (estimated from v6.2)
Calls/day:        ~2,720

With toolset scoping (Pro-Max):
  Single workflow:  ~14-18KB context → fewer tokens per call
  Effective calls:  ~3,200-3,500/day (estimated 15-25% savings)
```

### Cost Configuration

Pro-Max added cost tracking not present in v6.2:

```yaml
# config/cost_config.yaml
model_costs:
  gpt-5.4-mini:
    input_per_1k: 0.00015
    output_per_1k: 0.0006
  qwen3.5:9b:
    input_per_1k: 0.0
    output_per_1k: 0.0
```

Every LLM call is tracked in `cost_ledger` (SQLite) with per-deliverable attribution via `deliverable_context.py`. This enables the Gate 4 distillation pipeline to identify which steps are most expensive and should be migrated to Qwen first.

---

## 7. Memory Architecture

### v6.2 Description

v6.2 specified 5 memory layers:
1. Hermes built-in (session context, MEMORY.md)
2. Mem0 (per-client scoped memory)
3. LightRAG (semantic search over knowledge domains)
4. Observational Memory (DreamSkill-style consolidation)
5. Skill Library (SKILL.md files, OpenSpace-evolved)

### Pro-Max Implementation

Pro-Max implements **3 layers** in Gate 1-2, with 2 deferred:

| Layer | v6.2 | Pro-Max | Status |
|-------|------|---------|--------|
| 1. Hermes MEMORY.md | Session context | `bridge/git_watcher.py` updates MEMORY.md with commit activity | **Implemented** (433 lines) |
| 2. Mem0 | Per-client memory | **Deferred** — no Mem0 integration | Not built |
| 3. LightRAG | Semantic search | `scripts/content/search_rag.py` stub (28 lines) | **Stub** |
| 4. Observational Memory | DreamSkill consolidation | `augments/dreamskill/` (278 lines) | **Implemented** |
| 5. Skill Library | OpenSpace SKILL.md | `augments/openspace/` (749 lines) | **Implemented** |

### Why Mem0 Was Deferred

Mem0 is a per-client memory layer that v6.2 specified for scoped recall: `Mem0.search(task_context, client_id)`. Pro-Max deferred it because:

1. Gate 1 has no `config/clients/` directory — client parameterization isn't implemented yet
2. Hermes MEMORY.md + DreamSkill consolidation covers session-to-session memory
3. Mem0 adds another database (Redis or SQLite) and API surface
4. Client-scoped memory can be added as a manifest tool when clients are parameterized in Gate 2

### DreamSkill Implementation (Layer 4)

4-phase consolidation running on Qwen 3.5 9B via Ollama (zero cost), with rule-based fallback if Ollama is unavailable:

| Phase | What It Does | Implementation |
|-------|-------------|----------------|
| DECIDE | 24-hour cooldown check | `consolidator.py:_phase_decide()` — timestamp comparison |
| GATHER | Extract signals from structlog | `signals.py:extract_signals()` — regex patterns for corrections, preferences, decisions, recurring patterns |
| CONSOLIDATE | Merge into MEMORY.md | `consolidator.py:_phase_consolidate_qwen()` with `_phase_consolidate_fallback()` |
| PRUNE | Keep under 200 lines | `pruner.py:prune_memory()` — archives overflow to `archive.md` |

### Shared Memory (Cross-Agent, Layer 5 extension)

For parallel sessions via `delegate_task`, Pro-Max implements file-based IPC in `augments/deerflow/shared_memory.py` (123 lines):
- Thread-safe via `threading.Lock()`
- Process-safe via `fcntl.flock()` (POSIX)
- Capped at 500 observations per session
- Cleaned up on session end

This was not in v6.2 at all — v6.2 mentioned "persistent memory via debounced async queue" in the DeerFlow pattern reference but never specified an implementation.

---

## 8. RAG Architecture

### v6.2 Description

v6.2 specified:
- LightRAG with 4 query modes (hybrid, local, global, naive)
- Knowledge Graph Tool (Jesse Vincent) indexing 21,000 Wisdom Vault atoms
- Graphiti temporal knowledge graph (Gate 3-4 evaluation)

### Pro-Max Implementation

| Component | v6.2 Gate | Pro-Max Status |
|-----------|-----------|----------------|
| LightRAG | 1 | **Stub** — `scripts/content/search_rag.py` returns placeholder. Manifest registered but not wired to actual LightRAG instance. |
| Knowledge Graph Tool | 1 | **Not implemented** — not in Pro-Max scope |
| Graphiti | 3-4 | **Not implemented** — evaluation deferred |

### Why Knowledge Graph Tool Was Dropped

v6.2 placed the Knowledge Graph Tool (Jesse Vincent) in Gate 1 as a day-1 install. Pro-Max dropped it because:

1. It requires indexing the full Obsidian Wisdom Vault (21,000 atoms) before producing any output
2. Gate 1's objective is "first billable output" — knowledge graph search is nice-to-have, not required
3. LightRAG already provides semantic search when integrated
4. The Knowledge Graph Tool runs as a separate MCP server, adding operational complexity

LightRAG integration is the priority. The Knowledge Graph Tool can be added later as a manifest tool pointing to its MCP server.

---

## 9. Quality Assurance (6 Layers)

### v6.2 Description

v6.2 specified 6 QA layers with PydanticAI for input validation (~500 lines) and various libraries for visual/content/delivery checking.

### Pro-Max Implementation

`middleware/quality_gate.py` (376 lines) implements all 6 layers:

| Layer | Gate | What It Checks | Pro-Max Implementation |
|-------|------|----------------|----------------------|
| 1. Input validation | 1 | Schema, required fields | JSON Schema type validation against manifest input definitions |
| 2. Output verification | 1 | Structured output matches expected schema | Schema-based output checking |
| 3. Visual QA | 2 | Rendered images match target | `scripts/visual/calculate_delta.py` (226 lines) — 5-signal composite: SSIM (30%), pixel diff (25%), color delta-E (20%), layout position (15%), OCR text match (10%) |
| 4. Content quality | 2 | Language, tone, register | lingua-py language detection + tone analysis |
| 5. Delivery verification | 2 | Confirm delivery succeeded | HTTP status code validation |
| 6. Feedback loop | 2 | Quality scores feed into OpenSpace | structlog capture for skill evolution |

### What Changed from v6.2

1. **No PydanticAI for input validation.** v6.2 specified "pydantic models for brief schema, ~500 lines." Pro-Max uses JSON Schema type validation derived from manifest YAML definitions — no separate Pydantic model per tool. The adapter's `schemas.py` handles this with frozen Pydantic BaseModels for the manifest format itself, not for each tool's input.

2. **Wiring is explicit.** Pipeline scripts call `quality_gate.validate()` directly. `adapter/executor.py` calls it after atomic tool execution. Not magic injection, not middleware wrapping — explicit function calls. This was a v6.2 recommendation that Pro-Max actually implemented.

3. **Cost-aware quality tracking.** `middleware/cost_ledger.py` (173 lines) records quality scores alongside cost data per deliverable. `middleware/trace_exporter.py` (251 lines) detects anomalies (quality < 7.0 or cost > baseline + 2σ) and exports full traces. None of this existed in v6.2.

---

## 10. Reliability & Operational Governance

### v6.2 Description

v6.2 referenced §10 for "stall detection and circuit breaker" patterns, citing AMUX's auto-compact watchdog as a study target.

### Pro-Max Implementation

Pro-Max built reliability through middleware rather than a dedicated reliability module:

| Concern | v6.2 Approach | Pro-Max Implementation |
|---------|---------------|----------------------|
| Stall detection | AMUX watchdog pattern study | Not implemented — Hermes handles its own timeouts |
| Circuit breaker | §10 reference | Executor timeout enforcement per tool (`adapter/executor.py`) |
| Unattended safety | Implicit in §17 build sequence | `middleware/cron_guard.py` (74 lines) — test coverage check, token budget enforcement, quality threshold holds |
| Cost anomaly detection | Not in v6.2 | `middleware/trace_exporter.py` (251 lines) — checks per-deliverable cost against baseline + 2σ |
| Trace retention | Not in v6.2 | 90-day retention with archival (`config/cost_config.yaml`) |
| Cross-session tracing | Not in v6.2 | `middleware/deliverable_context.py` (56 lines) — ContextVar propagation of deliverable_id across `delegate_task` children |

### Cron Guard (New in Pro-Max)

Unattended sessions have explicit safety constraints not specified in v6.2:

```python
# middleware/cron_guard.py
def check_job_safety(job_config) -> dict:
    """Returns {allowed: bool, reason: str}"""
    # 1. Verify toolset manifests have test files
    # 2. Check token budget hasn't been exceeded
    # 3. Verify quality gate threshold is configured
```

If `should_hold_delivery()` returns True (quality < threshold), output is held for human review instead of delivered. This is the "quality gate hold" pattern described in v6.2's session model but never implemented there.

---

## 11. Security Architecture

### v6.2 Description

v6.2 referenced §11 for "deny-by-default permissions" and "session isolation," citing ZeroClaw as a study target.

### Pro-Max Implementation

Security is implemented per-module rather than as a centralized security layer:

| Concern | Implementation | File |
|---------|---------------|------|
| SSRF protection | URL scheme + private IP blocking | `scripts/content/fetch_url.py` |
| Path traversal prevention | `is_relative_to()` checks against allowed roots | `adapter/executor.py`, `scripts/document/render_typst.py`, `scripts/audio/process_media.py` |
| Shell injection prevention | `shlex.quote()` + `shell=False` on all subprocess calls | `adapter/executor.py` |
| Template injection | Jinja2 `SandboxedEnvironment` with autoescape | `scripts/content/render_template.py` |
| Skill safety | 19 regex patterns for dangerous operations | `augments/openspace/safety.py` (80 lines) |
| API key management | Environment variables only (`TELEGRAM_BOT_TOKEN`, `FAL_KEY`, `WHATSAPP_TOKEN`) | All delivery/generation scripts |
| Subprocess timeout | Per-tool configurable timeout (default 30s) | `adapter/executor.py` |
| Output size cap | 1MB subprocess output limit | `adapter/executor.py` (Gate 2 hardening) |

### Skill Safety (OpenSpace-specific)

Before any evolved skill loads, `augments/openspace/safety.py` checks for:
- File size > 50KB
- 19 dangerous patterns: `rm -rf`, `eval(`, `exec(`, `__import__`, `subprocess.call`, `os.system`, `shutil.rmtree`, `socket.connect`, network exfiltration, etc.

Returns `SafetyResult(is_safe=bool, reason=str)`. Unsafe skills are logged and skipped.

---

## 12. Skill Libraries (OpenSpace Absorption)

### v6.2 Description

v6.2 specified "4 skill libraries: ~200 skills absorbed" from external sources. It planned to install OpenSpace as an MCP server, sync skills to `~/.hermes/skills/openspace-evolved/`, and run a separate sync script.

### Pro-Max Implementation

Pro-Max absorbed OpenSpace **directly into the codebase** as `augments/openspace/` (749 lines across 8 files):

| File | Lines | Purpose |
|------|-------|---------|
| `capturer.py` | 107 | Detect repeating tool chains from prompt_log (threshold: 5 occurrences) |
| `version_dag.py` | 204 | SQLite-backed skill lineage with logical deactivation |
| `fixer.py` | 85 | Auto-repair broken skills via LLM (LLM call stubbed) |
| `deriver.py` | 91 | Generate enhanced variants (parent coexists) |
| `generator.py` | 110 | Generate SKILL.md + pipeline drafts from captured chains |
| `pruner.py` | 46 | Archive stale derivatives with zero usage |
| `safety.py` | 80 | 19-pattern safety check before load |
| `server.py` | 117 | FastMCP server exposing 4 tools for Claude Code integration |

### Three Evolution Modes

| Mode | Trigger | What Happens | Parent Fate |
|------|---------|-------------|-------------|
| CAPTURED | Tool chain repeats 5+ times | New SKILL.md + pipeline draft generated | N/A (new skill) |
| FIXED | Skill breaks (error logged) | LLM analyzes error → generates repair → `atomic_replace()` | Deactivated |
| DERIVED | Higher quality score detected | Enhanced variant generated → `save()` | Stays active (coexists) |

### Why OpenSpace Was Absorbed Instead of Run as MCP Server

v6.2 planned OpenSpace as an external MCP server. Pro-Max absorbed it because:

1. **Tighter integration.** Capturer reads directly from the same SQLite `prompt_log` that the prompt logger writes to. No serialization overhead.
2. **Version DAG in the same DB.** `state/openspace_skills.db` lives in the repo, queryable by quality gate and cost ledger.
3. **Safety checks before load.** `check_skill_safety()` runs before any evolved skill enters the system — easier to enforce when the code is local.
4. **No extra process.** MCP server mode (`server.py`, 117 lines) is available for Claude Code integration but is not required for Hermes operation.

The Gate 2+3 design doc explicitly overrode v6.2 on this point: "OpenSpace as Hermes lifecycle hooks instead of MCP server."

---

## 13. Design Intelligence (Template Cloning Loop)

### v6.2 Description

v6.2 §24 described a 7-step template cloning pipeline (~610 lines) for reverse-engineering visual designs into reusable Jinja2 templates.

### Pro-Max Implementation

Implemented as `pipelines/clone_converge.py` (128 lines) + supporting scripts:

| Component | v6.2 Est. | Pro-Max Actual | File |
|-----------|-----------|----------------|------|
| Vision prompt (reverse-engineer HTML/CSS) | ~50 lines | Stubbed (LLM vision call) | `clone_converge.py:_call_llm_for_html()` |
| Playwright renderer | ~80 lines | Stubbed | `clone_converge.py:_render_html_to_png()` |
| Multi-signal delta calculator | ~200 lines | **226 lines** (fully implemented) | `scripts/visual/calculate_delta.py` |
| Iteration controller | ~100 lines | Integrated into pipeline | `clone_converge.py:run()` |
| Delta feedback prompt builder | ~80 lines | Integrated into pipeline | `clone_converge.py` |
| Template parameterizer | ~100 lines | **31 lines** | `scripts/visual/parameterize_template.py` |

The delta calculator is the most complex component, implementing all 5 signals from v6.2 §24:

| Signal | Weight | Library | Fallback |
|--------|--------|---------|----------|
| SSIM | 30% | scikit-image | numpy MSE |
| Pixel diff | 25% | pixelmatch | numpy comparison |
| Color delta-E | 20% | Pillow + numpy (CIE76) | Average pixel difference |
| Layout position | 15% | OpenCV (Canny edge + contour matching) | Skipped |
| Text OCR | 10% | pytesseract + difflib | Skipped |

All optional dependencies degrade gracefully — if scikit-image isn't available, MSE fallback activates. If pytesseract isn't available, text match weight redistributes to other signals.

### What Changed from v6.2

The architecture is identical to v6.2 §24. The only difference is packaging: v6.2 described it as a standalone 610-line pipeline; Pro-Max split it into a 128-line pipeline orchestrator + 226-line delta calculator script + 31-line parameterizer script. Same logic, better separation of concerns.

---

## 14. Claude Code Integration (Bridge)

### v6.2 Description

v6.2 §14 mentioned "Claude Code Integration" briefly but didn't specify a bridge mechanism. The build plan's Session 4 referenced Mission Control as the primary integration point.

### Pro-Max Implementation

The bridge (`bridge/`, 887 lines across 6 files) is the primary Claude Code ↔ Vizier awareness layer:

| Component | Lines | Trigger | What It Does |
|-----------|-------|---------|-------------|
| `watcher.py` | 113 | Post-commit hook + launchd cron (5-min) | Orchestrates all bridge components |
| `git_watcher.py` | 433 | Via watcher.py | Detects commits → extracts symbols (functions/classes added/removed) → updates MEMORY.md |
| `skill_syncer.py` | 106 | Via watcher.py | Bi-directional sync: repo `skills/` ↔ `~/.hermes/skills/vizier/`. Newer mtime wins. |
| `manifest_syncer.py` | 90 | Via watcher.py | Detects new/modified manifests and pipelines → logs to MEMORY.md |
| `test_parser.py` | 128 | On demand | Module confidence classification (high/medium/low/none based on test count) |
| `cron_loader.py` | 117 | Session startup | Load cron YAML configs → register with Hermes scheduler |

### Key Design Decisions

1. **`manifest_syncer` updates the registry file, not the running session.** New tools are available on next session start, not mid-session. This is honest about Hermes's session init model.

2. **git_watcher skips CI authors.** Commits from `aider` and `hermes` are filtered out to prevent feedback loops.

3. **Thread-safe MEMORY.md updates.** `threading.Lock()` protects concurrent writes from watcher + cron.

4. **State persistence.** Two JSON state files track last-processed SHA and manifest mtimes, enabling idempotent re-runs.

This entire module is new to Pro-Max — v6.2 had no bridge specification.

---

## 15. Platform Layer

### v6.2 Description

v6.2 §15 specified "FastAPI engine + Next.js micro-app frontends on Vercel." §20.1 specified forking Mission Control (builderz-labs) for 32 production panels with 6 customization sessions.

### Pro-Max Implementation

**No platform layer in Gate 1.** No dashboard. No FastAPI engine. No Mission Control fork.

### Why Mission Control Was Deferred

v6.2 placed Mission Control as Gate 1 Session 4 (Day 3-5). Pro-Max deferred it because:

1. **Gate 1 objective is "first billable output," not "pretty dashboard."** The dashboard doesn't produce client deliverables.
2. **6 customization sessions** (Supabase bridge, deliverable attachment, LifeOS panels, campaign panels, poster gallery, RAG inspector) is a significant engineering investment that doesn't contribute to the revenue gate.
3. **Mission Control requires running alongside Hermes** on port 3000, adding operational complexity before the core engine is stable.
4. **Cloudflare Tunnel + Access** already provides remote access to the Mac Mini — CLI monitoring suffices for Gate 1.

Mission Control remains a Gate 2+ candidate when the engine is stable and needs a monitoring surface.

---

## 16. Service Packages

### v6.2 Description

v6.2 §16 described "6 verticals + 14 capability areas."

### Pro-Max Implementation

Not explicitly specified. The toolset map implicitly defines capability areas:

| Toolset | Capabilities | v6.2 Vertical |
|---------|-------------|---------------|
| vizier-content | Copy generation, brief interpretation, template rendering | Marketing |
| vizier-document | PDF, format conversion, PDF manipulation | Publishing |
| vizier-visual | Image generation, screenshots, image processing | Design |
| vizier-research | Data analysis, chart generation | Intelligence |
| vizier-audio | TTS, media processing | Audio production |
| vizier-delivery | Telegram, WhatsApp delivery | Delivery |
| vizier-code | Code scaffolding, git (deferred) | Development |
| vizier-knowledge | RAG, knowledge graph (deferred) | Knowledge |

The key architectural difference: v6.2 defined services around client offerings ("marketing package," "publishing package"). Pro-Max defines toolsets around tool groupings. The model selects tools based on task, not package. A single task can span multiple toolsets via `delegate_task`.

---

## 17. Build Sequence (4 Gates)

### v6.2 Build Plan (38 sessions, 24 weeks)

| Gate | v6.2 Sessions | v6.2 Weeks | v6.2 Key Outcome |
|------|---------------|------------|------------------|
| Gate 1 | 8 + training sprint | 2 | First billable output |
| Gate 2 | 13 | 4 | Overnight autonomous production |
| Gate 3 | 10 | 6 | Distillation + self-building |
| Gate 4 | 7 | 12 | Full autonomy |

### Pro-Max Build Sequence (actual)

| Gate | Scope | Key Outcome | Design Doc |
|------|-------|-------------|------------|
| Gate 1 | Adapter, core tools, content pipeline, bridge, quality gate L1-2 | First billable output via content workflow | `specs/2026-04-01-vizier-pro-max-design.md` §11 |
| Gate 2 | All toolsets, switch_toolset, parallel/unattended sessions, OpenSpace, DreamSkill, delivery channels, QG L3-6 | Overnight autonomous production | `specs/2026-04-02-gate-2-design.md` |
| Gate 3 | DSPy distillation (redesigned), code workflow, data-driven triggers, execute_code sandbox | Self-building | `specs/2026-04-01-gate-2-3-design.md` |
| Gate 4 | Deliverable ledger, progressive distillation, self-evolution, observation/research triggers | Full autonomy | `specs/2026-04-01-gate-4-design.md` |

### What v6.2 Put in Gate 1 That Pro-Max Deferred

| v6.2 Gate 1 Item | Pro-Max Gate | Reason for Deferral |
|-------------------|-------------|---------------------|
| Mission Control dashboard | 2+ | Doesn't produce billable output |
| DSPy + Promptfoo install | 3-4 | Needs golden dataset from production runs |
| Knowledge Graph Tool | 2+ | Requires Wisdom Vault indexing; not needed for first output |
| Front-loaded training sprint | Deferred indefinitely | Training needs production data first |
| PydanticAI tool wrappers | Rejected | Replaced by YAML manifests |
| ClawTeam TOML workflows | Rejected | Workflows implicit in toolset groupings |
| Qwen-Agent function calling | 2+ | Single model in Gate 1 |

### What v6.2 Put in Gate 2-3 That Pro-Max Built in Gate 1

| Component | v6.2 Gate | Pro-Max Gate 1 |
|-----------|-----------|----------------|
| All workflow manifests (visual, research, audio, delivery) | 2 | Manifests + scripts built, just not loaded by default |
| Template cloning pipeline (clone_converge) | 2 | Pipeline structure + delta calculator built |
| Cost tracking middleware | Not specified | Built (cost_ledger, cost_config, query_costs) |
| Cron guard safety layer | Not specified | Built (cron_guard, cron_loader) |
| Trace export + anomaly detection | Not specified | Built (trace_exporter) |

---

## 18. Cost Model

### v6.2 Description

v6.2 §18 specified monthly infrastructure at ~RM 50 with 80% of production on Qwen by month 12.

### Pro-Max Implementation

Pro-Max added cost tracking infrastructure not present in v6.2:

| Component | Lines | What It Does |
|-----------|-------|-------------|
| `middleware/cost_config.py` | 83 | YAML-based cost configuration (model rates, thresholds) |
| `middleware/cost_ledger.py` | 173 | Per-LLM-call cost recording via lifecycle hooks |
| `middleware/deliverable_context.py` | 56 | ContextVar-based deliverable_id propagation |
| `middleware/trace_exporter.py` | 251 | Anomaly detection + trace JSON export |
| `tools/query_costs.py` | 217 | Model-callable cost inspection (per deliverable, per client, distribution, anomalies) |
| `config/cost_config.yaml` | ~30 | Model pricing, baseline parameters, retention policy |
| `migrations/001_cost_ledger.sql` | Schema | SQLite tables for cost_ledger, quality_results, anomaly_log |

v6.2's cost model was a projection (Month 1: X calls/day, Month 12: Y calls/day). Pro-Max's cost model is instrumented — every token is tracked, attributed to a deliverable, and queryable by the model itself via `query_costs`.

---

## 19. Risk Register

### v6.2 Risks + Pro-Max Mitigations

| v6.2 Risk | v6.2 Mitigation | Pro-Max Mitigation |
|-----------|-----------------|-------------------|
| Overengineering | Revenue gate rule | Revenue gate rule + smaller scope (25 tools vs 47) |
| Wrong toolset at session start | Qwen pre-classification (Gate 2) | Same plan. Gate 1: human specifies workflow. |
| `switch_toolset` patch fails | Restart session | `plugins/switch_toolset.py` implemented with dual fallback |
| `run_pipeline` god-tool | Pipeline summary in system prompt | Registry summary + list mode — identical to v6.2 plan |
| `execute_code` sandbox bypass | Allowlists | Gate 2+ sandbox extensions (permissive imports + audit logging, per Gate 2+3 spec) |
| Unattended bad output | Quality threshold hold | `middleware/cron_guard.py` + `should_hold_delivery()` — explicit implementation |
| Adapter single point of failure | Test suite | 73 test files including integration tests |

### New Risks (Pro-Max specific)

| Risk | Impact | Mitigation |
|------|--------|------------|
| YAML manifest typo breaks tool registration | Tool unavailable | `adapter/schemas.py` Pydantic validation + `manifest_syncer` logs and skips invalid manifests |
| Cost ledger bloats state.db | Disk full, slow queries | 90-day retention + archival in `trace_exporter.py` |
| OpenSpace generates bad pipelines | Bad output | `safety.py` 19-pattern check + quality gate validation before promotion from `_drafts/` |
| Skill evolution conflicts with distillation | Version divergence | Gate 4 advisory locks on version DAG (documented in Gate 4 design) |
| DreamSkill consolidation loses important memory | Knowledge loss | 200-line cap with archive; Qwen consolidation + rule-based fallback |

---

## 20. Ecosystem Adoptions — What Was Actually Adopted

v6.2 §20 listed 16 ecosystem components across 4 gates. Here is what Pro-Max actually did with each:

| # | v6.2 Component | v6.2 Action | Pro-Max Action | Rationale |
|---|---------------|-------------|----------------|-----------|
| 20.1 | Mission Control | Fork + 6 customization sessions | **Deferred** | Doesn't produce billable output. Gate 2+ candidate. |
| 20.2 | PydanticAI | Install for tool contracts | **Rejected for tools, kept for scripts** | YAML manifests replaced `@agent.tool` decorators. Pydantic (not PydanticAI) validates manifests. |
| 20.3 | Knowledge Graph Tool | Clone + index Wisdom Vault | **Dropped from Gate 1** | Requires Wisdom Vault indexing before first output. |
| 20.4 | DSPy | Install for distillation | **Deferred to Gate 3-4** | Needs golden dataset from production runs. Gate 4 redesigned to use direct quality-gate evaluation instead. |
| 20.5 | Promptfoo | Install for benchmarking | **Deferred to Gate 3-4** | Same as DSPy — needs production data. |
| 20.6 | OpenSpace | Install as MCP server | **Absorbed into codebase** | 749 lines in `augments/openspace/`. MCP server available but not required. |
| 20.7 | ClawTeam TOML | Install for team templates | **Rejected** | Workflows implicit in toolset groupings. No TOML files. |
| 20.8 | Nanobot | Clone for code donor | **Patterns extracted** | Channel adapter patterns informed `scripts/delivery/` but no nanobot code was ported. |
| 20.9 | DreamSkill | Clone for pattern reference | **Absorbed into codebase** | 278 lines in `augments/dreamskill/`. 4-phase model implemented on Qwen local. |
| 20.10 | Qwen-Agent | Install for function calling | **Deferred** | Single model in Gate 1. Qwen routing is Gate 2+. |
| 20.11 | Hermes Self-Evolution | Clone + install | **Not adopted** | OpenSpace covers skill evolution. Hermes self-evolution is a separate concern (batch genetic optimization) — evaluated for Gate 4. |
| 20.12 | DeerFlow | Clone for patterns | **Patterns absorbed** | 285 lines in `augments/deerflow/`. Task decomposition + result synthesis + shared memory. Runtime (LangGraph) rejected. |
| 20.13 | Graphiti | Evaluate at Gate 3 | **Not evaluated yet** | Gate 3 not reached. |
| 20.14 | OpenSpace Local | Migrate from MCP to embedded | **Already embedded** | Pro-Max started embedded. MCP is the optional mode. |
| 20.15 | Graphiti Install | Gate 4 if justified | **Not reached** | Gate 4 not reached. |
| 20.16 | Coze Loop | Extract evaluation module | **Not adopted** | Quality gate + cost ledger + trace exporter cover evaluation needs. |

### Adoption Score

- **Actually adopted:** 3 (OpenSpace absorbed, DreamSkill absorbed, DeerFlow patterns absorbed)
- **Partially adopted:** 2 (PydanticAI kept for scripts only, Nanobot patterns informed delivery scripts)
- **Deferred:** 5 (Mission Control, DSPy, Promptfoo, Qwen-Agent, Knowledge Graph Tool)
- **Rejected:** 3 (ClawTeam TOML, Hermes Self-Evolution, Coze Loop)
- **Not reached:** 3 (Graphiti evaluate, Graphiti install, OpenSpace Local — already embedded)

---

## 21. Pattern Reference Queue — What Was Actually Studied

v6.2 §21 listed 6 codebases to study for patterns. Pro-Max cloned 3 into `scouts/`:

| Source | v6.2 Priority | Pro-Max Status | What Was Extracted |
|--------|---------------|----------------|-------------------|
| Letta/MemGPT | P0 | **Not studied** | DreamSkill covers memory consolidation |
| OpenAI Agents SDK | P0 | **Not studied** | Hermes `delegate_task` is sufficient |
| CrewAI | P1 | **Not studied** | Superagent model replaced agent roles |
| ZeroClaw | P2 | **Not studied** | Per-module security implemented instead |
| AMUX | P2 | **Not studied** | Hermes handles its own timeouts |
| Google ADK | P2 | **Not studied** | Pipeline/atomic/improvisation layers cover orchestration types |

The `scouts/` directory contains:
- `OpenSpace/` — full clone, patterns absorbed into `augments/openspace/`
- `deer-flow/` — full clone, patterns absorbed into `augments/deerflow/`
- `dream-skill/` — full clone, patterns absorbed into `augments/dreamskill/`

These are reference copies, not runtime dependencies. The relevant patterns were ported to Pro-Max's codebase.

---

## 22. Rejection Register — What Was Dropped and Why

This section consolidates every v6.2 architectural decision that Pro-Max overrode, with rationale.

### Architectural Rejections

| v6.2 Decision | Pro-Max Decision | Rationale |
|---------------|-----------------|-----------|
| **7 named agents** (Marketing Strategist, Publisher, Media, Analyst, Coder, Steward, Quality Gate) | **1 superagent** with workflow-scoped toolsets | v6.2's own corrections acknowledged this. Named agents added routing overhead (~1KB system prompt per agent role definition) with no functional benefit. Hermes's `delegate_task` provides sub-agent capability without named roles. |
| **PydanticAI `@agent.tool` decorators** for every tool | **YAML manifests** → `adapter/loader.py` → `registry.register()` | PydanticAI required Python handler code per tool (~40 lines each). YAML manifests require ~15 lines of YAML + a script. For 22 tools, this saves ~550 lines of boilerplate. Schema changes are YAML edits, not code changes. |
| **ClawTeam TOML workflow definitions** | **Workflows implicit in toolset groupings** (`config/toolsets.py`) | TOML files would be documentation, not runtime config. Hermes doesn't consume TOML natively. Toolsets already define which tools load per workflow. Adding a declarative layer adds indirection without functionality. |
| **Mission Control dashboard** in Gate 1 | **Deferred to Gate 2+** | 6 customization sessions ≈ 6 engineering sessions that don't produce billable output. Revenue gate rule says billable output first. CLI monitoring + Cloudflare Tunnel suffices for Gate 1. |
| **DSPy + Promptfoo** in Gate 1 | **Deferred to Gate 3-4** | Distillation needs a golden dataset (20-50 exemplars). Gate 1 hasn't produced enough output. Installing tooling before having data is premature. Gate 4 redesigned distillation to use direct quality-gate evaluation instead of DSPy. |
| **Knowledge Graph Tool** in Gate 1 | **Dropped from Gate 1** | Requires indexing 21,000 Wisdom Vault atoms before producing output. Not needed for "first billable output" objective. LightRAG is the simpler path. |
| **Front-loaded training sprint** (Week 2) | **Deferred indefinitely** | Training sprint assumes tools are working and calibrated. Gate 1 is about making tools work. Sprint can run after Gate 1 exit criteria are met. |
| **Qwen-Agent function calling patterns** | **Deferred to Gate 2** | Gate 1 uses GPT-5.4-mini only. Qwen routing is Gate 2 scope. Installing Qwen-Agent before using Qwen for routing is premature. |
| **47 tool count** | **25 tools (22 manifest + 3 custom)** | v6.2 counted libraries as tools. Pro-Max counts what Hermes registers. Libraries are implementation details of scripts, not tools. |
| **35 plugin count** | **4 lifecycle plugins** | v6.2 counted middleware, augments, and external tools as "plugins." Pro-Max counts only what hooks into Hermes lifecycle events. |
| **4 skill libraries** | **0 external libraries** | Skills are SKILL.md files managed by OpenSpace's version DAG. No external skill library runtime needed. |
| **OpenSpace as MCP server** (Gate 2) → **embedded** (Gate 4) | **Embedded from Gate 1** | Tighter integration with SQLite state. MCP mode available but optional. Gate 2+3 design doc explicitly overrode v6.2 on this. |
| **DSPy for distillation** | **Direct quality-gate evaluation** | Gate 4 design doc: "No DSPy. Distillation uses direct quality gate evaluation against exemplar traces instead." DSPy adds a dependency and learning curve for a problem solvable with the existing quality gate + cost ledger. |
| **Nanobot code porting** (telegram.py, whatsapp.py, memory.py, gateway/) | **Clean implementation** | `scripts/delivery/send_telegram.py` (66 lines) and `send_whatsapp.py` (56 lines) are simpler than porting nanobot's channel abstraction. Different architecture (script-based vs event-bus) makes porting impractical. |
| **Hermes Self-Evolution** (NousResearch genetic optimization) | **Not adopted** | OpenSpace captures/fixes/derives skills. Genetic batch optimization is a different time horizon and adds DSPy dependency. Evaluated for Gate 4 but not prioritized. |
| **Coze Loop evaluation patterns** | **Not adopted** | Quality gate (6 layers) + cost ledger + trace exporter already provide multi-dimensional evaluation. Coze Loop adds a ByteDance dependency for functionality already built. |

### Dependency Rejections

| v6.2 Dependency | Pro-Max Status | Rationale |
|-----------------|----------------|-----------|
| `pydantic-ai` | **Kept for scripts only** | Not used for tool registration. Used inside scripts for structured LLM output validation. |
| `clawteam` | **Rejected** | TOML team templates not needed. |
| `qwen-agent` | **Deferred** | Gate 2 scope. |
| `dspy` | **Rejected from Gate 1-3, evaluated for Gate 4** | Gate 4 design uses direct evaluation instead. |
| `promptfoo` | **Deferred** | Needs production data. |
| `nanobot` (code donor) | **Patterns only** | No code ported. |
| `dream-skill` (code donor) | **Patterns absorbed** | 4-phase model reimplemented in `augments/dreamskill/`. |
| `deer-flow` (code donor) | **Patterns absorbed** | Task decomposition + result synthesis reimplemented in `augments/deerflow/`. |
| `hermes-agent-self-evolution` | **Not adopted** | OpenSpace covers skill evolution. |
| `graphiti` + `falkordb` | **Not evaluated** | Gate 3+ scope. |

### The Simplicity Principle in Action

Every rejection follows v6.2's own P8 (Simplicity):

> "Following the Anthropic 'Building Effective Agents' hierarchy: single optimised LLM call → augmented LLM → workflow patterns → orchestrator-workers → full autonomous agents. Move up only when the layer below demonstrably fails."

Pro-Max applied this rigorously. If a simpler mechanism existed (YAML instead of PydanticAI, quality gate instead of DSPy, toolsets instead of TOML workflows), Pro-Max used the simpler mechanism. Complexity was added only when the simpler approach demonstrably failed — and in Gate 1, most of these failures haven't happened yet.

---

## 23. Distillation Pipeline — Redesigned for Gate 4

### v6.2 Description (§23)

v6.2 specified a 4-stage distillation progression:
1. Gate 1: Full LLM reasoning
2. Gate 2: OpenSpace captured patterns (46% cheaper)
3. Gate 3: DSPy distills to Qwen local (zero cost)
4. Gate 4: Self-distillation (autonomous)

### Pro-Max Redesign

The Gate 4 design doc (`specs/2026-04-01-gate-4-design.md`) rejected DSPy and replaced it with:

**Direct quality-gate evaluation against exemplar traces:**

1. Cost ledger identifies expensive steps (high token usage, frequent execution)
2. Candidate filter removes vision-dependent steps and those with < 20 exemplar traces
3. Prompt adapter generates Qwen-specific prompts (not identical to GPT-5.4-mini prompts)
4. Qualification: run Qwen version through quality gate against exemplar outputs
5. Model router switches qualified steps to Qwen with fallback retry
6. Auto-revert: 3 fallbacks in 24 hours → automatic revert to GPT-5.4-mini

**Why no DSPy:**
- DSPy is a prompt optimization framework that requires defining signatures, building eval datasets, and running genetic algorithms
- Pro-Max already has quality gates that evaluate output quality and cost ledgers that track per-step costs
- The information needed for distillation (which steps are expensive, what good output looks like) already exists in the system's own traces
- Adding DSPy introduces a new abstraction layer and learning curve for a problem solvable with existing infrastructure

### Progressive Offload Model

```
Step identified as expensive (cost_ledger)
  → Check: 20+ exemplar traces exist? Not vision-dependent?
  → Adapt prompt for Qwen (different template, few-shot examples)
  → Run through quality gate against exemplar outputs
  → If quality ≥ 7.0: route to Qwen
  → Monitor: 3 fallbacks in 24h → auto-revert to GPT-5.4-mini
  → Progressive: Qwen earns each step independently
```

---

## 24. Template Cloning Loop — Implemented as Pipeline

See §13 (Design Intelligence). v6.2 §24 is fully implemented as `pipelines/clone_converge.py` + `scripts/visual/calculate_delta.py`. Architecture identical to v6.2's specification; packaging differs (split into pipeline + scripts vs monolithic pipeline).

---

## 25. Reverse Prompt Engineering — Deferred

### v6.2 Description (§25)

v6.2 specified three approaches: RPEF (fast), RPEGA (precision), Kaggle dataset validation.

### Pro-Max Status

**Not implemented.** Deferred because:

1. Reverse prompt engineering requires existing high-quality outputs to reverse-engineer from
2. Gate 1 hasn't produced enough outputs to build a swipe bank
3. OpenSpace's CAPTURED mode achieves a similar goal (extracting successful patterns) without the reverse-engineering complexity
4. Can be added as a pipeline when swipe bank is populated

---

## 26. Front-Loaded Training Sprint — Deferred

### v6.2 Description (§26)

Two-week training sprint: swipe bank preloading, recipe reverse-engineering, model comparison, quality gate calibration, lock and review.

### Pro-Max Status

**Deferred indefinitely.** Rationale:

1. Training sprint assumes tools work and quality gate is calibrated — both are Gate 1 exit criteria, not Gate 1 activities
2. v6.2 placed this in "Phase 1D: Training Sprint — Week 2 (Day 8-14)" — but Gate 1 sessions 1-3 build the tools that the sprint needs
3. The sprint can run after Gate 1 exit criteria are met, using actual production outputs instead of synthetic test data
4. Pro-Max's approach: produce real client output first, then calibrate from reality, not from a pre-planned sprint

---

## 27. Prompt Logger Plugin — Implemented as Lifecycle Hook

### v6.2 Description (§27)

v6.2 provided a complete 30-line plugin for `~/.hermes/plugins/prompt_logger.py` with `pre_llm_call` and `post_llm_call` hooks writing to SQLite.

### Pro-Max Implementation

`plugins/prompt_logger.py` (124 lines) — expanded from v6.2's 30-line version:

| Feature | v6.2 (30 lines) | Pro-Max (124 lines) |
|---------|-----------------|---------------------|
| Basic prompt capture | Yes | Yes |
| Token count update | Yes | Yes |
| Thread-safe step counter | No | Yes (with 10K task cap + auto-clear) |
| Deliverable ID tracking | No | Yes (via `deliverable_context`) |
| Non-fatal error handling | No | Yes (errors logged, not raised) |
| Maximum tracked tasks | Unlimited (memory leak risk) | 10,000 with automatic clear |

The expansion from 30 to 124 lines addresses production concerns: memory management (bounded step counter), cross-deliverable tracing (deliverable_id column), and fault tolerance (non-fatal errors prevent plugin failures from crashing Hermes).

---

## APPENDIX A: Repository Structure (Actual)

```
~/vizier-pro-max/
├── adapter/                     # Manifest → Hermes tool engine (494 lines)
│   ├── loader.py                # Reads manifests → registry.register() (112)
│   ├── executor.py              # Runs scripts with validation (187)
│   └── schemas.py               # Manifest schema, YAML → OpenAI dict (195)
│
├── augments/                    # Absorbed agentic components (1,312 lines)
│   ├── openspace/               # Skill evolution (749 lines, 8 files)
│   ├── dreamskill/              # Memory consolidation (278 lines, 3 files)
│   └── deerflow/                # Sub-agent coordination (285 lines, 3 files)
│
├── bridge/                      # Claude Code ↔ Vizier awareness (887 lines)
│   ├── watcher.py               # Entry point (113)
│   ├── git_watcher.py           # Commits → MEMORY.md (433)
│   ├── skill_syncer.py          # Bi-directional skill sync (106)
│   ├── test_parser.py           # Module confidence (128)
│   ├── manifest_syncer.py       # New manifests detection (90)
│   └── cron_loader.py           # Cron config → scheduler (117)
│
├── config/                      # Configuration
│   ├── SOUL.md                  # Vizier persona + priority rules
│   ├── hermes.yaml              # Hermes runtime config
│   ├── toolsets.py              # Toolset definitions
│   ├── openspace.yaml           # Skill evolution config
│   ├── cost_config.yaml         # Cost tracking + thresholds
│   ├── mcp_servers.json         # OpenSpace MCP server config
│   └── cron/                    # Unattended session definitions
│       ├── content_calendar.yaml
│       ├── health_check.yaml
│       └── quality_review.yaml
│
├── manifests/                   # YAML tool definitions (22 tools)
│   ├── content/                 # httpx_fetch, jinja2_render, lightrag_search
│   ├── document/                # typst_render, pandoc_convert, pypdf_merge
│   ├── visual/                  # fal_generate, pillow_process, playwright_screenshot
│   ├── research/                # pandas_analyze, matplotlib_chart
│   ├── audio/                   # edge_tts_speak, ffmpeg_process
│   └── delivery/                # send_telegram, send_whatsapp
│
├── middleware/                   # Cross-cutting concerns (1,013 lines)
│   ├── quality_gate.py          # 6-layer QA (376)
│   ├── cost_ledger.py           # Per-call cost tracking (173)
│   ├── trace_exporter.py        # Anomaly detection + export (251)
│   ├── cost_config.py           # YAML config loader (83)
│   ├── cron_guard.py            # Unattended safety (74)
│   └── deliverable_context.py   # Cross-session tracing (56)
│
├── pipelines/                   # Collapsed pipeline scripts (349 lines)
│   ├── _registry.yaml           # Pipeline index (64)
│   ├── content_generate.py      # Brief → content → PDF (148)
│   ├── clone_converge.py        # Image → template convergence (128)
│   ├── poster_batch.py          # Batch poster production (stub, 26)
│   ├── competitive_analysis.py  # Market analysis (stub, 23)
│   └── tts_generate.py          # Text-to-speech (stub, 24)
│
├── plugins/                     # Hermes lifecycle hooks (324 lines)
│   ├── prompt_logger.py         # pre/post LLM call capture (124)
│   ├── deerflow_orchestration.py # decompose_task + merge_results (88)
│   ├── switch_toolset.py        # Mid-session toolset change (74)
│   └── context_injector.py      # Cross-session deliverable_id (38)
│
├── scripts/                     # The hands — stable executables (1,512 lines)
│   ├── content/                 # fetch_url (81), render_template (25), search_rag (28)
│   ├── document/                # render_typst (122), convert_format (73), merge_pdfs (62)
│   ├── visual/                  # screenshot_html (63), process_image (73), generate_image (71),
│   │                            # calculate_delta (226), parameterize_template (31)
│   ├── research/                # analyze_data (140), render_chart (76)
│   ├── audio/                   # process_media (143), speak_text (76)
│   └── delivery/                # send_telegram (66), send_whatsapp (56)
│
├── tools/                       # Custom Hermes tool handlers (475 lines)
│   ├── run_pipeline.py          # Pipeline executor + list mode (156)
│   ├── query_logs.py            # Prompt trace inspection (102)
│   └── query_costs.py           # Cost ledger inspection (217)
│
├── scouts/                      # Reference implementations (read-only)
│   ├── OpenSpace/               # Skill evolution reference
│   ├── deer-flow/               # Sub-agent patterns reference
│   └── dream-skill/             # Memory consolidation reference
│
├── state/
│   └── openspace_skills.db      # Skill version DAG (SQLite)
│
├── migrations/
│   └── 001_cost_ledger.sql      # Cost tracking schema
│
├── tests/                       # 73 test files
├── docs/                        # Design specs + implementation plans
├── pyproject.toml               # Python 3.11+, all dependencies
└── CLAUDE.md                    # Project-specific instructions
```

### Line Count Summary

| Module | Files | Lines |
|--------|-------|-------|
| adapter/ | 3 | 494 |
| augments/ | 14 | 1,312 |
| bridge/ | 6 | 887 |
| middleware/ | 6 | 1,013 |
| pipelines/ | 5 + registry | 349 |
| plugins/ | 4 | 324 |
| scripts/ | 17 | 1,512 |
| tools/ | 3 | 475 |
| **Total production code** | **58** | **~6,366** |
| tests/ | 73 | ~4,000+ |

---

## APPENDIX B: Dependency Comparison

### v6.2 Install Commands (Gate 1)

```bash
# v6.2 Gate 1 installs
pip install pydantic-ai        # Rejected for tool registration
pip install dspy               # Deferred to Gate 3-4
npm install -g promptfoo       # Deferred to Gate 3-4
# Mission Control fork          # Deferred to Gate 2+
# Knowledge Graph Tool           # Dropped from Gate 1
```

### Pro-Max Actual Dependencies (pyproject.toml)

```
# Core
pydantic, pyyaml, structlog, httpx, mcp

# Document
jinja2, pypdf, pillow

# Visual
playwright, scikit-image, opencv-python-headless, pytesseract, pixelmatch

# Data
pandas, matplotlib

# Language
lingua-py

# Audio
edge-tts

# Delivery
python-telegram-bot

# Dev
pytest, pytest-cov, pyright, ruff, black
```

No `pydantic-ai`, no `dspy`, no `promptfoo`, no `clawteam`, no `qwen-agent`. Every dependency serves a direct tool implementation purpose.

---

## APPENDIX C: Cross-Reference to v6.2 Build Plan Sessions

| v6.2 Session | v6.2 Scope | Pro-Max Equivalent |
|-------------|-----------|-------------------|
| Session 1 | Hermes install + first run | Assumed complete (Hermes v0.6.0 at `~/hermes-agent/`) |
| Session 2 | PydanticAI tool wrappers | **Replaced by** `adapter/` + `manifests/content/` + `scripts/content/` |
| Session 3 | Quality gate L1-2 | `middleware/quality_gate.py` (376 lines, all 6 layers) |
| Session 4 | Mission Control fork | **Deferred** |
| Session 5 | Prompt logger plugin | `plugins/prompt_logger.py` (124 lines) |
| Session 6 | DSPy + Promptfoo install | **Deferred** |
| Session 7 | Knowledge Graph Tool | **Dropped from Gate 1** |
| Session 8 | Content workflow E2E | `pipelines/content_generate.py` + supporting scripts |
| Day 8-14 | Training sprint | **Deferred** |
| Sessions 9-11 | Additional workflows | All manifests + scripts built (ahead of schedule) |
| Session 12 | OpenSpace install | `augments/openspace/` (absorbed, 749 lines) |
| Session 13 | DreamSkill install | `augments/dreamskill/` (absorbed, 278 lines) |
| Session 14 | Qwen-Agent install | **Deferred** |
| Sessions 15-16 | Scheduled/event triggers | `config/cron/` + `bridge/cron_loader.py` + `middleware/cron_guard.py` |
| Session 17 | Nanobot channel adapters | `scripts/delivery/` (clean implementation, 122 lines) |
| Session 18 | Template cloning loop | `pipelines/clone_converge.py` + `scripts/visual/calculate_delta.py` |
| Session 19 | ClawTeam TOML | **Rejected** |
| Session 20 | Mission Control expansion | **Deferred** |
| Session 21 | Quality gate L3-6 | Already in `middleware/quality_gate.py` (built ahead) |
| Sessions 22-24 | DSPy distillation + RPEF | **Deferred/Redesigned** |
| Sessions 25-26 | Code + Audio workflows | Audio built; Code deferred |
| Session 27 | Hermes self-evolution | **Not adopted** |
| Session 28 | DeerFlow patterns | `augments/deerflow/` (absorbed, 285 lines) |
| Sessions 29-31 | Data/pattern triggers, Graphiti | **Not reached** |
| Sessions 32-38 | Gate 4 self-distillation | Designed (`specs/2026-04-01-gate-4-design.md`), not built |

---

**This document is the canonical architecture reference for vizier-pro-max. When in doubt, this document and the code win.**
