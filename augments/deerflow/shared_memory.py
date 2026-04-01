"""Cross-agent shared memory via file-based IPC.

Thread-safe within a single process via threading.Lock.
Cross-process safe via fcntl file locking (POSIX).
JSON file at tmp/shared_memory_{session_id}.json.
Parent reads after children complete. Children write observations.
"""
from __future__ import annotations

import fcntl
import io
import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MAX_OBSERVATIONS = 500


class SharedMemory:
    """File-based shared memory for cross-agent observations.

    Thread-safe (threading.Lock) AND cross-process safe (fcntl.flock).
    Observations are capped at MAX_OBSERVATIONS to prevent unbounded growth.
    """

    def __init__(
        self,
        session_id: str,
        base_dir: Path | None = None,
        max_observations: int = MAX_OBSERVATIONS,
    ) -> None:
        self._session_id = session_id
        self._base_dir = base_dir or Path("tmp")
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.Lock()
        self._max_observations = max_observations

    @property
    def file_path(self) -> Path:
        """Path to the JSON shared memory file."""
        return self._base_dir / f"shared_memory_{self._session_id}.json"

    def write(self, source_id: str, observation: dict[str, Any]) -> None:
        """Append an observation from a child agent.

        Args:
            source_id: Identifier for the child agent writing.
            observation: Dict of observation data.

        Raises:
            ValueError: If observation limit is reached.
        """
        with self._thread_lock:
            with self._file_lock():
                existing = self._read_raw()
                if len(existing) >= self._max_observations:
                    msg = (
                        f"Observation limit reached ({self._max_observations}). "
                        "Cannot write more observations."
                    )
                    raise ValueError(msg)
                existing.append({"source": source_id, **observation})
                self.file_path.write_text(
                    json.dumps(existing, indent=2), encoding="utf-8"
                )
        logger.debug("SharedMemory write from %s", source_id)

    def read_all(self) -> list[dict[str, Any]]:
        """Read all observations."""
        with self._thread_lock:
            with self._file_lock():
                return self._read_raw()

    def cleanup(self) -> None:
        """Delete the shared memory file."""
        if self.file_path.exists():
            self.file_path.unlink()
            logger.info("SharedMemory cleaned up: %s", self.file_path)

    def _file_lock(self) -> _FileLockContext:
        """Return a context manager that holds an exclusive POSIX file lock."""
        return _FileLockContext(self._base_dir / f".lock_{self._session_id}")

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return data
        except (json.JSONDecodeError, OSError):
            return []


class _FileLockContext:
    """POSIX file lock context manager using fcntl.flock."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._fd: io.TextIOWrapper | None = None

    def __enter__(self) -> _FileLockContext:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self._lock_path, "w")  # noqa: SIM115
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
