# Gate 3 Execution Prompt

Copy-paste everything below the `---` line into a new Claude Code session.

---

Implement Gate 3 ("Builds Itself") for Vizier Pro-Max.

**Read these files first, in this order:**
1. `CLAUDE.md` — project conventions
2. `docs/superpowers/specs/2026-04-01-gate-2-3-design.md` — design spec (v3), focus on sections 2.3 and 14-17
3. `docs/superpowers/plans/2026-04-01-gate-3-implementation.md` — the implementation plan (5 chunks, 14 tasks)

**The implementation plan already exists.** Do NOT rewrite it. Use `superpowers:executing-plans` skill to execute it chunk by chunk. The plan has:
- Chunk 0: Prerequisites (synthetic session bootstrapping + quality gate calibration)
- Chunk 1: DSPy distillation pipeline (collector, compiler, evaluator, deployer)
- Chunk 2: Code workflow — self-building (tier classifier, promoter, notifier, vizier-code toolset)
- Chunk 3: execute_code sandbox extensions (AST guard, audit logger, Hermes plugin)
- Chunk 4: Data-driven triggers (file upload polling, classification, batch processing)

**Before starting Chunk 0**, do one pre-task not in the plan:
- Add 1MB output cap to `adapter/executor.py` subprocess capture (spec Section 2.3). Cap stdout/stderr at 1,048,576 bytes, truncate with `[TRUNCATED: output exceeded 1MB limit]` marker. Write test first. This is the only Gate 1/2 file you should modify.

**Gate 1 and Gate 2 are fully operational.** Do NOT modify existing Gate 1/2 code unless the plan explicitly says to. Check `git blame` before changing any file.

**Critical rules:**
- Pipelines MAY include LLM calls when self-contained. This is validated production behavior — do not "fix" this.
- Self-built pipelines must use `llm_chat()` (Hermes proxy), not direct openai/anthropic imports. `augments/openspace/safety.py` enforces this (already has 21 blocked patterns — extend, don't replace).
- Hermes hooks are synchronous (no async/await). `post_tool_call` hooks must be < 10ms. `on_session_end` can take 2-5s.
- TDD: write failing test, run it, implement, run it green, commit. Every task.
- `pyright` on every new file. 80%+ test coverage on all new modules.

**Exit criteria:**
- [ ] 1MB output cap on executor.py
- [ ] DSPy: at least 1 task type on Qwen at 90%+ accuracy
- [ ] Code workflow: at least 1 self-generated pipeline promoted
- [ ] Tiered autonomy: auto-promote for collapses, human-approve for new tools
- [ ] execute_code sandbox: guard + audit active
- [ ] Data triggers: CSV upload -> batch processing working
- [ ] Offline mode: Vizier functional (degraded) with Ollama only
- [ ] All new code passes pyright strict
- [ ] Test coverage >= 80% on all new modules
