"""Tests for the Hermes Telegram launcher."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from scripts.delivery import run_hermes_telegram


def test_build_gateway_env_sets_project_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "ensure_env", lambda: None)
    monkeypatch.setattr(run_hermes_telegram, "load_default_model", lambda: "gpt-5.4-mini")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = run_hermes_telegram.build_gateway_env()

    assert env["HERMES_ENABLE_PROJECT_PLUGINS"] == "true"
    assert env["MESSAGING_CWD"] == str(run_hermes_telegram.PROJECT_ROOT)
    assert env["HERMES_MODEL"] == "gpt-5.4-mini"
    assert env["HERMES_INFERENCE_PROVIDER"] == "openai"


def test_build_gateway_env_requires_telegram_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "ensure_env", lambda: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        run_hermes_telegram.build_gateway_env()


def test_build_gateway_command_defaults_to_gateway_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_hermes_telegram,
        "HERMES_BIN",
        run_hermes_telegram.PROJECT_ROOT / ".venv" / "bin" / "hermes",
    )

    command = run_hermes_telegram.build_gateway_command(["--replace"])

    assert command[:3] == [
        str(run_hermes_telegram.HERMES_BIN),
        "gateway",
        "run",
    ]
    assert command[3:] == ["--replace"]


def test_build_gateway_command_allows_explicit_status_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run_hermes_telegram,
        "HERMES_BIN",
        run_hermes_telegram.PROJECT_ROOT / ".venv" / "bin" / "hermes",
    )

    command = run_hermes_telegram.build_gateway_command(["status"])

    assert command == [
        str(run_hermes_telegram.HERMES_BIN),
        "gateway",
        "status",
    ]


def test_run_executes_hermes_with_project_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess(args=["hermes"], returncode=0)
    run_mock = MagicMock(return_value=completed)
    monkeypatch.setattr(run_hermes_telegram, "build_gateway_env", lambda: {"X": "1"})
    monkeypatch.setattr(
        run_hermes_telegram,
        "build_gateway_command",
        lambda args: ["hermes", "gateway", "run"],
    )
    monkeypatch.setattr(run_hermes_telegram.subprocess, "run", run_mock)

    result = run_hermes_telegram.run(["--replace"])

    assert result.returncode == 0
    run_mock.assert_called_once_with(
        ["hermes", "gateway", "run"],
        cwd=run_hermes_telegram.PROJECT_ROOT,
        env={"X": "1"},
        check=True,
    )
