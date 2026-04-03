"""Tests for switch_toolset Hermes plugin."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.modules.setdefault(
    "structlog",
    SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
)

from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode
from plugins.switch_toolset import (
    VIZIER_WORKFLOW_TOOLSETS,
    _handle_switch_toolset,
)


@pytest.fixture(autouse=True)
def _clear_mode_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIZIER_TELEGRAM_FRONT_DOOR", raising=False)
    monkeypatch.delenv("MESSAGING_CWD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    clear_telegram_mode()


@pytest.fixture()
def mock_agent() -> SimpleNamespace:
    """Fake agent with enabled_toolsets and _pending_toolsets_rebuild."""
    agent = SimpleNamespace(
        enabled_toolsets=["vizier-core", "code_execution", "delegation", "vizier-content"],
        _pending_toolsets_rebuild=None,
    )
    return agent


class TestHandleSwitchToolset:
    def test_switch_to_valid_toolset(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent))
        assert result["status"] == "pending"
        assert result["switching_to"] == "vizier-visual"
        assert mock_agent._pending_toolsets_rebuild is not None
        assert "vizier-visual" in mock_agent._pending_toolsets_rebuild
        assert "vizier-core" in mock_agent._pending_toolsets_rebuild
        assert "code_execution" in mock_agent._pending_toolsets_rebuild
        assert "delegation" in mock_agent._pending_toolsets_rebuild
        assert "vizier-content" not in mock_agent._pending_toolsets_rebuild

    def test_switch_to_unknown_toolset(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-unknown"}, mock_agent))
        assert "error" in result
        assert mock_agent._pending_toolsets_rebuild is None

    def test_switch_to_fallback_loads_all(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-fallback"}, mock_agent))
        assert result["switching_to"] == "vizier-fallback"
        assert "vizier-fallback" in mock_agent._pending_toolsets_rebuild

    def test_switch_preserves_non_vizier_toolsets(self, mock_agent: SimpleNamespace) -> None:
        mock_agent.enabled_toolsets = ["vizier-core", "hermes-cli", "vizier-document"]
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        assert "hermes-cli" in mock_agent._pending_toolsets_rebuild
        assert "vizier-core" in mock_agent._pending_toolsets_rebuild

    def test_two_switches_last_wins(self, mock_agent: SimpleNamespace) -> None:
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        _handle_switch_toolset({"toolset_name": "vizier-audio"}, mock_agent)
        assert "vizier-audio" in mock_agent._pending_toolsets_rebuild
        assert "vizier-visual" not in mock_agent._pending_toolsets_rebuild

    def test_switch_to_already_active_is_noop(self, mock_agent: SimpleNamespace) -> None:
        result = json.loads(_handle_switch_toolset({"toolset_name": "vizier-content"}, mock_agent))
        assert result["status"] == "pending"
        assert "vizier-content" in mock_agent._pending_toolsets_rebuild

    def test_switch_does_not_mutate_enabled_toolsets(self, mock_agent: SimpleNamespace) -> None:
        """Switch only sets _pending_toolsets_rebuild, never touches enabled_toolsets directly."""
        original = list(mock_agent.enabled_toolsets)
        _handle_switch_toolset({"toolset_name": "vizier-visual"}, mock_agent)
        assert mock_agent.enabled_toolsets == original
        assert mock_agent._pending_toolsets_rebuild is not None


class TestRegister:
    def test_register_calls_register_tool_and_hook(self) -> None:
        from plugins.switch_toolset import register
        ctx = MagicMock()
        register(ctx)
        ctx.register_tool.assert_called_once()
        ctx.register_hook.assert_called_once()

    def test_register_hides_tool_in_telegram_assistant_mode(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from plugins.switch_toolset import register

        monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

        ctx = MagicMock()
        register(ctx)

        check_fn = ctx.register_tool.call_args.kwargs["check_fn"]
        assert callable(check_fn)
        assert check_fn() is False

        set_telegram_mode(platform="telegram", mode="vizier_work")
        assert check_fn() is True

        set_telegram_mode(platform="telegram", mode="operator")
        assert check_fn() is True

    def test_on_agent_ready_injects_handler(self) -> None:
        from plugins.switch_toolset import register
        ctx = MagicMock()
        register(ctx)
        on_ready_fn = ctx.register_hook.call_args[0][1]
        agent = SimpleNamespace(_custom_agent_tools={})
        on_ready_fn(agent)
        assert "switch_toolset" in agent._custom_agent_tools
