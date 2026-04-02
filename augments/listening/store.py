"""SQLite-backed store for the listening engine."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

import structlog

from augments.listening.watchlist import (
    AdCreative,
    AdEngagement,
    ListeningItem,
    ListeningResult,
    SpikeAlert,
    WatchlistConfig,
)
from exceptions import WatchlistNotFoundError

logger = structlog.get_logger(__name__)

DEFAULT_DB_PATH = Path.home() / ".hermes" / "vizier_listening.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlists (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  client_id TEXT,
  keywords TEXT NOT NULL,
  sources TEXT NOT NULL,
  schedule TEXT NOT NULL,
  geo TEXT NOT NULL,
  language TEXT NOT NULL,
  spike_threshold REAL NOT NULL,
  alert_cooldown_hours INTEGER NOT NULL,
  alert_webhooks TEXT NOT NULL,
  webhook_type TEXT NOT NULL,
  active INTEGER NOT NULL,
  running INTEGER NOT NULL DEFAULT 0,
  current_run_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listening_results (
  id TEXT PRIMARY KEY,
  watchlist_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  source TEXT NOT NULL,
  keyword TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  summary TEXT NOT NULL,
  volume INTEGER NOT NULL,
  status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listening_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  result_id TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT,
  title TEXT NOT NULL,
  snippet TEXT NOT NULL,
  score REAL NOT NULL,
  engagement INTEGER NOT NULL,
  published_at TEXT
);
CREATE TABLE IF NOT EXISTS spike_alerts (
  id TEXT PRIMARY KEY,
  watchlist_id TEXT NOT NULL,
  keyword TEXT NOT NULL,
  source TEXT NOT NULL,
  current_volume INTEGER NOT NULL,
  baseline_volume REAL NOT NULL,
  delta_ratio REAL NOT NULL,
  fired_at TEXT NOT NULL,
  acknowledged INTEGER NOT NULL,
  alert_sent INTEGER NOT NULL,
  sample_items TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ad_creatives (
  ad_id TEXT NOT NULL,
  platform TEXT NOT NULL,
  advertiser TEXT NOT NULL,
  headline TEXT,
  body TEXT,
  image_url TEXT,
  video_url TEXT,
  landing_url TEXT,
  spend_range TEXT,
  impressions_range TEXT,
  engagement TEXT,
  status TEXT NOT NULL,
  active INTEGER NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (ad_id, platform)
);
"""


def _row_to_watchlist(row: sqlite3.Row) -> WatchlistConfig:
    return WatchlistConfig(
        id=row["id"],
        name=row["name"],
        client_id=row["client_id"],
        keywords=tuple(json.loads(row["keywords"])),
        sources=tuple(json.loads(row["sources"])),
        schedule=row["schedule"],
        geo=row["geo"],
        language=row["language"],
        spike_threshold=float(row["spike_threshold"]),
        alert_cooldown_hours=int(row["alert_cooldown_hours"]),
        alert_webhooks=tuple(json.loads(row["alert_webhooks"])),
        webhook_type=row["webhook_type"],
        active=bool(row["active"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_item(row: sqlite3.Row) -> ListeningItem:
    return ListeningItem(
        source=row["source"],
        url=row["url"],
        title=row["title"],
        snippet=row["snippet"],
        score=float(row["score"]),
        engagement=int(row["engagement"]),
        published_at=row["published_at"],
    )


def _row_to_alert(row: sqlite3.Row) -> SpikeAlert:
    sample_items = tuple(ListeningItem(**item) for item in json.loads(row["sample_items"]))
    return SpikeAlert(
        id=row["id"],
        watchlist_id=row["watchlist_id"],
        keyword=row["keyword"],
        source=row["source"],
        current_volume=int(row["current_volume"]),
        baseline_volume=float(row["baseline_volume"]),
        delta_ratio=float(row["delta_ratio"]),
        fired_at=row["fired_at"],
        acknowledged=bool(row["acknowledged"]),
        alert_sent=bool(row["alert_sent"]),
        sample_items=sample_items,
    )


def _row_to_ad_creative(row: sqlite3.Row) -> AdCreative:
    engagement_payload = json.loads(row["engagement"]) if row["engagement"] else None
    engagement = AdEngagement(**engagement_payload) if isinstance(engagement_payload, dict) else None
    return AdCreative(
        platform=row["platform"],
        ad_id=row["ad_id"],
        advertiser=row["advertiser"],
        headline=row["headline"],
        body=row["body"],
        image_url=row["image_url"],
        video_url=row["video_url"],
        landing_url=row["landing_url"],
        spend_range=row["spend_range"],
        impressions_range=row["impressions_range"],
        engagement=engagement,
        status=row["status"],
        active=bool(row["active"]),
        fetched_at=row["fetched_at"],
    )


class ListeningStore:
    """SQLite-backed store for listening data."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self._db_path))
        connection.row_factory = sqlite3.Row
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def save_watchlist(self, watchlist: WatchlistConfig) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO watchlists (
                  id, name, client_id, keywords, sources, schedule, geo, language,
                  spike_threshold, alert_cooldown_hours, alert_webhooks, webhook_type,
                  active, running, current_run_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT running FROM watchlists WHERE id = ?), 0), COALESCE((SELECT current_run_id FROM watchlists WHERE id = ?), NULL), ?, ?)
                """,
                (
                    watchlist.id,
                    watchlist.name,
                    watchlist.client_id,
                    json.dumps(list(watchlist.keywords)),
                    json.dumps(list(watchlist.sources)),
                    watchlist.schedule,
                    watchlist.geo,
                    watchlist.language,
                    watchlist.spike_threshold,
                    watchlist.alert_cooldown_hours,
                    json.dumps(list(watchlist.alert_webhooks)),
                    watchlist.webhook_type,
                    1 if watchlist.active else 0,
                    watchlist.id,
                    watchlist.id,
                    watchlist.created_at,
                    watchlist.updated_at,
                ),
            )
            connection.commit()

    def get_watchlist(self, watchlist_id: str) -> WatchlistConfig:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
        if row is None:
            raise WatchlistNotFoundError(watchlist_id)
        return _row_to_watchlist(row)

    def list_watchlists(
        self,
        client_id: str | None = None,
        active_only: bool = False,
    ) -> list[WatchlistConfig]:
        query = "SELECT * FROM watchlists"
        filters = []
        params: list[object] = []
        if client_id is not None:
            filters.append("client_id = ?")
            params.append(client_id)
        if active_only:
            filters.append("active = 1")
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY name"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_watchlist(row) for row in rows]

    def set_watchlist_running(
        self,
        watchlist_id: str,
        running: bool,
        run_id: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE watchlists SET running = ?, current_run_id = ? WHERE id = ?",
                (1 if running else 0, run_id, watchlist_id),
            )
            connection.commit()

    def is_watchlist_running(self, watchlist_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT running FROM watchlists WHERE id = ?", (watchlist_id,)).fetchone()
        return bool(row["running"]) if row is not None else False

    def is_watchlist_running_in_db(self, watchlist_id: str) -> bool:
        return self.is_watchlist_running(watchlist_id)

    def write_result(self, result: ListeningResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO listening_results
                (id, watchlist_id, run_id, source, keyword, timestamp, summary, volume, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.id,
                    result.watchlist_id,
                    result.run_id,
                    result.source,
                    result.keyword,
                    result.timestamp,
                    result.summary,
                    result.volume,
                    result.status,
                ),
            )
            connection.execute("DELETE FROM listening_items WHERE result_id = ?", (result.id,))
            for item in result.items:
                connection.execute(
                    """
                    INSERT INTO listening_items
                    (result_id, source, url, title, snippet, score, engagement, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.id,
                        item.source,
                        item.url,
                        item.title,
                        item.snippet,
                        item.score,
                        item.engagement,
                        item.published_at,
                    ),
                )
            connection.commit()

    def list_results(self, watchlist_id: str | None = None) -> list[ListeningResult]:
        query = "SELECT * FROM listening_results"
        params: list[object] = []
        if watchlist_id is not None:
            query += " WHERE watchlist_id = ?"
            params.append(watchlist_id)
        query += " ORDER BY timestamp DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
            results = []
            for row in rows:
                item_rows = connection.execute(
                    "SELECT * FROM listening_items WHERE result_id = ? ORDER BY id",
                    (row["id"],),
                ).fetchall()
                results.append(
                    ListeningResult(
                        id=row["id"],
                        watchlist_id=row["watchlist_id"],
                        run_id=row["run_id"],
                        source=row["source"],
                        keyword=row["keyword"],
                        timestamp=row["timestamp"],
                        items=tuple(_row_to_item(item_row) for item_row in item_rows),
                        summary=row["summary"],
                        volume=int(row["volume"]),
                        status=row["status"],
                    )
                )
        return results

    def get_baseline_volume(self, watchlist_id: str, keyword: str, source: str) -> float:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT AVG(volume) AS baseline
                FROM listening_results
                WHERE watchlist_id = ? AND keyword = ? AND source = ?
                """,
                (watchlist_id, keyword, source),
            ).fetchone()
        return float(row["baseline"]) if row is not None and row["baseline"] is not None else 0.0

    def write_spike_alert(self, alert: SpikeAlert) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO spike_alerts
                (id, watchlist_id, keyword, source, current_volume, baseline_volume, delta_ratio, fired_at, acknowledged, alert_sent, sample_items)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.id,
                    alert.watchlist_id,
                    alert.keyword,
                    alert.source,
                    alert.current_volume,
                    alert.baseline_volume,
                    alert.delta_ratio,
                    alert.fired_at,
                    1 if alert.acknowledged else 0,
                    1 if alert.alert_sent else 0,
                    json.dumps([asdict(item) for item in alert.sample_items]),
                ),
            )
            connection.commit()

    def get_spike_alerts(self, watchlist_id: str, keyword: str, source: str) -> list[SpikeAlert]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM spike_alerts
                WHERE watchlist_id = ? AND keyword = ? AND source = ?
                ORDER BY fired_at DESC
                """,
                (watchlist_id, keyword, source),
            ).fetchall()
        return [_row_to_alert(row) for row in rows]

    def save_ad_creatives(self, ads: list[AdCreative]) -> None:
        with self._connect() as connection:
            for ad in ads:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO ad_creatives
                    (ad_id, platform, advertiser, headline, body, image_url, video_url, landing_url, spend_range, impressions_range, engagement, status, active, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ad.ad_id,
                        ad.platform,
                        ad.advertiser,
                        ad.headline,
                        ad.body,
                        ad.image_url,
                        ad.video_url,
                        ad.landing_url,
                        ad.spend_range,
                        ad.impressions_range,
                        json.dumps(asdict(ad.engagement)) if ad.engagement is not None else None,
                        ad.status,
                        1 if ad.active else 0,
                        ad.fetched_at,
                    ),
                )
            connection.commit()

    def list_ad_creatives(self, platform: str | None = None) -> list[AdCreative]:
        query = "SELECT * FROM ad_creatives"
        params: list[object] = []
        if platform is not None:
            query += " WHERE platform = ?"
            params.append(platform)
        query += " ORDER BY fetched_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_ad_creative(row) for row in rows]
