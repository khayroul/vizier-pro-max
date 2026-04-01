"""Tests for data-driven file upload triggers."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.triggers.data_trigger import (
    FileClassification,
    ProcessResult,
    ValidationResult,
    classify_file,
    detect_schema,
    process_file,
    validate_file,
)


@pytest.fixture()
def rules_path() -> Path:
    """Return path to the test-friendly filename_rules.yaml."""
    return Path(__file__).resolve().parents[2] / "config" / "triggers" / "filename_rules.yaml"


@pytest.fixture()
def uploads_dir(tmp_path: Path) -> Path:
    """Create a temporary uploads directory."""
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    return uploads


# --- classify_file tests ---


def test_classify_posters_csv(rules_path: Path) -> None:
    """Posters prefix maps to vizier-visual + poster_batch."""
    result = classify_file("posters_march.csv", rules_path=rules_path)
    assert isinstance(result, FileClassification)
    assert result.toolset == "vizier-visual"
    assert result.pipeline == "poster_batch"
    assert result.matched_rule == "posters_"


def test_classify_invoices(rules_path: Path) -> None:
    """Invoices prefix maps to vizier-document with no pipeline."""
    result = classify_file("invoices_q1.csv", rules_path=rules_path)
    assert result.toolset == "vizier-document"
    assert result.pipeline is None
    assert result.matched_rule == "invoices_"


def test_classify_unknown(rules_path: Path) -> None:
    """Unknown filename falls back to vizier-fallback."""
    result = classify_file("random_file.csv", rules_path=rules_path)
    assert result.toolset == "vizier-fallback"
    assert result.pipeline is None
    assert result.matched_rule is None


# --- validate_file tests ---


def test_validate_valid_csv(tmp_path: Path) -> None:
    """A well-formed CSV passes validation."""
    csv_file = tmp_path / "valid.csv"
    csv_file.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\n")
    result = validate_file(csv_file)
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert result.format == "csv"
    assert result.error is None


def test_validate_invalid_file(tmp_path: Path) -> None:
    """A .txt file is not an accepted format."""
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("just some notes")
    result = validate_file(txt_file)
    assert result.valid is False
    assert result.error is not None
    assert "unsupported" in result.error.lower() or "extension" in result.error.lower()


def test_validate_empty_file(tmp_path: Path) -> None:
    """An empty CSV file fails validation."""
    empty_csv = tmp_path / "empty.csv"
    empty_csv.write_text("")
    result = validate_file(empty_csv)
    assert result.valid is False
    assert result.error is not None


def test_validate_valid_json(tmp_path: Path) -> None:
    """A well-formed JSON file passes validation."""
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps([{"name": "Alice", "age": 30}]))
    result = validate_file(json_file)
    assert result.valid is True
    assert result.format == "json"


def test_validate_invalid_json(tmp_path: Path) -> None:
    """A malformed JSON file fails validation."""
    json_file = tmp_path / "bad.json"
    json_file.write_text("{not valid json")
    result = validate_file(json_file)
    assert result.valid is False


def test_validate_xlsx_magic_bytes(tmp_path: Path) -> None:
    """An XLSX file with correct PK zip header passes."""
    xlsx_file = tmp_path / "data.xlsx"
    # PK zip header + some padding
    xlsx_file.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    result = validate_file(xlsx_file)
    assert result.valid is True
    assert result.format == "xlsx"


def test_validate_xlsx_bad_magic(tmp_path: Path) -> None:
    """An XLSX file without PK zip header fails."""
    xlsx_file = tmp_path / "fake.xlsx"
    xlsx_file.write_bytes(b"NOT_A_ZIP" + b"\x00" * 100)
    result = validate_file(xlsx_file)
    assert result.valid is False


# --- detect_schema tests ---


def test_detect_schema_csv(tmp_path: Path) -> None:
    """CSV schema detection returns column names with string type."""
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,age,city\nAlice,30,NYC\n")
    schema = detect_schema(csv_file)
    assert schema == {"name": "string", "age": "string", "city": "string"}


def test_detect_schema_json(tmp_path: Path) -> None:
    """JSON schema detection returns keys from first item."""
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps([{"id": 1, "title": "hello"}]))
    schema = detect_schema(json_file)
    assert "id" in schema
    assert "title" in schema


# --- process_file tests ---


def test_process_file_moves_to_processed(
    uploads_dir: Path, rules_path: Path
) -> None:
    """Successful processing moves file to _processed/."""
    csv_file = uploads_dir / "posters_march.csv"
    csv_file.write_text("name,age\nAlice,30\n")

    with patch("scripts.triggers.data_trigger._start_hermes_session"):
        result = process_file(csv_file, uploads_dir, rules_path=rules_path)

    assert isinstance(result, ProcessResult)
    assert result.status == "processed"
    assert result.toolset == "vizier-visual"
    assert result.pipeline == "poster_batch"
    assert result.error is None
    # Original file should be gone
    assert not csv_file.exists()
    # Should be in _processed/
    processed_dir = uploads_dir / "_processed"
    assert processed_dir.exists()
    processed_files = list(processed_dir.iterdir())
    assert len(processed_files) == 1
    assert "posters_march.csv" in processed_files[0].name


def test_process_file_moves_to_failed(
    uploads_dir: Path, rules_path: Path
) -> None:
    """Validation failure moves file to _failed/."""
    txt_file = uploads_dir / "bad_file.txt"
    txt_file.write_text("not a valid upload format")

    result = process_file(txt_file, uploads_dir, rules_path=rules_path)

    assert result.status == "failed"
    assert result.error is not None
    # Original file should be gone
    assert not txt_file.exists()
    # Should be in _failed/
    failed_dir = uploads_dir / "_failed"
    assert failed_dir.exists()
    failed_files = list(failed_dir.iterdir())
    assert len(failed_files) == 1
    assert "bad_file.txt" in failed_files[0].name
