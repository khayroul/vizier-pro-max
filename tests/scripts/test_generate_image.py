"""Tests for the fal.ai image wrapper via the Vizier gateway."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)


class TestGenerateImage:
    def test_generate_routes_through_gateway(self, tmp_path: Path) -> None:
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

        with patch("httpx.post", return_value=mock_response) as mock_post, \
             patch("httpx.get", return_value=mock_download):
            result = run(
                prompt="A sunset over mountains",
                output_path=str(output),
                gateway_headers={
                    "x-vizier-source": "pipeline",
                    "x-vizier-modality": "image_generation",
                    "x-vizier-deliverable-id": "did-123",
                },
            )

        assert result["file_path"] == str(output)
        assert output.exists()
        assert mock_post.call_args.args[0] == "http://127.0.0.1:11436/v1/images/generations"
        assert mock_post.call_args.kwargs["headers"]["x-vizier-deliverable-id"] == "did-123"
        assert mock_post.call_args.kwargs["json"]["model"] == "fal-ai/flux/schnell"
        assert mock_post.call_args.kwargs["json"]["size"] == "1024x1024"
        assert mock_post.call_args.kwargs["json"]["image_size"] == {"width": 1024, "height": 1024}

    def test_generate_gateway_error_raises(self, tmp_path: Path) -> None:
        from scripts.visual.generate_image import run

        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.text = "Gateway error"

        with patch("httpx.post", return_value=mock_response), \
             pytest.raises(RuntimeError, match="Vizier gateway image generation failed"):
            run(prompt="test", output_path=str(tmp_path / "out.png"))
