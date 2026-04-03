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
- `hero_presence`: does the rendered hero region contain enough visual mass for the requested composition?
- `text_zone_readability`: does the rendered text zone stay calm and high-contrast enough for overlay copy?
- `cta_salience`: does the rendered CTA zone show enough visible signal to avoid disappearing into the layout?

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
- `evaluations/reference_corpus/results/2026-04-03-ui-ux-quality-loop/after-manual-scorecard.template.json`

Objective delta after adding render-aware checks:

- average objective score: `14.2` -> `88.3`
- `reference_usage`: `0.0` -> `100.0`
- `copy_discipline`: `75.0` -> `100.0`
- `template_fit`: `20.0` -> `88.8`
- `prompt_guardrails`: `0.0` -> `81.2`
- `trace_persistence`: `0.0` -> `100.0`
- `hero_presence`: `0.0` -> `67.1`
- `text_zone_readability`: `0.0` -> `77.2`
- `cta_salience`: `0.0` -> `70.2`

Case-level template shifts:

- `swiss_analytics_hero`: `social-post` -> `floating-card-square`
- `retro_event_poster`: `social-post` -> `stacked-type-square`
- `donation_trust_landing`: `social-post` -> `hero-bottom-text-square`
- `premium_product_drop`: `social-post` -> `stacked-type-square`

Render-aware follow-up signals from the current run:

- `retro_event_poster`: hero presence is still weak at `25.6`
- `premium_product_drop`: hero presence is still weak at `42.7`
- `donation_trust_landing`: text-zone readability is still middling at `57.2`
- `swiss_analytics_hero`: CTA salience is still middling at `46.5`

## Still Manual / Approximate

The current harness is stronger than the old lookup-only checks, but it still does not fully automate taste.

Still manual or approximate:

- whether the hero truly feels premium rather than merely large
- whether CTA presence feels persuasive rather than just detectable
- whether composition feels intentional to a design reviewer
- whether reference usage is genuinely well-distilled or only mechanically present
- whether rendered outputs consistently avoid abstract or under-specified hero imagery

This follow-up direction also adds a poster-specific manual-review scorecard flow so the artifact reports can be turned into stable human review templates instead of ad hoc comments.

## Recommended Next Packet

The next follow-up packet should focus on:

- human scorecards across 12-20 poster/UI artifacts using the manual dimensions above
- tighter distillation of local reference matches into art-direction-ready guidance
- render-aware checks for hero occupancy, text-zone contrast, and CTA salience
- a small frozen gallery of accepted high-quality poster/UI outputs for regression review
