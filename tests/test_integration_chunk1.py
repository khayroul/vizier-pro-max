"""E2E integration test for Chunk 1: toolset switching."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plugins.switch_toolset import _handle_switch_toolset, register


class TestToolsetSwitchE2E:
    """Simulate the full flow: register → on_agent_ready → switch → rebuild."""

    def test_full_switch_flow(self) -> None:
        """Simulate: plugin register → agent init → model calls switch → rebuild."""
        # 1. Plugin registration
        ctx = MagicMock()
        register(ctx)
        on_ready_fn = ctx.register_hook.call_args[0][1]

        # 2. Agent init — on_agent_ready fires
        agent = SimpleNamespace(
            enabled_toolsets=["vizier-core", "code_execution", "delegation", "vizier-content"],
            _custom_agent_tools={},
            _pending_toolsets_rebuild=None,
        )
        on_ready_fn(agent)
        assert "switch_toolset" in agent._custom_agent_tools

        # 3. Model calls switch_toolset
        handler = agent._custom_agent_tools["switch_toolset"]
        result = json.loads(handler({"toolset_name": "vizier-visual"}, agent))
        assert result["status"] == "pending"

        # 4. Main loop would apply the rebuild
        assert agent._pending_toolsets_rebuild == [
            "vizier-core", "code_execution", "delegation", "vizier-visual"
        ]

    def test_fallback_when_plugin_not_injected(self) -> None:
        """If on_agent_ready didn't fire, registry fallback returns error."""
        from plugins.switch_toolset import _fallback_handler

        result = json.loads(_fallback_handler({"toolset_name": "vizier-visual"}))
        assert "error" in result
        assert "plugin initialization failed" in result["error"]

    def test_switch_then_switch_back(self) -> None:
        """Model switches to visual, then back to content."""
        agent = SimpleNamespace(
            enabled_toolsets=["vizier-core", "vizier-content"],
            _pending_toolsets_rebuild=None,
        )
        # Switch to visual
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, agent)
        assert "vizier-visual" in agent._pending_toolsets_rebuild

        # Simulate main loop applying the rebuild
        agent.enabled_toolsets = agent._pending_toolsets_rebuild
        agent._pending_toolsets_rebuild = None

        # Switch back to content
        _handle_switch_toolset({"toolset_name": "vizier-content"}, agent)
        assert "vizier-content" in agent._pending_toolsets_rebuild
        assert "vizier-visual" not in agent._pending_toolsets_rebuild
