"""Run the local Vizier inference gateway."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from adapter.env_loader import ensure_env
from middleware.inference_gateway import default_gateway_base_url, serve

_GATEWAY_OVERRIDE_KEYS = frozenset({
    "OPENAI_API_KEY",
    "VIZIER_UPSTREAM_OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "FAL_KEY",
    "ELEVENLABS_API_KEY",
    "GAMMA_API_KEY",
})


def _host_and_port_from_base_url(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11436
    return host, port


def _prepare_gateway_env() -> None:
    """Load repo env and normalize the upstream provider key for the gateway only."""
    ensure_env(override_keys=_GATEWAY_OVERRIDE_KEYS)
    upstream_key = os.environ.get("VIZIER_UPSTREAM_OPENAI_API_KEY", "").strip()
    legacy_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not upstream_key and legacy_key:
        os.environ["VIZIER_UPSTREAM_OPENAI_API_KEY"] = legacy_key
    os.environ.pop("OPENAI_API_KEY", None)


def main() -> int:
    """CLI entrypoint."""
    _prepare_gateway_env()
    base_url = os.environ.get("VIZIER_GATEWAY_BASE_URL", default_gateway_base_url())
    host, port = _host_and_port_from_base_url(base_url)
    serve(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
