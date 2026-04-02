"""Tests for Facebook ads adapter."""
from __future__ import annotations

import os

import pytest

from augments.listening.sources.ads.facebook_ads import FacebookAdsAdapter


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "data": [
                {
                    "id": "ad-1",
                    "page_name": "Batik Co",
                    "ad_creative_link_titles": ["Promo"],
                    "ad_creative_bodies": ["Body"],
                    "ad_creative_link_captions": ["https://example.com"],
                    "spend": {"lower_bound": "10", "upper_bound": "20", "currency": "MYR"},
                    "impressions": {"lower_bound": "100", "upper_bound": "200"},
                    "ad_delivery_status": "ACTIVE",
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
        assert "search_terms" in params
        return _FakeResponse()


class TestFacebookAdsAdapter:
    def test_fetches_ads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FB_ACCESS_TOKEN", "token")
        monkeypatch.setattr("augments.listening.sources.ads.facebook_ads.httpx.Client", _FakeClient)

        ads = FacebookAdsAdapter().fetch(query="batik")

        assert len(ads) == 1
        assert ads[0].advertiser == "Batik Co"
        assert ads[0].active is True
