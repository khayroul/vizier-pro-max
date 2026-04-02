"""Long-form nonfiction ebook pipeline with chart-aware exports."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from middleware.quality_scorer import QualityProperty
from pipelines.longform.spine import (
    build_metadata,
    ensure_output_dir,
    image_to_data_uri,
    normalize_chart_specs,
    normalize_sections,
    render_chapter_html,
    render_html_paragraphs,
    render_nonfiction_html,
    serialize_quality_report,
    write_text,
)
from scripts.document.assemble_epub import run as assemble_epub
from scripts.document.render_pdf import run as render_pdf
from scripts.research.compose_report import run as compose_report
from scripts.research.render_chart import run as chart_run

logger = structlog.get_logger(__name__)


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


def run(
    *,
    title: str,
    author: str,
    sections: list[dict[str, object]],
    charts: list[dict[str, object]] | None = None,
    output_dir: str = "output/longform/nonfiction",
    subtitle: str = "",
    date: str = "",
    cover_path: str = "",
    brand: dict[str, object] | None = None,
    export_pdf: bool = True,
    export_epub: bool = True,
) -> dict[str, Any]:
    """Generate a chart-aware nonfiction ebook package."""
    metadata = build_metadata(
        title=title,
        author=author,
        subtitle=subtitle,
        date=date,
        cover_path=cover_path,
        brand=brand,
    )
    normalized_sections = normalize_sections(sections)
    normalized_charts = normalize_chart_specs(charts or [])
    out_dir = ensure_output_dir(output_dir)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    chart_lookup = {section.heading: [] for section in normalized_sections}
    for idx, chart in enumerate(normalized_charts, start=1):
        if chart.section_heading not in chart_lookup:
            msg = (
                f"chart section_heading '{chart.section_heading}' does not match any section"
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

    report_html = render_nonfiction_html(metadata, normalized_sections, chart_lookup)
    html_path = out_dir / "book.html"
    markdown_path = out_dir / "book.md"
    epub_path = out_dir / "book.epub"
    pdf_path = out_dir / "book.pdf"

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
        for section in normalized_sections
    ]
    compose_report(
        title=metadata.title,
        subtitle=metadata.subtitle,
        author=metadata.author,
        date=metadata.date,
        client_name="",
        sections=markdown_sections,
        output_format="markdown",
        output_path=str(markdown_path),
    )

    result: dict[str, Any] = {
        "status": "completed",
        "title": metadata.title,
        "section_count": len(normalized_sections),
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
                    metadata,
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
            for idx, section in enumerate(normalized_sections, start=1)
        ]
        assemble_epub(
            title=metadata.title,
            author=metadata.author,
            chapters=chapters,
            cover_path=metadata.cover_path,
            output_path=str(epub_path),
        )
        result["epub_path"] = str(epub_path)

    quality_props = [
        QualityProperty(
            name="section_count",
            passed=len(normalized_sections) >= 3,
            pass_delta=1.5,
            fail_delta=1.5,
            detail=f"found {len(normalized_sections)} sections",
            is_gate=True,
        ),
        QualityProperty(
            name="chart_coverage",
            passed=bool(normalized_charts),
            pass_delta=1.0,
            fail_delta=1.0,
            detail=f"generated {result['chart_count']} charts",
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
        pipeline="nonfiction_ebook_generate",
        properties=quality_props,
    )

    logger.info(
        "nonfiction_ebook_generated",
        output_dir=str(out_dir),
        section_count=len(normalized_sections),
        chart_count=result["chart_count"],
    )
    return result
