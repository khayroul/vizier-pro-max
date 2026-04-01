"""Quality tests for poster_batch pipeline improvements."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


def test_screenshot_accepts_viewport_params() -> None:
    """screenshot_html.run() must accept custom viewport dimensions."""
    from scripts.visual.screenshot_html import run as screenshot_run

    import inspect

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

    with patch(
        "pipelines.poster_batch.screenshot_run", side_effect=tracking_screenshot
    ):
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
