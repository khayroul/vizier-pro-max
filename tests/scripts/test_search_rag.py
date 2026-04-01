"""Tests for search_rag script."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from scripts.content.search_rag import run as search


class TestSearchRag:
    def test_returns_unavailable_without_vault_path(self) -> None:
        """Without KG_VAULT_PATH, returns unavailable status."""
        with patch.dict(os.environ, {}, clear=True):
            result = search(query="test query")

        assert result["status"] == "unavailable"
        assert result["results"] == []
        assert result["mode"] == "hybrid"

    def test_mode_parameter_passed(self) -> None:
        """Mode parameter is reflected in output."""
        with patch.dict(os.environ, {}, clear=True):
            result = search(query="test", mode="local")

        assert result["mode"] == "local"

    def test_invalid_mode_raises(self) -> None:
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            search(query="test", mode="invalid")

    def test_empty_query_raises(self) -> None:
        """Empty query raises ValueError."""
        with pytest.raises(ValueError, match="query must not be empty"):
            search(query="   ")

    def test_lightrag_import_failure(self) -> None:
        """Graceful fallback when lightrag is not installed."""
        with patch.dict(os.environ, {"KG_VAULT_PATH": "/tmp/vault"}), \
             patch("scripts.content.search_rag._get_rag_instance", return_value=None):
            result = search(query="test query")

        assert result["status"] == "unavailable"
        assert result["results"] == []
