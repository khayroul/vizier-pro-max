"""E2E integration test for Chunk 3: parallel sessions + channels."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from augments.deerflow.result_synthesizer import merge
from augments.deerflow.shared_memory import SharedMemory
from augments.deerflow.task_decomposer import decompose


class TestChunk3Integration:
    def test_decompose_then_merge(self) -> None:
        """Full flow: decompose → (simulated delegate) → merge."""
        # Decompose
        decomposed = decompose(
            "Research the market, write social copy, design a poster for DMB"
        )
        assert len(decomposed["tasks"]) >= 2

        # Simulate delegate_task results
        child_results = [
            "Research: Malaysian F&B market growing 15% YoY."
            " output/research/dmb_brief.md",
            "Content: 3 social posts created. output/content/dmb_post1.txt",
            "Visual: Poster saved to output/posters/dmb_campaign.png",
        ]

        # Merge
        merged = merge(results=child_results)
        assert merged["result_count"] == 3
        assert len(merged["artifacts"]) >= 3

    def test_shared_memory_across_agents(self, tmp_path: Path) -> None:
        """Children write, parent reads."""
        mem = SharedMemory(session_id="integration-test", base_dir=tmp_path)

        # Children write
        mem.write("research-child", {"finding": "Market is $2B"})
        mem.write("content-child", {"output": "3 posts created"})

        # Parent reads
        data = mem.read_all()
        assert len(data) == 2

        # Cleanup
        mem.cleanup()
        assert not mem.file_path.exists()

    def test_cron_configs_loadable(self) -> None:
        """All cron configs in config/cron/ are valid."""
        from bridge.cron_loader import load_cron_configs

        configs = load_cron_configs(Path("config/cron"))
        assert len(configs) == 3
        ids = {c["id"] for c in configs}
        assert ids == {"content_calendar", "quality_review", "health_check"}

    def test_deerflow_plugin_registers_tools(self) -> None:
        """deerflow_orchestration plugin registers both tools."""
        from plugins.deerflow_orchestration import register

        ctx = MagicMock()
        register(ctx)
        assert ctx.register_tool.call_count == 2
        tool_names = {call.kwargs["name"] for call in ctx.register_tool.call_args_list}
        assert tool_names == {"decompose_task", "merge_results"}
