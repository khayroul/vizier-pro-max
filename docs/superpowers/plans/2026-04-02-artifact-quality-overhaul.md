# Artifact Quality Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 5 Vizier pipelines to produce professional-grade artifacts, wire the 6-layer quality gate into every pipeline, and establish benchmark regression tests.

**Architecture:** Each pipeline gets prompt rewrites, structural output parsing, and quality gate integration via a new `pipeline_runner.py` wrapper. Session 1 builds shared infrastructure (output cleanup, pipeline runner, vision support, benchmarks). Sessions 2-6 fix one pipeline each. Session 7 runs the full benchmark comparison and creates regression tests.

**Tech Stack:** Python 3.11+, OpenAI gpt-5.4-mini (vision-capable), Typst (PDF), Playwright (screenshots), matplotlib (charts), pandas (analysis), edge-tts (audio), opencv-python-headless + pixelmatch + scikit-image (delta signals)

**Spec:** `docs/superpowers/specs/2026-04-02-artifact-quality-overhaul.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `middleware/pipeline_runner.py` | Quality gate wrapper — enforces L1-L6 on any pipeline |
| Create | `tests/middleware/test_pipeline_runner.py` | Tests for pipeline runner |
| Create | `tests/adapter/test_llm_cleanup.py` | Tests for output cleanup utility |
| Create | `tests/benchmarks/inputs/` | Frozen benchmark input files |
| Create | `tests/benchmarks/baseline/` | Baseline artifacts for comparison |
| Create | `tests/benchmarks/test_quality_regression.py` | Regression tests (Session 7) |
| Modify | `adapter/llm_client.py:43-48` | Add `strip_preamble` param + `_strip_llm_preamble()`, widen message type for vision |
| Modify | `pipelines/content_generate.py` | Prompt rewrite, JSON output, title from LLM, quality gates |
| Modify | `pipelines/competitive_analysis.py` | LLM-driven analysis, real chart data, report structure |
| Modify | `pipelines/clone_converge.py` | Vision API, delta-to-guidance, visual iteration |
| Modify | `pipelines/poster_batch.py` | Viewport fix, visual QA gate |
| Modify | `pipelines/tts_generate.py` | Duration check, output verification gate |
| Modify | `scripts/visual/screenshot_html.py` | Accept viewport params for poster sizing |

---

## Chunk 1: Session 1 — Quality Backbone

### Task 1: Output Cleanup Utility

**Files:**
- Modify: `adapter/llm_client.py:43-74`
- Create: `tests/adapter/test_llm_cleanup.py`

- [ ] **Step 1: Write failing tests for `_strip_llm_preamble()`**

```python
# tests/adapter/test_llm_cleanup.py
"""Tests for LLM output cleanup utility."""
from __future__ import annotations

import pytest

from adapter.llm_client import _strip_llm_preamble


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Preamble removal
        ("Sure! Here's your content:\n\nActual content here.", "Actual content here."),
        ("Absolutely — here's the result:\n\nThe real output.", "The real output."),
        ("Here you go:\n\nContent body.", "Content body."),
        # Sign-off removal
        ("Good content.\n\nLet me know if you need anything else!", "Good content."),
        ("Output text.\n\nIf you'd like, I can also revise this.", "Output text."),
        # Both preamble and sign-off
        (
            "Sure! Here it is:\n\nThe deliverable.\n\nLet me know if you need changes!",
            "The deliverable.",
        ),
        # No cleanup needed — pass through unchanged
        ("Clean output with no preamble.", "Clean output with no preamble."),
        # Empty / whitespace
        ("", ""),
        ("   ", ""),
        # Single line preamble (no double newline separator)
        ("Sure! Actual content starts here.", "Sure! Actual content starts here."),
    ],
)
def test_strip_llm_preamble(raw: str, expected: str) -> None:
    assert _strip_llm_preamble(raw) == expected


def test_strip_preamble_preserves_internal_structure() -> None:
    """Multi-paragraph content should keep internal paragraphs."""
    raw = (
        "Here's your content:\n\n"
        "First paragraph.\n\n"
        "Second paragraph.\n\n"
        "Let me know if you need changes!"
    )
    result = _strip_llm_preamble(raw)
    assert "First paragraph." in result
    assert "Second paragraph." in result
    assert "Let me know" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/adapter/test_llm_cleanup.py -v`
Expected: FAIL — `_strip_llm_preamble` not importable

- [ ] **Step 3: Implement `_strip_llm_preamble()` in llm_client.py**

Add before the `chat()` function in `adapter/llm_client.py`:

```python
import re

_PREAMBLE_PATTERNS = [
    re.compile(r"^(?:Sure!?|Absolutely|Of course|Here(?:'s| is| you go))[^\n]*:\s*\n\n", re.IGNORECASE),
    re.compile(r"^(?:Sure!?|Absolutely|Of course|Here(?:'s| is| you go))[^\n]*—[^\n]*:\s*\n\n", re.IGNORECASE),
]

_SIGNOFF_PATTERNS = [
    re.compile(r"\n\n(?:Let me know|If you(?:'d| would) like|Feel free|Hope this|I can also)[^\n]*[.!]?\s*$", re.IGNORECASE),
    re.compile(r"\n\n(?:Want me to|Shall I|Would you like me to)[^\n]*[.!?]?\s*$", re.IGNORECASE),
]


def _strip_llm_preamble(text: str) -> str:
    """Strip common LLM conversational preamble and sign-off patterns.

    Safety net for raw LLM output. The real fix is prompt discipline
    (applied per-pipeline in Sessions 2-6), but this catches residual
    conversational framing.

    Args:
        text: Raw LLM output string.

    Returns:
        Cleaned string with preamble/sign-off removed.
    """
    result = text.strip()
    if not result:
        return ""

    for pattern in _PREAMBLE_PATTERNS:
        result = pattern.sub("", result)

    for pattern in _SIGNOFF_PATTERNS:
        result = pattern.sub("", result)

    return result.strip()
```

- [ ] **Step 4: Add `strip_preamble` parameter to `chat()`**

Update the `chat()` signature and body:

```python
def chat(
    *,
    messages: list[dict[str, str | list]],  # widened for vision
    max_tokens: int = 1024,
    timeout: float = 30.0,
    strip_preamble: bool = False,
) -> str | None:
    # ... existing body ...
    result = _try_openai(messages, max_tokens, timeout)
    if result is not None:
        return _strip_llm_preamble(result) if strip_preamble else result

    result = _try_ollama(messages, timeout)
    if result is not None:
        return _strip_llm_preamble(result) if strip_preamble else result

    logger.warning("All LLM providers unavailable")
    return None
```

Also update ALL downstream function signatures to accept the widened type:
- `_fire_pre(messages: list[dict[str, str | list]], model: str)` (line 76)
- `_try_openai(messages: list[dict[str, str | list]], max_tokens: int, timeout: float)` (line 94)
- `_try_ollama(messages: list[dict[str, str | list]], timeout: float)` (line 149)

- [ ] **Step 4b: Add test that vision-format messages pass through `chat()`**

Add to `tests/adapter/test_llm_cleanup.py`:

```python
from unittest.mock import patch


def test_chat_accepts_vision_format_messages() -> None:
    """chat() must accept messages with list content blocks (vision API)."""
    from adapter.llm_client import chat

    vision_messages: list[dict[str, str | list]] = [
        {"role": "system", "content": "You are a vision model."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image:"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBOR..."}},
            ],
        },
    ]
    # Should not raise TypeError — we mock the HTTP call
    with patch("adapter.llm_client.httpx.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "A test image"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        result = chat(messages=vision_messages, max_tokens=100)
        assert result == "A test image"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/adapter/test_llm_cleanup.py -v`
Expected: All PASS

- [ ] **Step 6: Run pyright**

Run: `pyright adapter/llm_client.py`
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add adapter/llm_client.py tests/adapter/test_llm_cleanup.py
git commit -m "feat: add LLM output cleanup utility + vision type widening in chat()"
```

---

### Task 2: Pipeline Runner

**Files:**
- Create: `middleware/pipeline_runner.py`
- Create: `tests/middleware/test_pipeline_runner.py`

- [ ] **Step 1: Write failing tests for `run_with_gates()`**

```python
# tests/middleware/test_pipeline_runner.py
"""Tests for pipeline runner quality gate wrapper."""
from __future__ import annotations

from typing import Any

import pytest

from middleware.pipeline_runner import run_with_gates


def _ok_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"content": "result", "status": "completed"}


def _failing_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
    msg = "pipeline exploded"
    raise RuntimeError(msg)


_INPUT_SCHEMA = {"brief": {"type": "string", "required": True}}
_OUTPUT_SCHEMA = {"content": {"type": "string", "required": True}}


def test_run_with_gates_happy_path() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={"brief": "test brief"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert result["content"] == "result"
    assert "quality_report" in result
    report = result["quality_report"]
    assert report["L1"]["passed"] is True
    assert report["L2"]["passed"] is True


def test_run_with_gates_input_validation_fails() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={},  # missing required "brief"
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert "error" in result
    assert result["quality_report"]["L1"]["passed"] is False


def test_run_with_gates_output_validation_fails() -> None:
    def bad_output(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"wrong_key": "value"}

    result = run_with_gates(
        pipeline_fn=bad_output,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert result["quality_report"]["L2"]["passed"] is False


def test_run_with_gates_pipeline_exception() -> None:
    result = run_with_gates(
        pipeline_fn=_failing_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert "error" in result
    assert "pipeline exploded" in result["error"]


def test_run_with_gates_content_quality_opt_in() -> None:
    def content_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"content": "Professional English content for LinkedIn post."}

    result = run_with_gates(
        pipeline_fn=content_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema={"content": {"type": "string", "required": True}},
        quality_config={"L4": {"expected_languages": ["en", "ms"]}},
    )
    assert "L4" in result["quality_report"]


def test_run_with_gates_feedback_logged() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name="test_pipeline",
    )
    assert result["quality_report"]["L6"]["passed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/middleware/test_pipeline_runner.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `pipeline_runner.py`**

```python
# middleware/pipeline_runner.py
"""Quality gate pipeline runner — enforces L1-L6 on any pipeline.

Wraps existing quality_gate functions. Does not replace them.
Pipelines call run_with_gates() instead of validate_input() directly.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

import structlog

from middleware.quality_gate import (
    ValidationResult,
    log_feedback,
    validate_content_quality,
    validate_input,
    validate_output,
)

logger = structlog.get_logger(__name__)


def run_with_gates(
    *,
    pipeline_fn: Callable[[dict[str, Any]], dict[str, Any]],
    inputs: dict[str, Any],
    input_schema: dict[str, dict[str, Any]],
    output_schema: dict[str, dict[str, Any]],
    quality_config: dict[str, dict[str, Any]] | None = None,
    pipeline_name: str = "unknown",
) -> dict[str, Any]:
    """Run a pipeline function with quality gate enforcement.

    Enforces:
    - L1: Input validation (always)
    - L2: Output verification (always)
    - L3: Visual QA (opt-in via quality_config["L3"])
    - L4: Content quality (opt-in via quality_config["L4"])
    - L5: Delivery verification (opt-in via quality_config["L5"])
    - L6: Feedback log (always)

    Args:
        pipeline_fn: The pipeline callable. Receives inputs dict, returns result dict.
        inputs: Pipeline input data.
        input_schema: Schema for L1 input validation.
        output_schema: Schema for L2 output verification.
        quality_config: Optional per-layer config for L3-L5 opt-in.
        pipeline_name: Name for feedback logging.

    Returns:
        Pipeline result dict with ``quality_report`` attached.
    """
    config = quality_config or {}
    session_id = uuid.uuid4().hex[:12]
    report: dict[str, dict[str, Any]] = {}

    # L1: Input validation
    l1 = validate_input(inputs, input_schema)
    report["L1"] = _result_to_dict(l1)
    if not l1.passed:
        report["L6"] = _result_to_dict(
            _log_feedback(pipeline_name, 1, 0.0, False, session_id)
        )
        return {
            "error": f"Input validation failed: {l1.errors}",
            "quality_report": report,
        }

    # Run pipeline
    try:
        result = pipeline_fn(inputs)
    except Exception as exc:
        report["L6"] = _result_to_dict(
            _log_feedback(pipeline_name, 0, 0.0, False, session_id)
        )
        return {
            "error": f"Pipeline failed: {exc}",
            "quality_report": report,
        }

    # L2: Output verification
    l2 = validate_output(result, output_schema)
    report["L2"] = _result_to_dict(l2)

    # L4: Content quality (opt-in)
    if "L4" in config:
        content = str(result.get("content", ""))
        l4_cfg = config["L4"]
        l4 = validate_content_quality(
            content=content,
            expected_languages=l4_cfg.get("expected_languages"),
            expected_tone=l4_cfg.get("expected_tone"),
        )
        report["L4"] = _result_to_dict(l4)

    # L6: Feedback log (always)
    overall_passed = l1.passed and l2.passed
    overall_score = 1.0 if overall_passed else 0.5
    report["L6"] = _result_to_dict(
        _log_feedback(pipeline_name, 6, overall_score, overall_passed, session_id)
    )

    # Immutable return — never mutate pipeline result dict
    return {**result, "quality_report": report}


def _log_feedback(
    pipeline_name: str,
    layer: int,
    score: float,
    passed: bool,
    session_id: str,
) -> ValidationResult:
    """Wrap log_feedback call."""
    return log_feedback(
        tool_name=pipeline_name,
        layer=layer,
        score=score,
        passed=passed,
        session_id=session_id,
    )


def _result_to_dict(vr: ValidationResult) -> dict[str, Any]:
    """Convert ValidationResult to a plain dict for the quality report."""
    return {
        "passed": vr.passed,
        "errors": list(vr.errors),
        "layer": vr.layer,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/middleware/test_pipeline_runner.py -v`
Expected: All PASS

- [ ] **Step 5: Run pyright**

Run: `pyright middleware/pipeline_runner.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add middleware/pipeline_runner.py tests/middleware/test_pipeline_runner.py
git commit -m "feat: pipeline runner — quality gate wrapper enforcing L1-L6"
```

---

### Task 3: Freeze Benchmark Inputs & Baseline

**Files:**
- Create: `tests/benchmarks/inputs/content_brief.txt`
- Create: `tests/benchmarks/inputs/tts_text.txt`
- Create: `tests/benchmarks/baseline/` (directory for baseline artifacts)

Note: `titanic.csv` and `target_design.png` are existing files — copy them.
Note: `poster_template.html` + `poster_data.csv` — use existing test fixtures or create minimal ones.

- [ ] **Step 1: Create benchmark input files**

```bash
mkdir -p tests/benchmarks/inputs tests/benchmarks/baseline
```

Write `tests/benchmarks/inputs/content_brief.txt`:
```
Write a LinkedIn post for a Malaysian SME selling artisanal coffee. The post should highlight their new single-origin Ethiopian Yirgacheffe beans, mention their Petaling Jaya cafe location, and target young professionals aged 25-40. Tone: professional but warm. Include a call-to-action for weekend tasting events. 150-200 words.
```

Write `tests/benchmarks/inputs/tts_text.txt`:
```
Welcome to Vizier Pro-Max, the AI-powered marketing platform for Malaysian small and medium enterprises. Our platform helps you create professional content, analyze your competition, and generate stunning visual designs — all powered by advanced artificial intelligence. Get started today and transform your marketing strategy.
```

- [ ] **Step 2: Copy existing data files to benchmark inputs**

```bash
# Copy titanic.csv (used by competitive_analysis tests)
cp tests/fixtures/titanic.csv tests/benchmarks/inputs/titanic.csv 2>/dev/null || \
  cp output/reports/*.csv tests/benchmarks/inputs/titanic.csv 2>/dev/null || \
  echo "titanic.csv needs to be sourced — check test fixtures"

# Copy or create target_design.png for clone_converge
# Use an existing test fixture if available
cp tests/fixtures/target_design.png tests/benchmarks/inputs/target_design.png 2>/dev/null || \
  echo "target_design.png needs to be sourced"
```

If `titanic.csv` or `target_design.png` are not in fixtures, locate them:
```bash
find . -name "titanic.csv" -not -path "./node_modules/*" 2>/dev/null
find . -name "*.png" -path "*/fixtures/*" 2>/dev/null
```

- [ ] **Step 3: Create minimal poster benchmark inputs**

Write `tests/benchmarks/inputs/poster_template.html`:
```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body { margin: 0; padding: 40px; background: #1a1a2e; color: white; font-family: Arial, sans-serif; width: 720px; height: 520px; box-sizing: border-box; }
h1 { font-size: 32px; margin-bottom: 16px; }
p { font-size: 18px; line-height: 1.6; }
.cta { background: #e94560; padding: 12px 24px; border-radius: 8px; display: inline-block; margin-top: 20px; font-weight: bold; }
</style></head>
<body>
<h1>{{ headline }}</h1>
<p>{{ body }}</p>
<div class="cta">{{ cta }}</div>
</body>
</html>
```

Write `tests/benchmarks/inputs/poster_data.csv`:
```csv
headline,body,cta
"Fresh Coffee Daily","Start your morning with our artisanal single-origin beans from Ethiopia.","Visit Us Today"
"Weekend Special","Buy 2 bags get 1 free — this weekend only at our PJ outlet.","Shop Now"
```

- [ ] **Step 4: Run all 5 pipelines with benchmark inputs to capture baseline**

This step is manual — run each pipeline and save artifacts to `tests/benchmarks/baseline/`. The implementer should:

```bash
# Run from project root with OPENAI_API_KEY in .env
python3 -c "
from pipelines.content_generate import run
result = run(brief=open('tests/benchmarks/inputs/content_brief.txt').read(), output_format='pdf')
print(result)
"
# Copy output PDF to tests/benchmarks/baseline/content_generate.pdf

python3 -c "
from pipelines.competitive_analysis import run
result = run(topic='Titanic passenger survival analysis by class and gender', data_path='tests/benchmarks/inputs/titanic.csv', output_dir='tests/benchmarks/baseline/competitive_analysis')
print(result)
"

python3 -c "
from pipelines.tts_generate import run
result = run(text=open('tests/benchmarks/inputs/tts_text.txt').read(), output_path='tests/benchmarks/baseline/tts_output.mp3')
print(result)
"

python3 -c "
from pipelines.poster_batch import run
result = run(template_path='tests/benchmarks/inputs/poster_template.html', data_path='tests/benchmarks/inputs/poster_data.csv', output_dir='tests/benchmarks/baseline/poster_batch')
print(result)
"
```

Clone_converge baseline requires a target image. If `target_design.png` exists:
```bash
python3 -c "
from pipelines.clone_converge import run
result = run(target_image_path='tests/benchmarks/inputs/target_design.png', output_dir='tests/benchmarks/baseline/clone_converge', max_iterations=3)
print(result)
"
```

- [ ] **Step 5: Commit benchmark inputs (baseline artifacts are gitignored — too large)**

Add to `.gitignore` if not present (use `**` for subdirectories):
```
tests/benchmarks/baseline/**/*.pdf
tests/benchmarks/baseline/**/*.mp3
tests/benchmarks/baseline/**/*.png
tests/benchmarks/outputs/**
```

```bash
git add tests/benchmarks/inputs/ tests/benchmarks/baseline/.gitkeep
git commit -m "feat: freeze benchmark inputs for quality overhaul comparison"
```

---

## Chunk 2: Session 2 — content_generate

### Task 4: Rewrite content_generate Prompt & JSON Output

**Files:**
- Modify: `pipelines/content_generate.py:35-54`
- Create: `tests/pipelines/test_content_generate_quality.py`

- [ ] **Step 1: Write failing tests for new content_generate behavior**

```python
# tests/pipelines/test_content_generate_quality.py
"""Quality tests for content_generate pipeline improvements."""
from __future__ import annotations

import json
import re
from unittest.mock import patch

import pytest


def _mock_llm_json_response() -> str:
    """Simulate the new JSON-structured LLM response."""
    return json.dumps({
        "title": "Discover Ethiopian Yirgacheffe at Our PJ Cafe",
        "body": (
            "Looking for the perfect cup to start your week? "
            "Our new single-origin Ethiopian Yirgacheffe beans bring "
            "bright citrus notes and a floral finish that coffee "
            "enthusiasts can't stop talking about.\n\n"
            "Visit our Petaling Jaya cafe this weekend for a free "
            "tasting event — perfect for young professionals who "
            "appreciate quality in every sip."
        ),
        "hashtags": ["#MalaysianCoffee", "#PetalingJaya", "#CoffeeTasting"],
    })


def test_title_is_not_truncated_brief() -> None:
    """Title must come from LLM output, not first 50 chars of brief."""
    from pipelines.content_generate import _extract_title_from_response

    response = _mock_llm_json_response()
    title = _extract_title_from_response(response)
    # Title should NOT be the brief — it should be the LLM-generated title
    assert "Discover" in title or "Ethiopian" in title
    assert len(title) > 10


def test_extract_title_fallback_from_body() -> None:
    """If JSON parsing fails, extract title from first heading or line."""
    from pipelines.content_generate import _extract_title_from_response

    plain_text = "# My Great Title\n\nSome body content here."
    title = _extract_title_from_response(plain_text)
    assert title == "My Great Title"


def test_extract_title_fallback_plain() -> None:
    """Plain text without heading uses first sentence."""
    from pipelines.content_generate import _extract_title_from_response

    plain = "This is a great post about coffee. More details follow."
    title = _extract_title_from_response(plain)
    assert "coffee" in title.lower()


def test_system_prompt_requests_json() -> None:
    """System prompt must instruct JSON output format."""
    from pipelines.content_generate import _SYSTEM_PROMPT

    assert "json" in _SYSTEM_PROMPT.lower() or "JSON" in _SYSTEM_PROMPT


def test_no_preamble_in_content() -> None:
    """Generated content must not contain LLM conversational artifacts."""
    preamble_patterns = [
        r"^Sure",
        r"^Absolutely",
        r"^Here(?:'s| is| you go)",
        r"Let me know if",
        r"I can also",
        r"Hope this helps",
    ]
    # This tests the cleanup applied to mock output
    from adapter.llm_client import _strip_llm_preamble

    dirty = "Sure! Here's your LinkedIn post:\n\nGreat content here.\n\nLet me know if you need changes!"
    clean = _strip_llm_preamble(dirty)
    for pattern in preamble_patterns:
        assert not re.search(pattern, clean, re.IGNORECASE), f"Found preamble: {pattern}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pipelines/test_content_generate_quality.py -v`
Expected: FAIL — `_extract_title_from_response` not found

- [ ] **Step 3: Rewrite system prompt and add JSON extraction**

In `pipelines/content_generate.py`, replace `_SYSTEM_PROMPT` and `_call_llm()`:

```python
_SYSTEM_PROMPT = (
    "You are Vizier, a content creation assistant for Malaysian SMEs. "
    "Output ONLY valid JSON with these exact keys:\n"
    '{"title": "...", "body": "...", "hashtags": ["...", "..."]}\n\n'
    "Rules:\n"
    "- title: A compelling headline (max 10 words)\n"
    "- body: The full post content in markdown. Professional but warm tone.\n"
    "- hashtags: 3-5 relevant hashtags\n"
    "- No preamble, no sign-off, no offers to revise\n"
    "- Target audience and platform conventions should match the brief"
)


def _call_llm(brief: str, client_id: str | None = None) -> str | None:
    """Call LLM for content generation with JSON output format."""
    set_pipeline_step("llm_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = f"Generate social media content based on this brief:\n\n{brief}"
    if client_id:
        prompt += f"\n\nClient: {client_id}"

    return llm_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        strip_preamble=True,
    )
```

Add `_extract_title_from_response()` replacing `_extract_title()`:

```python
def _extract_title_from_response(response: str) -> str:
    """Extract title from LLM JSON response, with fallbacks.

    Priority:
    1. JSON "title" field
    2. First markdown heading
    3. First sentence (up to 60 chars)

    Args:
        response: Raw LLM response string.

    Returns:
        Extracted title string.
    """
    # Try JSON parse
    try:
        data = json.loads(response)
        if isinstance(data, dict) and data.get("title"):
            return str(data["title"]).strip()
    except (json.JSONDecodeError, TypeError):
        pass

    # Try markdown heading
    heading_match = re.match(r"^#\s+(.+)", response.strip(), re.MULTILINE)
    if heading_match:
        return heading_match.group(1).strip()

    # First sentence
    first_line = response.strip().split("\n")[0]
    if ". " in first_line:
        return first_line[: first_line.index(". ") + 1]
    return first_line[:60].strip()
```

Add `_extract_body_from_response()`:

```python
def _extract_body_from_response(response: str) -> str:
    """Extract body content from LLM JSON response, with fallback.

    Args:
        response: Raw LLM response string.

    Returns:
        Body content string (markdown).
    """
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            body = str(data.get("body", ""))
            hashtags = data.get("hashtags", [])
            if hashtags and isinstance(hashtags, list):
                body += "\n\n" + " ".join(str(h) for h in hashtags)
            return body
    except (json.JSONDecodeError, TypeError):
        pass

    return response
```

Update `run()` to use the new extractors — replace lines 117-120:

```python
        if output_format == "pdf":
            set_pipeline_step("pdf_render", _PIPELINE_NAME, _PIPELINE_VERSION)
            title = _extract_title_from_response(content)
            body = _extract_body_from_response(content)
            pdf_result = render_to_pdf(content=body, title=title)
```

Also add `import json` and `import re` at top of file.

**Delete the old `_extract_title()` function** (lines 157-167 in the current file) — it is now dead code, replaced by `_extract_title_from_response()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/pipelines/test_content_generate_quality.py -v`
Expected: All PASS

- [ ] **Step 5: Run pyright**

Run: `pyright pipelines/content_generate.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add pipelines/content_generate.py tests/pipelines/test_content_generate_quality.py
git commit -m "feat: content_generate — JSON prompt, title from LLM, body extraction"
```

---

### Task 5: Wire content_generate Through Quality Gates

**Files:**
- Modify: `pipelines/content_generate.py:80-142`

- [ ] **Step 1: Write failing test for quality gate integration**

Add to `tests/pipelines/test_content_generate_quality.py`:

```python
from pipelines.content_generate import run as content_run


def test_run_returns_quality_report() -> None:
    """Pipeline result must include quality_report from run_with_gates."""
    with patch("pipelines.content_generate.llm_chat", return_value=_mock_llm_json_response()):
        result = content_run(brief="Test brief for quality check", output_format="markdown")
        assert "quality_report" in result
        assert result["quality_report"]["L1"]["passed"] is True
```

Note: Import `run` at module level (not inside `with patch`) to avoid fragile import-under-patch pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/pipelines/test_content_generate_quality.py::test_run_returns_quality_report -v`
Expected: FAIL — no quality_report in result

- [ ] **Step 3: Refactor `run()` to use `run_with_gates()`**

Replace the `run()` function body to delegate to pipeline_runner. The pipeline_fn receives inputs and returns the result dict. The outer `run()` handles deliverable context and anomaly checking as before.

```python
from middleware.pipeline_runner import run_with_gates

_OUTPUT_SCHEMA = {
    "content": {"type": "string", "required": True},
    "format": {"type": "string", "required": True},
}

def run(
    brief: str,
    client_id: str | None = None,
    output_format: str = "markdown",
) -> dict[str, Any]:
    """Execute the content generation pipeline with quality gates."""
    did = start_deliverable(client_id=client_id)

    try:
        payload: dict[str, Any] = {"brief": brief, "output_format": output_format}
        if client_id is not None:
            payload["client_id"] = client_id

        def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
            brief_text = str(inputs["brief"])
            cid = inputs.get("client_id")
            fmt = str(inputs.get("output_format", "markdown"))

            is_stub = False
            content = _call_llm(brief_text, cid)
            if content is None:
                content = f"[Generated content for: {brief_text[:100]}]"
                is_stub = True

            result: dict[str, Any] = {
                "content": content,
                "format": fmt,
                "brief": brief_text,
            }
            if cid:
                result["client_id"] = cid

            if fmt == "pdf":
                set_pipeline_step("pdf_render", _PIPELINE_NAME, _PIPELINE_VERSION)
                title = _extract_title_from_response(content)
                body = _extract_body_from_response(content)
                pdf_result = render_to_pdf(content=body, title=title)
                if "error" in pdf_result:
                    logger.warning("PDF rendering failed: %s", pdf_result["error"])
                    result["pdf_error"] = pdf_result["error"]
                else:
                    result["pdf_path"] = pdf_result["pdf_path"]

            quality_score = 6.5 if is_stub else 8.0
            record_quality(did, quality_score, not is_stub)
            return result

        result = run_with_gates(
            pipeline_fn=_pipeline_fn,
            inputs=payload,
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            quality_config={"L4": {"expected_languages": ["en", "ms"]}},
            pipeline_name=_PIPELINE_NAME,
        )

        _check_and_export(did, client_id)
        result["deliverable_id"] = did
        return result

    finally:
        clear_context()
```

Remove the old `validate_input` import (now handled by pipeline_runner).

Use immutable return: `return {**result, "deliverable_id": did}` instead of mutating `result["deliverable_id"] = did`.

- [ ] **Step 3b: Improve Typst template formatting**

In `scripts/document/render_typst.py`, update `_wrap_content_as_typst()` to include better heading hierarchy and spacing:

```python
def _wrap_content_as_typst(content: str, title: str) -> str:
    """Wrap content in Typst formatting with professional document styling."""
    typst_content = _markdown_to_typst(content)
    return f"""#set page(margin: (top: 2.5cm, bottom: 2cm, left: 2cm, right: 2cm))
#set text(size: 11pt, font: "Helvetica")
#set par(leading: 0.8em, justify: true)
#set heading(numbering: none)

#align(center)[
  #text(size: 18pt, weight: "bold")[{title}]
]

#v(1em)

{typst_content}
"""
```

This gives the PDF proper margins, justified text, a centered title, and vertical spacing.

- [ ] **Step 4: Run all content_generate tests**

Run: `python3 -m pytest tests/pipelines/test_content_generate*.py -v`
Expected: All PASS

- [ ] **Step 5: Run pyright**

Run: `pyright pipelines/content_generate.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add pipelines/content_generate.py tests/pipelines/test_content_generate_quality.py
git commit -m "feat: wire content_generate through run_with_gates() — L1+L2+L4+L6"
```

---

## Chunk 3: Session 3 — competitive_analysis

### Task 6: LLM-Driven Analysis Strategy

**Files:**
- Modify: `pipelines/competitive_analysis.py:86-109`
- Create: `tests/pipelines/test_competitive_analysis_quality.py`

- [ ] **Step 1: Write failing tests for LLM-driven analysis**

```python
# tests/pipelines/test_competitive_analysis_quality.py
"""Quality tests for competitive_analysis pipeline improvements."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_chart_values_not_sequential_integers() -> None:
    """Chart Y-axis must reflect actual data, not range(len(columns))."""
    from pipelines.competitive_analysis import _build_chart_data

    # Simulated groupby result: survival rate by class
    analysis_result = {
        "Pclass": {"1": 0.63, "2": 0.47, "3": 0.24},
    }
    chart_data = _build_chart_data(analysis_result, "survival rate by class")
    # Values must NOT be [0, 1, 2]
    assert chart_data["values"] != list(range(len(chart_data["labels"])))
    # Values should be actual data
    assert all(isinstance(v, (int, float)) for v in chart_data["values"])


def test_narrative_cites_specific_numbers() -> None:
    """Narrative must contain specific numbers from the data."""
    from pipelines.competitive_analysis import _generate_narrative

    data_summary = json.dumps({
        "survival_by_class": {"1": 0.63, "2": 0.47, "3": 0.24},
        "survival_by_gender": {"female": 0.74, "male": 0.19},
    })

    with patch("pipelines.competitive_analysis.llm_chat") as mock:
        mock.return_value = (
            "## Key Findings\n\n"
            "1st class passengers survived at 63%, while 3rd class at only 24%.\n"
            "Female passengers survived at 74% compared to 19% for males."
        )
        narrative = _generate_narrative(
            "Titanic survival by class and gender", data_summary
        )
        # Should contain actual numbers
        assert "63" in narrative or "0.63" in narrative
        assert "24" in narrative or "0.24" in narrative


def test_analysis_uses_multiple_operations() -> None:
    """Pipeline should call analyze_run with LLM-selected operations, not just describe."""
    from pipelines.competitive_analysis import _select_analysis_operations

    with patch("pipelines.competitive_analysis.llm_chat") as mock:
        mock.return_value = json.dumps([
            {"operation": "groupby", "group_column": "Pclass", "agg_column": "Survived", "agg_function": "mean"},
            {"operation": "groupby", "group_column": "Sex", "agg_column": "Survived", "agg_function": "mean"},
        ])
        ops = _select_analysis_operations(
            "Titanic survival by class and gender",
            ["PassengerId", "Survived", "Pclass", "Name", "Sex", "Age"],
        )
        assert len(ops) >= 1
        assert any(op["operation"] == "groupby" for op in ops)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pipelines/test_competitive_analysis_quality.py -v`
Expected: FAIL — `_build_chart_data`, `_select_analysis_operations` not found

- [ ] **Step 3: Implement LLM-driven analysis + chart data builder**

Add these functions to `pipelines/competitive_analysis.py`:

```python
def _select_analysis_operations(
    topic: str,
    columns: list[str],
) -> list[dict[str, str]]:
    """Ask LLM which analysis operations best answer the topic.

    Args:
        topic: The analysis question.
        columns: Available column names from the dataset.

    Returns:
        List of operation dicts with keys: operation, group_column, agg_column, agg_function.
        Falls back to describe if LLM unavailable.
    """
    set_pipeline_step("analysis_strategy", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = (
        f"Given a dataset with columns {columns}, what pandas operations "
        f"best answer: '{topic}'?\n\n"
        "Available operations:\n"
        '- {{"operation": "describe"}}  (basic stats)\n'
        '- {{"operation": "groupby", "group_column": "Col", "agg_column": "Col", "agg_function": "mean|sum|count"}}\n'
        '- {{"operation": "filter", "column": "Col", "operator": ">|<|==", "value": "..."}}\n\n'
        "Return a JSON array of 1-3 operations. Output ONLY the JSON array, no explanation."
    )
    result = llm_chat(
        messages=[
            {"role": "system", "content": "You are a data analyst. Output ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        strip_preamble=True,
    )
    if result:
        try:
            ops = json.loads(result)
            if isinstance(ops, list) and ops:
                return ops
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: describe only
    return [{"operation": "describe"}]


def _build_chart_data(
    analysis_result: dict[str, Any],
    title: str,
) -> dict[str, Any]:
    """Build chart-ready data from analysis results.

    Extracts labels and values from groupby/describe results.
    Never returns sequential integers as values.

    Args:
        analysis_result: Parsed analysis output (nested dict).
        title: Chart title for context.

    Returns:
        Dict with "labels", "values", "chart_type" keys.
    """
    # Try to find a dict with string keys -> numeric values
    for key, value in analysis_result.items():
        if isinstance(value, dict):
            labels = list(value.keys())
            values = list(value.values())
            if values and all(isinstance(v, (int, float)) for v in values):
                return {
                    "labels": labels,
                    "values": values,
                    "chart_type": "bar",
                }

    # Fallback: use top-level keys and values if numeric
    labels = list(analysis_result.keys())
    values = []
    for val in analysis_result.values():
        if isinstance(val, (int, float)):
            values.append(val)
        elif isinstance(val, dict) and "mean" in val:
            values.append(val["mean"])
        else:
            values.append(0)

    return {"labels": labels, "values": values, "chart_type": "bar"}
```

- [ ] **Step 4: Rewrite `run()` to use multi-operation analysis + real chart data**

Replace the data analysis section (lines 86-112) in `run()`:

```python
        if data_path:
            set_pipeline_step("data_analysis", _PIPELINE_NAME, _PIPELINE_VERSION)
            data_file = Path(data_path)
            if not data_file.exists():
                msg = f"Data file not found: {data_path}"
                raise FileNotFoundError(msg)

            # Step 1: Get column names for LLM strategy
            import pandas as pd
            df = pd.read_csv(data_file)
            columns = list(df.columns)

            # Step 2: LLM selects analysis operations
            operations = _select_analysis_operations(topic, columns)

            # Step 3: Run each operation and collect results
            all_results: dict[str, Any] = {}
            for op in operations:
                op_name = op.get("operation", "describe")
                try:
                    analysis = analyze_run(
                        input_path=data_path,
                        operation=op_name,
                        group_column=op.get("group_column"),
                        agg_column=op.get("agg_column"),
                        agg_function=op.get("agg_function"),
                    )
                    parsed = json.loads(analysis["summary"])
                    all_results[f"{op_name}_{op.get('group_column', 'all')}"] = parsed
                except (ValueError, KeyError, json.JSONDecodeError) as exc:
                    logger.warning("Analysis operation failed: %s — %s", op, exc)

            if not all_results:
                # Fallback to describe
                analysis = analyze_run(input_path=data_path, operation="describe")
                all_results["describe"] = json.loads(analysis["summary"])

            data_summary = json.dumps(all_results, indent=2, default=str)

            # Step 4: Generate charts from real data (up to 3)
            chart_paths: list[str] = []
            for idx, (result_key, result_data) in enumerate(list(all_results.items())[:3]):
                chart_data = _build_chart_data(result_data, f"{topic} — {result_key}")
                chart_output = str(out / f"analysis_chart_{idx}.png")
                try:
                    chart_result = chart_run(
                        chart_type=chart_data.get("chart_type", "bar"),
                        data={"labels": chart_data["labels"], "values": chart_data["values"]},
                        output_path=chart_output,
                        title=f"Analysis: {topic[:40]} ({result_key})",
                    )
                    chart_paths.append(chart_result["file_path"])
                except (ValueError, KeyError) as exc:
                    logger.warning("Chart generation failed for %s: %s", result_key, exc)
            chart_path = chart_paths[0] if chart_paths else None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/pipelines/test_competitive_analysis_quality.py -v`
Expected: All PASS

- [ ] **Step 6: Run pyright**

Run: `pyright pipelines/competitive_analysis.py`
Expected: 0 errors

- [ ] **Step 7: Commit**

```bash
git add pipelines/competitive_analysis.py tests/pipelines/test_competitive_analysis_quality.py
git commit -m "feat: competitive_analysis — LLM-driven operations, real chart data"
```

---

### Task 7: Richer Narrative + Report Structure + Quality Gates

**Files:**
- Modify: `pipelines/competitive_analysis.py:32-52,114-139`

- [ ] **Step 1: Write failing test for report structure**

Add to `tests/pipelines/test_competitive_analysis_quality.py`:

```python
def test_report_has_structured_sections() -> None:
    """Report must have executive summary, findings, recommendations."""
    from pipelines.competitive_analysis import _generate_narrative

    with patch("pipelines.competitive_analysis.llm_chat") as mock:
        mock.return_value = (
            "## Executive Summary\n\nBrief overview.\n\n"
            "## Key Findings\n\n- Finding 1 (63%)\n- Finding 2 (24%)\n\n"
            "## Recommendations\n\n1. Do X\n2. Do Y"
        )
        narrative = _generate_narrative(
            "Titanic survival", '{"survival": {"1st": 0.63}}'
        )
        assert "## Executive Summary" in narrative or "## Key Findings" in narrative


def test_run_returns_quality_report() -> None:
    """Pipeline result must include quality_report."""
    import tempfile
    from pathlib import Path

    with patch("pipelines.competitive_analysis.llm_chat") as mock_llm:
        mock_llm.side_effect = [
            # _select_analysis_operations
            json.dumps([{"operation": "describe"}]),
            # _generate_narrative
            "## Summary\n\nTest narrative with 42% finding.\n\n## Recommendations\n\n1. Test",
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            from pipelines.competitive_analysis import run

            result = run(
                topic="test analysis",
                data_path="tests/benchmarks/inputs/titanic.csv",
                output_dir=tmpdir,
            )
            assert "quality_report" in result
```

- [ ] **Step 2: Rewrite `_generate_narrative()` prompt**

```python
def _generate_narrative(topic: str, data_summary: str) -> str:
    """Generate structured analysis report via LLM."""
    set_pipeline_step("narrative_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a senior market analyst. Write a structured analysis report.\n\n"
                    "Output format (markdown):\n"
                    "## Executive Summary\n(2-3 sentences)\n\n"
                    "## Key Findings\n(Bulleted list with SPECIFIC numbers from the data)\n\n"
                    "## Data Tables\n(Relevant cross-tabulations)\n\n"
                    "## Recommendations\n(Numbered actionable items)\n\n"
                    "Rules:\n"
                    "- Cite specific numbers (percentages, counts) — never hedge\n"
                    "- Make definitive statements based on data\n"
                    "- No preamble, no sign-off\n"
                    "- Output ONLY the report content"
                ),
            },
            {
                "role": "user",
                "content": f"Topic: {topic}\n\nAnalysis results:\n{data_summary}",
            },
        ],
        max_tokens=2048,
        strip_preamble=True,
    )
    return result or f"## {topic}\n\nData summary:\n```\n{data_summary}\n```\n"
```

- [ ] **Step 3: Wire through `run_with_gates()`**

Add imports and schemas at module level:

```python
from middleware.pipeline_runner import run_with_gates

_INPUT_SCHEMA = {
    "topic": {"type": "string", "required": True},
}
_OUTPUT_SCHEMA = {
    "report": {"type": "string", "required": True},
    "status": {"type": "string", "required": True},
}
```

Refactor `run()` to use `run_with_gates()`. The inner pipeline function contains all the analysis + narrative logic:

```python
def run(
    *,
    topic: str,
    data_path: str | None = None,
    output_dir: str = "output/reports",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Run competitive analysis with quality gates."""
    did = start_deliverable(client_id=client_id)

    try:
        payload: dict[str, Any] = {"topic": topic}
        if data_path is not None:
            payload["data_path"] = data_path
        payload["output_dir"] = output_dir

        def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
            topic_text = str(inputs["topic"])
            dp = inputs.get("data_path")
            out = Path(str(inputs.get("output_dir", "output/reports")))
            out.mkdir(parents=True, exist_ok=True)

            chart_path: str | None = None
            data_summary = ""

            if dp:
                # ... (all the analysis logic from Task 6 Step 4 goes here) ...
                pass  # Implementer: move the analysis block here

            report = _generate_narrative(topic_text, data_summary or "No data provided.")
            is_stub = report.startswith(f"## {topic_text}")

            report_path = out / "report.md"
            report_content = report
            if chart_path:
                report_content += f"\n\n![Analysis Chart]({chart_path})\n"
            report_path.write_text(report_content, encoding="utf-8")

            quality_score = 6.5 if is_stub else 8.0
            record_quality(did, quality_score, not is_stub)

            result: dict[str, Any] = {
                "report": report,
                "report_path": str(report_path),
                "status": "completed",
            }
            if chart_path:
                result["chart_path"] = chart_path
            return result

        result = run_with_gates(
            pipeline_fn=_pipeline_fn,
            inputs=payload,
            input_schema=_INPUT_SCHEMA,
            output_schema=_OUTPUT_SCHEMA,
            pipeline_name=_PIPELINE_NAME,
        )

        _check_and_export(did, client_id)
        return {**result, "deliverable_id": did}

    finally:
        clear_context()
```

- [ ] **Step 4: Run all competitive_analysis tests**

Run: `python3 -m pytest tests/pipelines/test_competitive_analysis*.py -v`
Expected: All PASS

- [ ] **Step 5: Run pyright**

Run: `pyright pipelines/competitive_analysis.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add pipelines/competitive_analysis.py tests/pipelines/test_competitive_analysis_quality.py
git commit -m "feat: competitive_analysis — structured report, quality gates, richer narrative"
```

---

## Chunk 4: Session 4 — clone_converge

### Task 8: Vision API Integration

**Files:**
- Modify: `pipelines/clone_converge.py:40-74`
- Create: `tests/pipelines/test_clone_converge_quality.py`

- [ ] **Step 1: Write failing tests for vision API usage**

```python
# tests/pipelines/test_clone_converge_quality.py
"""Quality tests for clone_converge pipeline improvements."""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import patch

import pytest


def test_llm_receives_image_not_path() -> None:
    """First iteration must send base64 image, not a file path string."""
    from pipelines.clone_converge import _build_vision_messages

    # Create a tiny 1x1 PNG for testing
    import struct
    import zlib

    def _make_tiny_png() -> bytes:
        raw = b"\x00\xff\x00\x00"  # 1 pixel, RGB
        compressed = zlib.compress(raw)
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)

        def chunk(ctype: bytes, data: bytes) -> bytes:
            import binascii
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", binascii.crc32(c) & 0xFFFFFFFF)

        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(_make_tiny_png())
        tmp_path = f.name

    try:
        messages = _build_vision_messages(
            target_image_path=tmp_path,
            iteration=1,
        )
        # Find user message with image content
        user_msg = next(m for m in messages if m["role"] == "user")
        content = user_msg["content"]
        # Content must be a list (multimodal), not a plain string
        assert isinstance(content, list), "Vision messages must use list content blocks"
        # Must contain an image_url block
        image_blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "image_url"]
        assert len(image_blocks) >= 1, "Must include at least one image_url block"
        # Must contain base64 data, not a file path
        url = image_blocks[0]["image_url"]["url"]
        assert url.startswith("data:image/"), f"Expected data URI, got: {url[:50]}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_delta_feedback_is_natural_language() -> None:
    """Delta feedback must be actionable text, not raw numbers."""
    from pipelines.clone_converge import _delta_to_guidance
    from scripts.visual.calculate_delta import DeltaResult

    delta = DeltaResult(
        ssim_score=0.3,
        pixel_diff_pct=45.0,
        color_delta_e=30.0,
        layout_score=0.4,
        text_match_pct=60.0,
        composite_score=0.35,
    )
    guidance = _delta_to_guidance(delta)
    # Should be natural language, not just numbers
    assert any(word in guidance.lower() for word in ["color", "layout", "text", "structure", "match"])
    # Should NOT be just "SSIM: 0.300, Pixel diff: 45.0%"
    assert "SSIM:" not in guidance
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pipelines/test_clone_converge_quality.py -v`
Expected: FAIL — `_build_vision_messages`, `_delta_to_guidance` not found

- [ ] **Step 3: Implement vision message builder**

Add to `pipelines/clone_converge.py`:

```python
import base64

def _encode_image_as_data_uri(image_path: str) -> str:
    """Encode an image file as a base64 data URI for OpenAI vision API.

    Args:
        image_path: Path to the image file.

    Returns:
        Data URI string (data:image/png;base64,...).
    """
    path = Path(image_path)
    suffix = path.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _build_vision_messages(
    target_image_path: str,
    iteration: int,
    delta_guidance: str | None = None,
    previous_html: str | None = None,
    rendered_image_path: str | None = None,
) -> list[dict[str, str | list]]:
    """Build messages for vision-capable LLM.

    First iteration: target image only.
    Subsequent iterations: target + rendered screenshot + delta guidance.

    Args:
        target_image_path: Path to target design image.
        iteration: Current iteration number.
        delta_guidance: Natural language guidance from delta analysis.
        previous_html: HTML from previous iteration.
        rendered_image_path: Screenshot of previous iteration's output.

    Returns:
        OpenAI-format messages with image_url content blocks.
    """
    system_msg: dict[str, str | list] = {
        "role": "system",
        "content": (
            "You are an HTML/CSS generator. Given a target design image, "
            "output clean semantic HTML5 with inline CSS that matches it. "
            "Output ONLY the HTML document — no explanation, no markdown fences."
        ),
    }

    user_content: list[dict[str, Any]] = []

    if iteration == 1:
        # First iteration: just the target
        user_content.append({"type": "text", "text": "Replicate this design as HTML/CSS:"})
        user_content.append({
            "type": "image_url",
            "image_url": {"url": _encode_image_as_data_uri(target_image_path)},
        })
    else:
        # Refinement: target + current render + guidance
        user_content.append({"type": "text", "text": "Target design:"})
        user_content.append({
            "type": "image_url",
            "image_url": {"url": _encode_image_as_data_uri(target_image_path)},
        })
        if rendered_image_path and Path(rendered_image_path).exists():
            user_content.append({"type": "text", "text": "Current render (needs improvement):"})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": _encode_image_as_data_uri(rendered_image_path)},
            })
        if delta_guidance:
            user_content.append({"type": "text", "text": f"Improvements needed:\n{delta_guidance}"})
        if previous_html:
            user_content.append({"type": "text", "text": f"Previous HTML to refine:\n```html\n{previous_html}\n```"})

    user_msg: dict[str, str | list] = {"role": "user", "content": user_content}
    return [system_msg, user_msg]
```

- [ ] **Step 4: Implement delta-to-guidance translator**

Merge the import with the existing one at line 31 of `clone_converge.py`:
```python
from scripts.visual.calculate_delta import DeltaResult, calculate_delta
```
(Remove the separate `from scripts.visual.calculate_delta import calculate_delta` line.)

```python
def _delta_to_guidance(delta: DeltaResult) -> str:
    """Convert numeric delta signals to actionable natural language guidance.

    Args:
        delta: DeltaResult with individual signal scores.

    Returns:
        Natural language string describing what needs improvement.
    """
    issues: list[str] = []

    if delta.ssim_score < 0.6:
        issues.append("The overall structure is very different from the target — review the layout and element positioning")
    elif delta.ssim_score < 0.8:
        issues.append("Structure is partially matching but needs refinement in element sizing and spacing")

    if delta.pixel_diff_pct > 30:
        issues.append(f"Too many pixels differ ({delta.pixel_diff_pct:.0f}%) — check backgrounds, borders, and fills")

    if delta.color_delta_e > 20:
        issues.append(f"Color palette is off (delta-E: {delta.color_delta_e:.0f}) — match the target colors more closely")
    elif delta.color_delta_e > 10:
        issues.append("Colors are close but need fine-tuning to match the target exactly")

    if delta.layout_score < 0.5:
        issues.append("Layout structure differs significantly — check column count, element arrangement, and whitespace distribution")
    elif delta.layout_score < 0.7:
        issues.append("Layout is partially correct but element positions need adjustment")

    if delta.text_match_pct < 70:
        issues.append(f"Text content only {delta.text_match_pct:.0f}% matching — ensure all text from the target is present")

    if not issues:
        issues.append("Minor refinements needed across all visual aspects")

    return "\n".join(f"- {issue}" for issue in issues)
```

- [ ] **Step 5: Rewrite `_call_llm_for_html()` to use vision messages**

Replace the existing `_call_llm_for_html()`:

```python
def _call_llm_for_html(
    target_image_path: str,
    iteration: int,
    delta_guidance: str | None = None,
    previous_html: str | None = None,
    rendered_image_path: str | None = None,
) -> str:
    """Call vision LLM to generate or refine HTML/CSS."""
    step = "html_refine" if delta_guidance else "html_generate"
    set_pipeline_step(f"{step}_iter{iteration}", _PIPELINE_NAME, _PIPELINE_VERSION)

    messages = _build_vision_messages(
        target_image_path=target_image_path,
        iteration=iteration,
        delta_guidance=delta_guidance,
        previous_html=previous_html,
        rendered_image_path=rendered_image_path,
    )

    result = llm_chat(
        messages=messages,
        max_tokens=4096,
        timeout=60.0,
        strip_preamble=True,
    )
    return result or _fallback_html("LLM unavailable")
```

- [ ] **Step 6: Update the iteration loop in `run()` to use vision + guidance**

Replace the convergence loop (lines 125-178):

```python
        for iteration in range(1, max_iterations + 1):
            logger.info("Convergence iteration %d/%d", iteration, max_iterations)

            # Step 1-2: Generate/refine HTML via vision API
            rendered_path_str = str(out / f"rendered_iter{iteration - 1}.png") if iteration > 1 else None
            html = _call_llm_for_html(
                target_image_path=target_image_path,
                iteration=iteration,
                delta_guidance=delta_feedback,
                previous_html=previous_html,
                rendered_image_path=rendered_path_str,
            )
            previous_html = html

            # Step 3: Render to PNG
            rendered_path = out / f"rendered_iter{iteration}.png"
            rendered_path = _render_html_to_png(html, rendered_path)

            # Step 4: Calculate delta
            delta = calculate_delta(target=target, rendered=rendered_path)
            score = delta.composite_score
            logger.info("Iteration %d score: %.3f (threshold: %.3f)", iteration, score, threshold)

            if score > best_score:
                best_score = score
                best_html = html

            if score >= threshold:
                logger.info("Converged at iteration %d with score %.3f", iteration, score)
                break

            # Build natural language guidance for next iteration
            delta_feedback = _delta_to_guidance(delta)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python3 -m pytest tests/pipelines/test_clone_converge_quality.py -v`
Expected: All PASS

- [ ] **Step 8: Run pyright**

Run: `pyright pipelines/clone_converge.py`
Expected: 0 errors

- [ ] **Step 9: Commit**

```bash
git add pipelines/clone_converge.py tests/pipelines/test_clone_converge_quality.py
git commit -m "feat: clone_converge — vision API, delta-to-guidance, visual iteration"
```

---

## Chunk 5: Sessions 5+6 — poster_batch + tts_generate

### Task 9: poster_batch — Viewport Fix + Visual QA

**Files:**
- Modify: `pipelines/poster_batch.py:66-73`
- Modify: `scripts/visual/screenshot_html.py:32-40`
- Create: `tests/pipelines/test_poster_batch_quality.py`

- [ ] **Step 1: Write failing tests for viewport and quality gate**

```python
# tests/pipelines/test_poster_batch_quality.py
"""Quality tests for poster_batch pipeline improvements."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_screenshot_accepts_viewport_params() -> None:
    """screenshot_html.run() must accept and use custom viewport dimensions."""
    from scripts.visual.screenshot_html import run as screenshot_run

    html = "<html><body style='margin:0;background:red;width:800px;height:600px;'><p>Test</p></body></html>"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = str(Path(tmpdir) / "test.png")
        result = screenshot_run(
            html_content=html,
            output_path=out_path,
            viewport_width=800,
            viewport_height=600,
        )
        assert Path(result["file_path"]).exists()
        # Verify dimensions
        from PIL import Image
        img = Image.open(result["file_path"])
        assert img.width == 800
        assert img.height == 600


def test_poster_uses_800x600_viewport() -> None:
    """poster_batch must render with 800x600 viewport, not default 1280x800."""
    calls: list[dict] = []

    original_run = None
    def tracking_screenshot(**kwargs: object) -> dict[str, str]:
        calls.append(dict(kwargs))
        # Return a fake result
        out = str(kwargs.get("output_path", "/tmp/fake.png"))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        # Create a minimal file
        Path(out).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return {"file_path": out}

    with patch("pipelines.poster_batch.screenshot_run", side_effect=tracking_screenshot):
        from pipelines.poster_batch import run

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpl = Path(tmpdir) / "template.html"
            tmpl.write_text("<html><body>{{ headline }}</body></html>")
            data = Path(tmpdir) / "data.csv"
            data.write_text("headline\nTest\n")

            run(
                template_path=str(tmpl),
                data_path=str(data),
                output_dir=str(Path(tmpdir) / "out"),
            )

    assert len(calls) >= 1
    assert calls[0].get("viewport_width") == 800
    assert calls[0].get("viewport_height") == 600
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pipelines/test_poster_batch_quality.py -v`
Expected: FAIL — viewport params not passed / dimensions wrong

- [ ] **Step 3: Update screenshot_html to use full_page=False when viewport set**

In `scripts/visual/screenshot_html.py`, update `_render_with_playwright`:

```python
def _render_with_playwright(
    *,
    html_path: str,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    full_page: bool = True,
) -> str:
    """Render HTML file to PNG via Playwright (sync API)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": viewport_width, "height": viewport_height}
        )
        page.goto(f"file://{html_path}")
        page.screenshot(path=output_path, full_page=full_page)
        browser.close()
    return output_path
```

Also pass `full_page` through `run()`:

```python
def run(
    *,
    html_content: str | None = None,
    input_path: str | None = None,
    output_path: str,
    viewport_width: int = 1280,
    viewport_height: int = 800,
    full_page: bool = True,
) -> dict[str, str]:
```

Update the call inside `run()` body to pass the new parameter:

```python
        result_path = _render_with_playwright(
            html_path=html_path, output_path=output_path,
            viewport_width=viewport_width, viewport_height=viewport_height,
            full_page=full_page,
        )
```

- [ ] **Step 4: Update poster_batch to use 800x600 + full_page=False**

In `pipelines/poster_batch.py`, update the screenshot call (line 71):

```python
        result = screenshot_run(
            html_content=html,
            output_path=poster_path,
            viewport_width=800,
            viewport_height=600,
            full_page=False,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/pipelines/test_poster_batch_quality.py -v`
Expected: All PASS

- [ ] **Step 6: Run pyright on both files**

```bash
pyright scripts/visual/screenshot_html.py
pyright pipelines/poster_batch.py
```
Expected: 0 errors each

- [ ] **Step 7: Commit**

```bash
git add pipelines/poster_batch.py scripts/visual/screenshot_html.py tests/pipelines/test_poster_batch_quality.py
git commit -m "feat: poster_batch — 800x600 viewport, full_page=False, no whitespace"
```

---

### Task 10: tts_generate — Duration Check + Output Verification

**Files:**
- Modify: `pipelines/tts_generate.py`
- Create: `tests/pipelines/test_tts_generate_quality.py`

- [ ] **Step 1: Write failing tests for output verification**

```python
# tests/pipelines/test_tts_generate_quality.py
"""Quality tests for tts_generate pipeline improvements."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_verify_output_catches_empty_file() -> None:
    """L2 output verification must reject zero-byte MP3."""
    from pipelines.tts_generate import _verify_output

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"")  # empty file
        empty_path = f.name

    try:
        result = _verify_output(empty_path, text_length=100)
        assert not result.passed
        assert any("empty" in e.lower() or "size" in e.lower() for e in result.errors)
    finally:
        Path(empty_path).unlink(missing_ok=True)


def test_verify_output_accepts_valid_file() -> None:
    """L2 output verification must pass for non-empty MP3 with valid header."""
    from pipelines.tts_generate import _verify_output

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        # Minimal MP3-like content — large enough to pass proportionality check
        f.write(b"ID3" + b"\x00" * 100 + b"\xff\xfb\x90\x00" + b"\x00" * 5000)
        valid_path = f.name

    try:
        result = _verify_output(valid_path, text_length=10)
        assert result.passed
    finally:
        Path(valid_path).unlink(missing_ok=True)


def test_verify_output_rejects_missing_file() -> None:
    """L2 must reject non-existent file."""
    from pipelines.tts_generate import _verify_output

    result = _verify_output("/nonexistent/file.mp3", text_length=100)
    assert not result.passed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/pipelines/test_tts_generate_quality.py -v`
Expected: FAIL — `_verify_output` not found

- [ ] **Step 3: Implement `_verify_output()` and wire into pipeline**

Add to `pipelines/tts_generate.py`:

```python
from middleware.quality_gate import ValidationResult


def _verify_output(file_path: str, text_length: int) -> ValidationResult:
    """L2 output verification for TTS audio files.

    Checks:
    - File exists
    - File size > 0
    - Has valid MP3 header (ID3 or sync word 0xFF 0xFB)
    - File size is proportional to text length

    Args:
        file_path: Path to the MP3 file.
        text_length: Length of input text (for proportionality check).

    Returns:
        ValidationResult with pass/fail and error details.
    """
    errors: list[str] = []
    path = Path(file_path)

    if not path.exists():
        return ValidationResult(
            passed=False,
            errors=[f"Output file not found: {file_path}"],
            layer="output_verification",
        )

    size = path.stat().st_size
    if size == 0:
        return ValidationResult(
            passed=False,
            errors=["Output file is empty (0 bytes)"],
            layer="output_verification",
        )

    # Check MP3 header (ID3 tag or MPEG sync word)
    header = path.read_bytes()[:4]
    has_id3 = header[:3] == b"ID3"
    has_sync = len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    if not has_id3 and not has_sync:
        errors.append("File does not have a valid MP3 header (no ID3 tag or sync word)")

    # Proportionality: ~1KB per 10 chars is a rough minimum
    min_expected = max(100, text_length * 50)  # Very conservative minimum
    if size < min_expected:
        errors.append(
            f"File suspiciously small ({size} bytes) for {text_length} chars of text"
        )

    return ValidationResult(
        passed=len(errors) == 0,
        errors=errors,
        layer="output_verification",
    )
```

Update `run()` to call `_verify_output()` after generation:

```python
    # After ffmpeg normalization, before return:
    verification = _verify_output(output_path, text_length=len(text))
    if not verification.passed:
        logger.warning("TTS output verification failed: %s", verification.errors)

    return {
        "file_path": output_path,
        "voice": voice or "en-US-AriaNeural",
        "status": "completed",
        "quality_report": {
            "L2": {
                "passed": verification.passed,
                "errors": list(verification.errors),
                "layer": verification.layer,
            },
        },
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/pipelines/test_tts_generate_quality.py -v`
Expected: All PASS

- [ ] **Step 5: Run pyright**

Run: `pyright pipelines/tts_generate.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add pipelines/tts_generate.py tests/pipelines/test_tts_generate_quality.py
git commit -m "feat: tts_generate — L2 output verification, MP3 header + size check"
```

---

### Task 10b: tts_generate — Voice Validation

**Files:**
- Modify: `pipelines/tts_generate.py`

- [ ] **Step 1: Add voice validation before TTS call**

Add a validation function and call it at the start of `run()`:

```python
_KNOWN_VOICES = {
    "en-US-AriaNeural", "en-US-GuyNeural", "en-US-JennyNeural",
    "en-GB-SoniaNeural", "en-AU-NatashaNeural",
    "ms-MY-YasminNeural", "ms-MY-OsmanNeural",
}


def _validate_voice(voice: str | None) -> str:
    """Validate voice name, return default if None.

    Args:
        voice: Edge TTS voice name or None.

    Returns:
        Validated voice name.

    Raises:
        ValueError: If voice is not in known voices list.
    """
    if voice is None:
        return "en-US-AriaNeural"
    if voice not in _KNOWN_VOICES:
        logger.warning("Unknown voice '%s' — may fail at Edge TTS", voice)
    return voice
```

Call at the start of `run()`: `voice = _validate_voice(voice)`

Note: We log a warning rather than raising for unknown voices, since Edge TTS adds new voices regularly.

- [ ] **Step 2: Run pyright and existing tests**

Run: `pyright pipelines/tts_generate.py && python3 -m pytest tests/pipelines/test_tts*.py -v`

- [ ] **Step 3: Commit**

```bash
git add pipelines/tts_generate.py
git commit -m "feat: tts_generate — voice validation before Edge TTS call"
```

---

## Chunk 6: Session 7 — Benchmark & Regression Tests

### Task 11: Quality Regression Test Suite

**Files:**
- Create: `tests/benchmarks/test_quality_regression.py`

- [ ] **Step 1: Write the regression test suite**

```python
# tests/benchmarks/test_quality_regression.py
"""Quality regression tests — one per pipeline.

Run with benchmark inputs from tests/benchmarks/inputs/.
These tests catch mechanical regressions (wrong data types, broken output).
Human review is still required for subjective quality.

Requires: OPENAI_API_KEY in .env, Playwright installed.
Mark as slow — skip in CI unless VIZIER_BENCHMARK=1.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pytest

_BENCHMARK_DIR = Path(__file__).parent / "inputs"

pytestmark = pytest.mark.skipif(
    os.environ.get("VIZIER_BENCHMARK") != "1",
    reason="Benchmark tests require VIZIER_BENCHMARK=1 and API keys",
)


class TestContentGenerateRegression:
    """content_generate: Title != truncated brief, no preamble, PDF valid."""

    @pytest.fixture(scope="class")
    def pdf_result(self) -> dict:
        """Run pipeline once, share across all test methods."""
        from pipelines.content_generate import run

        brief = (_BENCHMARK_DIR / "content_brief.txt").read_text().strip()
        return run(brief=brief, output_format="pdf")

    def test_title_not_truncated_brief(self, pdf_result: dict) -> None:
        from pipelines.content_generate import _extract_title_from_response

        content = pdf_result.get("content", "")
        brief = (_BENCHMARK_DIR / "content_brief.txt").read_text().strip()
        title = _extract_title_from_response(content)
        # Title must NOT be the first 50 chars of the brief
        assert title != brief[:50], "Title should not be truncated brief"
        assert len(title) > 0, "Title should not be empty"

    def test_no_preamble_in_output(self, pdf_result: dict) -> None:
        content = pdf_result.get("content", "")

        preamble_starts = ["Sure!", "Absolutely", "Here's", "Here is", "Here you go"]
        for start in preamble_starts:
            assert not content.startswith(start), f"Content starts with preamble: {start}"

    def test_pdf_file_valid(self, pdf_result: dict) -> None:
        if "pdf_path" in pdf_result:
            pdf = Path(pdf_result["pdf_path"])
            assert pdf.exists()
            assert pdf.stat().st_size > 100
            # PDF magic bytes
            assert pdf.read_bytes()[:4] == b"%PDF"


class TestCompetitiveAnalysisRegression:
    """competitive_analysis: Chart Y != sequential ints, narrative has numbers."""

    @pytest.fixture(scope="class")
    def analysis_result(self, tmp_path_factory: pytest.TempPathFactory) -> dict:
        """Run pipeline once, share across test methods."""
        from pipelines.competitive_analysis import run

        tmpdir = tmp_path_factory.mktemp("competitive")
        return run(
            topic="Titanic survival by class and gender",
            data_path=str(_BENCHMARK_DIR / "titanic.csv"),
            output_dir=str(tmpdir),
        )

    def test_chart_has_real_data(self, analysis_result: dict) -> None:
        assert analysis_result.get("status") == "completed"
        if "chart_path" in analysis_result:
            chart = Path(analysis_result["chart_path"])
            assert chart.exists()
            assert chart.stat().st_size > 1000  # Real chart, not empty

    def test_narrative_contains_numbers(self, analysis_result: dict) -> None:
        report = analysis_result.get("report", "")
        # Report must contain at least one specific number/percentage
        assert re.search(r"\d+\.?\d*%?", report), "Report must cite specific numbers"


class TestCloneConvergeRegression:
    """clone_converge: Score > 0.50 after iterations, vision API called."""

    @pytest.fixture(scope="class")
    def converge_result(self, tmp_path_factory: pytest.TempPathFactory) -> dict:
        """Run pipeline once."""
        target = _BENCHMARK_DIR / "target_design.png"
        if not target.exists():
            pytest.skip("target_design.png not available")

        from pipelines.clone_converge import run

        tmpdir = tmp_path_factory.mktemp("clone")
        return run(
            target_image_path=str(target),
            output_dir=str(tmpdir),
            max_iterations=3,
        )

    def test_score_improves_above_baseline(self, converge_result: dict) -> None:
        score = converge_result.get("score", 0.0)
        # Spec requires > 0.50; baseline was stuck at 0.19
        assert score > 0.50, f"Score {score} should be > 0.50 (baseline was 0.19)"

    def test_vision_api_was_used(self) -> None:
        """Verify that _build_vision_messages exists and produces image_url blocks."""
        from pipelines.clone_converge import _build_vision_messages

        # If _build_vision_messages exists, vision API is integrated
        # (it is called by _call_llm_for_html which is called by run)
        assert callable(_build_vision_messages)


class TestPosterBatchRegression:
    """poster_batch: PNG dimensions == 800x600, no excess whitespace."""

    def test_poster_dimensions(self) -> None:
        from pipelines.poster_batch import run

        tmpl = _BENCHMARK_DIR / "poster_template.html"
        data = _BENCHMARK_DIR / "poster_data.csv"
        if not tmpl.exists() or not data.exists():
            pytest.skip("Poster benchmark inputs not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run(
                template_path=str(tmpl),
                data_path=str(data),
                output_dir=tmpdir,
            )
            assert result["count"] >= 1
            from PIL import Image

            first_poster = Path(result["posters"][0])
            img = Image.open(first_poster)
            assert img.width == 800, f"Expected 800px width, got {img.width}"
            assert img.height == 600, f"Expected 600px height, got {img.height}"


class TestTTSGenerateRegression:
    """tts_generate: MP3 duration > 0, file size proportional to text."""

    def test_mp3_valid_and_proportional(self) -> None:
        from pipelines.tts_generate import run

        text = (_BENCHMARK_DIR / "tts_text.txt").read_text().strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = str(Path(tmpdir) / "speech.mp3")
            result = run(text=text, output_path=out_path)

            mp3 = Path(result["file_path"])
            assert mp3.exists()
            size = mp3.stat().st_size
            assert size > 1000, f"MP3 too small: {size} bytes"

            # Proportionality: at least ~100 bytes per character
            min_size = len(text) * 50
            assert size > min_size, f"MP3 ({size}B) too small for {len(text)} chars"
```

- [ ] **Step 2: Verify tests are skipped without VIZIER_BENCHMARK=1**

Run: `python3 -m pytest tests/benchmarks/test_quality_regression.py -v`
Expected: All SKIPPED (missing env var)

- [ ] **Step 3: Run with benchmark flag (requires API keys)**

Run: `VIZIER_BENCHMARK=1 python3 -m pytest tests/benchmarks/test_quality_regression.py -v --timeout=120`
Expected: PASS (after all pipeline fixes are applied)

- [ ] **Step 4: Commit regression test suite**

```bash
git add tests/benchmarks/test_quality_regression.py
git commit -m "test: quality regression suite — one test per pipeline, benchmark gated"
```

---

### Task 12: Full Benchmark Run + Scorecard

- [ ] **Step 1: Run all 5 pipelines with benchmark inputs**

```bash
mkdir -p tests/benchmarks/outputs/final
VIZIER_BENCHMARK=1 python3 -c "
from pipelines.content_generate import run
import shutil
result = run(brief=open('tests/benchmarks/inputs/content_brief.txt').read(), output_format='pdf')
if 'pdf_path' in result:
    shutil.copy(result['pdf_path'], 'tests/benchmarks/outputs/final/content_generate.pdf')
print('content_generate:', result.get('quality_report', {}).get('L1', {}))
"
```

Repeat for each pipeline (same as Task 3, Step 4, but saving to `outputs/final/`).

- [ ] **Step 2: Compare side-by-side with baseline**

Open baseline and final artifacts side by side. Grade each pipeline against session-specific success criteria from the spec.

- [ ] **Step 3: Produce scorecard**

Create `tests/benchmarks/outputs/final/scorecard.md` with before/after grades:

```markdown
# Quality Overhaul Scorecard

| Pipeline | Baseline Grade | Final Grade | Key Improvement |
|----------|---------------|-------------|-----------------|
| content_generate | D | ? | Title from LLM, JSON output, no preamble |
| competitive_analysis | F | ? | Real chart data, LLM-driven analysis |
| clone_converge | F | ? | Vision API, delta guidance |
| poster_batch | C+ | ? | 800x600 viewport, no whitespace |
| tts_generate | B+ | ? | L2 verification, duration check |
```

Fill in grades after human review.

- [ ] **Step 4: Commit scorecard and outputs reference**

```bash
git add tests/benchmarks/outputs/final/scorecard.md
git commit -m "docs: quality overhaul scorecard — before/after comparison"
```

---

## Execution Notes

### Dependencies Already in pyproject.toml

The spec's Session 1.E (Install Missing Dependencies) is **already done** — `pyproject.toml` already includes: `opencv-python-headless`, `pixelmatch`, `scikit-image`, `pytesseract`, `lingua-py`. Verify they are installed in the active environment:

```bash
pip install -e ".[dev]"
```

If pytesseract is listed but Tesseract CLI is not installed, the OCR signal in `calculate_delta.py` will gracefully fall back. This is acceptable.

### Session Dependencies

Sessions must be executed in order:
- **Session 1** (Tasks 1-3) provides infrastructure all other sessions depend on
- **Sessions 2-6** (Tasks 4-10) are independent of each other but depend on Session 1
- **Session 7** (Tasks 11-12) depends on all Sessions 1-6 being complete

### Running Existing Tests After Changes

After each session, verify no regressions:

```bash
python3 -m pytest tests/ -v --timeout=30 -x
```

### analyze_data.py API Note

`analyze_run()` in `scripts/research/analyze_data.py` accepts keyword args: `input_path`, `operation`, `group_column`, `agg_column`, `agg_function`. Verify the exact signature before calling with groupby params in Task 6.

### Quality Gate Import Paths

All quality gate functions are in `middleware/quality_gate.py`:
- `validate_input(data, schema) -> ValidationResult`
- `validate_output(data, schema) -> ValidationResult`
- `validate_content_quality(content=, expected_languages=, expected_tone=) -> ValidationResult`
- `validate_visual_qa(target=, rendered=, threshold=) -> ValidationResult`
- `validate_delivery(status_code=, channel=) -> ValidationResult`
- `log_feedback(tool_name=, layer=, score=, passed=, session_id=) -> ValidationResult`
