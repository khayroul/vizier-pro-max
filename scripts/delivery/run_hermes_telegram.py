"""Start Hermes Telegram with Vizier project plugins and repo env."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

import yaml

from adapter.env_loader import ensure_env

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERMES_BIN = PROJECT_ROOT / ".venv" / "bin" / "hermes"
PYTHON_BIN = PROJECT_ROOT / ".venv" / "bin" / "python"
MODELS_CONFIG_PATH = PROJECT_ROOT / "config" / "models.yaml"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_PROVIDER = "openai"
GATEWAY_SUBCOMMANDS = {
    "run",
    "start",
    "stop",
    "restart",
    "status",
    "install",
    "uninstall",
    "setup",
}


def load_default_model() -> str:
    """Return the default model configured for Vizier."""
    if not MODELS_CONFIG_PATH.is_file():
        return DEFAULT_MODEL

    data = yaml.safe_load(MODELS_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    model = str(data.get("default_model", "")).strip()
    return model or DEFAULT_MODEL


def build_gateway_env() -> dict[str, str]:
    """Build the environment for Hermes Telegram runs."""
    ensure_env()
    env = os.environ.copy()
    env.setdefault("HERMES_ENABLE_PROJECT_PLUGINS", "true")
    env.setdefault("MESSAGING_CWD", str(PROJECT_ROOT))
    env.setdefault("HERMES_MODEL", load_default_model())
    env.setdefault("HERMES_INFERENCE_PROVIDER", DEFAULT_PROVIDER)

    if not env.get("TELEGRAM_BOT_TOKEN"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in the environment")
    if not env.get("OPENAI_API_KEY") and env.get("HERMES_INFERENCE_PROVIDER") == "openai":
        raise RuntimeError("OPENAI_API_KEY is required for the default Hermes provider")

    return env


def build_gateway_command(args: Sequence[str] | None = None) -> list[str]:
    """Build the Hermes CLI command for gateway execution."""
    cli_args = list(args or [])
    if cli_args and cli_args[0] in GATEWAY_SUBCOMMANDS:
        gateway_args = cli_args
    else:
        gateway_args = ["run", *cli_args]

    if HERMES_BIN.is_file():
        return [str(HERMES_BIN), "gateway", *gateway_args]
    return [str(PYTHON_BIN), "-m", "hermes_cli.main", "gateway", *gateway_args]


def run(args: Sequence[str] | None = None) -> subprocess.CompletedProcess[bytes]:
    """Launch Hermes gateway from the repo root."""
    env = build_gateway_env()
    command = build_gateway_command(args)
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    run(argv or sys.argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
