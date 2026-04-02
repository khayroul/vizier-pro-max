"""Tests for spike detector."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from augments.listening.spike_detector import SpikeDetector
from augments.listening.watchlist import ListeningItem, ListeningResult, SpikeAlert, WatchlistConfig


class _FakeStore:
    def __init__(self, baseline: float = 0.0, alerts: list[SpikeAlert] | None = None) -> None:
        self.baseline = baseline
        self.alerts = alerts or []
        self.saved: list[SpikeAlert] = []

    def get_baseline_volume(self, watchlist_id: str, keyword: str, source: str) -> float:
        return self.baseline

    def get_spike_alerts(self, watchlist_id: str, keyword: str, source: str) -> list[SpikeAlert]:
        return self.alerts

    def write_spike_alert(self, alert: SpikeAlert) -> None:
        self.saved.append(alert)


class _FakeClient:
    def __init__(self, timeout: float) -> None:
        self.timeout = timeout
        self.posts = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def post(self, url: str, json: dict[str, object]) -> "_FakeResponse":
        self.posts.append((url, json))
        return _FakeResponse()


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


def _watchlist() -> WatchlistConfig:
    now = datetime.now(UTC).isoformat()
    return WatchlistConfig(
        id="wl-1",
        name="Watchlist",
        client_id=None,
        keywords=("batik",),
        sources=("facebook_pages",),
        schedule="0 8 * * *",
        geo="MY",
        language="ms",
        spike_threshold=2.0,
        alert_cooldown_hours=24,
        alert_webhooks=("https://example.com/hook",),
        webhook_type="generic",
        active=True,
        created_at=now,
        updated_at=now,
    )


def _result(volume: int) -> ListeningResult:
    item = ListeningItem(
        source="facebook_pages",
        url="https://example.com/a",
        title="Title",
        snippet="Snippet",
        score=0.8,
        engagement=10,
        published_at=None,
    )
    return ListeningResult(
        id="res-1",
        watchlist_id="wl-1",
        run_id="run-1",
        source="facebook_pages",
        keyword="batik",
        timestamp="2026-04-02T00:00:00+00:00",
        items=(item,),
        summary="summary",
        volume=volume,
        status="ok",
    )


class TestSpikeDetector:
    def test_fires_alert_when_threshold_exceeded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        store = _FakeStore(baseline=2.0)
        monkeypatch.setattr("augments.listening.spike_detector.httpx.Client", _FakeClient)

        detector = SpikeDetector(store=store)  # type: ignore[arg-type]
        alerts = detector.check(_watchlist(), [_result(6)])

        assert len(alerts) == 1
        assert store.saved[0].alert_sent is True

    def test_skips_when_baseline_zero(self) -> None:
        store = _FakeStore(baseline=0.0)
        detector = SpikeDetector(store=store)  # type: ignore[arg-type]

        assert detector.check(_watchlist(), [_result(6)]) == []
