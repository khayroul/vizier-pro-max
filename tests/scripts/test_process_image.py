"""Tests for pillow_process wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture()
def sample_image(tmp_path: Path) -> Path:
    """Create a 200x200 red image."""
    img = Image.new("RGB", (200, 200), color="red")
    path = tmp_path / "input.png"
    img.save(path)
    return path


class TestProcessImage:
    def test_resize(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "resized.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="resize",
            width=100,
            height=100,
        )
        assert Path(result["file_path"]).exists()
        img = Image.open(result["file_path"])
        assert img.size == (100, 100)

    def test_crop(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "cropped.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="crop",
            left=10,
            top=10,
            right=110,
            bottom=110,
        )
        img = Image.open(result["file_path"])
        assert img.size == (100, 100)

    def test_rotate(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        output = tmp_path / "rotated.png"
        result = run(
            input_path=str(sample_image),
            output_path=str(output),
            operation="rotate",
            angle=90,
        )
        img = Image.open(result["file_path"])
        assert img.size == (200, 200)

    def test_unknown_operation_raises(self, sample_image: Path, tmp_path: Path) -> None:
        from scripts.visual.process_image import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_path=str(sample_image),
                output_path=str(tmp_path / "out.png"),
                operation="warp",
            )
