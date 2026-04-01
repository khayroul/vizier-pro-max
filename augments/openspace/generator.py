"""Generate SKILL.md and pipeline drafts from captured tool chains."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def generate_skill_md(
    *,
    chain: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate a SKILL.md from a captured tool chain.

    Args:
        chain: Dict with keys tools, occurrences, description.
        output_dir: Directory where the skill folder will be created.

    Returns:
        Path to the generated SKILL.md file.
    """
    tools: list[str] = chain["tools"]
    name = "_".join(tools[:3])
    skill_dir = output_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)

    tool_list = "\n".join(f"{i + 1}. `{tool}`" for i, tool in enumerate(tools))
    occurrences: int = chain["occurrences"]
    description: str = chain["description"]

    skill_content = f"""\
---
name: {name}
description: Collapsed pipeline for {description}
category: workflow
---

# {name}

Auto-captured from {occurrences} sessions.

## Tool Chain

{tool_list}

## Usage

This pattern was detected repeating across {occurrences} sessions.
Consider using `run_pipeline` with this as a collapsed pipeline.
"""
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(skill_content)
    logger.info("Generated SKILL.md: %s", skill_path)
    return skill_path


def generate_pipeline_draft(
    *,
    chain: dict[str, Any],
    output_dir: Path,
) -> Path:
    """Generate a pipeline draft Python file from a captured chain.

    Args:
        chain: Dict with keys tools, occurrences, description.
        output_dir: Directory where the draft .py file will be written.

    Returns:
        Path to the generated pipeline draft file.
    """
    tools: list[str] = chain["tools"]
    name = "_".join(tools[:3])
    occurrences: int = chain["occurrences"]
    description: str = chain["description"]

    tool_calls = []
    for tool in tools:
        tool_calls.append(f"    # Step: {tool}")
        tool_calls.append(f'    logger.info("Executing {tool}")')
        tool_calls.append(f'    # result = executor.run("{tool}", {{}})')

    tool_calls_str = "\n".join(tool_calls)

    draft_content = f'''\
"""Auto-generated pipeline draft: {description}

Captured from {occurrences} repeating sessions.
Review and customize before promoting from _drafts/.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def run(**kwargs: Any) -> dict[str, Any]:
    """Execute the {name} pipeline."""
{tool_calls_str}
    return {{"status": "draft", "pipeline": "{name}"}}
'''
    draft_path = output_dir / f"{name}.py"
    draft_path.write_text(draft_content)
    logger.info("Generated pipeline draft: %s", draft_path)
    return draft_path
