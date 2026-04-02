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
class StructuredNonfictionPackage:
    """Package-level config for structured nonfiction outputs."""

    profile: str = "ebook"
    package_mode: str = "single_document"
    include_toc: bool = True


@dataclass(frozen=True)
class StructuredNonfictionDocument:
    """A normalized structured-nonfiction document within a package."""

    title: str
    subtitle: str = ""
    slug: str = ""
    sections: tuple[LongformSection, ...] = ()
    charts: tuple[ChartSpec, ...] = ()


@dataclass(frozen=True)
class MarketingPlanStrategy:
    """Structured strategy inputs for marketing-plan style documents."""

    objective: str = ""
    audience: str = ""
    offer: str = ""
    positioning: str = ""
    key_message: str = ""
    market_context: str = ""
    budget: str = ""
    timeline: str = ""
    primary_cta: str = ""
    channels: tuple[str, ...] = ()
    kpis: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    recommended_actions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CampaignAngle:
    """Campaign angle used to derive strategy and creative docs."""

    name: str
    audience_segment: str = ""
    pain_point: str = ""
    promise: str = ""
    proof: str = ""
    message: str = ""
    offer: str = ""
    cta: str = ""
    channels: tuple[str, ...] = ()
    visual_direction: str = ""
    headline: str = ""
    body: str = ""
    notes: str = ""
    score: float | None = None


@dataclass(frozen=True)
class CreativeVariant:
    """Creative execution variant attached to a campaign angle."""

    angle_name: str
    channel: str = ""
    headline: str = ""
    body: str = ""
    cta: str = ""
    image_prompt: str = ""
    poster_path: str = ""
    notes: str = ""
    score: float | None = None


@dataclass(frozen=True)
class ContentCalendarEntry:
    """Simple content-calendar entry for marketing-plan addenda."""

    period: str
    channel: str = ""
    deliverable: str = ""
    theme: str = ""
    cta: str = ""
    notes: str = ""


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
