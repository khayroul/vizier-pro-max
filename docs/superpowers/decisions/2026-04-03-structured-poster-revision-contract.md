# Decision: Structured Poster Revision Contract

Date: `2026-04-03`
Status: `accepted`

## Context

- Poster generation already existed in `pipelines/poster_generate.py`, but poster revision still behaved too much like a fresh regenerate.
- The repeated failure modes were specific and user-visible:
  - duplicate headline treatment surviving in decorative/background form
  - logo visibility requests relying on the image model instead of a real asset
  - cleaner revisions becoming emptier rather than more disciplined
  - targeted feedback discarding prior strengths too casually
  - revision flows overclaiming success without a meaningful self-check
- This change touches poster runtime behavior, quality-gate semantics, and caller-facing revision state, so it could be mistaken later for an accidental refactor unless it is recorded explicitly.

## Decision

- Introduce a structured poster revision contract in `pipelines/poster_revision.py` with explicit preparation, revision execution, and self-check phases.
- Compile feedback into machine-usable change goals and preserve goals instead of passing through loose prose only.
- Carry prior poster context forward into revision generation, including prior template, prior creative brief, prior trace data, and prior known strengths/failures when available.
- Extend `pipelines/poster_generate.py` compatibly with:
  - `logo_image_path` for explicit logo asset overlays
  - `revision_goals`
  - `preserve_goals`
  - `prior_poster_context`
- Add runtime trace fields that describe logo rendering mode, template/render metadata, and revision guardrails so callers can report what changed without bluffing certainty.
- Add a structured self-check that can return `passed`, `partial`, or `unresolved` per goal and stay explicit about what still needs human review.
- Do not change Telegram routing, Telegram state handling, or alternate runtimes as part of this decision.

## Preserved Behavior

- Hermes remains the only runtime.
- Existing structured callers of `generate_poster` continue to work without sending revision-specific inputs.
- Poster generation still supports `reference_image_path` and the existing client/style-reference theming flows.
- Text-mark branding remains available when no official logo asset exists; the system now records that limitation instead of pretending it is equivalent to an official logo render.

## Invariants

- Poster revision must remain upstream-improving, not downstream rejection-only.
- Revision must preserve prior strengths unless the new feedback explicitly challenges them.
- Official logo rendering must use a supplied asset overlay when available; the image model must not be relied on to invent or redraw logos.
- The revision engine must report limitations honestly when no official logo asset exists.
- Self-check output must be structured and safe for caller summaries, and must not imply stronger certainty than the runtime can support.
- Existing non-revision poster generation must remain backward compatible.

## Validation

- `python3 -m pytest /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_generate.py /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_revision.py /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_client_integration.py /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_templates.py`
- Coverage added for:
  - structured goal compilation
  - preserve-goal derivation
  - prior-trace-aware revision preparation
  - `reference_image_path` preservation through revision
  - `logo_image_path` asset overlays
  - honest no-logo-asset limitations
  - structured self-check result shape
  - revision guardrail prompt assembly
  - compatibility for existing poster generation callers

## Follow-up

- Plugin/tool exposure for `logo_image_path` can be handled separately without changing the runtime contract introduced here.
- The current self-check is intentionally conservative; visual/manual review is still required for composition quality, exact logo prominence, and final mobile readability.
- If future packets add stronger visual verification, they should extend the structured self-check rather than replacing it with a boolean success claim.
