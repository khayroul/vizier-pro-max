"""Shared fixtures for scripts tests."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def fal_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure FAL_KEY is set for tests that don't explicitly clear the environment."""
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
