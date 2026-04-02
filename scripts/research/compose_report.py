"""Compose structured reports as Markdown or Typst."""
from __future__ import annotations

from pathlib import Path

import structlog

from scripts.document.md_to_typst import convert as markdown_to_typst

logger = structlog.get_logger(__name__)

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "templates" / "typst" / "long-report.typ"
_LEVEL_SIGIL = {1: "=", 2: "==", 3: "==="}


def _compose_markdown(
    *,
    title: str,
    subtitle: str,
    author: str,
    sections: list[dict[str, object]],
) -> str:
    """Compose a report as Markdown."""
    header = [f"# {title}"]
    if subtitle:
        header.append(f"\n_{subtitle}_")
    if author:
        header.append(f"\nPrepared by: {author}")

    body_parts = [
        f"\n{'#' * max(1, min(int(section.get('level', 1)), 3))} {section.get('heading', 'Untitled')}\n\n{section.get('body', '')}"
        for section in sections
    ]
    return "\n".join(header) + "\n" + "\n".join(body_parts).strip() + "\n"


def _compose_typst(
    *,
    title: str,
    subtitle: str,
    author: str,
    client_name: str,
    date: str,
    sections: list[dict[str, object]],
) -> str:
    """Compose a report as Typst using the long-report template when present."""
    preamble = _TEMPLATE_PATH.read_text(encoding="utf-8") if _TEMPLATE_PATH.exists() else ""
    body_parts = []
    for section in sections:
        heading = str(section.get("heading", "Untitled"))
        level = max(1, min(int(section.get("level", 1)), 3))
        body = markdown_to_typst(str(section.get("body", "")))
        body_parts.append(f"\n{_LEVEL_SIGIL[level]} {heading}\n\n{body}")

    document = preamble
    replacements = {
        'sys.inputs.at("title",         default: "Report")': f'sys.inputs.at("title",         default: "{title}")',
        'sys.inputs.at("subtitle",    default: "")': f'sys.inputs.at("subtitle",    default: "{subtitle}")',
        'sys.inputs.at("author",        default: "")': f'sys.inputs.at("author",        default: "{author}")',
        'sys.inputs.at("date",          default: "")': f'sys.inputs.at("date",          default: "{date}")',
        'sys.inputs.at("client_name",   default: "")': f'sys.inputs.at("client_name",   default: "{client_name}")',
    }
    for original, replacement in replacements.items():
        document = document.replace(original, replacement)

    if preamble:
        return document + "\n" + "\n".join(body_parts).strip() + "\n"

    title_block = [
        "#set page(paper: \"a4\", margin: (x: 2.5cm, y: 3cm))",
        f"= {title}",
    ]
    if subtitle:
        title_block.append(subtitle)
    if author:
        title_block.append(f"_Prepared by: {author}_")
    return "\n\n".join(title_block + body_parts) + "\n"


def run(
    *,
    title: str,
    sections: list[dict[str, object]],
    output_format: str = "markdown",
    subtitle: str = "",
    author: str = "",
    client_name: str = "",
    date: str = "",
    output_path: str = "",
) -> dict[str, object]:
    """Compose a structured report and optionally write it to disk."""
    if not title:
        msg = "title is required"
        raise ValueError(msg)
    if not sections:
        msg = "sections is required"
        raise ValueError(msg)
    if output_format not in {"markdown", "typst"}:
        msg = "output_format must be 'markdown' or 'typst'"
        raise ValueError(msg)

    composed = (
        _compose_typst(
            title=title,
            subtitle=subtitle,
            author=author,
            client_name=client_name,
            date=date,
            sections=sections,
        )
        if output_format == "typst"
        else _compose_markdown(
            title=title,
            subtitle=subtitle,
            author=author,
            sections=sections,
        )
    )

    result: dict[str, object] = {
        "content": composed,
        "output_format": output_format,
        "section_count": len(sections),
    }

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(composed, encoding="utf-8")
        result["file_path"] = str(output)

    logger.info("Composed report", output_format=output_format, section_count=len(sections))
    return result
