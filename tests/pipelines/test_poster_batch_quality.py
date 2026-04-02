"""Quality tests for poster_batch pipeline improvements."""
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_screenshot_accepts_viewport_params() -> None:
    """screenshot_html.run() must accept custom viewport dimensions."""
    from scripts.visual.screenshot_html import run as screenshot_run

    sig = inspect.signature(screenshot_run)
    assert "viewport_width" in sig.parameters
    assert "viewport_height" in sig.parameters


def test_poster_uses_800x600_viewport() -> None:
    """poster_batch must render with 800x600 viewport."""
    calls: list[dict] = []

    def tracking_screenshot(**kwargs: object) -> dict[str, str]:
        calls.append(dict(kwargs))
        out = str(kwargs.get("output_path", "/tmp/fake.png"))
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        return {"file_path": out}

    with (
        patch("pipelines.poster_batch.screenshot_run", side_effect=tracking_screenshot),
        patch("pipelines.poster_batch._generate_ai_background", return_value=None),
        patch("pipelines.poster_batch._generate_image_prompt", return_value="prompt"),
        patch("pipelines.poster_batch.start_deliverable", return_value="did"),
        patch("pipelines.poster_batch.clear_context"),
        patch("pipelines.poster_batch.record_quality"),
        patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
        patch("pipelines.poster_batch.score_poster_batch") as mock_score,
    ):
        fake_score = MagicMock()
        fake_score.score = 8.0
        fake_score.passed = True
        mock_score.return_value = fake_score

        from pipelines.poster_batch import run

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpl = Path(tmpdir) / "template.html"
            tmpl.write_text("<html><body>{{ headline }}</body></html>")
            data = Path(tmpdir) / "data.csv"
            data.write_text("headline\nTest\n")

            run(
                template_path=str(tmpl),
                data_path=str(data),
                output_dir=str(Path(tmpdir) / "out"),
            )

    assert len(calls) >= 1
    assert calls[0].get("viewport_width") == 800
    assert calls[0].get("viewport_height") == 600


def test_run_with_gates_integration() -> None:
    """run() must delegate to run_with_gates with correct schemas."""
    from pipelines.poster_batch import (
        _INPUT_SCHEMA,
        _OUTPUT_SCHEMA,
        _PIPELINE_NAME,
        _pipeline_fn,
        run,
    )

    captured: list[dict] = []

    def fake_run_with_gates(
        *,
        pipeline_fn,
        inputs,
        input_schema,
        output_schema,
        pipeline_name,
    ) -> dict:
        captured.append(
            {
                "pipeline_fn": pipeline_fn,
                "inputs": inputs,
                "input_schema": input_schema,
                "output_schema": output_schema,
                "pipeline_name": pipeline_name,
            }
        )
        return {"posters": [], "count": 0, "status": "completed", "quality_report": {}}

    with patch("pipelines.poster_batch.run_with_gates", side_effect=fake_run_with_gates):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpl = Path(tmpdir) / "template.html"
            tmpl.write_text("<p>test</p>")
            data = Path(tmpdir) / "data.csv"
            data.write_text("headline\nTest\n")

            run(
                template_path=str(tmpl),
                data_path=str(data),
            )

    assert len(captured) == 1
    call = captured[0]
    assert call["pipeline_fn"] is _pipeline_fn
    assert call["input_schema"] is _INPUT_SCHEMA
    assert call["output_schema"] is _OUTPUT_SCHEMA
    assert call["pipeline_name"] == _PIPELINE_NAME


def test_input_schema_required_fields() -> None:
    """_INPUT_SCHEMA must mark template_path and data_path as required."""
    from pipelines.poster_batch import _INPUT_SCHEMA

    assert _INPUT_SCHEMA["template_path"]["required"] is True
    assert _INPUT_SCHEMA["data_path"]["required"] is True
    assert _INPUT_SCHEMA.get("output_dir", {}).get("required", False) is False


def test_output_schema_required_fields() -> None:
    """_OUTPUT_SCHEMA must require posters, count, and status."""
    from pipelines.poster_batch import _OUTPUT_SCHEMA

    assert _OUTPUT_SCHEMA["posters"]["required"] is True
    assert _OUTPUT_SCHEMA["count"]["required"] is True
    assert _OUTPUT_SCHEMA["status"]["required"] is True


def test_start_deliverable_called_in_pipeline() -> None:
    """_pipeline_fn must call start_deliverable at the start of execution."""
    import pipelines.poster_batch as pb

    assert hasattr(pb, "start_deliverable"), "start_deliverable must be imported"
    src = inspect.getsource(pb._pipeline_fn)
    assert "start_deliverable" in src


def test_clear_context_called_in_finally() -> None:
    """_pipeline_fn must call clear_context in finally block."""
    import pipelines.poster_batch as pb

    src = inspect.getsource(pb._pipeline_fn)
    assert "clear_context" in src
    assert "finally" in src


def test_score_poster_batch_called_per_poster() -> None:
    """score_poster_batch must be called for each rendered poster."""
    score_calls: list[str] = []

    def tracking_score(path: str) -> MagicMock:
        score_calls.append(str(path))
        result = MagicMock()
        result.score = 8.0
        result.passed = True
        return result

    with (
        patch("pipelines.poster_batch.screenshot_run") as mock_ss,
        patch("pipelines.poster_batch._generate_ai_background", return_value=None),
        patch("pipelines.poster_batch._generate_image_prompt", return_value="prompt"),
        patch("pipelines.poster_batch.start_deliverable", return_value="did"),
        patch("pipelines.poster_batch.clear_context"),
        patch("pipelines.poster_batch.record_quality"),
        patch("pipelines.poster_batch.check_anomalies", return_value={"is_anomaly": False, "reasons": []}),
        patch("pipelines.poster_batch.score_poster_batch", side_effect=tracking_score),
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            poster_paths = [
                str(Path(tmpdir) / f"poster_{i:04d}.png") for i in range(2)
            ]
            mock_ss.side_effect = [{"file_path": p} for p in poster_paths]

            tmpl = Path(tmpdir) / "template.html"
            tmpl.write_text("<p>{{ headline }}</p>")
            data = Path(tmpdir) / "data.csv"
            data.write_text("headline\nA\nB\n")

            from pipelines.poster_batch import _pipeline_fn

            _pipeline_fn(
                {
                    "template_path": str(tmpl),
                    "data_path": str(data),
                    "output_dir": tmpdir,
                }
            )

    # Called once per poster loop + once for final record_quality
    assert len(score_calls) >= 2
