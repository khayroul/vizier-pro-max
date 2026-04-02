"""Tests for Facebook pages adapter."""
from __future__ import annotations

import pytest

from augments.listening.sources.facebook_pages import FacebookPagesAdapter


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "data": [
                {
                    "name": "Batik Co",
                    "link": "https://facebook.com/batik",
                    "fan_count": 123,
                    "about": "Traditional batik craftsmanship",
                }
            ]
        }


class _FakeClient:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def get(self, url: str, params: dict[str, object]) -> _FakeResponse:
        assert params["q"] == "batik"
        return _FakeResponse()


class TestFacebookPagesAdapter:
    def test_searches_pages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FB_ACCESS_TOKEN", "token")
        monkeypatch.setattr("augments.listening.sources.facebook_pages.httpx.Client", _FakeClient)

        items = FacebookPagesAdapter().search(["batik"], geo="MY", language="ms", limit=10)

        assert len(items) == 1
        assert items[0].title == "Batik Co"
        assert items[0].engagement == 123
