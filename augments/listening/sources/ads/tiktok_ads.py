"""TikTok Creative Center adapter."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import httpx
import structlog

from augments.listening.watchlist import AdCreative, AdEngagement

logger = structlog.get_logger(__name__)

_TOP_ADS_URL = "https://ads.tiktok.com/creative_radar_api/v1/top_ads/list"


class TikTokAdsAdapter:
    name: ClassVar[str] = "tiktok_ads"

    def available(self) -> bool:
        return True

    def fetch(
        self,
        query: str,
        country: str = "MY",
        limit: int = 5,
        status: str = "active",
    ) -> list[AdCreative]:
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    _TOP_ADS_URL,
                    params={
                        "keyword": query,
                        "country_code": country,
                        "period": 7,
                        "order_by": "reach",
                        "page": 1,
                        "page_size": min(limit, 20),
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                response.raise_for_status()
        except (httpx.HTTPError, httpx.RequestError) as exc:
            logger.warning("tiktok_ads fetch failed", query=query, error=str(exc))
            return []

        payload = response.json().get("data", {})
        if not isinstance(payload, dict):
            return []
        materials = payload.get("materials", [])
        if not isinstance(materials, list):
            return []
        fetched_at = datetime.now(UTC).isoformat()
        return [_parse_tiktok_ad(material, fetched_at) for material in materials if isinstance(material, dict)]


def _parse_tiktok_ad(material: dict[str, object], fetched_at: str) -> AdCreative:
    video_info = material.get("video_info")
    video_dict = video_info if isinstance(video_info, dict) else {}
    return AdCreative(
        platform="tiktok",
        ad_id=str(material.get("id", "")),
        advertiser=str(material.get("advertiser_name", "")),
        headline=None,
        body=None,
        image_url=str(video_dict.get("cover")) if video_dict.get("cover") else None,
        video_url=str(video_dict.get("vid_url")) if video_dict.get("vid_url") else None,
        landing_url=str(material.get("landing_page")) if material.get("landing_page") else None,
        spend_range=None,
        impressions_range=None,
        engagement=AdEngagement(
            likes=int(material.get("like_count", 0)),
            views=int(material.get("play_count", 0)),
            shares=int(material.get("share_count", 0)),
            comments=int(material.get("comment_count", 0)),
        ),
        status="active",
        active=True,
        fetched_at=fetched_at,
    )
