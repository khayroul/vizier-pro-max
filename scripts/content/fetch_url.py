"""Fetch a URL via httpx and return structured response."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

_ALLOWED_SCHEMES = {"http", "https"}
_ALLOWED_METHODS = {"GET", "HEAD"}


def _validate_url(url: str) -> None:
    """Validate URL scheme and resolved IP to prevent SSRF.

    Args:
        url: The URL to validate.

    Raises:
        ValueError: If the URL has a disallowed scheme, resolves to a
            private/loopback/link-local IP, or cannot be resolved.
    """
    parsed = urlparse(url)

    if parsed.scheme not in _ALLOWED_SCHEMES:
        msg = (
            f"Disallowed URL scheme: {parsed.scheme!r}."
            f" Only {sorted(_ALLOWED_SCHEMES)} allowed."
        )
        raise ValueError(msg)

    hostname = parsed.hostname
    if not hostname:
        msg = "URL has no hostname"
        raise ValueError(msg)

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        msg = f"Cannot resolve hostname {hostname!r}: {exc}"
        raise ValueError(msg) from exc

    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        ip_addr = ipaddress.ip_address(ip_str)
        if ip_addr.is_private or ip_addr.is_loopback or ip_addr.is_link_local:
            msg = f"URL resolves to disallowed IP: {ip_str}"
            raise ValueError(msg)


def fetch(url: str, method: str = "GET") -> dict[str, object]:
    """Fetch a URL and return status + body.

    Args:
        url: URL to fetch.
        method: HTTP method (GET or HEAD only).

    Returns:
        Dict with status_code and body.

    Raises:
        ValueError: If URL fails SSRF validation or method is disallowed.
    """
    upper_method = method.upper()
    if upper_method not in _ALLOWED_METHODS:
        msg = (
            f"Disallowed HTTP method: {method!r}."
            f" Only {sorted(_ALLOWED_METHODS)} allowed."
        )
        raise ValueError(msg)

    _validate_url(url)

    with httpx.Client(timeout=10.0) as client:
        response = client.request(upper_method, url)
        return {
            "status_code": response.status_code,
            "body": response.text[:10000],
        }
