"""Tests for listening collector."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

from augments.listening.collector import Collector
from augments.listening.watchlist import ListeningItem, WatchlistConfig


class _FakeStore:
    def __init__(self) -> None:
        self.results = []

    def write_result(self, result: object) -> None:
        self.results.append(result)


class _FakeLast30Adapter:
    def available(self) -> bool:
        return True

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
        sources: list[str] | None = None,
    ) -> list[ListeningItem]:
        return [
            ListeningItem(
                source=sources[0] if sources else "reddit",
                url="https://example.com/a",
                title=f"{keywords[0]} title",
                snippet="snippet",
                score=0.8,
                engagement=10,
                published_at=None,
            )
        ]


class _FakeDirectAdapter:
    def available(self) -> bool:
        return True

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]:
        return [
            ListeningItem(
                source="facebook_pages",
                url="https://example.com/b",
                title=f"{keywords[0]} page",
                snippet="snippet",
                score=0.9,
                engagement=20,
                published_at=None,
            )
        ]


def _watchlist() -> WatchlistConfig:
    now = datetime.now(UTC).isoformat()
    return WatchlistConfig(
        id="wl-1",
        name="Watchlist",
        client_id=None,
        keywords=("batik",),
        sources=("reddit", "facebook_pages"),
        schedule="0 8 * * *",
        geo="MY",
        language="ms",
        spike_threshold=2.0,
        alert_cooldown_hours=24,
        alert_webhooks=(),
        webhook_type="generic",
        active=True,
        created_at=now,
        updated_at=now,
    )


class TestCollector:
    def test_collects_and_persists_results(self) -> None:
        store = _FakeStore()
        collector = Collector(
            store=store,  # type: ignore[arg-type]
            last30days_adapter=_FakeLast30Adapter(),  # type: ignore[arg-type]
            direct_adapters={"facebook_pages": _FakeDirectAdapter()},  # type: ignore[arg-type]
        )

        with patch("augments.listening.collector.llm_chat", return_value=None):
            results = collector.collect(_watchlist(), "run-1")

        assert len(results) == 2
        assert len(store.results) == 2
        assert all(result.volume == 1 for result in results)
