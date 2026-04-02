# Artifact Quality Overhaul v2 — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite all 5 pipelines to produce client-ready outputs for Telegram/WhatsApp delivery, replace hardcoded quality scores with property-based scoring, and extract shared env loading.

**Architecture:** Bottom-up — build shared foundations first (env_loader, quality_scorer), then modify each pipeline independently. Each pipeline ships with its own scorer integration and updated tests.

**Tech Stack:** Python 3.11+, pytest, httpx, Jinja2, Playwright, fal.ai, Typst, edge-tts, matplotlib, Pillow

**Spec:** `docs/superpowers/specs/2026-04-02-artifact-quality-overhaul-v2-design.md`

---

## Chunk 1: Foundations

### Task 1: Extract shared .env loader (`adapter/env_loader.py`)

**Files:**
- Create: `adapter/env_loader.py`
- Modify: `adapter/llm_client.py:24-35`
- Modify: `scripts/visual/generate_image.py:41` (add ensure_env call)
- Create: `tests/adapter/test_env_loader.py`

- [ ] **Step 1: Write failing tests for env_loader**

```python
# tests/adapter/test_env_loader.py
"""Tests for adapter/env_loader.py — shared .env loading."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from adapter.env_loader import ensure_env


@pytest.fixture(autouse=True)
def _reset_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the _loaded flag between tests."""
    import adapter.env_loader as mod
    monkeypatch.setattr(mod, "_loaded", False)


class TestEnsureEnv:
    def test_loads_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_XYZ=hello\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("TEST_VAR_XYZ", raising=False)

        ensure_env()

        assert os.environ["TEST_VAR_XYZ"] == "hello"

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("IDEM_VAR=first\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("IDEM_VAR", raising=False)

        ensure_env()
        env_file.write_text("IDEM_VAR=second\n")
        ensure_env()  # Should not re-read

        assert os.environ["IDEM_VAR"] == "first"

    def test_does_not_overwrite_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=from_file\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.setenv("EXISTING_VAR", "from_env")

        ensure_env()

        assert os.environ["EXISTING_VAR"] == "from_env"

    def test_strips_quotes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('QUOTED_VAR="hello world"\nSINGLE_Q=\'value\'\n')
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("QUOTED_VAR", raising=False)
        monkeypatch.delenv("SINGLE_Q", raising=False)

        ensure_env()

        assert os.environ["QUOTED_VAR"] == "hello world"
        assert os.environ["SINGLE_Q"] == "value"

    def test_skips_comments_and_blank_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nVALID_KEY=yes\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("VALID_KEY", raising=False)

        ensure_env()

        assert os.environ["VALID_KEY"] == "yes"

    def test_missing_env_file_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / "nonexistent.env"
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)

        ensure_env()  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/adapter/test_env_loader.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement env_loader**

```python
# adapter/env_loader.py
"""Load .env file from project root into os.environ. Idempotent."""
from __future__ import annotations

import os
from pathlib import Path


_lock = __import__("threading").Lock()
_loaded = False


def _env_file_path() -> Path:
    """Return the path to the project .env file."""
    return Path(__file__).resolve().parent.parent / ".env"


def ensure_env() -> None:
    """Load .env into os.environ. Idempotent, thread-safe — only reads file once."""
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        env_file = _env_file_path()
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
        _loaded = True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/adapter/test_env_loader.py -v`
Expected: ALL PASS

- [ ] **Step 5: Update llm_client.py to use ensure_env()**

Replace lines 23-35 of `adapter/llm_client.py` (the inline .env loading block) with:

```python
from adapter.env_loader import ensure_env

ensure_env()
```

- [ ] **Step 6: Add ensure_env() to generate_image.py**

Add at top of `run()` in `scripts/visual/generate_image.py`, before the `api_key = os.environ.get("FAL_KEY")` line:

```python
from adapter.env_loader import ensure_env
ensure_env()
```

(Import goes at module top with other imports.)

- [ ] **Step 7: Run existing tests to verify no regressions**

Run: `pytest tests/adapter/ tests/pipelines/test_content_generate.py -v --timeout=60`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add adapter/env_loader.py tests/adapter/test_env_loader.py adapter/llm_client.py scripts/visual/generate_image.py
git commit -m "feat: extract shared .env loader to adapter/env_loader.py"
```

---

### Task 2: Quality scorer middleware (`middleware/quality_scorer.py`)

**Files:**
- Create: `middleware/quality_scorer.py`
- Create: `tests/middleware/test_quality_scorer.py`

- [ ] **Step 1: Write failing tests for quality scorer**

```python
# tests/middleware/test_quality_scorer.py
"""Tests for middleware/quality_scorer.py — property-based quality scoring."""
from __future__ import annotations

import pytest

from middleware.quality_scorer import (
    QualityProperty,
    QualityScore,
    compute_score,
    score_competitive_analysis,
    score_content_generate,
    score_clone_converge,
    score_poster_batch,
    score_tts_generate,
)


class TestComputeScore:
    def test_all_pass(self) -> None:
        props = [
            QualityProperty(name="a", passed=True, pass_delta=2.0, fail_delta=2.0, detail="ok"),
            QualityProperty(name="b", passed=True, pass_delta=1.0, fail_delta=1.0, detail="ok"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 8.0  # 5.0 + 2.0 + 1.0
        assert result.passed is True

    def test_all_fail(self) -> None:
        props = [
            QualityProperty(name="a", passed=False, pass_delta=2.0, fail_delta=2.0, detail="bad"),
            QualityProperty(name="b", passed=False, pass_delta=1.0, fail_delta=1.0, detail="bad"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 2.0  # 5.0 - 2.0 - 1.0
        assert result.passed is False

    def test_clamp_high(self) -> None:
        props = [
            QualityProperty(name="a", passed=True, pass_delta=4.0, fail_delta=0.0, detail="ok"),
            QualityProperty(name="b", passed=True, pass_delta=4.0, fail_delta=0.0, detail="ok"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 10.0

    def test_clamp_low(self) -> None:
        props = [
            QualityProperty(name="a", passed=False, pass_delta=0.0, fail_delta=3.0, detail="bad"),
            QualityProperty(name="b", passed=False, pass_delta=0.0, fail_delta=3.0, detail="bad"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 1.0

    def test_gate_failure_caps_at_four(self) -> None:
        props = [
            QualityProperty(name="gate", passed=False, pass_delta=0.0, fail_delta=0.0, detail="gate fail", is_gate=True),
            QualityProperty(name="bonus", passed=True, pass_delta=3.0, fail_delta=0.0, detail="ok"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 4.0
        assert result.passed is False

    def test_bonus_properties_no_penalty(self) -> None:
        props = [
            QualityProperty(name="bonus", passed=False, pass_delta=1.0, fail_delta=0.0, detail="missed"),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == 5.0  # No penalty for missing bonus


class TestScoreCompetitiveAnalysis:
    def test_good_report(self) -> None:
        report = (
            "## Executive Summary\nMarket is competitive.\n"
            "## Competitor Profiles\n"
            "Cafe A charges RM15 per cup. Cafe B has 4.5 stars with 200 reviews. "
            "Cafe C offers RM12 lattes. Cafe D is at RM18. Cafe E has 3.8 rating.\n"
            "## Opportunities and Recommendations\nTarget pricing gap."
        )
        charts = ["/tmp/chart.png"]
        result = score_competitive_analysis(report, charts)
        assert result.score >= 7.0
        assert result.passed is True

    def test_bad_report_no_competitors(self) -> None:
        report = "Some generic analysis without any specific names."
        result = score_competitive_analysis(report, [])
        assert result.score < 7.0
        assert result.passed is False


class TestScorePosterBatch:
    def test_good_poster(self, tmp_path) -> None:
        # Create a fake poster file > 50KB with color variance
        from PIL import Image
        import numpy as np
        arr = np.random.randint(0, 255, (600, 800, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        poster = tmp_path / "poster.png"
        img.save(str(poster))

        result = score_poster_batch(str(poster))
        assert result.score >= 7.0

    def test_tiny_poster_fails(self, tmp_path) -> None:
        poster = tmp_path / "tiny.png"
        poster.write_bytes(b"\x89PNG" + b"\x00" * 50)
        result = score_poster_batch(str(poster))
        assert result.passed is False


class TestScoreContentGenerate:
    def test_good_content(self, tmp_path) -> None:
        pdf = tmp_path / "doc.pdf"
        pdf.write_bytes(b"%PDF-" + b"x" * 6000)  # > 5KB
        result = score_content_generate(
            content="A" * 150,
            title="Good Title",
            pdf_path=str(pdf),
            hashtags=["#one", "#two", "#three"],
        )
        assert result.score >= 7.0

    def test_short_content_fails_gate(self) -> None:
        result = score_content_generate(content="short", title="T", pdf_path=None)
        assert result.passed is False


class TestScoreCloneConverge:
    def test_good_template(self, tmp_path) -> None:
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<html>{{ headline }} {{ body }}</html>")
        result = score_clone_converge(str(tmpl), composite_score=0.75, iterations=2)
        assert result.score >= 7.0

    def test_no_placeholders(self, tmp_path) -> None:
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<html><body>Static</body></html>")
        result = score_clone_converge(str(tmpl), composite_score=0.5, iterations=1)
        assert result.score < 7.0


class TestScoreTtsGenerate:
    def test_good_audio(self, tmp_path) -> None:
        mp3 = tmp_path / "speech.mp3"
        # Valid ID3 header + enough bytes
        mp3.write_bytes(b"ID3" + b"\x00" * 20000)
        result = score_tts_generate(str(mp3), text_length=100)
        assert result.score >= 7.0

    def test_invalid_header(self, tmp_path) -> None:
        mp3 = tmp_path / "bad.mp3"
        mp3.write_bytes(b"RIFF" + b"\x00" * 20000)
        result = score_tts_generate(str(mp3), text_length=100)
        assert result.passed is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/middleware/test_quality_scorer.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement quality_scorer**

```python
# middleware/quality_scorer.py
"""Property-based quality scoring per pipeline.

Replaces hardcoded 8.0 self-grades with measurable property checks.
Each pipeline has a scorer function that inspects actual outputs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class QualityProperty:
    """A single measurable quality property."""

    name: str
    passed: bool
    pass_delta: float
    fail_delta: float
    detail: str
    is_gate: bool = False


@dataclass(frozen=True)
class QualityScore:
    """Composite quality score from property checks."""

    score: float
    passed: bool
    properties: list[QualityProperty]
    pipeline: str


def compute_score(
    properties: list[QualityProperty],
    *,
    pipeline: str,
    base: float = 5.0,
) -> QualityScore:
    """Compute a composite score from quality properties.

    Algorithm:
    1. Start at base (5.0)
    2. Add pass_delta for passed, subtract fail_delta for failed
    3. If any gate property fails, cap at 4.0
    4. Clamp to [1.0, 10.0]
    5. passed = score >= 7.0

    Args:
        properties: List of quality property check results.
        pipeline: Pipeline name for the score record.
        base: Starting score (default 5.0).

    Returns:
        QualityScore with final score and property details.
    """
    score = base
    gate_failed = False

    for prop in properties:
        if prop.passed:
            score += prop.pass_delta
        else:
            score -= prop.fail_delta
            if prop.is_gate:
                gate_failed = True

    if gate_failed:
        score = min(score, 4.0)

    score = max(1.0, min(10.0, score))
    return QualityScore(
        score=score,
        passed=score >= 7.0,
        properties=list(properties),
        pipeline=pipeline,
    )


# ---------------------------------------------------------------------------
# Per-pipeline scorers
# ---------------------------------------------------------------------------


def score_competitive_analysis(
    report: str,
    chart_paths: list[str],
) -> QualityScore:
    """Score a competitive analysis report on named competitors, citations, charts, structure."""
    props: list[QualityProperty] = []

    # Named competitors: >= 3 distinct capitalized multi-word names
    name_pattern = re.compile(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*")
    names = set(name_pattern.findall(report))
    # Filter out common section headers
    section_words = {"Executive", "Summary", "Key", "Findings", "Recommendations",
                     "Competitor", "Profiles", "Opportunities", "Market"}
    competitor_names = {n for n in names if n.split()[0] not in section_words and len(n) > 3}
    props.append(QualityProperty(
        name="named_competitors",
        passed=len(competitor_names) >= 3,
        pass_delta=2.0,
        fail_delta=2.0,
        detail=f"Found {len(competitor_names)} competitor names: {list(competitor_names)[:5]}",
    ))

    # Numeric citations: >= 5 concrete numbers
    numbers = re.findall(r"\d+\.?\d*%?", report)
    # Filter out tiny numbers that are likely formatting artifacts
    meaningful_numbers = [n for n in numbers if len(n) > 1 or n not in "0123"]
    props.append(QualityProperty(
        name="numeric_citations",
        passed=len(meaningful_numbers) >= 5,
        pass_delta=1.0,
        fail_delta=1.0,
        detail=f"Found {len(meaningful_numbers)} numeric citations",
    ))

    # Chart validity: at least one chart exists
    valid_charts = [p for p in chart_paths if Path(p).exists() and Path(p).stat().st_size > 1000]
    props.append(QualityProperty(
        name="chart_validity",
        passed=len(valid_charts) > 0,
        pass_delta=1.0,
        fail_delta=2.0,
        detail=f"{len(valid_charts)} valid charts",
    ))

    # Report structure: all 3 required sections
    sections = ["summary", "profile", "recommend"]
    report_lower = report.lower()
    found_sections = [s for s in sections if s in report_lower]
    props.append(QualityProperty(
        name="report_structure",
        passed=len(found_sections) >= 3,
        pass_delta=1.0,
        fail_delta=1.0,
        detail=f"Found sections: {found_sections}",
    ))

    return compute_score(props, pipeline="competitive_analysis")


def score_poster_batch(poster_path: str) -> QualityScore:
    """Score a poster on dimensions, visual density, and color variance."""
    props: list[QualityProperty] = []
    path = Path(poster_path)

    # Image dimensions: exactly 800x600
    try:
        from PIL import Image
        img = Image.open(path)
        correct_dims = img.width == 800 and img.height == 600
    except Exception:
        correct_dims = False
        img = None
    props.append(QualityProperty(
        name="image_dimensions",
        passed=correct_dims,
        pass_delta=0.0,
        fail_delta=0.0,
        detail=f"Dimensions: {img.width}x{img.height}" if img else "Cannot read image",
        is_gate=True,
    ))

    # Visual density: file size > 50KB
    file_size = path.stat().st_size if path.exists() else 0
    props.append(QualityProperty(
        name="visual_density",
        passed=file_size > 50_000,
        pass_delta=2.0,
        fail_delta=2.0,
        detail=f"File size: {file_size} bytes",
    ))

    # Not monochrome: color variance (std dev > 20)
    not_mono = False
    if img is not None:
        try:
            import numpy as np
            arr = np.array(img)
            not_mono = float(arr.std()) > 20.0
        except Exception:
            not_mono = False
    props.append(QualityProperty(
        name="not_monochrome",
        passed=not_mono,
        pass_delta=1.0,
        fail_delta=1.0,
        detail="Image has color variance" if not_mono else "Image appears monochrome",
    ))

    return compute_score(props, pipeline="poster_batch")


def score_content_generate(
    content: str,
    title: str,
    pdf_path: str | None,
    hashtags: list[str] | None = None,
) -> QualityScore:
    """Score content generation on length, title quality, PDF, hashtags."""
    props: list[QualityProperty] = []

    # Content length > 100 chars (gate)
    props.append(QualityProperty(
        name="content_length",
        passed=len(content) > 100,
        pass_delta=0.0,
        fail_delta=0.0,
        detail=f"Content length: {len(content)} chars",
        is_gate=True,
    ))

    # Title quality: not the brief itself, < 80 chars
    title_ok = len(title) < 80 and len(title) > 0
    props.append(QualityProperty(
        name="title_quality",
        passed=title_ok,
        pass_delta=1.0,
        fail_delta=1.0,
        detail=f"Title: '{title[:40]}...' ({len(title)} chars)",
    ))

    # PDF renders: exists and > 5KB
    pdf_ok = False
    if pdf_path:
        pdf_file = Path(pdf_path)
        pdf_ok = pdf_file.exists() and pdf_file.stat().st_size > 5000
    props.append(QualityProperty(
        name="pdf_renders",
        passed=pdf_ok,
        pass_delta=1.0,
        fail_delta=2.0,
        detail=f"PDF: {'exists and > 5KB' if pdf_ok else 'missing or too small'}",
    ))

    # Has hashtags: >= 3
    tag_count = len(hashtags) if hashtags else 0
    props.append(QualityProperty(
        name="has_hashtags",
        passed=tag_count >= 3,
        pass_delta=1.0,
        fail_delta=0.0,  # Bonus — no penalty
        detail=f"Hashtags: {tag_count}",
    ))

    return compute_score(props, pipeline="content_generate")


def score_clone_converge(
    template_path: str,
    composite_score: float,
    iterations: int,
) -> QualityScore:
    """Score clone convergence on placeholders, valid HTML, convergence, iterations."""
    props: list[QualityProperty] = []
    path = Path(template_path)
    content = path.read_text(encoding="utf-8") if path.exists() else ""

    # Has placeholders: >= 2 {{ }} Jinja2 variables
    placeholders = re.findall(r"\{\{.*?\}\}", content)
    props.append(QualityProperty(
        name="has_placeholders",
        passed=len(placeholders) >= 2,
        pass_delta=2.0,
        fail_delta=2.0,
        detail=f"Found {len(placeholders)} placeholders",
    ))

    # Valid HTML (gate)
    has_html = "<html" in content.lower() and "</html>" in content.lower()
    props.append(QualityProperty(
        name="valid_html",
        passed=has_html,
        pass_delta=0.0,
        fail_delta=0.0,
        detail="Has <html> tags" if has_html else "Missing HTML tags",
        is_gate=True,
    ))

    # Convergence score > 0.6
    props.append(QualityProperty(
        name="convergence_score",
        passed=composite_score > 0.6,
        pass_delta=1.0,
        fail_delta=1.0,
        detail=f"Composite score: {composite_score:.3f}",
    ))

    # Multiple iterations >= 2 (bonus)
    props.append(QualityProperty(
        name="multiple_iterations",
        passed=iterations >= 2,
        pass_delta=1.0,
        fail_delta=0.0,
        detail=f"Iterations: {iterations}",
    ))

    return compute_score(props, pipeline="clone_converge")


def score_tts_generate(file_path: str, text_length: int) -> QualityScore:
    """Score TTS output on MP3 header, file size, and duration adequacy."""
    props: list[QualityProperty] = []
    path = Path(file_path)

    # MP3 header valid (gate)
    header_ok = False
    if path.exists():
        header = path.read_bytes()[:4]
        has_id3 = header[:3] == b"ID3"
        has_sync = len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        header_ok = has_id3 or has_sync
    props.append(QualityProperty(
        name="mp3_header_valid",
        passed=header_ok,
        pass_delta=0.0,
        fail_delta=0.0,
        detail="Valid MP3 header" if header_ok else "Invalid or missing MP3 header",
        is_gate=True,
    ))

    # File size adequate
    file_size = path.stat().st_size if path.exists() else 0
    min_size = max(100, text_length * 50)
    props.append(QualityProperty(
        name="file_size_adequate",
        passed=file_size > min_size,
        pass_delta=1.0,
        fail_delta=2.0,
        detail=f"File size: {file_size} bytes (min: {min_size})",
    ))

    # Duration adequate (heuristic)
    min_duration_bytes = max(16_000, int((text_length / 2.5) * 16_000))
    props.append(QualityProperty(
        name="duration_adequate",
        passed=file_size > min_duration_bytes,
        pass_delta=1.0,
        fail_delta=1.0,
        detail=f"Duration heuristic: {file_size} bytes (min: {min_duration_bytes})",
    ))

    return compute_score(props, pipeline="tts_generate")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/middleware/test_quality_scorer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run pyright**

Run: `pyright middleware/quality_scorer.py`
Expected: 0 errors

- [ ] **Step 6: Commit**

```bash
git add middleware/quality_scorer.py tests/middleware/test_quality_scorer.py
git commit -m "feat: add property-based quality scorer middleware"
```

---

## Chunk 2: Small Pipeline Changes

### Task 3: TTS Generate — dependency checks + new scoring

**Files:**
- Modify: `pipelines/tts_generate.py`
- Modify: `tests/pipelines/test_tts_generate.py` (if exists, or create new test)

- [ ] **Step 1: Write failing test for dependency check**

Add to existing TTS tests or create new test file:

```python
# In tests/pipelines/test_tts_generate.py — add these tests
def test_raises_without_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ffmpeg raises RuntimeError with clear message."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    from pipelines.tts_generate import run
    with pytest.raises(RuntimeError, match="ffmpeg not found"):
        run(text="hello", output_path="/tmp/test.mp3")


def test_raises_without_edge_tts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing edge-tts raises RuntimeError with clear message."""
    import builtins
    original_import = builtins.__import__

    def mock_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "edge_tts":
            raise ImportError("No module named 'edge_tts'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    # Need to reimport to trigger the check
    # This test verifies the check exists in run()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipelines/test_tts_generate.py -v -k "ffmpeg or edge_tts"`
Expected: FAIL

- [ ] **Step 3: Implement dependency checks and scorer integration**

In `pipelines/tts_generate.py`:

1. Add `import shutil` at top
2. Add at the start of `run()`, before any work:

```python
if not shutil.which("ffmpeg"):
    raise RuntimeError("ffmpeg not found on PATH — required for audio normalization")
try:
    import edge_tts  # noqa: F401
except ImportError:
    raise RuntimeError("edge-tts package not installed — run: pip install edge-tts")
```

3. Add duration heuristic after existing `_verify_output()` call:

```python
# Duration heuristic check
if quality_result.passed:
    min_duration_bytes = max(16_000, int((len(text) / 2.5) * 16_000))
    actual_size = Path(output_path).stat().st_size
    if actual_size < min_duration_bytes:
        logger.warning(
            "Audio duration suspect: %d bytes < %d minimum for %d chars",
            actual_size, min_duration_bytes, len(text),
        )
```

4. Replace the return dict to use quality scorer:

```python
from middleware.quality_scorer import score_tts_generate
score = score_tts_generate(output_path, text_length=len(text))
```

Return `score.score` and `score.passed` in the quality_report section.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/pipelines/test_tts_generate.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/tts_generate.py tests/pipelines/test_tts_generate.py
git commit -m "feat: tts_generate — dependency checks, duration heuristic, property scoring"
```

---

### Task 4: Content Generate — structured response + styled PDF

**Files:**
- Modify: `pipelines/content_generate.py`
- Modify: `scripts/document/render_typst.py`
- Modify: `tests/pipelines/test_content_generate_quality.py`

- [ ] **Step 1: Write failing tests for _extract_structured_response and styled PDF**

Add to `tests/pipelines/test_content_generate_quality.py`:

```python
def test_extract_structured_response_parses_json() -> None:
    """_extract_structured_response returns ContentResponse from JSON."""
    from pipelines.content_generate import _extract_structured_response, ContentResponse

    raw = json.dumps({
        "title": "Test Title",
        "body": "Test body content",
        "hashtags": ["#one", "#two", "#three"],
    })
    result = _extract_structured_response(raw)
    assert isinstance(result, ContentResponse)
    assert result.title == "Test Title"
    assert result.body == "Test body content"
    assert result.hashtags == ["#one", "#two", "#three"]


def test_extract_structured_response_fallback() -> None:
    """Non-JSON input returns sensible defaults."""
    from pipelines.content_generate import _extract_structured_response

    result = _extract_structured_response("Just plain text content.")
    assert result.body == "Just plain text content."
    assert len(result.title) > 0


def test_render_to_pdf_accepts_accent_and_hashtags() -> None:
    """render_to_pdf accepts optional accent_color and hashtags params."""
    import inspect
    from scripts.document.render_typst import render_to_pdf

    sig = inspect.signature(render_to_pdf)
    assert "accent_color" in sig.parameters
    assert "hashtags" in sig.parameters
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipelines/test_content_generate_quality.py -v -k "structured or accent"`
Expected: FAIL

- [ ] **Step 3: Add ContentResponse dataclass and _extract_structured_response to content_generate.py**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ContentResponse:
    """Structured fields from LLM content generation response."""
    title: str
    body: str
    hashtags: list[str]


def _extract_structured_response(response: str) -> ContentResponse:
    """Parse LLM JSON response into structured fields. Single parse.

    Falls back to extracting from plain text if JSON parsing fails.

    Args:
        response: Raw LLM response text (expected JSON).

    Returns:
        ContentResponse with title, body, and hashtags.
    """
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            return ContentResponse(
                title=str(data.get("title", "")),
                body=str(data.get("body", "")),
                hashtags=[str(t) for t in data.get("hashtags", []) if t],
            )
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract from plain text
    title = _extract_title_from_response(response)
    return ContentResponse(title=title, body=response, hashtags=[])
```

- [ ] **Step 4: Update _pipeline_fn to use _extract_structured_response**

Replace the content extraction in `_pipeline_fn`:

```python
# Extract structured fields from the response
parsed = _extract_structured_response(raw_content)
content = parsed.body

# ... (result dict stays the same)

# PDF rendering — pass hashtags and accent
if output_format == "pdf":
    set_pipeline_step("pdf_render", _PIPELINE_NAME, _PIPELINE_VERSION)
    pdf_result = render_to_pdf(
        content=content,
        title=parsed.title,
        accent_color="2563eb",
        hashtags=parsed.hashtags if parsed.hashtags else None,
    )
    # ... rest same

# Quality scoring — replace hardcoded 8.0
from middleware.quality_scorer import score_content_generate
score = score_content_generate(
    content=content,
    title=parsed.title,
    pdf_path=result.get("pdf_path"),
    hashtags=parsed.hashtags,
)
did = get_deliverable_id()
if did:
    record_quality(did, score.score, score.passed)
```

- [ ] **Step 5: Update render_typst.py with branded template**

Add `accent_color` and `hashtags` parameters to `render_to_pdf()` and rewrite `_wrap_content_as_typst()`:

```python
def render_to_pdf(
    content: str,
    output_path: str | None = None,
    title: str = "Document",
    accent_color: str = "2563eb",
    hashtags: list[str] | None = None,
) -> dict[str, str]:
```

New `_wrap_content_as_typst()`:

```python
def _wrap_content_as_typst(
    content: str,
    title: str,
    accent_color: str = "2563eb",
    hashtags: list[str] | None = None,
) -> str:
    typst_content = _markdown_to_typst(content)
    hashtag_block = ""
    if hashtags:
        escaped = " ".join(f"\\#{tag.lstrip('#')}" for tag in hashtags)
        hashtag_block = f'\n#v(1.5em)\n#text(size: 10pt, fill: luma(120))[{escaped}]\n'

    return f"""#set page(
  paper: "a5",
  flipped: true,
  margin: (top: 2.5cm, bottom: 2cm, left: 2cm, right: 2cm),
)
#set text(size: 12pt)
#set par(justify: true, leading: 1.4em, spacing: 1.2em)

#rect(width: 100%, height: 6pt, fill: rgb("{accent_color}"))

#v(0.8em)

#text(size: 22pt, weight: "bold", fill: rgb("{accent_color}"))[{title}]

#v(0.3em)

#line(length: 40%, stroke: 0.5pt + luma(180))

#v(0.8em)

{typst_content}
{hashtag_block}
#v(1fr)

#rect(width: 100%, height: 6pt, fill: rgb("{accent_color}"))
"""
```

Pass through the new params in `render_to_pdf()`:
```python
typst_source = _wrap_content_as_typst(content, title, accent_color, hashtags)
```

- [ ] **Step 6: Update tests/scripts/test_render_typst.py for branded template**

Add to the existing `TestWrapContentAsTypst` class:

```python
def test_includes_accent_bar(self) -> None:
    output = _wrap_content_as_typst("Body", "Title", accent_color="2563eb")
    assert 'fill: rgb("2563eb")' in output

def test_includes_hashtags(self) -> None:
    output = _wrap_content_as_typst("Body", "Title", hashtags=["#AI", "#Tech"])
    assert "AI" in output
    assert "Tech" in output
    assert "luma(120)" in output  # Muted gray for hashtags

def test_a5_landscape(self) -> None:
    output = _wrap_content_as_typst("Body", "Title")
    assert 'paper: "a5"' in output
    assert "flipped: true" in output

def test_render_styled_pdf_larger_than_plain(self, tmp_path: Path) -> None:
    if shutil.which("typst") is None:
        pytest.skip("typst CLI not installed")
    styled = str(tmp_path / "styled.pdf")
    result = render_to_pdf(
        content="Test content " * 20,
        output_path=styled,
        title="Styled Doc",
        accent_color="2563eb",
        hashtags=["#one", "#two", "#three"],
    )
    assert "pdf_path" in result
    assert Path(result["pdf_path"]).stat().st_size > 5000
```

Update the `_wrap_content_as_typst` call signature in existing tests to pass the new params (backward compat: existing calls still work since new params have defaults).

- [ ] **Step 7: Run tests**

Run: `pytest tests/pipelines/test_content_generate_quality.py tests/pipelines/test_content_generate.py tests/scripts/test_render_typst.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add pipelines/content_generate.py scripts/document/render_typst.py tests/pipelines/test_content_generate_quality.py tests/scripts/test_render_typst.py
git commit -m "feat: content_generate — structured response, styled Typst PDF, property scoring"
```

---

### Task 5: Clone Converge — min iterations + parameterization + scoring

**Files:**
- Modify: `pipelines/clone_converge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipelines/test_clone_converge_quality.py
"""Tests for clone_converge v2 — min_iterations, parameterization, delta logging."""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_run_signature_has_min_iterations() -> None:
    """run() accepts min_iterations parameter."""
    import inspect
    from pipelines.clone_converge import run
    sig = inspect.signature(run)
    assert "min_iterations" in sig.parameters
    assert sig.parameters["min_iterations"].default == 2


def test_min_iterations_enforced(tmp_path: Path) -> None:
    """Even if score >= threshold on iter 1, must run min_iterations."""
    iteration_count = 0

    def mock_llm(**kwargs: object) -> str:
        nonlocal iteration_count
        iteration_count += 1
        return "<html><head></head><body><h1>Test</h1></body></html>"

    target = tmp_path / "target.png"
    # Create a minimal valid PNG
    from PIL import Image
    Image.new("RGB", (100, 100), "red").save(str(target))

    with patch("pipelines.clone_converge.llm_chat", side_effect=mock_llm), \
         patch("pipelines.clone_converge.screenshot_run") as mock_ss, \
         patch("pipelines.clone_converge.calculate_delta") as mock_delta, \
         patch("pipelines.clone_converge.record_quality"), \
         patch("pipelines.clone_converge.check_anomalies", return_value={"is_anomaly": False}):

        # Return perfect score every time
        mock_delta.return_value = MagicMock(
            composite_score=0.95, ssim_score=0.95, color_delta_e=5.0,
            pixel_diff_pct=2.0, layout_score=0.9, text_match_pct=95.0,
        )
        mock_ss.return_value = {"file_path": str(tmp_path / "rendered.png")}
        # Create the rendered file so delta can read it
        Image.new("RGB", (100, 100), "red").save(str(tmp_path / "rendered.png"))

        from pipelines.clone_converge import run
        result = run(
            target_image_path=str(target),
            output_dir=str(tmp_path / "out"),
            max_iterations=5,
            min_iterations=2,
            threshold=0.80,
        )

    assert result["iterations"] >= 2


def test_parameterization_pass_adds_placeholders(tmp_path: Path) -> None:
    """After convergence, template should contain {{ headline }} and {{ body }}."""
    converged_html = "<html><head></head><body><h1>My Title</h1><p>My Body</p></body></html>"
    parameterized_html = '<html><head></head><body><h1>{{ headline }}</h1><p>{{ body }}</p></body></html>'

    def mock_llm(*, messages: list, **kwargs: object) -> str:
        # Check if this is the parameterization call
        prompt_text = str(messages[-1].get("content", ""))
        if "Jinja2 template" in prompt_text or "{{ headline }}" in prompt_text:
            return parameterized_html
        return converged_html

    target = tmp_path / "target.png"
    from PIL import Image
    Image.new("RGB", (100, 100), "red").save(str(target))

    with patch("pipelines.clone_converge.llm_chat", side_effect=mock_llm), \
         patch("pipelines.clone_converge.screenshot_run") as mock_ss, \
         patch("pipelines.clone_converge.calculate_delta") as mock_delta, \
         patch("pipelines.clone_converge.record_quality"), \
         patch("pipelines.clone_converge.check_anomalies", return_value={"is_anomaly": False}):

        mock_delta.return_value = MagicMock(
            composite_score=0.90, ssim_score=0.90, color_delta_e=5.0,
            pixel_diff_pct=2.0, layout_score=0.9, text_match_pct=95.0,
        )
        mock_ss.return_value = {"file_path": str(tmp_path / "rendered.png")}
        Image.new("RGB", (100, 100), "red").save(str(tmp_path / "rendered.png"))

        from pipelines.clone_converge import run
        result = run(
            target_image_path=str(target),
            output_dir=str(tmp_path / "out"),
            max_iterations=3,
            min_iterations=2,
            threshold=0.80,
        )

    template = Path(result["template_path"]).read_text()
    assert "{{ headline }}" in template
    assert "{{ body }}" in template
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipelines/test_clone_converge_quality.py -v`
Expected: FAIL

- [ ] **Step 3: Implement changes to clone_converge.py**

1. Update `_PIPELINE_VERSION` to `"2.0"`
2. Add `min_iterations: int = 2` parameter to `run()`
3. Change convergence check:

```python
if score >= threshold and iteration >= min_iterations:
    # Converged
```

4. Add delta component logging after `calculate_delta()`:

```python
logger.info(
    "Delta components",
    iteration=iteration,
    ssim=delta.ssim_score,
    color_delta_e=delta.color_delta_e,
    pixel_diff_pct=delta.pixel_diff_pct,
    layout_score=delta.layout_score,
    text_match_pct=delta.text_match_pct,
    composite=delta.composite_score,
)
```

5. Add parameterization pass after convergence loop (both converged and max_iterations paths):

```python
def _parameterize_template(html: str) -> str:
    """Run LLM call to convert HTML into Jinja2 template with placeholders."""
    set_pipeline_step("parameterize", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = (
        "Convert this HTML into a Jinja2 template. Replace:\n"
        "- The main heading text with {{ headline }}\n"
        "- Body/description text with {{ body }}\n"
        "- Call-to-action text with {{ cta }}\n"
        "Keep ALL CSS, layout, and structure exactly the same.\n"
        "Output ONLY the modified HTML."
    )
    result = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid HTML with Jinja2 placeholders."},
            {"role": "user", "content": f"{prompt}\n\n```html\n{html}\n```"},
        ],
        max_tokens=4096,
        strip_preamble=True,
    )
    if result and "{{ headline }}" in result and "{{ body }}" in result:
        return result

    # Retry once with reinforced prompt
    logger.warning("Parameterization missing placeholders, retrying")
    retry_result = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid HTML. You MUST include {{ headline }} and {{ body }} placeholders."},
            {"role": "user", "content": f"{prompt}\n\nYou MUST include {{{{ headline }}}} and {{{{ body }}}} placeholders.\n\n```html\n{html}\n```"},
        ],
        max_tokens=4096,
        strip_preamble=True,
    )
    if retry_result and "{{ headline }}" in retry_result:
        return retry_result

    logger.warning("Parameterization failed after retry, using original HTML")
    return html
```

6. Call `_parameterize_template(best_html)` before saving, and use quality scorer:

```python
from middleware.quality_scorer import score_clone_converge
# ... after convergence loop
parameterized = _parameterize_template(best_html)
template_path = out / "template.html"
template_path.write_text(parameterized)
score = score_clone_converge(str(template_path), best_score, iteration)
record_quality(did, score.score, score.passed)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/pipelines/test_clone_converge_quality.py tests/pipelines/ -v -k "clone" --timeout=60`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add pipelines/clone_converge.py tests/pipelines/test_clone_converge_quality.py
git commit -m "feat: clone_converge — min 2 iterations, Jinja2 parameterization, delta logging, property scoring"
```

---

## Chunk 3: Major Pipeline Rewrites

### Task 6: Poster Batch — AI background + quality gate integration

**Files:**
- Modify: `pipelines/poster_batch.py` (rewrite)
- Replace: `tests/benchmarks/inputs/poster_template.html`
- Modify: `tests/pipelines/test_poster_batch.py`
- Modify: `tests/pipelines/test_poster_batch_quality.py`

- [ ] **Step 1: Write failing tests for new poster_batch**

```python
# tests/pipelines/test_poster_batch_quality.py
"""Tests for poster_batch v2 — AI background, quality gates, base64 injection."""
from __future__ import annotations

import base64
import csv
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_poster_batch_has_quality_gate_integration() -> None:
    """poster_batch must use run_with_gates."""
    import inspect
    source = inspect.getsource(__import__("pipelines.poster_batch", fromlist=["run"]))
    assert "run_with_gates" in source


def test_poster_batch_has_input_output_schemas() -> None:
    """poster_batch must define _INPUT_SCHEMA and _OUTPUT_SCHEMA."""
    from pipelines import poster_batch
    assert hasattr(poster_batch, "_INPUT_SCHEMA")
    assert hasattr(poster_batch, "_OUTPUT_SCHEMA")


def test_poster_batch_has_start_deliverable() -> None:
    """poster_batch must use start_deliverable lifecycle."""
    import inspect
    source = inspect.getsource(__import__("pipelines.poster_batch", fromlist=["run"]))
    assert "start_deliverable" in source


def test_poster_renders_with_background_image(tmp_path: Path) -> None:
    """When fal.ai works, template receives base64 background_image."""
    calls: list[dict] = []

    def tracking_screenshot(**kwargs: object) -> dict[str, str]:
        calls.append(dict(kwargs))
        out = str(kwargs.get("output_path", str(tmp_path / "poster.png")))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"\x89PNG" + b"\x00" * 100)
        return {"file_path": out}

    # Create a fake AI image
    fake_img = tmp_path / "bg.png"
    fake_img.write_bytes(b"\x89PNG" + b"\x00" * 200)

    tmpl = tmp_path / "template.html"
    tmpl.write_text(
        '<body style="background-image: url(\'{{ background_image }}\');">'
        "<h1>{{ headline }}</h1></body>"
    )
    data = tmp_path / "data.csv"
    data.write_text("headline,body,cta\nTest,Body,CTA\n")

    with patch("pipelines.poster_batch.screenshot_run", side_effect=tracking_screenshot), \
         patch("pipelines.poster_batch._generate_ai_background", return_value=str(fake_img)), \
         patch("pipelines.poster_batch.record_quality"), \
         patch("pipelines.poster_batch.start_deliverable", return_value="test-did"), \
         patch("pipelines.poster_batch.clear_context"), \
         patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False}):

        from pipelines.poster_batch import run
        result = run(
            template_path=str(tmpl),
            data_path=str(data),
            output_dir=str(tmp_path / "out"),
        )

    assert result["count"] >= 1
    # Check that html_content passed to screenshot contains base64
    html_passed = calls[0].get("html_content", "")
    assert "data:image/png;base64," in str(html_passed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipelines/test_poster_batch_quality.py -v`
Expected: FAIL

- [ ] **Step 3: Replace poster template HTML**

Write new `tests/benchmarks/inputs/poster_template.html`:

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    width: 800px; height: 600px;
    background-image: url('{{ background_image }}');
    background-size: cover;
    background-position: center;
    font-family: 'Segoe UI', Arial, sans-serif;
    color: #ffffff;
  }
  .overlay {
    width: 100%; height: 100%;
    background: linear-gradient(
      to bottom,
      rgba(0,0,0,0.3) 0%,
      rgba(0,0,0,0.6) 50%,
      rgba(0,0,0,0.7) 100%
    );
    display: grid;
    grid-template-rows: 1fr auto 1fr;
    align-items: center;
    padding: 48px 60px;
  }
  .headline {
    font-size: 36px; font-weight: 700;
    text-shadow: 0 2px 8px rgba(0,0,0,0.7);
    align-self: end;
  }
  .body-text {
    font-size: 18px; line-height: 1.5;
    text-shadow: 0 1px 4px rgba(0,0,0,0.6);
    padding: 20px 0;
  }
  .cta {
    align-self: start;
  }
  .cta-button {
    display: inline-block;
    background: {{ accent_color | default('#e94560') }}; color: #fff;
    padding: 14px 36px;
    border-radius: 8px;
    font-size: 16px; font-weight: 600;
    text-decoration: none;
    box-shadow: 0 4px 12px rgba(233,69,96,0.4);
  }
</style>
</head>
<body>
  <div class="overlay">
    <h1 class="headline">{{ headline }}</h1>
    <p class="body-text">{{ body }}</p>
    <div class="cta"><span class="cta-button">{{ cta }}</span></div>
  </div>
</body>
</html>
```

- [ ] **Step 4: Rewrite poster_batch.py**

Complete rewrite with AI background generation, base64 injection, quality gate integration:

```python
"""Batch poster production — AI background + HTML overlay -> posters.

Two-layer composition:
1. fal_generate AI background (800x600)
2. Base64 inject into Jinja2 template
3. Playwright screenshot
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
from jinja2.sandbox import SandboxedEnvironment

from adapter.llm_client import chat as llm_chat
from middleware.cost_ledger import record_quality
from middleware.deliverable_context import (
    clear_context,
    set_pipeline_step,
    start_deliverable,
)
from middleware.pipeline_runner import run_with_gates
from middleware.quality_scorer import score_poster_batch
from middleware.trace_exporter import (
    check_anomalies,
    export_trace,
    log_anomaly,
    notify_anomaly,
)
from scripts.visual.screenshot_html import run as screenshot_run

logger = structlog.get_logger(__name__)

_PIPELINE_NAME = "poster_batch"
_PIPELINE_VERSION = "2.0"

_INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "template_path": {"type": "string", "required": True},
    "data_path": {"type": "string", "required": True},
    "output_dir": {"type": "string", "required": False},
    "client_id": {"type": "string", "required": False},
}

_OUTPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "posters": {"type": "array", "required": True},
    "count": {"type": "integer", "required": True},
    "status": {"type": "string", "required": True},
}

_GRADIENT_FALLBACK = "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)"


def _generate_image_prompt(headline: str, style_hint: str | None) -> str:
    """Ask LLM for an image generation prompt based on content."""
    set_pipeline_step("image_prompt", _PIPELINE_NAME, _PIPELINE_VERSION)
    context = style_hint or headline
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate a short image prompt for an AI image generator. "
                    "The image will be used as a poster background. Rules:\n"
                    "- No text in the image\n"
                    "- Photography style, suitable as background\n"
                    "- Soft lighting, shallow depth of field\n"
                    "- Output ONLY the prompt, nothing else"
                ),
            },
            {"role": "user", "content": f"Context: {context}"},
        ],
        max_tokens=100,
        strip_preamble=True,
    )
    return result or f"professional photography, {context}, soft lighting, shallow depth of field"


def _generate_ai_background(prompt: str, output_path: str) -> str | None:
    """Generate AI background via fal.ai. Returns path or None on failure."""
    try:
        from adapter.env_loader import ensure_env
        ensure_env()
        from scripts.visual.generate_image import run as fal_run
        result = fal_run(
            prompt=prompt,
            output_path=output_path,
            width=800,
            height=600,
        )
        return result["file_path"]
    except (RuntimeError, httpx.HTTPError, httpx.TimeoutException, KeyError, FileNotFoundError, OSError) as exc:
        logger.warning("AI background generation failed: %s", exc)
        return None


def _encode_background(image_path: str | None) -> str:
    """Encode image as base64 data URI, or return CSS gradient fallback."""
    if image_path is None:
        return _GRADIENT_FALLBACK
    try:
        image_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except (FileNotFoundError, OSError):
        return _GRADIENT_FALLBACK


def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
    """Core pipeline logic for poster batch production."""
    template_path: str = inputs["template_path"]
    data_path: str = inputs["data_path"]
    output_dir: str = inputs.get("output_dir", "output/posters")
    client_id: str | None = inputs.get("client_id")

    did = start_deliverable(client_id=client_id)

    try:
        tmpl_file = Path(template_path)
        if not tmpl_file.exists():
            msg = f"Template not found: {template_path}"
            raise FileNotFoundError(msg)

        data_file = Path(data_path)
        if not data_file.exists():
            msg = f"Data file not found: {data_path}"
            raise FileNotFoundError(msg)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        template_text = tmpl_file.read_text(encoding="utf-8")
        env = SandboxedEnvironment()
        template = env.from_string(template_text)

        df = pd.read_csv(data_file)
        rows = df.to_dict(orient="records")

        if not rows:
            return {
                "posters": [],
                "count": 0,
                "status": "completed",
                "deliverable_id": did,
            }

        posters: list[str] = []
        for idx, row in enumerate(rows):
            headline = str(row.get("headline", ""))
            style_hint = row.get("style_hint")

            # Step 1: Generate image prompt
            image_prompt = _generate_image_prompt(headline, style_hint)

            # Step 2: Generate AI background
            bg_path = str(out / f"bg_{idx:04d}.png")
            ai_image = _generate_ai_background(image_prompt, bg_path)

            # Step 3: Encode as base64 and render template
            background_image = _encode_background(ai_image)
            html = template.render(
                background_image=background_image,
                accent_color=row.get("accent_color", "#e94560"),
                **row,
            )

            # Step 4: Screenshot
            poster_path = str(out / f"poster_{idx:04d}.png")
            result = screenshot_run(
                html_content=html,
                output_path=poster_path,
                viewport_width=800,
                viewport_height=600,
                full_page=False,
            )
            posters.append(result["file_path"])

            # Score each poster
            poster_score = score_poster_batch(result["file_path"])
            logger.info(
                "Poster %d/%d rendered (score: %.1f): %s",
                idx + 1, len(rows), poster_score.score, poster_path,
            )

        # Record quality from last poster (or average if needed)
        if posters:
            final_score = score_poster_batch(posters[-1])
            record_quality(did, final_score.score, final_score.passed)

        _check_and_export(did, client_id)

        return {
            "posters": posters,
            "count": len(posters),
            "status": "completed",
            "deliverable_id": did,
        }
    finally:
        clear_context()


def run(
    *,
    template_path: str | None = None,
    data_path: str | None = None,
    output_dir: str = "output/posters",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Run poster batch pipeline with quality gates.

    Args:
        template_path: Path to Jinja2 HTML template.
        data_path: Path to CSV file with one row per poster.
        output_dir: Directory for output PNG files.
        client_id: Client identifier for cost tracking.

    Returns:
        Dict with posters list, count, status, deliverable_id, quality_report.
    """
    if not template_path:
        msg = "template_path is required"
        raise ValueError(msg)
    if not data_path:
        msg = "data_path is required"
        raise ValueError(msg)

    inputs: dict[str, Any] = {
        "template_path": template_path,
        "data_path": data_path,
        "output_dir": output_dir,
    }
    if client_id is not None:
        inputs["client_id"] = client_id

    return run_with_gates(
        pipeline_fn=_pipeline_fn,
        inputs=inputs,
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name=_PIPELINE_NAME,
    )


def _check_and_export(did: str, client_id: str | None) -> None:
    """Check anomalies and export trace if needed."""
    anomaly = check_anomalies(did)
    if anomaly["is_anomaly"]:
        trace_path = export_trace(did)
        log_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
        notify_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
```

- [ ] **Step 5: Update existing test_poster_batch.py for new signature**

The existing tests mock `screenshot_run` and should still work. Update to account for new imports and the `_pipeline_fn` / `run_with_gates` pattern. The `run()` function signature is backward-compatible (added optional `client_id`).

Also update `test_poster_batch_quality.py` to verify base64 injection and quality gate integration.

- [ ] **Step 6: Run tests**

Run: `pytest tests/pipelines/test_poster_batch*.py -v --timeout=60`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add pipelines/poster_batch.py tests/benchmarks/inputs/poster_template.html tests/pipelines/test_poster_batch*.py
git commit -m "feat: poster_batch — AI background, base64 injection, quality gate integration, property scoring"
```

---

### Task 7: Competitive Analysis — web research flow + new scoring

**Files:**
- Modify: `pipelines/competitive_analysis.py` (rewrite `_pipeline_fn`)

- [ ] **Step 1: Write failing tests for web research helpers**

```python
# tests/pipelines/test_competitive_analysis_quality.py
"""Tests for competitive_analysis v2 — web research flow."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_generate_search_queries_returns_urls() -> None:
    """_generate_search_urls returns list of URL strings."""
    from pipelines.competitive_analysis import _generate_search_urls

    mock_response = json.dumps([
        "https://www.yelp.com/search?find_desc=coffee&find_loc=Petaling+Jaya",
        "https://www.tripadvisor.com/Restaurants-Petaling-Jaya-Coffee",
    ])
    with patch("pipelines.competitive_analysis.llm_chat", return_value=mock_response):
        urls = _generate_search_urls("coffee shops in Petaling Jaya")
    assert len(urls) >= 2
    assert all(url.startswith("http") for url in urls)


def test_extract_competitors_returns_structured_data() -> None:
    """_extract_competitors returns list of competitor dicts."""
    from pipelines.competitive_analysis import _extract_competitors

    raw_text = "Cafe A is at RM15. Cafe B has 4.5 stars."
    mock_response = json.dumps([
        {"name": "Cafe A", "pricing_range": "RM15", "strengths": "good price"},
        {"name": "Cafe B", "pricing_range": "RM18", "strengths": "high rating"},
        {"name": "Cafe C", "pricing_range": "RM12", "strengths": "location"},
    ])
    with patch("pipelines.competitive_analysis.llm_chat", return_value=mock_response):
        competitors = _extract_competitors("coffee", [raw_text])
    assert len(competitors) >= 3
    assert all("name" in c for c in competitors)


def test_web_research_fallback_on_no_fetches() -> None:
    """When all fetches fail, falls back to LLM-only analysis."""
    from pipelines.competitive_analysis import _fetch_and_extract

    with patch("pipelines.competitive_analysis._fetch_url", return_value=None):
        results = _fetch_and_extract(["http://fail1.com", "http://fail2.com"])
    assert results == []


def test_pipeline_uses_web_research_when_no_data_path() -> None:
    """When data_path is None, pipeline activates web research flow."""
    import inspect
    source = inspect.getsource(
        __import__("pipelines.competitive_analysis", fromlist=["_pipeline_fn"])
    )
    assert "_generate_search_urls" in source
    assert "_fetch_and_extract" in source
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/pipelines/test_competitive_analysis_quality.py -v`
Expected: FAIL

- [ ] **Step 3: Implement web research helpers**

Add to `competitive_analysis.py`:

```python
from scripts.content.fetch_url import fetch as httpx_fetch


def _generate_search_urls(topic: str) -> list[str]:
    """Generate 3-5 URLs for competitor research via LLM."""
    set_pipeline_step("search_url_generation", _PIPELINE_NAME, _PIPELINE_VERSION)
    prompt = (
        f'Given the topic "{topic}", generate 3-5 URLs that would contain '
        "competitor information. Target structured data sources like Google Maps "
        "business listings, Yelp pages, industry directories, or social media "
        "business profiles. Return ONLY a JSON array of URL strings.\n"
        "Do NOT return generic search engine result pages.\n"
        "Focus on: pricing, location, reviews, unique selling points."
    )
    raw = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid JSON arrays of URL strings."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512,
        strip_preamble=True,
    )
    if raw is None:
        return []
    try:
        urls = json.loads(raw)
        if isinstance(urls, list):
            return [str(u) for u in urls if isinstance(u, str) and u.startswith("http")]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _fetch_url(url: str) -> str | None:
    """Fetch a URL via httpx_fetch, returning body text or None."""
    try:
        result = httpx_fetch(url)
        if result.get("status_code") == 200:
            return str(result.get("body", ""))
    except (ValueError, httpx.HTTPError, httpx.TimeoutException, ConnectionError, OSError) as exc:
        logger.warning("Fetch failed for %s: %s", url, exc)
    return None


def _fetch_and_extract(urls: list[str]) -> list[str]:
    """Fetch URLs and return list of successful page texts."""
    texts: list[str] = []
    for url in urls:
        text = _fetch_url(url)
        if text:
            texts.append(text)
    return texts


def _extract_competitors(topic: str, page_texts: list[str]) -> list[dict[str, str]]:
    """Extract structured competitor data from fetched page texts."""
    set_pipeline_step("competitor_extraction", _PIPELINE_NAME, _PIPELINE_VERSION)
    combined = "\n\n---\n\n".join(page_texts[:5])  # Limit to avoid token overflow
    prompt = (
        f"From the following web page content about '{topic}', extract competitor information.\n"
        "Return a JSON array of objects with these keys:\n"
        "name, location, pricing_range, strengths, weaknesses, differentiator\n"
        "Extract at least 3 competitors. Return ONLY valid JSON.\n\n"
        f"Content:\n{combined[:8000]}"
    )
    raw = llm_chat(
        messages=[
            {"role": "system", "content": "You output only valid JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1024,
        strip_preamble=True,
    )
    if raw is None:
        return []
    try:
        competitors = json.loads(raw)
        if isinstance(competitors, list):
            return [c for c in competitors if isinstance(c, dict) and "name" in c]
    except (json.JSONDecodeError, TypeError):
        pass
    return []
```

- [ ] **Step 4: Rewrite _pipeline_fn with web research flow**

Update `_pipeline_fn` to branch on `data_path`:

- **If `data_path` is None:** Run web research flow (Steps 1-3 from spec), then chart + narrative
- **If `data_path` is provided:** Keep existing CSV analysis flow (backward compat)

For the web research path:
1. `_generate_search_urls(topic)`
2. `_fetch_and_extract(urls)` — need >= 2 successful
3. `_extract_competitors(topic, texts)` — need >= 3 competitors
4. Build charts from competitor pricing data
5. Generate narrative from competitor JSON
6. Fallback path: if < 2 fetches, run LLM-only analysis with -2 quality penalty disclaimer

Replace hardcoded scoring with:
```python
from middleware.quality_scorer import score_competitive_analysis
score = score_competitive_analysis(report, chart_paths)
record_quality(did, score.score, score.passed)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/pipelines/test_competitive_analysis*.py -v --timeout=60`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add pipelines/competitive_analysis.py tests/pipelines/test_competitive_analysis_quality.py
git commit -m "feat: competitive_analysis — web research flow, competitor extraction, property scoring"
```

---

## Chunk 4: Integration Tests + Final Verification

### Task 8: Update benchmark regression tests

**Files:**
- Modify: `tests/benchmarks/test_quality_regression.py`

- [ ] **Step 1: Update benchmark test assertions per spec**

Update the test classes with revised assertions:

```python
class TestCompetitiveAnalysisRegression:
    # ... existing fixture ...

    def test_competitive_analysis_has_competitors(self, analysis_result: dict) -> None:
        """Report must name >= 3 businesses."""
        report = analysis_result.get("report", "")
        # Count capitalized multi-word names (competitor names)
        import re
        names = set(re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*", report))
        assert len(names) >= 3, f"Report should name >= 3 competitors, found {len(names)}"

    # Keep existing tests, add new ones


class TestPosterBatchRegression:
    def test_poster_has_visual_content(self) -> None:
        """Poster file size > 50KB, dimensions 800x600."""
        # ... run pipeline ...
        from PIL import Image
        img = Image.open(first_poster)
        assert img.width == 800
        assert img.height == 600
        assert first_poster.stat().st_size > 50_000


class TestContentGenerateRegression:
    # ... existing fixture ...

    def test_content_pdf_is_styled(self, pdf_result: dict) -> None:
        """Styled PDF should be > 5KB (larger than plain text)."""
        if "pdf_path" in pdf_result:
            pdf = Path(pdf_result["pdf_path"])
            assert pdf.exists()
            assert pdf.stat().st_size > 5000, "Styled PDF should be > 5KB"


class TestCloneConvergeRegression:
    def test_clone_converge_has_placeholders(self, converge_result: dict) -> None:
        """Template must contain {{ headline }}."""
        if "template_path" in converge_result:
            content = Path(converge_result["template_path"]).read_text()
            assert "{{ headline }}" in content or "{{headline}}" in content


class TestTTSGenerateRegression:
    def test_tts_produces_audio(self) -> None:
        """MP3 exists, valid header, > minimum size."""
        # ... existing test enhanced with header check ...
        header = mp3.read_bytes()[:3]
        assert header == b"ID3" or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)
```

- [ ] **Step 2: Run all non-benchmark tests to check for regressions**

Run: `pytest tests/ -v --timeout=120 -k "not benchmark"`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/benchmarks/test_quality_regression.py
git commit -m "test: update benchmark assertions for artifact quality overhaul v2"
```

---

### Task 9: Run pyright + final verification

- [ ] **Step 1: Run pyright on all changed files**

```bash
pyright adapter/env_loader.py middleware/quality_scorer.py pipelines/competitive_analysis.py pipelines/poster_batch.py pipelines/content_generate.py pipelines/clone_converge.py pipelines/tts_generate.py scripts/document/render_typst.py
```

Expected: 0 errors

- [ ] **Step 2: Fix any pyright errors**

- [ ] **Step 3: Run full test suite (non-benchmark)**

Run: `pytest tests/ -v --timeout=120 -k "not benchmark"`
Expected: ALL PASS

- [ ] **Step 4: Final commit if pyright fixes needed**

```bash
git add -u
git commit -m "fix: resolve pyright type errors from quality overhaul"
```

---

## Execution Order Summary

| Task | Pipeline/Module | Depends On | Est. Complexity |
|------|----------------|-----------|----------------|
| 1 | env_loader | — | Small |
| 2 | quality_scorer | — | Medium |
| 3 | tts_generate | Task 2 | Small |
| 4 | content_generate | Task 2 | Medium |
| 5 | clone_converge | Task 2 | Medium |
| 6 | poster_batch | Tasks 1, 2 | Large |
| 7 | competitive_analysis | Task 2 | Large |
| 8 | benchmark tests | Tasks 3-7 | Small |
| 9 | pyright + verify | Tasks 1-8 | Small |

**Parallelizable:** Tasks 3, 4, 5 are independent after Task 2. Tasks 6 and 7 are independent of each other.
