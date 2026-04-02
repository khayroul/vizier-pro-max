"""Spike detection and webhook delivery."""
from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from augments.listening.store import ListeningStore
from augments.listening.watchlist import ListeningResult, SpikeAlert, WatchlistConfig

logger = structlog.get_logger(__name__)

_MAX_SAMPLE_ITEMS = 3


class SpikeDetector:
    """Detect spikes against historical baseline volume."""

    def __init__(self, store: ListeningStore | None = None) -> None:
        self._store = store or ListeningStore()

    def check(
        self,
        watchlist: WatchlistConfig,
        results: list[ListeningResult],
    ) -> list[SpikeAlert]:
        alerts = []
        for result in results:
            alert = self._check_result(watchlist, result)
            if alert is not None:
                alerts.append(alert)
        return alerts

    def _check_result(
        self,
        watchlist: WatchlistConfig,
        result: ListeningResult,
    ) -> SpikeAlert | None:
        baseline = self._store.get_baseline_volume(watchlist.id, result.keyword, result.source)
        if baseline == 0.0:
            return None

        delta_ratio = result.volume / baseline
        if delta_ratio < watchlist.spike_threshold:
            return None
        if self._in_cooldown(watchlist, result.keyword, result.source):
            return None

        alert = SpikeAlert(
            id=str(uuid.uuid4()),
            watchlist_id=watchlist.id,
            keyword=result.keyword,
            source=result.source,
            current_volume=result.volume,
            baseline_volume=baseline,
            delta_ratio=round(delta_ratio, 4),
            fired_at=datetime.now(UTC).isoformat(),
            acknowledged=False,
            alert_sent=False,
            sample_items=result.items[:_MAX_SAMPLE_ITEMS],
        )
        delivered = self._deliver(alert, watchlist)
        self._store.write_spike_alert(delivered)
        return delivered

    def _in_cooldown(self, watchlist: WatchlistConfig, keyword: str, source: str) -> bool:
        cutoff = datetime.now(UTC) - timedelta(hours=watchlist.alert_cooldown_hours)
        for alert in self._store.get_spike_alerts(watchlist.id, keyword, source):
            if alert.alert_sent and datetime.fromisoformat(alert.fired_at) > cutoff:
                return True
        return False

    def _deliver(self, alert: SpikeAlert, watchlist: WatchlistConfig) -> SpikeAlert:
        if not watchlist.alert_webhooks:
            return alert

        payload = _build_payload(alert, watchlist.webhook_type)
        sent = False
        with httpx.Client(timeout=10.0) as client:
            for webhook in watchlist.alert_webhooks:
                try:
                    response = client.post(webhook, json=payload)
                    response.raise_for_status()
                    sent = True
                except (httpx.HTTPError, httpx.RequestError) as exc:
                    logger.warning("Spike webhook delivery failed", webhook=webhook, error=str(exc))
        return dataclasses.replace(alert, alert_sent=sent)


def _build_payload(alert: SpikeAlert, webhook_type: str) -> dict[str, object]:
    summary = (
        f"Spike detected: *{alert.keyword}* on {alert.source}\n"
        f"Volume: {alert.current_volume} (baseline: {alert.baseline_volume:.1f}, ratio: {alert.delta_ratio:.2f}x)"
    )
    sample_url = alert.sample_items[0].url if alert.sample_items else None
    if webhook_type == "telegram":
        return {"text": summary, "parse_mode": "Markdown"}
    if webhook_type == "slack":
        return {"text": summary, "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": summary}}]}
    if webhook_type == "discord":
        return {"content": summary, "embeds": [{"title": f"Spike: {alert.keyword}", "url": sample_url or ""}]}
    return {
        "watchlist_id": alert.watchlist_id,
        "keyword": alert.keyword,
        "source": alert.source,
        "delta": alert.delta_ratio,
        "current_volume": alert.current_volume,
        "baseline_volume": alert.baseline_volume,
        "summary": summary,
        "sample_url": sample_url,
        "fired_at": alert.fired_at,
    }
