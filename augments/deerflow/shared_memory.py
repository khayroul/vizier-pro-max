"""Cross-agent shared memory via file-based IPC.

Thread-safe. JSON file at tmp/shared_memory_{session_id}.json.
Parent reads after children complete. Children write observations.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SharedMemory:
    """File-based shared memory for cross-agent observations."""

    def __init__(
        self,
        session_id: str,
        base_dir: Path | None = None,
    ) -> None:
        self._session_id = session_id
        self._base_dir = base_dir or Path("tmp")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @property
    def file_path(self) -> Path:
        return self._base_dir / f"shared_memory_{self._session_id}.json"

    def write(self, source_id: str, observation: dict[str, Any]) -> None:
        """Append an observation from a child agent."""
        with self._lock:
            existing = self._read_raw()
            existing.append({
                "source": source_id,
                **observation,
            })
            self.file_path.write_text(json.dumps(existing, indent=2))
        logger.debug("SharedMemory write from %s", source_id)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all observations."""
        with self._lock:
            return self._read_raw()

    def cleanup(self) -> None:
        """Delete the shared memory file."""
        if self.file_path.exists():
            self.file_path.unlink()
            logger.info("SharedMemory cleaned up: %s", self.file_path)

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            return json.loads(self.file_path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
