"""Tests for fal_generate wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateImage:
    def test_generate_returns_paths(self, tmp_path: Path) -> None:
        from scripts.visual.generate_image import run

        output = tmp_path / "generated.png"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "images": [{"url": "https://fal.ai/output/abc.png"}],
        }
        mock_download = MagicMock()
        mock_download.status_code = 200
        mock_download.content = b"\x89PNG fake image data"

        with patch("httpx.post", return_value=mock_response), \
             patch("httpx.get", return_value=mock_download):
            result = run(
                prompt="A sunset over mountains",
                output_path=str(output),
            )
        assert result["file_path"] == str(output)
        assert output.exists()

    def test_generate_missing_api_key_raises(self) -> None:
        from scripts.visual.generate_image import run

        with patch.dict("os.environ", {}, clear=True), \
             pytest.raises(RuntimeError, match="FAL_KEY"):
            run(prompt="test", output_path="/tmp/out.png")

    def test_generate_api_error_raises(self, tmp_path: Path) -> None:
        from scripts.visual.generate_image import run

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limited"
        mock_response.raise_for_status.side_effect = Exception("429 Too Many Requests")

        with patch("httpx.post", return_value=mock_response), \
             patch.dict("os.environ", {"FAL_KEY": "test-key"}), \
             pytest.raises(Exception, match="429"):
            run(prompt="test", output_path=str(tmp_path / "out.png"))
