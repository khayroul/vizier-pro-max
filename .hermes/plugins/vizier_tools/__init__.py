"""Project-local Hermes plugin that exposes Vizier tools inside Hermes."""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

logger = logging.getLogger(__name__)

VIZIER_ROOT = Path(__file__).resolve().parents[3]

RUN_PIPELINE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "description": "Set to 'list' to inspect available pipelines",
            "enum": ["list"],
        },
        "name": {
            "type": "string",
            "description": "Pipeline name to execute",
        },
        "args": {
            "type": "object",
            "description": "Arguments to pass to the pipeline",
        },
    },
    "required": [],
}

QUERY_LOGS_SCHEMA = {
    "type": "object",
    "properties": {
        "last_n": {
            "type": "integer",
            "description": "Return the last N log entries (default 10)",
        },
        "task_id": {
            "type": "string",
            "description": "Filter by a specific task ID",
        },
        "summary": {
            "type": "boolean",
            "description": "Return token totals instead of raw entries",
        },
    },
    "required": [],
}

QUERY_COSTS_SCHEMA = {
    "type": "object",
    "properties": {
        "deliverable_id": {
            "type": "string",
            "description": "Step-level cost breakdown for a deliverable",
        },
        "client_id": {
            "type": "string",
            "description": "Cost rollup for a client",
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
            "description": "Max rows for anomaly queries (default 50, max 1000)",
        },
    },
    "required": [],
}


def _ensure_repo_on_path() -> None:
    repo_root = str(VIZIER_ROOT)
    if repo_root in sys.path:
        return
    sys.path.insert(0, repo_root)


def _import_repo_module(module_name: str) -> ModuleType:
    _ensure_repo_on_path()
    return importlib.import_module(module_name)


def _load_repo_tool_module(alias: str, relative_path: str) -> ModuleType:
    _ensure_repo_on_path()
    module_path = VIZIER_ROOT / relative_path
    if not module_path.is_file():
        raise FileNotFoundError(f"Vizier module not found: {module_path}")

    cached = sys.modules.get(alias)
    if cached is not None and getattr(cached, "__file__", "") == str(module_path):
        return cached

    spec = importlib.util.spec_from_file_location(alias, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _safe_register(label: str, action: Callable[[], None]) -> None:
    try:
        action()
        logger.info("Vizier plugin registered %s", label)
    except Exception as exc:  # pragma: no cover - defensive log path
        logger.warning("Vizier plugin failed to register %s: %s", label, exc)


def _register_prompt_logging(ctx: Any) -> None:
    prompt_logger = _import_repo_module("plugins.prompt_logger")
    ctx.register_hook("pre_llm_call", prompt_logger.pre_llm_call)
    ctx.register_hook("post_llm_call", prompt_logger.post_llm_call)


def _register_cost_observability(ctx: Any) -> None:
    from middleware.cost_ledger import post_llm_call, pre_llm_call
    from plugins.context_injector import inject_from_task_context

    query_costs_mod = _load_repo_tool_module(
        "_vizier_query_costs_tool",
        "tools/query_costs.py",
    )

    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_llm_call", post_llm_call)

    def _on_session_start(**kwargs: Any) -> None:
        inject_from_task_context(kwargs.get("context"))

    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_tool(
        name="query_costs",
        toolset="vizier-core",
        schema=QUERY_COSTS_SCHEMA,
        handler=query_costs_mod.query_costs,
        check_fn=lambda: True,
        description=(
            "Inspect Vizier cost ledger data for deliverables, clients, models, "
            "and anomaly history."
        ),
    )


def _register_run_pipeline(ctx: Any) -> None:
    run_pipeline_mod = _load_repo_tool_module(
        "_vizier_run_pipeline_tool",
        "tools/run_pipeline.py",
    )
    ctx.register_tool(
        name="run_pipeline",
        toolset="vizier-core",
        schema=RUN_PIPELINE_SCHEMA,
        handler=run_pipeline_mod.run_pipeline,
        check_fn=lambda: True,
        description="Execute Vizier collapsed pipelines or list the available ones.",
    )


def _register_query_logs(ctx: Any) -> None:
    query_logs_mod = _load_repo_tool_module(
        "_vizier_query_logs_tool",
        "tools/query_logs.py",
    )
    ctx.register_tool(
        name="query_logs",
        toolset="vizier-core",
        schema=QUERY_LOGS_SCHEMA,
        handler=query_logs_mod.query_logs,
        check_fn=lambda: True,
        description="Inspect Vizier prompt logs and token traces.",
    )


def _register_repo_plugin(ctx: Any, module_name: str) -> None:
    plugin_mod = _import_repo_module(module_name)
    register = getattr(plugin_mod, "register", None)
    if register is None:
        raise AttributeError(f"{module_name} has no register(ctx)")
    register(ctx)


def _vizier_turn_context(**_: Any) -> str:
    return (
        "Vizier project tools are loaded in this repo.\n"
        "- Use run_pipeline for deterministic production workflows. Call "
        "run_pipeline with action='list' if you need to inspect names.\n"
        "- Prefer marketing_plan_generate for plain-language marketing briefs "
        "that should produce strategy documents and creative assets.\n"
        "- Prefer structured_nonfiction_generate for proposals, reports, content "
        "calendars, technical documents, and other nonfiction packages.\n"
        "- For posters and social creatives, call search_palettes, then "
        "search_fonts, then generate_poster. generate_poster accepts either "
        "a raw brief or explicit headline/body copy and will normalize a "
        "freeform brief before rendering.\n"
        "- When a tool or pipeline returns client-facing files, include "
        "MEDIA:/absolute/path for the PDFs or images you want Hermes to send "
        "back as attachments.\n"
        "- Do not send internal manifest/json/md support files to clients "
        "unless the user explicitly asks for them."
    )


def register(ctx: Any) -> None:
    """Called by Hermes plugin loader."""
    _ensure_repo_on_path()

    from adapter.env_loader import ensure_env

    ensure_env()

    _safe_register("prompt logging hooks", lambda: _register_prompt_logging(ctx))
    _safe_register(
        "cost observability hooks",
        lambda: _register_cost_observability(ctx),
    )
    _safe_register("run_pipeline tool", lambda: _register_run_pipeline(ctx))
    _safe_register("query_logs tool", lambda: _register_query_logs(ctx))
    _safe_register(
        "design intelligence tools",
        lambda: _register_repo_plugin(ctx, "plugins.design_intelligence"),
    )
    _safe_register(
        "poster generation tool",
        lambda: _register_repo_plugin(ctx, "plugins.poster_tool"),
    )
    _safe_register(
        "switch_toolset tool",
        lambda: _register_repo_plugin(ctx, "plugins.switch_toolset"),
    )
    _safe_register(
        "telegram mode router hook",
        lambda: _register_repo_plugin(ctx, "plugins.telegram_mode_router"),
    )
    _safe_register(
        "deerflow orchestration tools",
        lambda: _register_repo_plugin(ctx, "plugins.deerflow_orchestration"),
    )
    ctx.register_hook("pre_llm_call", _vizier_turn_context)
    logger.info("Vizier project plugin loaded from %s", VIZIER_ROOT)
