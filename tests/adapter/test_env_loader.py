"""Tests for adapter/env_loader.py — shared .env loading."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from adapter.env_loader import ensure_env


@pytest.fixture(autouse=True)
def _reset_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the _loaded flag between tests."""
    import adapter.env_loader as mod

    monkeypatch.setattr(mod, "_loaded", False)


class TestEnsureEnv:
    def test_loads_env_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR_XYZ=hello\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("TEST_VAR_XYZ", raising=False)
        ensure_env()
        assert os.environ["TEST_VAR_XYZ"] == "hello"

    def test_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("IDEM_VAR=first\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("IDEM_VAR", raising=False)
        ensure_env()
        env_file.write_text("IDEM_VAR=second\n")
        ensure_env()
        assert os.environ["IDEM_VAR"] == "first"

    def test_does_not_overwrite_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_VAR=from_file\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.setenv("EXISTING_VAR", "from_env")
        ensure_env()
        assert os.environ["EXISTING_VAR"] == "from_env"

    @pytest.mark.parametrize("key_name", ["OPENAI_API_KEY", "ELEVENLABS_API_KEY", "GAMMA_API_KEY"])
    def test_overrides_repo_secret_keys_by_default(
        self, key_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(f"{key_name}=from_file\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.setenv(key_name, "from_env")
        ensure_env()
        assert os.environ[key_name] == "from_file"

    def test_custom_override_keys(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("CUSTOM_SECRET=from_file\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.setenv("CUSTOM_SECRET", "from_env")
        ensure_env(override_keys={"CUSTOM_SECRET"})
        assert os.environ["CUSTOM_SECRET"] == "from_file"

    def test_strips_quotes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text('QUOTED_VAR="hello world"\nSINGLE_Q=\'value\'\n')
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("QUOTED_VAR", raising=False)
        monkeypatch.delenv("SINGLE_Q", raising=False)
        ensure_env()
        assert os.environ["QUOTED_VAR"] == "hello world"
        assert os.environ["SINGLE_Q"] == "value"

    def test_skips_comments_and_blank_lines(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("# comment\n\nVALID_KEY=yes\n")
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        monkeypatch.delenv("VALID_KEY", raising=False)
        ensure_env()
        assert os.environ["VALID_KEY"] == "yes"

    def test_missing_env_file_is_noop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_file = tmp_path / "nonexistent.env"
        monkeypatch.setattr("adapter.env_loader._env_file_path", lambda: env_file)
        ensure_env()  # Should not raise
