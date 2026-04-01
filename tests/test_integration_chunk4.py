# tests/test_integration_chunk4.py
"""E2E integration test for Chunk 4: augments + quality gates."""
from __future__ import annotations

import sqlite3
from pathlib import Path


class TestChunk4Integration:
    def test_capturer_finds_chain_and_generates_draft(self, tmp_path: Path) -> None:
        """Capturer detects a chain -> generator creates draft."""
        from augments.openspace.capturer import detect_repeating_chains
        from augments.openspace.generator import generate_pipeline_draft

        # Create mock DB with repeating chain
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE prompt_log (
                id INTEGER PRIMARY KEY, session_id TEXT,
                timestamp TEXT, tool_name TEXT, tool_args TEXT, result TEXT
            )
        """)
        for s in range(6):
            for tool in ["httpx_fetch", "jinja2_render"]:
                conn.execute(
                    "INSERT INTO prompt_log VALUES (NULL, ?, ?, ?, '{}', 'ok')",
                    (f"s{s}", f"2026-04-0{s+1}", tool),
                )
        conn.commit()
        conn.close()

        chains = detect_repeating_chains(db_path=db_path, threshold=5)
        assert len(chains) >= 1

        draft_dir = tmp_path / "_drafts"
        draft_dir.mkdir()
        draft = generate_pipeline_draft(chain=chains[0], output_dir=draft_dir)
        assert draft.exists()
        assert "def run(" in draft.read_text()

    def test_version_dag_lifecycle(self, tmp_path: Path) -> None:
        """Import -> fix -> deactivate old -> new active."""
        from augments.openspace.version_dag import SkillRecord, VersionDAG

        dag = VersionDAG(db_path=tmp_path / "test.db")
        dag.save(SkillRecord(
            skill_id="s__v0", name="s", path=Path("/s"),
            is_active=True, origin="IMPORTED", generation=0,
            parent_ids=[], change_summary="import",
        ))
        dag.atomic_replace(
            new_record=SkillRecord(
                skill_id="s__v1", name="s", path=Path("/s_v1"),
                is_active=True, origin="FIXED", generation=1,
                parent_ids=["s__v0"], change_summary="fix",
            ),
            old_skill_id="s__v0",
        )
        old_record = dag.get("s__v0")
        assert old_record is not None
        assert old_record.is_active is False

        new_record = dag.get("s__v1")
        assert new_record is not None
        assert new_record.is_active is True

        assert len(dag.get_lineage("s__v1")) == 2

    def test_quality_gate_layers_available(self) -> None:
        """Quality gate has layers 1-6 registered."""
        from middleware.quality_gate import LAYERS

        assert len(LAYERS) >= 6
