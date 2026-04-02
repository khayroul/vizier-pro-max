"""Structured nonfiction family for strategy, report, and ebook-style documents."""
from __future__ import annotations

import csv
import json
import shutil
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any

import structlog

from middleware.quality_scorer import QualityProperty
from pipelines.longform.models import CreativeVariant
from pipelines.longform.spine import (
    build_metadata,
    build_marketing_plan_documents,
    build_structured_nonfiction_package,
    ensure_output_dir,
    image_to_data_uri,
    normalize_campaign_angles,
    normalize_chart_specs,
    normalize_content_calendar_entries,
    normalize_creative_variants,
    normalize_marketing_strategy,
    normalize_sections,
    normalize_structured_nonfiction_documents,
    render_chapter_html,
    render_html_paragraphs,
    render_nonfiction_html,
    serialize_quality_report,
    slugify,
    uses_marketing_workflow,
    write_text,
)
from scripts.document.assemble_epub import run as assemble_epub
from scripts.document.render_pdf import run as render_pdf
from scripts.research.compose_report import run as compose_report
from scripts.research.render_chart import run as chart_run

logger = structlog.get_logger(__name__)


def poster_run(**kwargs: object) -> dict[str, object]:
    """Lazy poster-generation wrapper to keep the import optional."""
    from pipelines.poster_generate import run as _poster_run

    return _poster_run(**kwargs)


def gamma_generate_run(**kwargs: object) -> dict[str, object]:
    """Lazy Gamma wrapper to keep the import optional."""
    from scripts.document.gamma_generate import run as _gamma_run

    return _gamma_run(**kwargs)


def _has_marketing_inputs(
    *,
    strategy: dict[str, object] | None,
    campaign_angles: list[dict[str, object]] | None,
    creative_variants: list[dict[str, object]] | None,
    content_calendar: list[dict[str, object]] | None,
) -> bool:
    """Return whether structured marketing inputs were provided."""
    return any((strategy, campaign_angles, creative_variants, content_calendar))


def _materialize_creative_variants(
    *,
    creative_variants: list[CreativeVariant],
    campaign_angles: list[Any],
    output_dir: Path,
    generate_posters: bool,
    poster_defaults: dict[str, object] | None,
) -> list[CreativeVariant]:
    """Generate poster assets for creative variants that do not already have them."""
    if not generate_posters or not creative_variants:
        return creative_variants

    defaults = poster_defaults or {}
    assets_dir = output_dir / "creative-assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    angle_lookup = {angle.name: angle for angle in campaign_angles}

    rendered_variants: list[CreativeVariant] = []
    for idx, variant in enumerate(creative_variants, start=1):
        if variant.poster_path:
            rendered_variants.append(variant)
            continue

        angle = angle_lookup.get(variant.angle_name)
        prompt = (
            variant.image_prompt
            or (angle.visual_direction if angle else "")
            or f"Editorial poster for {variant.angle_name}"
        )
        output_path = assets_dir / f"{slugify(f'{variant.angle_name} {variant.channel} {idx}')}.png"
        poster_kwargs = {
            **defaults,
            "headline": variant.headline or variant.angle_name,
            "body": variant.body or (angle.promise if angle else ""),
            "cta": variant.cta or (angle.cta if angle else "") or "Learn More",
            "image_prompt": prompt,
            "output_path": str(output_path),
        }
        poster_result = poster_run(**poster_kwargs)
        rendered_variants.append(
            replace(
                variant,
                poster_path=str(poster_result["poster_path"]),
                image_prompt=prompt,
            )
        )
    return rendered_variants


def _build_variant_notes(
    *,
    strategy: Any,
    angle: Any | None,
    variant: CreativeVariant,
    poster_path: str,
) -> str:
    """Render an operator-friendly markdown summary for one creative variant."""
    lines = [
        f"# {variant.headline or variant.angle_name}",
        "",
        f"- Angle: {variant.angle_name}",
        f"- Channel: {variant.channel or 'General'}",
        f"- CTA: {variant.cta or strategy.primary_cta or 'Not specified'}",
    ]
    if poster_path:
        lines.append(f"- Poster: {poster_path}")
    if angle is not None and angle.visual_direction:
        lines.append(f"- Visual Direction: {angle.visual_direction}")
    if variant.image_prompt:
        lines.append(f"- Image Prompt: {variant.image_prompt}")
    if angle is not None and angle.promise:
        lines.append(f"- Promise: {angle.promise}")
    if angle is not None and angle.proof:
        lines.append(f"- Proof: {angle.proof}")
    if angle is not None and angle.pain_point:
        lines.append(f"- Pain Point: {angle.pain_point}")
    if variant.notes:
        lines.extend(["", "## Notes", "", variant.notes])
    if variant.body:
        lines.extend(["", "## Body Copy", "", variant.body])
    return "\n".join(lines).strip() + "\n"


def _write_operations_csv(entries: list[dict[str, object]]) -> str:
    """Serialize operational creative entries as CSV."""
    buffer = StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "angle_name",
            "channel",
            "headline",
            "body",
            "cta",
            "poster_path",
            "asset_dir",
            "client_asset_dir",
            "internal_asset_dir",
            "copy_json_path",
            "notes_path",
            "score",
        ],
    )
    writer.writeheader()
    for entry in entries:
        writer.writerow(
            {
                "angle_name": entry["angle_name"],
                "channel": entry["channel"],
                "headline": entry["headline"],
                "body": entry["body"],
                "cta": entry["cta"],
                "poster_path": entry["poster_path"],
                "asset_dir": entry["asset_dir"],
                "client_asset_dir": entry["client_asset_dir"],
                "internal_asset_dir": entry["internal_asset_dir"],
                "copy_json_path": entry["copy_json_path"],
                "notes_path": entry["notes_path"],
                "score": entry["score"],
            }
        )
    return buffer.getvalue()


def _export_operational_assets(
    *,
    title: str,
    output_dir: Path,
    strategy: Any,
    campaign_angles: list[Any],
    creative_variants: list[CreativeVariant],
) -> tuple[list[CreativeVariant], dict[str, object]]:
    """Export one folder per creative variant plus a bundle manifest."""
    bundle_dir = output_dir / "operational-assets"
    client_bundle_dir = bundle_dir / "client"
    internal_bundle_dir = bundle_dir / "internal"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    client_bundle_dir.mkdir(parents=True, exist_ok=True)
    internal_bundle_dir.mkdir(parents=True, exist_ok=True)
    angle_lookup = {angle.name: angle for angle in campaign_angles}
    angle_counters: dict[str, int] = {}
    manifest_entries: list[dict[str, object]] = []
    updated_variants: list[CreativeVariant] = []

    for variant in creative_variants:
        angle_slug = slugify(variant.angle_name)
        angle_counters[angle_slug] = angle_counters.get(angle_slug, 0) + 1
        variant_index = angle_counters[angle_slug]
        channel_slug = slugify(variant.channel or "general")
        client_variant_dir = (
            client_bundle_dir / angle_slug / f"{variant_index:02d}-{channel_slug}"
        )
        internal_variant_dir = (
            internal_bundle_dir / angle_slug / f"{variant_index:02d}-{channel_slug}"
        )
        client_variant_dir.mkdir(parents=True, exist_ok=True)
        internal_variant_dir.mkdir(parents=True, exist_ok=True)

        poster_path = ""
        if variant.poster_path:
            source_path = Path(variant.poster_path)
            if not source_path.exists():
                msg = f"poster asset not found: {variant.poster_path}"
                raise FileNotFoundError(msg)
            suffix = source_path.suffix or ".png"
            copied_poster_path = client_variant_dir / f"poster{suffix}"
            shutil.copy2(source_path, copied_poster_path)
            poster_path = str(copied_poster_path)

        angle = angle_lookup.get(variant.angle_name)
        copy_payload = {
            "angle_name": variant.angle_name,
            "channel": variant.channel,
            "headline": variant.headline,
            "body": variant.body,
            "cta": variant.cta or strategy.primary_cta,
            "image_prompt": variant.image_prompt,
            "poster_path": poster_path,
            "score": variant.score,
            "notes": variant.notes,
            "strategy_context": {
                "objective": strategy.objective,
                "offer": strategy.offer,
                "primary_cta": strategy.primary_cta,
            },
            "angle_context": (
                {
                    "promise": angle.promise,
                    "proof": angle.proof,
                    "pain_point": angle.pain_point,
                    "message": angle.message,
                    "visual_direction": angle.visual_direction,
                }
                if angle is not None
                else {}
            ),
        }
        copy_json_path = internal_variant_dir / "copy.json"
        notes_path = internal_variant_dir / "notes.md"
        write_text(copy_json_path, json.dumps(copy_payload, indent=2))
        write_text(
            notes_path,
            _build_variant_notes(
                strategy=strategy,
                angle=angle,
                variant=variant,
                poster_path=poster_path,
            ),
        )

        manifest_entry = {
            "angle_name": variant.angle_name,
            "channel": variant.channel,
            "headline": variant.headline,
            "body": variant.body,
            "cta": variant.cta or strategy.primary_cta,
            "poster_path": poster_path,
            "asset_dir": str(client_variant_dir),
            "client_asset_dir": str(client_variant_dir),
            "internal_asset_dir": str(internal_variant_dir),
            "copy_json_path": str(copy_json_path),
            "notes_path": str(notes_path),
            "score": variant.score if variant.score is not None else "",
        }
        manifest_entries.append(manifest_entry)
        updated_variants.append(
            replace(
                variant,
                poster_path=poster_path or variant.poster_path,
                cta=variant.cta or strategy.primary_cta,
            )
        )

    manifest_path = internal_bundle_dir / "manifest.json"
    captions_csv_path = internal_bundle_dir / "captions.csv"
    write_text(
        manifest_path,
        json.dumps(
            {
                "title": title,
                "variant_count": len(manifest_entries),
                "poster_count": sum(
                    1 for entry in manifest_entries if entry["poster_path"]
                ),
                "assets": manifest_entries,
            },
            indent=2,
        ),
    )
    write_text(captions_csv_path, _write_operations_csv(manifest_entries))

    return updated_variants, {
        "bundle_dir": str(bundle_dir),
        "client_bundle_dir": str(client_bundle_dir),
        "internal_bundle_dir": str(internal_bundle_dir),
        "manifest_path": str(manifest_path),
        "captions_csv_path": str(captions_csv_path),
        "variant_count": len(manifest_entries),
        "poster_count": sum(1 for entry in manifest_entries if entry["poster_path"]),
        "client_poster_paths": [
            entry["poster_path"]
            for entry in manifest_entries
            if entry["poster_path"]
        ],
        "assets": manifest_entries,
    }


def _resolve_structured_documents(
    *,
    metadata: Any,
    package: Any,
    sections: list[dict[str, object]] | None,
    charts: list[dict[str, object]] | None,
    documents: list[dict[str, object]] | None,
    strategy: dict[str, object] | None,
    campaign_angles: list[dict[str, object]] | None,
    creative_variants: list[dict[str, object]] | None,
    content_calendar: list[dict[str, object]] | None,
    generate_posters: bool,
    poster_defaults: dict[str, object] | None,
    output_dir: Path,
    export_operational_assets: bool,
) -> tuple[list[Any], dict[str, object] | None, dict[str, object] | None]:
    """Resolve documents either from generic sections or the marketing workflow."""
    has_marketing_inputs = _has_marketing_inputs(
        strategy=strategy,
        campaign_angles=campaign_angles,
        creative_variants=creative_variants,
        content_calendar=content_calendar,
    )
    if has_marketing_inputs and not uses_marketing_workflow(package.profile):
        msg = (
            "strategy, campaign_angles, creative_variants, and content_calendar "
            "are only supported for marketing profiles"
        )
        raise ValueError(msg)

    if has_marketing_inputs:
        if documents:
            msg = "documents cannot be combined with structured marketing inputs"
            raise ValueError(msg)
        normalized_strategy = normalize_marketing_strategy(strategy)
        normalized_angles = normalize_campaign_angles(campaign_angles)
        normalized_variants = normalize_creative_variants(
            creative_variants,
            angles=normalized_angles,
            strategy=normalized_strategy,
        )
        normalized_variants = _materialize_creative_variants(
            creative_variants=normalized_variants,
            campaign_angles=normalized_angles,
            output_dir=output_dir,
            generate_posters=generate_posters,
            poster_defaults=poster_defaults,
        )
        operational_assets = None
        if export_operational_assets and normalized_variants:
            normalized_variants, operational_assets = _export_operational_assets(
                title=metadata.title,
                output_dir=output_dir,
                strategy=normalized_strategy,
                campaign_angles=normalized_angles,
                creative_variants=normalized_variants,
            )
        normalized_calendar = normalize_content_calendar_entries(content_calendar)
        extra_sections = tuple(normalize_sections(sections or [])) if sections else ()
        extra_charts = tuple(normalize_chart_specs(charts or []))
        documents, marketing_summary = build_marketing_plan_documents(
            title=metadata.title,
            subtitle=metadata.subtitle,
            package=package,
            strategy=normalized_strategy,
            campaign_angles=normalized_angles,
            creative_variants=normalized_variants,
            content_calendar=normalized_calendar,
            extra_sections=extra_sections,
            extra_charts=extra_charts,
        )
        if operational_assets is not None:
            marketing_summary = {
                **marketing_summary,
                "operational_assets": operational_assets,
            }
        return documents, marketing_summary, operational_assets

    normalized_documents = normalize_structured_nonfiction_documents(
        title=metadata.title,
        subtitle=metadata.subtitle,
        sections=sections,
        charts=charts,
        documents=documents,
        package=package,
    )
    return normalized_documents, None, None


def _build_markdown_body(
    section_heading: str,
    body: str,
    chart_paths: list[dict[str, str]],
) -> str:
    """Append chart references to section markdown."""
    rendered = body.strip()
    for chart in chart_paths:
        caption = chart["caption"] or chart["title"] or section_heading
        rendered += f"\n\n![{caption}]({chart['file_path']})"
    return rendered


def _build_epub_body_html(
    body: str,
    chart_paths: list[dict[str, str]],
) -> str:
    """Build EPUB-ready HTML with inline chart images."""
    rendered = render_html_paragraphs(body)
    for chart in chart_paths:
        rendered += (
            "<figure style='margin:24px 0;'>"
            f"<img src='{chart['data_uri']}' alt='{chart['title']}' "
            "style='max-width:100%;border-radius:12px;' />"
            f"<figcaption style='font-size:13px;color:#666;'>{chart['caption']}</figcaption>"
            "</figure>"
        )
    return rendered


def _render_document(
    *,
    metadata: Any,
    document: Any,
    package: Any,
    output_dir: Path,
    export_pdf: bool,
    export_epub: bool,
) -> dict[str, Any]:
    """Render one structured nonfiction document."""
    document_metadata = build_metadata(
        title=document.title,
        author=metadata.author,
        subtitle=document.subtitle or metadata.subtitle,
        date=metadata.date,
        cover_path=metadata.cover_path,
        brand=metadata.brand,
    )
    doc_dir = output_dir / document.slug
    assets_dir = doc_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    chart_lookup = {section.heading: [] for section in document.sections}
    for idx, chart in enumerate(document.charts, start=1):
        if chart.section_heading not in chart_lookup:
            msg = (
                f"chart section_heading '{chart.section_heading}' does not match any section "
                f"in document '{document.title}'"
            )
            raise ValueError(msg)

        chart_title = chart.title or f"{chart.section_heading} Chart"
        chart_path = assets_dir / f"chart_{idx}.png"
        chart_result = chart_run(
            chart_type=chart.chart_type,
            data=chart.data,
            output_path=str(chart_path),
            title=chart_title,
        )
        chart_lookup[chart.section_heading].append(
            {
                "title": chart_title,
                "caption": chart.caption,
                "file_path": chart_result["file_path"],
                "data_uri": image_to_data_uri(chart_result["file_path"]),
            }
        )

    report_html = render_nonfiction_html(
        document_metadata,
        list(document.sections),
        chart_lookup,
        include_toc=package.include_toc,
    )
    html_path = doc_dir / "document.html"
    markdown_path = doc_dir / "document.md"
    epub_path = doc_dir / "document.epub"
    pdf_path = doc_dir / "document.pdf"
    write_text(html_path, report_html)

    markdown_sections = [
        {
            "heading": section.heading,
            "level": section.level,
            "body": _build_markdown_body(
                section.heading,
                section.body,
                chart_lookup.get(section.heading, []),
            ),
        }
        for section in document.sections
    ]
    compose_report(
        title=document_metadata.title,
        subtitle=document_metadata.subtitle,
        author=document_metadata.author,
        date=document_metadata.date,
        client_name="",
        sections=markdown_sections,
        output_format="markdown",
        output_path=str(markdown_path),
    )

    result: dict[str, Any] = {
        "slug": document.slug,
        "title": document.title,
        "subtitle": document.subtitle,
        "section_count": len(document.sections),
        "chart_count": sum(len(items) for items in chart_lookup.values()),
        "html_path": str(html_path),
        "markdown_path": str(markdown_path),
        "chart_paths": [
            chart["file_path"]
            for items in chart_lookup.values()
            for chart in items
        ],
    }

    if export_pdf:
        render_pdf(html_content=report_html, output_path=str(pdf_path))
        result["pdf_path"] = str(pdf_path)

    if export_epub:
        chapters = [
            {
                "title": section.heading,
                "html": render_chapter_html(
                    document_metadata,
                    chapter_number=idx,
                    title=section.heading,
                    body=_build_epub_body_html(
                        section.body,
                        chart_lookup.get(section.heading, []),
                    ),
                    callout=section.callout,
                    illustration_path=section.image_path,
                ),
            }
            for idx, section in enumerate(document.sections, start=1)
        ]
        assemble_epub(
            title=document_metadata.title,
            author=document_metadata.author,
            chapters=chapters,
            cover_path=document_metadata.cover_path,
            output_path=str(epub_path),
        )
        result["epub_path"] = str(epub_path)

    quality_props = [
        QualityProperty(
            name="section_count",
            passed=len(document.sections) >= 3,
            pass_delta=1.5,
            fail_delta=1.5,
            detail=f"found {len(document.sections)} sections",
            is_gate=True,
        ),
        QualityProperty(
            name="chart_coverage",
            passed=bool(document.charts) or package.profile in {
                "marketing_plan",
                "campaign_dossier",
                "proposal",
                "content_calendar",
                "creative_pack",
            },
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"generated {result['chart_count']} charts",
        ),
        QualityProperty(
            name="toc_enabled",
            passed=package.include_toc,
            pass_delta=1.0,
            fail_delta=0.5,
            detail=f"include_toc={package.include_toc}",
        ),
        QualityProperty(
            name="pdf_export",
            passed=not export_pdf or pdf_path.exists(),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"pdf export requested={export_pdf}",
        ),
        QualityProperty(
            name="epub_export",
            passed=not export_epub or epub_path.exists(),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"epub export requested={export_epub}",
        ),
    ]
    result["quality_report"] = serialize_quality_report(
        pipeline="structured_nonfiction_generate",
        properties=quality_props,
    )
    return result


def _build_gamma_input_text(
    *,
    metadata: Any,
    rendered_documents: list[dict[str, Any]],
) -> str:
    """Build combined markdown input for Gamma from rendered documents."""
    parts = [f"# {metadata.title}"]
    if metadata.subtitle:
        parts.extend(["", metadata.subtitle])

    for document in rendered_documents:
        markdown_path = Path(str(document["markdown_path"]))
        markdown_text = markdown_path.read_text(encoding="utf-8").strip()
        parts.extend(
            [
                "",
                f"## {document['title']}",
                "",
                markdown_text,
            ]
        )

    return "\n".join(part for part in parts if part is not None).strip()


def _build_gamma_additional_instructions(
    *,
    profile: str,
    gamma_format: str,
    custom_instructions: str,
) -> str:
    """Build default Gamma instructions and append any custom guidance."""
    if gamma_format == "presentation":
        if profile in {"marketing_plan", "campaign_dossier", "creative_pack"}:
            base = (
                "Create a polished client-facing presentation deck. Keep each card concise, "
                "commercially sharp, and premium in tone. Structure the deck for decision-makers "
                "and cover executive summary, audience, offer, positioning, campaign angles, "
                "channel plan, creative direction, and next steps."
            )
        else:
            base = (
                "Create a polished presentation deck that summarizes the source material clearly. "
                "Use concise card titles, short body copy, and preserve important numbers, "
                "recommendations, and action items."
            )
    else:
        base = (
            "Create a polished Gamma artifact from the source material. Preserve the core structure, "
            "improve readability, and keep the tone professional."
        )

    extra = custom_instructions.strip()
    if extra:
        return f"{base}\n\nAdditional instructions:\n{extra}"
    return base


def _export_gamma_artifact(
    *,
    metadata: Any,
    package: Any,
    rendered_documents: list[dict[str, Any]],
    output_dir: Path,
    gamma_format: str,
    gamma_text_mode: str,
    gamma_export_as: str,
    gamma_theme_id: str,
    gamma_folder_ids: list[str] | None,
    gamma_num_cards: int | None,
    gamma_card_split: str,
    gamma_card_dimensions: str,
    gamma_image_source: str,
    gamma_image_model: str,
    gamma_image_style: str,
    gamma_image_style_preset: str,
    gamma_text_amount: str,
    gamma_tone: str,
    gamma_audience: str,
    gamma_language: str,
    gamma_additional_instructions: str,
    gamma_template_id: str,
    gamma_template_prompt: str,
    gamma_header_footer: dict[str, Any] | None,
    gamma_card_options: dict[str, Any] | None,
    gamma_sharing_options: dict[str, Any] | None,
    gamma_output_path: str,
) -> dict[str, Any]:
    """Export rendered documents to Gamma and return the generation details."""
    input_text = _build_gamma_input_text(
        metadata=metadata,
        rendered_documents=rendered_documents,
    )
    output_path = gamma_output_path.strip()
    if not output_path and gamma_export_as.strip():
        output_path = str(
            output_dir / f"{slugify(metadata.title)}-gamma.{gamma_export_as.strip()}"
        )

    effective_num_cards = gamma_num_cards
    if effective_num_cards is None and gamma_format == "presentation":
        effective_num_cards = 10 if package.profile in {
            "marketing_plan",
            "campaign_dossier",
            "creative_pack",
        } else 8

    return gamma_generate_run(
        input_text=input_text,
        text_mode=gamma_text_mode,
        format=gamma_format,
        additional_instructions=_build_gamma_additional_instructions(
            profile=package.profile,
            gamma_format=gamma_format,
            custom_instructions=gamma_additional_instructions,
        ),
        export_as=gamma_export_as,
        theme_id=gamma_theme_id,
        folder_ids=gamma_folder_ids,
        num_cards=effective_num_cards,
        card_split=gamma_card_split,
        card_dimensions=gamma_card_dimensions,
        image_source=gamma_image_source,
        image_model=gamma_image_model,
        image_style=gamma_image_style,
        image_style_preset=gamma_image_style_preset,
        text_amount=gamma_text_amount,
        tone=gamma_tone,
        audience=gamma_audience,
        language=gamma_language,
        template_gamma_id=gamma_template_id,
        template_prompt=gamma_template_prompt,
        header_footer=gamma_header_footer,
        card_options=gamma_card_options,
        sharing_options=gamma_sharing_options,
        output_path=output_path,
    )


def run(
    *,
    title: str,
    author: str,
    sections: list[dict[str, object]] | None = None,
    charts: list[dict[str, object]] | None = None,
    output_dir: str = "output/longform/structured-nonfiction",
    subtitle: str = "",
    date: str = "",
    cover_path: str = "",
    brand: dict[str, object] | None = None,
    export_pdf: bool = True,
    export_epub: bool = True,
    profile: str = "ebook",
    package_mode: str = "single_document",
    include_toc: bool = True,
    documents: list[dict[str, object]] | None = None,
    strategy: dict[str, object] | None = None,
    campaign_angles: list[dict[str, object]] | None = None,
    creative_variants: list[dict[str, object]] | None = None,
    content_calendar: list[dict[str, object]] | None = None,
    generate_posters: bool = False,
    poster_defaults: dict[str, object] | None = None,
    export_operational_assets: bool = True,
    export_gamma: bool = False,
    gamma_format: str = "presentation",
    gamma_text_mode: str = "condense",
    gamma_export_as: str = "pdf",
    gamma_theme_id: str = "",
    gamma_folder_ids: list[str] | None = None,
    gamma_num_cards: int | None = None,
    gamma_card_split: str = "",
    gamma_card_dimensions: str = "",
    gamma_image_source: str = "noImages",
    gamma_image_model: str = "",
    gamma_image_style: str = "",
    gamma_image_style_preset: str = "",
    gamma_text_amount: str = "",
    gamma_tone: str = "",
    gamma_audience: str = "",
    gamma_language: str = "",
    gamma_additional_instructions: str = "",
    gamma_template_id: str = "",
    gamma_template_prompt: str = "",
    gamma_header_footer: dict[str, Any] | None = None,
    gamma_card_options: dict[str, Any] | None = None,
    gamma_sharing_options: dict[str, Any] | None = None,
    gamma_output_path: str = "",
) -> dict[str, Any]:
    """Generate one or more structured nonfiction documents."""
    if poster_defaults is not None and not isinstance(poster_defaults, dict):
        msg = "poster_defaults must be an object"
        raise ValueError(msg)

    metadata = build_metadata(
        title=title,
        author=author,
        subtitle=subtitle,
        date=date,
        cover_path=cover_path,
        brand=brand,
    )
    package = build_structured_nonfiction_package(
        profile=profile,
        package_mode=package_mode,
        include_toc=include_toc,
    )
    out_dir = ensure_output_dir(output_dir)
    normalized_documents, marketing_summary, operational_assets = _resolve_structured_documents(
        metadata=metadata,
        package=package,
        sections=sections,
        charts=charts,
        documents=documents,
        strategy=strategy,
        campaign_angles=campaign_angles,
        creative_variants=creative_variants,
        content_calendar=content_calendar,
        generate_posters=generate_posters,
        poster_defaults=poster_defaults,
        output_dir=out_dir,
        export_operational_assets=export_operational_assets,
    )

    rendered_documents = [
        _render_document(
            metadata=metadata,
            document=document,
            package=package,
            output_dir=out_dir,
            export_pdf=export_pdf,
            export_epub=export_epub,
        )
        for document in normalized_documents
    ]

    result: dict[str, Any] = {
        "status": "completed",
        "title": metadata.title,
        "profile": package.profile,
        "package_mode": package.package_mode,
        "document_count": len(rendered_documents),
        "documents": rendered_documents,
    }
    if marketing_summary is not None:
        result["marketing_summary"] = marketing_summary
        result["campaign_angle_count"] = marketing_summary["campaign_angle_count"]
        result["creative_variant_count"] = marketing_summary["creative_variant_count"]
        result["poster_count"] = marketing_summary["poster_count"]
        result["poster_paths"] = marketing_summary["poster_paths"]
    if operational_assets is not None:
        result["operational_assets"] = operational_assets
        result["operational_bundle_dir"] = operational_assets["bundle_dir"]
        result["client_bundle_dir"] = operational_assets["client_bundle_dir"]
        result["internal_bundle_dir"] = operational_assets["internal_bundle_dir"]

    gamma_generation: dict[str, Any] | None = None
    if export_gamma:
        gamma_generation = _export_gamma_artifact(
            metadata=metadata,
            package=package,
            rendered_documents=rendered_documents,
            output_dir=out_dir,
            gamma_format=gamma_format,
            gamma_text_mode=gamma_text_mode,
            gamma_export_as=gamma_export_as,
            gamma_theme_id=gamma_theme_id,
            gamma_folder_ids=gamma_folder_ids,
            gamma_num_cards=gamma_num_cards,
            gamma_card_split=gamma_card_split,
            gamma_card_dimensions=gamma_card_dimensions,
            gamma_image_source=gamma_image_source,
            gamma_image_model=gamma_image_model,
            gamma_image_style=gamma_image_style,
            gamma_image_style_preset=gamma_image_style_preset,
            gamma_text_amount=gamma_text_amount,
            gamma_tone=gamma_tone,
            gamma_audience=gamma_audience,
            gamma_language=gamma_language,
            gamma_additional_instructions=gamma_additional_instructions,
            gamma_template_id=gamma_template_id,
            gamma_template_prompt=gamma_template_prompt,
            gamma_header_footer=gamma_header_footer,
            gamma_card_options=gamma_card_options,
            gamma_sharing_options=gamma_sharing_options,
            gamma_output_path=gamma_output_path,
        )
        result["gamma_generation"] = gamma_generation
        result["gamma_url"] = gamma_generation.get("gamma_url", "")
        if gamma_generation.get("file_path"):
            result["gamma_file_path"] = gamma_generation["file_path"]

    if package.package_mode == "single_document":
        primary = rendered_documents[0]
        result.update({
            "section_count": primary["section_count"],
            "chart_count": primary["chart_count"],
            "html_path": primary["html_path"],
            "markdown_path": primary["markdown_path"],
            "chart_paths": primary["chart_paths"],
        })
        if "pdf_path" in primary:
            result["pdf_path"] = primary["pdf_path"]
        if "epub_path" in primary:
            result["epub_path"] = primary["epub_path"]

    passing_documents = sum(
        1
        for document in rendered_documents
        if document["quality_report"]["passed"]
    )
    package_props = [
        QualityProperty(
            name="document_count",
            passed=len(rendered_documents) >= 1,
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"rendered {len(rendered_documents)} documents",
            is_gate=True,
        ),
        QualityProperty(
            name="profile_supported",
            passed=True,
            pass_delta=1.0,
            fail_delta=0.0,
            detail=f"profile={package.profile}",
        ),
        QualityProperty(
            name="document_quality",
            passed=passing_documents == len(rendered_documents),
            pass_delta=1.5,
            fail_delta=1.5,
            detail=(
                f"{passing_documents}/{len(rendered_documents)} documents passed"
            ),
        ),
    ]
    if marketing_summary is not None:
        package_props.extend(
            [
                QualityProperty(
                    name="campaign_angles",
                    passed=marketing_summary["campaign_angle_count"] >= 1,
                    pass_delta=1.0,
                    fail_delta=1.0,
                    detail=(
                        f"campaign angles={marketing_summary['campaign_angle_count']}"
                    ),
                    is_gate=True,
                ),
                QualityProperty(
                    name="creative_variants",
                    passed=marketing_summary["creative_variant_count"] >= 1,
                    pass_delta=1.0,
                    fail_delta=1.0,
                    detail=(
                        "creative variants="
                        f"{marketing_summary['creative_variant_count']}"
                    ),
                    is_gate=True,
                ),
                QualityProperty(
                    name="poster_assets",
                    passed=(
                        not generate_posters
                        or marketing_summary["poster_count"]
                        >= marketing_summary["creative_variant_count"]
                    ),
                    pass_delta=1.0,
                    fail_delta=1.0,
                    detail=f"poster count={marketing_summary['poster_count']}",
                ),
            ]
        )
    if operational_assets is not None:
        package_props.append(
            QualityProperty(
                name="operational_asset_bundle",
                passed=(
                    Path(str(operational_assets["manifest_path"])).exists()
                    and Path(str(operational_assets["captions_csv_path"])).exists()
                    and Path(str(operational_assets["client_bundle_dir"])).exists()
                ),
                pass_delta=1.0,
                fail_delta=1.0,
                detail=(
                    "client bundle="
                    f"{operational_assets['client_bundle_dir']}"
                ),
            )
        )
    if export_gamma:
        package_props.append(
            QualityProperty(
                name="gamma_export",
                passed=bool(gamma_generation and gamma_generation.get("gamma_url")),
                pass_delta=1.0,
                fail_delta=1.0,
                detail=(
                    f"gamma_url={gamma_generation.get('gamma_url', '')}"
                    if gamma_generation is not None
                    else "gamma export not attempted"
                ),
            )
        )
    result["quality_report"] = serialize_quality_report(
        pipeline="structured_nonfiction_generate",
        properties=package_props,
    )

    logger.info(
        "structured_nonfiction_generated",
        output_dir=str(out_dir),
        profile=package.profile,
        package_mode=package.package_mode,
        document_count=len(rendered_documents),
        marketing_summary=marketing_summary,
    )
    return result
