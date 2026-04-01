"""Tests for pypdf_merge wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter


@pytest.fixture()
def sample_pdfs(tmp_path: Path) -> list[Path]:
    """Create 2 minimal PDFs."""
    pdfs = []
    for i in range(2):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        path = tmp_path / f"doc{i}.pdf"
        with open(path, "wb") as f:
            writer.write(f)
        pdfs.append(path)
    return pdfs


class TestMergePdfs:
    def test_merge_two_pdfs(self, sample_pdfs: list[Path], tmp_path: Path) -> None:
        from scripts.document.merge_pdfs import run

        output = tmp_path / "merged.pdf"
        result = run(
            input_paths=[str(p) for p in sample_pdfs],
            output_path=str(output),
            operation="merge",
        )
        assert Path(result["file_path"]).exists()
        assert output.stat().st_size > 0

    def test_extract_page(self, sample_pdfs: list[Path], tmp_path: Path) -> None:
        from scripts.document.merge_pdfs import run

        output = tmp_path / "extracted.pdf"
        result = run(
            input_paths=[str(sample_pdfs[0])],
            output_path=str(output),
            operation="extract",
            pages=[0],
        )
        assert Path(result["file_path"]).exists()

    def test_unknown_operation_raises(
        self, sample_pdfs: list[Path], tmp_path: Path
    ) -> None:
        from scripts.document.merge_pdfs import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(
                input_paths=[str(sample_pdfs[0])],
                output_path=str(tmp_path / "out.pdf"),
                operation="encrypt",
            )
