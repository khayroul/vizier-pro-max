"""Threads search adapter."""
from __future__ import annotations

import os
from typing import ClassVar

import httpx
import structlog

from augments.listening.watchlist import ListeningItem

logger = structlog.get_logger(__name__)

_BASE_URL = "https://graph.threads.net/v1.0"


class ThreadsAdapter:
    name: ClassVar[str] = "threads"

    def available(self) -> bool:
        return bool(os.environ.get("THREADS_ACCESS_TOKEN"))

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]:
        token = os.environ.get("THREADS_ACCESS_TOKEN", "")
        items: list[ListeningItem] = []
        with httpx.Client(timeout=30.0) as client:
            for keyword in keywords:
                try:
                    response = client.get(
                        f"{_BASE_URL}/search",
                        params={
                            "q": keyword,
                            "limit": min(limit, 50),
                            "access_token": token,
                            "fields": "id,text,timestamp,permalink,like_count",
                        },
                    )
                    response.raise_for_status()
                except (httpx.HTTPError, httpx.RequestError) as exc:
                    logger.warning("threads request failed", keyword=keyword, error=str(exc))
                    continue
                payload = response.json().get("data", [])
                if not isinstance(payload, list):
                    continue
                for post in payload:
                    if not isinstance(post, dict):
                        continue
                    text = str(post.get("text", ""))
                    items.append(
                        ListeningItem(
                            source="threads",
                            url=str(post.get("permalink")) if post.get("permalink") else None,
                            title=text[:120],
                            snippet=text[:300],
                            score=0.5,
                            engagement=int(post.get("like_count", 0)),
                            published_at=str(post.get("timestamp")) if post.get("timestamp") else None,
                        )
                    )
        return items
