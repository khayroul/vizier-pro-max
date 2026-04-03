"""Start Hermes Telegram with Vizier project plugins and repo env."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from xml.sax.saxutils import escape

import httpx
import yaml

from adapter.env_loader import ensure_env

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()
HERMES_BIN = PROJECT_ROOT / ".venv" / "bin" / "hermes"
PYTHON_BIN = PROJECT_ROOT / ".venv" / "bin" / "python"
INFERENCE_GATEWAY_SCRIPT = PROJECT_ROOT / "scripts" / "delivery" / "run_inference_gateway.py"
MODELS_CONFIG_PATH = PROJECT_ROOT / "config" / "models.yaml"
HERMES_CONFIG_PATH = PROJECT_ROOT / "config" / "hermes.yaml"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_PROVIDER = "custom"
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
LAUNCH_AGENT_LABEL = "ai.hermes.gateway"
LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
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


def load_default_provider() -> str:
    """Return the default Hermes inference provider configured for Vizier."""
    if not HERMES_CONFIG_PATH.is_file():
        return DEFAULT_PROVIDER

    data = yaml.safe_load(HERMES_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    model_cfg = data.get("model") or {}
    if isinstance(model_cfg, dict):
        provider = str(model_cfg.get("provider", "")).strip().lower()
        if provider:
            return provider
    return DEFAULT_PROVIDER


def load_runtime_base_url() -> str:
    """Return the configured OpenAI-compatible endpoint base URL, if any."""
    if not HERMES_CONFIG_PATH.is_file():
        return ""

    data = yaml.safe_load(HERMES_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    model_cfg = data.get("model") or {}
    if isinstance(model_cfg, dict):
        base_url = str(model_cfg.get("base_url", "")).strip()
        if base_url:
            return base_url
    return ""


def _is_local_gateway_url(base_url: str) -> bool:
    normalized = base_url.strip().lower()
    return normalized.startswith("http://127.0.0.1:11436") or normalized.startswith("http://localhost:11436")


def _gateway_health_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/health"


def _require_local_gateway_ready(base_url: str, *, timeout: float = 2.0) -> None:
    """Fail closed if Hermes is pointed at a local Vizier gateway that is down."""
    if not _is_local_gateway_url(base_url):
        return

    health_url = _gateway_health_url(base_url)
    try:
        response = httpx.get(health_url, timeout=timeout)
    except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
        msg = f"Vizier inference gateway is not reachable at {health_url}: {exc}"
        raise RuntimeError(msg) from exc

    if response.status_code != 200:
        msg = f"Vizier inference gateway health check failed at {health_url} with status {response.status_code}"
        raise RuntimeError(msg)


def _build_inference_gateway_env(base_url: str) -> dict[str, str]:
    """Build the child environment for the local inference gateway process."""
    from scripts.delivery.run_inference_gateway import _prepare_gateway_env

    _prepare_gateway_env()
    env = os.environ.copy()
    env.setdefault("VIRTUAL_ENV", str(PROJECT_ROOT / ".venv"))
    env.setdefault(
        "PATH",
        f"{PROJECT_ROOT / '.venv' / 'bin'}:{os.environ.get('PATH', os.defpath)}",
    )
    if base_url:
        env["VIZIER_GATEWAY_BASE_URL"] = base_url
    return env


def _inference_gateway_command() -> list[str]:
    return [str(PYTHON_BIN), str(INFERENCE_GATEWAY_SCRIPT)]


def _ensure_local_gateway_process(
    base_url: str,
    *,
    poll_attempts: int = 20,
    poll_interval: float = 0.25,
) -> subprocess.Popen[bytes] | None:
    """Start the local inference gateway if Hermes depends on it and it is not running."""
    if not _is_local_gateway_url(base_url):
        return None

    try:
        _require_local_gateway_ready(base_url, timeout=0.5)
        return None
    except RuntimeError:
        pass

    process = subprocess.Popen(
        _inference_gateway_command(),
        cwd=PROJECT_ROOT,
        env=_build_inference_gateway_env(base_url),
    )

    for _ in range(poll_attempts):
        if process.poll() is not None:
            msg = f"Vizier inference gateway exited before becoming healthy (exit={process.poll()})"
            raise RuntimeError(msg)
        try:
            _require_local_gateway_ready(base_url, timeout=0.5)
            return process
        except RuntimeError:
            time.sleep(poll_interval)

    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)
    msg = f"Vizier inference gateway did not become healthy at {_gateway_health_url(base_url)}"
    raise RuntimeError(msg)


def _stop_local_gateway_process(process: subprocess.Popen[bytes] | None) -> None:
    """Terminate a local inference gateway process started by this launcher."""
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)


def build_gateway_env() -> dict[str, str]:
    """Build the environment for Hermes Telegram runs."""
    ensure_env()
    env = os.environ.copy()
    provider = load_default_provider()
    env.setdefault("HERMES_HOME", str(DEFAULT_HERMES_HOME))
    env.setdefault("HERMES_ENABLE_PROJECT_PLUGINS", "true")
    env.setdefault("MESSAGING_CWD", str(PROJECT_ROOT))
    env.setdefault("HERMES_TOOL_PROGRESS_MODE", "off")
    env.setdefault("HERMES_MODEL", load_default_model())
    env.setdefault("HERMES_INFERENCE_PROVIDER", provider)
    env.setdefault("VIRTUAL_ENV", str(PROJECT_ROOT / ".venv"))
    env.setdefault(
        "PATH",
        f"{PROJECT_ROOT / '.venv' / 'bin'}:{os.environ.get('PATH', os.defpath)}",
    )

    if not env.get("TELEGRAM_BOT_TOKEN"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in the environment")
    provider = str(env.get("HERMES_INFERENCE_PROVIDER", "")).strip().lower()
    base_url = str(env.get("OPENAI_BASE_URL") or load_runtime_base_url()).strip()
    if base_url:
        env.setdefault("OPENAI_BASE_URL", base_url)
        env.setdefault("VIZIER_GATEWAY_BASE_URL", base_url)

    normalized_base_url = base_url.lower()
    if provider == "custom" and _is_local_gateway_url(base_url):
        env["OPENAI_API_KEY"] = "vizier-local-gateway"
        env.pop("VIZIER_UPSTREAM_OPENAI_API_KEY", None)
    if provider == "custom" and "api.openai.com" in normalized_base_url and not env.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required for the configured OpenAI-compatible Hermes endpoint")

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
    base_url = str(env.get("OPENAI_BASE_URL", "")).strip()
    gateway_process = _ensure_local_gateway_process(base_url)
    command = build_gateway_command(args)
    try:
        _require_local_gateway_ready(base_url)
        return subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=True)
    finally:
        _stop_local_gateway_process(gateway_process)


def _launchctl_target() -> str:
    return f"gui/{os.getuid()}"


def _launchctl_service() -> str:
    return f"{_launchctl_target()}/{LAUNCH_AGENT_LABEL}"


def _launch_agent_env() -> dict[str, str]:
    env = build_gateway_env()
    return {
        "PATH": env["PATH"],
        "VIRTUAL_ENV": env["VIRTUAL_ENV"],
        "HERMES_HOME": env["HERMES_HOME"],
        "OPENAI_BASE_URL": env.get("OPENAI_BASE_URL", ""),
        "OPENAI_API_KEY": env.get("OPENAI_API_KEY", ""),
        "HOME": str(Path.home()),
        "PYTHONUNBUFFERED": "1",
    }


def build_launch_agent_plist() -> str:
    """Build a launchd plist that runs this launcher in foreground mode."""
    launch_env = _launch_agent_env()
    env_lines = "\n".join(
        f"        <key>{escape(key)}</key>\n        <string>{escape(value)}</string>"
        for key, value in launch_env.items()
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCH_AGENT_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>{escape(str(PYTHON_BIN))}</string>
        <string>{escape(str(SCRIPT_PATH))}</string>
        <string>run</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{escape(str(PROJECT_ROOT))}</string>

    <key>EnvironmentVariables</key>
    <dict>
{env_lines}
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>{escape(str(DEFAULT_HERMES_HOME / "logs" / "gateway.log"))}</string>

    <key>StandardErrorPath</key>
    <string>{escape(str(DEFAULT_HERMES_HOME / "logs" / "gateway.error.log"))}</string>
</dict>
</plist>
"""


def _launchctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["launchctl", *args],
        cwd=PROJECT_ROOT,
        check=check,
        capture_output=True,
    )


def _write_launch_agent_plist() -> None:
    LAUNCH_AGENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT_PATH.write_text(build_launch_agent_plist(), encoding="utf-8")


def start_service() -> None:
    """Install and start the Vizier-aware launchd service."""
    build_gateway_env()
    _write_launch_agent_plist()
    _launchctl("bootout", _launchctl_target(), str(LAUNCH_AGENT_PATH), check=False)
    _launchctl("bootstrap", _launchctl_target(), str(LAUNCH_AGENT_PATH))
    _launchctl("kickstart", "-k", _launchctl_service())
    print("✓ Updated gateway launchd service definition to use the Vizier launcher")
    print("✓ Service started")


def stop_service() -> None:
    """Stop the Vizier-aware launchd service if it is loaded."""
    _launchctl("bootout", _launchctl_target(), str(LAUNCH_AGENT_PATH), check=False)
    print("✓ Service stopped")


def status_service() -> None:
    """Print launchd status for the Vizier-aware gateway service."""
    print(f"Launchd plist: {LAUNCH_AGENT_PATH}")
    if LAUNCH_AGENT_PATH.is_file():
        if LAUNCH_AGENT_PATH.read_text(encoding="utf-8") == build_launch_agent_plist():
            print("✓ Service definition matches the current Vizier launcher")
        else:
            print("⚠ Service definition is stale relative to the current Vizier launcher")
            print("  Run: scripts/delivery/run_hermes_telegram.py restart")
    else:
        print("⚠ Service definition is missing")

    status = _launchctl("print", _launchctl_service(), check=False)
    if status.returncode == 0:
        print("✓ Gateway service is loaded")
        print(status.stdout.decode("utf-8", errors="replace").strip())
        return

    print("⚠ Gateway service is not loaded")
    stderr = status.stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        print(stderr)


def restart_service() -> None:
    """Restart the Vizier-aware launchd service."""
    stop_service()
    start_service()


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Dispatch foreground and service-management subcommands."""
    args = list(argv or [])
    command = args[0] if args else "run"
    remainder = args[1:] if args else []

    if command in {"run"}:
        run(remainder)
        return 0
    if command in {"start", "install", "setup"}:
        start_service()
        return 0
    if command in {"stop", "uninstall"}:
        stop_service()
        return 0
    if command == "restart":
        restart_service()
        return 0
    if command == "status":
        status_service()
        return 0

    run(args)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""
    return run_cli(argv or sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
