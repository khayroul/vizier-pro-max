"""Quality tests for tts_generate pipeline improvements."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_verify_output_catches_empty_file() -> None:
    """L2 output verification must reject zero-byte MP3."""
    from pipelines.tts_generate import _verify_output

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"")
        empty_path = f.name

    try:
        result = _verify_output(empty_path, text_length=100)
        assert not result.passed
        assert any("empty" in e.lower() or "size" in e.lower() for e in result.errors)
    finally:
        Path(empty_path).unlink(missing_ok=True)


def test_verify_output_accepts_valid_file() -> None:
    """L2 output verification must pass for non-empty MP3 with valid header."""
    from pipelines.tts_generate import _verify_output

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(b"ID3" + b"\x00" * 100 + b"\xff\xfb\x90\x00" + b"\x00" * 5000)
        valid_path = f.name

    try:
        result = _verify_output(valid_path, text_length=10)
        assert result.passed
    finally:
        Path(valid_path).unlink(missing_ok=True)


def test_verify_output_rejects_missing_file() -> None:
    """L2 must reject non-existent file."""
    from pipelines.tts_generate import _verify_output

    result = _verify_output("/nonexistent/file.mp3", text_length=100)
    assert not result.passed
