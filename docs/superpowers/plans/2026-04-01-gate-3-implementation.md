# Vizier Pro-Max Gate 3 Implementation Plan — "Builds Itself"

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vizier generates its own tools, distills routine tasks to local Qwen, processes uploaded data autonomously, and runs code in a sandboxed environment — all with tiered safety gates.

**Architecture:** DSPy compilation distills GPT-5.4-mini knowledge into Qwen 3.5 9B for cost-free offline routing. Self-building workflow uses OpenSpace CAPTURED patterns + tiered autonomy (auto-promote collapses, human-approve atomics). execute_code gains AST-based sandbox guard + audit trail. File uploads trigger batch pipelines automatically.

**Tech Stack:** Python 3.11+, Hermes Agent v0.6.0, DSPy, Qwen 3.5 9B (Ollama — already installed), scikit-learn (evaluator metrics), watchdog (optional, fallback to polling)

**Spec:** `docs/superpowers/specs/2026-04-01-gate-2-3-design.md` §14-17

**Gate 2 plan (format reference):** `docs/superpowers/plans/2026-04-02-gate-2-implementation.md`

**Hermes internals:**
- `~/hermes-agent/run_agent.py` — AIAgent, `_invoke_tool` (line 5268), main loop (line 6302+)
- `~/hermes-agent/tools/registry.py` — `registry.register(name, toolset, schema, handler, check_fn, ...)`
- `~/hermes-agent/hermes_cli/plugins.py` — `VALID_HOOKS`, `PluginContext.register_tool()`, `register_hook()`

**Gate 2 outputs this plan depends on:**
- `plugins/prompt_logger.py` — SQLite trace store (training data source)
- `middleware/quality_gate.py` — 6-layer QA pipeline (evaluator reference)
- `augments/openspace/capturer.py` — Pattern detection (auto-promote source)
- `augments/openspace/safety.py` — AST-based skill validation (reused by sandbox)
- `augments/openspace/generator.py` — Draft generation (self-building input)
- `bridge/manifest_syncer.py` — Registry promotion (auto-promote target)
- `config/toolsets.py` — VIZIER_WORKFLOW_TOOLSETS (add vizier-code)

---

## File Map

### Chunk 0 — Prerequisites (Burn-in + Calibration)

| File | Responsibility |
|------|---------------|
| `scripts/bootstrap/generate_synthetic_sessions.py` | Generate 200+ synthetic training examples from pipeline test fixtures |
| `scripts/bootstrap/calibrate_quality_gate.py` | Run N deliverables through quality gate, output human-vs-automated score comparison |
| `config/bootstrap/synthetic_sessions.yaml` | Template definitions for synthetic session generation |
| `tests/bootstrap/test_generate_synthetic.py` | Tests for synthetic generator |
| `tests/bootstrap/test_calibrate_quality.py` | Tests for calibration script |

### Chunk 1 — DSPy Distillation Pipeline

| File | Responsibility |
|------|---------------|
| `augments/distillation/__init__.py` | Package init |
| `augments/distillation/collector.py` | Extract training examples from prompt_logger SQLite |
| `augments/distillation/compiler.py` | DSPy program definition + BootstrapFewShot compilation |
| `augments/distillation/evaluator.py` | Compare Qwen output vs GPT-5.4-mini reference |
| `augments/distillation/deployer.py` | Swap distilled model into models.yaml when accuracy >= 90% |
| `config/distillation_config.yaml` | Per-task routing map (task type → model, accuracy, deployed_at) |
| `config/models.yaml` | Centralized model routing (extend with distilled_tasks section) |
| `tests/augments/test_collector.py` | Collector unit tests |
| `tests/augments/test_compiler.py` | Compiler unit tests |
| `tests/augments/test_evaluator.py` | Evaluator unit tests |
| `tests/augments/test_deployer.py` | Deployer unit tests |
| `tests/test_integration_distillation.py` | E2E: collect → compile → evaluate → deploy |

### Chunk 2 — Code Workflow (Self-Building)

| File | Responsibility |
|------|---------------|
| `augments/selfbuild/__init__.py` | Package init |
| `augments/selfbuild/tier_classifier.py` | Classify generated artifact as Tier 1 (auto) or Tier 2 (human) |
| `augments/selfbuild/promoter.py` | Auto-promote Tier 1 collapses, hold Tier 2 for review |
| `augments/selfbuild/notifier.py` | Telegram notification for Tier 2 human approval |
| `config/toolsets.py` | Add vizier-code to VIZIER_WORKFLOW_TOOLSETS |
| `manifests/code/aider_edit.yaml` | Manifest for aider-based file editing |
| `manifests/code/git_commit.yaml` | Manifest for git commit tool |
| `config/SOUL.md` | Add self-building rules (new files → execute_code, edits → aider_edit) |
| `tests/augments/test_tier_classifier.py` | Tier classification tests |
| `tests/augments/test_promoter.py` | Promotion workflow tests |
| `tests/augments/test_notifier.py` | Notification tests |
| `tests/test_integration_selfbuild.py` | E2E: generate → classify → promote/hold |

### Chunk 3 — execute_code Sandbox Extensions

| File | Responsibility |
|------|---------------|
| `augments/sandbox/__init__.py` | Package init |
| `augments/sandbox/guard.py` | Pre-execution AST scan for blocked patterns |
| `augments/sandbox/audit.py` | Post-execution logging (code, files touched, network calls) |
| `plugins/sandbox_plugin.py` | Hermes plugin: pre_tool_call + post_tool_call on execute_code |
| `tests/augments/test_guard.py` | Guard unit tests (blocked patterns, edge cases) |
| `tests/augments/test_audit.py` | Audit logging tests |
| `tests/test_integration_sandbox.py` | E2E: execute_code with guard + audit |

### Chunk 4 — Data-Driven Triggers

| File | Responsibility |
|------|---------------|
| `scripts/triggers/__init__.py` | Package init |
| `scripts/triggers/data_trigger.py` | Watch uploads/, validate, classify, start Hermes session |
| `config/triggers/filename_rules.yaml` | Filename convention → toolset + pipeline mapping |
| `tests/scripts/test_data_trigger.py` | Trigger unit tests |
| `tests/test_integration_triggers.py` | E2E: upload CSV → batch process → delivery |

### Test Files (summary)

| Test file | Tests for |
|-----------|-----------|
| `tests/bootstrap/test_generate_synthetic.py` | Synthetic session generator |
| `tests/bootstrap/test_calibrate_quality.py` | Quality gate calibration |
| `tests/augments/test_collector.py` | DSPy training data extraction |
| `tests/augments/test_compiler.py` | DSPy compilation |
| `tests/augments/test_evaluator.py` | Qwen vs GPT accuracy comparison |
| `tests/augments/test_deployer.py` | Model routing deployment |
| `tests/test_integration_distillation.py` | E2E distillation pipeline |
| `tests/augments/test_tier_classifier.py` | Tier 1/2 classification |
| `tests/augments/test_promoter.py` | Auto-promote + hold workflows |
| `tests/augments/test_notifier.py` | Telegram review notifications |
| `tests/test_integration_selfbuild.py` | E2E self-building |
| `tests/augments/test_guard.py` | Sandbox AST guard |
| `tests/augments/test_audit.py` | Sandbox audit logging |
| `tests/test_integration_sandbox.py` | E2E sandbox execution |
| `tests/scripts/test_data_trigger.py` | File upload trigger |
| `tests/test_integration_triggers.py` | E2E data-driven batch |

---

## Chunk 0: Prerequisites — Burn-in Bootstrapping + Quality Gate Calibration

> **Why this chunk exists:** Gate 3's DSPy distillation requires 200+ classified session exemplars from prompt_logger, and the evaluator trusts quality gate scores to validate Qwen vs GPT-5.4-mini. Gate 2 is code-complete but hasn't accumulated enough production runs. This chunk bridges the gap with synthetic bootstrapping and calibration.

### Task 1: Synthetic session generator

**Files:**
- Create: `scripts/bootstrap/__init__.py`, `scripts/bootstrap/generate_synthetic_sessions.py`
- Create: `config/bootstrap/synthetic_sessions.yaml`
- Create: `tests/bootstrap/__init__.py`, `tests/bootstrap/test_generate_synthetic.py`

- [ ] **Step 1: Define synthetic session templates**

Create `config/bootstrap/synthetic_sessions.yaml` with template definitions covering all distillable task types:

```yaml
# Each template represents a class of session that Gate 2 pipelines handle
templates:
  task_classification:
    count: 80  # largest category — most important for distillation
    variations:
      - input: "Create a social media post about {topic}"
        expected_toolset: vizier-content
        expected_pipeline: content_generate
      - input: "Design a poster for {event}"
        expected_toolset: vizier-visual
        expected_pipeline: poster_batch
      - input: "Generate a competitive analysis of {market}"
        expected_toolset: vizier-research
        expected_pipeline: competitive_analysis
      - input: "Convert this document to PDF"
        expected_toolset: vizier-document
        expected_pipeline: null  # atomic tools, no pipeline
      - input: "Create a voiceover for {script}"
        expected_toolset: vizier-audio
        expected_pipeline: tts_generate

  template_selection:
    count: 50
    variations:
      - input: "Use the minimalist template for {brand}"
        expected_template: "minimalist"
      - input: "Corporate style for {client}"
        expected_template: "corporate"

  tool_routing:
    count: 40
    variations:
      - input: "Resize this image to 1080x1080"
        expected_tool: pillow_process
      - input: "Take a screenshot of this HTML"
        expected_tool: playwright_screenshot

  outline_generation:
    count: 30
    variations:
      - input: "Brief: {brief_text}"
        expected_output_keys: ["headline", "body", "cta", "hashtags"]
```

- [ ] **Step 2: Write synthetic session generator**

Create `scripts/bootstrap/generate_synthetic_sessions.py`:

```python
"""Generate synthetic training examples and insert into prompt_logger SQLite.

Reads templates from config/bootstrap/synthetic_sessions.yaml, expands
placeholders with randomized values, and writes (input, toolset, pipeline,
success) rows into the same SQLite schema that prompt_logger uses.

This bridges the gap between Gate 2 code-complete and the 200+ exemplars
DSPy collector needs for compilation.
"""
```

Key behavior:
- Load templates from YAML
- Expand `{topic}`, `{event}`, `{market}`, etc. with randomized values from a seed word list
- Insert into prompt_logger SQLite with `synthetic=True` flag (so collector can filter if needed)
- Each row: `(session_id, timestamp, input_message, toolset_chosen, pipeline_used, tool_calls, success, synthetic)`
- Deterministic with seed for reproducibility
- Target: 200+ rows total across all task types

- [ ] **Step 3: Write tests for synthetic generator**

Create `tests/bootstrap/test_generate_synthetic.py`:
- Test that generator produces >= 200 rows
- Test that all task types are represented
- Test that synthetic flag is set
- Test deterministic output with same seed
- Test that rows match prompt_logger schema

- [ ] **Step 4: Run generator, verify prompt_logger has 200+ rows**

```bash
python -m scripts.bootstrap.generate_synthetic_sessions
# Verify:
python -c "import sqlite3; db = sqlite3.connect('data/prompt_log.db'); print(db.execute('SELECT COUNT(*) FROM sessions WHERE synthetic=1').fetchone())"
```

### Task 2: Quality gate calibration

**Files:**
- Create: `scripts/bootstrap/calibrate_quality_gate.py`
- Create: `tests/bootstrap/test_calibrate_quality.py`

- [ ] **Step 5: Write quality gate calibration script**

Create `scripts/bootstrap/calibrate_quality_gate.py`:

```python
"""Run sample deliverables through quality gate layers 1-6 and output
a calibration report comparing automated scores against expected outcomes.

Purpose: Validate that quality gate scores are trustworthy before DSPy
evaluator uses them to judge Qwen vs GPT-5.4-mini output quality.
"""
```

Key behavior:
- Collect sample deliverables: use existing pipeline test fixtures as inputs
- Run each through `middleware/quality_gate.py` all 6 layers
- For each deliverable, record:
  - Layer scores (1-6)
  - Composite score
  - Expected outcome (pass/fail based on known fixture quality)
- Output calibration report:
  - Accuracy: % of correct pass/fail decisions
  - Per-layer precision/recall
  - Recommended threshold adjustments (if accuracy < 90%)
- Write report to `data/calibration_report.json`

- [ ] **Step 6: Write calibration tests**

Create `tests/bootstrap/test_calibrate_quality.py`:
- Test that known-good fixtures score >= 7/10
- Test that known-bad fixtures (e.g., empty output, wrong format) score < 7/10
- Test that calibration report contains all required fields
- Test threshold recommendation logic

- [ ] **Step 7: Run calibration, review report, adjust quality gate thresholds if needed**

```bash
python -m scripts.bootstrap.calibrate_quality_gate
cat data/calibration_report.json
```

If accuracy < 90%, adjust thresholds in `middleware/quality_gate.py` layer configs before proceeding to Chunk 1.

- [ ] **Step 8: Run pyright + tests for Chunk 0**

```bash
pyright scripts/bootstrap/ tests/bootstrap/
pytest tests/bootstrap/ -v --tb=short
```

---

## Chunk 1: DSPy Distillation Pipeline

> **Prerequisite:** Chunk 0 complete (200+ exemplars in prompt_logger, quality gate calibrated).
> **Spec reference:** §14

### Task 1: Package scaffolding + collector

**Files:**
- Create: `augments/distillation/__init__.py`
- Create: `augments/distillation/collector.py`
- Create: `tests/augments/test_collector.py`

- [ ] **Step 1: Create distillation package init**

```python
# augments/distillation/__init__.py
"""DSPy distillation pipeline — migrate tasks from GPT-5.4-mini to Qwen local."""
```

- [ ] **Step 2: Write collector.py**

Extract training examples from prompt_logger SQLite:

```python
"""Extract (input, toolset, success) training pairs from prompt_logger.

Returns list[TrainingExample] with at least 200 rows for the target task type.
Supports filtering by task_type, date range, and synthetic flag.
Splits into train/test sets (80/20) with stratified sampling.
"""
```

Key behavior:
- Query prompt_logger SQLite for classified sessions
- Filter by task_type (e.g., "task_classification", "template_selection")
- Return `list[TrainingExample]` dataclass with (input, expected_output, metadata)
- Split into train (80%) and held-out test (20%) sets
- Raise `InsufficientDataError` if fewer than 200 examples available

- [ ] **Step 3: Write collector tests**

- Test extraction from populated DB (use synthetic rows from Chunk 0)
- Test train/test split ratios
- Test filtering by task_type
- Test InsufficientDataError when < 200 rows
- Test that synthetic rows are included by default, excludable via flag

### Task 2: DSPy compiler

**Files:**
- Create: `augments/distillation/compiler.py`
- Create: `tests/augments/test_compiler.py`

- [ ] **Step 4: Write compiler.py**

```python
"""DSPy program definition + compilation from GPT-5.4-mini teacher to Qwen student.

Defines a DSPy Signature (message -> toolset) and uses BootstrapFewShot
to optimize prompts for Qwen 3.5 9B via Ollama.
"""
```

Key behavior:
- Define DSPy `Signature`: `input_message -> toolset_name`
- Define DSPy `Module` wrapping the signature with Chain-of-Thought
- Configure teacher LM: GPT-5.4-mini via existing Hermes API config
- Configure student LM: Qwen 3.5 9B via Ollama (`http://localhost:11434`)
- Run `BootstrapFewShot` optimizer with training examples from collector
- Save compiled program to `data/distilled/{task_type}/program.json`
- Return compilation metrics (num_examples, num_bootstrapped, duration)

- [ ] **Step 5: Write compiler tests**

- Test DSPy program definition (signature, module)
- Test compilation with mock LMs (don't hit real APIs in unit tests)
- Test program serialization/deserialization
- Test that compiled program produces valid toolset names

### Task 3: Evaluator + deployer

**Files:**
- Create: `augments/distillation/evaluator.py`
- Create: `augments/distillation/deployer.py`
- Create: `config/distillation_config.yaml`
- Create: `tests/augments/test_evaluator.py`
- Create: `tests/augments/test_deployer.py`

- [ ] **Step 6: Write evaluator.py**

```python
"""Compare Qwen distilled output against GPT-5.4-mini reference.

Uses held-out test set from collector. Reports accuracy, latency,
and per-class precision/recall. Uses calibrated quality gate scores
(from Chunk 0) for output quality comparison.
"""
```

Key behavior:
- Load compiled DSPy program from disk
- Run held-out test examples through Qwen program
- Compare against expected outputs: exact match for classification, quality gate score for generated content
- Return `EvaluationReport` dataclass: accuracy, per_class_metrics, avg_latency, recommendation (deploy/hold)
- Threshold: accuracy >= 90% → recommend deploy

- [ ] **Step 7: Write deployer.py**

```python
"""Swap distilled model into routing config when evaluation passes.

Updates config/models.yaml and config/distillation_config.yaml with
the newly deployed task type, accuracy, and timestamp.
Immutable: writes new config, does not mutate in place.
"""
```

Key behavior:
- Read current `config/models.yaml`
- Add/update `distilled_tasks.{task_type}` entry with model, accuracy, deployed_at
- Write updated config (new file, atomic rename)
- Update `config/distillation_config.yaml` with deployment record
- Return `DeploymentResult` with before/after routing state

- [ ] **Step 8: Create distillation_config.yaml**

```yaml
# config/distillation_config.yaml
# Per-task routing map — updated by deployer.py
tasks:
  task_classification:
    status: pending  # pending | compiled | deployed | reverted
    min_examples: 200
    accuracy_threshold: 0.90
    consecutive_passes: 0  # increment on each successful evaluation
    deployed_at: null
    pipeline_version: null
```

- [ ] **Step 9: Write evaluator + deployer tests**

- Evaluator: test accuracy calculation, threshold logic, per-class metrics
- Deployer: test config file updates (immutable write), atomic rename, rollback on failure
- Test that deployer refuses to deploy when accuracy < 90%

### Task 4: Integration test

**Files:**
- Create: `tests/test_integration_distillation.py`

- [ ] **Step 10: Write E2E distillation integration test**

Test the full pipeline with mocked LMs:
1. Collector extracts examples from prompt_logger (synthetic rows)
2. Compiler runs BootstrapFewShot (mocked teacher/student)
3. Evaluator tests on held-out set
4. Deployer updates models.yaml (when accuracy >= 90%)
5. Verify models.yaml has correct routing entry

Also test the failure path: accuracy < 90% → deployer does NOT update config.

- [ ] **Step 11: Run pyright + tests for Chunk 1**

```bash
pyright augments/distillation/ tests/augments/test_collector.py tests/augments/test_compiler.py tests/augments/test_evaluator.py tests/augments/test_deployer.py tests/test_integration_distillation.py
pytest tests/augments/test_collector.py tests/augments/test_compiler.py tests/augments/test_evaluator.py tests/augments/test_deployer.py tests/test_integration_distillation.py -v --tb=short
```

---

## Chunk 2: Code Workflow — Self-Building

> **Prerequisite:** Chunk 1 complete (distillation pipeline proven). OpenSpace capturer + generator from Gate 2 working.
> **Spec reference:** §15

### Task 1: Tier classifier + promoter

**Files:**
- Create: `augments/selfbuild/__init__.py`
- Create: `augments/selfbuild/tier_classifier.py`
- Create: `augments/selfbuild/promoter.py`
- Create: `tests/augments/test_tier_classifier.py`
- Create: `tests/augments/test_promoter.py`

- [ ] **Step 1: Create selfbuild package init**

- [ ] **Step 2: Write tier_classifier.py**

```python
"""Classify generated artifacts as Tier 1 (auto-promote) or Tier 2 (human-approve).

Tier 1: Pipeline collapses from OpenSpace CAPTURED — no external side effects.
Tier 2: New atomic tools, tools with network/filesystem side effects, client-facing tools.
"""
```

Key behavior:
- Input: generated artifact (script path, manifest path, test path)
- Check if artifact is a pipeline collapse (origin == "openspace_captured") → Tier 1
- Check manifest for side effects: `side_effects` field, network calls, file writes outside output/ → Tier 2
- Check if tool interacts with delivery channels → Tier 2
- Return `TierDecision` dataclass with tier, reasons, artifact_paths

- [ ] **Step 3: Write promoter.py**

```python
"""Promote Tier 1 artifacts automatically, hold Tier 2 for human review.

Tier 1 flow: safety check → quality gate on sample → test execution → promote to _registry.yaml
Tier 2 flow: safety check → move to _drafts/ → notify human via Telegram
"""
```

Key behavior:
- Tier 1: call `safety.check_skill_safety()` → run quality gate on sample input → execute test file → if all pass, call `manifest_syncer` to register
- Tier 2: call `safety.check_skill_safety()` → copy to `_drafts/` → call notifier
- Return `PromotionResult` with status (promoted/held/rejected), reasons

- [ ] **Step 4: Write tier classifier + promoter tests**

- Tier classifier: test pipeline collapse → Tier 1, new atomic tool → Tier 2, delivery tool → Tier 2
- Promoter: test Tier 1 happy path (all checks pass → promoted), Tier 1 safety fail → rejected, Tier 2 → held + notified

### Task 2: Notifier + vizier-code toolset

**Files:**
- Create: `augments/selfbuild/notifier.py`
- Create: `manifests/code/aider_edit.yaml`, `manifests/code/git_commit.yaml`
- Modify: `config/toolsets.py`, `config/SOUL.md`
- Create: `tests/augments/test_notifier.py`

- [ ] **Step 5: Write notifier.py**

```python
"""Send Telegram notification for Tier 2 human approval.

Includes: artifact type, file paths, diff summary, approve/reject prompt.
Uses existing scripts/delivery/send_telegram.py.
"""
```

- [ ] **Step 6: Create vizier-code manifests**

Create `manifests/code/aider_edit.yaml` and `manifests/code/git_commit.yaml` following existing manifest conventions.

- [ ] **Step 7: Update config/toolsets.py — add vizier-code**

Add `"vizier-code"` to `VIZIER_WORKFLOW_TOOLSETS`.

- [ ] **Step 8: Update SOUL.md — add self-building rules**

Add to `config/SOUL.md`:
- "New files: use execute_code. Edit existing files: use aider_edit."
- "Pipeline collapses auto-promote. New atomic tools require human approval."
- "Never import LLM SDKs inside pipeline code."

- [ ] **Step 9: Write notifier tests**

- Test message formatting
- Test Telegram API call (mocked)

### Task 3: Integration test

**Files:**
- Create: `tests/test_integration_selfbuild.py`

- [ ] **Step 10: Write E2E self-building integration test**

Test full flow:
1. OpenSpace capturer detects repeating pattern
2. Generator creates pipeline draft in `_drafts/`
3. Tier classifier → Tier 1 (pipeline collapse)
4. Promoter: safety + quality gate + test → promote
5. Verify artifact in `_registry.yaml`

Also test Tier 2 path: new atomic tool → held → notifier called.

- [ ] **Step 11: Run pyright + tests for Chunk 2**

```bash
pyright augments/selfbuild/ tests/augments/test_tier_classifier.py tests/augments/test_promoter.py tests/augments/test_notifier.py tests/test_integration_selfbuild.py
pytest tests/augments/test_tier_classifier.py tests/augments/test_promoter.py tests/augments/test_notifier.py tests/test_integration_selfbuild.py -v --tb=short
```

---

## Chunk 3: execute_code Sandbox Extensions

> **Prerequisite:** Chunk 2 complete (self-building needs sandbox for safe code generation).
> **Spec reference:** §16

### Task 1: AST guard

**Files:**
- Create: `augments/sandbox/__init__.py`
- Create: `augments/sandbox/guard.py`
- Create: `tests/augments/test_guard.py`

- [ ] **Step 1: Create sandbox package init**

- [ ] **Step 2: Write guard.py**

```python
"""Pre-execution AST scan for blocked patterns in execute_code input.

Blocks: os.system, subprocess, eval/exec, LLM API imports, filesystem
writes outside output/ and tmp/.
Reuses pattern detection from augments/openspace/safety.py where applicable.
"""
```

Key behavior:
- Parse code string to AST
- Walk AST checking for:
  - `import subprocess`, `import os` + `os.system`/`os.exec*` calls
  - `eval()`, `exec()` builtins
  - `import openai`, `import anthropic` (no LLM in execute_code)
  - `open()` calls with paths outside `output/` and `tmp/`
  - Network calls to non-allowed endpoints
- Return `GuardResult`: allowed (bool), blocked_patterns (list), error_message (str)
- Clear error messages: "Blocked: subprocess.run() — use the ffmpeg_process tool instead"

- [ ] **Step 3: Write guard tests**

- Test each blocked pattern individually
- Test that safe code passes
- Test complex AST (nested functions, decorators, comprehensions)
- Test edge cases: dynamic imports (`__import__`), importlib

### Task 2: Audit logger + Hermes plugin

**Files:**
- Create: `augments/sandbox/audit.py`
- Create: `plugins/sandbox_plugin.py`
- Create: `tests/augments/test_audit.py`

- [ ] **Step 4: Write audit.py**

```python
"""Post-execution logging for execute_code.

Records: code executed (hash + first 500 chars), files touched,
network calls made, execution duration, exit code.
Writes to SQLite (same DB as prompt_logger for correlation).
"""
```

- [ ] **Step 5: Write sandbox_plugin.py**

```python
"""Hermes plugin: pre_tool_call guard + post_tool_call audit on execute_code.

Hooks into Hermes lifecycle:
- pre_tool_call: run guard.check() on code argument. If blocked, return error.
- post_tool_call: run audit.record() with execution results.
Only applies to execute_code tool (skip other tools).
"""
```

- [ ] **Step 6: Write audit + plugin tests**

- Audit: test SQLite record creation, test field population
- Plugin: test that guard blocks bad code before execution, test that audit records after execution

### Task 3: Integration test

**Files:**
- Create: `tests/test_integration_sandbox.py`

- [ ] **Step 7: Write E2E sandbox integration test**

1. Execute safe code → guard passes → audit records
2. Execute blocked code (subprocess) → guard rejects → audit records rejection
3. Execute code that writes to output/ → guard passes
4. Execute code that writes to /etc/ → guard rejects

- [ ] **Step 8: Run pyright + tests for Chunk 3**

```bash
pyright augments/sandbox/ plugins/sandbox_plugin.py tests/augments/test_guard.py tests/augments/test_audit.py tests/test_integration_sandbox.py
pytest tests/augments/test_guard.py tests/augments/test_audit.py tests/test_integration_sandbox.py -v --tb=short
```

---

## Chunk 4: Data-Driven Triggers

> **Prerequisite:** Chunk 3 complete (sandbox needed for safe file processing).
> **Spec reference:** §17

### Task 1: File trigger + config

**Files:**
- Create: `scripts/triggers/__init__.py`
- Create: `scripts/triggers/data_trigger.py`
- Create: `config/triggers/filename_rules.yaml`
- Create: `tests/scripts/test_data_trigger.py`

- [ ] **Step 1: Create triggers package init**

- [ ] **Step 2: Create filename_rules.yaml**

```yaml
# config/triggers/filename_rules.yaml
# Filename prefix → toolset + pipeline mapping
rules:
  - prefix: "posters_"
    toolset: vizier-visual
    pipeline: poster_batch
  - prefix: "invoices_"
    toolset: vizier-document
    pipeline: null  # model decides
  - prefix: "content_calendar_"
    toolset: vizier-content
    pipeline: content_generate
  - prefix: "analysis_"
    toolset: vizier-research
    pipeline: competitive_analysis

fallback:
  toolset: vizier-fallback
  pipeline: null  # pre-classifier on first row
```

- [ ] **Step 3: Write data_trigger.py**

```python
"""Watch uploads/ directory for new files, classify, and start Hermes sessions.

Polls uploads/ every 30 seconds. On new file:
1. Validate format (CSV, JSON, XLSX)
2. Detect schema (column names, types)
3. Classify by filename convention (config/triggers/filename_rules.yaml)
4. Fallback: pre-classifier on first row of data
5. Start Hermes session with toolset + file path + schema as prompt
6. Move processed file to uploads/_processed/{timestamp}_{filename}
"""
```

Key behavior:
- Poll `uploads/` directory (ignore `_processed/` subdirectory)
- Validate file format: CSV via csv.Sniffer, JSON via json.load, XLSX via openpyxl
- Match filename against rules from YAML config
- If no match: extract first row, pass to pre-classifier (Qwen)
- Start Hermes session via subprocess: `hermes --toolset {toolset} --prompt "Process: {path}. Schema: {schema}"`
- On completion: move file to `uploads/_processed/`
- On failure: move to `uploads/_failed/` with error log
- health_check cron (Gate 2) handles cleanup of `_processed/` older than 7 days

- [ ] **Step 4: Write trigger tests**

- Test filename matching against rules
- Test format validation (valid CSV, invalid file, empty file)
- Test schema detection
- Test file move after processing (mocked Hermes session)
- Test fallback classification path
- Test concurrent file handling (2 files appear simultaneously)

### Task 2: Integration test

**Files:**
- Create: `tests/test_integration_triggers.py`

- [ ] **Step 5: Write E2E trigger integration test**

1. Place a `posters_test.csv` in `uploads/`
2. data_trigger detects, classifies as vizier-visual + poster_batch
3. Hermes session starts (mocked)
4. File moves to `uploads/_processed/`
5. Verify no file left in `uploads/`

Also test failure path: invalid CSV → `uploads/_failed/`.

- [ ] **Step 6: Run pyright + tests for Chunk 4**

```bash
pyright scripts/triggers/ tests/scripts/test_data_trigger.py tests/test_integration_triggers.py
pytest tests/scripts/test_data_trigger.py tests/test_integration_triggers.py -v --tb=short
```

---

## Exit Criteria — Gate 3 "Builds Itself"

- [ ] **Chunk 0:** 200+ session exemplars in prompt_logger (synthetic + any real). Quality gate calibration accuracy >= 90% on test fixtures. Threshold adjustments applied if needed.
- [ ] **Chunk 1:** DSPy distillation — at least 1 task type (task_classification) compiled and deployed to Qwen at 90%+ accuracy on held-out set.
- [ ] **Chunk 2:** Self-building — Vizier generated and auto-promoted at least 1 pipeline collapse. Tier 2 hold + Telegram notification working.
- [ ] **Chunk 3:** execute_code sandbox — AST guard blocks all prohibited patterns. Audit trail in SQLite for every execute_code call.
- [ ] **Chunk 4:** Data triggers — CSV upload to `uploads/` triggers batch processing and delivery.
- [ ] Offline mode functional: Qwen handles distilled tasks without API calls.
- [ ] All new code passes `pyright` strict mode.
- [ ] Test coverage >= 80% on all new modules.
- [ ] Revenue rule: Gate 2 has produced billable output before Gate 3 work begins.
