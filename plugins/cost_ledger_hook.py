"""Hermes plugin — registers cost_ledger lifecycle hooks and query_costs tool.

Fires cost_ledger.pre/post_llm_call for every LLM call made by the Hermes
agent loop (agent reasoning, tool-calling steps).  Pipeline LLM calls are
captured separately via adapter/llm_client.py.

Also registers context_injector as on_session_start so deliverable_id
is propagated into child sessions spawned via delegate_task.
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader on session startup."""

    # --- Lifecycle hooks -------------------------------------------------- #

    from middleware.cost_ledger import post_llm_call, pre_llm_call

    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_llm_call", post_llm_call)
    logger.info("cost_ledger: pre/post_llm_call hooks registered")

    # Cross-session deliverable_id injection (delegate_task child sessions).
    from plugins.context_injector import inject_from_task_context

    def _on_session_start(**kwargs: Any) -> None:
        context = kwargs.get("context")
        inject_from_task_context(context)

    ctx.register_hook("on_session_start", _on_session_start)
    logger.info("cost_ledger: on_session_start hook registered")

    # --- query_costs tool -------------------------------------------------- #

    from middleware.cost_config import calculate_cost
    from tools.query_costs import query_costs

    ctx.register_tool(
        name="query_costs",
        toolset="vizier-core",
        schema={
            "type": "object",
            "properties": {
                "deliverable_id": {
                    "type": "string",
                    "description": "Step-level cost breakdown for a deliverable",
                },
                "client_id": {
                    "type": "string",
                    "description": "Cost rollup for a client (all their deliverables)",
                },
                "distribution": {
                    "type": "boolean",
                    "description": "Token distribution broken down by model",
                },
                "anomaly_history": {
                    "type": "boolean",
                    "description": "Recent anomaly log entries",
                },
                "top_steps": {
                    "type": "integer",
                    "description": "N most expensive pipeline steps (default 10)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows for list queries (default 50, max 1000)",
                },
            },
            "required": [],
        },
        handler=query_costs,
        check_fn=lambda: True,
        description=(
            "Inspect cost ledger: per-deliverable step breakdown, per-client rollup,"
            " model token distribution, anomaly history, top expensive steps"
        ),
    )
    logger.info("cost_ledger: query_costs tool registered")

    # Silence unused import warning — calculate_cost is available for callers.
    _ = calculate_cost
