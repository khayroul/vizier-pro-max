"""Tests for Google Trends adapter."""
from __future__ import annotations

import pytest

from augments.listening.sources.google_trends import GoogleTrendsAdapter


class TestGoogleTrendsAdapter:
    def test_search_uses_fetch_helper(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("augments.listening.sources.google_trends._PYTRENDS_AVAILABLE", True)
        monkeypatch.setattr(
            "augments.listening.sources.google_trends._fetch_trend_data",
            lambda keyword, geo: (80, 55.0, "2026-04-02T00:00:00+00:00"),
        )

        items = GoogleTrendsAdapter().search(["batik"], geo="MY", language="ms", limit=10)

        assert len(items) == 1
        assert items[0].engagement == 80
        assert "batik" in items[0].title.lower()
