"""Tests for quality gate middleware layers 1-2."""
from __future__ import annotations

import pytest

from middleware.quality_gate import validate_input, validate_output, ValidationResult


class TestValidateInput:
    def test_passes_valid_input(self) -> None:
        schema = {"brief": {"type": "string", "required": True}}
        result = validate_input({"brief": "Write an ad for DMB"}, schema)
        assert result.passed is True

    def test_fails_missing_required_field(self) -> None:
        schema = {"brief": {"type": "string", "required": True}}
        result = validate_input({}, schema)
        assert result.passed is False
        assert "brief" in result.errors[0]

    def test_fails_wrong_type(self) -> None:
        schema = {"count": {"type": "integer", "required": True}}
        result = validate_input({"count": "not_a_number"}, schema)
        assert result.passed is False


class TestValidateOutput:
    def test_passes_valid_output(self) -> None:
        schema = {"content": {"type": "string"}}
        result = validate_output({"content": "Hello world"}, schema)
        assert result.passed is True

    def test_fails_empty_required_output(self) -> None:
        schema = {"content": {"type": "string", "required": True}}
        result = validate_output({}, schema)
        assert result.passed is False

    def test_passes_empty_schema(self) -> None:
        result = validate_output({"anything": "goes"}, {})
        assert result.passed is True
