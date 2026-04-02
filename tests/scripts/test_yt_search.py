"""Tests for scripts/research/yt_search.py."""
from __future__ import annotations

import sys
import types

import pytest


class _FakeYoutubeDL:
    def __init__(self, _opts: dict[str, object]) -> None:
        self.opts = _opts

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def extract_info(self, _query: str, download: bool = False) -> dict[str, object]:
        assert download is False
        return {
            "entries": [
                {
                    "id": "abc123",
                    "title": "Fresh Video",
                    "channel": "Vizier",
                    "upload_date": "29990101",
                    "view_count": 42,
                    "duration": 120,
                    "description": "desc",
                    "url": "https://youtube.com/watch?v=abc123",
                },
                {
                    "id": "old999",
                    "title": "Old Video",
                    "channel": "Vizier",
                    "upload_date": "20000101",
                    "view_count": 10,
                    "duration": 120,
                    "description": "old",
                    "url": "https://youtube.com/watch?v=old999",
                },
            ]
        }


class TestYtSearch:
    def test_returns_filtered_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))

        from scripts.research.yt_search import run

        result = run(query="batik", date_filter="this_week")

        assert result["query"] == "batik"
        assert result["result_count"] == 1
        assert result["results"][0]["video_id"] == "abc123"

    def test_rejects_unknown_date_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))

        from scripts.research.yt_search import run

        with pytest.raises(ValueError, match="Unsupported date_filter"):
            run(query="batik", date_filter="yesterday")

    def test_requires_query(self) -> None:
        from scripts.research.yt_search import run

        with pytest.raises(ValueError, match="query is required"):
            run(query="")
