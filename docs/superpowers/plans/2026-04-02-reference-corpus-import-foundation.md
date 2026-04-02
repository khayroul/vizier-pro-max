# Reference Corpus Import Foundation

## Scope

This session adds pinned local reference corpora for UI UX Pro Max, Vega-Lite,
and Quarto under `references/`. These are reference layers for Vizier only.
Hermes remains the only runtime.

## Imported

### UI UX Pro Max

- Structured CSVs for UI styles, UX guidelines, chart usage, landing patterns,
  typography pairings, and product color systems.
- Normalized datasets for `ui_styles`, `visual_motifs`, `ux_guidelines`,
  `landing_patterns`, `chart_usage_patterns`, `typography_pairings`, and
  `color_systems`.

Vizier should use this corpus to improve visual direction, UI pattern choice,
layout taste, CTA structure, and practical UX heuristics. It should not invoke
the upstream skill or CLI.

### Vega-Lite

- A pinned Vega-Lite JSON schema snapshot.
- A curated subset of example specs covering comparison, trend, uncertainty,
  density, correlation, faceting, and exploratory matrices.
- Normalized datasets for `chart_grammar` and `chart_patterns`.

Vizier should use this corpus to strengthen chart grammar awareness, chart
family recommendation, and infographic/chart specification quality. It should
not treat Vega-Lite as a runtime renderer in this phase.

### Quarto

- Pinned Quarto schema files for layout, formatting, figures, tables, and
  Typst-related document controls.
- Project templates for `book`, `website`, and `manuscript`.
- Architecture notes for HTML callouts and Typst long-form templates.
- Normalized datasets for `document_layout_options`,
  `table_figure_conventions`, `callout_patterns`, `publishing_patterns`, and
  `longform_structure_patterns`.

Vizier should use this corpus to improve report layout, publishing structure,
callout handling, tables, figures, and long-form formatting advice. It should
not execute Quarto or adopt Quarto as an alternate pipeline runtime.

## Not Wired Yet

- At import time, no Hermes tools were registered yet. See
  `docs/superpowers/plans/2026-04-02-reference-corpus-lookup-layer.md` for the
  first lookup-layer follow-up.
- No chart renderer or document renderer runtime has been added.
- No style calibration packs have been built on top of the imported corpora yet.

## Recommended Follow-Up

Build thin Hermes-native lookup helpers over `references.inventory` for:

- `search_ui_styles`
- `search_ux_guidelines`
- `search_chart_patterns`
- `search_report_layouts`
- `search_quarto_layouts`

After that, add targeted recommendation logic to poster/report pipelines without
changing the runtime boundary.
