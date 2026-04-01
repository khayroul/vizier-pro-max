"""Tests for OpenSpace MCP server — tool registration and basic behavior."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from augments.openspace.version_dag import SkillRecord, VersionDAG


class TestOpenSpaceServer:
    """Verify server module loads and registers the expected tools."""

    def test_server_module_imports(self) -> None:
        """Server module imports without error."""
        from augments.openspace import server

        assert hasattr(server, "mcp")

    def test_server_has_four_tools(self) -> None:
        """Server registers exactly 4 tools."""
        from augments.openspace.server import mcp

        tools = asyncio.run(mcp.list_tools())
        tool_names = {t.name for t in tools}
        expected = {"execute_evolution", "search_skills", "fix_skill", "get_lineage"}
        assert expected == tool_names


class TestExecuteEvolution:
    """Unit tests for execute_evolution tool function."""

    def test_valid_mode_returns_triggered(self) -> None:
        """Valid mode without target returns triggered status."""
        from augments.openspace.server import execute_evolution

        result = json.loads(execute_evolution("CAPTURED"))
        assert result["status"] == "triggered"
        assert result["mode"] == "CAPTURED"
        assert result["target"] == "auto-detect"

    def test_invalid_mode_returns_error(self) -> None:
        """Invalid mode returns an error payload."""
        from augments.openspace.server import execute_evolution

        result = json.loads(execute_evolution("BOGUS"))
        assert "error" in result
        assert "BOGUS" in result["error"]

    def test_mode_is_case_insensitive(self) -> None:
        """Mode matching is case-insensitive."""
        from augments.openspace.server import execute_evolution

        result = json.loads(execute_evolution("fixed"))
        assert result["status"] == "triggered"
        assert result["mode"] == "FIXED"


class TestSearchSkills:
    """Unit tests for search_skills tool function."""

    def test_empty_dag_returns_no_results(self, tmp_path: Path) -> None:
        """Search on empty DAG returns zero results."""
        import augments.openspace.server as srv

        srv._dag = VersionDAG(db_path=tmp_path / "test.db")
        result = json.loads(srv.search_skills("anything"))
        assert result["results"] == []
        assert result["total"] == 0

    def test_search_matches_by_name(self, tmp_path: Path) -> None:
        """Search finds skills whose name contains the query."""
        import augments.openspace.server as srv

        dag = VersionDAG(db_path=tmp_path / "test.db")
        dag.save(SkillRecord(
            skill_id="s1",
            name="deploy-helper",
            path=Path("skills/deploy.py"),
            is_active=True,
            origin="CAPTURED",
            generation=0,
            parent_ids=[],
            change_summary="Deploys stuff",
        ))
        srv._dag = dag
        result = json.loads(srv.search_skills("deploy"))
        assert result["total"] == 1
        assert result["results"][0]["skill_id"] == "s1"


class TestFixSkill:
    """Unit tests for fix_skill tool function."""

    def test_missing_skill_returns_error(self, tmp_path: Path) -> None:
        """Fixing a non-existent skill returns error."""
        import augments.openspace.server as srv

        srv._dag = VersionDAG(db_path=tmp_path / "test.db")
        result = json.loads(srv.fix_skill("no-such-id", "some error"))
        assert "error" in result

    def test_existing_skill_returns_fix_triggered(self, tmp_path: Path) -> None:
        """Fixing an existing skill returns fix_triggered status."""
        import augments.openspace.server as srv

        dag = VersionDAG(db_path=tmp_path / "test.db")
        dag.save(SkillRecord(
            skill_id="s1",
            name="broken-skill",
            path=Path("skills/broken.py"),
            is_active=True,
            origin="CAPTURED",
            generation=0,
            parent_ids=[],
            change_summary="It broke",
        ))
        srv._dag = dag
        result = json.loads(srv.fix_skill("s1", "TypeError at line 5"))
        assert result["status"] == "fix_triggered"
        assert result["skill_id"] == "s1"


class TestGetLineage:
    """Unit tests for get_lineage tool function."""

    def test_missing_skill_returns_error(self, tmp_path: Path) -> None:
        """Lineage for non-existent skill returns error."""
        import augments.openspace.server as srv

        srv._dag = VersionDAG(db_path=tmp_path / "test.db")
        result = json.loads(srv.get_lineage("no-such-id"))
        assert "error" in result

    def test_single_skill_returns_lineage(self, tmp_path: Path) -> None:
        """Lineage for a root skill returns single entry."""
        import augments.openspace.server as srv

        dag = VersionDAG(db_path=tmp_path / "test.db")
        dag.save(SkillRecord(
            skill_id="root",
            name="root-skill",
            path=Path("skills/root.py"),
            is_active=True,
            origin="IMPORTED",
            generation=0,
            parent_ids=[],
            change_summary="Initial import",
        ))
        srv._dag = dag
        result = json.loads(srv.get_lineage("root"))
        assert len(result["lineage"]) == 1
        assert result["lineage"][0]["skill_id"] == "root"
