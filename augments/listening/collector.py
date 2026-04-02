"""Listening collection orchestration."""
from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Protocol

import structlog

from adapter.llm_client import chat as llm_chat
from augments.listening.sources import LAST30DAYS_SOURCES, build_direct_adapters
from augments.listening.sources.last30days import Last30DaysAdapter
from augments.listening.store import ListeningStore
from augments.listening.watchlist import ListeningItem, ListeningResult, WatchlistConfig

logger = structlog.get_logger(__name__)

_MAX_WORKERS = 4


class _AdapterLike(Protocol):
    def available(self) -> bool: ...

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]: ...


class Collector:
    """Collect listening data from configured sources."""

    def __init__(
        self,
        store: ListeningStore | None = None,
        last30days_adapter: Last30DaysAdapter | None = None,
        direct_adapters: dict[str, _AdapterLike] | None = None,
        limit_per_keyword: int = 20,
    ) -> None:
        self._store = store or ListeningStore()
        self._last30 = last30days_adapter or Last30DaysAdapter()
        self._direct_adapters = direct_adapters or build_direct_adapters()
        self._limit = limit_per_keyword

    def collect(self, watchlist: WatchlistConfig, run_id: str) -> list[ListeningResult]:
        """Collect and persist results for a watchlist."""
        sources = set(watchlist.sources)
        batched_sources = sorted(sources & LAST30DAYS_SOURCES)
        direct_sources = sorted(sources - LAST30DAYS_SOURCES)
        results: list[ListeningResult] = []

        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {}
            if batched_sources and self._last30.available():
                futures[pool.submit(self._run_last30days, watchlist, run_id, batched_sources)] = "last30days"
            for source in direct_sources:
                adapter = self._direct_adapters.get(source)
                if adapter is None or not adapter.available():
                    continue
                futures[pool.submit(self._run_direct, adapter, watchlist, run_id, source)] = source

            for future in as_completed(futures):
                try:
                    results.extend(future.result())
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Collector worker failed", source=futures[future], error=str(exc))

        return results

    def _run_last30days(
        self,
        watchlist: WatchlistConfig,
        run_id: str,
        sources: list[str],
    ) -> list[ListeningResult]:
        items = self._last30.search(
            list(watchlist.keywords),
            geo=watchlist.geo,
            language=watchlist.language,
            limit=self._limit,
            sources=sources,
        )
        results: list[ListeningResult] = []
        for source in sources:
            source_items = [item for item in items if item.source == source]
            for keyword in watchlist.keywords:
                filtered = tuple(
                    item for item in source_items if keyword.lower() in f"{item.title} {item.snippet}".lower()
                ) or tuple(source_items)
                results.append(self._persist_result(watchlist.id, run_id, source, keyword, _deduplicate(filtered)))
        return results

    def _run_direct(
        self,
        adapter: _AdapterLike,
        watchlist: WatchlistConfig,
        run_id: str,
        source: str,
    ) -> list[ListeningResult]:
        items = adapter.search(
            list(watchlist.keywords),
            geo=watchlist.geo,
            language=watchlist.language,
            limit=self._limit,
        )
        results: list[ListeningResult] = []
        for keyword in watchlist.keywords:
            filtered = tuple(
                item for item in items if keyword.lower() in f"{item.title} {item.snippet}".lower()
            ) or tuple(items)
            results.append(self._persist_result(watchlist.id, run_id, source, keyword, _deduplicate(filtered)))
        return results

    def _persist_result(
        self,
        watchlist_id: str,
        run_id: str,
        source: str,
        keyword: str,
        items: tuple[ListeningItem, ...],
    ) -> ListeningResult:
        result = ListeningResult(
            id=str(uuid.uuid4()),
            watchlist_id=watchlist_id,
            run_id=run_id,
            source=source,
            keyword=keyword,
            timestamp=datetime.now(UTC).isoformat(),
            items=items,
            summary=_summarise(keyword, source, items),
            volume=len(items),
            status="ok",
        )
        self._store.write_result(result)
        return result


def _deduplicate(items: tuple[ListeningItem, ...]) -> tuple[ListeningItem, ...]:
    """Keep the highest-scoring item per URL."""
    seen: dict[str, ListeningItem] = {}
    no_url: list[ListeningItem] = []
    for item in items:
        if item.url is None:
            no_url.append(item)
            continue
        if item.url not in seen or item.score > seen[item.url].score:
            seen[item.url] = item
    return tuple(seen.values()) + tuple(no_url)


def _summarise(keyword: str, source: str, items: tuple[ListeningItem, ...]) -> str:
    """Generate a short markdown summary, using LLM when available."""
    if not items:
        return f"### {source}\n\nNo items found for `{keyword}`."

    snippet_lines = "\n".join(
        f"- {item.title}: {item.snippet[:140]}" for item in items[:5]
    )
    response = llm_chat(
        messages=[
            {
                "role": "system",
                "content": "Summarize listening items in 2-3 concise markdown bullet points. Output only markdown.",
            },
            {
                "role": "user",
                "content": f"Keyword: {keyword}\nSource: {source}\nItems:\n{snippet_lines}",
            },
        ],
        max_tokens=180,
        strip_preamble=True,
    )
    if response:
        return response
    return f"### {source}\n\n{snippet_lines}"
