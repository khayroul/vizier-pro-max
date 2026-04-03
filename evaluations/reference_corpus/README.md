# Reference Corpus Quality Eval

This evaluation layer measures two different things:

1. Whether the local reference substrate exists and returns the kinds of
   reference matches we expect.
2. Whether poster/UI artifact runs are actually becoming less generic and more
   traceable.

Hermes remains the only runtime. UI UX Pro Max, Vega-Lite, and Quarto stay
local reference corpora only.

## What It Measures Well

- deterministic milestone capability checks
- deterministic lookup probes for the public reference-search tools
- artifact-run trace completeness for poster/UI generation
- objective poster proxies such as:
  - reference tools consulted
  - material influences captured
  - template fit
  - copy discipline
  - prompt guardrail coverage
  - hero-region visual presence
  - text-zone readability calmness
- CTA-region salience

## What It Still Measures Poorly

- final visual taste
- whether the generated hero image truly feels premium
- whether the generated hero subject is actually recognizable instead of an abstract stand-in
- subtle hierarchy failures that need human eyes
- nuanced brand-fit judgments

That is why the poster/UI suite now ships with explicit manual-review fields
for:

- `composition_choice`
- `hero_prominence`
- `hierarchy_readability`
- `cta_emphasis`
- `copy_sharpness`
- `visual_polish`
- `reference_utilization`

## Files

- `suite.yaml`
  - frozen cross-family lookup/eval suite
- `poster_ui_suite.yaml`
  - frozen poster/UI artifact-run suite
- `rubric.yaml`
  - manual scoring rubric for the general reference suite
- `milestones.yaml`
  - git milestones used by the deterministic capability/lookup probe
- `results/`
  - before/after reports, comparisons, and artifact bundles

## Recommended Use

1. Run `probe-milestones` when the substrate changes.
2. Run `run-poster-suite` when poster/UI quality logic changes.
3. Compare the before/after poster reports to see whether:
   - more references were actually consulted
   - template choice improved
   - copy/CTA discipline improved
   - prompt guardrails became more explicit
   - CTA and readability checks still align with the live template geometry
4. Generate a poster review template with `prepare-poster-scorecard`.
5. Use the poster scorecard for the subjective visual call and compare completed reviews with `compare-poster-scorecards`.
