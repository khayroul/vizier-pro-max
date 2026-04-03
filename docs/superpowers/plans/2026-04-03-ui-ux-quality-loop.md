# UI/UX Quality Loop: Poster-First Measurement Packet

## Scope

This packet focuses on poster and visual UI quality only.

- Hermes remains the only runtime.
- UI UX Pro Max, Vega-Lite, and Quarto remain pinned local reference corpora only.
- Telegram and operator routing work are explicitly out of scope for this packet.

## What We Measured

We extended the reference-corpus evaluation flow so poster/UI runs can be measured as generated artifacts instead of lookup-only proxies.

Objective checks in the poster suite:

- `reference_usage`: did poster generation consult the expected local reference tools and persist materially influencing items?
- `copy_discipline`: did the generated brief keep headline/body/CTA concise and action-led?
- `template_fit`: did the selected template match the prompt family instead of defaulting to a generic poster?
- `prompt_guardrails`: did the generated image prompt carry hierarchy, contrast, composition, and CTA guidance?
- `trace_persistence`: did the run persist a generation trace that future sessions can inspect?

Manual review remains required for:

- composition choice
- hero prominence
- hierarchy and readability
- CTA emphasis
- copy sharpness
- visual polish
- reference utilization quality

## Baseline Weaknesses

Before this packet, the recurring poster/UI failure mode was:

- generic fallback composition, usually `social-post`
- weak or generic headline and CTA language
- little to no persisted evidence of which references influenced the result
- prompt assembly that did not explicitly defend hierarchy, contrast, hero scale, or CTA presence
- no stable before/after artifact bundle for poster/UI work

## What Changed

The poster/UI path now:

- auto-consults the local visual reference route
- traces reference families, lookup tools, datasets consulted, and material influences
- persists a sibling `poster.trace.json` artifact for poster runs
- recommends templates from poster/UI composition cues instead of defaulting to `social-post`
- sharpens freeform and model-produced poster briefs toward shorter headlines and stronger CTA language
- injects art-direction guardrails into prompt assembly for composition, hero scale, readability, CTA emphasis, and color discipline
- runs through a poster artifact suite with stable before/after reports and comparison output

## Evidence

Poster artifact suite comparison recorded in:

- `evaluations/reference_corpus/results/2026-04-03-ui-ux-quality-loop/before-report.json`
- `evaluations/reference_corpus/results/2026-04-03-ui-ux-quality-loop/after-report.json`
- `evaluations/reference_corpus/results/2026-04-03-ui-ux-quality-loop/comparison.json`

Objective delta:

- average objective score: `19.0` -> `94.0`
- `reference_usage`: `0.0` -> `100.0`
- `copy_discipline`: `75.0` -> `100.0`
- `template_fit`: `20.0` -> `88.8`
- `prompt_guardrails`: `0.0` -> `81.2`
- `trace_persistence`: `0.0` -> `100.0`

Case-level template shifts:

- `swiss_analytics_hero`: `social-post` -> `floating-card-square`
- `retro_event_poster`: `social-post` -> `stacked-type-square`
- `donation_trust_landing`: `social-post` -> `hero-bottom-text-square`
- `premium_product_drop`: `social-post` -> `stacked-type-square`

## Still Manual / Approximate

The current harness is stronger than the old lookup-only checks, but it still does not fully automate taste.

Still manual or approximate:

- whether the hero truly feels premium rather than merely large
- whether CTA presence feels persuasive rather than just detectable
- whether composition feels intentional to a design reviewer
- whether reference usage is genuinely well-distilled or only mechanically present
- whether rendered outputs consistently avoid abstract or under-specified hero imagery

## Recommended Next Packet

The next follow-up packet should focus on:

- human scorecards across 12-20 poster/UI artifacts using the manual dimensions above
- tighter distillation of local reference matches into art-direction-ready guidance
- render-aware checks for hero occupancy, text-zone contrast, and CTA salience
- a small frozen gallery of accepted high-quality poster/UI outputs for regression review
