# Telegram Poster Feedback Loop

Current Commit 4 behavior for Telegram poster work:

- Supported reference inputs:
  - Telegram `photo`
  - Telegram image `document`
  - File types: `png`, `jpg`, `jpeg`
- Not supported in this loop yet:
  - `pdf`
  - `heic`
  - multi-page documents
  - permanent asset archival

Session-scoped poster state is keyed to the active Hermes gateway session boundary for that chat:

- latest generated poster path
- latest poster trace path
- latest reference/sample poster image path
- latest poster brief summary
- latest feedback note

Practical revision flow:

1. User generates a poster.
2. Hermes stores the latest poster artifact + trace for that Telegram session.
3. User can send a reference image in the same chat; it replaces the active session reference image.
4. User can send feedback like logo visibility, duplicate headline, or layout cleanup.
5. Hermes routes that turn into `vizier_work`, prefers `revise_poster`, and passes the latest poster/reference state into the turn.
6. `revise_poster` compiles explicit change goals, preserves prior strengths, and reuses the previous hero image when safe instead of regenerating loosely.

User-facing Telegram behavior:

- Image-only reference turns are acknowledged directly and stored quietly.
- Poster revision turns should summarize planned deltas briefly before revising.
- Post-revision responses should summarize what changed and avoid claiming "Fixed" unless the revision self-check fully supports it.

Known limitation for the next packet:

- Poster session state is current-session only. It is not reconstructed from older resumed sessions or permanent asset libraries yet.
