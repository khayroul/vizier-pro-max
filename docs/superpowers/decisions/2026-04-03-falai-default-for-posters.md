# Decision: Make fal.ai the default poster image backend

Date: `2026-04-03`
Status: `accepted`

## Context

- A live poster benchmark on `2026-04-03` showed the current `fal.ai` path was materially cheaper and faster than the OpenAI image path for the same poster request.
- Measured poster generation with the same brief produced:
  - OpenAI path: about `23.6s` and about `$0.045` per poster
  - fal.ai path: about `5.9s` and about `$0.0048` to `$0.0076` per poster
- The repo still defaulted poster generation to OpenAI in the pipeline fallback, client defaults, and client YAML configs.
- This change could be misread later as a quality regression or an accidental provider swap unless the cost and latency rationale are preserved.

## Decision

- Change the default poster image backend from `openai` to `falai`.
- Apply the default change at all normal resolution points:
  - repo-level poster fallback
  - client default dataclass
  - current client configs that explicitly pinned `openai`
  - registry/help text
- Do not remove the `openai` poster path. It remains supported as an explicit override.

## Preserved Behavior

- The two-layer poster pipeline remains the same:
  - normalize the creative brief
  - generate a hero image
  - render the HTML template with Playwright
- Users and pipelines can still explicitly request `image_mode="openai"` when needed.
- This decision changes the default backend, not the poster feature set, template system, or client-theming model.

## Invariants

- Poster generation must remain available with both `falai` and `openai`.
- Leaving `image_mode` empty must now resolve to `falai`.
- Client-config-driven poster generation must inherit the new default unless a client explicitly overrides it later.
- Tests that exercise default poster behavior must prove the backend resolution rather than silently relying on prior OpenAI defaults.

## Validation

- Updated poster-focused tests in:
  - [test_poster_generate.py](/Users/Executor/vizier-pro-max/tests/pipelines/test_poster_generate.py)
  - [test_poster_client_integration.py](/Users/Executor/vizier-pro-max/tests/pipelines/test_poster_client_integration.py)
- Verified with:

```bash
python3 -m pytest /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_generate.py /Users/Executor/vizier-pro-max/tests/pipelines/test_poster_client_integration.py -q
```

- Result: `58 passed`

## Follow-up

- `fal.ai` image generation still needs first-class metering into Vizier’s ledger so the cheaper default is also the truthful default.
- Hermes compression and other active-session auxiliary paths still need the same decision-note discipline when their routing boundary is hardened.
