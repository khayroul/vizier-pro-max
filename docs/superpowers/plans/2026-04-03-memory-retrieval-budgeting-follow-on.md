# Memory Retrieval and Budgeting Follow-on

**Date:** 2026-04-03  
**Status:** Proposed follow-on packet  
**Primary spec:** `docs/superpowers/specs/2026-04-02-v6_2-implementation-spec.md`

---

## 1. Goal

Add a personal-assistant-safe retrieval and budgeting layer on top of the canonical observational ledger.

This follow-on exists to preserve two truths at the same time:

- Vizier should remember broadly and durably.
- Vizier should inject memory into prompt context narrowly and deliberately.

The core rule is:

**non-selected memory is not forgotten memory**

This follow-on may be scheduled after the broader architecture wave settles if you want lower churn, but its only intended hard dependency is the canonical observational-memory layer.

---

## 2. Design Rules

### 2.1 Canonical versus derived memory

- `episodes.sqlite`, `observations.sqlite`, and `reflections.sqlite` remain the canonical observational store.
- `MEMORY.md` becomes a human-readable derived artifact, not the retrieval authority.
- prompt assembly should use a budgeted memory pack derived from the ledger rather than the full list of active records.

### 2.2 Memory classes

The follow-on should classify memories for ranking and retention without changing the canonical contract surface unless absolutely necessary.

Prefer deriving classes from tags and provenance metadata first:

- `core_identity`
- `user_preference`
- `relationship`
- `long_term_goal`
- `project_context`
- `workflow_lesson`
- `historical`
- `ephemeral`

### 2.3 Pinning

Support at least these pin modes:

- user-pinned: explicit "remember this" or "never forget this"
- system-pinned: repeated strong evidence or promotion into durable assistant context

Pinned memories must survive derived-view pruning and must outrank unpinned memories in prompt assembly.

### 2.4 Retrieval ranking

Default ranking order:

1. pinned memory
2. core identity and durable personal preferences
3. direct relevance to current task, project, person, or workflow
4. promoted lessons
5. reflection confidence and support breadth
6. recency

Recency alone must not dominate personal-assistant memory selection.

### 2.5 Derived views

The follow-on should distinguish between:

- broad human-readable memory view
- compact prompt-memory pack
- archival view for overflow

Avoid duplicate prompt surface area:

- promoted lessons should not be repeated again as equivalent active reflections unless needed for context
- raw observations should only appear when there is no better reflection-level summary for the same topic

---

## 3. Target File Scope

Expected owned paths for the packet:

- `augments/observational/retrieval.py`
- `augments/observational/compiler.py`
- `augments/observational/ledger.py`
- `augments/dreamskill/consolidator.py`
- `augments/dreamskill/pruner.py`
- `tests/augments/test_observational_retrieval.py`
- `tests/augments/test_observational_compiler.py`
- `tests/augments/test_observational_ledger.py`
- `tests/augments/test_consolidator.py`

The implementation should avoid changing `augments/observational/types.py` unless the ranking layer is truly blocked without a contract change.

---

## 4. Implementation Shape

### 4.1 Retrieval module

Introduce a retrieval helper that can:

- rank reflections for prompt context
- rank observations as a fallback surface
- build a prompt-memory pack with explicit size limits
- expose retrieval filters by tags, applies_to, task context, and pinned status

### 4.2 Ledger queries

Extend the ledger with helper queries that avoid full-table prompt assembly for every turn.

The important shift is from:

- `list everything active`

to:

- `retrieve the best memory set for this context and this budget`

### 4.3 Compiler changes

Update the compiler so it can:

- render a broader human-readable `MEMORY.md`
- render a compact prompt-memory pack
- avoid duplicate promoted-lesson and reflection output

### 4.4 Consolidation changes

Update consolidation so it:

- writes derived memory views from the ledger
- applies explicit budgeting or token-aware pruning to derived prompt-facing output
- never deletes canonical ledger rows merely because a derived view overflows

### 4.5 Pruning

Replace or augment line-count pruning with explicit-budget behavior.

If exact token counting is too heavy for the first version, use a deterministic budget approximation and hard caps by:

- section count
- item count
- evidence snippet length

---

## 5. Acceptance

- canonical observational ledgers remain the source of truth
- omission from prompt assembly does not delete or invalidate canonical memory
- pinned or durable personal-assistant memories outrank ephemeral operational memories
- prompt-memory assembly obeys an explicit budget
- derived memory output avoids duplicate promoted-lesson and reflection rendering
- tests cover ranking, pinning, budgeting, and archival behavior

---

## 6. Non-goals

- do not add selfbuild promotion logic here
- do not change bridge capture semantics here
- do not redesign Hermes `session_search` or Honcho here
- do not delete historical observational rows solely to reduce prompt size

---

## 7. Suggested Verification

```bash
python3 -m pytest \
  tests/augments/test_observational_ledger.py \
  tests/augments/test_observational_compiler.py \
  tests/augments/test_observational_retrieval.py \
  tests/augments/test_consolidator.py -q
```
