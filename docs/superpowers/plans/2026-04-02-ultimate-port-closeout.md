# Ultimate Port Closeout

Date: 2 April 2026

## Summary

This closeout treats the Vizier Ultimate port as complete inside Pro-Max without expanding into repo-wide legacy stabilization.

Included in scope:

- visual and document template port
- poster branding and `client_id` config flow
- document assembly tools: template render, PDF, EPUB, PPTX, Markdown-to-Typst
- research tools: report composer, YouTube search, YouTube transcript extraction
- listening engine plus ads clone

Not included in scope:

- refactoring or stabilizing older legacy pipelines outside the ported surface
- making the entire historical test suite deterministic

## Locked Public Interface

- `poster_generate.run(...)` supports `brand_name`, `logo_mark`, `brand_css`, and `client_id`
- `poster_batch.run(...)` supports `client_id` batch mode where `template_path` is optional
- legacy non-client poster batches still require `template_path`
- the listening engine is a Pro-Max-native slimmer port, not a line-for-line Ultimate transplant

## Verified Green Matrix

The following commands define done for this closeout and were rerun successfully:

- `python3 -m pytest tests/adapter tests/bridge tests/bootstrap tests/config -q`
  Result: `145 passed`
- `python3 -m pytest tests/middleware tests/migrations tests/tools tests/templates tests/benchmarks -q`
  Result: `113 passed, 13 skipped`
- `python3 -m pytest tests/plugins tests/scripts -q`
  Result: `185 passed`
- `python3 -m pytest tests/augments -q`
  Result: `160 passed, 1 warning`
- `python3 -m pytest tests/pipelines/test_poster_generate.py tests/pipelines/test_poster_batch.py tests/pipelines/test_poster_batch_quality.py tests/pipelines/test_poster_templates.py tests/pipelines/test_poster_client_integration.py tests/pipelines/test_ads_clone.py -q`
  Result: `72 passed`
- `python3 -m pytest tests/test_operational.py tests/test_acceptance_gate3.py -q`
  Result: `59 passed, 1 skipped`

Known warning during the green matrix:

- `requests` dependency warning from the local environment about unsupported `urllib3` / `chardet` or `charset_normalizer` versions

## Explicit Legacy Blockers

These are documented, not fixed, in this closeout:

- `tests/pipelines/test_content_generate.py`
  Current stall: `TestContentGeneratePipeline::test_returns_content_for_valid_brief`
- `tests/pipelines/test_competitive_analysis.py`
  Current stall: `TestCompetitiveAnalysis::test_analysis_without_data`
- `tests/pipelines/test_clone_converge_full.py`
  Current stall: `TestCloneConverge::test_run_with_mocked_pipeline`
- top-level `tests/test_integration*.py`

Observed behavior for the three pipeline stalls:

- manual interruption lands inside `httpcore/_backends/sync.py`, indicating a network-bound wait path
- `pytest-timeout` is not installed in this repo, so `pytest --timeout=...` is currently unsupported and is not part of closeout verification

## Assumptions

- Done means the Ultimate-derived features are shipped and verified inside Pro-Max
- Done does not mean the entire historical repository is green
- No extra dependency or harness work is added unless it is required by the ported features themselves
