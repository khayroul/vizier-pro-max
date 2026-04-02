"""Deliverable Context — propagates deliverable_id + client_id via contextvars.

In-process: automatic propagation within a session.
Cross-session: deliverable_id passed explicitly in delegate_task context
field and injected via set_context() on child session startup.

Pipeline step context:
    Before each LLM call, pipelines should call set_pipeline_step() so that
    cost_ledger.pre_llm_call() can record step_name / pipeline_name even when
    Hermes fires the hook without those fields.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_deliverable_id: ContextVar[str | None] = ContextVar("deliverable_id", default=None)
_client_id: ContextVar[str | None] = ContextVar("client_id", default=None)
_step_name: ContextVar[str | None] = ContextVar("pipeline_step_name", default=None)
_pipeline_name: ContextVar[str | None] = ContextVar("pipeline_name", default=None)
_pipeline_version: ContextVar[str | None] = ContextVar("pipeline_version", default=None)


def start_deliverable(client_id: str | None = None) -> str:
    """Start a new deliverable — generates UUID4, sets context.

    Args:
        client_id: Optional client identifier for cost rollup.

    Returns:
        The generated deliverable_id (UUID4 string).
    """
    did = str(uuid.uuid4())
    _deliverable_id.set(did)
    _client_id.set(client_id)
    return did


def set_context(deliverable_id: str, client_id: str | None = None) -> None:
    """Restore context from an explicit deliverable_id (cross-session).

    Args:
        deliverable_id: Existing deliverable ID to restore.
        client_id: Optional client identifier.
    """
    _deliverable_id.set(deliverable_id)
    _client_id.set(client_id)


def set_pipeline_step(
    step_name: str | None,
    pipeline_name: str | None = None,
    pipeline_version: str | None = None,
) -> None:
    """Set pipeline step context before an LLM call.

    Pipelines call this so cost_ledger.pre_llm_call() can record which step
    and pipeline produced each LLM call, even when Hermes fires the hook
    without those fields.

    Args:
        step_name: Name of the current pipeline step (e.g. "draft", "format").
        pipeline_name: Pipeline identifier (e.g. "content_generate").
        pipeline_version: Optional semver string (e.g. "1.0").
    """
    _step_name.set(step_name)
    _pipeline_name.set(pipeline_name)
    _pipeline_version.set(pipeline_version)


def get_deliverable_id() -> str | None:
    """Return the current deliverable_id, or None if not set."""
    return _deliverable_id.get()


def get_client_id() -> str | None:
    """Return the current client_id, or None if not set."""
    return _client_id.get()


def get_step_name() -> str | None:
    """Return the current pipeline step name, or None if not set."""
    return _step_name.get()


def get_pipeline_name() -> str | None:
    """Return the current pipeline name, or None if not set."""
    return _pipeline_name.get()


def get_pipeline_version() -> str | None:
    """Return the current pipeline version, or None if not set."""
    return _pipeline_version.get()


def clear_context() -> None:
    """Clear all deliverable and pipeline step context between pipeline runs."""
    _deliverable_id.set(None)
    _client_id.set(None)
    _step_name.set(None)
    _pipeline_name.set(None)
    _pipeline_version.set(None)
