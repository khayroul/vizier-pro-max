"""Load client brand configuration from YAML files."""
from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path

import structlog
import yaml

logger = structlog.get_logger(__name__)

_CLIENTS_DIR = Path(__file__).parent / "clients"
_STYLE_REFERENCES_PATH = Path(__file__).parent / "style_references.yaml"


@dataclass(frozen=True)
class BrandConfig:
    primary_color: str = "#1A1A2E"
    secondary_color: str = "#F0F0F5"
    accent_color: str = "#2563EB"
    headline_font: str = "Georgia"
    body_font: str = "Inter"
    logo_mark: str = ""


@dataclass(frozen=True)
class ClientDefaults:
    template_name: str = "social-post"
    image_mode: str = "falai"
    style_hint: str = ""
    language: str = "en"
    tone: str = "formal"
    style_reference: str = ""
    style_reference_options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ClientConfig:
    client_id: str
    client_name: str
    brand: BrandConfig
    defaults: ClientDefaults


@dataclass(frozen=True)
class StyleReference:
    style_id: str
    display_name: str
    categories: list[str] = field(default_factory=list)
    primary_color: str = "#1A1A2E"
    secondary_color: str = "#F0F0F5"
    accent_color: str = "#2563EB"
    headline_font: str = "Georgia"
    body_font: str = "Inter"
    template_name: str = "social-post"
    style_hint: str = ""
    avoid_hint: str = ""


@functools.lru_cache(maxsize=32)
def load_client(client_id: str) -> ClientConfig | None:
    """Load a client config by ID."""
    path = _CLIENTS_DIR / f"{client_id}.yaml"
    if not path.exists():
        logger.warning("Client config not found", client_id=client_id)
        return None

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    brand_raw = raw.get("brand", {})
    defaults_raw = raw.get("defaults", {})

    return ClientConfig(
        client_id=raw.get("client_id", client_id),
        client_name=raw.get("client_name", client_id),
        brand=BrandConfig(
            **{
                key: value
                for key, value in brand_raw.items()
                if key in BrandConfig.__dataclass_fields__
            }
        ),
        defaults=ClientDefaults(
            **{
                key: value
                for key, value in defaults_raw.items()
                if key in ClientDefaults.__dataclass_fields__
            }
        ),
    )


@functools.lru_cache(maxsize=1)
def _load_style_reference_map() -> dict[str, StyleReference]:
    """Load shared style references from YAML."""
    if not _STYLE_REFERENCES_PATH.exists():
        logger.warning(
            "Style reference catalog not found", path=str(_STYLE_REFERENCES_PATH)
        )
        return {}

    raw = yaml.safe_load(_STYLE_REFERENCES_PATH.read_text(encoding="utf-8")) or {}
    refs: dict[str, StyleReference] = {}
    for style_id, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        refs[str(style_id)] = StyleReference(
            style_id=str(style_id),
            display_name=str(payload.get("display_name", style_id)),
            categories=[str(v) for v in payload.get("categories", []) if v],
            primary_color=str(payload.get("primary_color", "#1A1A2E")),
            secondary_color=str(payload.get("secondary_color", "#F0F0F5")),
            accent_color=str(payload.get("accent_color", "#2563EB")),
            headline_font=str(payload.get("headline_font", "Georgia")),
            body_font=str(payload.get("body_font", "Inter")),
            template_name=str(payload.get("template_name", "social-post")),
            style_hint=str(payload.get("style_hint", "")),
            avoid_hint=str(payload.get("avoid_hint", "")),
        )
    return refs


def load_style_reference(style_id: str) -> StyleReference | None:
    """Load a shared style reference by ID."""
    return _load_style_reference_map().get(style_id)


def list_style_references() -> list[str]:
    """List available shared style reference IDs."""
    return sorted(_load_style_reference_map())


def list_clients() -> list[str]:
    """List available client IDs."""
    if not _CLIENTS_DIR.exists():
        return []
    return sorted(
        path.stem for path in _CLIENTS_DIR.glob("*.yaml") if path.stem != "_schema"
    )


def brand_to_css_vars(brand: BrandConfig) -> dict[str, str]:
    """Map a brand config to both Ultimate and Pro-Max CSS variables."""
    return {
        "--bg-color": brand.primary_color,
        "--accent-color": brand.accent_color,
        "--font-headline": brand.headline_font,
        "--font-body": brand.body_font,
        "--font-headline-weight": "700",
        "--font-body-weight": "400",
        "--text-color": "#ffffff",
        "--text-muted": "rgba(255, 255, 255, 0.72)",
        "--color-accent": brand.accent_color,
        "--color-accent-end": brand.secondary_color,
        "--color-accent-glow": brand.accent_color,
        "--color-bg": brand.primary_color,
        "--color-text": "#ffffff",
        "--font-heading": brand.headline_font,
        "--font-weight-heading": "700",
        "--font-weight-body": "400",
        "--letter-spacing-heading": "-0.02em",
        "--letter-spacing-body": "0em",
        "--line-height-heading": "1.1",
        "--line-height-body": "1.5",
    }


def style_reference_to_css_vars(style: StyleReference) -> dict[str, str]:
    """Map a style reference into CSS custom properties for poster theming."""
    return {
        "--bg-color": style.primary_color,
        "--accent-color": style.accent_color,
        "--font-headline": style.headline_font,
        "--font-body": style.body_font,
        "--font-headline-weight": "700",
        "--font-body-weight": "400",
        "--text-color": "#ffffff",
        "--text-muted": "rgba(255, 255, 255, 0.72)",
        "--color-accent": style.accent_color,
        "--color-accent-end": style.secondary_color,
        "--color-accent-glow": style.accent_color,
        "--color-bg": style.primary_color,
        "--color-text": "#ffffff",
        "--font-heading": style.headline_font,
        "--font-weight-heading": "700",
        "--font-weight-body": "400",
        "--letter-spacing-heading": "-0.02em",
        "--letter-spacing-body": "0em",
        "--line-height-heading": "1.1",
        "--line-height-body": "1.5",
    }
