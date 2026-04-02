"""Tests for scripts/research/yt_transcript.py."""
from __future__ import annotations

import sys
import types

import pytest


class _NoTranscriptFound(Exception):
    pass


class _TranscriptsDisabled(Exception):
    pass


class _FakeTranscriptApi:
    @staticmethod
    def get_transcript(video_id: str, languages: list[str]) -> list[dict[str, object]]:
        if video_id == "manual123":
            return [{"start": 0.0, "duration": 1.0, "text": "hello"}]
        if video_id == "auto456":
            raise _NoTranscriptFound()
        raise RuntimeError("boom")


class _FakeYoutubeDL:
    def __init__(self, _opts: dict[str, object]) -> None:
        self.opts = _opts

    def __enter__(self) -> "_FakeYoutubeDL":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def extract_info(self, _url: str, download: bool = False) -> dict[str, object]:
        assert download is False
        return {
            "automatic_captions": {
                "en": [{"ext": "json3", "url": "https://example.com/captions.json3"}]
            }
        }


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {
            "events": [
                {"tStartMs": 0, "dDurationMs": 1000, "segs": [{"utf8": "hello"}]},
                {"tStartMs": 1000, "dDurationMs": 1000, "segs": [{"utf8": "world"}]},
            ]
        }


class TestYtTranscript:
    def test_fetches_manual_transcript(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_module = types.SimpleNamespace(
            NoTranscriptFound=_NoTranscriptFound,
            TranscriptsDisabled=_TranscriptsDisabled,
            YouTubeTranscriptApi=_FakeTranscriptApi,
        )
        monkeypatch.setitem(sys.modules, "youtube_transcript_api", fake_module)

        from scripts.research.yt_transcript import run

        result = run(video_ids=["manual123"])

        assert len(result["transcripts"]) == 1
        assert result["transcripts"][0]["source"] == "manual"
        assert result["failed"] == []

    def test_falls_back_to_auto_captions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_transcript_module = types.SimpleNamespace(
            NoTranscriptFound=_NoTranscriptFound,
            TranscriptsDisabled=_TranscriptsDisabled,
            YouTubeTranscriptApi=_FakeTranscriptApi,
        )
        monkeypatch.setitem(sys.modules, "youtube_transcript_api", fake_transcript_module)
        monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL))

        import scripts.research.yt_transcript as yt_transcript

        monkeypatch.setattr(yt_transcript.httpx, "get", lambda url, timeout=10: _FakeResponse())

        result = yt_transcript.run(video_ids=["auto456"], languages=["en"])

        assert len(result["transcripts"]) == 1
        assert result["transcripts"][0]["source"] == "auto"
        assert result["transcripts"][0]["full_text"] == "hello world"

    def test_records_failures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_module = types.SimpleNamespace(
            NoTranscriptFound=_NoTranscriptFound,
            TranscriptsDisabled=_TranscriptsDisabled,
            YouTubeTranscriptApi=_FakeTranscriptApi,
        )
        monkeypatch.setitem(sys.modules, "youtube_transcript_api", fake_module)

        from scripts.research.yt_transcript import run

        result = run(video_ids=["broken789"], fallback_auto=False)

        assert result["transcripts"] == []
        assert result["failed"][0]["video_id"] == "broken789"

    def test_requires_video_ids(self) -> None:
        from scripts.research.yt_transcript import run

        with pytest.raises(ValueError, match="video_ids is required"):
            run(video_ids=[])
