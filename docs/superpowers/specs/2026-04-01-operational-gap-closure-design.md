# Operational Gap Closure — Design Spec

**Date:** 2026-04-01
**Status:** Draft
**Scope:** Close all remaining stubs in Gate 2/3 code to reach full operational status

## Problem

7 components have stub implementations despite all underlying dependencies being available and a proven LLM integration pattern existing in `content_generate.py`. This leaves ~30% of advertised capability non-functional.

## Approach

Minimal wiring — no new abstractions. Each stub gets the simplest correct implementation using existing tools and the proven Hermes LLM proxy pattern.

## Changes

### 1. LLM Integration (3 files)

All three use the same pattern: `httpx.post` to `http://localhost:11435/v1/chat/completions` with `gpt-5.4-mini`, specific system prompts, and graceful fallback.

#### 1a. `augments/openspace/fixer.py::_call_llm_for_fix`
- **System prompt:** "You are a skill repair engine. Given a broken SKILL.md and an error traceback, output a corrected SKILL.md. Preserve the original structure. Output ONLY valid markdown."
- **User prompt:** Original SKILL.md content + error context
- **Timeout:** 30s
- **Fallback:** Return original content with `<!-- AUTO-FIX FAILED -->` comment appended
- **Max tokens:** 2048

#### 1b. `augments/openspace/deriver.py::_call_llm_for_enhancement`
- **System prompt:** "You are a skill enhancement engine. Given a SKILL.md and quality scores, output an improved version. Preserve structure, improve clarity/coverage. Output ONLY valid markdown."
- **User prompt:** Original SKILL.md + quality scores as formatted key-value pairs
- **Timeout:** 30s
- **Fallback:** Return original content unchanged
- **Max tokens:** 2048

#### 1c. `pipelines/clone_converge.py` — two helpers

**`_call_llm_for_html`:**
- **System prompt:** "You are an HTML/CSS generator. Given a description of a visual design, output clean semantic HTML5 with inline CSS. Output ONLY the HTML document, no explanation."
- **User prompt:** "Generate HTML/CSS matching the target image." + delta feedback if available + previous HTML if refining
- **Timeout:** 45s (longer — generates more content)
- **Fallback:** Return minimal HTML stub with error comment
- **Max tokens:** 4096
- **Note:** Vision not available on gpt-5.4-mini free tier. First iteration uses text description of target. Future gate can upgrade to vision model.

**`_render_html_to_png`:**
- **Implementation:** Call `scripts.visual.screenshot_html.run(html_content=html, output_path=str(output_path))` directly
- **No LLM needed** — this is a Playwright call, not an LLM call

### 2. Pipeline Implementations (3 files)

Each pipeline follows the `content_generate.py` pattern: validate input, call existing scripts in sequence, return result dict.

#### 2a. `pipelines/tts_generate.py`
- **Input:** `text`, `voice` (default "en-US-AriaNeural"), `output_path`
- **Steps:**
  1. Validate text is non-empty
  2. Call `scripts.audio.speak_text.run(text=text, voice=voice, output_path=raw_path)` → raw audio
  3. Call `scripts.audio.process_media.run(input_path=raw_path, output_path=output_path, operation="normalize")` → normalized MP3
  4. Clean up raw intermediate file
- **Output:** `{"file_path": output_path, "voice": voice, "status": "completed"}`

#### 2b. `pipelines/poster_batch.py`
- **Input:** `csv_path`, `template_path`, `output_dir`, `output_format` (default "png")
- **Steps:**
  1. Load CSV via pandas, validate columns exist
  2. Read Jinja2 template
  3. For each row: render template with row data → HTML string
  4. For each rendered HTML: call `scripts.visual.screenshot_html.run()` → PNG
  5. Collect all output paths
- **Output:** `{"posters": [paths], "count": N, "status": "completed"}`

#### 2c. `pipelines/competitive_analysis.py`
- **Input:** `topic`, `data_path` (CSV with competitor data), `output_dir`
- **Steps:**
  1. Load CSV via `scripts.research.analyze_data.run(input_path=data_path, operation="describe")`
  2. Generate summary chart via `scripts.research.render_chart.run(data_path=data_path, chart_type="bar", ...)`
  3. Call LLM via Hermes proxy for narrative analysis of the data summary
  4. Compile report (markdown with chart reference)
- **Output:** `{"report": markdown_str, "chart_path": path, "status": "completed"}`
- **LLM fallback:** Return data summary without narrative if LLM unavailable

### 3. LightRAG Integration (`scripts/content/search_rag.py`)

- **Dependency:** Add `lightrag-hku>=0.1` to pyproject.toml (the official LightRAG package)
- **Implementation:** In-process LightRAG with local storage (no server required)
- **Config:** `KG_VAULT_PATH` env var points to knowledge graph directory
- **Modes:** "hybrid" (default), "local", "global" — passed through to LightRAG query API
- **Fallback:** If `KG_VAULT_PATH` not set or LightRAG import fails, return empty results with warning
- **No indexing in this scope** — assumes knowledge graph is pre-built. Indexing is a separate operational task.

## Testing Strategy

- All existing tests must continue to pass (LLM helpers are mocked in existing tests)
- New pipeline tests mock the underlying script calls (same pattern as existing pipeline tests)
- Each new pipeline gets: happy path test, missing input test, fallback test
- `search_rag` gets: stub fallback test (no KG configured), mode parameter test

## Files Modified

| File | Change |
|------|--------|
| `augments/openspace/fixer.py` | Replace `_call_llm_for_fix` stub with httpx call |
| `augments/openspace/deriver.py` | Replace `_call_llm_for_enhancement` stub with httpx call |
| `pipelines/clone_converge.py` | Replace both helper stubs with real implementations |
| `pipelines/tts_generate.py` | Full implementation replacing stub |
| `pipelines/poster_batch.py` | Full implementation replacing stub |
| `pipelines/competitive_analysis.py` | Full implementation replacing stub |
| `scripts/content/search_rag.py` | Full LightRAG integration replacing stub |
| `pyproject.toml` | Add `lightrag-hku` dependency |

## Files Created

| File | Purpose |
|------|---------|
| `tests/pipelines/test_tts_generate.py` | Pipeline tests |
| `tests/pipelines/test_poster_batch.py` | Pipeline tests |
| `tests/pipelines/test_competitive_analysis.py` | Pipeline tests |
| `tests/scripts/test_search_rag.py` | RAG search tests |

## Out of Scope

- WhatsApp file attachment (deferred by user)
- LightRAG knowledge graph indexing (operational task, not code)
- Vision model upgrade for clone_converge (future gate)
- DSPy distillation (Gate 3 Chunk 1)

## Exit Criteria

- All 7 stubs replaced with working implementations
- All existing tests pass (324+)
- New tests pass for all new implementations
- Pyright clean on all modified files
- Zero `NotImplementedError` in production code
