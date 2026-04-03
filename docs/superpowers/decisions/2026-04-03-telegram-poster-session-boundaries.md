# Telegram Poster Session Boundaries

## Context and trigger

Telegram mode routing existed, and first-pass poster generation existed, but poster feedback turns still behaved too loosely. Sample/reference posters sent through Telegram needed to remain session-safe, revision turns needed an explicit change plan instead of casual regeneration, and the front door needed calmer user-facing behavior.

This decision was triggered by Commit 4 scope for the Telegram front door: add session boundaries, Telegram poster/sample intake, session-scoped poster state, structured poster revision flow, cleaner UX, and a lightweight self-check.

## Decision taken

We keep Hermes as the only runtime and implement the poster feedback loop at the Hermes gateway/session boundary rather than introducing any parallel runtime.

The Telegram poster flow now:

- stores poster-review state per Telegram gateway session boundary
- accepts Telegram `photo` and image `document` poster references for `png`, `jpg`, and `jpeg`
- treats a newly received supported sample image as the active reference for that same session
- exposes `revise_poster` for Telegram revision work only when there is already a poster session to revise
- compiles revision feedback into explicit change goals plus preservation goals before regenerating
- returns a lightweight `self_check` and requires softer user-facing claims unless every requested goal is clearly addressed
- keeps critique-only poster turns assistant-oriented unless the user is clearly asking for changes
- keeps Hermes tool-progress chatter out of the normal Telegram poster/reference/revision flow

## Prior work or subsystem being preserved

- Hermes remains the only runtime and continues to own Telegram gateway execution.
- Existing `generate_poster` callers remain valid.
- Telegram routing boundaries remain intact:
  - `assistant` for support/advice/planning/drafting
  - `vizier_work` for deliverables and production workflows
  - `operator` for repo/system/debug work
- UI UX Pro Max, Vega-Lite, and Quarto remain pinned local reference corpora only, not runtimes.

## Invariants that must remain true

- Hermes is still the only runtime.
- Poster reference and revision state must stay isolated per Telegram session boundary with no cross-session bleed.
- A newly received supported sample poster image supersedes the previous active reference for that session.
- `revise_poster` must not appear on Telegram before a poster exists to revise.
- Critique-only poster turns can remain assistant-oriented unless the user explicitly asks for a change.
- Telegram poster-reference support in this loop is limited to `png`, `jpg`, and `jpeg`.

## Validation or tests

- `tests/pipelines/test_poster_generate.py`
- `tests/plugins/test_telegram_mode_router.py`
- `tests/plugins/test_vizier_tools_project_plugin.py`
- `tests/plugins/test_telegram_tool_policy.py`
- `hermes-agent/tests/gateway/test_telegram_documents.py`
- `hermes-agent/tests/gateway/test_telegram_photo_interrupts.py`
- `hermes-agent/tests/gateway/test_telegram_poster_feedback.py`
- `hermes-agent/tests/test_telegram_tool_surface_lifecycle.py`

## Follow-up work

- Commit 5 memory separation should decide what, if anything, graduates from session-only poster state into longer-lived memory.
- Commit 6 ambiguity policy should keep sample/reference-only turns deliberate when the user has not yet asked for generation or revision.
- Commit 7 eval should add poster-feedback-loop probes that measure whether revisions actually improved instead of merely changed.
