"""Tests for parameterize_template — Jinja2 placeholder injection."""
from __future__ import annotations

from scripts.visual.parameterize_template import parameterize_template


class TestParameterizeTemplate:
    def test_replaces_text_with_placeholder(self) -> None:
        html = "<h1>Acme Corp</h1><p>Best widgets since 2020</p>"
        mapping = {"Acme Corp": "company_name", "Best widgets since 2020": "tagline"}
        result = parameterize_template(html=html, mapping=mapping)
        assert "{{ company_name }}" in result
        assert "{{ tagline }}" in result
        assert "Acme Corp" not in result

    def test_preserves_html_structure(self) -> None:
        html = '<div class="header"><h1>Title</h1></div>'
        mapping = {"Title": "heading"}
        result = parameterize_template(html=html, mapping=mapping)
        assert '<div class="header">' in result
        assert "{{ heading }}" in result

    def test_empty_mapping_returns_original(self) -> None:
        html = "<p>Hello World</p>"
        result = parameterize_template(html=html, mapping={})
        assert result == html

    def test_multiple_occurrences_replaced(self) -> None:
        html = "<p>Acme</p><footer>Acme</footer>"
        mapping = {"Acme": "brand"}
        result = parameterize_template(html=html, mapping=mapping)
        assert result.count("{{ brand }}") == 2
        assert "Acme" not in result
