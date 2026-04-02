"""Ads library clone pipeline."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

import structlog

from augments.listening.sources.ads.facebook_ads import FacebookAdsAdapter
from augments.listening.sources.ads.tiktok_ads import TikTokAdsAdapter
from augments.listening.store import ListeningStore
from augments.listening.watchlist import AdCreative
from middleware.deliverable_context import clear_context, start_deliverable
from middleware.pipeline_runner import run_with_gates

logger = structlog.get_logger(__name__)

_PIPELINE_NAME = "ads_clone"

_INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "platform": {"type": "string", "required": True},
    "query": {"type": "string", "required": True},
    "country": {"type": "string", "required": False},
    "limit": {"type": "integer", "required": False},
    "status": {"type": "string", "required": False},
    "client_id": {"type": "string", "required": False},
}

_OUTPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "ads": {"type": "array", "required": True},
    "count": {"type": "integer", "required": True},
    "status": {"type": "string", "required": True},
    "deliverable_id": {"type": "string", "required": True},
}


def _rank_score(ad: AdCreative) -> int:
    if ad.engagement is None:
        return 0
    return ad.engagement.views + ad.engagement.likes + ad.engagement.shares + ad.engagement.comments


def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
    platform = str(inputs["platform"])
    query = str(inputs["query"])
    country = str(inputs.get("country", "MY"))
    limit = int(inputs.get("limit", 5))
    status = str(inputs.get("status", "active"))
    client_id = str(inputs.get("client_id", "")) or None

    did = start_deliverable(client_id=client_id)
    try:
        adapter = FacebookAdsAdapter() if platform == "facebook" else TikTokAdsAdapter()
        if not adapter.available():
            return {"ads": [], "count": 0, "status": "unavailable", "deliverable_id": did}

        ads = adapter.fetch(query=query, country=country, limit=limit, status=status)
        ranked = sorted(ads, key=_rank_score, reverse=True)
        ListeningStore().save_ad_creatives(ranked)
        return {
            "ads": [_ad_to_dict(ad) for ad in ranked],
            "count": len(ranked),
            "status": "completed",
            "deliverable_id": did,
        }
    finally:
        clear_context()


def run(
    *,
    platform: str,
    query: str,
    country: str = "MY",
    limit: int = 5,
    status: str = "active",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Run the ads clone pipeline."""
    if platform not in {"facebook", "tiktok"}:
        raise ValueError("platform must be 'facebook' or 'tiktok'")

    return run_with_gates(
        pipeline_fn=_pipeline_fn,
        inputs={
            "platform": platform,
            "query": query,
            "country": country,
            "limit": limit,
            "status": status,
            **({"client_id": client_id} if client_id is not None else {}),
        },
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name=_PIPELINE_NAME,
    )


def _ad_to_dict(ad: AdCreative) -> dict[str, object]:
    data = asdict(ad)
    return data
