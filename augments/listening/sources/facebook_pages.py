"""Facebook Pages adapter."""
from __future__ import annotations

import os
from typing import ClassVar

import httpx
import structlog

from augments.listening.watchlist import ListeningItem

logger = structlog.get_logger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v19.0"


class FacebookPagesAdapter:
    name: ClassVar[str] = "facebook_pages"

    def available(self) -> bool:
        return bool(os.environ.get("FB_ACCESS_TOKEN"))

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]:
        token = os.environ.get("FB_ACCESS_TOKEN", "")
        items: list[ListeningItem] = []
        with httpx.Client(timeout=30.0) as client:
            for keyword in keywords:
                try:
                    response = client.get(
                        f"{_GRAPH_BASE}/pages/search",
                        params={
                            "q": keyword,
                            "limit": min(limit, 25),
                            "access_token": token,
                            "fields": "id,name,link,fan_count,about",
                        },
                    )
                    response.raise_for_status()
                except (httpx.HTTPError, httpx.RequestError) as exc:
                    logger.warning("facebook_pages request failed", keyword=keyword, error=str(exc))
                    continue
                payload = response.json().get("data", [])
                if not isinstance(payload, list):
                    continue
                for page in payload:
                    if not isinstance(page, dict):
                        continue
                    items.append(
                        ListeningItem(
                            source="facebook_pages",
                            url=str(page.get("link")) if page.get("link") else None,
                            title=str(page.get("name", "")),
                            snippet=str(page.get("about", ""))[:300],
                            score=0.4,
                            engagement=int(page.get("fan_count", 0)),
                            published_at=None,
                        )
                    )
        return items
