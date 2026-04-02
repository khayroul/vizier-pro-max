"""Typed models for long-form publishing pipelines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LongformMetadata:
    """Shared metadata for all long-form artifacts."""

    title: str
    author: str
    subtitle: str = ""
    date: str = ""
    language: str = "en"
    cover_path: str = ""
    brand: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LongformSection:
    """A nonfiction section with optional callout and inline image."""

    heading: str
    body: str
    level: int = 1
    callout: str = ""
    image_path: str = ""


@dataclass(frozen=True)
class ChartSpec:
    """Chart request for nonfiction output."""

    section_heading: str
    chart_type: str
    data: dict[str, Any]
    title: str = ""
    caption: str = ""


@dataclass(frozen=True)
class LongformChapter:
    """A novel chapter with optional summary and illustration."""

    title: str
    body: str
    summary: str = ""
    illustration_path: str = ""


@dataclass(frozen=True)
class LongformSpread:
    """A children-book spread or page."""

    title: str
    text: str
    illustration_path: str = ""
    caption: str = ""

