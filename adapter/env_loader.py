"""Load .env file from project root into os.environ. Idempotent."""
from __future__ import annotations

import os
import threading
from pathlib import Path

_lock = threading.Lock()
_loaded = False


def _env_file_path() -> Path:
    """Return the path to the project .env file."""
    return Path(__file__).resolve().parent.parent / ".env"


def ensure_env() -> None:
    """Load .env into os.environ. Idempotent, thread-safe.

    Reads the project-root .env file and sets environment variables that are
    not already present. Uses double-checked locking to guarantee at-most-once
    execution even under concurrent callers.
    """
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        env_file = _env_file_path()
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
        _loaded = True
