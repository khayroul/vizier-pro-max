"""Tests for the repo-local Hermes Vizier project plugin."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from plugins.telegram_mode_state import clear_telegram_mode, set_telegram_mode
from plugins.telegram_tool_policy import (
    PROJECT_LOCAL_TELEGRAM_TOOLS,
    TOOLS_BY_CLASSIFICATION,
    ASSISTANT_SAFE,
    SHARED,
    WORK_ONLY,
    OPERATOR_ONLY,
)

PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / ".hermes"
    / "plugins"
    / "vizier_tools"
    / "__init__.py"
)


def _install_structlog_stub() -> None:
    sys.modules.setdefault(
        "structlog",
        SimpleNamespace(get_logger=lambda *args, **kwargs: MagicMock()),
    )


@pytest.fixture(autouse=True)
def _clear_mode_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIZIER_TELEGRAM_FRONT_DOOR", raising=False)
    monkeypatch.delenv("MESSAGING_CWD", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    clear_telegram_mode()


def _load_plugin_module():
    _install_structlog_stub()
    spec = importlib.util.spec_from_file_location(
        "test_vizier_tools_project_plugin",
        PLUGIN_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_register_exposes_expected_tools_and_hooks() -> None:
    module = _load_plugin_module()
    ctx = MagicMock()

    module.register(ctx)

    tool_names = {call.kwargs["name"] for call in ctx.register_tool.call_args_list}
    assert tool_names == PROJECT_LOCAL_TELEGRAM_TOOLS

    hook_names = [call.args[0] for call in ctx.register_hook.call_args_list]
    assert "pre_tool_resolution" in hook_names
    assert "pre_llm_call" in hook_names
    assert "post_llm_call" in hook_names
    assert "on_session_start" in hook_names
    assert "on_agent_ready" in hook_names


def test_register_adds_vizier_turn_context_hook() -> None:
    module = _load_plugin_module()
    ctx = MagicMock()

    module.register(ctx)

    contexts: list[str] = []
    for call in ctx.register_hook.call_args_list:
        if call.args[0] != "pre_llm_call":
            continue
        try:
            result = call.args[1](
                session_id="session-1",
                user_message="make me a marketing plan",
                conversation_history=[],
                is_first_turn=True,
                model="gpt-5.4-mini",
                platform="telegram",
            )
        except TypeError:
            continue
        if isinstance(result, str):
            contexts.append(result)

    assert any("marketing_plan_generate" in context for context in contexts)
    assert any("MEDIA:/absolute/path" in context for context in contexts)
    assert any("raw brief or explicit headline/body copy" in context for context in contexts)
    assert any("Telegram front door mode routing is active." in context for context in contexts)


def test_registered_tool_surface_matches_telegram_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MESSAGING_CWD", "/Users/Executor/vizier-pro-max")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")

    module = _load_plugin_module()
    ctx = MagicMock()
    module.register(ctx)

    tool_defs = {
        call.kwargs["name"]: call.kwargs for call in ctx.register_tool.call_args_list
    }

    def visible_tools() -> set[str]:
        visible: set[str] = set()
        for name, tool_def in tool_defs.items():
            check_fn = tool_def["check_fn"]
            assert callable(check_fn)
            if check_fn():
                visible.add(name)
        return visible

    assistant_tools = visible_tools()
    assert assistant_tools == set(TOOLS_BY_CLASSIFICATION[ASSISTANT_SAFE])

    set_telegram_mode(platform="telegram", mode="vizier_work")
    assert visible_tools() == (
        set(TOOLS_BY_CLASSIFICATION[ASSISTANT_SAFE])
        | set(TOOLS_BY_CLASSIFICATION[WORK_ONLY])
        | set(TOOLS_BY_CLASSIFICATION[SHARED])
    )

    set_telegram_mode(platform="telegram", mode="operator")
    assert visible_tools() == (
        set(TOOLS_BY_CLASSIFICATION[ASSISTANT_SAFE])
        | set(TOOLS_BY_CLASSIFICATION[OPERATOR_ONLY])
        | set(TOOLS_BY_CLASSIFICATION[SHARED])
    )
