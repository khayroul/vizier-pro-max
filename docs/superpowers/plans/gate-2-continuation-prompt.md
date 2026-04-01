# Gate 2 Continuation Prompt

Copy everything below the line into a new Claude Code session.

---

I'm building Vizier Pro-Max. Gate 2 is in progress — Chunk 1 complete, Chunk 2 partially done.

**Read these files first:**
- Plan: `~/vizier-pro-max/docs/superpowers/plans/2026-04-02-gate-2-implementation.md`
- Spec: `~/vizier-pro-max/docs/superpowers/specs/2026-04-02-gate-2-design.md`
- Gate 1 plan (format reference): `~/vizier-pro-max/docs/superpowers/plans/2026-04-01-gate-1-implementation.md`

**Current state (150 tests passing):**

✅ Chunk 1 DONE (Tasks 1-4): Hermes patch applied (`~/hermes-agent/` branch `vizier-gate2-patch`), switch_toolset plugin working, integration tests passing.

✅ Task 5 DONE: playwright_screenshot (manifest + script + 4 tests)

**Resume from Task 6.** Execute Tasks 6-11 (rest of Chunk 2), then Chunk 3 (Tasks 12-17).

Use `superpowers:subagent-driven-development` skill to execute. Dispatch one subagent per task. Each task has full TDD code in the plan — give the subagent the exact code from the plan file.

**Key rules:**
- TDD strictly: test first → verify fail → implement → verify pass → pyright → ruff → commit
- `from __future__ import annotations` in ALL Python files
- Do NOT break existing tests (150 passing)
- Manifests use `type: python_function` with `entrypoint: "module.path:run"`
- All scripts export a `run(**kwargs)` function returning a dict
- Commit after each task

**After Chunk 3 is done (Task 17)**, stop and report. Chunk 4 (Tasks 18-27) has 6 abbreviated tasks (21-26) that need their steps expanded into full TDD code before execution — that's a separate session.
