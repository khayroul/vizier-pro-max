# Vizier Pro-Max — Architecture Design Spec

**Date:** 2026-04-01
**Author:** Khairul / Premier Marketing
**Status:** Draft — pending review
**Repo:** ~/vizier-pro-max/ (clean slate)
**Fallback:** ~/vizier-ultimate/ (Gate 2, Hermes v0.6.0)

---

## 1. Identity & Philosophy

**Vizier** is the brain — the persona, the decision-maker, the identity.
**Hermes** is the engine — the sole runtime that executes Vizier's decisions.
**Stable Python scripts** are the hands — proven libraries and CLIs wired as tools.
**Absorbed agentic components** are the nervous system — OpenSpace, dream-skill, DeerFlow ported as Hermes plugins.

### Core Principles

1. **Hermes is the sole runtime.** No competing runtimes. No LangGraph, no CrewAI, no OpenAI Agents SDK as runtime. Patterns extracted, runtimes rejected.
2. **Superagent model.** ONE Hermes agent with workflow-scoped toolset loading. No named agent roles.
3. **Scripts as hands.** Stable Python libraries/CLIs are the tool layer. The model never touches raw APIs — scripts encapsulate all execution.
4. **Collapse what repeats.** Deterministic sequences become collapsed pipelines behind `run_pipeline`. Atomic tools exist as fallback. `execute_code` for improvisation. OpenSpace captures new patterns automatically.
5. **Toolsets control token cost.** Tools are grouped into named toolsets. Only the relevant toolset loads per task. `switch_toolset` enables mid-session changes.
6. **Bridge connects inside and outside.** Claude Code builds on the outside, the bridge informs Vizier on the inside. Bidirectional awareness.
7. **Gate-by-gate revenue rule.** Each gate must produce billable output before the next unlocks.

---

## 2. Repository Structure

```
~/vizier-pro-max/
├── bridge/                   # Bidirectional Claude Code <-> Vizier awareness
│   ├── watcher.py            # Entry point (git hook + cron trigger)
│   ├── git_watcher.py        # Commits -> Hermes MEMORY.md
│   ├── skill_syncer.py       # Bi-directional skill flow (repo <-> ~/.hermes/skills/)
│   ├── test_parser.py        # Module confidence registry
│   └── manifest_syncer.py    # New manifests -> auto-register in Hermes
│
├── adapter/                  # Universal manifest -> Hermes tool engine
│   ├── loader.py             # Reads manifests -> registers Hermes tools into toolsets
│   ├── executor.py           # Runs scripts with validation + error handling
│   └── schemas.py            # Manifest schema, base types
│
├── manifests/                # YAML tool definitions (atomic tools, ~70% of tools)
│   ├── content/
│   ├── document/
│   ├── visual/
│   ├── research/
│   ├── audio/
│   └── code/
│
├── tools/                    # Custom PydanticAI wrappers (complex tools only)
│   ├── switch_toolset.py     # Meta: change active toolset mid-session
│   ├── run_pipeline.py       # Meta: execute collapsed pipelines by name
│   ├── execute_code.py       # Meta: sandboxed Python execution (improvisation)
│   └── prompt_logger.py      # Meta: full chain visibility
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
│   │   ├── capturer.py       # Successful patterns -> SKILL.md
│   │   ├── fixer.py          # Auto-repair broken skills from error logs
│   │   ├── deriver.py        # Promote better variants
│   │   ├── version_dag.py    # Skill lineage tracking
│   │   ├── safety.py         # check_skill_safety before load
│   │   └── pruner.py         # Archive stale skills to reduce index
│   ├── dreamskill/           # Memory consolidation (4-phase on Qwen local)
│   │   ├── consolidator.py   # DECIDE -> GATHER -> CONSOLIDATE -> PRUNE
│   │   ├── signals.py        # Signal extraction from structlog traces
│   │   └── pruner.py         # MEMORY.md size management
│   └── deerflow/             # Sub-agent spawning patterns
│       ├── spawner.py        # Scoped sub-agent creation
│       ├── parallel.py       # Concurrent execution + result synthesis
│       └── shared_memory.py  # Debounced async queue
│
├── workflows/                # TOML workflow definitions
│   ├── content.toml
│   ├── document.toml
│   ├── visual.toml
│   ├── research.toml
│   ├── code.toml
│   ├── knowledge.toml
│   └── audio.toml
│
├── middleware/                # Cross-cutting concerns (not model-callable tools)
│   └── quality_gate.py       # 6-layer QA on every workflow output
│
├── scripts/                  # The actual hands (stable executables)
│   ├── content/              # Cherry-picked + new scripts
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
│   └── SOUL.md               # Vizier persona, voice, tool-layer priority rules
│
├── tests/
├── docs/
├── pyproject.toml
└── CLAUDE.md
```

---

## 3. Tool Architecture: Three Layers

### 3.1 Layer 1 — Collapsed Pipelines (Cheapest)

Deterministic sequences wrapped as single scripts. Registered in `pipelines/_registry.yaml`, executed via `run_pipeline` tool.

**Token cost:** 1 LLM turn per pipeline execution. The `run_pipeline` tool schema is ~1.5KB regardless of how many pipelines exist.

**Pipeline registry injected into system prompt** as a summary (~500 tokens for 20 pipelines):
```
Available pipelines: invoice (brief->PDF->deliver), report (data->typst->PDF),
content_generate (brief->RAG->copy), poster_batch (template+CSV->images), ...
```

**`run_pipeline` has a `list` mode:** When model is uncertain, it calls `run_pipeline(action="list")` to get full pipeline schemas. Costs one turn but only when needed.

### 3.2 Layer 2 — Atomic Tools (Moderate)

Individual library/CLI wrappers registered via YAML manifests. Loaded per toolset. Used when:
- No pipeline covers the task
- Pipeline failed and model needs manual control
- Steps require model reasoning between them (e.g., RAG retrieval -> decide what to generate)

### 3.3 Layer 3 — Improvisation (Expensive, Creative)

`execute_code` tool runs arbitrary Python in a sandboxed subprocess. Used when:
- No pipeline or atomic tool combination fits
- Novel task requiring new composition
- One-off operations

**Sandbox constraints:**
- Allowlisted imports only (libraries in the tool stack)
- Write access restricted to `output/` and `tmp/`
- Network access only to configured endpoints
- Timeout: 30s default (configurable)

### 3.4 Priority Rule (in SOUL.md)

```
When executing a task:
1. FIRST: Try run_pipeline. If a pipeline exists for this task, use it.
2. IF NO PIPELINE: Use atomic tools from your active toolset.
3. IF TOOLSET INSUFFICIENT: Call switch_toolset to load the right one.
4. IF ATOMIC TOOLS INSUFFICIENT: Use execute_code to compose a solution.
5. NEVER skip layers. Always try the cheaper option first.
```

### 3.5 The Capture Loop (OpenSpace Integration)

```
Novel task -> no pipeline exists
  -> Model uses atomic tools (4-5 calls)
  -> Prompt logger records full chain
  -> Same pattern repeats 5+ times (configurable threshold)
  -> OpenSpace CAPTURED generates pipeline script -> pipelines/_drafts/
  -> Quality gate validates draft pipeline
  -> Bridge: manifest_syncer promotes to pipelines/ + updates _registry.yaml
  -> Next occurrence: 1 call instead of 4-5

Pipeline breaks -> run_pipeline returns error
  -> Model falls back to atomic tools (graceful degradation)
  -> OpenSpace FIXED detects failure -> patches pipeline script
  -> Next occurrence: patched pipeline works

Pipeline doesn't quite fit -> model mixes pipeline + atomic tools
  -> Variant repeats -> OpenSpace captures as new pipeline variant
```

---

## 4. Toolset Map

### 4.1 vizier-core (always loaded, 4 tools)

| Tool | Type | Purpose |
|------|------|---------|
| `switch_toolset` | custom wrapper | Change active toolset mid-session |
| `run_pipeline` | custom wrapper | Execute collapsed pipelines by name or list them |
| `execute_code` | custom wrapper | Sandboxed Python execution (improvisation) |
| `prompt_logger` | custom wrapper | Full chain visibility, query execution logs |

### 4.2 Workflow Toolsets (loaded per task)

**vizier-content (3 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `httpx_fetch` | httpx | Fetch URLs, APIs |
| `jinja2_render` | jinja2 | Template rendering |
| `lightrag_search` | lightrag | RAG retrieval |

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

**vizier-research (3 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `httpx_fetch` | httpx | Web fetching (shared with content) |
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

**vizier-knowledge (3 atomic tools):**
| Tool | Library | Purpose |
|------|---------|---------|
| `lightrag_search` | lightrag | RAG retrieval (shared with content) |
| `sqlite_query` | sqlite3 | Direct DB queries |
| `kg_search` | kg-tools | Knowledge graph queries |

**Collapsed pipelines:** `knowledge_query`, `wisdom_vault_search`

**vizier-fallback (all atomic tools combined):**

Loaded ONLY when a pipeline fails and atomic tools in the current toolset are insufficient. Contains all atomic tools from all workflows. ~22 tools, ~44KB — expensive but recoverable.

### 4.3 Token Cost Summary

| Scenario | Tools in context | Approx schema cost |
|----------|-----------------|-------------------|
| Single workflow | core (4) + workflow (2-3) | 6-7 tools, ~12-14KB |
| Complex task (2 workflows) | core (4) + 2 workflows (4-6) | 8-10 tools, ~16-20KB |
| Pipeline failure + fallback | core (4) + fallback (22) | 26 tools, ~52KB |

Compare: v6.2 architecture = 47 tools all loaded = ~94KB per turn.

---

## 5. Manifest Format

A YAML file that turns any script/CLI into a Hermes tool with zero wrapper code.

```yaml
# manifests/document/typst_render.yaml
name: typst_render
description: "Compile Typst markup into PDF"
version: "1.0"
workflow: document                    # -> registers into vizier-document toolset

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

**Execution types:**
- `cli` — subprocess call, args interpolated from input
- `python_script` — imports and calls `entrypoint` function from `path`
- `python_function` — direct function call (for tools already importable)

**The adapter** (`adapter/loader.py`) reads all manifests on startup, generates Pydantic models for each input/output schema, and registers them as Hermes tools in the appropriate toolset.

---

## 6. Bridge (Claude Code <-> Vizier Awareness)

### 6.1 git_watcher.py

Detects commits by Claude Code (or human), extracts file/function/class changes from git diff, writes structured entries to Hermes MEMORY.md. Skips commits by "aider" and "hermes" authors.

**Trigger:** Post-commit git hook + launchd cron (5-min fallback).

Cherry-picked from vizier-ultimate (`vizier/adapter/git_watcher.py`, 373 lines, proven).

### 6.2 skill_syncer.py

Bi-directional sync between repo skills and `~/.hermes/skills/vizier/`.
- Repo -> Hermes: newer mtime wins (Claude Code writes skill, Hermes picks it up)
- Hermes -> Repo: only new skills (Hermes auto-creates skill, it appears in git)

Cherry-picked from vizier-ultimate (`vizier/adapter/skill_syncer.py`, 94 lines, proven).

### 6.3 test_parser.py

Maps source modules to test files. Classifies confidence: high/medium/low/none. Modules with "none" excluded from autonomous overnight runs.

Cherry-picked from vizier-ultimate (`vizier/adapter/test_parser.py`, 119 lines, proven).

### 6.4 manifest_syncer.py (NEW)

Watches `manifests/` and `pipelines/` directories. When a new YAML or pipeline script appears:
1. Validates against manifest schema
2. Triggers `adapter/loader.py` to hot-register the new tool
3. Updates `pipelines/_registry.yaml` if it's a new pipeline
4. Logs the addition to Hermes MEMORY.md

**Effect:** Claude Code creates a manifest file, Vizier gains a new tool immediately.

### 6.5 watcher.py (Entry Point)

Single entry point that runs all bridge components. Called by:
- Post-commit git hook (immediate)
- Launchd plist (5-min cron fallback)

```python
def run():
    git_watcher.run(repo_path)
    skill_syncer.sync_both(repo_skills, hermes_skills)
    test_parser.update_confidence(repo_path)
    manifest_syncer.check_and_register(manifests_dir, pipelines_dir)
```

---

## 7. Augments (Nervous System)

### 7.1 OpenSpace — Skill Evolution

Ported from HKUDS/OpenSpace. Three evolution modes as Hermes plugins.

**CAPTURED:** After workflow succeeds, distill execution pattern into SKILL.md. Also detects repeating atomic tool chains (5+ occurrences, configurable) and generates collapsed pipeline drafts in `pipelines/_drafts/`.

**FIXED:** When a skill or pipeline breaks, auto-analyze error log, generate repair patch, verify fix, create new version. No human intervention.

**DERIVED:** When a better pattern detected (higher quality score, fewer tokens), promote as new version. Old version archived, not deleted.

**Pruner:** Periodically reviews skill usage frequency. Skills not invoked in N sessions moved to `~/.hermes/skills/_archived/` — excluded from index scan but recoverable.

**Gate mapping:**
- Gate 2: OpenSpace as MCP server alongside Hermes
- Gate 4: Embedded directly into Hermes plugins

### 7.2 Dream-Skill — Memory Consolidation

Ported from grandamenium/dream-skill. 4-phase model on Qwen 3.5 9B local (zero cost).

1. **DECIDE** — threshold check on session exit (~10ms). Skip if below threshold.
2. **GATHER SIGNAL** — scan structlog traces for corrections, preferences, decisions, patterns.
3. **CONSOLIDATE** — merge into Hermes MEMORY.md. Resolve contradictions. Absolute dates. No duplicates.
4. **PRUNE & INDEX** — keep MEMORY.md under 200 lines. Demote verbose entries to topic files.

Consolidates both Vizier's own learnings AND Claude Code commits (via bridge/git_watcher). Single unified memory.

### 7.3 DeerFlow — Sub-Agent Spawning

Ported from ByteDance/deer-flow (patterns only, not LangGraph runtime).

**Scoped spawning:** Lead agent spawns sub-agent with scoped context, scoped toolset, and termination conditions (timeout, quality threshold, max iterations).

**Parallel execution:** 2-3 sub-agents run concurrently. Each gets its own toolset via `switch_toolset`. Parent synthesizes results.

**Shared memory:** Debounced async queue prevents memory fragmentation from concurrent sub-agent writes.

**When used:** Complex tasks only — "produce a campaign with research + copy + poster + PDF." Simple tasks (single workflow) handled by superagent directly.

---

## 8. Middleware

### 8.1 Quality Gate

6-layer QA that runs after every workflow output. NOT a model-callable tool — it's a pipeline step wired into every workflow.

| Layer | What it checks | Tools used |
|-------|---------------|-----------|
| 1. Input validation | Brief schema, required fields | pydantic |
| 2. Output verification | Structured output matches expected schema | pydantic |
| 3. Visual QA | Rendered images match expectations | pixelmatch, imagehash |
| 4. Content quality | Language, tone, register checks | lingua-py |
| 5. Delivery verification | Confirm delivery succeeded | httpx status checks |
| 6. Feedback loop | Quality scores feed into OpenSpace | structlog |

Gate 1: Layers 1-2 only.
Gate 2: Layers 1-6.

### 8.2 Prompt Logger

Captures full prompt chain for every LLM call. SQLite table in Hermes state.db. Enables:
- Click any task in dashboard -> see every step with full prompt + tools + tokens
- Compare high-scoring vs low-scoring output chains
- Feed chains into OpenSpace for pattern detection
- Track token usage per step to find expensive workflow steps

Cherry-picked from v6.2 architecture Section 27 (30-line plugin, proven design).

---

## 9. Configuration

### 9.1 SOUL.md (Vizier Persona)

Defines Vizier's identity, voice, and behavioral rules. Loaded by Hermes as agent identity.

Key behavioral rules:
- Tool-layer priority: pipeline -> atomic -> improvise
- Always try `run_pipeline` first
- Use `switch_toolset` when current toolset is insufficient
- Never skip layers — cheaper option first

### 9.2 hermes.yaml

```yaml
model:
  provider: "custom"
  default: "gpt-5.4-mini"
  base_url: "https://api.openai.com/v1"

agent:
  max_turns: 90

memory:
  memory_enabled: true

compression:
  enabled: true
  threshold: 0.50
```

### 9.3 models.yaml

```yaml
routing:
  pass_1: "qwen-3.5-9b"    # Local, free — task classification + tool selection
  pass_2: "gpt-5.4-mini"   # Cloud, free 10M/day — reasoning + generation

distillation:
  target: "qwen-3.5-9b"
  threshold: 0.5            # Delta below this -> ship on Qwen
```

### 9.4 clients/{client_id}.yaml

```yaml
client_id: "dmb"
name: "DMB"
brand_color: "#2E75B6"
telegram_chat_id: "..."
template_preference: "modern"
```

No client names hardwired in code. New client = new YAML file.

---

## 10. Gate 1 Scope — "It Works"

**Objective:** Hermes running as Vizier, one content workflow producing billable output end-to-end, quality gate active, dashboard visible, bridge connected.

### What gets built in Gate 1

| Component | What | Estimated effort |
|-----------|------|-----------------|
| adapter/ | Manifest loader + executor + schemas | ~300 lines |
| tools/switch_toolset.py | Toolset switching meta-tool | ~50 lines |
| tools/run_pipeline.py | Pipeline executor + list mode | ~100 lines |
| tools/execute_code.py | Sandboxed code execution | ~80 lines |
| tools/prompt_logger.py | Chain logging plugin | ~30 lines (from v6.2 §27) |
| manifests/content/ | httpx_fetch, jinja2_render, lightrag_search | 3 YAML files |
| manifests/document/ | typst_render | 1 YAML file |
| pipelines/content_generate.py | Brief -> RAG -> copy pipeline | ~80 lines |
| middleware/quality_gate.py | Layers 1-2 (input + output validation) | ~100 lines |
| bridge/ | git_watcher, skill_syncer, test_parser, watcher | ~600 lines (cherry-picked) |
| config/SOUL.md | Vizier persona + tool priority rules | ~50 lines |
| workflows/content.toml | Content workflow definition | ~20 lines |

### What gets installed in Gate 1

```bash
# Hermes Agent (already installed at ~/.hermes/)
# PydanticAI
pip install pydantic-ai --break-system-packages
# DSPy
pip install dspy --break-system-packages
# Promptfoo
npm install -g promptfoo
# Knowledge Graph Tool (Wisdom Vault)
# Qwen 3.5 9B via Ollama
ollama pull qwen3.5:9b
```

### What does NOT happen in Gate 1

- No visual/audio/code workflows
- No OpenSpace/dream-skill/DeerFlow augments (Gate 2)
- No dashboard customization (use Mission Control fork as-is)
- No scheduled/event triggers (human prompts only)
- No distillation pipeline
- No template cloning loop

### Gate 1 Exit Criteria

- [ ] Hermes running as Vizier (SOUL.md loaded) on Mac Mini M4
- [ ] Manifest adapter registering tools into toolsets
- [ ] `switch_toolset` working mid-session
- [ ] `run_pipeline` executing content_generate pipeline
- [ ] Content workflow producing billable output end-to-end
- [ ] Quality gate layers 1-2 active
- [ ] Prompt logger capturing every LLM call
- [ ] Bridge: git_watcher + skill_syncer connected
- [ ] Dashboard (Mission Control) accessible remotely
- [ ] DSPy + Promptfoo installed with baseline delta measured
- [ ] Knowledge Graph indexing Wisdom Vault
- [ ] First revenue from Vizier Pro-Max output

---

## 11. Gate 2-4 Overview (Not Detailed Here)

**Gate 2 — "Works While I Sleep" (Week 3-6):**
- All workflow toolsets active (visual, research, audio, document-full)
- OpenSpace skill evolution
- Dream-skill memory consolidation
- Scheduled + event-driven triggers
- Template cloning loop
- DeerFlow sub-agent patterns
- Quality gate layers 1-6
- Telegram/WhatsApp channels

**Gate 3 — "Builds Itself" (Week 7-12):**
- DSPy distillation pipeline (GPT-5.4-mini -> Qwen local)
- Pipeline collapser auto-generating from atomic chains
- OpenSpace CAPTURED -> pipeline promotion
- Code workflow active (self-building)
- Data-driven + pattern-driven triggers

**Gate 4 — "Improves Itself" (Week 13-24):**
- Self-distillation (autonomous migration to Qwen)
- OpenSpace embedded (local mode)
- Research-driven + observation-driven triggers
- Vizier-fallback toolset rarely needed (most tasks have pipelines)
- Human role: auditor, not operator

---

## 12. Key Differences from v6.2 Architecture

| Aspect | v6.2 | Pro-Max |
|--------|------|---------|
| Tool registration | 47 individual PydanticAI wrappers | YAML manifests + adapter (zero code for ~70%) |
| Tool loading | All tools per session | Toolset-scoped, `switch_toolset` mid-session |
| Token cost per turn | ~94KB (all 47 tools) | ~12-20KB (one toolset + core) |
| Pipeline handling | execute_code collapses manually | `run_pipeline` + auto-capture via OpenSpace |
| Bridge | Not specified | First-class: git_watcher, skill_syncer, test_parser, manifest_syncer |
| Improvisation | Not specified | `execute_code` sandbox + capture loop |
| Fallback on failure | Not specified | Pipeline -> atomic -> execute_code -> vizier-fallback toolset |

---

## 13. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Qwen local misroutes task to wrong toolset | Stuck with wrong tools for session | `switch_toolset` meta-tool enables mid-session correction |
| `run_pipeline` is a god-tool, model doesn't know pipeline schemas | Wastes turns discovering pipelines | Pipeline registry summary in system prompt (~500 tokens) + list mode |
| `execute_code` sandbox bypass | Security breach | Allowlisted imports, restricted filesystem, configured network endpoints, timeout |
| OpenSpace CAPTURED generates bad pipelines | Bad output shipped | Quality gate validates draft pipelines before promotion from _drafts/ |
| Capture threshold too low (false patterns) | Noise pipelines bloat registry | Default threshold 5 (configurable), prune stale pipelines |
| Manifest adapter is single point of failure | All tools break | Comprehensive test suite for adapter, fallback to direct tool registration |
| Too many pipelines bloat system prompt | Token cost creeps up | Pipeline registry summary capped at 500 tokens, pruner archives unused |
| vizier-ultimate fallback needed | Wasted Pro-Max effort | Pro-Max is additive — worst case, proven tools cherry-picked back |
