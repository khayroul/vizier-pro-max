"""Deliverable Context — propagates deliverable_id + client_id via contextvars.

In-process: automatic propagation within a session.
Cross-session: deliverable_id passed explicitly in delegate_task context
field and injected via set_context() on child session startup.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar

_deliverable_id: ContextVar[str | None] = ContextVar("deliverable_id", default=None)
_client_id: ContextVar[str | None] = ContextVar("client_id", default=None)


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


def get_deliverable_id() -> str | None:
    """Return the current deliverable_id, or None if not set."""
    return _deliverable_id.get()


def get_client_id() -> str | None:
    """Return the current client_id, or None if not set."""
    return _client_id.get()


def clear_context() -> None:
    """Clear deliverable context — use between pipeline runs."""
    _deliverable_id.set(None)
    _client_id.set(None)
