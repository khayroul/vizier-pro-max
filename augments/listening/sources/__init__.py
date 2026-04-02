"""Listening source adapter protocol and registry helpers."""
from __future__ import annotations

from typing import ClassVar, Protocol

from augments.listening.watchlist import ListeningItem

VALID_SOURCES: frozenset[str] = frozenset(
    {
        "reddit",
        "x",
        "youtube",
        "tiktok",
        "instagram",
        "web",
        "threads",
        "facebook_pages",
        "facebook_groups",
        "google_trends",
    }
)

LAST30DAYS_SOURCES: frozenset[str] = frozenset(
    {"reddit", "x", "youtube", "tiktok", "instagram", "web"}
)


class SourceAdapter(Protocol):
    name: ClassVar[str]

    def search(
        self,
        keywords: list[str],
        geo: str,
        language: str,
        limit: int,
    ) -> list[ListeningItem]: ...

    def available(self) -> bool: ...


def build_direct_adapters() -> dict[str, SourceAdapter]:
    """Build the default direct adapter registry."""
    from augments.listening.sources.facebook_groups import FacebookGroupsAdapter
    from augments.listening.sources.facebook_pages import FacebookPagesAdapter
    from augments.listening.sources.google_trends import GoogleTrendsAdapter
    from augments.listening.sources.threads import ThreadsAdapter

    adapters: tuple[SourceAdapter, ...] = (
        FacebookPagesAdapter(),
        FacebookGroupsAdapter(),
        GoogleTrendsAdapter(),
        ThreadsAdapter(),
    )
    return {adapter.name: adapter for adapter in adapters}
