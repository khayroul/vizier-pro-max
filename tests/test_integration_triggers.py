"""Integration tests for data-driven file upload triggers."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.triggers.data_trigger import process_file


@pytest.fixture()
def rules_path() -> Path:
    """Return path to the filename_rules.yaml config."""
    return Path(__file__).resolve().parents[1] / "config" / "triggers" / "filename_rules.yaml"


@pytest.fixture()
def uploads_dir(tmp_path: Path) -> Path:
    """Create a temporary uploads directory."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    return uploads


class TestIntegrationTriggerSuccess:
    """End-to-end: valid CSV placed in uploads/ is processed correctly."""

    def test_valid_csv_processed_and_moved(
        self, uploads_dir: Path, rules_path: Path
    ) -> None:
        """Place posters_test.csv, trigger processes, file lands in _processed/."""
        csv_file = uploads_dir / "posters_test.csv"
        csv_file.write_text("title,color,size\nSpring Sale,red,A3\nSummer,blue,A2\n")

        with patch("scripts.triggers.data_trigger._start_hermes_session"):
            result = process_file(csv_file, uploads_dir, rules_path=rules_path)

        assert result.status == "processed"
        assert result.toolset == "vizier-visual"
        assert result.pipeline == "poster_batch"
        assert result.schema == {"title": "string", "color": "string", "size": "string"}

        # No file left in uploads root
        remaining = [
            f for f in uploads_dir.iterdir()
            if f.is_file()
        ]
        assert remaining == []

        # File is in _processed/
        processed_dir = uploads_dir / "_processed"
        processed_files = list(processed_dir.iterdir())
        assert len(processed_files) == 1
        assert "posters_test.csv" in processed_files[0].name


class TestIntegrationTriggerFailure:
    """End-to-end: invalid file placed in uploads/ ends up in _failed/."""

    def test_invalid_content_moved_to_failed(
        self, uploads_dir: Path, rules_path: Path
    ) -> None:
        """Place a .txt file (unsupported), trigger rejects, file lands in _failed/."""
        bad_file = uploads_dir / "mystery.txt"
        bad_file.write_text("this is not CSV, JSON, or XLSX")

        result = process_file(bad_file, uploads_dir, rules_path=rules_path)

        assert result.status == "failed"
        assert result.error is not None

        # No file left in uploads root
        remaining = [f for f in uploads_dir.iterdir() if f.is_file()]
        assert remaining == []

        # File is in _failed/
        failed_dir = uploads_dir / "_failed"
        failed_files = list(failed_dir.iterdir())
        assert len(failed_files) == 1
        assert "mystery.txt" in failed_files[0].name

    def test_malformed_csv_moved_to_failed(
        self, uploads_dir: Path, rules_path: Path
    ) -> None:
        """Place an empty CSV (no content), trigger rejects it."""
        empty_csv = uploads_dir / "posters_empty.csv"
        empty_csv.write_text("")

        result = process_file(empty_csv, uploads_dir, rules_path=rules_path)

        assert result.status == "failed"
        assert result.error is not None

        failed_dir = uploads_dir / "_failed"
        assert failed_dir.exists()
        failed_files = list(failed_dir.iterdir())
        assert len(failed_files) == 1
