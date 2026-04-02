"""Cron-based listening scheduler."""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import structlog
from croniter import croniter

from augments.listening.collector import Collector
from augments.listening.spike_detector import SpikeDetector
from augments.listening.store import ListeningStore
from augments.listening.watchlist import WatchlistConfig

logger = structlog.get_logger(__name__)

ALREADY_RUNNING = "already_running"
_CHECK_INTERVAL = 60


class ListeningScheduler:
    """Daemon scheduler for listening runs."""

    def __init__(
        self,
        store: ListeningStore | None = None,
        collector: Collector | None = None,
        spike_detector: SpikeDetector | None = None,
    ) -> None:
        self._store = store or ListeningStore()
        self._collector = collector or Collector(store=self._store)
        self._detector = spike_detector or SpikeDetector(store=self._store)
        self._running_lock = threading.Lock()
        self._running_watchlists: dict[str, str] = {}
        self._worker_pool = ThreadPoolExecutor(max_workers=3)
        self._stop_event = threading.Event()
        self._daemon_thread: threading.Thread | None = None

    def start(self) -> None:
        if self._daemon_thread and self._daemon_thread.is_alive():
            return
        self._stop_event.clear()
        self._daemon_thread = threading.Thread(target=self._loop, name="listening-scheduler", daemon=True)
        self._daemon_thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def shutdown(self, wait: bool = True) -> None:
        self._stop_event.set()
        self._worker_pool.shutdown(wait=wait)

    def is_watchlist_running(self, watchlist_id: str) -> bool:
        with self._running_lock:
            return watchlist_id in self._running_watchlists

    def run_now(self, watchlist_id: str) -> str:
        with self._running_lock:
            if watchlist_id in self._running_watchlists or self._store.is_watchlist_running(watchlist_id):
                return ALREADY_RUNNING
            run_id = str(uuid.uuid4())
            self._running_watchlists[watchlist_id] = run_id
        try:
            self._execute_run(watchlist_id, run_id)
        finally:
            with self._running_lock:
                self._running_watchlists.pop(watchlist_id, None)
        return run_id

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(timeout=_CHECK_INTERVAL)

    def _tick(self) -> None:
        for watchlist in self._store.list_watchlists(active_only=True):
            if not self._is_due(watchlist):
                continue
            with self._running_lock:
                if watchlist.id in self._running_watchlists or self._store.is_watchlist_running_in_db(watchlist.id):
                    continue
                run_id = str(uuid.uuid4())
                self._running_watchlists[watchlist.id] = run_id
            self._worker_pool.submit(self._execute_run_guarded, watchlist.id, run_id)

    def _is_due(self, watchlist: WatchlistConfig) -> bool:
        now = datetime.now(UTC)
        iterator = croniter(watchlist.schedule, start_time=now)
        previous_run = iterator.get_prev(datetime)
        return (now - previous_run).total_seconds() <= _CHECK_INTERVAL

    def _execute_run_guarded(self, watchlist_id: str, run_id: str) -> None:
        try:
            self._execute_run(watchlist_id, run_id)
        finally:
            with self._running_lock:
                self._running_watchlists.pop(watchlist_id, None)

    def _execute_run(self, watchlist_id: str, run_id: str) -> None:
        watchlist = self._store.get_watchlist(watchlist_id)
        self._store.set_watchlist_running(watchlist_id, True, run_id)
        try:
            results = self._collector.collect(watchlist, run_id)
            self._detector.check(watchlist, results)
        finally:
            self._store.set_watchlist_running(watchlist_id, False, None)
