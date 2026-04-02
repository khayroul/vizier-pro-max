"""Tests for listening watchlist models and schedule parsing."""
from __future__ import annotations

import pytest

from augments.listening.watchlist import ListeningItem, parse_schedule


class TestParseSchedule:
    def test_daily_at_hour(self) -> None:
        assert parse_schedule("daily at 8am") == "0 8 * * *"

    def test_every_hours(self) -> None:
        assert parse_schedule("every 6 hours") == "0 */6 * * *"

    def test_weekdays(self) -> None:
        assert parse_schedule("weekdays at 9am") == "0 9 * * 1-5"

    def test_passthrough_cron(self) -> None:
        assert parse_schedule("0 8 * * *") == "0 8 * * *"

    def test_invalid_schedule_raises(self) -> None:
        with pytest.raises(Exception):
            parse_schedule("sometime later")


class TestDataclasses:
    def test_listening_item_frozen(self) -> None:
        item = ListeningItem(
            source="reddit",
            url="https://example.com",
            title="Title",
            snippet="Snippet",
            score=0.5,
            engagement=10,
            published_at=None,
        )
        with pytest.raises(AttributeError):
            item.title = "Changed"  # type: ignore[misc]
