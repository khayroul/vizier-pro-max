"""Tests for children_book_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.children_book_generate import run


def _write_file(path: str, payload: bytes) -> None:
    Path(path).write_bytes(payload)


def _fake_pdf_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_file(output_path, b"%PDF-1.4")
    return {"file_path": output_path}


def _fake_epub_run(**kwargs: object) -> dict[str, str]:
    output_path = str(kwargs["output_path"])
    _write_file(output_path, b"epub")
    return {"file_path": output_path}


class TestChildrenBookGenerate:
    def test_generates_storybook_package(self, tmp_path: Path) -> None:
        image_path = tmp_path / "spread.png"
        image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

        with (
            patch(
                "pipelines.children_book_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.children_book_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="Mika and the Moon Kite",
                author="Vizier",
                spreads=[
                    {"title": "Spread 1", "text": "Mika found a kite.", "illustration_path": str(image_path)},
                    {"title": "Spread 2", "text": "The moon glowed softly.", "illustration_path": str(image_path)},
                    {"title": "Spread 3", "text": "A breeze carried whispers.", "illustration_path": str(image_path)},
                    {"title": "Spread 4", "text": "The kite danced above town."},
                    {"title": "Spread 5", "text": "Friends ran after the tail."},
                    {"title": "Spread 6", "text": "They laughed beneath the stars."},
                ],
                output_dir=str(tmp_path / "storybook"),
            )

        assert result["status"] == "completed"
        assert result["spread_count"] == 6
        assert Path(result["html_path"]).exists()
        assert Path(result["pdf_path"]).exists()
        assert Path(result["epub_path"]).exists()
        assert result["quality_report"]["passed"] is True

    def test_requires_spreads(self, tmp_path: Path) -> None:
        try:
            run(
                title="Mika and the Moon Kite",
                author="Vizier",
                spreads=[],
                output_dir=str(tmp_path / "storybook"),
                export_pdf=False,
                export_epub=False,
            )
        except ValueError as exc:
            assert "spreads" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
