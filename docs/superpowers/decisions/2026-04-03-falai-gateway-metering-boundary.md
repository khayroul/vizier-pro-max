# Decision: Route fal.ai poster generation through the Vizier gateway

Date: `2026-04-03`
Status: `accepted`

## Context

- `fal.ai` became the default poster backend in [`2026-04-03-falai-default-for-posters.md`](/Users/Executor/vizier-pro-max/docs/superpowers/decisions/2026-04-03-falai-default-for-posters.md), but the image wrapper still called `https://fal.run` directly.
- That meant the cheaper default was not yet the truthful default: the request could bypass Vizier’s inference boundary and ledger trail.
- Poster generation needs the same evidence model as the OpenAI path so costs, latency, and attribution can be compared honestly.

## Decision

- Route `fal.ai` image generation through the local Vizier inference gateway instead of calling the provider directly from `scripts/visual/generate_image.py`.
- Keep `fal.ai` available as the poster default backend.
- Preserve the existing poster behavior and image outputs while moving provider access under Vizier-owned metering.

## Preserved Behavior

- `poster_generate` and `poster_batch` still generate the same poster artifacts and still support `openai` as an explicit image backend.
- The `fal.ai` backend remains the default for posters.
- The wrapper still downloads the generated image and writes the same local output file path.

## Invariants

- Hermes remains the sole runtime kernel.
- Vizier owns the inference boundary and the append-only evidence trail.
- No direct provider call should remain in the poster path outside the gateway.
- The gateway must record provider name, modality, source, status, and failure reason for fal-backed image attempts.

## Validation

- Added gateway tests for `fal.ai` image routing and ledger logging.
- Added wrapper and poster-path tests to verify the gateway headers are propagated.
- Verified the batch poster path stamps a dedicated background-generation step before the image call.

## Follow-up

- If a future provider-key rename is needed, it should happen only in the gateway boundary, not in poster callers.
- Keep the same decision-note discipline if additional image backends are routed through the gateway later.
