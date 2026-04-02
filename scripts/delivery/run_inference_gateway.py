"""Run the local Vizier inference gateway."""
from __future__ import annotations

import os
from urllib.parse import urlparse

from adapter.env_loader import ensure_env
from middleware.inference_gateway import default_gateway_base_url, serve


def _host_and_port_from_base_url(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11436
    return host, port


def main() -> int:
    """CLI entrypoint."""
    ensure_env()
    base_url = os.environ.get("VIZIER_GATEWAY_BASE_URL", default_gateway_base_url())
    host, port = _host_and_port_from_base_url(base_url)
    serve(host=host, port=port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
