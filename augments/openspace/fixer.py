"""Auto-repair broken skills from error logs.

Scans error context, generates a fix via LLM, creates a new
skill version with atomic_replace in the version DAG.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from adapter.llm_client import chat as llm_chat
from augments.openspace.version_dag import SkillRecord, VersionDAG

logger = logging.getLogger(__name__)


def _call_llm_for_fix(skill_content: str, error_context: str) -> str:
    """Call LLM to generate a fix (OpenAI -> Ollama fallback).

    Returns fixed SKILL.md content, or original with error comment on failure.
    """
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a skill repair engine. Given a broken SKILL.md "
                    "and an error traceback, output a corrected SKILL.md. "
                    "Preserve the original structure. Output ONLY valid markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"SKILL.md:\n{skill_content}\n\n"
                    f"ERROR:\n{error_context}"
                ),
            },
        ],
        max_tokens=2048,
    )
    if result is not None:
        return result
    return skill_content + "\n<!-- AUTO-FIX FAILED: LLM unavailable -->\n"


def fix_skill(
    *,
    dag: VersionDAG,
    skill_id: str,
    error_context: str,
    output_dir: Path,
) -> SkillRecord | None:
    """Fix a broken skill by generating a patched version.

    Args:
        dag: The version DAG storing skill lineage.
        skill_id: ID of the broken skill to fix.
        error_context: Error message/traceback from structlog.
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

    # Generate fix via LLM
    fixed_content = _call_llm_for_fix(original_content, error_context)

    # Create new version directory
    new_gen = existing.generation + 1
    uid = uuid.uuid4().hex[:8]
    new_id = f"{existing.name}__v{new_gen}_{uid}"
    new_dir = output_dir / new_id
    new_dir.mkdir(parents=True, exist_ok=True)

    # Write fixed SKILL.md
    (new_dir / "SKILL.md").write_text(fixed_content)

    # Create new record
    new_record = SkillRecord(
        skill_id=new_id,
        name=existing.name,
        path=new_dir,
        is_active=True,
        origin="FIXED",
        generation=new_gen,
        parent_ids=(skill_id,),
        change_summary=f"Fixed: {error_context[:100]}",
    )

    # Atomic replace: deactivate old, insert new
    dag.atomic_replace(new_record=new_record, old_skill_id=skill_id)

    logger.info("Fixed skill %s -> %s", skill_id, new_id)
    return new_record
