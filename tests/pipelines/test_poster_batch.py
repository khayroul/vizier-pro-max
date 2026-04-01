"""Tests for poster_batch pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pipelines.poster_batch import run


class TestPosterBatch:
    def test_batch_produces_posters(self, tmp_path: Path) -> None:
        """Full batch: CSV rows -> template render -> screenshots."""
        # Create template
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<h1>{{ title }}</h1><p>{{ body }}</p>")

        # Create CSV
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("title,body\nHello,World\nFoo,Bar\n")

        output_dir = str(tmp_path / "posters")

        with patch("pipelines.poster_batch.screenshot_run") as mock_ss:
            mock_ss.side_effect = [
                {"file_path": str(tmp_path / "posters" / "poster_0000.png")},
                {"file_path": str(tmp_path / "posters" / "poster_0001.png")},
            ]

            result = run(
                template_path=str(tmpl),
                data_path=str(csv_file),
                output_dir=output_dir,
            )

        assert result["status"] == "completed"
        assert result["count"] == 2
        assert len(result["posters"]) == 2
        assert mock_ss.call_count == 2

    def test_missing_template_raises(self, tmp_path: Path) -> None:
        """Missing template raises FileNotFoundError."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n")

        with pytest.raises(FileNotFoundError, match="Template not found"):
            run(template_path="/nonexistent.html", data_path=str(csv_file))

    def test_missing_data_raises(self, tmp_path: Path) -> None:
        """Missing data file raises FileNotFoundError."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<p>test</p>")

        with pytest.raises(FileNotFoundError, match="Data file not found"):
            run(template_path=str(tmpl), data_path="/nonexistent.csv")

    def test_no_template_path_raises(self) -> None:
        """No template_path raises ValueError."""
        with pytest.raises(ValueError, match="template_path is required"):
            run(data_path="/some/data.csv")

    def test_empty_csv(self, tmp_path: Path) -> None:
        """Empty CSV returns empty posters list."""
        tmpl = tmp_path / "template.html"
        tmpl.write_text("<p>{{ x }}</p>")
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("x\n")

        result = run(
            template_path=str(tmpl),
            data_path=str(csv_file),
            output_dir=str(tmp_path / "out"),
        )
        assert result["count"] == 0
        assert result["posters"] == []
