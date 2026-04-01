"""Classify generated artifacts as Tier 1 (auto-promote) or Tier 2 (human-approve).

Tier 1: Pipeline collapses from OpenSpace CAPTURED — no external side effects.
Tier 2: New atomic tools, tools with network/filesystem side effects, client-facing tools.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_DELIVERY_KEYWORDS = frozenset({"delivery", "vizier-delivery"})


@dataclass(frozen=True)
class TierDecision:
    """Classification result for a generated artifact."""

    tier: int
    reasons: list[str] = field(default_factory=list)
    artifact_paths: list[Path] = field(default_factory=list)


def _is_pipeline(artifact_path: Path) -> bool:
    """Check if artifact lives in a pipelines/ directory and is a .py file."""
    return artifact_path.suffix == ".py" and "pipelines" in artifact_path.parts


def _read_manifest_toolset(manifest_path: Path) -> str | None:
    """Extract toolset value from a YAML manifest (simple line parsing)."""
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError:
        return None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("toolset:"):
            value = stripped.split(":", 1)[1].strip().strip("'\"")
            return value
    return None


def classify(
    *,
    artifact_path: Path,
    manifest_path: Path | None,
    origin: str,
) -> TierDecision:
    """Classify an artifact as Tier 1 or Tier 2.

    Args:
        artifact_path: Path to the generated artifact file.
        manifest_path: Optional path to the artifact's YAML manifest.
        origin: Origin tag (e.g. "openspace_captured", "manual").

    Returns:
        TierDecision with tier, reasons, and artifact_paths.
    """
    reasons: list[str] = []
    artifact_paths = [artifact_path]

    # Check delivery toolset first — always Tier 2
    if manifest_path is not None and manifest_path.exists():
        toolset = _read_manifest_toolset(manifest_path)
        if toolset and toolset.lower() in _DELIVERY_KEYWORDS:
            reasons.append(f"Delivery toolset detected: {toolset}")
            logger.info(
                "tier_classified",
                tier=2,
                artifact=str(artifact_path),
                reasons=reasons,
            )
            return TierDecision(tier=2, reasons=reasons, artifact_paths=artifact_paths)

    # Tier 1: pipeline from openspace_captured
    if origin == "openspace_captured" and _is_pipeline(artifact_path):
        reasons.append("Pipeline collapse from openspace_captured origin")
        logger.info(
            "tier_classified",
            tier=1,
            artifact=str(artifact_path),
            reasons=reasons,
        )
        return TierDecision(tier=1, reasons=reasons, artifact_paths=artifact_paths)

    # Tier 2: has manifest (new atomic tool)
    if manifest_path is not None and manifest_path.exists():
        reasons.append("New atomic tool with manifest requires human review")
        logger.info(
            "tier_classified",
            tier=2,
            artifact=str(artifact_path),
            reasons=reasons,
        )
        return TierDecision(tier=2, reasons=reasons, artifact_paths=artifact_paths)

    # Conservative default: Tier 2
    reasons.append("Conservative default — unrecognized artifact type")
    logger.info(
        "tier_classified",
        tier=2,
        artifact=str(artifact_path),
        reasons=reasons,
    )
    return TierDecision(tier=2, reasons=reasons, artifact_paths=artifact_paths)
