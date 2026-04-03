# Decision: Poster Revision Tool Surface

Date: `2026-04-03`
Status: `accepted`

## Context and Trigger

- Poster generation was already exposed through `plugins/poster_tool.py`, but poster feedback still funneled through a single `revise_poster` entrypoint tied to session state.
- The Telegram/front-door layer needs a smaller, safer, structured sequence it can call directly:
  - `prepare_poster_revision`
  - `revise_poster_structured`
  - `check_poster_revision`
  - optional `resolve_brand_asset`
  - optional `summarize_poster_revision`
- Without a stable tool contract, the front door would keep improvising regeneration behavior and success messaging.

## Decision Taken

- Keep `generate_poster` unchanged for first-pass poster creation.
- Preserve legacy `revise_poster`, but treat it as a compatibility wrapper for existing session-bound callers.
- Expose new poster-layer Hermes tools with structured JSON payloads and compact Telegram-facing summaries:
  - `prepare_poster_revision`
  - `revise_poster_structured`
  - `check_poster_revision`
  - `resolve_brand_asset`
  - `summarize_poster_revision`
- Allow the new tools to accept either explicit caller state or session fallback state, while keeping availability limited to `vizier_work`.
- Keep brand asset resolution local-first and truth-preserving. Style references and text marks do not count as official logo assets.

## Prior Work Preserved

- Hermes remains the only runtime.
- Existing `generate_poster` callers continue to work.
- Existing session-scoped `revise_poster` remains available for older callers that still depend on it.
- Telegram session storage and routing stay outside this change.

## Invariants

- The poster layer must return structured outputs rather than vague prose.
- Telegram-facing summaries must stay compact and calm, and must not overclaim visual success.
- Official logo asset availability must be reported honestly.
- Tool exposure must not broaden outside `vizier_work`.
- The front door stays thin; revision planning and summary shaping belong in the poster layer.

## Validation and Tests

- `python3 -m pytest /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_revision.py /Users/Executor/vizier-pro-max/tests/plugins/test_poster_revision_tools.py /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_generate.py /Users/Executor/vizier-pro-max/tests/plugins/test_vizier_tools_project_plugin.py`

## Follow-up Work

- If the runtime later gains true image-logo placement inside revision execution, keep the public tool names and return fields stable.
- Telegram/front-door code should pass the structured payloads through instead of re-deriving summaries or goal status on its own.
