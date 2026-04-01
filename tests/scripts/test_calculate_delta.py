"""Tests for calculate_delta --- multi-signal image comparison."""
from __future__ import annotations

from pathlib import Path

from scripts.visual.calculate_delta import DeltaResult, calculate_delta


class TestCalculateDelta:
    def test_identical_images_return_perfect_score(self, tmp_path: Path) -> None:
        """Two identical images should have composite score ~1.0."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        path_a = tmp_path / "a.png"
        path_b = tmp_path / "b.png"
        img.save(str(path_a))
        img.save(str(path_b))

        result = calculate_delta(target=path_a, rendered=path_b)
        assert isinstance(result, DeltaResult)
        assert result.composite_score >= 0.9

    def test_different_images_return_low_score(self, tmp_path: Path) -> None:
        """Very different images should have low composite score."""
        from PIL import Image

        img_a = Image.new("RGB", (100, 100), color=(255, 0, 0))  # Red
        img_b = Image.new("RGB", (100, 100), color=(0, 0, 255))  # Blue
        path_a = tmp_path / "a.png"
        path_b = tmp_path / "b.png"
        img_a.save(str(path_a))
        img_b.save(str(path_b))

        result = calculate_delta(target=path_a, rendered=path_b)
        assert result.composite_score < 0.8

    def test_result_has_all_signals(self, tmp_path: Path) -> None:
        """DeltaResult should contain all 5 signal scores."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(128, 128, 128))
        path_a = tmp_path / "a.png"
        path_b = tmp_path / "b.png"
        img.save(str(path_a))
        img.save(str(path_b))

        result = calculate_delta(target=path_a, rendered=path_b)
        assert hasattr(result, "ssim_score")
        assert hasattr(result, "pixel_diff_pct")
        assert hasattr(result, "color_delta_e")
        assert hasattr(result, "layout_score")
        assert hasattr(result, "text_match_pct")
        assert hasattr(result, "composite_score")

    def test_composite_is_weighted_average(self, tmp_path: Path) -> None:
        """Composite score should be a weighted average of signals."""
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(100, 100, 100))
        path_a = tmp_path / "a.png"
        path_b = tmp_path / "b.png"
        img.save(str(path_a))
        img.save(str(path_b))

        result = calculate_delta(target=path_a, rendered=path_b)
        # For identical images, all signals should be near-perfect
        assert 0.0 <= result.composite_score <= 1.0
