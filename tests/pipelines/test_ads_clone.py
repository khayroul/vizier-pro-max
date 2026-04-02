"""Tests for ads_clone pipeline."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from augments.listening.watchlist import AdCreative, AdEngagement
from pipelines.ads_clone import run


class _FakeAdapter:
    def __init__(self, ads: list[AdCreative]) -> None:
        self._ads = ads

    def available(self) -> bool:
        return True

    def fetch(
        self,
        query: str,
        country: str = "MY",
        limit: int = 5,
        status: str = "active",
    ) -> list[AdCreative]:
        return self._ads


class _FakeStore:
    def __init__(self) -> None:
        self.saved = []

    def save_ad_creatives(self, ads: list[AdCreative]) -> None:
        self.saved.extend(ads)


def _ads() -> list[AdCreative]:
    return [
        AdCreative(
            platform="tiktok",
            ad_id="1",
            advertiser="A",
            headline=None,
            body=None,
            image_url=None,
            video_url=None,
            landing_url=None,
            spend_range=None,
            impressions_range=None,
            engagement=AdEngagement(likes=1, views=10),
            status="active",
            active=True,
            fetched_at="2026-04-02T00:00:00+00:00",
        ),
        AdCreative(
            platform="tiktok",
            ad_id="2",
            advertiser="B",
            headline=None,
            body=None,
            image_url=None,
            video_url=None,
            landing_url=None,
            spend_range=None,
            impressions_range=None,
            engagement=AdEngagement(likes=5, views=100),
            status="active",
            active=True,
            fetched_at="2026-04-02T00:00:00+00:00",
        ),
    ]


class TestAdsClonePipeline:
    def test_ranks_and_returns_ads(self) -> None:
        fake_store = _FakeStore()
        with (
            patch("pipelines.ads_clone.FacebookAdsAdapter", return_value=_FakeAdapter(_ads())),
            patch("pipelines.ads_clone.ListeningStore", return_value=fake_store),
            patch("pipelines.ads_clone.start_deliverable", return_value="did-1"),
            patch("pipelines.ads_clone.clear_context"),
        ):
            result = run(platform="facebook", query="batik")

        assert result["count"] == 2
        assert result["ads"][0]["ad_id"] == "2"
        assert result["quality_report"]["L1"]["passed"] is True

    def test_invalid_platform_raises(self) -> None:
        try:
            run(platform="instagram", query="batik")
        except ValueError as exc:
            assert "platform" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
