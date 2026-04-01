"""Root test configuration — shared fixtures for all test modules."""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def allow_temp_paths_for_security_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Allow test temp directories in path containment security checks.

    The security hardening added path containment validation to executor.py,
    render_typst.py, and process_media.py. Tests use pytest tmp_path which
    lives outside the project root. This fixture adds the system temp dir
    to VIZIER_ALLOWED_ROOTS so tests pass while production stays secure.
    """
    tmp_root = tempfile.gettempdir()
    existing = os.environ.get("VIZIER_ALLOWED_ROOTS", "")
    roots = f"{existing}:{tmp_root}" if existing else tmp_root
    monkeypatch.setenv("VIZIER_ALLOWED_ROOTS", roots)
