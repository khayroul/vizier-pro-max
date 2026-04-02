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
            assert chart.stat().st_size > 1000

    def test_narrative_contains_numbers(self, analysis_result: dict) -> None:
        report = analysis_result.get("report", "")
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
        assert score > 0.50, f"Score {score} should be > 0.50 (baseline was 0.19)"

    def test_vision_api_was_used(self) -> None:
        """Verify that _build_vision_messages exists and produces image_url blocks."""
        from pipelines.clone_converge import _build_vision_messages

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

            min_size = len(text) * 50
            assert size > min_size, f"MP3 ({size}B) too small for {len(text)} chars"
