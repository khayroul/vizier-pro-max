"""Google Trends adapter."""
from __future__ import annotations

from typing import ClassVar

import structlog

from augments.listening.watchlist import ListeningItem

logger = structlog.get_logger(__name__)

try:
    from pytrends.request import TrendReq  # type: ignore[import-untyped]

    _PYTRENDS_AVAILABLE = True
except ImportError:
    TrendReq = None  # type: ignore[assignment]
    _PYTRENDS_AVAILABLE = False


def _fetch_trend_data(keyword: str, geo: str) -> tuple[int, float, str] | None:
    """Fetch interest-over-time data for a keyword."""
    if not _PYTRENDS_AVAILABLE:
        return None
    try:
        trend = TrendReq(hl="en-US", tz=480)  # type: ignore[operator]
        trend.build_payload([keyword], geo=geo, timeframe="now 7-d")  # type: ignore[union-attr]
        frame = trend.interest_over_time()  # type: ignore[union-attr]
        if frame.empty or keyword not in frame.columns:
            return None
        latest = int(frame[keyword].iloc[-1])
        average = float(frame[keyword].mean())
        published_at = str(frame.index[-1])
        return latest, average, published_at
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        logger.warning("google_trends fetch failed", keyword=keyword, error=str(exc))
        return None


class GoogleTrendsAdapter:
    name: ClassVar[str] = "google_trends"

    def available(self) -> bool:
        return _PYTRENDS_AVAILABLE

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]:
        items: list[ListeningItem] = []
        for keyword in keywords:
            result = _fetch_trend_data(keyword, geo)
            if result is None:
                continue
            latest, average, published_at = result
            items.append(
                ListeningItem(
                    source="google_trends",
                    url=f"https://trends.google.com/trends/explore?q={keyword}&geo={geo}",
                    title=f"Google Trends: {keyword}",
                    snippet=f"Interest score {latest}/100 (7d avg: {average:.1f}) in {geo}",
                    score=round(min(latest / 100.0, 1.0), 4),
                    engagement=latest,
                    published_at=published_at,
                )
            )
        return items
