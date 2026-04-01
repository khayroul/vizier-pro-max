"""Tests for clone_converge — full convergence loop."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.clone_converge import run


class TestCloneConverge:
    def test_run_with_mocked_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline with mocked LLM and screenshot."""
        from PIL import Image

        # Create a target image
        target = tmp_path / "target.png"
        Image.new("RGB", (100, 100), color=(255, 0, 0)).save(str(target))

        # Mock the LLM call to return HTML
        mock_html = (
            "<html><body style='background:red;"
            "width:100px;height:100px'></body></html>"
        )

        # Mock screenshot to return an image similar to target
        rendered = tmp_path / "rendered.png"
        Image.new("RGB", (100, 100), color=(250, 5, 5)).save(str(rendered))

        llm_patch = patch(
            "pipelines.clone_converge._call_llm_for_html",
            return_value=mock_html,
        )
        render_patch = patch(
            "pipelines.clone_converge._render_html_to_png",
            return_value=rendered,
        )
        with llm_patch, render_patch:
            result = run(
                target_image_path=str(target),
                output_dir=str(tmp_path / "output"),
                max_iterations=2,
                threshold=0.70,
            )

        assert result["status"] in ("converged", "max_iterations")
        assert "score" in result

    def test_run_returns_score(self, tmp_path: Path) -> None:
        """Pipeline always returns a composite score."""
        from PIL import Image

        target = tmp_path / "target.png"
        Image.new("RGB", (50, 50), color=(0, 255, 0)).save(str(target))

        rendered = tmp_path / "rendered.png"
        Image.new("RGB", (50, 50), color=(0, 255, 0)).save(str(rendered))

        mock_html = "<html><body style='background:green'></body></html>"

        llm_patch = patch(
            "pipelines.clone_converge._call_llm_for_html",
            return_value=mock_html,
        )
        render_patch = patch(
            "pipelines.clone_converge._render_html_to_png",
            return_value=rendered,
        )
        with llm_patch, render_patch:
            result = run(
                target_image_path=str(target),
                output_dir=str(tmp_path / "output"),
                threshold=0.70,
            )

        assert isinstance(result["score"], float)
