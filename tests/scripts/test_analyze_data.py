"""Tests for pandas_analyze wrapper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    csv = tmp_path / "data.csv"
    csv.write_text("name,value,category\nA,10,X\nB,20,X\nC,30,Y\nD,40,Y\n")
    return csv


class TestAnalyzeData:
    def test_describe(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(input_path=str(sample_csv), operation="describe")
        assert "value" in result["summary"]

    def test_groupby(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(
            input_path=str(sample_csv),
            operation="groupby",
            group_column="category",
            agg_column="value",
            agg_function="sum",
        )
        data = json.loads(result["summary"])
        assert len(data) == 2

    def test_filter(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        result = run(
            input_path=str(sample_csv),
            operation="filter",
            filter_expr="value > 20",
        )
        data = json.loads(result["summary"])
        assert len(data) == 2

    def test_unknown_operation_raises(self, sample_csv: Path) -> None:
        from scripts.research.analyze_data import run

        with pytest.raises(ValueError, match="Unknown operation"):
            run(input_path=str(sample_csv), operation="pivot_table")
