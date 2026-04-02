"""Tests for config/client_loader.py."""
from __future__ import annotations

from config.client_loader import (
    brand_to_css_vars,
    list_clients,
    list_style_references,
    load_client,
    load_style_reference,
    style_reference_to_css_vars,
)


class TestLoadClient:
    def setup_method(self) -> None:
        load_client.cache_clear()

    def test_loads_seeded_clients(self) -> None:
        for client_id in ("dmb", "ar-rawdhah", "rempah-tok-ma"):
            client = load_client(client_id)
            assert client is not None
            assert client.client_id == client_id
            assert client.client_name
            assert client.defaults.template_name
            assert client.defaults.style_reference
            assert client.defaults.style_reference_options

    def test_missing_client_returns_none(self) -> None:
        assert load_client("missing-client") is None


class TestListClients:
    def test_lists_seeded_client_ids(self) -> None:
        assert list_clients() == ["ar-rawdhah", "dmb", "rempah-tok-ma"]


class TestBrandToCssVars:
    def test_maps_brand_to_ultimate_and_promax_variables(self) -> None:
        client = load_client("dmb")
        assert client is not None

        css_vars = brand_to_css_vars(client.brand)

        assert css_vars["--bg-color"] == "#2C1810"
        assert css_vars["--accent-color"] == "#C4956A"
        assert css_vars["--font-headline"] == "Playfair Display"
        assert css_vars["--font-body"] == "Inter"
        assert css_vars["--color-bg"] == "#2C1810"
        assert css_vars["--color-accent"] == "#C4956A"
        assert css_vars["--font-heading"] == "Playfair Display"


class TestStyleReferences:
    def test_lists_seeded_style_references(self) -> None:
        style_ids = list_style_references()
        assert "aesop" in style_ids
        assert "zus-coffee" in style_ids
        assert "starbucks" in style_ids
        assert "nike" in style_ids

    def test_loads_style_reference(self) -> None:
        style = load_style_reference("zus-coffee")
        assert style is not None
        assert style.display_name == "ZUS Coffee"
        assert style.template_name == "center-stage-square"
        assert "fnb" in style.categories

    def test_maps_style_reference_to_css_vars(self) -> None:
        style = load_style_reference("boh-tea")
        assert style is not None
        css_vars = style_reference_to_css_vars(style)
        assert css_vars["--bg-color"] == "#2F5D3A"
        assert css_vars["--accent-color"] == "#B08D57"
        assert css_vars["--font-heading"] == "Playfair Display"
