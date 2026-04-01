"""Promote better skill variants by generating enhanced versions.

Compares quality scores, generates an enhanced version via LLM,
creates a new directory. Parent remains active (coexists).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from augments.openspace.version_dag import SkillRecord, VersionDAG

logger = logging.getLogger(__name__)


def _call_llm_for_enhancement(
    skill_content: str, quality_scores: dict[str, float]
) -> str:
    """Call GPT-5.4-mini via Hermes to generate an enhanced version.

    In production, this calls the Hermes delegate_task or direct LLM API.
    Mocked in tests.
    """
    raise NotImplementedError("LLM call not available in this context")


def derive_skill(
    *,
    dag: VersionDAG,
    skill_id: str,
    quality_scores: dict[str, float],
    output_dir: Path,
) -> SkillRecord | None:
    """Derive an enhanced version of a skill.

    Parent remains active (coexists with derived version).

    Args:
        dag: The version DAG storing skill lineage.
        skill_id: ID of the skill to derive from.
        quality_scores: Mapping of skill_id to quality score.
        output_dir: Parent directory for new skill directories.

    Returns:
        The new SkillRecord if successful, None if skill not found.
    """
    existing = dag.get(skill_id)
    if existing is None:
        logger.warning("Skill not found: %s", skill_id)
        return None

    # Read original skill content
    original_skill_md = existing.path / "SKILL.md"
    original_content = ""
    if original_skill_md.exists():
        original_content = original_skill_md.read_text()

    # Generate enhancement via LLM
    enhanced_content = _call_llm_for_enhancement(original_content, quality_scores)

    # Create new version directory
    new_gen = existing.generation + 1
    uid = uuid.uuid4().hex[:8]
    new_id = f"{existing.name}__v{new_gen}_{uid}"
    new_dir = output_dir / new_id
    new_dir.mkdir(parents=True, exist_ok=True)

    # Write enhanced SKILL.md
    (new_dir / "SKILL.md").write_text(enhanced_content)

    # Create new record — parent stays active (no atomic_replace)
    new_record = SkillRecord(
        skill_id=new_id,
        name=existing.name,
        path=new_dir,
        is_active=True,
        origin="DERIVED",
        generation=new_gen,
        parent_ids=[skill_id],
        change_summary=(
            f"Enhanced variant (score: {quality_scores.get(skill_id, 'N/A')})"
        ),
    )

    # Save without deactivating parent (coexists)
    dag.save(new_record)

    logger.info("Derived skill %s -> %s", skill_id, new_id)
    return new_record
