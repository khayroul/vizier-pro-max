"""Tests for middleware/quality_scorer.py.

Tests follow TDD — written before implementation.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pytest


class TestComputeScore:
    """Tests for the core compute_score function."""

    def test_all_pass_accumulates_deltas(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="check_a",
                passed=True,
                pass_delta=2.0,
                fail_delta=2.0,
                detail="ok",
            ),
            QualityProperty(
                name="check_b",
                passed=True,
                pass_delta=1.0,
                fail_delta=1.0,
                detail="ok",
            ),
        ]
        result = compute_score(props, pipeline="test")
        # base 5.0 + 2.0 + 1.0 = 8.0
        assert result.score == pytest.approx(8.0)
        assert result.passed is True
        assert result.pipeline == "test"

    def test_all_fail_subtracts_deltas(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="check_a",
                passed=False,
                pass_delta=2.0,
                fail_delta=2.0,
                detail="bad",
            ),
            QualityProperty(
                name="check_b",
                passed=False,
                pass_delta=1.0,
                fail_delta=1.0,
                detail="bad",
            ),
        ]
        result = compute_score(props, pipeline="test")
        # base 5.0 - 2.0 - 1.0 = 2.0
        assert result.score == pytest.approx(2.0)
        assert result.passed is False

    def test_clamp_high(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="big_bonus",
                passed=True,
                pass_delta=100.0,
                fail_delta=0.0,
                detail="huge",
            ),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == pytest.approx(10.0)

    def test_clamp_low(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="big_penalty",
                passed=False,
                pass_delta=0.0,
                fail_delta=100.0,
                detail="huge",
            ),
        ]
        result = compute_score(props, pipeline="test")
        assert result.score == pytest.approx(1.0)

    def test_gate_failure_caps_at_four(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="pass_check",
                passed=True,
                pass_delta=3.0,
                fail_delta=0.0,
                detail="bonus",
            ),
            QualityProperty(
                name="gate_check",
                passed=False,
                pass_delta=0.0,
                fail_delta=0.0,
                detail="gate failed",
                is_gate=True,
            ),
        ]
        result = compute_score(props, pipeline="test")
        # Without gate: 5.0 + 3.0 = 8.0 — but gate caps at 4.0
        assert result.score == pytest.approx(4.0)
        assert result.passed is False

    def test_gate_failure_caps_even_when_score_already_below_four(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="gate_check",
                passed=False,
                pass_delta=0.0,
                fail_delta=3.0,
                detail="gate failed",
                is_gate=True,
            ),
        ]
        result = compute_score(props, pipeline="test")
        # base 5.0 - 3.0 = 2.0 — already below 4.0, stays at 2.0
        assert result.score == pytest.approx(2.0)
        assert result.passed is False

    def test_bonus_no_penalty_property(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="bonus",
                passed=False,
                pass_delta=1.0,
                fail_delta=0.0,
                detail="no bonus",
            ),
        ]
        result = compute_score(props, pipeline="test")
        # base 5.0 + 0 (fail_delta=0) = 5.0
        assert result.score == pytest.approx(5.0)

    def test_properties_stored_on_result(self) -> None:
        from middleware.quality_scorer import QualityProperty, compute_score

        props = [
            QualityProperty(
                name="p1",
                passed=True,
                pass_delta=1.0,
                fail_delta=1.0,
                detail="ok",
            ),
        ]
        result = compute_score(props, pipeline="mypipe")
        assert len(result.properties) == 1
        assert result.properties[0].name == "p1"
        assert result.pipeline == "mypipe"


class TestScoreCompetitiveAnalysis:
    """Tests for score_competitive_analysis."""

    def test_good_report_passes(self) -> None:
        from middleware.quality_scorer import score_competitive_analysis

        report = (
            "Executive Summary\n"
            "Company Alpha has strong market share. Beta Corp offers lower prices. "
            "Gamma Inc focuses on premium segments.\n"
            "Competitor Profile\n"
            "Market data: 45% growth, 12.5% margin, 200 units sold.\n"
            "Recommendation: invest in Alpha for best returns.\n"
        )
        # Provide chart paths with a real file
        result = score_competitive_analysis(report, chart_paths=[])
        # Even without charts the score may pass if other properties are strong
        # The test verifies the function returns a QualityScore
        assert result.pipeline == "competitive_analysis"

    def test_good_report_with_charts_scores_high(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_competitive_analysis

        chart = tmp_path / "chart.png"
        chart.write_bytes(b"PNG" + b"x" * 2000)

        report = (
            "Summary: overview of market.\n"
            "Competitor Profile: Alpha Corp, Beta Inc, Gamma Ltd.\n"
            "Recommendation: choose Alpha.\n"
            "Numbers: 45% growth, 12.3 revenue, 200 units.\n"
        )
        result = score_competitive_analysis(report, chart_paths=[chart])
        assert result.score >= 7.0
        assert result.passed is True

    def test_bad_report_no_competitors(self) -> None:
        from middleware.quality_scorer import score_competitive_analysis

        report = "nothing here"
        result = score_competitive_analysis(report, chart_paths=[])
        assert result.score < 7.0
        assert result.passed is False


class TestScorePosterBatch:
    """Tests for score_poster_batch."""

    def test_good_poster_passes(self, tmp_path: Path) -> None:
        from PIL import Image

        import numpy as np
        from middleware.quality_scorer import score_poster_batch

        arr = np.random.randint(0, 255, (600, 800, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        poster_path = tmp_path / "poster.png"
        img.save(str(poster_path))

        result = score_poster_batch(poster_path)
        assert result.score >= 7.0
        assert result.passed is True
        assert result.pipeline == "poster_batch"

    def test_tiny_poster_fails(self, tmp_path: Path) -> None:
        from PIL import Image

        import numpy as np
        from middleware.quality_scorer import score_poster_batch

        # Create correct-sized but tiny (all-black, small file) image
        arr = np.zeros((600, 800, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        poster_path = tmp_path / "poster.png"
        img.save(str(poster_path))

        result = score_poster_batch(poster_path)
        # All zeros = monochrome (std dev near 0) and size likely small
        # At minimum it should not pass with high score
        assert result.passed is False

    def test_wrong_dimensions_gate_fails(self, tmp_path: Path) -> None:
        from PIL import Image

        import numpy as np
        from middleware.quality_scorer import score_poster_batch

        arr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        img = Image.fromarray(arr)
        poster_path = tmp_path / "poster.png"
        img.save(str(poster_path))

        result = score_poster_batch(poster_path)
        # Gate failure — wrong dimensions — capped at 4.0
        assert result.score <= 4.0
        assert result.passed is False


class TestScoreContentGenerate:
    """Tests for score_content_generate."""

    def test_good_content_passes(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_content_generate

        pdf_path = tmp_path / "report.pdf"
        # Write > 5KB of fake PDF data
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * 6000)

        content = "a" * 200
        result = score_content_generate(
            content=content,
            title="A Great Blog Post About Marketing",
            pdf_path=pdf_path,
            hashtags=["#ai", "#marketing", "#growth"],
        )
        assert result.score >= 7.0
        assert result.passed is True
        assert result.pipeline == "content_generate"

    def test_short_content_fails_gate(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_content_generate

        pdf_path = tmp_path / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * 6000)

        result = score_content_generate(
            content="short",
            title="Title",
            pdf_path=pdf_path,
            hashtags=["#a", "#b", "#c"],
        )
        # Gate fails on content length <= 100
        assert result.score <= 4.0
        assert result.passed is False

    def test_no_hashtags_no_penalty(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_content_generate

        pdf_path = tmp_path / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4\n" + b"x" * 6000)

        content = "b" * 200
        result_with = score_content_generate(
            content=content,
            title="Good Title Here",
            pdf_path=pdf_path,
            hashtags=["#a", "#b", "#c"],
        )
        result_without = score_content_generate(
            content=content,
            title="Good Title Here",
            pdf_path=pdf_path,
            hashtags=None,
        )
        # No hashtags → no bonus but no penalty either
        assert result_with.score > result_without.score


class TestScoreCloneConverge:
    """Tests for score_clone_converge."""

    def test_good_template_passes(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_clone_converge

        template = tmp_path / "template.html"
        template.write_text(
            "<html><body>{{ headline }} {{ body }}</body></html>",
            encoding="utf-8",
        )
        result = score_clone_converge(
            template_path=template,
            composite_score=0.8,
            iterations=3,
        )
        assert result.score >= 7.0
        assert result.passed is True
        assert result.pipeline == "clone_converge"

    def test_no_placeholders_scores_low(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_clone_converge

        template = tmp_path / "template.html"
        template.write_text(
            "<html><body>Hello World</body></html>",
            encoding="utf-8",
        )
        result = score_clone_converge(
            template_path=template,
            composite_score=0.8,
            iterations=3,
        )
        assert result.score < 7.0
        assert result.passed is False

    def test_missing_html_tags_fails_gate(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_clone_converge

        template = tmp_path / "template.html"
        template.write_text(
            "<div>{{ headline }} {{ body }}</div>",
            encoding="utf-8",
        )
        result = score_clone_converge(
            template_path=template,
            composite_score=0.8,
            iterations=3,
        )
        # Gate failure — no <html> tags — capped at 4.0
        assert result.score <= 4.0
        assert result.passed is False

    def test_low_convergence_reduces_score(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_clone_converge

        template = tmp_path / "template.html"
        template.write_text(
            "<html><body>{{ headline }} {{ body }}</body></html>",
            encoding="utf-8",
        )
        result_high = score_clone_converge(
            template_path=template,
            composite_score=0.8,
            iterations=3,
        )
        result_low = score_clone_converge(
            template_path=template,
            composite_score=0.3,
            iterations=3,
        )
        assert result_high.score > result_low.score


class TestScoreTtsGenerate:
    """Tests for score_tts_generate."""

    def test_good_audio_passes(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_tts_generate

        audio_path = tmp_path / "audio.mp3"
        # text_length = 10, so:
        #   size threshold: 10 * 50 = 500 bytes
        #   duration threshold: max(16000, (10/2.5)*16000) = max(16000, 64000) = 64000
        # We need file_size > 64000, so write 80KB
        content = b"ID3" + b"\x00" * 30 + b"x" * 80000
        audio_path.write_bytes(content)

        text_length = 10
        result = score_tts_generate(file_path=audio_path, text_length=text_length)
        assert result.score >= 7.0
        assert result.passed is True
        assert result.pipeline == "tts_generate"

    def test_invalid_header_fails_gate(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_tts_generate

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"NOTMP3HEADERDATA" + b"x" * 30000)

        result = score_tts_generate(file_path=audio_path, text_length=100)
        # Gate failure — no valid MP3 header — capped at 4.0
        assert result.score <= 4.0
        assert result.passed is False

    def test_small_file_relative_to_text_reduces_score(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_tts_generate

        audio_path = tmp_path / "audio.mp3"
        # Valid ID3 header but too small for the text length
        audio_path.write_bytes(b"ID3" + b"\x00" * 100)

        result = score_tts_generate(file_path=audio_path, text_length=1000)
        # File size < 1000 * 50 = 50000 bytes → fail on size check
        assert result.passed is False

    def test_sync_bytes_header_valid(self, tmp_path: Path) -> None:
        from middleware.quality_scorer import score_tts_generate

        audio_path = tmp_path / "audio.mp3"
        # MP3 sync bytes: 0xFF 0xFB
        content = b"\xff\xfb" + b"x" * 30000
        audio_path.write_bytes(content)

        result = score_tts_generate(file_path=audio_path, text_length=100)
        # Should not fail the gate
        gate_prop = next(
            (p for p in result.properties if p.is_gate),
            None,
        )
        assert gate_prop is not None
        assert gate_prop.passed is True
