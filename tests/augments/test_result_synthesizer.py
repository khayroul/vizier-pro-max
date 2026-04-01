"""Tests for DeerFlow result_synthesizer."""
from __future__ import annotations

import pytest

from augments.deerflow.result_synthesizer import merge


class TestResultSynthesizer:
    def test_merge_single_result(self) -> None:
        result = merge(results=["Research complete: market size is $2B"])
        assert "market size" in result["merged"]

    def test_merge_multiple_results(self) -> None:
        result = merge(results=[
            "Research: market growing 15% YoY",
            "Copy: 3 social media posts created at output/posts/",
            "Visual: poster saved to output/posters/dmb.png",
        ])
        assert "Research" in result["merged"]
        assert "Copy" in result["merged"]
        assert "Visual" in result["merged"]

    def test_dedup_file_paths(self) -> None:
        result = merge(results=[
            "Output: output/file1.pdf, output/file2.pdf",
            "Output: output/file1.pdf, output/file3.pdf",
        ])
        # file1.pdf should appear only once
        assert result["artifacts"].count("output/file1.pdf") == 1

    def test_empty_results(self) -> None:
        result = merge(results=[])
        assert result["merged"] == ""
        assert result["artifacts"] == []

    def test_report_format(self) -> None:
        result = merge(
            results=["Finding A", "Finding B"],
            output_format="report",
        )
        assert "report" in result["format"]
