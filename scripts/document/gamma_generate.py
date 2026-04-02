"""Gamma generation wrapper for presentations and document exports."""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

from adapter.env_loader import ensure_env

logger = structlog.get_logger(__name__)

_API_BASE = "https://public-api.gamma.app/v1.0"
_GENERATIONS_ENDPOINT = f"{_API_BASE}/generations"
_GENERATIONS_FROM_TEMPLATE_ENDPOINT = f"{_API_BASE}/generations/from-template"
_THEMES_ENDPOINT = f"{_API_BASE}/themes"
_FOLDERS_ENDPOINT = f"{_API_BASE}/folders"
_ALLOWED_OUTPUT_DIR = (Path(__file__).parent.parent.parent / "output").resolve()
_FORMAT_VALUES = frozenset({"presentation", "document", "webpage", "social"})
_TEXT_MODE_VALUES = frozenset({"generate", "condense", "preserve"})
_EXPORT_VALUES = frozenset({"pptx", "pdf", "png"})
_CARD_SPLIT_VALUES = frozenset({"inputTextBreaks", "auto"})
_TEXT_AMOUNT_VALUES = frozenset({"brief", "medium", "detailed", "extensive"})
_IMAGE_SOURCE_VALUES = frozenset({
    "aiGenerated",
    "pictographic",
    "pexels",
    "giphy",
    "webAllImages",
    "webFreeToUse",
    "webFreeToUseCommercially",
    "themeAccent",
    "placeholder",
    "noImages",
})
_IMAGE_STYLE_PRESET_VALUES = frozenset({
    "photorealistic",
    "illustration",
    "abstract",
    "3D",
    "lineArt",
    "custom",
})
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    collapsed = _SLUG_RE.sub("-", value.strip().lower()).strip("-")
    return collapsed or "gamma-export"


def _is_output_path_allowed(resolved_path: Path) -> bool:
    """Check if an output path is within allowed directories."""
    if resolved_path.is_relative_to(_ALLOWED_OUTPUT_DIR):
        return True
    extra = os.environ.get("VIZIER_ALLOWED_ROOTS", "")
    if extra:
        for root in extra.split(":"):
            if root and resolved_path.is_relative_to(Path(root).resolve()):
                return True
    return False


def _get_api_key() -> str:
    ensure_env()
    api_key = os.environ.get("GAMMA_API_KEY", "").strip()
    if not api_key:
        msg = "GAMMA_API_KEY environment variable required for Gamma generation"
        raise RuntimeError(msg)
    return api_key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _validate_enum(value: str, allowed: set[str] | frozenset[str], *, field_name: str) -> str:
    normalized = value.strip()
    if normalized not in allowed:
        msg = f"{field_name} must be one of {sorted(allowed)}"
        raise ValueError(msg)
    return normalized


def _normalize_mapping(
    value: dict[str, Any] | None,
    *,
    field_name: str,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object when provided"
        raise ValueError(msg)
    return {str(key): item for key, item in value.items()}


def _build_output_path(
    *,
    generation_id: str,
    output_path: str,
    export_as: str,
) -> Path:
    if output_path:
        resolved = Path(output_path).resolve()
    else:
        out_dir = _ALLOWED_OUTPUT_DIR / "gamma"
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = f".{export_as}" if export_as else ""
        resolved = (out_dir / f"{_slugify(generation_id)}{suffix}").resolve()

    if not _is_output_path_allowed(resolved):
        msg = f"Output path escapes allowed directory: {resolved}"
        raise ValueError(msg)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _request_json(
    *,
    method: str,
    url: str,
    api_key: str,
    json_payload: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    response = httpx.request(
        method,
        url,
        headers=_headers(api_key),
        json=json_payload,
        params=params,
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        msg = f"Gamma API request failed ({exc.response.status_code}): {detail}"
        raise RuntimeError(msg) from exc

    payload = response.json()
    if not isinstance(payload, dict):
        msg = "Gamma API returned a non-object JSON payload"
        raise RuntimeError(msg)
    return payload


def _build_text_options(
    *,
    text_amount: str,
    tone: str,
    audience: str,
    language: str,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    if text_amount.strip():
        options["amount"] = _validate_enum(
            text_amount,
            _TEXT_AMOUNT_VALUES,
            field_name="text_amount",
        )
    if tone.strip():
        options["tone"] = tone.strip()
    if audience.strip():
        options["audience"] = audience.strip()
    if language.strip():
        options["language"] = language.strip()
    return options


def _build_image_options(
    *,
    image_source: str,
    image_model: str,
    image_style: str,
    image_style_preset: str,
) -> dict[str, Any]:
    options: dict[str, Any] = {}
    normalized_image_source = ""
    if image_source.strip():
        normalized_image_source = _validate_enum(
            image_source,
            _IMAGE_SOURCE_VALUES,
            field_name="image_source",
        )
        options["source"] = normalized_image_source

    if normalized_image_source == "aiGenerated":
        if image_style_preset.strip():
            options["stylePreset"] = _validate_enum(
                image_style_preset,
                _IMAGE_STYLE_PRESET_VALUES,
                field_name="image_style_preset",
            )
        if image_model.strip():
            options["model"] = image_model.strip()
        if image_style.strip():
            options["style"] = image_style.strip()

    return options


def _build_card_options(
    *,
    card_dimensions: str,
    header_footer: dict[str, Any] | None,
    card_options: dict[str, Any] | None,
) -> dict[str, Any]:
    options = _normalize_mapping(card_options, field_name="card_options")
    if card_dimensions.strip():
        options["dimensions"] = card_dimensions.strip()
    normalized_header_footer = _normalize_mapping(
        header_footer,
        field_name="header_footer",
    )
    if normalized_header_footer:
        options["headerFooter"] = normalized_header_footer
    return options


def _compose_template_prompt(
    *,
    input_text: str,
    template_prompt: str,
    additional_instructions: str,
) -> str:
    parts: list[str] = []
    if template_prompt.strip():
        parts.append(template_prompt.strip())
    if input_text.strip():
        parts.append(input_text.strip())
    if additional_instructions.strip():
        parts.append(f"Additional instructions:\n{additional_instructions.strip()}")
    return "\n\n".join(parts).strip()


def list_themes(
    *,
    query: str = "",
    limit: int = 20,
    after: str = "",
) -> dict[str, Any]:
    """List Gamma workspace themes."""
    api_key = _get_api_key()
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    if query.strip():
        params["query"] = query.strip()
    if after.strip():
        params["after"] = after.strip()
    return _request_json(
        method="GET",
        url=_THEMES_ENDPOINT,
        api_key=api_key,
        params=params,
    )


def list_folders(
    *,
    query: str = "",
    limit: int = 20,
    after: str = "",
) -> dict[str, Any]:
    """List Gamma workspace folders."""
    api_key = _get_api_key()
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    if query.strip():
        params["query"] = query.strip()
    if after.strip():
        params["after"] = after.strip()
    return _request_json(
        method="GET",
        url=_FOLDERS_ENDPOINT,
        api_key=api_key,
        params=params,
    )


def run(
    *,
    input_text: str = "",
    text_mode: str = "condense",
    format: str = "presentation",
    additional_instructions: str = "",
    export_as: str = "pdf",
    theme_id: str = "",
    folder_ids: list[str] | None = None,
    num_cards: int | None = None,
    image_source: str = "",
    image_model: str = "",
    image_style: str = "",
    image_style_preset: str = "",
    card_split: str = "",
    card_dimensions: str = "",
    text_amount: str = "",
    tone: str = "",
    audience: str = "",
    language: str = "",
    header_footer: dict[str, Any] | None = None,
    card_options: dict[str, Any] | None = None,
    sharing_options: dict[str, Any] | None = None,
    template_gamma_id: str = "",
    template_prompt: str = "",
    output_path: str = "",
    poll_interval: float = 5.0,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Create a Gamma generation, poll until completion, and optionally download the export."""
    use_template = bool(template_gamma_id.strip())
    if use_template:
        if not _compose_template_prompt(
            input_text=input_text,
            template_prompt=template_prompt,
            additional_instructions=additional_instructions,
        ):
            msg = "template_prompt or input_text is required for template-based generation"
            raise ValueError(msg)
        normalized_text_mode = ""
    else:
        if not input_text.strip():
            msg = "input_text is required"
            raise ValueError(msg)
        normalized_text_mode = _validate_enum(
            text_mode,
            _TEXT_MODE_VALUES,
            field_name="text_mode",
        )
    normalized_format = _validate_enum(
        format,
        _FORMAT_VALUES,
        field_name="format",
    )
    normalized_export_as = ""
    if export_as.strip():
        normalized_export_as = _validate_enum(
            export_as,
            _EXPORT_VALUES,
            field_name="export_as",
        )
    if num_cards is not None and num_cards <= 0:
        msg = "num_cards must be greater than 0 when provided"
        raise ValueError(msg)
    normalized_card_split = ""
    if card_split.strip():
        normalized_card_split = _validate_enum(
            card_split,
            _CARD_SPLIT_VALUES,
            field_name="card_split",
        )
    if poll_interval <= 0:
        msg = "poll_interval must be greater than 0"
        raise ValueError(msg)
    if timeout <= 0:
        msg = "timeout must be greater than 0"
        raise ValueError(msg)

    api_key = _get_api_key()
    payload: dict[str, Any] = {}
    endpoint = _GENERATIONS_ENDPOINT
    if use_template:
        endpoint = _GENERATIONS_FROM_TEMPLATE_ENDPOINT
        payload = {
            "gammaId": template_gamma_id.strip(),
            "prompt": _compose_template_prompt(
                input_text=input_text,
                template_prompt=template_prompt,
                additional_instructions=additional_instructions,
            ),
        }
    else:
        payload = {
            "inputText": input_text.strip(),
            "textMode": normalized_text_mode,
            "format": normalized_format,
        }
        if additional_instructions.strip():
            payload["additionalInstructions"] = additional_instructions.strip()

    if normalized_export_as:
        payload["exportAs"] = normalized_export_as
    if theme_id.strip():
        payload["themeId"] = theme_id.strip()
    if folder_ids:
        payload["folderIds"] = [
            str(folder_id).strip()
            for folder_id in folder_ids
            if str(folder_id).strip()
        ]
    if num_cards is not None:
        payload["numCards"] = int(num_cards)
    if normalized_card_split and not use_template:
        payload["cardSplit"] = normalized_card_split

    text_options = _build_text_options(
        text_amount=text_amount,
        tone=tone,
        audience=audience,
        language=language,
    )
    if text_options and not use_template:
        payload["textOptions"] = text_options

    image_options = _build_image_options(
        image_source=image_source,
        image_model=image_model,
        image_style=image_style,
        image_style_preset=image_style_preset,
    )
    if image_options and not use_template:
        payload["imageOptions"] = image_options

    merged_card_options = _build_card_options(
        card_dimensions=card_dimensions,
        header_footer=header_footer,
        card_options=card_options,
    )
    if merged_card_options:
        payload["cardOptions"] = merged_card_options

    merged_sharing_options = _normalize_mapping(
        sharing_options,
        field_name="sharing_options",
    )
    if merged_sharing_options:
        payload["sharingOptions"] = merged_sharing_options

    create_response = _request_json(
        method="POST",
        url=endpoint,
        api_key=api_key,
        json_payload=payload,
        timeout=30.0,
    )
    generation_id = str(create_response.get("generationId", "")).strip()
    if not generation_id:
        msg = "Gamma API did not return a generationId"
        raise RuntimeError(msg)

    status_url = f"{_GENERATIONS_ENDPOINT}/{generation_id}"
    deadline = time.monotonic() + timeout
    last_payload: dict[str, Any] = create_response

    while time.monotonic() <= deadline:
        status_response = _request_json(
            method="GET",
            url=status_url,
            api_key=api_key,
            timeout=30.0,
        )
        last_payload = status_response
        status = str(status_response.get("status", "")).strip().lower()
        if status == "completed":
            break
        if status == "failed":
            error_detail = str(
                status_response.get("errorMessage", status_response.get("message", "Gamma generation failed"))
            ).strip()
            raise RuntimeError(error_detail or "Gamma generation failed")
        time.sleep(poll_interval)
    else:
        msg = f"Gamma generation timed out after {timeout:.1f}s"
        raise TimeoutError(msg)

    gamma_url = str(last_payload.get("gammaUrl", "")).strip()
    export_url = str(last_payload.get("exportUrl", "")).strip()
    result: dict[str, Any] = {
        "generation_id": generation_id,
        "status": str(last_payload.get("status", "completed")).strip() or "completed",
        "request_mode": "from_template" if use_template else "from_text",
        "gamma_url": gamma_url,
        "export_url": export_url,
        "credits": last_payload.get("credits", {}),
    }
    warnings = create_response.get("warnings") or last_payload.get("warnings") or []
    if warnings:
        result["warnings"] = warnings

    if export_url and normalized_export_as:
        resolved_output = _build_output_path(
            generation_id=generation_id,
            output_path=output_path,
            export_as=normalized_export_as,
        )
        download_response = httpx.get(export_url, timeout=60.0)
        try:
            download_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            msg = f"Gamma export download failed ({exc.response.status_code}): {detail}"
            raise RuntimeError(msg) from exc
        resolved_output.write_bytes(download_response.content)
        result["file_path"] = str(resolved_output)

    logger.info(
        "gamma_generation_completed",
        generation_id=generation_id,
        status=result["status"],
        gamma_url=gamma_url or None,
        export_url=export_url or None,
    )
    return result
