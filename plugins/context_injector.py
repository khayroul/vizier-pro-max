"""Context Injector — cross-session deliverable_id propagation.

Reads deliverable_id from delegate_task context field on child
session startup and sets it in local contextvars.
"""
from __future__ import annotations

from typing import Any

import structlog

from middleware.deliverable_context import set_context

logger = structlog.get_logger(__name__)


def inject_from_task_context(context: dict[str, Any] | None) -> None:
    """Extract deliverable_id from task context and set in local contextvars.

    Called by Hermes on child session startup when processing a
    delegate_task batch entry with context: {deliverable_id, client_id}.

    Args:
        context: The context dict from a delegate_task batch entry.
                 May be None or missing deliverable_id.
    """
    if not context or "deliverable_id" not in context:
        return

    deliverable_id = context["deliverable_id"]
    client_id = context.get("client_id")
    set_context(deliverable_id=deliverable_id, client_id=client_id)
    logger.info(
        "Injected deliverable context: deliverable_id=%s, client_id=%s",
        deliverable_id,
        client_id,
    )
