"""Tests for listening store."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from augments.listening.store import ListeningStore
from augments.listening.watchlist import (
    AdCreative,
    AdEngagement,
    ListeningItem,
    ListeningResult,
    SpikeAlert,
    WatchlistConfig,
)


def _watchlist() -> WatchlistConfig:
    now = datetime.now(UTC).isoformat()
    return WatchlistConfig(
        id="wl-1",
        name="Watchlist",
        client_id="client-1",
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


def _result() -> ListeningResult:
    item = ListeningItem(
        source="facebook_pages",
        url="https://example.com/post",
        title="Batik Promo",
        snippet="New launch",
        score=0.8,
        engagement=12,
        published_at="2026-04-02T00:00:00+00:00",
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
        volume=3,
        status="ok",
    )


class TestListeningStore:
    def test_save_and_get_watchlist(self, tmp_path: Path) -> None:
        store = ListeningStore(tmp_path / "listening.db")
        watchlist = _watchlist()
        store.save_watchlist(watchlist)

        loaded = store.get_watchlist("wl-1")
        assert loaded.id == "wl-1"
        assert loaded.keywords == ("batik",)

    def test_write_results_and_baseline(self, tmp_path: Path) -> None:
        store = ListeningStore(tmp_path / "listening.db")
        store.save_watchlist(_watchlist())
        store.write_result(_result())

        results = store.list_results("wl-1")
        assert len(results) == 1
        assert results[0].items[0].title == "Batik Promo"
        assert store.get_baseline_volume("wl-1", "batik", "facebook_pages") == 3.0

    def test_write_and_get_spike_alerts(self, tmp_path: Path) -> None:
        store = ListeningStore(tmp_path / "listening.db")
        alert = SpikeAlert(
            id="alert-1",
            watchlist_id="wl-1",
            keyword="batik",
            source="facebook_pages",
            current_volume=10,
            baseline_volume=4.0,
            delta_ratio=2.5,
            fired_at="2026-04-02T00:00:00+00:00",
            acknowledged=False,
            alert_sent=True,
            sample_items=_result().items,
        )
        store.write_spike_alert(alert)

        alerts = store.get_spike_alerts("wl-1", "batik", "facebook_pages")
        assert len(alerts) == 1
        assert alerts[0].alert_sent is True

    def test_save_and_list_ad_creatives(self, tmp_path: Path) -> None:
        store = ListeningStore(tmp_path / "listening.db")
        creative = AdCreative(
            platform="tiktok",
            ad_id="ad-1",
            advertiser="TokMa",
            headline=None,
            body=None,
            image_url="https://example.com/image.png",
            video_url=None,
            landing_url=None,
            spend_range=None,
            impressions_range=None,
            engagement=AdEngagement(likes=10, views=100),
            status="active",
            active=True,
            fetched_at="2026-04-02T00:00:00+00:00",
        )
        store.save_ad_creatives([creative])

        ads = store.list_ad_creatives("tiktok")
        assert len(ads) == 1
        assert ads[0].engagement is not None
        assert ads[0].engagement.views == 100
