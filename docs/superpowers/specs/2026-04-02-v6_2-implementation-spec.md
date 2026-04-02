# Vizier v6.2 Implementation Spec

**Date:** 2026-04-02  
**Status:** Draft for execution  
**Scope:** Memory, bridge, self-improvement, governance, and clone foundations  
**Reference:** `/Users/Executor/Downloads/vizier-platform-architecture-v6_2.md`

---

## 1. Purpose

This spec turns the v6.2 aspiration into an implementable architecture that can be built safely in parallel.

The core conclusion from the Hermes deep dive is:

- Hermes remains the sole runtime.
- Vizier should reuse Hermes primitives for runtime memory, skills, sessions, delegation, hooks, trajectories, and benchmarks.
- Vizier should add the layers Hermes does not already provide:
  - apprenticeship bridge capture
  - structured observational memory
  - candidate-only mutation flow
  - promotion governance
  - clone-specific structured generation and evaluation

This spec is intentionally biased toward fail-closed behavior, replayability, and explicit provenance.

---

## 2. System Boundary

### 2.1 Hermes owns

- runtime session execution
- `MEMORY.md` and `USER.md`
- `state.db` session storage and `session_search`
- skills loading and `skill_manage`
- plugin hooks
- Honcho integration
- delegation
- trajectories and batch evaluation substrate

### 2.2 Vizier owns

- external-builder capture
- build and runtime observational memory
- candidate registry and lineage
- selfbuild replay and promotion decisions
- distillation governance
- clone `DesignSpec` and clone benchmarks

### 2.3 Anti-goals

Vizier will not:

- replace Hermes with another runtime
- duplicate Hermes session storage with a second transcript database
- auto-promote from a single successful run
- let bridge code make policy decisions
- let OpenSpace or distillation write directly into production without a gate

---

## 3. Memory Model

The v6.2 aspiration names multiple memory technologies. For implementation, they collapse into three planes:

### 3.1 Working memory

- current Hermes conversation context
- `MEMORY.md` / `USER.md`
- active Honcho context
- ephemeral session-level state

### 3.2 Retrieval memory

- Hermes `state.db`
- `session_search`
- Honcho semantic recall
- future adapters such as Mem0 or LightRAG if needed later

### 3.3 Promoted memory

- observations
- reflections
- promoted lessons
- reusable skills
- governed candidate artifacts

The critical design rule is:

**retrieval memory recalls facts; promoted memory changes future behavior**

That means raw sessions, transcripts, or traces are never treated as approved policy on their own.

---

## 4. Core Contracts

All packets in this program must use these contract shapes. Exact field types may be implemented as dataclasses, `TypedDict`, Pydantic models, or another typed representation, but the contract meanings are fixed.

### 4.1 `BuildCaptureEvent`

Represents one externally or internally observed builder/runtime event.

Required fields:

- `event_id`
- `timestamp`
- `source`
  - `human`
  - `codex`
  - `claude`
  - `vizier`
- `context_type`
  - `external_build`
  - `runtime`
  - `selfbuild`
  - `evolution`
- `task_id`
- `event_type`
  - `task_started`
  - `decision_made`
  - `file_changed`
  - `command_run`
  - `verification_run`
  - `failure_seen`
  - `artifact_created`
  - `task_completed`
- `summary`
- `status`
  - `ok`
  - `degraded`
  - `error`

Optional fields:

- `parent_task_id`
- `files_touched`
- `commands`
- `verifications`
- `artifacts`
- `labels`
- `trace_refs`
- `metadata`

### 4.2 `DecisionPacket`

Normalized handoff between capture, observational memory, evolution, and selfbuild.

Required fields:

- `packet_id`
- `source_event_ids`
- `problem`
- `proposed_change`
- `verification_plan`
- `candidate_targets`
- `status`
  - `draft`
  - `ready_for_reflection`
  - `ready_for_candidate`
  - `archived`

Optional fields:

- `evidence`
- `risk_tier`
- `confidence`
- `notes`

### 4.3 `Observation`

Structured learned statement derived from one or more episodes.

Required fields:

- `observation_id`
- `episode_ids`
- `kind`
  - `pattern`
  - `preference`
  - `anti_pattern`
  - `workflow`
  - `constraint`
  - `failure_mode`
- `statement`
- `confidence`
  - `low`
  - `medium`
  - `high`
- `status`
  - `active`
  - `superseded`
  - `rejected`

Optional fields:

- `supporting_evidence`
- `applies_to`
- `tags`
- `superseded_by`

### 4.4 `CandidateArtifact`

Represents a proposed change that is not yet promoted.

Required fields:

- `candidate_id`
- `artifact_type`
  - `skill`
  - `prompt`
  - `template`
  - `pipeline`
  - `routing`
  - `distillation_program`
- `source`
  - `bridge`
  - `openspace`
  - `distillation`
  - `manual`
- `candidate_path`
- `intended_target`
- `status`
  - `draft`
  - `under_evaluation`
  - `held`
  - `rejected`
  - `promoted`

Optional fields:

- `decision_packet_id`
- `provenance`
- `eval_pack`
- `risk_tier`

### 4.5 `PromotionDecision`

Single source of truth for selfbuild outcomes.

Required fields:

- `decision_id`
- `candidate_id`
- `outcome`
  - `promoted`
  - `held`
  - `rejected`
  - `archived`
- `timestamp`
- `reasons`

Optional fields:

- `replay_results`
- `benchmark_results`
- `regression_report`
- `promoted_to`
- `approver`

---

## 5. State Layout

Runtime-generated architecture state lives outside source code and remains append-first where possible.

```text
state/
├── build_capture/
│   ├── events.jsonl
│   └── index.sqlite
├── observational/
│   ├── episodes.sqlite
│   ├── observations.sqlite
│   └── reflections.sqlite
├── candidates/
│   ├── skills/
│   ├── prompts/
│   ├── templates/
│   ├── pipelines/
│   ├── routing/
│   └── distillation/
├── selfbuild/
│   ├── decisions.jsonl
│   ├── replay/
│   └── benchmarks/
└── distillation/
    ├── approved_traces/
    └── evaluations/
```

Rules:

- Source code is not the candidate scratchpad.
- Generated artifacts land in `state/candidates/` first.
- `MEMORY.md` may remain, but it is a rendered view, not the canonical observational ledger.
- Promotion records are append-only.

---

## 6. Runtime Flow

### 6.1 External apprenticeship flow

`human/Codex/Claude build session -> bridge capture -> decision packet -> observational memory -> candidate artifact -> selfbuild -> promoted artifact`

### 6.2 Runtime self-improvement flow

`Hermes run -> capture hooks -> observational reflection -> OpenSpace candidate -> selfbuild decision -> optional promotion`

### 6.3 Distillation flow

`approved traces only -> compile/evaluate distilled candidate -> selfbuild decision -> deployment`

### 6.4 Clone flow

`image ingest -> OCR/layout/palette extraction -> DesignSpec -> deterministic skeleton -> render -> region-aware scoring -> targeted refinement -> selfbuild/benchmarks`

---

## 7. Component Responsibilities

### 7.1 Bridge

Purpose:

- capture evidence
- normalize event packets
- sync local/runtime observations into structured inputs

Bridge must not:

- infer lessons
- promote artifacts
- write directly into active skills or pipelines

### 7.2 Observational memory

Purpose:

- derive observations from evidence
- attach provenance and confidence
- track supersession and rejection
- produce promoted lessons only after sufficient support

### 7.3 OpenSpace

Purpose:

- generate candidate artifacts
- repair or mutate candidate variants
- preserve lineage

OpenSpace must not:

- mutate active production surfaces directly

### 7.4 Selfbuild

Purpose:

- run replay
- run benchmark checks
- classify regressions
- issue one decision record

Selfbuild is the only promotion gate.

### 7.5 Distillation

Purpose:

- operate on approved traces
- evaluate candidate distilled programs
- request deployment through selfbuild

### 7.6 Clone architecture

Purpose:

- move clone generation away from unconstrained end-to-end HTML guessing
- produce replayable `DesignSpec` artifacts
- keep parameterization deterministic where possible

---

## 8. Parallel Packet Order

The implementation program is intentionally split into one serial gate and two parallel waves.

### 8.1 Wave 0

- `contracts-ledger`

This lands first. All later packets rely on the same contracts and state roots.

### 8.2 Wave 1

These can proceed in parallel once Wave 0 is merged:

- `bridge-capture`
- `observational-memory`
- `selfbuild-gate`
- `openspace-candidate-flow`
- `distillation-governance`

### 8.3 Wave 2

These begin after the foundations are stable:

- `quality-ci`
- `clone-designspec`

---

## 9. Acceptance Criteria

The architecture is considered implemented when all of the following are true:

- build and runtime events are captured into structured evidence
- observational memory is canonical and `MEMORY.md` is derivative
- OpenSpace emits candidates only
- selfbuild is the sole promotion path
- distillation uses approved traces only
- first-party CI enforces doctor, lint, types, and offline tests
- clone flow emits `DesignSpec` and benchmark-friendly outputs

---

## 10. Reuse vs Build

### Reuse from Hermes

- `memory_tool`
- `session_search_tool`
- `hermes_state.SessionDB`
- `skill_manage`
- Honcho session modeling
- plugin hooks
- delegation
- trajectories
- `batch_runner`
- benchmark environments

### Build in Vizier

- apprenticeship bridge capture
- observational ledger
- decision packet pipeline
- selfbuild governance
- candidate registry
- clone `DesignSpec`

### Adopt later

[NousResearch/hermes-agent-self-evolution](https://github.com/NousResearch/hermes-agent-self-evolution) is suitable as an offline optimizer later, especially for skill evolution, but it is not the primary governance layer for Vizier.

---

## 11. Non-Negotiable Rules

- Silent fallback cannot masquerade as success.
- A remembered pattern is not automatically a promoted policy.
- A generated artifact is not production until selfbuild promotes it.
- Bridge code stays deterministic and non-judgmental.
- Distillation never trains or deploys from degraded traces.
- Clone quality is editability plus fidelity, not screenshot similarity alone.
