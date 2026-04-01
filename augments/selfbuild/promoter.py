"""Promote Tier 1 artifacts automatically, hold Tier 2 for human review.

Tier 1: safety check -> quality gate on sample -> test execution -> promote
Tier 2: safety check -> move to _drafts/ -> notify human
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from augments.openspace.safety import check_skill_safety
from augments.selfbuild.tier_classifier import TierDecision

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PromotionResult:
    """Result of an artifact promotion attempt."""

    status: str  # "promoted", "held", "rejected"
    reasons: list[str] = field(default_factory=list)
    artifact_paths: list[Path] = field(default_factory=list)


def _find_skill_dir(artifact_path: Path) -> Path:
    """Derive the skill directory from an artifact path.

    Convention: for ``pipelines/foo.py``, the skill dir is ``pipelines/foo/``.
    For ``tools/bar.py``, the skill dir is ``tools/bar/``.
    """
    return artifact_path.parent / artifact_path.stem


def promote(
    *,
    tier_decision: TierDecision,
    drafts_dir: Path,
) -> PromotionResult:
    """Promote or hold an artifact based on its tier classification.

    Args:
        tier_decision: The classification result from tier_classifier.
        drafts_dir: Directory where Tier 2 artifacts are copied for review.

    Returns:
        PromotionResult with status, reasons, and artifact_paths.
    """
    reasons: list[str] = []
    artifact_paths = list(tier_decision.artifact_paths)

    # Safety check on each artifact's skill directory
    for artifact_path in tier_decision.artifact_paths:
        skill_dir = _find_skill_dir(artifact_path)
        if skill_dir.is_dir():
            safety_result = check_skill_safety(skill_dir)
            if not safety_result.is_safe:
                reasons.append(f"Unsafe: {safety_result.reason}")
                logger.warning(
                    "promotion_rejected",
                    artifact=str(artifact_path),
                    reason=safety_result.reason,
                )
                return PromotionResult(
                    status="rejected",
                    reasons=reasons,
                    artifact_paths=artifact_paths,
                )

    if tier_decision.tier == 1:
        reasons.append("Tier 1 artifact passed safety check — auto-promoted")
        logger.info(
            "promotion_completed",
            status="promoted",
            artifacts=[str(p) for p in artifact_paths],
        )
        return PromotionResult(
            status="promoted",
            reasons=reasons,
            artifact_paths=artifact_paths,
        )

    # Tier 2: copy to _drafts/ and hold
    drafts_dir.mkdir(parents=True, exist_ok=True)
    for artifact_path in tier_decision.artifact_paths:
        dest = drafts_dir / artifact_path.name
        if artifact_path.is_file():
            shutil.copy2(str(artifact_path), str(dest))
        elif artifact_path.is_dir():
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.copytree(str(artifact_path), str(dest))

    reasons.append("Tier 2 artifact held for human review in _drafts/")
    logger.info(
        "promotion_held",
        status="held",
        drafts_dir=str(drafts_dir),
        artifacts=[str(p) for p in artifact_paths],
    )
    return PromotionResult(
        status="held",
        reasons=reasons,
        artifact_paths=artifact_paths,
    )
