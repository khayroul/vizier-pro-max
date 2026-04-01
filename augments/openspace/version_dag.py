"""SQLite store for skill lineage — version DAG with logical deactivation."""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SkillRecord:
    """A skill record in the version DAG."""

    skill_id: str
    name: str
    path: Path
    is_active: bool
    origin: str  # IMPORTED | CAPTURED | FIXED | DERIVED
    generation: int
    parent_ids: list[str]
    change_summary: str
    total_selections: int = 0
    total_completions: int = 0


class VersionDAG:
    """SQLite-backed skill lineage store."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or Path("state/openspace_skills.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        """Create tables if they don't exist."""
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS skill_records (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                path TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                origin TEXT NOT NULL,
                generation INTEGER NOT NULL DEFAULT 0,
                change_summary TEXT NOT NULL DEFAULT '',
                total_selections INTEGER NOT NULL DEFAULT 0,
                total_completions INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS skill_lineage_parents (
                skill_id TEXT NOT NULL,
                parent_id TEXT NOT NULL,
                PRIMARY KEY (skill_id, parent_id),
                FOREIGN KEY (skill_id) REFERENCES skill_records(skill_id)
            );
            """
        )

    def save(self, record: SkillRecord) -> None:
        """Upsert a skill record and its parent links."""
        self._conn.execute(
            """INSERT OR REPLACE INTO skill_records
               (skill_id, name, path, is_active, origin, generation, change_summary,
                total_selections, total_completions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.skill_id,
                record.name,
                str(record.path),
                int(record.is_active),
                record.origin,
                record.generation,
                record.change_summary,
                record.total_selections,
                record.total_completions,
            ),
        )
        for parent_id in record.parent_ids:
            self._conn.execute(
                "INSERT OR IGNORE INTO skill_lineage_parents"
                " (skill_id, parent_id) VALUES (?, ?)",
                (record.skill_id, parent_id),
            )
        self._conn.commit()

    def get(self, skill_id: str) -> SkillRecord | None:
        """Retrieve a skill by ID, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM skill_records WHERE skill_id = ?",
            (skill_id,),
        ).fetchone()
        if row is None:
            return None
        parent_rows = self._conn.execute(
            "SELECT parent_id FROM skill_lineage_parents WHERE skill_id = ?",
            (skill_id,),
        ).fetchall()
        return SkillRecord(
            skill_id=row[0],
            name=row[1],
            path=Path(row[2]),
            is_active=bool(row[3]),
            origin=row[4],
            generation=row[5],
            change_summary=row[6],
            total_selections=row[7],
            total_completions=row[8],
            parent_ids=[r[0] for r in parent_rows],
        )

    def deactivate(self, skill_id: str) -> None:
        """Logically deactivate a skill (soft delete)."""
        self._conn.execute(
            "UPDATE skill_records SET is_active = 0 WHERE skill_id = ?",
            (skill_id,),
        )
        self._conn.commit()

    def atomic_replace(
        self, *, new_record: SkillRecord, old_skill_id: str
    ) -> None:
        """Insert new active record and deactivate old in one transaction."""
        with self._conn:
            self._conn.execute(
                "UPDATE skill_records SET is_active = 0 WHERE skill_id = ?",
                (old_skill_id,),
            )
            self._conn.execute(
                """INSERT OR REPLACE INTO skill_records
                   (skill_id, name, path, is_active, origin, generation,
                    change_summary, total_selections, total_completions)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    new_record.skill_id,
                    new_record.name,
                    str(new_record.path),
                    int(new_record.is_active),
                    new_record.origin,
                    new_record.generation,
                    new_record.change_summary,
                    new_record.total_selections,
                    new_record.total_completions,
                ),
            )
            for parent_id in new_record.parent_ids:
                self._conn.execute(
                    "INSERT OR IGNORE INTO skill_lineage_parents"
                    " (skill_id, parent_id) VALUES (?, ?)",
                    (new_record.skill_id, parent_id),
                )

    def list_active(self) -> list[SkillRecord]:
        """Return all active skill records."""
        rows = self._conn.execute(
            "SELECT skill_id FROM skill_records WHERE is_active = 1"
        ).fetchall()
        results: list[SkillRecord] = []
        for (sid,) in rows:
            record = self.get(sid)
            if record is not None:
                results.append(record)
        return results

    def get_lineage(self, skill_id: str) -> list[SkillRecord]:
        """Walk the parent DAG back to roots, returning all ancestors."""
        visited: list[SkillRecord] = []
        queue = [skill_id]
        seen: set[str] = set()
        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            record = self.get(current)
            if record is not None:
                visited.append(record)
                queue.extend(record.parent_ids)
        return visited
