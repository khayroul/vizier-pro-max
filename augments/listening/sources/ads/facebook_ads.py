"""Facebook Ads Library adapter."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import ClassVar

import httpx
import structlog

from augments.listening.watchlist import AdCreative

logger = structlog.get_logger(__name__)

_ADS_ARCHIVE_URL = "https://graph.facebook.com/v19.0/ads_archive"


class FacebookAdsAdapter:
    name: ClassVar[str] = "facebook_ads"

    def available(self) -> bool:
        return bool(os.environ.get("FB_ACCESS_TOKEN"))

    def fetch(
        self,
        query: str,
        country: str = "MY",
        limit: int = 5,
        status: str = "active",
    ) -> list[AdCreative]:
        token = os.environ.get("FB_ACCESS_TOKEN", "")
        active_status = "ACTIVE" if status == "active" else "ALL"
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(
                    _ADS_ARCHIVE_URL,
                    params={
                        "search_terms": query,
                        "ad_reached_countries": f'["{country}"]',
                        "ad_active_status": active_status,
                        "limit": min(limit, 20),
                        "access_token": token,
                        "fields": (
                            "id,page_name,ad_creative_link_titles,"
                            "ad_creative_bodies,ad_creative_link_captions,"
                            "ad_snapshot_url,spend,impressions,ad_delivery_status"
                        ),
                    },
                )
                response.raise_for_status()
        except (httpx.HTTPError, httpx.RequestError) as exc:
            logger.warning("facebook_ads fetch failed", query=query, error=str(exc))
            return []

        payload = response.json().get("data", [])
        if not isinstance(payload, list):
            return []
        fetched_at = datetime.now(UTC).isoformat()
        return [_parse_facebook_ad(entry, fetched_at) for entry in payload if isinstance(entry, dict)]


def _parse_facebook_ad(entry: dict[str, object], fetched_at: str) -> AdCreative:
    titles = entry.get("ad_creative_link_titles")
    bodies = entry.get("ad_creative_bodies")
    captions = entry.get("ad_creative_link_captions")
    titles_list = titles if isinstance(titles, list) else []
    bodies_list = bodies if isinstance(bodies, list) else []
    captions_list = captions if isinstance(captions, list) else []
    spend = entry.get("spend")
    spend_dict = spend if isinstance(spend, dict) else {}
    impressions = entry.get("impressions")
    impressions_dict = impressions if isinstance(impressions, dict) else {}

    spend_range = None
    if "lower_bound" in spend_dict:
        spend_range = f"{spend_dict.get('lower_bound')}-{spend_dict.get('upper_bound')} {spend_dict.get('currency', '')}".strip()

    impressions_range = None
    if "lower_bound" in impressions_dict:
        impressions_range = f"{impressions_dict.get('lower_bound')}-{impressions_dict.get('upper_bound')}"

    is_active = str(entry.get("ad_delivery_status", "")).upper() == "ACTIVE"
    return AdCreative(
        platform="facebook",
        ad_id=str(entry.get("id", "")),
        advertiser=str(entry.get("page_name", "")),
        headline=str(titles_list[0]) if titles_list else None,
        body=str(bodies_list[0]) if bodies_list else None,
        image_url=None,
        video_url=None,
        landing_url=str(captions_list[0]) if captions_list else None,
        spend_range=spend_range,
        impressions_range=impressions_range,
        engagement=None,
        status="active" if is_active else "inactive",
        active=is_active,
        fetched_at=fetched_at,
    )
