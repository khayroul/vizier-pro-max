"""Facebook Groups adapter."""
from __future__ import annotations

import os
from typing import ClassVar

import httpx
import structlog

from augments.listening.watchlist import ListeningItem

logger = structlog.get_logger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_GROUP_PREFIX = "group:"


class FacebookGroupsAdapter:
    name: ClassVar[str] = "facebook_groups"

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
        group_ids = [keyword[len(_GROUP_PREFIX) :] for keyword in keywords if keyword.startswith(_GROUP_PREFIX)]
        if not group_ids:
            return []

        items: list[ListeningItem] = []
        with httpx.Client(timeout=30.0) as client:
            for group_id in group_ids:
                try:
                    response = client.get(
                        f"{_GRAPH_BASE}/groups/{group_id}/feed",
                        params={
                            "limit": min(limit, 25),
                            "access_token": token,
                            "fields": "id,message,created_time,permalink_url,likes.summary(true)",
                        },
                    )
                    response.raise_for_status()
                except (httpx.HTTPError, httpx.RequestError) as exc:
                    logger.warning("facebook_groups request failed", group_id=group_id, error=str(exc))
                    continue
                payload = response.json().get("data", [])
                if not isinstance(payload, list):
                    continue
                for post in payload:
                    if not isinstance(post, dict):
                        continue
                    likes = 0
                    raw_likes = post.get("likes")
                    if isinstance(raw_likes, dict):
                        summary = raw_likes.get("summary")
                        if isinstance(summary, dict):
                            likes = int(summary.get("total_count", 0))
                    message = str(post.get("message", ""))
                    items.append(
                        ListeningItem(
                            source="facebook_groups",
                            url=str(post.get("permalink_url")) if post.get("permalink_url") else None,
                            title=message[:120],
                            snippet=message[:300],
                            score=0.5,
                            engagement=likes,
                            published_at=str(post.get("created_time")) if post.get("created_time") else None,
                        )
                    )
        return items
