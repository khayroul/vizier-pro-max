"""Tests for novel_generate pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pipelines.novel_generate import run


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


class TestNovelGenerate:
    def test_generates_manuscript_package(self, tmp_path: Path) -> None:
        with (
            patch(
                "pipelines.novel_generate.render_pdf",
                side_effect=_fake_pdf_run,
            ),
            patch(
                "pipelines.novel_generate.assemble_epub",
                side_effect=_fake_epub_run,
            ),
        ):
            result = run(
                title="Lanterns Over Penang",
                author="Vizier",
                chapters=[
                    {"title": "Arrival", "body": "A" * 320, "summary": "The city wakes."},
                    {"title": "Storm", "body": "B" * 330},
                    {"title": "Dawn", "body": "C" * 340},
                ],
                output_dir=str(tmp_path / "novel"),
            )

        assert result["status"] == "completed"
        assert result["chapter_count"] == 3
        assert Path(result["html_path"]).exists()
        assert Path(result["pdf_path"]).exists()
        assert Path(result["epub_path"]).exists()
        assert result["quality_report"]["passed"] is True

    def test_requires_chapters(self, tmp_path: Path) -> None:
        try:
            run(
                title="Lanterns Over Penang",
                author="Vizier",
                chapters=[],
                output_dir=str(tmp_path / "novel"),
                export_pdf=False,
                export_epub=False,
            )
        except ValueError as exc:
            assert "chapters" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
