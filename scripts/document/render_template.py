"""Fill an HTML document template with content and brand variables."""
from __future__ import annotations

import re
from pathlib import Path

_PLACEHOLDER_PATTERN = re.compile(r"\{\{(\w+)\}\}")
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "documents"


def _resolve_template_path(template_name: str = "", template_path: str = "") -> Path:
    """Resolve a document template path from name or explicit path."""
    if template_path:
        path = Path(template_path)
    elif template_name:
        path = _TEMPLATES_DIR / f"{template_name}.html"
    else:
        msg = "template_name or template_path is required"
        raise ValueError(msg)

    if not path.exists():
        msg = f"Template not found: {path}"
        raise FileNotFoundError(msg)
    return path


def _fill_template(template_html: str, variables: dict[str, str]) -> str:
    """Replace {{placeholder}} tokens with provided values."""
    return _PLACEHOLDER_PATTERN.sub(
        lambda match: variables.get(match.group(1), ""),
        template_html,
    )


def run(
    *,
    template_name: str = "",
    template_path: str = "",
    content: dict[str, str] | None = None,
    brand: dict[str, str] | None = None,
    output_path: str,
) -> dict[str, object]:
    """Render a document template to a filled HTML file."""
    if not output_path:
        msg = "output_path is required"
        raise ValueError(msg)

    resolved_path = _resolve_template_path(
        template_name=template_name,
        template_path=template_path,
    )
    template_html = resolved_path.read_text(encoding="utf-8")
    merged = {
        **{key: str(value) for key, value in (brand or {}).items()},
        **{key: str(value) for key, value in (content or {}).items()},
    }
    rendered_html = _fill_template(template_html, merged)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(rendered_html, encoding="utf-8")

    return {
        "filled_template_path": str(output_file),
        "html_length": len(rendered_html),
    }
