"""Tests for the shared longform spine helpers."""
from __future__ import annotations

from pathlib import Path

from pipelines.longform.spine import image_to_data_uri, normalize_sections


class TestLongformSpine:
    def test_image_to_data_uri(self, tmp_path: Path) -> None:
        image = tmp_path / "sample.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

        uri = image_to_data_uri(str(image))

        assert uri.startswith("data:image/png;base64,")

    def test_normalize_sections_requires_heading(self) -> None:
        try:
            normalize_sections([{"body": "Hello"}])
        except ValueError as exc:
            assert "heading" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

