"""Tests for quality gate layers 3-6."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from middleware.quality_gate import (
    LAYERS,
    log_feedback,
    validate_content_quality,
    validate_delivery,
    validate_visual_qa,
)


class TestLAYERSConstant:
    def test_layers_has_six_entries(self) -> None:
        assert len(LAYERS) >= 6

    def test_layers_has_all_names(self) -> None:
        expected = {
            1: "input_validation",
            2: "output_verification",
            3: "visual_qa",
            4: "content_quality",
            5: "delivery_verification",
            6: "feedback_loop",
        }
        for key, value in expected.items():
            assert LAYERS[key] == value


class TestVisualQA:
    def test_passes_for_good_score(self, tmp_path: Path) -> None:
        """Visual QA passes when composite score >= threshold."""
        from scripts.visual.calculate_delta import DeltaResult
        mock_delta = DeltaResult(
            ssim_score=0.95, pixel_diff_pct=2.0, color_delta_e=1.5,
            layout_score=0.98, text_match_pct=99.0, composite_score=0.95,
        )
        with patch("middleware.quality_gate.calculate_delta", return_value=mock_delta):
            result = validate_visual_qa(
                target=tmp_path / "target.png",
                rendered=tmp_path / "rendered.png",
                threshold=0.80,
            )
        assert result.passed is True

    def test_fails_for_low_score(self, tmp_path: Path) -> None:
        """Visual QA fails when composite score < threshold."""
        from scripts.visual.calculate_delta import DeltaResult
        mock_delta = DeltaResult(
            ssim_score=0.5, pixel_diff_pct=30.0, color_delta_e=15.0,
            layout_score=0.4, text_match_pct=60.0, composite_score=0.45,
        )
        with patch("middleware.quality_gate.calculate_delta", return_value=mock_delta):
            result = validate_visual_qa(
                target=tmp_path / "target.png",
                rendered=tmp_path / "rendered.png",
                threshold=0.80,
            )
        assert result.passed is False
        assert any("visual" in e.lower() or "score" in e.lower() for e in result.errors)


class TestContentQuality:
    def test_passes_for_expected_language(self) -> None:
        """Content quality passes for expected language."""
        result = validate_content_quality(
            content="This is a great product for your business.",
            expected_languages=["en"],
        )
        assert result.passed is True

    def test_flags_unexpected_language(self) -> None:
        """Content quality flags when language detection doesn't match expected."""
        # Mock lingua to return a different language
        with patch("middleware.quality_gate._detect_language", return_value="fr"):
            result = validate_content_quality(
                content="Ceci est un texte en français.",
                expected_languages=["en", "ms"],
            )
        assert result.passed is False


class TestDeliveryVerification:
    def test_passes_for_success_status(self) -> None:
        """Delivery passes for 2xx status."""
        result = validate_delivery(status_code=200, channel="telegram")
        assert result.passed is True

    def test_fails_for_error_status(self) -> None:
        """Delivery fails for non-2xx status."""
        result = validate_delivery(status_code=500, channel="whatsapp")
        assert result.passed is False
        assert any("500" in e for e in result.errors)


class TestFeedbackLoop:
    def test_log_feedback_returns_result(self) -> None:
        """Feedback loop logs and returns a ValidationResult."""
        result = log_feedback(
            tool_name="poster_batch",
            layer=3,
            score=0.92,
            passed=True,
            session_id="test-session",
        )
        assert result.passed is True
        assert result.layer == "feedback_loop"
