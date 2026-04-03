"""Hermes plugin: registers switch_toolset as an agent-level tool.

Dual registration: schema goes to registry (model sees it), execution
is intercepted by _custom_agent_tools in _invoke_tool. The registry
handler is a fallback if on_agent_ready failed to inject the real handler.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

from config.toolsets import VIZIER_WORKFLOW_TOOLSETS
from plugins.telegram_tool_policy import telegram_tool_allows

logger = structlog.get_logger(__name__)

SWITCH_TOOLSET_SCHEMA = {
    "type": "object",
    "properties": {
        "toolset_name": {
            "type": "string",
            "description": "Target workflow toolset to switch to",
            "enum": sorted(VIZIER_WORKFLOW_TOOLSETS),
        },
    },
    "required": ["toolset_name"],
}


def _handle_switch_toolset(args: dict[str, Any], agent: Any) -> str:
    """Set the pending rebuild — main loop applies it between turns."""
    new_ts = args.get("toolset_name", "")
    if new_ts not in VIZIER_WORKFLOW_TOOLSETS:
        return json.dumps({"error": f"Unknown toolset: {new_ts}"})

    base = [t for t in agent.enabled_toolsets if t not in VIZIER_WORKFLOW_TOOLSETS]
    agent._pending_toolsets_rebuild = base + [new_ts]

    return json.dumps({
        "status": "pending",
        "switching_to": new_ts,
        "keeping": base,
        "message": f"Switching to '{new_ts}' after this turn completes.",
    })


def _fallback_handler(args: dict[str, Any], **kwargs: Any) -> str:
    logger.warning(
        "switch_toolset: agent-level handler not injected"
        " — on_agent_ready may have failed"
    )
    return json.dumps(
        {"error": "switch_toolset not available — plugin initialization failed"}
    )


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    ctx.register_tool(
        name="switch_toolset",
        toolset="vizier-core",
        schema=SWITCH_TOOLSET_SCHEMA,
        handler=_fallback_handler,
        check_fn=lambda: telegram_tool_allows("switch_toolset"),
        description="Switch the active workflow toolset mid-session",
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["switch_toolset"] = _handle_switch_toolset
        logger.info("switch_toolset registered as agent-level tool")

    ctx.register_hook("on_agent_ready", on_agent_ready)
