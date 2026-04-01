"""Tests for pandoc_convert wrapper."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


class TestConvertFormat:
    def test_markdown_to_html(self, tmp_path: Path) -> None:
        from scripts.document.convert_format import run

        md_file = tmp_path / "input.md"
        md_file.write_text("# Hello\n\nWorld")
        output = tmp_path / "output.html"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            run(
                input_path=str(md_file),
                output_path=str(output),
                from_format="markdown",
                to_format="html",
            )
        cmd = mock_run.call_args[0][0]
        assert "pandoc" in cmd[0]
        assert "-f" in cmd
        assert "markdown" in cmd

    def test_auto_detect_format(self, tmp_path: Path) -> None:
        from scripts.document.convert_format import run

        md_file = tmp_path / "input.md"
        md_file.write_text("# Test")
        output = tmp_path / "output.docx"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            run(input_path=str(md_file), output_path=str(output))
        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "markdown" in cmd  # auto-detected from .md
        assert "docx" in cmd      # auto-detected from .docx
