"""Hermes plugin: registers decompose_task and merge_results as agent-level tools."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

DECOMPOSE_TASK_SCHEMA = {
    "type": "object",
    "properties": {
        "task_description": {
            "type": "string",
            "description": "The complex task to decompose into parallel sub-tasks",
        },
    },
    "required": ["task_description"],
}

MERGE_RESULTS_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Child task results from delegate_task to merge",
        },
        "output_format": {
            "type": "string",
            "enum": ["summary", "report", "campaign_package"],
            "description": "How to structure the merged output",
        },
    },
    "required": ["results"],
}


def _handle_decompose_task(args: dict[str, Any], agent: Any) -> str:
    from augments.deerflow.task_decomposer import (
        decompose,  # type: ignore[import-untyped]
    )

    result = decompose(args.get("task_description", ""))
    return json.dumps(result)


def _handle_merge_results(args: dict[str, Any], agent: Any) -> str:
    from augments.deerflow.result_synthesizer import (
        merge,  # type: ignore[import-untyped]
    )

    result = merge(
        results=args.get("results", []),
        output_format=args.get("output_format", "summary"),
    )
    return json.dumps(result)


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    ctx.register_tool(
        name="decompose_task",
        toolset="vizier-core",
        schema=DECOMPOSE_TASK_SCHEMA,
        handler=lambda args, **kw: '{"error": "Must be handled by agent loop"}',
        check_fn=lambda: True,
        description=(
            "Decompose a complex task into parallel sub-tasks for delegate_task"
        ),
    )
    ctx.register_tool(
        name="merge_results",
        toolset="vizier-core",
        schema=MERGE_RESULTS_SCHEMA,
        handler=lambda args, **kw: '{"error": "Must be handled by agent loop"}',
        check_fn=lambda: True,
        description="Merge child task results into a unified deliverable",
    )

    def on_agent_ready(agent: Any, **kwargs: Any) -> None:
        agent._custom_agent_tools["decompose_task"] = _handle_decompose_task
        agent._custom_agent_tools["merge_results"] = _handle_merge_results
        logger.info("decompose_task + merge_results registered as agent-level tools")

    ctx.register_hook("on_agent_ready", on_agent_ready)
