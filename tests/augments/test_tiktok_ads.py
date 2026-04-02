"""Tests for TikTok ads adapter."""
from __future__ import annotations

import pytest

from augments.listening.sources.ads.tiktok_ads import TikTokAdsAdapter


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "data": {
                "materials": [
                    {
                        "id": "tk-1",
                        "advertiser_name": "Tok Ma",
                        "video_info": {"cover": "https://example.com/cover.png", "vid_url": "https://example.com/video.mp4"},
                        "landing_page": "https://example.com",
                        "like_count": 10,
                        "play_count": 100,
                        "share_count": 3,
                        "comment_count": 2,
                    }
                ]
            }
        }


class _FakeClient:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def get(self, url: str, params: dict[str, object], headers: dict[str, str]) -> _FakeResponse:
        assert params["keyword"] == "rempah"
        return _FakeResponse()


class TestTikTokAdsAdapter:
    def test_fetches_ads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("augments.listening.sources.ads.tiktok_ads.httpx.Client", _FakeClient)

        ads = TikTokAdsAdapter().fetch(query="rempah")

        assert len(ads) == 1
        assert ads[0].advertiser == "Tok Ma"
        assert ads[0].engagement is not None
        assert ads[0].engagement.views == 100
