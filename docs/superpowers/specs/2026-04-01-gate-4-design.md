# Gate 4 Design — "Improves Itself"

**Date:** 2026-04-01
**Status:** Draft
**Predecessor:** Gate 3 — "Builds Itself"
**Objective:** Vizier operates autonomously — progressive distillation to Qwen, full cost visibility per deliverable, self-evolving pipelines, human role is auditor not operator.

---

## 1. Auditor Requirements

Gate 4 redefines the human role from operator to auditor. Three requirements drive the design:

1. **Confidence that it works** — system proves itself via quality gates and cost tracking, not human supervision
2. **Cost visibility per deliverable** — token counts and model costs rolled up from individual LLM calls → pipeline steps → deliverables → client
3. **Drill-down on suboptimal runs** — when something costs too much or scores too low, full trace (input/output/prompt per step) available for diagnosis

---

## 2. Architecture Overview

Three parallel tracks, sequenced by dependency:

| Track | Purpose | Gate 2/3 Dependencies |
|-------|---------|----------------------|
| **Track 1: Deliverable Ledger** | Cost tracking, anomaly detection, trace export | Minimal — can start immediately |
| **Track 2: Progressive Distillation** | Offload pipeline steps from GPT-5.4-mini to Qwen | Cost ledger data, all workflow toolsets, Qwen local |
| **Track 3: Self-Evolution** | Embedded OpenSpace, observation/research triggers | OpenSpace, Dream-skill, parallel sessions |

Track 1 feeds Track 2 (cost data drives distillation priority).
Track 1 feeds Track 3 (anomaly data drives observation triggers).
Track 2 and Track 3 coordinate via pipeline versioning.

---

## 3. Track 1: Deliverable Ledger + Trace System

### 3.1 Context Propagation — `middleware/deliverable_context.py`

Every pipeline run gets a unique `deliverable_id` + `client_id`. Two propagation modes:

- **In-process:** Python `contextvars` for tool calls and LLM calls within a single session
- **Cross-session:** `deliverable_id` passed as explicit parameter in `delegate_task` calls. Child session startup hook reads it from task parameters and injects into local contextvars

The prompt_logger and quality gate read `deliverable_id` from context — no changes to their interfaces, just an additional field they attach.

### 3.2 Deliverable Ledger — `middleware/cost_ledger.py`

Hermes lifecycle hook captures per-call data:

| Field | Source |
|-------|--------|
| `model` | LLM call metadata |
| `input_tokens`, `output_tokens` | LLM response |
| `prompt_text`, `response_text` | LLM call content |
| `latency_ms` | Timer |
| `step_name` | Pipeline step context |
| `deliverable_id` | deliverable_context |
| `pipeline_version` | Pipeline registry |

Storage: SQLite `cost_ledger` table with `deliverable_id` as foreign key (extends prompt_logger's DB).

`deliverable_summary` view joins cost data + quality gate scores into one row per deliverable:

```
deliverable_id | client_id | pipeline | pipeline_version | total_cost
total_tokens | quality_score | all_gates_passed | model_breakdown | timestamp
```

Cost baselines: rolling average per pipeline type + version. Bootstrapped from first 20 runs, recalculated every 10th run. Stored in `cost_baselines` table:

```
pipeline_name | pipeline_version | avg_cost | stddev | sample_count
```

### 3.3 Anomaly Detection + Trace Export — `middleware/trace_exporter.py`

"Not optimum" defined by two signals:

1. **Quality below threshold** — quality gate score < configured minimum (default 7.0)
2. **Cost above baseline** — cost > baseline average + 2 standard deviations

When either triggers:

- Full trace exported to `traces/{deliverable_id}.json`:
  - Input/output/prompt for every step
  - Model used per step
  - Token counts per step
  - Quality scores per gate layer
- Telegram notification: deliverable ID, client, pipeline, trigger reason, trace path
- Traces are immutable — never overwritten, retained as distillation training data

### 3.4 Query Interface — `tools/query_costs.py`

Model-callable tool for Vizier self-inspection:

- Per-deliverable cost breakdown (step-level detail)
- Per-client cost rollup (date range filter)
- Most expensive pipeline steps across runs
- Anomaly history (date range filter)
- Model distribution: percentage of work on Qwen vs GPT-5.4-mini

---

## 4. Track 2: Progressive Distillation Pipeline

### Design Principle

Qwen handles everything it can do reliably. GPT-5.4-mini stays in the loop for tasks beyond Qwen's capability. Progressive offload, not hard cutover. Each step earns its place on Qwen by proving reliability against the same quality gates used for GPT-5.4-mini.

### Qwen Deployment

Local Mac Mini M4, shared with Dream-skill (Gate 2). GPU scheduling via `config/gpu_scheduler.yaml`:

| Priority | Job Type |
|----------|----------|
| High | Runtime Qwen inference (live pipeline steps) |
| Medium | Dream-skill consolidation (scheduled) |
| Low | Distillation evaluation (batch) |

Simple queue — no concurrent GPU jobs.

### 4.1 Distillation Candidates — `distillation/candidate_selector.py`

- Queries cost ledger to rank pipeline steps by monthly cost (highest cost = highest savings if distilled)
- Filters out steps in exclusion list:
  - Vision-dependent steps
  - Steps requiring >8K context
  - Multi-turn reasoning chains
  - Steps with <20 exemplar traces (insufficient training data)
- Outputs ranked list with savings potential per step

### 4.2 Prompt Adapter — `distillation/prompt_adapter.py`

Same task may need a different prompt for Qwen vs GPT-5.4-mini. For each candidate step:

1. Collect N exemplar traces from cost ledger (input/output pairs where quality >= 7)
2. Generate prompt variations:
   - Original GPT-5.4-mini prompt (baseline)
   - Reformatted for Qwen's preferred chat template
   - Prompt with few-shot examples extracted from exemplars
3. Run each variation on Qwen, score against GPT-5.4-mini reference outputs using quality gate
4. Select best-performing prompt variant for that step

### 4.3 Distillation Runner — `distillation/runner.py`

For each candidate step with its adapted prompt:

1. Run Qwen on N test inputs using the adapted prompt
2. Score against GPT-5.4-mini reference outputs using quality gate layers
3. If Qwen scores >= threshold on M consecutive runs (configurable, default M=10), mark as "distillation-ready"
4. Pin results to specific `pipeline_version` — results only valid for the version tested against

Runs as a batch job, not during live pipeline execution.

### 4.4 Model Router — `middleware/model_router.py`

Sits between Vizier and Hermes LLM calls:

- Reads `distillation_config.yaml` for step → model + prompt mapping
- Default: GPT-5.4-mini with original prompt
- Distilled steps: Qwen with adapted prompt
- Fallback: if Qwen call fails or quality gate scores below threshold at runtime, auto-retry with GPT-5.4-mini
  - Log the fallback — feeds back into candidate_selector as reliability signal
  - Three fallbacks in 24 hours → auto-revert step to GPT-5.4-mini, flag for re-evaluation

### 4.5 Distillation Config — `config/distillation_config.yaml`

Per-step entries:

```yaml
steps:
  content_generate.copy_draft:
    model: qwen-3.5-9b
    prompt_template: prompts/qwen/copy_draft.txt
    quality_threshold: 7.0
    promoted_at: 2026-05-15T10:00:00Z
    pipeline_version: "1.2.0"
    consecutive_passes: 10
```

Global settings:

```yaml
global:
  min_consecutive_passes: 10
  fallback_retry_limit: 3
  auto_revert_threshold: 3  # fallbacks in 24h
  exclusions:
    - "visual.*"
    - "*.reasoning_chain"
```

Changes require human approval before activation — Telegram notification with diff.

---

## 5. Track 3: Self-Evolution

### 5.1 Embedded OpenSpace — `plugins/openspace.py`

Gate 2 runs OpenSpace as an MCP server with 4 FastMCP tools. Gate 4 embeds it as a Hermes plugin:

- CAPTURED, FIXED, DERIVED logic moves into lifecycle hooks firing after every pipeline run
- No network hop, no MCP protocol overhead
- All skill/pipeline modifications create a **new version**, never mutate existing
- Version DAG tracks lineage (carried from Gate 2)
- **Pipeline versioning with advisory locks:** if distillation runner is evaluating version N, OpenSpace creates version N+1 but doesn't promote it until distillation completes or releases its pin
- MCP server remains as optional read-only debug interface (search_skills, get_lineage only — no mutation from outside)

### 5.2 Observation-Driven Triggers — `plugins/observer.py`

For parallel sessions. Vizier watches its own execution patterns and spawns work:

| Pattern | Action |
|---------|--------|
| Quality trending down over last 10 runs on a step | Spawn OpenSpace FIXED attempt |
| 3+ Qwen fallbacks on a distilled step | Spawn distillation re-evaluation |
| 3+ cost anomalies on same pipeline in a week | Spawn investigation parallel session |

Safety bounds per observation type:

- **Cooldown period:** configurable, default 24h — prevents runaway spawning
- **Token budget cap:** per spawned session
- **Context propagation:** all spawned work inherits `deliverable_id` for cost tracking

Observer runs as a lightweight periodic check (every 30 minutes), not a continuous stream.

### 5.3 Research-Driven Triggers — `plugins/researcher.py`

For unattended sessions. Vizier initiates work based on accumulated knowledge:

- Queries Dream-skill consolidated memory + cost ledger for actionable patterns:
  - **Client pattern detection:** "Client X's last 5 briefs share trait Y" → proactively prepare template
  - **Pipeline optimization:** "Steps A→B always run together" → propose collapsed pipeline
  - **Knowledge gaps:** "RAG retrieval returns low-relevance results for topic Z" → trigger knowledge ingestion

Bounds:

- Daily research quota: max N research sessions per day (configurable, default 3)
- Token budget per session
- All research-initiated deliverables go through full quality gate before any client delivery
- Research outputs that create new pipelines or skills go through evolution_guard (5.4)

### 5.4 Self-Evolution Safety — `middleware/evolution_guard.py`

All self-modifications (new pipelines, skill fixes, distillation promotions) pass through:

1. **Sandbox execution:** New/modified pipeline runs against test fixtures before promotion. Must pass quality gate with score >= threshold
2. **Version control:** Every change creates a new version. Rollback = revert to previous version
3. **Auto-revert:** If quality drops in next 5 production runs after promotion, auto-revert and flag
4. **Rate limit:** Max N self-modifications per day (configurable, default 5)
5. **Conflict detection:** Check if distillation runner has a pin on the pipeline being modified. If so, queue the modification
6. **Audit log:** Every self-modification recorded — rationale, before/after metrics, trigger source (observation/research/manual)

Daily Telegram digest: summary of all self-modifications, auto-reverts, and anomalies with links to audit log entries and trace files.

---

## 6. Dependency Matrix

| Gate 4 Component | Gate 1 Deps | Gate 2 Deps | Gate 3 Deps |
|---|---|---|---|
| `deliverable_context` | prompt_logger | `delegate_task` (cross-session) | — |
| `cost_ledger` | prompt_logger DB | quality gate L3-6 | — |
| `trace_exporter` | — | quality gate L3-6, `send_telegram` | — |
| `query_costs` | — | — | — |
| `candidate_selector` | cost_ledger | all workflow toolsets | — |
| `prompt_adapter` | cost_ledger | Qwen 3.5 9B local | — |
| `distillation_runner` | cost_ledger | quality gate L3-6, Qwen local | — |
| `model_router` | — | — | — |
| `embedded_openspace` | — | OpenSpace MCP server | — |
| `observer` | cost_ledger | parallel sessions | pattern-driven triggers |
| `researcher` | — | Dream-skill memory | data-driven triggers |
| `evolution_guard` | — | — | code workflow |

---

## 7. Gate 4 Exit Criteria

1. **Cost ledger active** — every LLM call and tool execution tracked with `deliverable_id`, cost rolled up per deliverable and per client
2. **Anomaly detection firing** — suboptimal runs (quality or cost) auto-export full traces and notify via Telegram
3. **At least 3 pipeline steps distilled to Qwen** — running in production with quality >= threshold, fallback to GPT-5.4-mini working
4. **Model router live** — step-level routing between GPT-5.4-mini and Qwen based on distillation config
5. **Prompt adaptation validated** — Qwen-specific prompts producing equivalent quality to GPT-5.4-mini prompts
6. **OpenSpace embedded** — running as Hermes plugin, not MCP server. Version DAG active, advisory locks coordinating with distillation
7. **Observation triggers active** — at least one observation type (quality degradation, fallback detection, or cost anomaly clustering) spawning corrective work
8. **Research triggers active** — at least one research-initiated action (template preparation, pipeline optimization, or knowledge ingestion) executed through quality gate
9. **Evolution guard enforcing** — sandbox execution, auto-revert, rate limiting, conflict detection all active
10. **Daily audit digest** — Telegram summary of self-modifications, anomalies, cost breakdown, model distribution
11. **Human role = auditor** — no manual pipeline management required, all operational decisions made by Vizier with human reviewing outcomes

---

## 8. Estimated Scope

| Track | New Files | New Lines (est.) | Tests (est.) |
|-------|-----------|------------------|--------------|
| Track 1: Deliverable Ledger | ~8 | ~600 | ~40 |
| Track 2: Progressive Distillation | ~10 | ~900 | ~50 |
| Track 3: Self-Evolution | ~10 | ~800 | ~45 |
| **Total** | **~28** | **~2,300** | **~135** |

---

## 9. Key Design Decisions

1. **No DSPy** — distillation uses direct quality gate evaluation against exemplar traces. Simpler, reuses existing infrastructure.
2. **Prompt adaptation over blind substitution** — same task may need different prompts for different models. The prompt adapter phase is critical for distillation success.
3. **Pipeline versioning with advisory locks** — prevents distillation/evolution conflicts without heavy locking infrastructure.
4. **Progressive offload, not cutover** — Qwen earns each step. Three fallbacks in 24h triggers auto-revert. No risk of quality degradation at scale.
5. **Embedded OpenSpace, MCP server optional** — by Gate 4, Hermes is the operator. Network hop overhead unjustified for the primary path.
6. **Cross-session context via explicit parameters** — contextvars don't cross process boundaries. `delegate_task` carries `deliverable_id` explicitly.
