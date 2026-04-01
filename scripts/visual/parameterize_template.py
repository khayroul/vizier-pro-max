"""Replace specific content in HTML with Jinja2 placeholders."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def parameterize_template(
    *,
    html: str,
    mapping: dict[str, str],
) -> str:
    """Replace literal content with Jinja2 template variables.

    Args:
        html: The HTML content to parameterize.
        mapping: Dict of {literal_content: placeholder_name}.
                 e.g. {"Acme Corp": "company_name"} -> {{ company_name }}

    Returns:
        HTML with content replaced by Jinja2 variables.
    """
    result = html
    # Sort by length descending to replace longer strings first
    # (avoids partial replacement issues)
    for content, placeholder in sorted(mapping.items(), key=lambda item: -len(item[0])):
        jinja_var = f"{{{{ {placeholder} }}}}"
        result = result.replace(content, jinja_var)
    return result
