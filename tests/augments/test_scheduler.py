"""Tests for listening scheduler."""
from __future__ import annotations

from datetime import UTC, datetime

from augments.listening.scheduler import ALREADY_RUNNING, ListeningScheduler
from augments.listening.watchlist import WatchlistConfig


class _FakeStore:
    def __init__(self) -> None:
        now = datetime.now(UTC).isoformat()
        self.watchlist = WatchlistConfig(
            id="wl-1",
            name="Watchlist",
            client_id=None,
            keywords=("batik",),
            sources=("facebook_pages",),
            schedule="0 * * * *",
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
        self.running = False

    def get_watchlist(self, watchlist_id: str) -> WatchlistConfig:
        return self.watchlist

    def list_watchlists(self, client_id: str | None = None, active_only: bool = True) -> list[WatchlistConfig]:
        return [self.watchlist]

    def is_watchlist_running(self, watchlist_id: str) -> bool:
        return self.running

    def is_watchlist_running_in_db(self, watchlist_id: str) -> bool:
        return self.running

    def set_watchlist_running(self, watchlist_id: str, running: bool, run_id: str | None) -> None:
        self.running = running


class _FakeCollector:
    def __init__(self) -> None:
        self.calls = []

    def collect(self, wl: WatchlistConfig, run_id: str) -> list[object]:
        self.calls.append((wl.id, run_id))
        return []


class _FakeDetector:
    def __init__(self) -> None:
        self.calls = []

    def check(self, wl: WatchlistConfig, results: list[object]) -> list[object]:
        self.calls.append((wl.id, results))
        return []


class TestListeningScheduler:
    def test_run_now_executes_collection(self) -> None:
        store = _FakeStore()
        collector = _FakeCollector()
        detector = _FakeDetector()
        scheduler = ListeningScheduler(store=store, collector=collector, spike_detector=detector)  # type: ignore[arg-type]

        run_id = scheduler.run_now("wl-1")

        assert run_id != ALREADY_RUNNING
        assert len(collector.calls) == 1
        assert len(detector.calls) == 1

    def test_run_now_returns_already_running(self) -> None:
        store = _FakeStore()
        store.running = True
        scheduler = ListeningScheduler(store=store, collector=_FakeCollector(), spike_detector=_FakeDetector())  # type: ignore[arg-type]

        assert scheduler.run_now("wl-1") == ALREADY_RUNNING
