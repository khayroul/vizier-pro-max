"""Shared helpers for long-form book pipelines."""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any

from middleware.quality_scorer import QualityProperty, compute_score
from pipelines.longform.models import (
    CampaignAngle,
    ChartSpec,
    ContentCalendarEntry,
    CreativeVariant,
    LongformChapter,
    LongformMetadata,
    LongformSection,
    LongformSpread,
    MarketingPlanStrategy,
    StructuredNonfictionDocument,
    StructuredNonfictionPackage,
)

_ROOT = Path(__file__).resolve().parents[2]
_DOC_TEMPLATES = _ROOT / "templates" / "documents"
_NEWLINES_RE = re.compile(r"\n{2,}")
_SLUG_RE = re.compile(r"[^a-z0-9]+")

_DEFAULT_BRAND = {
    "primary_color": "#1A1A2E",
    "secondary_color": "#F4F4F8",
    "accent_color": "#E94560",
    "headline_font": "Georgia, 'Times New Roman', serif",
    "body_font": "system-ui, -apple-system, sans-serif",
}

_STRUCTURED_NONFICTION_PROFILES = frozenset({
    "ebook",
    "marketing_plan",
    "campaign_dossier",
    "creative_pack",
    "content_calendar",
    "technical_report",
    "business_report",
    "proposal",
    "research_brief",
    "whitepaper",
    "playbook",
    "training_manual",
    "illustrated_encyclopedia",
    "case_study",
    "audit_report",
})

_PACKAGE_MODES = frozenset({"single_document", "document_bundle"})
_MARKETING_PROFILES = frozenset({"marketing_plan", "campaign_dossier", "creative_pack"})


def build_metadata(
    *,
    title: str,
    author: str,
    subtitle: str = "",
    date: str = "",
    language: str = "en",
    cover_path: str = "",
    brand: dict[str, object] | None = None,
) -> LongformMetadata:
    """Validate and normalize shared long-form metadata."""
    if not title.strip():
        msg = "title is required"
        raise ValueError(msg)
    if not author.strip():
        msg = "author is required"
        raise ValueError(msg)

    merged_brand = {**_DEFAULT_BRAND}
    if brand:
        merged_brand.update(
            {key: str(value) for key, value in brand.items() if value}
        )

    return LongformMetadata(
        title=title.strip(),
        author=author.strip(),
        subtitle=subtitle.strip(),
        date=date.strip(),
        language=language.strip() or "en",
        cover_path=cover_path.strip(),
        brand=merged_brand,
    )


def slugify(value: str) -> str:
    """Convert text into a filesystem-safe slug."""
    collapsed = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return collapsed or "document"


def build_structured_nonfiction_package(
    *,
    profile: str = "ebook",
    package_mode: str = "single_document",
    include_toc: bool = True,
) -> StructuredNonfictionPackage:
    """Validate structured-nonfiction family options."""
    normalized_profile = profile.strip().lower() or "ebook"
    if normalized_profile not in _STRUCTURED_NONFICTION_PROFILES:
        msg = (
            f"Unsupported structured_nonfiction profile: {profile!r}. "
            f"Valid: {sorted(_STRUCTURED_NONFICTION_PROFILES)}"
        )
        raise ValueError(msg)

    normalized_mode = package_mode.strip().lower() or "single_document"
    if normalized_mode not in _PACKAGE_MODES:
        msg = (
            f"Unsupported package_mode: {package_mode!r}. "
            f"Valid: {sorted(_PACKAGE_MODES)}"
        )
        raise ValueError(msg)

    return StructuredNonfictionPackage(
        profile=normalized_profile,
        package_mode=normalized_mode,
        include_toc=include_toc,
    )


def uses_marketing_workflow(profile: str) -> bool:
    """Return whether a profile should use the campaign-aware marketing builder."""
    return profile in _MARKETING_PROFILES


def _normalize_string_list(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Normalize a list-like value into a tuple of strings."""
    if value in (None, ""):
        return ()

    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())

    if not isinstance(value, (list, tuple)):
        msg = f"{field_name} must be a list of strings or a comma-separated string"
        raise ValueError(msg)

    items = [str(item).strip() for item in value if str(item).strip()]
    return tuple(items)


def _normalize_optional_score(
    value: object,
    *,
    field_name: str,
) -> float | None:
    """Normalize an optional numeric score."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        msg = f"{field_name} must be numeric when provided"
        raise ValueError(msg) from exc


def normalize_marketing_strategy(
    strategy: dict[str, object] | None,
) -> MarketingPlanStrategy:
    """Normalize a marketing strategy object."""
    if strategy is None:
        return MarketingPlanStrategy()
    if not isinstance(strategy, dict):
        msg = "strategy must be an object"
        raise ValueError(msg)

    return MarketingPlanStrategy(
        objective=str(strategy.get("objective", "")).strip(),
        audience=str(strategy.get("audience", "")).strip(),
        offer=str(strategy.get("offer", "")).strip(),
        positioning=str(strategy.get("positioning", "")).strip(),
        key_message=str(
            strategy.get("key_message", strategy.get("message_house", ""))
        ).strip(),
        market_context=str(strategy.get("market_context", "")).strip(),
        budget=str(strategy.get("budget", "")).strip(),
        timeline=str(strategy.get("timeline", "")).strip(),
        primary_cta=str(
            strategy.get("primary_cta", strategy.get("cta", ""))
        ).strip(),
        channels=_normalize_string_list(
            strategy.get("channels"),
            field_name="strategy.channels",
        ),
        kpis=_normalize_string_list(
            strategy.get("kpis"),
            field_name="strategy.kpis",
        ),
        constraints=_normalize_string_list(
            strategy.get("constraints"),
            field_name="strategy.constraints",
        ),
        recommended_actions=_normalize_string_list(
            strategy.get("recommended_actions"),
            field_name="strategy.recommended_actions",
        ),
    )


def normalize_campaign_angles(
    items: list[dict[str, object]] | None,
) -> list[CampaignAngle]:
    """Normalize campaign-angle inputs."""
    if not items:
        return []

    angles: list[CampaignAngle] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            msg = f"campaign_angles[{idx}] must be an object"
            raise ValueError(msg)
        name = str(
            item.get("name", item.get("angle", item.get("title", "")))
        ).strip()
        if not name:
            msg = f"campaign_angles[{idx}] name is required"
            raise ValueError(msg)
        angles.append(
            CampaignAngle(
                name=name,
                audience_segment=str(item.get("audience_segment", "")).strip(),
                pain_point=str(item.get("pain_point", "")).strip(),
                promise=str(item.get("promise", "")).strip(),
                proof=str(item.get("proof", "")).strip(),
                message=str(item.get("message", "")).strip(),
                offer=str(item.get("offer", "")).strip(),
                cta=str(item.get("cta", "")).strip(),
                channels=_normalize_string_list(
                    item.get("channels"),
                    field_name=f"campaign_angles[{idx}].channels",
                ),
                visual_direction=str(item.get("visual_direction", "")).strip(),
                headline=str(item.get("headline", "")).strip(),
                body=str(item.get("body", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
                score=_normalize_optional_score(
                    item.get("score"),
                    field_name=f"campaign_angles[{idx}].score",
                ),
            )
        )
    return angles


def normalize_creative_variants(
    items: list[dict[str, object]] | None,
    *,
    angles: list[CampaignAngle],
    strategy: MarketingPlanStrategy,
) -> list[CreativeVariant]:
    """Normalize or synthesize creative variants from campaign angles."""
    if not items:
        return [
            CreativeVariant(
                angle_name=angle.name,
                channel=(
                    angle.channels[0]
                    if angle.channels
                    else (strategy.channels[0] if strategy.channels else "")
                ),
                headline=angle.headline or angle.name,
                body=angle.body
                or " ".join(
                    part.strip()
                    for part in (
                        angle.promise,
                        angle.proof,
                        angle.message,
                    )
                    if part.strip()
                ),
                cta=angle.cta or strategy.primary_cta or "Learn more",
                image_prompt=angle.visual_direction,
                notes=angle.notes,
                score=angle.score,
            )
            for angle in angles
        ]

    variants: list[CreativeVariant] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            msg = f"creative_variants[{idx}] must be an object"
            raise ValueError(msg)
        angle_name = str(
            item.get("angle_name", item.get("angle", ""))
        ).strip()
        if not angle_name:
            msg = f"creative_variants[{idx}] angle_name is required"
            raise ValueError(msg)
        variants.append(
            CreativeVariant(
                angle_name=angle_name,
                channel=str(item.get("channel", "")).strip(),
                headline=str(item.get("headline", "")).strip(),
                body=str(item.get("body", "")).strip(),
                cta=str(item.get("cta", "")).strip(),
                image_prompt=str(item.get("image_prompt", "")).strip(),
                poster_path=str(item.get("poster_path", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
                score=_normalize_optional_score(
                    item.get("score"),
                    field_name=f"creative_variants[{idx}].score",
                ),
            )
        )
    return variants


def normalize_content_calendar_entries(
    items: list[dict[str, object]] | None,
) -> list[ContentCalendarEntry]:
    """Normalize content-calendar rows."""
    if not items:
        return []

    entries: list[ContentCalendarEntry] = []
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            msg = f"content_calendar[{idx}] must be an object"
            raise ValueError(msg)
        period = str(item.get("period", item.get("week", ""))).strip()
        if not period:
            msg = f"content_calendar[{idx}] period is required"
            raise ValueError(msg)
        entries.append(
            ContentCalendarEntry(
                period=period,
                channel=str(item.get("channel", "")).strip(),
                deliverable=str(item.get("deliverable", "")).strip(),
                theme=str(item.get("theme", "")).strip(),
                cta=str(item.get("cta", "")).strip(),
                notes=str(item.get("notes", "")).strip(),
            )
        )
    return entries


def _join_paragraphs(parts: list[str]) -> str:
    """Join text parts into paragraph-separated prose."""
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _format_labelled(label: str, value: str) -> str:
    """Format a single labelled sentence when a value exists."""
    if not value.strip():
        return ""
    return f"{label}: {value.strip()}"


def _format_labelled_list(label: str, items: tuple[str, ...]) -> str:
    """Format a labelled sentence for a tuple of values."""
    if not items:
        return ""
    return f"{label}: {', '.join(items)}"


def _build_strategy_sections(
    *,
    strategy: MarketingPlanStrategy,
    campaign_angles: list[CampaignAngle],
    content_calendar: list[ContentCalendarEntry],
    extra_sections: tuple[LongformSection, ...],
) -> list[LongformSection]:
    """Build strategy-first sections for a marketing plan."""
    summary_callout = _join_paragraphs(
        [
            _format_labelled("Objective", strategy.objective),
            _format_labelled_list("Channels", strategy.channels),
            _format_labelled("Primary CTA", strategy.primary_cta),
        ]
    )
    strategy_sections = [
        LongformSection(
            heading="Executive Summary",
            body=_join_paragraphs(
                [
                    _format_labelled("Objective", strategy.objective),
                    _format_labelled("Audience", strategy.audience),
                    _format_labelled("Offer", strategy.offer),
                    _format_labelled("Positioning", strategy.positioning),
                    _format_labelled("Key Message", strategy.key_message),
                ]
            )
            or "Campaign strategy summary pending.",
            callout=summary_callout,
        ),
        LongformSection(
            heading="Audience and Market Context",
            body=_join_paragraphs(
                [
                    _format_labelled("Audience", strategy.audience),
                    _format_labelled("Market Context", strategy.market_context),
                    _format_labelled_list("Constraints", strategy.constraints),
                ]
            )
            or "Audience and market context were not supplied.",
        ),
        LongformSection(
            heading="Messaging and Positioning",
            body=_join_paragraphs(
                [
                    _format_labelled("Positioning", strategy.positioning),
                    _format_labelled("Offer", strategy.offer),
                    _format_labelled("Key Message", strategy.key_message),
                ]
            )
            or "Messaging direction was not supplied.",
        ),
    ]

    if campaign_angles:
        angle_paragraphs = []
        for angle in campaign_angles:
            score_text = (
                f" Score: {angle.score:.1f}."
                if angle.score is not None
                else ""
            )
            angle_paragraphs.append(
                _join_paragraphs(
                    [
                        f"{angle.name}: {angle.promise or angle.message or 'Angle summary pending.'}{score_text}",
                        _format_labelled("Audience Segment", angle.audience_segment),
                        _format_labelled("Pain Point", angle.pain_point),
                        _format_labelled("Proof", angle.proof),
                        _format_labelled_list("Channels", angle.channels),
                    ]
                )
            )
        strategy_sections.append(
            LongformSection(
                heading="Campaign Angles",
                body=_join_paragraphs(angle_paragraphs),
            )
        )

    strategy_sections.append(
        LongformSection(
            heading="Channel Plan and KPIs",
            body=_join_paragraphs(
                [
                    _format_labelled_list("Channels", strategy.channels),
                    _format_labelled_list("KPIs", strategy.kpis),
                    _format_labelled("Timeline", strategy.timeline),
                    _format_labelled("Budget", strategy.budget),
                    _format_labelled_list(
                        "Recommended Actions",
                        strategy.recommended_actions,
                    ),
                ]
            )
            or "Channel plan and KPI detail were not supplied.",
        )
    )

    if content_calendar:
        strategy_sections.append(
            LongformSection(
                heading="Content Calendar Snapshot",
                body=_join_paragraphs(
                    [
                        _join_paragraphs(
                            [
                                _format_labelled("Period", entry.period),
                                _format_labelled("Channel", entry.channel),
                                _format_labelled("Theme", entry.theme),
                                _format_labelled(
                                    "Deliverable",
                                    entry.deliverable,
                                ),
                                _format_labelled("CTA", entry.cta),
                                _format_labelled("Notes", entry.notes),
                            ]
                        )
                        for entry in content_calendar
                    ]
                ),
            )
        )

    strategy_sections.extend(extra_sections)
    return strategy_sections


def _build_creative_sections(
    *,
    strategy: MarketingPlanStrategy,
    campaign_angles: list[CampaignAngle],
    creative_variants: list[CreativeVariant],
) -> list[LongformSection]:
    """Build creative-pack sections grouped by campaign angle."""
    variant_lookup: dict[str, list[CreativeVariant]] = {}
    for variant in creative_variants:
        variant_lookup.setdefault(variant.angle_name, []).append(variant)

    angle_lookup = {angle.name: angle for angle in campaign_angles}
    section_order = list(angle_lookup)
    for angle_name in variant_lookup:
        if angle_name not in angle_lookup:
            section_order.append(angle_name)

    creative_sections = [
        LongformSection(
            heading="Creative Direction",
            body=_join_paragraphs(
                [
                    _format_labelled_list("Channels", strategy.channels),
                    _format_labelled("Primary CTA", strategy.primary_cta),
                    _format_labelled(
                        "Creative Objective",
                        strategy.objective,
                    ),
                ]
            )
            or "Creative direction pending.",
        )
    ]

    for angle_name in section_order:
        angle = angle_lookup.get(angle_name)
        variants = variant_lookup.get(angle_name, [])
        image_path = next(
            (
                variant.poster_path
                for variant in variants
                if variant.poster_path.strip()
            ),
            "",
        )
        variant_paragraphs = []
        for idx, variant in enumerate(variants, start=1):
            score_text = (
                f" Score: {variant.score:.1f}."
                if variant.score is not None
                else ""
            )
            variant_paragraphs.append(
                _join_paragraphs(
                    [
                        f"Variant {idx}: {variant.headline or 'Headline pending.'}{score_text}",
                        _format_labelled("Channel", variant.channel),
                        _format_labelled("Body Copy", variant.body),
                        _format_labelled("CTA", variant.cta),
                        _format_labelled("Image Prompt", variant.image_prompt),
                        _format_labelled("Notes", variant.notes),
                    ]
                )
            )

        creative_sections.append(
            LongformSection(
                heading=angle_name,
                body=_join_paragraphs(
                    [
                        _format_labelled(
                            "Audience Segment",
                            angle.audience_segment if angle else "",
                        ),
                        _format_labelled(
                            "Pain Point",
                            angle.pain_point if angle else "",
                        ),
                        _format_labelled(
                            "Promise",
                            angle.promise if angle else "",
                        ),
                        _format_labelled(
                            "Proof",
                            angle.proof if angle else "",
                        ),
                        _format_labelled(
                            "Message",
                            angle.message if angle else "",
                        ),
                        _format_labelled(
                            "Offer",
                            angle.offer if angle else "",
                        ),
                        _format_labelled_list(
                            "Channels",
                            angle.channels if angle else (),
                        ),
                        _format_labelled(
                            "Visual Direction",
                            angle.visual_direction if angle else "",
                        ),
                        _format_labelled(
                            "Notes",
                            angle.notes if angle else "",
                        ),
                        _join_paragraphs(variant_paragraphs),
                    ]
                )
                or "Creative execution detail pending.",
                callout=(
                    angle.cta if angle and angle.cta else strategy.primary_cta
                ),
                image_path=image_path,
            )
        )

    creative_sections.append(
        LongformSection(
            heading="Production Notes",
            body=_join_paragraphs(
                [
                    _format_labelled(
                        "Poster Count",
                        str(
                            sum(
                                1
                                for variant in creative_variants
                                if variant.poster_path.strip()
                            )
                        ),
                    ),
                    _format_labelled(
                        "Variant Count",
                        str(len(creative_variants)),
                    ),
                    _format_labelled_list("Channels", strategy.channels),
                    _format_labelled("Primary CTA", strategy.primary_cta),
                ]
            )
            or "Production notes pending.",
        )
    )
    return creative_sections


def _build_angle_score_charts(
    campaign_angles: list[CampaignAngle],
) -> tuple[ChartSpec, ...]:
    """Create a simple angle-score chart when scores are available."""
    scored_angles = [angle for angle in campaign_angles if angle.score is not None]
    if not scored_angles:
        return ()

    return (
        ChartSpec(
            section_heading="Campaign Angles",
            chart_type="bar",
            data={
                "labels": [angle.name for angle in scored_angles],
                "values": [angle.score for angle in scored_angles],
            },
            title="Campaign Angle Prioritization",
            caption="Relative score assigned to each campaign angle.",
        ),
    )


def build_marketing_plan_documents(
    *,
    title: str,
    subtitle: str,
    package: StructuredNonfictionPackage,
    strategy: MarketingPlanStrategy,
    campaign_angles: list[CampaignAngle],
    creative_variants: list[CreativeVariant],
    content_calendar: list[ContentCalendarEntry],
    extra_sections: tuple[LongformSection, ...],
    extra_charts: tuple[ChartSpec, ...],
) -> tuple[list[StructuredNonfictionDocument], dict[str, object]]:
    """Build combined or bundled marketing-plan documents from structured inputs."""
    if package.profile == "creative_pack" and package.package_mode != "single_document":
        msg = "creative_pack profile only supports package_mode='single_document'"
        raise ValueError(msg)
    if package.package_mode == "document_bundle" and not (
        campaign_angles or creative_variants
    ):
        msg = (
            "campaign_angles or creative_variants are required when "
            "package_mode='document_bundle' for marketing profiles"
        )
        raise ValueError(msg)

    strategy_sections = _build_strategy_sections(
        strategy=strategy,
        campaign_angles=campaign_angles,
        content_calendar=content_calendar,
        extra_sections=extra_sections,
    )
    creative_sections = _build_creative_sections(
        strategy=strategy,
        campaign_angles=campaign_angles,
        creative_variants=creative_variants,
    )
    auto_charts = _build_angle_score_charts(campaign_angles)

    if package.profile == "creative_pack":
        documents = [
            StructuredNonfictionDocument(
                title=title.strip(),
                subtitle=subtitle.strip(),
                slug=slugify(title),
                sections=tuple(creative_sections),
                charts=extra_charts,
            )
        ]
    elif package.package_mode == "document_bundle":
        documents = [
            StructuredNonfictionDocument(
                title=f"{title.strip()} Strategy Plan",
                subtitle=subtitle.strip(),
                slug=slugify(f"{title} strategy plan"),
                sections=tuple(strategy_sections),
                charts=tuple(auto_charts + extra_charts),
            ),
            StructuredNonfictionDocument(
                title=f"{title.strip()} Creative Pack",
                subtitle=subtitle.strip(),
                slug=slugify(f"{title} creative pack"),
                sections=tuple(creative_sections),
                charts=(),
            ),
        ]
    else:
        documents = [
            StructuredNonfictionDocument(
                title=title.strip(),
                subtitle=subtitle.strip(),
                slug=slugify(title),
                sections=tuple(strategy_sections + creative_sections),
                charts=tuple(auto_charts + extra_charts),
            )
        ]

    summary = {
        "campaign_angle_count": len(campaign_angles),
        "creative_variant_count": len(creative_variants),
        "poster_count": sum(
            1
            for variant in creative_variants
            if variant.poster_path.strip()
        ),
        "content_calendar_entry_count": len(content_calendar),
        "document_titles": [document.title for document in documents],
        "angle_names": [angle.name for angle in campaign_angles],
        "poster_paths": [
            variant.poster_path
            for variant in creative_variants
            if variant.poster_path.strip()
        ],
    }
    return documents, summary


def normalize_sections(items: list[dict[str, object]]) -> list[LongformSection]:
    """Normalize nonfiction sections from raw dicts."""
    if not items:
        msg = "sections is required"
        raise ValueError(msg)

    sections: list[LongformSection] = []
    for item in items:
        heading = str(item.get("heading", "")).strip()
        body = str(item.get("body", "")).strip()
        if not heading:
            msg = "section heading is required"
            raise ValueError(msg)
        if not body:
            msg = f"section '{heading}' body is required"
            raise ValueError(msg)
        sections.append(
            LongformSection(
                heading=heading,
                body=body,
                level=max(1, min(int(item.get("level", 1)), 3)),
                callout=str(item.get("callout", "")).strip(),
                image_path=str(item.get("image_path", "")).strip(),
            )
        )
    return sections


def normalize_chart_specs(items: list[dict[str, object]]) -> list[ChartSpec]:
    """Normalize chart specifications from raw dicts."""
    charts: list[ChartSpec] = []
    for item in items:
        section_heading = str(item.get("section_heading", "")).strip()
        chart_type = str(item.get("chart_type", "")).strip()
        data = item.get("data")
        if not section_heading:
            msg = "chart section_heading is required"
            raise ValueError(msg)
        if not chart_type:
            msg = f"chart type is required for section '{section_heading}'"
            raise ValueError(msg)
        if not isinstance(data, dict):
            msg = f"chart data for section '{section_heading}' must be an object"
            raise ValueError(msg)
        charts.append(
            ChartSpec(
                section_heading=section_heading,
                chart_type=chart_type,
                data=data,
                title=str(item.get("title", "")).strip(),
                caption=str(item.get("caption", "")).strip(),
            )
        )
    return charts


def normalize_structured_nonfiction_documents(
    *,
    title: str,
    subtitle: str,
    sections: list[dict[str, object]] | None,
    charts: list[dict[str, object]] | None,
    documents: list[dict[str, object]] | None,
    package: StructuredNonfictionPackage,
) -> list[StructuredNonfictionDocument]:
    """Normalize one or many structured nonfiction documents."""
    if package.package_mode == "single_document":
        if documents:
            msg = "documents cannot be provided when package_mode='single_document'"
            raise ValueError(msg)
        normalized_sections = tuple(normalize_sections(sections or []))
        normalized_charts = tuple(normalize_chart_specs(charts or []))
        return [
            StructuredNonfictionDocument(
                title=title.strip(),
                subtitle=subtitle.strip(),
                slug=slugify(title),
                sections=normalized_sections,
                charts=normalized_charts,
            )
        ]

    if not documents:
        msg = "documents is required when package_mode='document_bundle'"
        raise ValueError(msg)

    normalized_documents: list[StructuredNonfictionDocument] = []
    for idx, document in enumerate(documents, start=1):
        if not isinstance(document, dict):
            msg = f"document bundle entry {idx} must be an object"
            raise ValueError(msg)
        doc_title = str(document.get("title", "")).strip() or f"{title} Part {idx}"
        doc_subtitle = str(document.get("subtitle", "")).strip()
        doc_sections = tuple(
            normalize_sections(document.get("sections", []))  # type: ignore[arg-type]
        )
        doc_charts = tuple(
            normalize_chart_specs(document.get("charts", []))  # type: ignore[arg-type]
        )
        doc_slug = str(document.get("slug", "")).strip() or slugify(doc_title)
        normalized_documents.append(
            StructuredNonfictionDocument(
                title=doc_title,
                subtitle=doc_subtitle,
                slug=doc_slug,
                sections=doc_sections,
                charts=doc_charts,
            )
        )
    return normalized_documents


def normalize_chapters(items: list[dict[str, object]]) -> list[LongformChapter]:
    """Normalize novel chapters from raw dicts."""
    if not items:
        msg = "chapters is required"
        raise ValueError(msg)

    chapters: list[LongformChapter] = []
    for item in items:
        title = str(item.get("title", "")).strip()
        body = str(item.get("body", "")).strip()
        if not title:
            msg = "chapter title is required"
            raise ValueError(msg)
        if not body:
            msg = f"chapter '{title}' body is required"
            raise ValueError(msg)
        chapters.append(
            LongformChapter(
                title=title,
                body=body,
                summary=str(item.get("summary", "")).strip(),
                illustration_path=str(item.get("illustration_path", "")).strip(),
            )
        )
    return chapters


def normalize_spreads(items: list[dict[str, object]]) -> list[LongformSpread]:
    """Normalize children's-book spreads from raw dicts."""
    if not items:
        msg = "spreads is required"
        raise ValueError(msg)

    spreads: list[LongformSpread] = []
    for idx, item in enumerate(items, start=1):
        title = str(item.get("title", f"Spread {idx}")).strip()
        text = str(item.get("text", "")).strip()
        if not text:
            msg = f"spread {idx} text is required"
            raise ValueError(msg)
        spreads.append(
            LongformSpread(
                title=title,
                text=text,
                illustration_path=str(item.get("illustration_path", "")).strip(),
                caption=str(item.get("caption", "")).strip(),
            )
        )
    return spreads


def ensure_output_dir(path: str) -> Path:
    """Create and return the output directory."""
    output_dir = Path(path)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_text(path: Path, content: str) -> str:
    """Write text content and return the string path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def render_markdown_paragraphs(text: str) -> str:
    """Convert raw text blocks into simple HTML paragraphs."""
    paragraphs = [
        chunk.strip()
        for chunk in _NEWLINES_RE.split(text.strip())
        if chunk.strip()
    ]
    return "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)


def render_html_paragraphs(text: str) -> str:
    """Alias for text-to-HTML paragraph rendering used by pipeline forks."""
    return render_markdown_paragraphs(text)


def image_to_data_uri(image_path: str) -> str:
    """Convert a local image path to a data URI for portable embeds."""
    if not image_path:
        return ""

    path = Path(image_path)
    if not path.exists():
        msg = f"image not found: {image_path}"
        raise FileNotFoundError(msg)

    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _fill_template(template_name: str, variables: dict[str, str]) -> str:
    """Load a document template and replace simple {{tokens}}."""
    template_path = _DOC_TEMPLATES / template_name
    content = template_path.read_text(encoding="utf-8")
    for key, value in variables.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    return content


def render_title_page_html(metadata: LongformMetadata, eyebrow: str) -> str:
    """Render a simple reusable title page."""
    subtitle = (
        f"<p class='subtitle'>{html.escape(metadata.subtitle)}</p>"
        if metadata.subtitle
        else ""
    )
    date_html = (
        f"<span><strong>Date</strong><br>{html.escape(metadata.date)}</span>"
        if metadata.date
        else ""
    )
    return (
        "<section class='title-page'>"
        f"<p class='eyebrow'>{html.escape(eyebrow)}</p>"
        f"<h1>{html.escape(metadata.title)}</h1>"
        f"{subtitle}"
        "<div class='meta'>"
        f"<span><strong>Author</strong><br>{html.escape(metadata.author)}</span>"
        f"{date_html}"
        "</div>"
        "</section>"
    )


def wrap_book_shell_html(metadata: LongformMetadata, body_html: str) -> str:
    """Wrap HTML fragments in a styled long-form document shell."""
    return (
        "<html><head><meta charset='UTF-8'>"
        "<style>"
        "body{margin:0;background:#fff;color:#1f2933;"
        f"font-family:{html.escape(metadata.brand['body_font'])};"
        "}"
        ".title-page{display:flex;flex-direction:column;justify-content:center;"
        "min-height:100vh;padding:64px 56px;background:#f8fafc;page-break-after:always;}"
        ".title-page .eyebrow{font-size:12px;letter-spacing:.14em;text-transform:uppercase;"
        f"color:{html.escape(metadata.brand['accent_color'])};margin-bottom:16px;"
        "}"
        ".title-page h1{margin:0 0 12px;font-size:44px;line-height:1.1;"
        f"font-family:{html.escape(metadata.brand['headline_font'])};"
        f"color:{html.escape(metadata.brand['primary_color'])};"
        "}"
        ".title-page .subtitle{font-size:20px;color:#64748b;margin:0 0 28px;}"
        ".title-page .meta{display:flex;gap:24px;color:#475569;font-size:14px;}"
        ".chapter,.spread{padding:56px 56px 72px;page-break-after:always;}"
        ".chapter h2,.spread h2{margin:0 0 18px;font-size:30px;line-height:1.2;"
        f"font-family:{html.escape(metadata.brand['headline_font'])};"
        f"color:{html.escape(metadata.brand['primary_color'])};"
        "}"
        ".chapter .kicker,.spread .kicker{font-size:12px;letter-spacing:.14em;text-transform:uppercase;"
        f"color:{html.escape(metadata.brand['accent_color'])};margin:0 0 10px;"
        "}"
        ".chapter p,.spread p{font-size:18px;line-height:1.7;margin:0 0 16px;}"
        ".callout{margin-top:28px;padding:16px 18px;border-left:4px solid "
        f"{html.escape(metadata.brand['accent_color'])};background:#f8fafc;color:#475569;"
        "}"
        "</style></head><body>"
        f"{body_html}"
        "</body></html>"
    )


def render_nonfiction_html(
    metadata: LongformMetadata,
    sections: list[LongformSection],
    charts_by_section: dict[str, list[dict[str, str]]],
    *,
    include_toc: bool = True,
) -> str:
    """Render nonfiction sections through the report template."""
    body_parts: list[str] = []
    summary_source = sections[0].callout or sections[0].body
    executive_summary = (
        f"<p>{html.escape(summary_source[:320])}</p>"
        if summary_source
        else "<p>Summary unavailable.</p>"
    )

    toc_html = ""
    for section in sections:
        anchor = slugify(section.heading)
        level_tag = f"h{max(2, min(section.level + 1, 4))}"
        section_html = [
            f"<{level_tag} id='{anchor}'>{html.escape(section.heading)}</{level_tag}>"
        ]
        section_html.append(render_markdown_paragraphs(section.body))
        if section.callout:
            section_html.append(
                f"<blockquote class='pull-quote'>{html.escape(section.callout)}</blockquote>"
            )
        if section.image_path:
            data_uri = image_to_data_uri(section.image_path)
            section_html.append(
                "<figure class='embedded-asset'>"
                f"<img src='{data_uri}' alt='{html.escape(section.heading)}' "
                "style='max-width:100%;border-radius:12px;margin:16px 0;' />"
                "</figure>"
            )
        for chart in charts_by_section.get(section.heading, []):
            section_html.append(
                "<figure class='embedded-asset'>"
                f"<img src='{chart['data_uri']}' alt='{html.escape(chart['title'])}' "
                "style='max-width:100%;border-radius:12px;margin:16px 0;' />"
                f"<figcaption style='font-size:13px;color:#666;'>{html.escape(chart['caption'])}</figcaption>"
                "</figure>"
            )
        body_parts.append("".join(section_html))
    if include_toc:
        toc_items = "".join(
            (
                f"<li style='margin:0 0 10px {max(section.level - 1, 0) * 18}px;'>"
                f"<a href='#{slugify(section.heading)}'>{html.escape(section.heading)}</a>"
                "</li>"
            )
            for section in sections
        )
        toc_html = (
            "<nav class='toc' style='page-break-after:always;padding:16px 0 32px;'>"
            "<p class='section-label'>Contents</p>"
            "<h2>Table of Contents</h2>"
            f"<ol style='margin:16px 0 0 20px;line-height:1.6;'>{toc_items}</ol>"
            "</nav>"
        )

    return _fill_template(
        "report.html",
        {
            "title": html.escape(metadata.title),
            "subtitle": html.escape(metadata.subtitle),
            "author": html.escape(metadata.author),
            "date": html.escape(metadata.date),
            "footer": "Generated by Vizier",
            "executive_summary": executive_summary,
            "body": toc_html + "".join(body_parts),
            **metadata.brand,
        },
    )


def render_chapter_html(
    metadata: LongformMetadata,
    *,
    chapter_number: int,
    title: str,
    body: str,
    callout: str = "",
    illustration_path: str = "",
) -> str:
    """Render a stylized chapter fragment for book outputs."""
    body_html = (
        body
        if "<p" in body or "<figure" in body or "<img" in body
        else render_markdown_paragraphs(body)
    )
    if illustration_path:
        data_uri = image_to_data_uri(illustration_path)
        body_html = (
            "<figure style='margin:0 0 24px;'>"
            f"<img src='{data_uri}' alt='{html.escape(title)}' "
            "style='width:100%;max-height:320px;object-fit:cover;border-radius:14px;' />"
            "</figure>"
            + body_html
        )

    callout_html = ""
    if callout:
        callout_html = f"<aside class='callout'>{html.escape(callout)}</aside>"

    return (
        "<section class='chapter'>"
        f"<p class='kicker'>Chapter {chapter_number}</p>"
        f"<h2>{html.escape(title)}</h2>"
        f"{body_html}"
        f"{callout_html}"
        "</section>"
    )


def render_children_spread_html(
    metadata: LongformMetadata,
    *,
    spread_number: int,
    spread: LongformSpread,
) -> str:
    """Render a picture-book spread as standalone HTML."""
    illustration = ""
    if spread.illustration_path:
        illustration_uri = image_to_data_uri(spread.illustration_path)
        illustration = (
            "<figure style='margin:0 0 24px;'>"
            f"<img src='{illustration_uri}' alt='{html.escape(spread.title)}' "
            "style='width:100%;max-height:360px;object-fit:cover;border-radius:20px;"
            "box-shadow:0 20px 50px rgba(0,0,0,0.12);' />"
            f"<figcaption style='margin-top:10px;font-size:13px;color:#666;'>{html.escape(spread.caption)}</figcaption>"
            "</figure>"
        )

    return (
        "<section style='page-break-after:always;padding:48px;min-height:100vh;"
        f"background:{html.escape(metadata.brand['secondary_color'])};'>"
        f"<p style='font-size:12px;letter-spacing:0.14em;text-transform:uppercase;"
        f"color:{html.escape(metadata.brand['accent_color'])};margin-bottom:12px;'>"
        f"Spread {spread_number}</p>"
        f"<h1 style='font-family:{html.escape(metadata.brand['headline_font'])};"
        f"color:{html.escape(metadata.brand['primary_color'])};margin:0 0 24px;'>"
        f"{html.escape(spread.title)}</h1>"
        f"{illustration}"
        f"<div style='font-family:{html.escape(metadata.brand['body_font'])};font-size:20px;"
        "line-height:1.7;color:#222;max-width:38rem;'>"
        f"{render_markdown_paragraphs(spread.text)}"
        "</div>"
        "</section>"
    )


def serialize_quality_report(
    *,
    pipeline: str,
    properties: list[QualityProperty],
) -> dict[str, object]:
    """Convert a quality score into the repo's plain-dict response shape."""
    score = compute_score(properties, pipeline=pipeline)
    return {
        "passed": score.passed,
        "score": score.score,
        "layer": "output_verification",
        "properties": [
            {
                "name": prop.name,
                "passed": prop.passed,
                "detail": prop.detail,
                "is_gate": prop.is_gate,
            }
            for prop in score.properties
        ],
    }
