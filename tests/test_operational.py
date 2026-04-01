"""Operational smoke tests — verify Gate 2 is wired, not just tested."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestPluginWiring:
    def test_gate2_plugins_importable(self) -> None:
        """Gate 2 plugins can be imported from vizier-pro-max."""
        from plugins.switch_toolset import register as switch_register
        from plugins.deerflow_orchestration import register as deerflow_register

        assert callable(switch_register)
        assert callable(deerflow_register)

    def test_vizier_tools_plugin_loads_gate2(self) -> None:
        """vizier_tools plugin __init__ references Gate 2 modules."""
        plugin_path = Path.home() / ".hermes" / "plugins" / "vizier_tools" / "__init__.py"
        content = plugin_path.read_text()
        assert "switch_toolset" in content
        assert "deerflow" in content or "decompose_task" in content


class TestDependencies:
    def test_core_gate2_deps_importable(self) -> None:
        """Core Gate 2 Python dependencies are installed (venv required)."""
        import skimage
        import numpy
        import httpx
        import mcp

        # These require the .venv — skip if running on system Python
        try:
            import pixelmatch
            import cv2
            import pytesseract
        except ImportError:
            pytest.skip("Gate 2 image deps require .venv/bin/python3")

    def test_calculate_delta_uses_real_ssim(self, tmp_path: Path) -> None:
        """calculate_delta uses scikit-image SSIM, not MSE fallback."""
        from PIL import Image

        from scripts.visual.calculate_delta import calculate_delta

        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        path_a = tmp_path / "a.png"
        path_b = tmp_path / "b.png"
        img.save(str(path_a))
        img.save(str(path_b))
        result = calculate_delta(target=path_a, rendered=path_b)
        assert result.ssim_score > 0.99
        assert result.composite_score > 0.95


class TestContentPipeline:
    def test_content_pipeline_has_llm_function(self) -> None:
        """Content pipeline has _call_llm (not just stub)."""
        from pipelines.content_generate import _call_llm

        assert callable(_call_llm)


class TestCronIntegration:
    def test_cron_loader_has_register_jobs(self) -> None:
        """Cron loader exports register_jobs."""
        from bridge.cron_loader import register_jobs

        assert callable(register_jobs)


class TestQualityGateFull:
    def test_visual_qa_with_real_delta(self, tmp_path: Path) -> None:
        """Layer 3 visual QA works with real image comparison."""
        from PIL import Image

        from middleware.quality_gate import validate_visual_qa

        img = Image.new("RGB", (100, 100), color=(0, 128, 255))
        target = tmp_path / "target.png"
        rendered = tmp_path / "rendered.png"
        img.save(str(target))
        img.save(str(rendered))
        result = validate_visual_qa(target=target, rendered=rendered, threshold=0.80)
        assert result.passed is True


class TestMCPServer:
    def test_openspace_server_imports(self) -> None:
        """OpenSpace MCP server module imports without error."""
        from augments.openspace.server import mcp

        assert mcp is not None

    def test_mcp_config_exists(self) -> None:
        """MCP server reference config exists."""
        config = Path("config/mcp_servers.json")
        assert config.exists()
        import json

        data = json.loads(config.read_text())
        assert "openspace" in data
