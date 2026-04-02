"""Shared helpers for long-form book pipelines."""
from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any

from middleware.quality_scorer import QualityProperty, compute_score
from pipelines.longform.models import (
    ChartSpec,
    LongformChapter,
    LongformMetadata,
    LongformSection,
    LongformSpread,
)

_ROOT = Path(__file__).resolve().parents[2]
_DOC_TEMPLATES = _ROOT / "templates" / "documents"
_NEWLINES_RE = re.compile(r"\n{2,}")

_DEFAULT_BRAND = {
    "primary_color": "#1A1A2E",
    "secondary_color": "#F4F4F8",
    "accent_color": "#E94560",
    "headline_font": "Georgia, 'Times New Roman', serif",
    "body_font": "system-ui, -apple-system, sans-serif",
}


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
) -> str:
    """Render nonfiction sections through the report template."""
    body_parts: list[str] = []
    summary_source = sections[0].callout or sections[0].body
    executive_summary = (
        f"<p>{html.escape(summary_source[:320])}</p>"
        if summary_source
        else "<p>Summary unavailable.</p>"
    )

    for section in sections:
        level_tag = f"h{max(2, min(section.level + 1, 4))}"
        section_html = [f"<{level_tag}>{html.escape(section.heading)}</{level_tag}>"]
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

    return _fill_template(
        "report.html",
        {
            "title": html.escape(metadata.title),
            "subtitle": html.escape(metadata.subtitle),
            "author": html.escape(metadata.author),
            "date": html.escape(metadata.date),
            "footer": "Generated by Vizier",
            "executive_summary": executive_summary,
            "body": "".join(body_parts),
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
