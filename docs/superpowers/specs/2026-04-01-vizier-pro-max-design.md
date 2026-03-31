# Vizier Pro-Max — Architecture Design Spec

**Date:** 2026-04-01
**Author:** Khairul / Premier Marketing
**Status:** Draft v3 — second review fixes applied
**Repo:** ~/vizier-pro-max/ (clean slate)
**Fallback:** ~/vizier-ultimate/ (Gate 2, Hermes v0.6.0)
**Hermes version:** v0.6.0 at ~/hermes-agent/

---

## 1. Identity & Philosophy

**Vizier** is the brain — the persona, the decision-maker, the identity.
**Hermes** is the engine — the sole runtime that executes Vizier's decisions.
**Stable Python scripts** are the hands — proven libraries and CLIs wired as tools.
**Absorbed agentic components** are the nervous system — OpenSpace, dream-skill, DeerFlow ported as Hermes plugins.

### Core Principles

1. **Hermes is the sole runtime.** No competing runtimes. No LangGraph, no CrewAI, no OpenAI Agents SDK as runtime. Patterns extracted, runtimes rejected.
2. **Superagent model.** ONE Hermes agent with workflow-scoped toolset loading. No named agent roles. Complex tasks use Hermes's native `delegate_task` for sub-agents (not custom spawning).
3. **Scripts as hands.** Stable Python libraries/CLIs are the tool layer. The model never touches raw APIs — scripts encapsulate all execution.
4. **Collapse what repeats.** Deterministic sequences become collapsed pipelines behind `run_pipeline`. Atomic tools exist as fallback. `execute_code` for improvisation. OpenSpace captures new patterns automatically.
5. **Toolsets control token cost.** Tools are grouped into named toolsets. Only the relevant toolset loads per task. Gate 1: toolset set at session start. Gate 2: `switch_toolset` enables mid-session changes (requires Hermes patch).
6. **Bridge connects inside and outside.** Claude Code builds on the outside, the bridge informs Vizier on the inside. Bidirectional awareness.
7. **Gate-by-gate revenue rule.** Each gate must produce billable output before the next unlocks.

---

## 2. Session Model

Vizier operates across three session types. Each has distinct toolset, trigger, and supervision characteristics.

### 2.1 Interactive Sessions (Gate 1+)

**Trigger:** Human prompt via Telegram, WhatsApp, dashboard chat, API call.
**Toolset:** Set at session start based on task classification. Gate 2+: switchable mid-session.
**Supervision:** Human in the loop. Vizier asks for clarification when needed.
**Concurrency:** One session per channel. Sequential.

### 2.2 Parallel Sessions (Gate 2+)

**Trigger:** Complex task decomposed via Hermes `delegate_task`. Parent spawns 2-3 child sessions.
**Toolset:** Each child gets its own toolset at spawn time (scoped by the parent).
**Supervision:** Parent agent synthesizes results. No human in the loop during execution.
**Concurrency:** Up to 3 parallel children per parent. Each child runs in isolated context with its own tool surface.

**How it works with Hermes:** `delegate_task` is a built-in Hermes tool that creates a scoped sub-conversation. Each child's toolsets are **intersected with the parent's** — children cannot access tools the parent doesn't have. This means the parent orchestration session must be started with broad toolsets.

**Parent session strategy:** The parent runs with `vizier-fallback` (all tools, ~54KB) so it can delegate to any workflow. The token cost is acceptable for the orchestrating session because it's coordinating, not doing heavy reasoning. Each child runs lean with its scoped toolset (~14-18KB).

**Child constraints (Hermes built-in):**
- Children cannot use `execute_code` (blocked by `DELEGATE_BLOCKED_TOOLS`)
- Children are restricted to Layer 1 (pipelines) and Layer 2 (atomic tools) — no improvisation
- If a child needs improvisation, the parent must handle it after child results return

**Example:**
```
Parent receives: "Produce campaign for DMB: research + copy + poster + PDF"
Parent session: enabled_toolsets=["vizier-fallback"] (~54KB, orchestration session)
  -> delegate_task("research brief for DMB", toolsets=["vizier-research"])  # child: ~14KB
  -> delegate_task("generate 3 ad copies for DMB", toolsets=["vizier-content"])  # child: ~14KB
  -> delegate_task("design poster for DMB campaign", toolsets=["vizier-visual"])  # child: ~14KB
  -> Parent waits for all 3 -> synthesizes into campaign package
  -> run_pipeline("report") to compile PDF
  -> send_telegram to deliver
```

### 2.3 Unattended Sessions (Gate 2+)

**Trigger:** Hermes cron, event-driven (Islamic calendar, client milestones), data-driven (file upload).
**Toolset:** Predefined per scheduled task in cron config. Fixed for the session.
**Supervision:** Zero human input. Quality gate is the only checkpoint. If quality score < threshold, output is held for human review instead of delivered.
**Concurrency:** Multiple unattended sessions can run simultaneously via Hermes cron scheduler.

**Safety constraints for unattended:**
- Only modules with test_parser confidence "high" or "medium" are eligible
- Quality gate must pass all active layers (no override)
- Token budget cap per unattended session (prevent runaway costs)
- Delivery held if quality score < configurable threshold (default: 7/10)
- Structlog captures full trace for post-mortem review

**Scheduled task types:**
| Type | Trigger | Example |
|------|---------|---------|
| Content calendar | Hermes cron (daily/weekly) | Generate scheduled social posts per client |
| Quality review | Hermes cron (weekly) | Audit last week's output scores, flag regressions |
| Health check | Hermes cron (daily) | System status, token usage, error rates |
| Event-driven | Islamic calendar (adhan-python) | Ramadan content, Eid campaigns, Friday posts |
| Client milestone | Campaign deadline, product launch | Auto-generate deliverables before due date |
| Data-driven | CSV/file upload via API | Batch poster production from product data |

**Gate mapping for session types:**
| Session type | Gate 1 | Gate 2 | Gate 3 | Gate 4 |
|-------------|--------|--------|--------|--------|
| Interactive | Human prompts only | + Telegram/WhatsApp channels | + code workflow | Full |
| Parallel | Not available | delegate_task with scoped toolsets | + pattern-driven | + observation-driven |
| Unattended | Not available | Scheduled + event-driven cron | + data-driven triggers | + research-driven, self-evolving |

---

## 3. Repository Structure

```
~/vizier-pro-max/
├── bridge/                   # Bidirectional Claude Code <-> Vizier awareness
│   ├── watcher.py            # Entry point (git hook + cron trigger)
│   ├── git_watcher.py        # Commits -> Hermes MEMORY.md
│   ├── skill_syncer.py       # Bi-directional skill flow (repo <-> ~/.hermes/skills/)
│   ├── test_parser.py        # Module confidence registry
│   └── manifest_syncer.py    # New manifests -> updates registry (next session picks up)
│
├── adapter/                  # Universal manifest -> Hermes tool engine
│   ├── loader.py             # Reads manifests -> calls tools.registry.register() with OpenAI-format schemas
│   ├── executor.py           # Runs scripts with validation + error handling
│   └── schemas.py            # Manifest schema, base types, YAML -> OpenAI tool dict conversion
│
├── manifests/                # YAML tool definitions (atomic tools, ~70% of tools)
│   ├── content/
│   ├── document/
│   ├── visual/
│   ├── research/
│   ├── audio/
│   └── code/
│
├── tools/                    # Custom Hermes tool handlers (complex tools only)
│   ├── run_pipeline.py       # Execute collapsed pipelines by name or list them
│   └── query_logs.py         # Inspect prompt logger traces (model-callable)
│
├── plugins/                  # Hermes lifecycle hooks (NOT tools — auto-invoked)
│   └── prompt_logger.py      # pre_llm_call / post_llm_call capture
│
├── pipelines/                # Collapsed pipeline scripts
│   ├── _registry.yaml        # Pipeline index (name, description, input/output schema)
│   ├── content_generate.py
│   ├── content_social.py
│   ├── invoice.py
│   ├── report.py
│   ├── clone_converge.py
│   ├── poster_batch.py
│   └── _drafts/              # Auto-generated from OpenSpace CAPTURED
│
├── augments/                 # Absorbed agentic components (nervous system)
│   ├── openspace/            # Skill evolution (CAPTURED/FIXED/DERIVED)
│   │   ├── capturer.py       # Successful patterns -> SKILL.md + pipeline drafts
│   │   ├── fixer.py          # Auto-repair broken skills/pipelines from error logs
│   │   ├── deriver.py        # Promote better variants
│   │   ├── version_dag.py    # Skill lineage tracking
│   │   ├── safety.py         # check_skill_safety before load
│   │   └── pruner.py         # Archive stale skills to reduce index
│   ├── dreamskill/           # Memory consolidation (4-phase on Qwen local)
│   │   ├── consolidator.py   # DECIDE -> GATHER -> CONSOLIDATE -> PRUNE
│   │   ├── signals.py        # Signal extraction from structlog traces
│   │   └── pruner.py         # MEMORY.md size management
│   └── deerflow/             # Sub-agent coordination patterns (for delegate_task)
│       ├── task_decomposer.py  # Complex task -> parallel sub-task specs
│       ├── result_synthesizer.py # Merge sub-agent outputs into final deliverable
│       └── shared_memory.py  # Debounced async queue for cross-agent observations
│
├── middleware/                # Cross-cutting concerns (not model-callable tools)
│   └── quality_gate.py       # 6-layer QA — called by pipeline scripts and adapter/executor.py
│
├── scripts/                  # The actual hands (stable executables)
│   ├── content/
│   ├── document/
│   ├── visual/
│   ├── research/
│   ├── audio/
│   └── code/
│
├── config/
│   ├── clients/              # Per-client YAML ({client_id})
│   ├── hermes.yaml           # Hermes runtime config
│   ├── models.yaml           # Model routing (GPT-5.4-mini + Qwen local)
│   ├── SOUL.md               # Vizier persona, voice, tool-layer priority rules
│   └── cron/                 # Unattended session definitions (Gate 2+)
│       ├── content_calendar.yaml
│       ├── quality_review.yaml
│       └── health_check.yaml
│
├── tests/
├── docs/
├── pyproject.toml
└── CLAUDE.md
```

### Key design decisions (post-review)

- **No PydanticAI in the tool registration layer.** Hermes uses `tools.registry.register()` with OpenAI-format tool dicts. The adapter generates these directly from YAML manifests. PydanticAI is used only inside scripts for input validation — not for tool registration.
- **No TOML workflow files in Gate 1.** Workflow definitions are documentation, not runtime config. Hermes doesn't consume TOML natively. Workflows are implicit in toolset groupings and pipeline definitions.
- **Quality gate wiring:** Pipeline scripts call `middleware.quality_gate.validate()` directly. The adapter's `executor.py` calls it after every atomic tool execution. Not magic — explicit function calls.
- **`manifest_syncer` updates the registry file, not the running session.** New tools are available on next session start, not mid-session. This is honest about Hermes's session init model.

---

## 4. Tool Architecture: Three Layers

### 4.1 Layer 1 — Collapsed Pipelines (Cheapest)

Deterministic sequences wrapped as single scripts. Registered in `pipelines/_registry.yaml`, executed via `run_pipeline` tool.

**Token cost per turn:** `run_pipeline` tool schema ~1.5KB + pipeline registry summary in system prompt ~2KB = **~3.5KB baseline** regardless of pipeline count.

**`run_pipeline` has a `list` mode:** When model is uncertain, it calls `run_pipeline(action="list")` to get full pipeline schemas. Costs one turn but only when needed.

### 4.2 Layer 2 — Atomic Tools (Moderate)

Individual library/CLI wrappers registered via YAML manifests. Loaded per toolset. Used when:
- No pipeline covers the task
- Pipeline failed and model needs manual control
- Steps require model reasoning between them

### 4.3 Layer 3 — Improvisation (Expensive, Creative)

Hermes's built-in `execute_code` tool (Unix domain socket RPC to sandboxed subprocess). Gate 1 uses it unmodified. Gate 2+ adds a wrapper with additional constraints:

**Gate 2+ sandbox extensions (on top of Hermes built-in):**
- Allowlisted imports only (libraries in the tool stack)
- Write access restricted to `output/` and `tmp/`
- Network access only to configured endpoints
- Timeout: 30s default (configurable)

**Note:** `execute_code` is blocked for `delegate_task` children (Hermes built-in restriction). Improvisation via execute_code is parent-session only. Children are restricted to Layer 1 (pipelines) and Layer 2 (atomic tools).

### 4.4 Priority Rule (in SOUL.md)

```
When executing a task:
1. FIRST: Try run_pipeline. If a pipeline exists for this task, use it.
2. IF NO PIPELINE: Use atomic tools from your active toolset.
3. IF ATOMIC TOOLS INSUFFICIENT: Use execute_code to compose a solution.
4. NEVER skip layers. Always try the cheaper option first.
```

(Gate 1 has no `switch_toolset` — toolset is set at session start. Gate 2 adds mid-session switching.)

### 4.5 The Capture Loop (OpenSpace Integration, Gate 2+)

```
Novel task -> no pipeline exists
  -> Model uses atomic tools (4-5 calls)
  -> Prompt logger records full chain
  -> Same pattern repeats 5+ times (configurable, default 5)
  -> OpenSpace CAPTURED generates pipeline script -> pipelines/_drafts/
  -> Quality gate validates draft pipeline
  -> Bridge: manifest_syncer updates _registry.yaml
  -> Next session: run_pipeline handles it in 1 call instead of 4-5

Pipeline breaks -> run_pipeline returns error
  -> Model falls back to atomic tools (graceful degradation)
  -> OpenSpace FIXED detects failure -> patches pipeline script
  -> Next session: patched pipeline works

Pipeline doesn't quite fit -> model mixes pipeline + atomic tools
  -> Variant repeats -> OpenSpace captures as new pipeline variant
```

---

## 5. Toolset Map

### 5.1 Always-Loaded Toolsets

**vizier-core (3 tools):**
| Tool | Type | Purpose |
|------|------|---------|
| `run_pipeline` | custom handler | Execute collapsed pipelines by name or list them |
| `query_logs` | custom handler | Inspect prompt logger traces (last N calls, filter by task) |
| `httpx_fetch` | manifest (shared) | Fetch URLs, APIs — used by content, research, delivery |

**Hermes built-in toolsets (always enabled alongside vizier-core):**
- `code_execution` — Hermes's built-in `execute_code` (improvisation layer)
- `delegation` — Hermes's built-in `delegate_task` (parallel sessions, Gate 2+)

**Prompt logger** is a Hermes lifecycle hook plugin (`pre_llm_call`, `post_llm_call`), NOT a tool. It captures every LLM call automatically. The `query_logs` tool provides model-accessible inspection of captured traces.

**`lightrag_search`** is registered in vizier-core (shared across content, knowledge, and research workflows) to avoid name collisions when multiple toolsets load.

Note: `switch_toolset` is **Gate 2** (requires Hermes patch to mutate `self.tools` mid-session). Gate 1 sets toolset at session init only.

### 5.2 Workflow Toolsets (loaded per task)

**vizier-content (1 atomic tool — httpx_fetch and lightrag_search are in vizier-core):**
| Tool | Library | Purpose |
|------|---------|---------|
| `jinja2_render` | jinja2 | Template rendering |

**Collapsed pipelines:** `content_generate`, `content_social`, `content_email`

**vizier-document (3 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `typst_render` | typst CLI | PDF rendering |
| `pandoc_convert` | pandoc CLI | Format conversion |
| `pypdf_merge` | pypdf | PDF manipulation |

**Collapsed pipelines:** `invoice`, `report`, `ebook_compile`, `presentation`

**vizier-visual (3 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `playwright_screenshot` | playwright | HTML -> screenshot |
| `pillow_process` | pillow | Image manipulation |
| `fal_generate` | fal.ai | AI image generation |

**Collapsed pipelines:** `clone_converge`, `poster_batch`, `bg_remove_batch`

**vizier-research (2 atomic tools — httpx_fetch is in vizier-core):**
| Tool | Library | Purpose |
|------|---------|---------|
| `pandas_analyze` | pandas | Data analysis |
| `matplotlib_chart` | matplotlib | Chart generation |

**Collapsed pipelines:** `competitive_analysis`, `market_scan`, `trend_report`

**vizier-audio (2 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `ffmpeg_process` | ffmpeg CLI | Audio/video processing |
| `edge_tts_speak` | edge-tts | Text-to-speech |

**Collapsed pipelines:** `tts_generate`, `transcribe`, `podcast_produce`

**vizier-delivery (2 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `send_telegram` | python-telegram-bot | Telegram delivery |
| `send_whatsapp` | httpx | WhatsApp delivery |

No collapsed pipelines — destination/message always varies.

**vizier-code (2 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `aider_edit` | aider | Code scaffolding |
| `git_commit` | git CLI | Version control |

**Collapsed pipelines:** `build_tool_wrapper`

**vizier-knowledge (2 atomic tools — lightrag_search is in vizier-core):**
| Tool | Library | Purpose |
|------|---------|---------|
| `sqlite_query` | sqlite3 | Direct DB queries |
| `kg_search` | kg-tools | Knowledge graph queries |

**Collapsed pipelines:** `knowledge_query`, `wisdom_vault_search`

**vizier-fallback (all atomic tools combined, ~22 tools):**

Loaded ONLY on explicit request when current toolset is insufficient and no pipeline fits. Contains all atomic tools from all workflows. Expensive (~44KB) but available as last resort before `execute_code`.

### 5.3 Token Cost Summary

| Scenario | Tools in context | Approx cost (schemas + system prompt) |
|----------|-----------------|--------------------------------------|
| Single workflow | core (3) + workflow (2-3) + pipeline summary | ~14-18KB total |
| Complex task (parallel sub-agents) | Each child: core (3) + its workflow (2-3) | ~14-18KB per child |
| Pipeline failure + fallback | core (3) + fallback (22) + pipeline summary | ~54KB total |

Compare: v6.2 architecture = 47 tools all loaded = ~94KB+ per turn.

---

## 6. Manifest Format

A YAML file that turns any script/CLI into a Hermes tool with zero handler code.

```yaml
# manifests/document/typst_render.yaml
name: typst_render
description: "Compile Typst markup into PDF"
version: "1.0"
toolset: vizier-document             # registers into this Hermes toolset

execution:
  type: cli                           # or "python_script", "python_function"
  command: "typst compile {input_path} {output_path}"
  timeout: 30

input:
  input_path:
    type: string
    required: true
    description: "Path to .typ source file"
  output_path:
    type: string
    required: true
    description: "Path for output PDF"

output:
  file_path:
    type: string
    description: "Path to generated PDF"

retry:
  max_attempts: 2
  on: [timeout, runtime_error]
```

### Adapter -> Hermes Integration (resolves review C3)

`adapter/loader.py` converts each manifest YAML into an OpenAI-format tool dict and calls Hermes's `tools.registry.register()`:

```python
# Pseudocode for adapter/loader.py
from tools.registry import registry

def register_manifest(manifest: dict) -> None:
    """Convert YAML manifest to Hermes tool registration."""
    tool_schema = {
        "type": "object",
        "properties": {
            name: {"type": prop["type"], "description": prop.get("description", "")}
            for name, prop in manifest["input"].items()
        },
        "required": [n for n, p in manifest["input"].items() if p.get("required")],
    }

    registry.register(
        name=manifest["name"],
        toolset=manifest["toolset"],           # e.g., "vizier-document"
        schema=tool_schema,
        handler=lambda args, **kw: executor.run(manifest, args),
        check_fn=lambda: True,                  # or check for CLI availability
        description=manifest["description"],
    )
```

No PydanticAI in this path. Pydantic (not PydanticAI) validates manifest YAML structure. PydanticAI is used only inside pipeline/script code for structured LLM output validation.

---

## 7. Bridge (Claude Code <-> Vizier Awareness)

### 7.1 git_watcher.py

Cherry-picked from vizier-ultimate (`vizier/adapter/git_watcher.py`, 373 lines, proven). Detects commits, extracts file/function/class changes, writes to Hermes MEMORY.md.

**Trigger:** Post-commit git hook + launchd cron (5-min fallback).

### 7.2 skill_syncer.py

Cherry-picked from vizier-ultimate (94 lines, proven). Bi-directional sync. Newer mtime wins on conflict.

### 7.3 test_parser.py

Cherry-picked from vizier-ultimate (119 lines, proven). Module confidence classification for unattended session eligibility.

### 7.4 manifest_syncer.py (NEW)

Watches `manifests/` and `pipelines/` directories. When new files appear:
1. Validates YAML against manifest schema
2. Updates `pipelines/_registry.yaml` if new pipeline
3. Logs to Hermes MEMORY.md: "New tool available: {name}. Restart session to use."

**Honest behavior:** New tools available on next session start, not mid-session. Hermes rebuilds its tool surface at init.

**Error handling:** Invalid manifests logged and skipped (not crash). Merge conflicts in skill_syncer detected and flagged for human resolution. Large git diffs (50+ files) summarized, not listed individually.

### 7.5 watcher.py (Entry Point)

Runs all bridge components. Called by post-commit hook + launchd cron.

---

## 8. Augments (Nervous System)

### 8.1 OpenSpace — Skill Evolution (Gate 2+)

Three evolution modes ported from HKUDS/OpenSpace as Hermes plugins.

**CAPTURED:** Distill successful patterns into SKILL.md. Detect repeating atomic tool chains (threshold: 5 occurrences, configurable in `config/openspace.yaml`) and generate collapsed pipeline drafts.

**FIXED:** Auto-repair broken skills/pipelines from error logs. Create new version, archive broken version.

**DERIVED:** Promote better variants (higher quality score, fewer tokens). Version DAG tracks lineage.

**Pruner:** Skills not invoked in N sessions -> `~/.hermes/skills/_archived/`. Recoverable but excluded from index scan.

### 8.2 Dream-Skill — Memory Consolidation (Gate 2+)

4-phase model on Qwen 3.5 9B local (zero cost). Triggered on session exit.

1. **DECIDE** — threshold check (~10ms)
2. **GATHER SIGNAL** — scan structlog traces
3. **CONSOLIDATE** — merge into MEMORY.md, resolve contradictions
4. **PRUNE & INDEX** — keep under 200 lines

### 8.3 DeerFlow — Sub-Agent Coordination (Gate 2+)

Patterns applied to Hermes's native `delegate_task` (NOT a custom runtime):

- **task_decomposer.py** — Complex task -> parallel sub-task specs with toolset assignments
- **result_synthesizer.py** — Merge sub-agent outputs into coherent deliverable
- **shared_memory.py** — Debounced async queue for cross-agent observations

---

## 9. Middleware

### 9.1 Quality Gate

6-layer QA. Wiring mechanism: pipeline scripts call `quality_gate.validate()` directly. `adapter/executor.py` calls it after atomic tool execution. Explicit function calls, not magic injection.

| Layer | Gate | What it checks |
|-------|------|---------------|
| 1. Input validation | 1 | Brief schema, required fields (pydantic) |
| 2. Output verification | 1 | Structured output matches expected schema (pydantic) |
| 3. Visual QA | 2 | Rendered images match expectations (pixelmatch, imagehash) |
| 4. Content quality | 2 | Language, tone, register (lingua-py) |
| 5. Delivery verification | 2 | Confirm delivery succeeded (httpx status) |
| 6. Feedback loop | 2 | Quality scores feed into OpenSpace (structlog) |

### 9.2 Prompt Logger

Hermes lifecycle hooks (`pre_llm_call`, `post_llm_call`). SQLite table in state.db. Cherry-picked from v6.2 §27 (30-line plugin).

---

## 10. Configuration

### 10.1 SOUL.md (Vizier Persona)

Loaded by Hermes as agent identity (`~/.hermes/SOUL.md`, symlinked from `config/SOUL.md`).

Key behavioral rules:
- Tool-layer priority: pipeline -> atomic -> improvise
- Always try `run_pipeline` first
- Never skip layers — cheaper option first
- For unattended sessions: hold delivery if quality score < 7/10

### 10.2 Model Routing

Gate 1: GPT-5.4-mini only (free 10M/day). Qwen 3.5 9B used for dream-skill memory consolidation (Gate 2+).

Two-pass routing (Gate 2+): Qwen classifies task -> determines toolset -> Hermes session starts with that toolset + GPT-5.4-mini as the reasoning model. Implementation: a pre-session Python script that calls Ollama, classifies, and passes `--toolsets vizier-{workflow}` to the Hermes CLI.

### 10.3 clients/{client_id}.yaml

```yaml
client_id: "dmb"
name: "DMB"
brand_color: "#2E75B6"
telegram_chat_id: "..."
template_preference: "modern"
```

No client names hardwired in code. New client = new YAML file.

---

## 11. Gate 1 Scope — "It Works"

**Objective:** Hermes running as Vizier, one content workflow producing billable output end-to-end, quality gate active, bridge connected.

### What gets built in Gate 1

| Component | What | Estimated effort |
|-----------|------|-----------------|
| adapter/ | Manifest loader (-> registry.register()) + executor + schemas | ~300 lines |
| tools/run_pipeline.py | Pipeline executor + list mode | ~100 lines |
| tools/query_logs.py | Inspect prompt logger traces | ~50 lines |
| plugins/prompt_logger.py | Hermes lifecycle hook (pre/post LLM call) | ~30 lines |
| manifests/content/ | httpx_fetch, jinja2_render, lightrag_search | 3 YAML files |
| manifests/document/ | typst_render | 1 YAML file |
| pipelines/content_generate.py | Brief -> RAG -> copy pipeline | ~80 lines |
| pipelines/_registry.yaml | Pipeline index | ~20 lines |
| middleware/quality_gate.py | Layers 1-2 (input + output validation) | ~100 lines |
| bridge/ | git_watcher, skill_syncer, test_parser, manifest_syncer, watcher | ~650 lines |
| config/SOUL.md | Vizier persona + tool priority rules | ~50 lines |
| config/hermes.yaml | Hermes runtime config | ~20 lines |

**Total new code:** ~1,350 lines + 4 YAML manifests.

### What gets installed in Gate 1

No additional installs beyond what Hermes v0.6.0 already provides. Pro-Max tools are Python libraries installed into the project venv.

### Pre-Gate 2 Setup (install when Gate 1 is complete)

```bash
# Qwen 3.5 9B for routing/memory
ollama pull qwen3.5:9b
# Knowledge Graph Tool (Wisdom Vault)
# Follow Jesse Vincent's install -> set KG_VAULT_PATH -> run kg-index
# DSPy for distillation pipeline (Gate 3)
pip install dspy --break-system-packages
```

### What does NOT happen in Gate 1

- No `switch_toolset` (requires Hermes patch — deferred to Gate 2)
- No `execute_code` sandbox extensions (use Hermes built-in as-is)
- No visual/audio/code/research workflows
- No OpenSpace/dream-skill/DeerFlow augments
- No scheduled/event/data triggers (human prompts only)
- No parallel or unattended sessions
- No distillation pipeline
- No dashboard customization (Mission Control fork as-is)

### Gate 1 Exit Criteria

- [ ] Hermes running as Vizier (SOUL.md loaded) on Mac Mini M4
- [ ] Manifest adapter registering tools into Hermes toolsets via `registry.register()`
- [ ] `run_pipeline` executing content_generate pipeline end-to-end
- [ ] Content workflow producing complete deliverable (brief -> RAG -> copy -> PDF -> deliver)
- [ ] Quality gate layers 1-2 active on every output
- [ ] Prompt logger lifecycle hook capturing every LLM call
- [ ] `query_logs` tool returning prompt chain data
- [ ] Bridge connected: git_watcher updating MEMORY.md, skill_syncer flowing skills
- [ ] Dashboard (Mission Control fork) running and remotely accessible

---

## 12. Gate 2-4 Overview

**Gate 2 — "Works While I Sleep" (Week 3-6):**
- `switch_toolset` meta-tool (Hermes patch: flag-based `self.tools` rebuild after each turn)
- All workflow toolsets active
- Parallel sessions via `delegate_task` + DeerFlow patterns
- Unattended sessions: scheduled cron + event-driven triggers
- OpenSpace skill evolution (MCP server mode)
- Dream-skill memory consolidation (Qwen local)
- Template cloning loop
- Quality gate layers 1-6
- Telegram/WhatsApp channels

**Gate 3 — "Builds Itself" (Week 7-12):**
- DSPy distillation pipeline (GPT-5.4-mini -> Qwen local)
- OpenSpace CAPTURED -> auto-pipeline promotion
- Code workflow active (self-building tools and pipelines)
- Data-driven + pattern-driven triggers
- `execute_code` sandbox extensions

**Gate 4 — "Improves Itself" (Week 13-24):**
- Self-distillation (autonomous migration to Qwen)
- OpenSpace embedded (local mode, no MCP server)
- Research-driven + observation-driven triggers
- Human role: auditor, not operator

---

## 13. Key Differences from v6.2 Architecture

| Aspect | v6.2 | Pro-Max |
|--------|------|---------|
| Tool registration | 47 individual wrappers | YAML manifests -> registry.register() (~70% zero code) |
| Tool loading | All tools per session | Toolset-scoped (Gate 1: session init, Gate 2: mid-session switch) |
| Token cost per turn | ~94KB (all 47 tools) | ~14-18KB (one toolset + core + pipeline summary) |
| Pipelines | execute_code manual collapse | `run_pipeline` + auto-capture via OpenSpace |
| Session types | Not specified | Interactive, parallel, unattended — each with distinct rules |
| Bridge | Not specified | git_watcher, skill_syncer, test_parser, manifest_syncer |
| Improvisation | Not specified | `execute_code` -> capture loop -> new pipeline |
| Fallback chain | Not specified | Pipeline -> atomic -> execute_code -> vizier-fallback |

---

## 14. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Wrong toolset at session start (Gate 1) | Wrong tools, must restart | Pre-session Qwen classification (Gate 2). Gate 1: user specifies workflow. |
| `switch_toolset` Hermes patch fails | No mid-session switching | Acceptable in Gate 1. Gate 2 fallback: restart session with correct toolset. |
| `run_pipeline` god-tool: model doesn't know schemas | Wasted turns | Pipeline registry summary in system prompt (~2KB) + list mode |
| `execute_code` sandbox bypass | Security breach | Extend Hermes built-in with allowlists, not replace it |
| OpenSpace generates bad pipelines | Bad output | Quality gate validates before promotion from _drafts/ |
| Capture threshold too low | Noise pipelines | Default 5 (configurable), pruner archives unused |
| Adapter is single point of failure | Tools don't load | Test suite + fallback to direct registry.register() calls |
| Unattended session produces bad output | Client receives garbage | Quality threshold hold: score < 7/10 -> held for human review |
| Pipeline registry bloats system prompt | Token creep | Summary capped at ~2KB, pruner archives unused pipelines |
| Manifest syncer fails validation | Broken tool registration | Invalid manifests logged and skipped, not crash |
