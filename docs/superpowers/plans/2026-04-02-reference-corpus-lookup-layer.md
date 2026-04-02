# Reference Corpus Lookup Layer

## Scope

This follow-up adds the first Hermes-native lookup substrate on top of the
normalized local reference corpora. Hermes remains the only runtime. Vega-Lite,
Quarto, and UI UX Pro Max stay reference-only imports.

## What Is Exposed

- `search_ui_styles`
  - Queries `ui_ux_pro_max/ui_styles`
  - Enriches results with `ui_ux_pro_max/visual_motifs`
- `search_ux_guidelines`
  - Queries `ui_ux_pro_max/ux_guidelines`
- `search_chart_patterns`
  - Queries `ui_ux_pro_max/chart_usage_patterns`
  - Queries `vega_lite/chart_patterns`
- `search_report_layouts`
  - Queries `quarto/document_layout_options`
  - Queries `quarto/table_figure_conventions`
  - Queries `quarto/longform_structure_patterns`
- `search_quarto_layouts`
  - Queries `quarto/document_layout_options`
  - Queries `quarto/callout_patterns`
  - Queries `quarto/publishing_patterns`
  - Queries `quarto/longform_structure_patterns`

## Integration Shape

- Reusable lookup/index code lives in `references/` and loads deterministic
  normalized datasets through `references.inventory`.
- Hermes tool registration stays in `plugins/design_intelligence/`.
- Results are local-search matches with dataset metadata and relevance scores.

## Still Unwired

- No pipeline orchestration chooses among these tools automatically yet.
- Poster/report/content pipelines do not consume these lookups directly yet.
- No Vega-Lite renderer, Quarto executor, or UI UX Pro Max runtime has been
  introduced.
- No cross-pipeline recommendation layer has been added on top of the search
  helpers yet.
