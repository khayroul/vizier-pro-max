"""Fetch a URL via httpx and return structured response."""
from __future__ import annotations

import httpx


def fetch(url: str, method: str = "GET") -> dict[str, object]:
    """Fetch a URL and return status + body.

    Args:
        url: URL to fetch.
        method: HTTP method.

    Returns:
        Dict with status_code and body.
    """
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, url)
        return {
            "status_code": response.status_code,
            "body": response.text[:10000],
        }
