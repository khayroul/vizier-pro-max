"""Listening engine data models and schedule parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from exceptions import InputCheckError


@dataclass(frozen=True)
class ListeningItem:
    source: str
    url: str | None
    title: str
    snippet: str
    score: float
    engagement: int
    published_at: str | None


@dataclass(frozen=True)
class WatchlistConfig:
    id: str
    name: str
    client_id: str | None
    keywords: tuple[str, ...]
    sources: tuple[str, ...]
    schedule: str
    geo: str
    language: str
    spike_threshold: float
    alert_cooldown_hours: int
    alert_webhooks: tuple[str, ...]
    webhook_type: Literal["telegram", "slack", "discord", "generic"]
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ListeningResult:
    id: str
    watchlist_id: str
    run_id: str
    source: str
    keyword: str
    timestamp: str
    items: tuple[ListeningItem, ...]
    summary: str
    volume: int
    status: str


@dataclass(frozen=True)
class AdEngagement:
    likes: int = 0
    views: int = 0
    shares: int = 0
    comments: int = 0


@dataclass(frozen=True)
class SpikeAlert:
    id: str
    watchlist_id: str
    keyword: str
    source: str
    current_volume: int
    baseline_volume: float
    delta_ratio: float
    fired_at: str
    acknowledged: bool
    alert_sent: bool
    sample_items: tuple[ListeningItem, ...]


@dataclass(frozen=True)
class AdCreative:
    platform: str
    ad_id: str
    advertiser: str
    headline: str | None
    body: str | None
    image_url: str | None
    video_url: str | None
    landing_url: str | None
    spend_range: str | None
    impressions_range: str | None
    engagement: AdEngagement | None
    status: str
    active: bool
    fetched_at: str


_HOUR_MAP = {
    "12am": 0,
    "1am": 1,
    "2am": 2,
    "3am": 3,
    "4am": 4,
    "5am": 5,
    "6am": 6,
    "7am": 7,
    "8am": 8,
    "9am": 9,
    "10am": 10,
    "11am": 11,
    "12pm": 12,
    "1pm": 13,
    "2pm": 14,
    "3pm": 15,
    "4pm": 16,
    "5pm": 17,
    "6pm": 18,
    "7pm": 19,
    "8pm": 20,
    "9pm": 21,
    "10pm": 22,
    "11pm": 23,
}

_CRON_RE = re.compile(
    r"^(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)$"
)
_DAILY_RE = re.compile(r"daily\s+at\s+(\d{1,2}(?:am|pm))$", re.IGNORECASE)
_EVERY_HOURS_RE = re.compile(r"every\s+(\d+)\s+hours?$", re.IGNORECASE)
_WEEKDAYS_RE = re.compile(r"weekdays\s+at\s+(\d{1,2}(?:am|pm))$", re.IGNORECASE)


def parse_schedule(schedule: str) -> str:
    """Convert a human schedule string into a cron expression."""
    stripped = schedule.strip()
    if _CRON_RE.match(stripped):
        return stripped

    daily = _DAILY_RE.match(stripped)
    if daily:
        hour = _HOUR_MAP.get(daily.group(1).lower())
        if hour is None:
            raise InputCheckError("schedule", [f"Unknown hour: {daily.group(1)}"])
        return f"0 {hour} * * *"

    every_hours = _EVERY_HOURS_RE.match(stripped)
    if every_hours:
        hours = int(every_hours.group(1))
        if hours < 1 or hours > 23:
            raise InputCheckError("schedule", [f"Hours must be 1-23, got {hours}"])
        return f"0 */{hours} * * *"

    weekdays = _WEEKDAYS_RE.match(stripped)
    if weekdays:
        hour = _HOUR_MAP.get(weekdays.group(1).lower())
        if hour is None:
            raise InputCheckError("schedule", [f"Unknown hour: {weekdays.group(1)}"])
        return f"0 {hour} * * 1-5"

    raise InputCheckError(
        "schedule",
        [
            f"Cannot parse schedule: {schedule!r}. Use 'daily at 8am', 'every 6 hours', 'weekdays at 9am', or a raw cron expression.",
        ],
    )
