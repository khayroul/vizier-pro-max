# Quality Overhaul Scorecard

**Date:** 2 April 2026
**Status:** Implementation complete, pending human review of benchmark artifacts

## Before/After Grades

| Pipeline | Baseline Grade | Final Grade | Key Improvement |
|----------|---------------|-------------|-----------------|
| content_generate | D | Pending | Title from LLM JSON, no preamble, Typst styling |
| competitive_analysis | F | Pending | LLM-driven operations, real chart data, structured report |
| clone_converge | F | Pending | Vision API with base64 images, delta-to-guidance feedback |
| poster_batch | C+ | Pending | 800x600 viewport, full_page=False, no whitespace |
| tts_generate | B+ | Pending | L2 verification (MP3 header, size), voice validation |

## Quality Gate Coverage

| Layer | Before | After |
|-------|--------|-------|
| L1 Input validation | content_generate only | All pipelines via run_with_gates |
| L2 Output verification | None | content_generate, competitive_analysis, tts_generate |
| L3 Visual QA | Broken (clone_converge) | Functional via vision API |
| L4 Content quality | None | content_generate (language check) |
| L5 Delivery verification | None | Opt-in ready |
| L6 Feedback loop | None | All pipelines via run_with_gates |

## Changes Summary

- **Session 1:** Output cleanup utility, pipeline runner, benchmark inputs
- **Session 2:** content_generate JSON prompt, title extraction, quality gates
- **Session 3:** competitive_analysis LLM-driven ops, real charts, report structure
- **Session 4:** clone_converge vision API, delta guidance, visual iteration
- **Session 5:** poster_batch 800x600 viewport fix
- **Session 6:** tts_generate L2 verification, voice validation
- **Session 7:** Regression test suite (9 tests, gated by VIZIER_BENCHMARK=1)

## Next Steps

1. Run `VIZIER_BENCHMARK=1 python3 -m pytest tests/benchmarks/test_quality_regression.py -v --timeout=120` with API keys
2. Human review of produced artifacts
3. Fill in final grades above
4. File follow-up fixes for any pipelines still producing subpar output
