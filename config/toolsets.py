"""Vizier toolset constants — single source of truth."""
from __future__ import annotations

VIZIER_WORKFLOW_TOOLSETS = frozenset({
    "vizier-content",
    "vizier-document",
    "vizier-visual",
    "vizier-research",
    "vizier-audio",
    "vizier-delivery",
    "vizier-fallback",
    # vizier-code and vizier-knowledge deferred to Gate 3
})
