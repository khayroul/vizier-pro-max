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
    monkeypatch.setattr(run_hermes_telegram, "load_default_provider", lambda: "custom")
    monkeypatch.setattr(
        run_hermes_telegram,
        "load_runtime_base_url",
        lambda: "https://api.openai.com/v1",
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    env = run_hermes_telegram.build_gateway_env()

    assert env["HERMES_ENABLE_PROJECT_PLUGINS"] == "true"
    assert env["MESSAGING_CWD"] == str(run_hermes_telegram.PROJECT_ROOT)
    assert env["HERMES_MODEL"] == "gpt-5.4-mini"
    assert env["HERMES_INFERENCE_PROVIDER"] == "custom"


def test_build_gateway_env_requires_telegram_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "ensure_env", lambda: None)
    monkeypatch.setattr(run_hermes_telegram, "load_default_provider", lambda: "custom")
    monkeypatch.setattr(
        run_hermes_telegram,
        "load_runtime_base_url",
        lambda: "https://api.openai.com/v1",
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        run_hermes_telegram.build_gateway_env()


def test_build_gateway_env_requires_openai_key_for_openai_compatible_custom_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "ensure_env", lambda: None)
    monkeypatch.setattr(run_hermes_telegram, "load_default_provider", lambda: "custom")
    monkeypatch.setattr(
        run_hermes_telegram,
        "load_runtime_base_url",
        lambda: "https://api.openai.com/v1",
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        run_hermes_telegram.build_gateway_env()


def test_build_gateway_env_uses_dummy_key_for_local_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "ensure_env", lambda: None)
    monkeypatch.setattr(run_hermes_telegram, "load_default_provider", lambda: "custom")
    monkeypatch.setattr(
        run_hermes_telegram,
        "load_runtime_base_url",
        lambda: "http://127.0.0.1:11436/v1",
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    env = run_hermes_telegram.build_gateway_env()

    assert env["OPENAI_BASE_URL"] == "http://127.0.0.1:11436/v1"
    assert env["VIZIER_GATEWAY_BASE_URL"] == "http://127.0.0.1:11436/v1"
    assert env["OPENAI_API_KEY"] == "vizier-local-gateway"


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


def test_build_launch_agent_plist_uses_vizier_launcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(run_hermes_telegram, "build_gateway_env", lambda: {
        "PATH": "/tmp/bin",
        "VIRTUAL_ENV": "/tmp/venv",
        "HERMES_HOME": "/tmp/hermes",
        "OPENAI_BASE_URL": "http://127.0.0.1:11436/v1",
        "OPENAI_API_KEY": "vizier-local-gateway",
    })

    plist = run_hermes_telegram.build_launch_agent_plist()

    assert str(run_hermes_telegram.SCRIPT_PATH) in plist
    assert "<string>run</string>" in plist
    assert str(run_hermes_telegram.PROJECT_ROOT) in plist
    assert "MESSAGING_CWD" not in plist
    assert "TELEGRAM_BOT_TOKEN" not in plist
    assert "vizier-local-gateway" in plist


def test_run_cli_dispatches_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setattr(run_hermes_telegram, "start_service", lambda: called.append("start"))

    exit_code = run_hermes_telegram.run_cli(["start"])

    assert exit_code == 0
    assert called == ["start"]


def test_run_cli_dispatches_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setattr(run_hermes_telegram, "status_service", lambda: called.append("status"))

    exit_code = run_hermes_telegram.run_cli(["status"])

    assert exit_code == 0
    assert called == ["status"]
