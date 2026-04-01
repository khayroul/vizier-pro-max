# Gate 3 Final Wiring — Production Bridge + Real Distillation + Hermes Integration

Complete the 3 remaining Gate 3 exit criteria. All Gate 3 code is written and tested (180 unit tests, 51 acceptance tests, 100% coverage). What's missing is wiring it to real infrastructure.

**Read these files first:**
1. `CLAUDE.md` — project conventions
2. `tests/test_acceptance_gate3.py` — the known-answer tests (your north star)
3. `augments/distillation/collector.py` — reads from `data/prompt_log.db` table `training_sessions`
4. `augments/distillation/compiler.py` — DSPy compilation, teacher=GPT-5.4-mini, student=Qwen
5. `augments/distillation/evaluator.py` — accuracy comparison
6. `augments/distillation/deployer.py` — updates `config/models.yaml`
7. `scripts/triggers/data_trigger.py` — `_start_hermes_session()` is a logging stub (line 229)

**Environment:** `OPENAI_API_KEY` is in `.env`. Load it with `source .env` or `set -a; source .env; set +a` before running anything that needs the API. Ollama is running locally with `qwen3.5:9b` at `http://localhost:11434`.

---

## Task 1: Production bridge (ETL from Hermes state.db → training_sessions)

The Hermes database lives at `~/.hermes/state.db` with this schema:
- `sessions` table: id, source, model, started_at, ended_at, tool_call_count, input_tokens, output_tokens, title, ...
- `messages` table: id, session_id, role, content, tool_call_id, tool_calls, tool_name, timestamp, ...

The DSPy collector reads from `data/prompt_log.db` table `training_sessions`:
- Schema: session_id, timestamp, input_message, task_type, toolset_chosen, pipeline_used, tool_calls, success, synthetic

**Create `scripts/bridge/sync_hermes_sessions.py`** that:
1. Reads sessions + messages from `~/.hermes/state.db`
2. For each session: extracts the first user message as `input_message`, collects tool_name from messages as `tool_calls`
3. Classifies task_type using the existing Qwen pre-classifier (or simple heuristic: map toolset from session tools to task_type)
4. Determines `toolset_chosen` from the tools used in the session
5. Marks `success=1` if session has `end_reason='completed'` or similar
6. Marks `synthetic=0` (these are real sessions)
7. Inserts into `data/prompt_log.db` table `training_sessions`
8. Idempotent: skip sessions already synced (check by session_id)
9. Runnable as: `python3 -m scripts.bridge.sync_hermes_sessions`

**Also create `scripts/bridge/__init__.py`** and **`tests/scripts/test_sync_hermes.py`**.

Write test first. Test with a mock state.db (create temp SQLite with Hermes schema, insert fake sessions + messages, run sync, verify training_sessions populated correctly).

---

## Task 2: Wire _start_hermes_session to real Hermes CLI

Replace the logging stub in `scripts/triggers/data_trigger.py` line 229 (`_start_hermes_session`) with actual Hermes invocation.

Check how Hermes is invoked by reading `hermes-agent/` — look for CLI entry point, how `--toolset` and `--prompt` args work. Then:
1. Build the subprocess command: `python3 -m hermes_agent` or whatever the real entry point is
2. Pass toolset, pipeline, file_path, and schema as prompt context
3. Set timeout (5 minutes for batch processing)
4. Capture stdout/stderr, return result
5. Load `.env` before subprocess if needed (pass env dict)

**Keep the logging stub available** — add a `dry_run` parameter (default False) that logs instead of executing. Tests should use `dry_run=True`.

Write test first. The acceptance test `TestFileTriggerRoundTrip` should still pass (it doesn't mock `_start_hermes_session` — update it if needed to use dry_run).

---

## Task 3: Run real DSPy distillation

This is NOT a code task — it's a run-and-verify task. Do it AFTER Tasks 1 and 2.

### Step 1: Bootstrap training data
```bash
source .env
python3 -m scripts.bootstrap.generate_synthetic_sessions
# Verify: python3 -c "import sqlite3; db=sqlite3.connect('data/prompt_log.db'); print(db.execute('SELECT COUNT(*) FROM training_sessions').fetchone())"
```

### Step 2: Sync any real Hermes sessions
```bash
python3 -m scripts.bridge.sync_hermes_sessions
```

### Step 3: Run distillation for task_classification
```python
from augments.distillation.collector import collect
from augments.distillation.compiler import compile_program
from augments.distillation.evaluator import evaluate
from augments.distillation.deployer import deploy

# Collect
result = collect("task_classification")
print(f"Collected {result.total_count} examples ({len(result.train_set)} train, {len(result.test_set)} test)")

# Compile (this hits GPT-5.4-mini as teacher + Qwen as student)
compiled = compile_program(result.train_set, "task_classification")
print(f"Compiled: {compiled.num_bootstrapped} bootstrapped examples in {compiled.duration_seconds:.1f}s")

# Evaluate
test_data = [{"input_text": e.input_text, "expected_output": e.expected_output} for e in result.test_set]
report = evaluate(compiled.program_path, test_data, "task_classification")
print(f"Accuracy: {report.accuracy:.1%} — Recommendation: {report.recommendation}")

# Deploy if >= 90%
if report.recommendation == "deploy":
    deploy_result = deploy("task_classification", report.accuracy, compiled.program_path)
    print(f"Deployed: {deploy_result.status}")
else:
    print(f"Accuracy {report.accuracy:.1%} < 90% — not deploying. Review results.")
```

### Step 4: Verify distillation result
- If accuracy >= 90%: check `config/models.yaml` has `distilled_tasks.task_classification`
- If accuracy < 90%: report the actual accuracy and what went wrong. Do NOT force deploy.

### Step 5: Test offline mode
If deployed, temporarily set `offline_mode: true` in `config/models.yaml` and verify the collector + evaluator still work with Qwen-only inference.

---

## Rules
- TDD: write test first, run RED, implement, run GREEN
- `pyright` on every new file
- No mocks for Task 3 — that's the whole point
- Source `.env` before any command that needs OPENAI_API_KEY
- Do NOT modify existing Gate 1/2 code unless required for wiring
- Commit after each task with conventional commit format

## Exit criteria for this session
- [ ] `scripts/bridge/sync_hermes_sessions.py` working + tested
- [ ] `_start_hermes_session()` wired to real Hermes (with dry_run fallback)
- [ ] DSPy distillation ran for real on task_classification
- [ ] Accuracy result recorded (pass or fail — honest number)
- [ ] If >= 90%: `config/models.yaml` updated with distilled task
- [ ] All existing tests still pass (run `pytest tests/test_acceptance_gate3.py -v`)
