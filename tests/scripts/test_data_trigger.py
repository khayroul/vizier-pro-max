"""Tests for data-driven file upload triggers."""
from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.triggers.data_trigger import (
    FileClassification,
    ProcessResult,
    ValidationResult,
    _start_hermes_session,
    classify_file,
    detect_schema,
    poll_uploads,
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


def test_classify_content_calendar(rules_path: Path) -> None:
    """Content calendar prefix maps to vizier-content + content_generate."""
    result = classify_file("content_calendar_april.csv", rules_path=rules_path)
    assert result.toolset == "vizier-content"
    assert result.pipeline == "content_generate"


def test_classify_analysis(rules_path: Path) -> None:
    """Analysis prefix maps to vizier-research + competitive_analysis."""
    result = classify_file("analysis_q2.csv", rules_path=rules_path)
    assert result.toolset == "vizier-research"
    assert result.pipeline == "competitive_analysis"


def test_detect_schema_xlsx(tmp_path: Path) -> None:
    """XLSX schema detection returns empty dict (stub)."""
    xlsx_file = tmp_path / "data.xlsx"
    xlsx_file.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    schema = detect_schema(xlsx_file)
    assert schema == {}


def test_detect_schema_unsupported(tmp_path: Path) -> None:
    """Unsupported file type returns empty schema."""
    txt_file = tmp_path / "data.txt"
    txt_file.write_text("hello")
    schema = detect_schema(txt_file)
    assert schema == {}


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


# --- Line 140: unreachable "Unknown format" ---
# This line is unreachable by design (guard after extension check).
# Adding pragma: no cover in source is the correct approach.


# --- Line 148: empty CSV content (non-zero file, whitespace only) ---


def test_validate_csv_whitespace_only(tmp_path: Path) -> None:
    """A CSV file with only whitespace is treated as empty."""
    csv_file = tmp_path / "blank.csv"
    csv_file.write_text("   \n  \n")
    result = validate_file(csv_file)
    assert result.valid is False
    assert result.format == "csv"
    assert result.error is not None
    assert "empty" in result.error.lower()


# --- Lines 152-153: csv.Error from binary garbage ---


def test_validate_csv_sniff_error(tmp_path: Path) -> None:
    """When csv.Sniffer raises csv.Error, validation fails gracefully."""
    csv_file = tmp_path / "garbage.csv"
    csv_file.write_text("some,data\n1,2\n")

    with patch.object(
        csv.Sniffer, "sniff", side_effect=csv.Error("Could not determine delimiter")
    ):
        result = validate_file(csv_file)

    assert result.valid is False
    assert result.format == "csv"
    assert result.error is not None
    assert "csv validation failed" in result.error.lower()


# --- Lines 214-216: JSON dict-only data (not list) ---


def test_detect_schema_json_dict(tmp_path: Path) -> None:
    """JSON schema detection works for a top-level dict."""
    json_file = tmp_path / "config.json"
    json_file.write_text(json.dumps({"name": "Alice", "count": 42, "active": True}))
    schema = detect_schema(json_file)
    assert schema == {"name": "str", "count": "int", "active": "bool"}


def test_detect_schema_json_scalar(tmp_path: Path) -> None:
    """JSON schema detection returns empty for a scalar value."""
    json_file = tmp_path / "scalar.json"
    json_file.write_text(json.dumps("just a string"))
    schema = detect_schema(json_file)
    assert schema == {}


# --- Line 238: xlsx schema stub warning ---


def test_detect_schema_xlsx_logs_warning(tmp_path: Path) -> None:
    """XLSX schema detection emits a warning log (covers line 238)."""
    from scripts.triggers.data_trigger import _detect_schema_xlsx

    xlsx_file = tmp_path / "data.xlsx"
    xlsx_file.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    # Call internal function directly to ensure the logger.warning line executes
    schema = _detect_schema_xlsx(xlsx_file)
    assert schema == {}


# --- Line 238: _start_hermes_session body ---


def test_start_hermes_session_runs(tmp_path: Path) -> None:
    """Calling _start_hermes_session executes its logger.info body."""
    dummy_file = tmp_path / "test.csv"
    dummy_file.write_text("a,b\n1,2\n")
    # Should not raise; just exercises the logger.info call
    _start_hermes_session(
        toolset="vizier-test",
        pipeline=None,
        file_path=dummy_file,
        schema={"a": "string", "b": "string"},
    )


# --- Lines 314-317: exception in Hermes session start ---


def test_process_file_hermes_failure(
    uploads_dir: Path, rules_path: Path
) -> None:
    """When _start_hermes_session raises, file moves to _failed/."""
    csv_file = uploads_dir / "posters_march.csv"
    csv_file.write_text("name,age\nAlice,30\n")

    with patch(
        "scripts.triggers.data_trigger._start_hermes_session",
        side_effect=RuntimeError("connection refused"),
    ):
        result = process_file(csv_file, uploads_dir, rules_path=rules_path)

    assert result.status == "failed"
    assert result.error is not None
    assert "Hermes session failed" in result.error
    assert "connection refused" in result.error
    assert result.toolset == "vizier-visual"
    assert result.schema == {"name": "string", "age": "string"}

    failed_dir = uploads_dir / "_failed"
    assert failed_dir.exists()
    failed_files = list(failed_dir.iterdir())
    assert len(failed_files) == 1


# --- Lines 354-370: poll_uploads infinite loop ---


def test_poll_uploads_processes_files_then_stops(
    uploads_dir: Path, rules_path: Path
) -> None:
    """poll_uploads processes files and stops on KeyboardInterrupt."""
    csv_file = uploads_dir / "posters_test.csv"
    csv_file.write_text("title,color\nSpring,red\n")

    call_count = 0

    def sleep_then_interrupt(seconds: float) -> None:
        nonlocal call_count
        call_count += 1
        raise KeyboardInterrupt

    with (
        patch("scripts.triggers.data_trigger._start_hermes_session"),
        patch("scripts.triggers.data_trigger.time.sleep", side_effect=sleep_then_interrupt),
    ):
        poll_uploads(uploads_dir, interval=1.0, rules_path=rules_path)

    assert call_count == 1
    # File should have been processed and moved
    assert not csv_file.exists()


def test_poll_uploads_skips_meta_dirs(
    uploads_dir: Path, rules_path: Path
) -> None:
    """poll_uploads skips _processed and _failed directories."""
    processed_dir = uploads_dir / "_processed"
    processed_dir.mkdir()
    (processed_dir / "old.csv").write_text("a,b\n1,2\n")

    failed_dir = uploads_dir / "_failed"
    failed_dir.mkdir()
    (failed_dir / "bad.csv").write_text("x,y\n")

    def sleep_then_interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    with patch("scripts.triggers.data_trigger.time.sleep", side_effect=sleep_then_interrupt):
        poll_uploads(uploads_dir, interval=1.0, rules_path=rules_path)

    # Meta-dir files should remain untouched
    assert (processed_dir / "old.csv").exists()
    assert (failed_dir / "bad.csv").exists()


def test_poll_uploads_nonexistent_dir(tmp_path: Path) -> None:
    """poll_uploads handles a non-existent uploads directory gracefully."""
    missing_dir = tmp_path / "does_not_exist"

    def sleep_then_interrupt(seconds: float) -> None:
        raise KeyboardInterrupt

    with patch("scripts.triggers.data_trigger.time.sleep", side_effect=sleep_then_interrupt):
        poll_uploads(missing_dir, interval=1.0)
