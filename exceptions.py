"""Shared domain exceptions for Vizier Pro-Max."""
from __future__ import annotations


class HermesError(Exception):
    """Base exception for domain errors."""


class InputCheckError(HermesError):
    """Raised when structured input validation fails."""

    def __init__(self, engine: str, errors: list[str]) -> None:
        self.engine = engine
        self.errors = errors
        super().__init__(f"Input validation failed for {engine}: {errors}")


class ListeningError(HermesError):
    """Base exception for listening engine failures."""


class WatchlistNotFoundError(ListeningError):
    """Raised when a watchlist ID does not exist."""

    def __init__(self, watchlist_id: str) -> None:
        self.watchlist_id = watchlist_id
        super().__init__(f"Watchlist not found: {watchlist_id}")


class SourceUnavailableError(ListeningError):
    """Raised when a requested source adapter is unavailable."""

    def __init__(self, source: str, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"Source '{source}' unavailable: {reason}")


class CollectionFailedError(ListeningError):
    """Raised when a collection run fails."""

    def __init__(self, run_id: str, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"Collection failed for run {run_id}: {reason}")
