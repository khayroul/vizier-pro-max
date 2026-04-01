"""Tests for OpenSpace version DAG — SQLite skill lineage store."""
from __future__ import annotations

from pathlib import Path

import pytest

from augments.openspace.version_dag import SkillRecord, VersionDAG


@pytest.fixture()
def dag(tmp_path: Path) -> VersionDAG:
    return VersionDAG(db_path=tmp_path / "skills.db")


class TestVersionDAG:
    def test_save_and_retrieve(self, dag: VersionDAG) -> None:
        record = SkillRecord(
            skill_id="test__v0_abc12345",
            name="test",
            path=Path("/skills/test"),
            is_active=True,
            origin="CAPTURED",
            generation=0,
            parent_ids=[],
            change_summary="Initial capture",
        )
        dag.save(record)
        retrieved = dag.get("test__v0_abc12345")
        assert retrieved is not None
        assert retrieved.name == "test"
        assert retrieved.is_active is True

    def test_deactivate(self, dag: VersionDAG) -> None:
        record = SkillRecord(
            skill_id="fix__v0_def67890",
            name="fix",
            path=Path("/skills/fix"),
            is_active=True,
            origin="IMPORTED",
            generation=0,
            parent_ids=[],
            change_summary="Import",
        )
        dag.save(record)
        dag.deactivate("fix__v0_def67890")
        retrieved = dag.get("fix__v0_def67890")
        assert retrieved is not None
        assert retrieved.is_active is False

    def test_atomic_replace(self, dag: VersionDAG) -> None:
        """Insert new active + deactivate old in one transaction."""
        old = SkillRecord(
            skill_id="old__v0_111",
            name="old",
            path=Path("/skills/old"),
            is_active=True,
            origin="IMPORTED",
            generation=0,
            parent_ids=[],
            change_summary="Original",
        )
        dag.save(old)

        new = SkillRecord(
            skill_id="old__v1_222",
            name="old",
            path=Path("/skills/old_v1"),
            is_active=True,
            origin="FIXED",
            generation=1,
            parent_ids=["old__v0_111"],
            change_summary="Fixed bug",
        )
        dag.atomic_replace(new_record=new, old_skill_id="old__v0_111")

        assert dag.get("old__v0_111").is_active is False  # type: ignore[union-attr]
        assert dag.get("old__v1_222").is_active is True  # type: ignore[union-attr]

    def test_list_active(self, dag: VersionDAG) -> None:
        for i in range(3):
            dag.save(
                SkillRecord(
                    skill_id=f"skill_{i}",
                    name=f"skill_{i}",
                    path=Path(f"/skills/{i}"),
                    is_active=(i != 1),  # deactivate middle one
                    origin="CAPTURED",
                    generation=0,
                    parent_ids=[],
                    change_summary=f"Skill {i}",
                )
            )
        active = dag.list_active()
        assert len(active) == 2

    def test_get_lineage(self, dag: VersionDAG) -> None:
        dag.save(
            SkillRecord(
                skill_id="a__v0",
                name="a",
                path=Path("/a"),
                is_active=False,
                origin="IMPORTED",
                generation=0,
                parent_ids=[],
                change_summary="v0",
            )
        )
        dag.save(
            SkillRecord(
                skill_id="a__v1",
                name="a",
                path=Path("/a_v1"),
                is_active=True,
                origin="FIXED",
                generation=1,
                parent_ids=["a__v0"],
                change_summary="v1",
            )
        )
        lineage = dag.get_lineage("a__v1")
        assert len(lineage) == 2
