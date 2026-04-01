"""Tests for deliverable context propagation."""
from __future__ import annotations

import uuid

import pytest

from middleware.deliverable_context import (
    clear_context,
    get_client_id,
    get_deliverable_id,
    set_context,
    start_deliverable,
)


class TestStartDeliverable:
    def test_returns_uuid4_string(self) -> None:
        clear_context()
        did = start_deliverable(client_id="client_abc")
        parsed = uuid.UUID(did, version=4)
        assert str(parsed) == did

    def test_sets_deliverable_id(self) -> None:
        clear_context()
        did = start_deliverable(client_id="client_abc")
        assert get_deliverable_id() == did

    def test_sets_client_id(self) -> None:
        clear_context()
        start_deliverable(client_id="client_abc")
        assert get_client_id() == "client_abc"

    def test_client_id_defaults_to_none(self) -> None:
        clear_context()
        start_deliverable()
        assert get_client_id() is None


class TestSetContext:
    def test_restores_existing_ids(self) -> None:
        clear_context()
        set_context(deliverable_id="existing_123", client_id="client_x")
        assert get_deliverable_id() == "existing_123"
        assert get_client_id() == "client_x"


class TestClearContext:
    def test_clears_both_ids(self) -> None:
        clear_context()
        start_deliverable(client_id="client_abc")
        clear_context()
        assert get_deliverable_id() is None
        assert get_client_id() is None


class TestGettersWithNoContext:
    def test_returns_none_by_default(self) -> None:
        clear_context()
        assert get_deliverable_id() is None
        assert get_client_id() is None
