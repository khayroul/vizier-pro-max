# Telegram Poster Session Boundaries

## Context and trigger

Telegram mode routing existed, and first-pass poster generation existed, but poster feedback turns still behaved like loose regeneration. Sample/reference posters sent through Telegram were not session-safe, Telegram image documents were not part of the clean poster flow, and revision replies could over-claim success without a grounded change list.

This decision was triggered by Commit 4 scope for the Telegram front door: add session boundaries, Telegram poster/sample intake, session-scoped poster state, structured poster revision flow, cleaner UX, and a lightweight self-check.

## Decision taken

We keep Hermes as the only runtime and add a project-local Telegram poster session layer that:

- stores poster state per `HERMES_SESSION_KEY`
- treats Telegram PNG/JPG/JPEG photos and image documents as supported poster reference inputs
- automatically reuses the latest session reference image for poster work when `reference_image_path` is omitted
- exposes a dedicated `revise_poster` tool that only appears once a session already has a tracked poster
- compiles revision feedback into explicit change goals and preservation goals before regenerating
- returns a lightweight self-check checklist and softens Telegram success claims accordingly
- defaults the Telegram launcher to `HERMES_TOOL_PROGRESS_MODE=off` so internal tool chatter stays out of the user-facing flow

## Prior work or subsystem being preserved

- Hermes remains the only runtime and continues to own Telegram gateway execution.
- Existing `generate_poster` callers remain valid.
- Telegram mode routing boundaries remain intact:
  - `assistant` for support/advice/planning/drafting
  - `vizier_work` for deliverables and production workflows
  - `operator` for repo/system/debug work
- Existing Hermes document support remains available; the new poster session layer only narrows poster-reference guidance, not the underlying document runtime.

## Invariants that must remain true

- Hermes is still the only runtime.
- UI UX Pro Max, Vega-Lite, and Quarto remain local reference corpora only.
- Poster reference/session state must stay isolated per Telegram session key with no cross-session bleed.
- A newly received supported poster sample supersedes the prior active reference for that same session.
- `revise_poster` must not appear before there is already a poster to revise.
- Telegram critique-only turns can remain assistant-oriented unless the user explicitly asks for changes.

## Validation or tests

- `tests/plugins/test_telegram_poster_session.py`
- `tests/plugins/test_telegram_mode_router.py`
- `tests/plugins/test_vizier_tools_project_plugin.py`
- `tests/pipelines/test_poster_revision.py`
- `tests/pipelines/test_poster_generate.py`
- `tests/scripts/test_run_hermes_telegram.py`
- `hermes-agent/tests/test_telegram_tool_surface_lifecycle.py`

## Follow-up work

- Commit 5 memory separation should decide what poster session data, if any, graduates into longer-lived memory versus staying session-only.
- Commit 6 ambiguity policy should make sample/reference-only turns even more deliberate when the user has not yet asked for creation or revision.
- Commit 7 eval should add Telegram poster feedback-loop quality probes, including “revision did not get worse” checks.
