"""Tests for playwright_screenshot wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


class TestScreenshotHtml:
    def test_screenshot_html_string(self, tmp_path: Path) -> None:
        from scripts.visual.screenshot_html import run
        output = tmp_path / "output.png"
        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            output.write_bytes(b"\x89PNG fake")
            result = run(html_content="<h1>Hello</h1>", output_path=str(output))
        assert result["file_path"] == str(output)
        assert output.exists()

    def test_screenshot_html_file(self, tmp_path: Path) -> None:
        from scripts.visual.screenshot_html import run
        html_file = tmp_path / "input.html"
        html_file.write_text("<h1>Test</h1>")
        output = tmp_path / "output.png"
        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            output.write_bytes(b"\x89PNG fake")
            result = run(input_path=str(html_file), output_path=str(output))
        assert result["file_path"] == str(output)

    def test_screenshot_requires_html_or_path(self) -> None:
        from scripts.visual.screenshot_html import run
        with pytest.raises(ValueError, match="html_content or input_path"):
            run(output_path="/tmp/out.png")

    def test_screenshot_custom_viewport(self, tmp_path: Path) -> None:
        from scripts.visual.screenshot_html import run
        output = tmp_path / "output.png"
        with patch("scripts.visual.screenshot_html._render_with_playwright") as mock_render:
            mock_render.return_value = str(output)
            output.write_bytes(b"\x89PNG fake")
            run(html_content="<h1>Hi</h1>", output_path=str(output), viewport_width=1920, viewport_height=1080)
        call_kwargs = mock_render.call_args[1]
        assert call_kwargs["viewport_width"] == 1920
        assert call_kwargs["viewport_height"] == 1080
