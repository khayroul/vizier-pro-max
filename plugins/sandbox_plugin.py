"""Hermes plugin: pre_tool_call guard + post_tool_call audit on execute_code.

Only applies to execute_code tool (skip other tools).
Hooks are synchronous -- no async/await.
"""
from __future__ import annotations

import time
from pathlib import Path

import structlog

from augments.sandbox.audit import record
from augments.sandbox.guard import check

logger = structlog.get_logger(__name__)

_AUDIT_DB_PATH = Path("data/code_audit.db")


def pre_tool_call(
    tool_name: str,
    tool_args: dict[str, object],
    **kwargs: object,
) -> dict[str, str] | None:
    """Hermes lifecycle hook -- fires before every tool call.

    Args:
        tool_name: Name of the tool being invoked.
        tool_args: Arguments passed to the tool.
        **kwargs: Additional context from Hermes.

    Returns:
        None to allow execution, or dict with "error" key to block.
    """
    if tool_name != "execute_code":
        return None

    code = str(tool_args.get("code", ""))
    guard_result = check(code)

    if not guard_result.allowed:
        logger.warning(
            "sandbox_blocked",
            tool=tool_name,
            patterns=guard_result.blocked_patterns,
        )
        return {"error": guard_result.error_message}

    return None


def post_tool_call(
    tool_name: str,
    tool_args: dict[str, object],
    result: str,
    **kwargs: object,
) -> None:
    """Hermes lifecycle hook -- fires after every tool call.

    Args:
        tool_name: Name of the tool that was invoked.
        tool_args: Arguments that were passed to the tool.
        result: String result from tool execution.
        **kwargs: Additional context from Hermes.
    """
    if tool_name != "execute_code":
        return

    code = str(tool_args.get("code", ""))
    duration_ms = float(kwargs.get("duration_ms", 0.0))  # type: ignore[arg-type]
    exit_code = int(kwargs.get("exit_code", 0))  # type: ignore[arg-type]
    files_touched: list[str] = list(kwargs.get("files_touched", []))  # type: ignore[arg-type]

    record(
        code=code,
        exit_code=exit_code,
        duration_ms=duration_ms,
        files_touched=files_touched,
        db_path=_AUDIT_DB_PATH,
    )
