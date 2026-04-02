# Vizier Pro-Max — Wave 1 & 2 Execution Prompt

Copy everything below the line into a new Claude Code session launched from `~/vizier-pro-max/`.

---

## Prompt

I'm building Vizier Pro-Max. Task 1 (project scaffold) is complete. The plan is at `docs/superpowers/plans/2026-04-01-gate-1-implementation.md` and the spec is at `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`.

I need you to execute the remaining Gate 1 tasks in parallel waves. Activate `.venv` first: `source .venv/bin/activate`.

### Wave 1 — Run these 4 agents in parallel (no dependencies between them)

**Agent A: Adapter chain (Tasks 2 → 3 → 4 — sequential within agent)**
- Task 2: `adapter/schemas.py` — manifest Pydantic models, YAML → OpenAI tool dict
- Task 3: `adapter/executor.py` — execute tools (CLI, python_script, python_function) with timeout/retry
- Task 4: `adapter/loader.py` — glob manifests, register into Hermes via `registry.register()`
- Follow TDD: write test → verify fail → implement → verify pass → pyright → commit each task

**Agent B: Logger chain (Tasks 5 → 6 — sequential within agent)**
- Task 5: `plugins/prompt_logger.py` — Hermes lifecycle hooks (pre/post LLM call), SQLite capture
- Task 6: `tools/query_logs.py` — model-callable tool to inspect prompt_log table
- Follow TDD for each. Commit separately.

**Agent C: Quality gate (Task 8)**
- Task 8: `middleware/quality_gate.py` — Layers 1-2: input validation + output verification
- ValidationResult dataclass, validate_input(), validate_output(), validate() dispatcher
- Follow TDD. Commit when done.

**Agent D: Config (Task 12)**
- Task 12: Create `config/SOUL.md` (Vizier persona + tool-layer priority rules) and `config/hermes.yaml`
- Symlink SOUL.md: `ln -sf ~/vizier-pro-max/config/SOUL.md ~/.hermes/SOUL.md`
- Commit when done.

### Wave 2 — Run these 4 agents in parallel (after Wave 1 completes)

**Agent E: run_pipeline (Task 7)**
- Task 7: `tools/run_pipeline.py` — execute or list collapsed pipelines by name
- Needs: `pipelines/_registry.yaml` (create it)
- Follow TDD. Commit when done.

**Agent F: Content pipeline (Task 9)**
- Task 9: `pipelines/content_generate.py` — brief → RAG → copy pipeline (Gate 1 stub with input validation)
- Needs: `middleware/quality_gate.py` from Wave 1
- Follow TDD. Commit when done.

**Agent G: Manifests + scripts (Task 10)**
- Task 10: Create 4 YAML manifests + 3 wrapper scripts:
  - `manifests/content/httpx_fetch.yaml` + `scripts/content/fetch_url.py`
  - `manifests/content/jinja2_render.yaml` + `scripts/content/render_template.py`
  - `manifests/content/lightrag_search.yaml` + `scripts/content/search_rag.py` (stub)
  - `manifests/document/typst_render.yaml` (CLI type, no script needed)
- Write integration test `tests/adapter/test_manifest_integration.py` to verify loading
- Commit when done.

**Agent H: Bridge (Task 11)**
- Task 11: Cherry-pick from `~/vizier-ultimate/vizier/adapter/`:
  - `git_watcher.py` → `bridge/git_watcher.py` (adapt `_STATE_FILE` path to `~/.vizier-pro-max/`)
  - `skill_syncer.py` → `bridge/skill_syncer.py` (no changes needed)
  - `test_parser.py` → `bridge/test_parser.py` (no changes needed)
- Build NEW: `bridge/manifest_syncer.py` (watch manifests/ for new YAML files)
- Build NEW: `bridge/watcher.py` (entry point running all bridge components)
- Cherry-pick tests from `~/vizier-ultimate/tests/vizier/adapter/`, adapt imports from `vizier.adapter.X` → `bridge.X`
- Commit when done.

### Wave 3 — After Wave 2 completes

**Task 13: Integration test** — `tests/test_integration.py`
- End-to-end: manifests load → pipeline executes → quality gate validates
- Run full test suite: `pytest tests/ -v --cov`
- Target 80%+ coverage

### Key references
- Hermes registry API: `~/hermes-agent/tools/registry.py` — `registry.register(name, toolset, schema, handler, check_fn, ...)`
- Handler signature: `lambda args, **kw: ...` (Hermes passes task_id, parent_agent etc in kwargs)
- All code in plan has exact implementations. Follow them but fix any issues you find.
- Run `pyright <file>` and `ruff check <file>` after every implementation.
- Each task gets its own commit with conventional commit format.
