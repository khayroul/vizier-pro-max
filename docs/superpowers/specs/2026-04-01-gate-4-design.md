# Gate 4 Design — "Improves Itself"

**Date:** 2026-04-01
**Status:** Draft
**Predecessor:** Gate 3 — "Builds Itself"
**Objective:** Vizier operates autonomously — progressive distillation to Qwen, full cost visibility per deliverable, self-evolving pipelines, human role is auditor not operator.

**Note on Gate 3:** Gate 3 does not yet have a design spec. Section 10 defines the exact interfaces Gate 4 requires from Gate 3. Gate 3 spec must be written and reviewed before Gate 4 implementation begins for Track 3 components.

**Note on DSPy:** The main design spec (Section 12) references DSPy for Gate 3 distillation. This Gate 4 spec supersedes that approach — distillation uses direct quality gate evaluation against exemplar traces instead. The main spec should be updated to remove DSPy references when Gate 3 is specced.

---

## 1. Auditor Requirements

Gate 4 redefines the human role from operator to auditor. Three requirements drive the design:

1. **Confidence that it works** — system proves itself via quality gates and cost tracking, not human supervision
2. **Cost visibility per deliverable** — token counts and model costs rolled up from individual LLM calls → pipeline steps → deliverables → client
3. **Drill-down on suboptimal runs** — when something costs too much or scores too low, full trace (input/output/prompt per step) available for diagnosis

---

## 2. Architecture Overview

Three parallel tracks, sequenced by dependency:

| Track | Purpose | Key Dependencies |
|-------|---------|-----------------|
| **Track 1: Deliverable Ledger** | Cost tracking, anomaly detection, trace export | prompt_logger (Gate 1). `deliverable_summary` view degrades gracefully with L1-2 quality scores until Gate 2 L3-6 arrive |
| **Track 2: Progressive Distillation** | Offload pipeline steps from GPT-5.4-mini to Qwen | Cost ledger (Track 1), all workflow toolsets (Gate 2), Qwen local (Gate 2) |
| **Track 3: Self-Evolution** | Embedded OpenSpace, observation/research triggers | OpenSpace (Gate 2), Dream-skill (Gate 2), parallel sessions (Gate 2), pattern-driven triggers (Gate 3) |

Track 1 feeds Track 2 (cost data drives distillation priority).
Track 1 feeds Track 3 (anomaly data drives observation triggers).
Track 2 and Track 3 coordinate via pipeline versioning.

---

## 3. Track 1: Deliverable Ledger + Trace System

### 3.1 Context Propagation — `middleware/deliverable_context.py`

Every pipeline run gets a unique `deliverable_id` (UUID4) + `client_id`. Two propagation modes:

- **In-process:** Python `contextvars` for tool calls and LLM calls within a single session
- **Cross-session:** `deliverable_id` injected into the `context` field of `delegate_task` batch entries (Gate 2 format: `[{goal, context, toolsets}]`). A sub-component `plugins/context_injector.py` reads `deliverable_id` from task `context` on child session startup and sets it in local contextvars (covered by `deliverable_context` row in the dependency matrix)

The prompt_logger and quality gate read `deliverable_id` from context — no changes to their interfaces, just an additional field they attach. Existing prompt_logger records without `deliverable_id` remain valid (field is nullable).

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

Storage: SQLite `cost_ledger` table in prompt_logger's DB. Schema migration via `migrations/001_cost_ledger.sql` — adds new tables, views, and a nullable `deliverable_id` column to the existing `prompt_log` table (backward compatible — existing records have NULL).

`deliverable_summary` view joins cost data + quality gate scores into one row per deliverable:

```
deliverable_id | client_id | pipeline | pipeline_version | total_cost
total_tokens | quality_score | all_gates_passed | model_breakdown | timestamp
```

The `quality_score` and `all_gates_passed` columns are nullable — the view works with Gate 1 quality gate (L1-2) and gains richer scores when Gate 2 quality gate (L3-6) is available. The cost_ledger table itself has no Gate 2 dependency.

Cost baselines: rolling average per pipeline type + version. Bootstrapped from first 20 runs, recalculated every 10th run (both configurable in `config/cost_config.yaml`). Stored in `cost_baselines` table:

```
pipeline_name | pipeline_version | avg_cost | stddev | sample_count
```

### 3.3 Anomaly Detection + Trace Export — `middleware/trace_exporter.py`

Depends on: cost_ledger (Gate 4 Track 1), prompt_logger (Gate 1), quality gate (Gate 1 L1-2, enhanced with Gate 2 L3-6), send_telegram (Gate 2).

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
- **Retention policy:** traces older than 90 days archived to `traces/archive/` (compressed). Configurable in `config/cost_config.yaml`

### 3.4 Query Interface — `tools/query_costs.py`

Depends on: cost_ledger (Gate 4 Track 1).

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

Local Mac Mini M4, shared with Dream-skill (Gate 2). Model identifier: `qwen3.5:9b` (Ollama format, consistent with Gate 2 spec).

GPU scheduling via `middleware/gpu_scheduler.py` — a process-level file lock (`/tmp/vizier_gpu.lock`) ensuring no concurrent GPU jobs. Config in `config/gpu_scheduler.yaml`:

| Priority | Job Type | Behavior |
|----------|----------|----------|
| High | Runtime Qwen inference (live pipeline steps) | Preempts low-priority batch jobs |
| Medium | Dream-skill consolidation (scheduled) | Waits for high-priority to complete |
| Low | Distillation evaluation (batch) | Runs only when GPU idle |

The model_router, distillation_runner, and Dream-skill consolidator all acquire the GPU lock before Qwen calls. High-priority jobs can interrupt low-priority jobs between inference calls (not mid-call).

### 4.1 Distillation Candidates — `distillation/candidate_selector.py`

- Queries cost ledger to rank pipeline steps by monthly cost (highest cost = highest savings if distilled)
- Filters out steps in exclusion list (configurable in `distillation_config.yaml`):
  - Vision-dependent steps
  - Steps exceeding `max_context_tokens` threshold (configurable, default 8K — conservative bound for reliable Qwen 3.5 9B output quality despite 128K window capacity; tunable based on empirical results)
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

Depends on: distillation_config.yaml (Gate 4 Track 2), gpu_scheduler (Gate 4 Track 2), Qwen local (Gate 2).

Sits between Vizier and Hermes LLM calls:

- Reads `distillation_config.yaml` for step → model + prompt mapping
- Default: GPT-5.4-mini with original prompt
- Distilled steps: Qwen with adapted prompt (acquires GPU lock via gpu_scheduler)
- Fallback: if Qwen call fails or quality gate scores below threshold at runtime, auto-retry with GPT-5.4-mini
  - Log the fallback — feeds back into candidate_selector as reliability signal
  - Three fallbacks in 24 hours → auto-revert step to GPT-5.4-mini, flag for re-evaluation
- **Revert mechanism:** creates a new version of `distillation_config.yaml` with the step reverted (immutable config history). Previous configs retained in `config/distillation_history/`

### 4.5 Distillation Config — `config/distillation_config.yaml`

Per-step entries:

```yaml
steps:
  content_generate.copy_draft:
    model: "qwen3.5:9b"
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
  max_context_tokens: 8192  # conservative Qwen quality bound, tunable
  exclusions:
    - "visual.*"
    - "*.reasoning_chain"
```

Changes require human approval before activation — Telegram notification with diff.

---

## 5. Track 3: Self-Evolution

### 5.1 Embedded OpenSpace — `plugins/openspace/`

Gate 2 runs OpenSpace as an MCP server with 7 modules under `augments/openspace/`. Gate 4 re-hosts the same modules as a Hermes plugin package under `plugins/openspace/`:

```
plugins/openspace/
├── __init__.py        # Hermes plugin registration + lifecycle hooks
├── capturer.py        # From augments/openspace/capturer.py
├── fixer.py           # From augments/openspace/fixer.py
├── deriver.py         # From augments/openspace/deriver.py
├── version_dag.py     # From augments/openspace/version_dag.py
├── safety.py          # From augments/openspace/safety.py
└── pruner.py          # From augments/openspace/pruner.py
```

Key changes from Gate 2:

- `__init__.py` registers CAPTURED/FIXED/DERIVED as Hermes lifecycle hooks (post-pipeline-run)
- No network hop, no MCP protocol overhead
- `augments/openspace/server.py` remains as optional read-only MCP debug interface (search_skills, get_lineage only — no mutation from outside)
- All skill/pipeline modifications create a **new version**, never mutate existing
- Version DAG tracks lineage (carried from Gate 2)
- **Pipeline versioning with advisory locks:** if distillation runner is evaluating version N, OpenSpace creates version N+1 but doesn't promote it until distillation completes or releases its pin

### 5.2 Observation-Driven Triggers — `plugins/observer.py`

For parallel sessions. Vizier watches its own execution patterns and spawns work via `delegate_task` (single-task batch, no decomposition needed):

| Pattern | Action |
|---------|--------|
| Quality trending down over last 10 runs on a step | Spawn OpenSpace FIXED attempt via `delegate_task` |
| 3+ Qwen fallbacks on a distilled step | Spawn distillation re-evaluation via `delegate_task` |
| 3+ cost anomalies on same pipeline in a week | Spawn investigation session via `delegate_task` |

Safety bounds per observation type:

- **Cooldown period:** configurable, default 24h — prevents runaway spawning
- **Token budget cap:** per spawned session
- **Context propagation:** spawned tasks carry a system `deliverable_id` (prefixed `obs_`) for cost tracking — these are internal costs, not client-billable

Observer runs as a lightweight periodic check (every 30 minutes), not a continuous stream.

### 5.3 Research-Driven Triggers — `plugins/researcher.py`

For unattended sessions. Vizier initiates work based on accumulated knowledge. Spawns via Hermes cron mechanism (same as Gate 2 unattended sessions):

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
2. **Version control:** Every change creates a new version (immutable). Rollback = revert to previous version
3. **Auto-revert:** If quality drops in next 5 production runs after promotion, auto-revert and flag
4. **Rate limit:** Max N self-modifications per day (configurable, default 5)
5. **Conflict detection:** Check if distillation runner has a pin on the pipeline being modified. If so, queue the modification
6. **Audit log:** Every self-modification recorded — rationale, before/after metrics, trigger source (observation/research/manual)

Daily Telegram digest: summary of all self-modifications, auto-reverts, and anomalies with links to audit log entries and trace files.

---

## 6. Dependency Matrix

| Gate 4 Component | Gate 1 Deps | Gate 2 Deps | Gate 4 Internal Deps | Gate 3 Deps |
|---|---|---|---|---|
| `deliverable_context` | prompt_logger | `delegate_task` (cross-session) | — | — |
| `cost_ledger` | prompt_logger DB | — (view degrades gracefully) | — | — |
| `trace_exporter` | prompt_logger | `send_telegram`, quality gate L3-6 | cost_ledger | — |
| `query_costs` | — | — | cost_ledger | — |
| `gpu_scheduler` | — | Qwen local | — | — |
| `candidate_selector` | — | all workflow toolsets | cost_ledger | — |
| `prompt_adapter` | — | Qwen local | cost_ledger, gpu_scheduler | — |
| `distillation_runner` | — | quality gate L3-6, Qwen local | cost_ledger, gpu_scheduler | — |
| `model_router` | — | Qwen local | distillation_config, gpu_scheduler | — |
| `embedded_openspace` | — | OpenSpace modules | — | — |
| `observer` | — | parallel sessions (`delegate_task`) | cost_ledger | pattern-driven triggers |
| `researcher` | — | Dream-skill memory, cron mechanism | cost_ledger | data-driven triggers |
| `evolution_guard` | — | — | — | code workflow |

---

## 7. Gate 4 Exit Criteria

1. **Cost ledger active** — every LLM call and tool execution tracked with `deliverable_id`, cost rolled up per deliverable and per client
2. **Anomaly detection firing** — suboptimal runs (quality or cost) auto-export full traces and notify via Telegram
3. **At least 3 pipeline steps distilled to Qwen** — running in production with quality >= threshold, fallback to GPT-5.4-mini working
4. **Model router live** — step-level routing between GPT-5.4-mini and Qwen based on distillation config
5. **Prompt adaptation validated** — Qwen-specific prompts producing equivalent quality to GPT-5.4-mini prompts
6. **OpenSpace embedded** — running as Hermes plugin package, not MCP server. Version DAG active, advisory locks coordinating with distillation
7. **Observation triggers active** — at least one observation type (quality degradation, fallback detection, or cost anomaly clustering) spawning corrective work via `delegate_task`
8. **Research triggers active** — at least one research-initiated action (template preparation, pipeline optimization, or knowledge ingestion) executed through quality gate
9. **Evolution guard enforcing** — sandbox execution, auto-revert, rate limiting, conflict detection all active
10. **Daily audit digest** — Telegram summary of self-modifications, anomalies, cost breakdown, model distribution
11. **Autonomous operation validated** — system operated for 7 consecutive days with zero manual pipeline interventions required

---

## 8. Estimated Scope

| Track | Source Files | Test Files | New Lines (est.) | Tests (est.) |
|-------|-------------|-----------|------------------|--------------|
| Track 1: Deliverable Ledger | ~6 | ~6 | ~700 | ~40 |
| Track 2: Progressive Distillation | ~7 | ~7 | ~1,100 | ~55 |
| Track 3: Self-Evolution | ~10 | ~8 | ~900 | ~50 |
| **Total** | **~23** | **~21** | **~2,700** | **~145** |

Plus: 3 config files (cost_config.yaml, gpu_scheduler.yaml, distillation_config.yaml), 1 migration file.

---

## 9. Key Design Decisions

1. **No DSPy** — distillation uses direct quality gate evaluation against exemplar traces. Simpler, reuses existing infrastructure. Supersedes main spec's Gate 3 DSPy reference.
2. **Prompt adaptation over blind substitution** — same task may need different prompts for different models. The prompt adapter phase is critical for distillation success.
3. **Pipeline versioning with advisory locks** — prevents distillation/evolution conflicts without heavy locking infrastructure.
4. **Progressive offload, not cutover** — Qwen earns each step. Three fallbacks in 24h triggers auto-revert. No risk of quality degradation at scale.
5. **Embedded OpenSpace as plugin package, MCP server optional** — by Gate 4, Hermes is the operator. Network hop overhead unjustified for the primary path. Multi-file structure preserved from Gate 2 `augments/openspace/`.
6. **Cross-session context via explicit parameters** — contextvars don't cross process boundaries. `delegate_task` carries `deliverable_id` in its `context` field.
7. **Immutable config history** — distillation config changes create new versions, never overwrite. Enables rollback and audit trail.
8. **Conservative Qwen context threshold** — 8K default despite 128K window capacity. Smaller context = more reliable output quality. Tunable per step based on empirical results.

---

## 10. Required Gate 3 Interfaces

Gate 4 Track 3 depends on three Gate 3 components. These interfaces must be satisfied by Gate 3's design:

### 10.1 Pattern-Driven Triggers (needed by: `observer`)

The observer needs a mechanism to register pattern-based trigger rules that fire when execution data matches a pattern. Required interface:

- `register_pattern(pattern_spec, callback)` — register a pattern to watch for
- Pattern spec includes: metric name, condition (threshold, trend, count), time window
- Callback receives the matched data points

If Gate 3 implements this differently, the observer can adapt as long as the capability exists to fire callbacks based on execution data patterns.

### 10.2 Data-Driven Triggers (needed by: `researcher`)

The researcher needs the ability to initiate unattended sessions based on data analysis results (not just cron schedules). Required interface:

- Ability to programmatically create a cron job or one-shot scheduled task
- Task includes: prompt, toolsets, token budget, quality threshold
- Same format as Gate 2 cron configs but created at runtime, not statically

### 10.3 Code Workflow (needed by: `evolution_guard`)

The evolution guard needs the ability to create and modify pipeline files and skill files programmatically. Required interface:

- `aider_edit` tool (from vizier-code toolset) or equivalent for modifying Python files
- `git_commit` tool for committing changes
- Sandbox execution environment for testing changes before promotion

---

## 11. Migration Notes

### 11.1 Database Schema Migration

The cost_ledger extends prompt_logger's SQLite database. Migration via `migrations/001_cost_ledger.sql`:

- Adds `cost_ledger` table (does not modify existing `prompt_log` table)
- Adds `cost_baselines` table
- Adds `deliverable_summary` view (joins cost_ledger with quality gate results)
- Adds nullable `deliverable_id` column to `prompt_log` table (backward compatible — existing records have NULL)

### 11.2 OpenSpace Migration (Gate 2 → Gate 4)

- Gate 2 `augments/openspace/` modules copied to `plugins/openspace/` with plugin registration wrapper
- `augments/openspace/server.py` remains in place as read-only MCP debug interface
- No data migration needed — version DAG storage format unchanged
