# Gate 3 Execution Prompt

Use this prompt to start a Gate 3 implementation session.

---

You are implementing Gate 3 ("Builds Itself") for the Vizier Pro-Max project.

**Gate 1 and Gate 2 are fully operational.** Do not modify existing Gate 1/2 code unless the implementation plan explicitly says to.

**Spec:** `docs/superpowers/specs/2026-04-01-gate-2-3-design.md` (sections 14-17, plus Section 2.3 for the 1MB output cap)
**Implementation Plan:** `docs/superpowers/plans/2026-04-01-gate-3-implementation.md`
**Parent Spec:** `docs/superpowers/specs/2026-04-01-vizier-pro-max-design.md`
**CLAUDE.md:** Read it first for project conventions.

**Gate 3 scope (4 components + 1 hardening fix):**

0. **Executor Output Cap** (Spec Section 2.3)
   - Add 1MB cap on subprocess stdout/stderr in `adapter/executor.py`
   - Only remaining Gate 1 hardening fix. Do this first.

1. **DSPy Distillation Pipeline** (Spec Section 14)
   - `augments/distillation/` — collector.py, compiler.py, evaluator.py, deployer.py
   - Collect 200+ examples from prompt_logger SQLite
   - Compile DSPy programs (teacher: GPT-5.4-mini, student: Qwen 3.5 9B via Ollama)
   - Deploy when accuracy >= 90%, update `config/models.yaml`
   - Start with task classification, add template selection + tool routing incrementally
   - Depends on pre-classifier having accumulated enough session data

2. **Code Workflow — Self-Building** (Spec Section 15)
   - Tiered autonomy: auto-promote pipeline collapses (Tier 1), human-approve new atomic tools (Tier 2)
   - safety.py: validate self-built pipelines use `llm_chat()` (shared Hermes proxy), not direct SDK imports
   - vizier-code toolset: `manifests/code/` + `scripts/code/` (aider_edit, git_commit)
   - Promotion: `_drafts/` -> safety check -> quality gate -> manifest_syncer -> active

3. **execute_code Sandbox Extensions** (Spec Section 16)
   - Hermes plugin (`pre_tool_call` hook on execute_code, `post_tool_call` for audit)
   - `augments/sandbox/guard.py` — AST scan for blocked patterns (21+ already in safety.py)
   - `augments/sandbox/audit.py` — post-execution logging to SQLite
   - Permissive imports, restricted filesystem (output/ + tmp/ only), restricted network

4. **Data-Driven Triggers** (Spec Section 17)
   - `scripts/triggers/data_trigger.py` — polls uploads/ every 30s
   - Filename convention for auto-classification (posters_*.csv -> vizier-visual)
   - Processed files -> `uploads/_processed/`, 7-day cleanup via health_check cron

**Critical rules:**
- Pipelines MAY include LLM calls when self-contained (brief->deliverable). This is validated production behavior.
- Self-built pipelines must use `llm_chat()` (Hermes proxy), not direct openai/anthropic imports. safety.py enforces this.
- Hermes hooks are synchronous (no async/await). Keep `post_tool_call` hooks < 10ms. `on_session_end` can take 2-5s.
- `delegate_task` accepts `toolsets` parameter (verified in Hermes source). Children inherit parent's toolsets (intersection).
- Use the writing-plans skill before implementation if no plan file exists yet.
- Follow TDD: write tests first, then implement.
- pyright strict mode + 80% test coverage on all new modules.
- Do NOT modify existing Gate 1/2 files unless the plan says to. Check git blame before changing any file.

**Exit criteria (Spec Section 18):**
- [ ] 1MB output cap added to executor.py
- [ ] DSPy: at least 1 task type on Qwen at 90%+ accuracy
- [ ] Code workflow: at least 1 self-generated pipeline promoted
- [ ] Tiered autonomy: auto-promote for collapses, human-approve for new tools
- [ ] execute_code sandbox: guard + audit active on execute_code
- [ ] Data triggers: CSV upload -> batch processing -> delivery working
- [ ] Offline mode: Vizier functional (degraded) with Ollama only
- [ ] All new code passes pyright strict mode
- [ ] Test coverage >= 80% on all new modules
