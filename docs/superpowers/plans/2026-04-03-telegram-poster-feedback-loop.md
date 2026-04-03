# Telegram Poster Feedback Loop

## Supported Telegram poster inputs

Telegram poster/sample intake now supports:

- `photo`
- image `document`

Accepted v1 poster reference formats:

- `png`
- `jpg`
- `jpeg`

Still not supported as poster references in this flow:

- `pdf`
- `heic`
- multi-page documents

## Session-scoped poster state

Poster state is stored per `HERMES_SESSION_KEY` under Hermes home so it stays isolated per Telegram chat/session.

Tracked fields:

- latest generated poster path
- latest generated poster trace path
- latest generated poster tool args/result
- latest active reference/sample poster image path
- latest brief text when available
- latest feedback note
- latest revision plan snapshot

A newly received supported sample image replaces the prior active reference image for that same session.

## Feedback and revision flow

Telegram feedback turns no longer rely on a loose `generate_poster` rerun. When a session already has a poster:

1. Telegram feedback is compiled into explicit revision goals.
2. Prior poster state is reused so the revision starts from the existing concept.
3. The active Telegram reference image is reused automatically unless a new `reference_image_path` is supplied.
4. `revise_poster` returns:
   - structured change goals
   - preservation goals
   - a calm Telegram summary
   - a lightweight self-check checklist

Critique-only poster turns can remain in assistant mode. Poster change requests route into `vizier_work`.

## Telegram UX notes

- The Telegram launcher now defaults `HERMES_TOOL_PROGRESS_MODE=off`, which removes internal tool chatter from the normal front-door experience.
- Poster replies should describe revisions as targeted improvements, not guaranteed fixes, unless the requested checks clearly pass.
