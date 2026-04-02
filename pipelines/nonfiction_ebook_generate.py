"""Compatibility wrapper for the structured nonfiction family."""
from __future__ import annotations

from typing import Any

from pipelines.structured_nonfiction_generate import run as _run_structured_nonfiction


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
    return _run_structured_nonfiction(
        title=title,
        author=author,
        sections=sections,
        charts=charts,
        output_dir=output_dir,
        subtitle=subtitle,
        date=date,
        cover_path=cover_path,
        brand=brand,
        export_pdf=export_pdf,
        export_epub=export_epub,
        profile="ebook",
        package_mode="single_document",
        include_toc=True,
    )
