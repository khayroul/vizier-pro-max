"""Load .env file from project root into os.environ. Idempotent."""
from __future__ import annotations

import os
import threading
from collections.abc import Collection
from pathlib import Path

_lock = threading.Lock()
_loaded = False
_DEFAULT_OVERRIDE_KEYS = frozenset({
    "VIZIER_UPSTREAM_OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
    "GAMMA_API_KEY",
})


def _env_file_path() -> Path:
    """Return the path to the project .env file."""
    return Path(__file__).resolve().parent.parent / ".env"


def ensure_env(*, override_keys: Collection[str] | None = None) -> None:
    """Load .env into os.environ. Idempotent, thread-safe.

    Reads the project-root .env file and sets environment variables that are
    not already present. For repo-owned provider secrets, the project `.env`
    is treated as authoritative and overrides inherited shell values by
    default. Uses double-checked locking to guarantee at-most-once execution
    even under concurrent callers.

    Args:
        override_keys: Optional collection of keys that should always be loaded
            from the project `.env`, even when already present in ``os.environ``.
            Defaults to repo-owned secret keys such as provider credentials.
    """
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        env_file = _env_file_path()
        if env_file.exists():
            effective_override_keys = (
                _DEFAULT_OVERRIDE_KEYS
                if override_keys is None
                else frozenset(override_keys)
            )
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and (
                    key in effective_override_keys or key not in os.environ
                ):
                    os.environ[key] = value
        _loaded = True
