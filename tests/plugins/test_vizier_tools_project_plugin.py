"""Tests for the repo-local Hermes Vizier project plugin."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / ".hermes"
    / "plugins"
    / "vizier_tools"
    / "__init__.py"
)


def _load_plugin_module():
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
    assert {"run_pipeline", "query_logs", "query_costs"} <= tool_names
    assert {"search_palettes", "search_fonts", "generate_poster"} <= tool_names
    assert {"switch_toolset", "decompose_task", "merge_results"} <= tool_names

    hook_names = [call.args[0] for call in ctx.register_hook.call_args_list]
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
