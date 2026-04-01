# Artifact Quality Overhaul — 7-Session Plan

**Date:** 2 April 2026
**Author:** Khairul / Premier Marketing
**Status:** Approved design, pending implementation plan
**Scope:** All 5 pipelines + quality backbone + benchmark regression

---

## Problem Statement

All 5 Vizier pipelines produce subpar artifacts. The 6-layer quality gate exists in `middleware/quality_gate.py` but is not wired into any pipeline execution path beyond Layer 1 input validation in `content_generate`. LLM output goes raw to deliverables with conversational preamble, meaningless charts, blind image generation, and no output verification.

### Artifact Grades (Baseline — 2 April 2026)

| Pipeline | Grade | Root Cause |
|----------|-------|------------|
| content_generate (PDF) | D | Title from brief, LLM preamble/sign-off leaked, no styling, no RAG |
| competitive_analysis (chart + report) | F | Chart plots `range(len(columns))` — sequential integers. Only `describe()` called, topic ignored |
| clone_converge (template) | F | LLM receives file path string, not image. Cannot see target. Score stuck at 0.19 |
| poster_batch (posters) | C+ | Viewport whitespace, no quality gate. Works otherwise |
| tts_generate (audio) | B+ | Works. No output quality checks |

### Architecture Alignment

Architecture spec (§9) mandates 6-layer QA on every workflow:

| Layer | Spec | Current State |
|-------|------|---------------|
| L1 Input validation | Schema + required fields | Called by content_generate only |
| L2 Output verification | Structured output matches expected | **Not called by any pipeline** |
| L3 Visual QA | Rendered images match target | Called by clone_converge only (broken) |
| L4 Content quality | Language, tone, register | **Not called by any pipeline** |
| L5 Delivery verification | Confirm delivery succeeded | **Not called by any pipeline** |
| L6 Feedback loop | Quality scores feed into OpenSpace | **Not called by any pipeline** |

---

## Session Map

| Session | Focus | Deliverable |
|---------|-------|-------------|
| 1 | Quality backbone + benchmark freeze | Infrastructure — no artifact |
| 2 | content_generate | PDF — compare vs baseline |
| 3 | competitive_analysis | Chart + report — compare vs baseline |
| 4 | clone_converge + install deps | Template — compare vs baseline |
| 5 | poster_batch | Posters — compare vs baseline |
| 6 | tts_generate | Audio — compare vs baseline |
| 7 | Full benchmark comparison + regression tests | Scorecard + regression suite |

---

## Session 1: Quality Backbone

### A. Output Cleanup Utility

Small function (~20 lines) in `adapter/llm_client.py` that strips common LLM conversational patterns:
- Preamble ("Sure!", "Absolutely — here's...", "Here you go:")
- Meta-commentary ("If you'd like, I can also...", "Let me know if...")
- Trailing sign-offs

Post-processing option on `chat()`, not a separate module. The real fix is prompts (Sessions 2-6), but this is a safety net.

### B. Quality Gate Pipeline Runner

`middleware/pipeline_runner.py` — lightweight wrapper enforcing quality gates. Wraps the existing `quality_gate.validate_input()` and `quality_gate.validate_output()` functions — does not replace them:

```python
def run_with_gates(
    pipeline_fn: Callable,
    inputs: dict,
    input_schema: dict,
    output_schema: dict,
    quality_config: dict | None = None,
) -> dict:
```

Enforces:
- L1: `quality_gate.validate_input(inputs, input_schema)` — always
- L2: `quality_gate.validate_output(result, output_schema)` — always
- L3: Visual QA — opt-in via `quality_config` (visual pipelines only)
- L4: Content quality — opt-in (content pipelines only)
- L5: Delivery verification — opt-in (delivery pipelines only)
- L6: Feedback log — always

Returns result with `quality_report` attached.

Sessions 2-6 replace direct `validate_input()` calls in each pipeline with `run_with_gates()` calls to avoid duplicate validation.

### C. Prompt Discipline

Shared prompt principles (constant or docstring, not a YAML config system):
- "Output ONLY the deliverable content"
- "No preamble, no sign-off, no offers to revise"
- "Use the specified format exactly"

Each pipeline applies these inline during its session.

### D. Extend `llm_client.chat()` for Vision

The current `chat()` signature types messages as `list[dict[str, str]]`, which cannot carry OpenAI vision content blocks (image_url). Extend the type to `list[dict[str, str | list]]` so Session 4 (clone_converge) can pass base64-encoded images. This is infrastructure — do it here, not in Session 4.

### E. Install Missing Dependencies

`pip install opencv-python-headless pixelmatch` — needed for clone_converge delta signals (Session 4). pytesseract only if Tesseract CLI is available. lingua for L4 content quality.

Add these to `pyproject.toml` optional dependencies (not just a one-off pip install) so future environments get them automatically.

### F. Freeze Benchmark Inputs

Save today's exact inputs to `tests/benchmarks/inputs/`:
- `content_brief.txt` — LinkedIn post brief
- `titanic.csv` — competitive analysis dataset
- `target_design.png` — clone_converge target
- `tts_text.txt` — TTS input text
- `poster_template.html` + `poster_data.csv` — poster batch inputs

Save today's artifacts to `tests/benchmarks/baseline/` for comparison.

---

## Session 2: content_generate

### Problems
1. Title is first 50 chars of the brief (truncated instruction, not a title)
2. System prompt produces conversational output with preamble/sign-off
3. No RAG retrieval (architecture §8)
4. PDF has no visual design — raw text dump
5. No output format control

### Fixes

**Prompt rewrite**: System prompt specifies output structure — JSON with fields `title`, `body`, `hashtags`. Pipeline extracts proper title, separates hashtags, strips framing structurally.

**Title from LLM output**: The LLM generates the title, or pipeline derives from first heading in body. Brief is an instruction, not a title.

**Typst template**: Proper heading hierarchy, margins, font sizing. Still simple — not a design system — but looks like a document.

**RAG integration**: If LightRAG is wired, add retrieval step between brief and generation. If not available, skip.

**Quality gate**: Wire through `run_with_gates()`. L2 catches empty/truncated LLM response before PDF render. L4 for language check.

### Success criteria
- PDF has a real title (not truncated brief)
- No LLM conversational artifacts in output
- Structured headings and professional formatting
- L2 output validation passes

---

## Session 3: competitive_analysis

### Problems
1. Chart plots `range(len(columns))` — meaningless
2. Only calls `describe()` regardless of topic
3. LLM receives raw describe() JSON, speculates instead of analyzing
4. No topic-aware analysis strategy

### Fixes

**LLM-driven analysis strategy**: Before pandas, ask LLM: "Given this topic and these columns, what groupby/aggregation/filter operations answer the question?" LLM returns operations from the existing set (`describe`, `groupby`, `filter` in `analyze_data.py`). Pipeline calls `analyze_run()` multiple times with LLM-selected operations instead of hardcoded `operation="describe"`.

**Chart from real analysis**: Plot groupby result (e.g. survival rate by class x gender), not column indices. Pipeline passes analysis output to `render_chart.run()` with appropriate chart type.

**Multi-chart support**: Allow 2-3 charts per analysis when warranted.

**Richer narrative**: LLM receives actual cross-tabulation results. Makes definitive statements ("1st class women survived at 96.8%") instead of hedging.

**Report structure**: Markdown with executive summary, findings, data tables, chart embeds, recommendations.

### Success criteria
- Chart Y-axis reflects actual data values (not sequential integers)
- Narrative cites specific numbers from the data
- Analysis directly answers the topic question
- Report has clear structure with sections

---

## Session 4: clone_converge

### Problems
1. LLM cannot see the target image (passes file path string)
2. Delta feedback is raw numbers, not actionable
3. cv2, pixelmatch, pytesseract missing — 3/5 delta signals use stubs
4. No convergence possible

### Fixes

**Vision API integration**: Use OpenAI vision endpoint — encode target image as base64, pass in `image_url` content block. This is the critical fix.

**Delta-to-guidance translator**: Convert numeric delta signals to natural language: "Color palette is too light — target uses dark navy. Layout should be two columns, not one." Either via vision model qualitative diff or signal-to-text mapping.

**Iteration strategy**: Each iteration sends target image + current rendered screenshot + delta scores to the vision model. LLM can visually compare.

**Real delta scoring**: With cv2 + pixelmatch installed (Session 1), SSIM, pixel diff, and layout signals use real implementations.

### Success criteria
- Score improves across iterations (not stuck at 0.19)
- Final render has matching color palette, layout proportions, text content
- Vision API actually receives the image

---

## Session 5: poster_batch

### Problems
1. Viewport mismatch — whitespace around poster
2. No quality gate

### Fixes

**Viewport control**: Set Playwright viewport to 800x600 (matching poster dimensions), `full_page=False`.

**Visual QA gate**: L3 — check PNG isn't blank, has expected dimensions, file size reasonable.

**Template validation**: Render first row before batch. Fail fast on Jinja2 errors.

### Success criteria
- Full-bleed posters, no whitespace border
- Correct dimensions (800x600)
- L3 visual QA passes

---

## Session 6: tts_generate

### Problems
1. Works well already
2. No quality gates

### Fixes

**Duration check**: MP3 is non-zero duration, proportional to input text length.

**Output verification**: L2 — file exists, size > 0, valid MP3 header.

**Voice validation**: Verify voice name is valid before Edge TTS call.

### Success criteria
- L2 output verification passes
- Duration check catches truncated/silent files

---

## Session 7: Benchmark & Iterate

### Process

1. Run all 5 pipelines with frozen benchmark inputs from Session 1
2. Save artifacts to `tests/benchmarks/outputs/final/`
3. Compare side-by-side with `tests/benchmarks/baseline/`
4. Score each against session-specific success criteria
5. Produce scorecard with before/after grades

### Regression Tests

One pytest test per pipeline in `tests/benchmarks/test_quality_regression.py`:
- content_generate: Title != truncated brief, no preamble pattern match, PDF file valid
- competitive_analysis: Chart Y-values != sequential integers, narrative contains specific numbers
- clone_converge: Score > 0.50 after 3 iterations, vision API called
- poster_batch: PNG dimensions == 800x600, no excess whitespace
- tts_generate: MP3 duration > 0, file size proportional to text length

These prevent future regressions.

### Iteration
If any pipeline still produces subpar output, file specific fixes for a follow-up session.

---

## Files Changed Per Session

| Session | New Files | Modified Files |
|---------|-----------|---------------|
| 1 | `middleware/pipeline_runner.py`, `tests/benchmarks/inputs/*`, `tests/benchmarks/baseline/*` | `adapter/llm_client.py`, `pyproject.toml` |
| 2 | None | `pipelines/content_generate.py`, `scripts/document/render_typst.py` |
| 3 | None | `pipelines/competitive_analysis.py`, `scripts/research/render_chart.py`, `scripts/research/analyze_data.py` |
| 4 | None | `pipelines/clone_converge.py`, `scripts/visual/calculate_delta.py` |
| 5 | None | `pipelines/poster_batch.py`, `scripts/visual/screenshot_html.py` |
| 6 | None | `pipelines/tts_generate.py` |
| 7 | `tests/benchmarks/test_quality_regression.py`, `tests/benchmarks/outputs/final/*` | None |

---

## Out of Scope

- **`pipelines/poster_generate.py`** — a separate, more advanced pipeline (AI-generated backgrounds via gpt-image-1/fal.ai + template overlay). Different from `poster_batch.py` which is CSV-driven batch rendering. `poster_generate` is a Gate 2+ pipeline and will be addressed separately.

## Regression Policy

If a session's changes regress another pipeline (e.g. output cleanup in Session 1 strips valid content from tts_generate), the regression is detected during that session's benchmark comparison. The specific change is isolated and reverted before proceeding to the next session.

---

## Dependencies

- OpenAI API key in `.env` (already present)
- OpenAI vision endpoint access (verify gpt-5.4-mini supports vision, else use gpt-5.4)
- `pip install opencv-python-headless pixelmatch` (Session 1)
- `pip install lingua-language-detector` (Session 1, for L4)
- Tesseract CLI for pytesseract (check availability)
- LightRAG availability (check for Session 2 RAG integration)
