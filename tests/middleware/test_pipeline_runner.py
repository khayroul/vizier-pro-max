"""Tests for pipeline runner quality gate wrapper."""
from __future__ import annotations

from typing import Any

import pytest

from middleware.pipeline_runner import run_with_gates


def _ok_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"content": "result", "status": "completed"}


def _failing_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
    msg = "pipeline exploded"
    raise RuntimeError(msg)


_INPUT_SCHEMA = {"brief": {"type": "string", "required": True}}
_OUTPUT_SCHEMA = {"content": {"type": "string", "required": True}}


def test_run_with_gates_happy_path() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={"brief": "test brief"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert result["content"] == "result"
    assert "quality_report" in result
    report = result["quality_report"]
    assert report["L1"]["passed"] is True
    assert report["L2"]["passed"] is True


def test_run_with_gates_input_validation_fails() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={},  # missing required "brief"
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert "error" in result
    assert result["quality_report"]["L1"]["passed"] is False


def test_run_with_gates_output_validation_fails() -> None:
    def bad_output(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"wrong_key": "value"}

    result = run_with_gates(
        pipeline_fn=bad_output,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert result["quality_report"]["L2"]["passed"] is False


def test_run_with_gates_pipeline_exception() -> None:
    result = run_with_gates(
        pipeline_fn=_failing_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
    )
    assert "error" in result
    assert "pipeline exploded" in result["error"]


def test_run_with_gates_content_quality_opt_in() -> None:
    def content_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
        return {"content": "Professional English content for LinkedIn post."}

    result = run_with_gates(
        pipeline_fn=content_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema={"content": {"type": "string", "required": True}},
        quality_config={"L4": {"expected_languages": ["en", "ms"]}},
    )
    assert "L4" in result["quality_report"]


def test_run_with_gates_feedback_logged() -> None:
    result = run_with_gates(
        pipeline_fn=_ok_pipeline,
        inputs={"brief": "test"},
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name="test_pipeline",
    )
    assert result["quality_report"]["L6"]["passed"] is True
