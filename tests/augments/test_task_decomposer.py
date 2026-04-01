"""Tests for DeerFlow task_decomposer."""
from __future__ import annotations

from augments.deerflow.task_decomposer import decompose


class TestTaskDecomposer:
    def test_single_research_task(self) -> None:
        result = decompose("Analyze market trends for Malaysian F&B industry")
        tasks = result["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["toolsets"] == ["vizier-research"]

    def test_multi_workflow_decomposition(self) -> None:
        result = decompose(
            "Create a campaign for DMB: research the market, "
            "write social copy, design a poster"
        )
        tasks = result["tasks"]
        assert len(tasks) == 3
        toolsets_used = {t["toolsets"][0] for t in tasks}
        assert "vizier-research" in toolsets_used
        assert "vizier-content" in toolsets_used
        assert "vizier-visual" in toolsets_used

    def test_caps_at_three_tasks(self) -> None:
        result = decompose(
            "Research, write copy, design poster, create audio, build PDF report"
        )
        assert len(result["tasks"]) <= 3

    def test_fallback_to_single_task(self) -> None:
        result = decompose("Do something vague and unrecognizable")
        tasks = result["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["toolsets"] == ["vizier-fallback"]

    def test_output_format_matches_delegate_task(self) -> None:
        """Output is directly passable to delegate_task(tasks=...)."""
        result = decompose("Analyze data and generate a chart")
        for task in result["tasks"]:
            assert "goal" in task
            assert "toolsets" in task
            assert isinstance(task["toolsets"], list)

    def test_context_passed_through(self) -> None:
        result = decompose(
            "Design a poster for client DMB",
        )
        assert any(
            "DMB" in t.get("context", "") or "DMB" in t["goal"]
            for t in result["tasks"]
        )
