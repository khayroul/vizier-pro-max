"""Render Jinja2 templates with provided variables."""
from __future__ import annotations

from jinja2 import BaseLoader, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment


def render(template_string: str, variables: dict[str, object]) -> dict[str, object]:
    """Render a Jinja2 template string.

    Args:
        template_string: Jinja2 template markup.
        variables: Dict of template variables.

    Returns:
        Dict with rendered output or error.
    """
    try:
        env = SandboxedEnvironment(loader=BaseLoader(), autoescape=True)
        template = env.from_string(template_string)
        rendered = template.render(**variables)
        return {"rendered": rendered}
    except TemplateSyntaxError as exc:
        return {"error": f"Template syntax error: {exc}"}
