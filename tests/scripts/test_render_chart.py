"""Tests for matplotlib_chart wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestRenderChart:
    def test_bar_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "chart.png"
        result = run(
            chart_type="bar",
            data={"labels": ["A", "B", "C"], "values": [10, 20, 30]},
            output_path=str(output),
            title="Test Chart",
        )
        assert Path(result["file_path"]).exists()
        assert output.stat().st_size > 0

    def test_line_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "line.png"
        result = run(
            chart_type="line",
            data={"x": [1, 2, 3], "y": [10, 20, 15]},
            output_path=str(output),
        )
        assert Path(result["file_path"]).exists()

    def test_pie_chart(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        output = tmp_path / "pie.png"
        result = run(
            chart_type="pie",
            data={"labels": ["A", "B"], "values": [60, 40]},
            output_path=str(output),
        )
        assert Path(result["file_path"]).exists()

    def test_unknown_chart_type_raises(self, tmp_path: Path) -> None:
        from scripts.research.render_chart import run

        with pytest.raises(ValueError, match="Unknown chart_type"):
            run(
                chart_type="3d_scatter",
                data={"x": [1], "y": [1]},
                output_path=str(tmp_path / "out.png"),
            )
