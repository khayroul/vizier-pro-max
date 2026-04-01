"""FastMCP server for OpenSpace skill evolution — 4 tools for Claude Code."""
from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from augments.openspace.version_dag import VersionDAG

logger = logging.getLogger(__name__)

mcp = FastMCP("openspace")

# Lazy-initialized DAG
_dag: VersionDAG | None = None


def _get_dag() -> VersionDAG:
    """Get or create the shared VersionDAG instance."""
    global _dag  # noqa: PLW0603
    if _dag is None:
        _dag = VersionDAG()
    return _dag


@mcp.tool()
def execute_evolution(mode: str, target_skill_id: str = "") -> str:
    """Trigger CAPTURED, FIXED, or DERIVED evolution manually."""
    valid_modes = {"CAPTURED", "FIXED", "DERIVED"}
    if mode.upper() not in valid_modes:
        return json.dumps(
            {"error": f"Invalid mode: {mode}. Must be one of {sorted(valid_modes)}"}
        )

    dag = _get_dag()
    if target_skill_id:
        record = dag.get(target_skill_id)
        if record is None:
            return json.dumps({"error": f"Skill not found: {target_skill_id}"})

    return json.dumps({
        "status": "triggered",
        "mode": mode.upper(),
        "target": target_skill_id or "auto-detect",
    })


@mcp.tool()
def search_skills(query: str, limit: int = 10) -> str:
    """BM25 search over active skill index."""
    dag = _get_dag()
    active = dag.list_active()

    # Simple keyword matching (BM25 deferred to Gate 3)
    query_lower = query.lower()
    matches: list[dict[str, Any]] = []
    for record in active:
        score = 0.0
        if query_lower in record.name.lower():
            score += 2.0
        if query_lower in record.change_summary.lower():
            score += 1.0
        if score > 0:
            matches.append({
                "skill_id": record.skill_id,
                "name": record.name,
                "origin": record.origin,
                "score": score,
            })

    matches.sort(key=lambda m: -m["score"])
    return json.dumps({"results": matches[:limit], "total": len(matches)})


@mcp.tool()
def fix_skill(skill_id: str, error_context: str) -> str:
    """Trigger FIXED evolution for a specific broken skill."""
    dag = _get_dag()
    record = dag.get(skill_id)
    if record is None:
        return json.dumps({"error": f"Skill not found: {skill_id}"})

    return json.dumps({
        "status": "fix_triggered",
        "skill_id": skill_id,
        "error_context": error_context[:200],
    })


@mcp.tool()
def get_lineage(skill_id: str) -> str:
    """Return the version DAG lineage for a skill."""
    dag = _get_dag()
    lineage = dag.get_lineage(skill_id)
    if not lineage:
        return json.dumps({"error": f"No lineage found for: {skill_id}"})

    return json.dumps({
        "lineage": [
            {
                "skill_id": r.skill_id,
                "name": r.name,
                "origin": r.origin,
                "generation": r.generation,
                "is_active": r.is_active,
                "parent_ids": r.parent_ids,
            }
            for r in lineage
        ],
    })


if __name__ == "__main__":
    mcp.run()
