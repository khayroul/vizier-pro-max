"""Tests for cross-session context injector plugin."""
from __future__ import annotations

import pytest

from middleware.deliverable_context import clear_context, get_client_id, get_deliverable_id
from plugins.context_injector import inject_from_task_context


class TestInjectFromTaskContext:
    def test_injects_deliverable_id(self) -> None:
        clear_context()
        inject_from_task_context({"deliverable_id": "d-123", "client_id": "acme"})
        assert get_deliverable_id() == "d-123"
        assert get_client_id() == "acme"

    def test_handles_missing_deliverable_id(self) -> None:
        clear_context()
        inject_from_task_context({"some_other_key": "value"})
        assert get_deliverable_id() is None

    def test_handles_empty_context(self) -> None:
        clear_context()
        inject_from_task_context({})
        assert get_deliverable_id() is None

    def test_handles_none_context(self) -> None:
        clear_context()
        inject_from_task_context(None)
        assert get_deliverable_id() is None
