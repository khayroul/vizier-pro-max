"""Batch poster production — AI background + HTML overlay -> posters.

Two-layer composition:
1. fal_generate AI background (800x600)
2. Base64 inject into Jinja2 template
3. Playwright screenshot
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import structlog
from jinja2.sandbox import SandboxedEnvironment

from adapter.env_loader import ensure_env
from adapter.llm_client import chat as llm_chat
from middleware.cost_ledger import record_quality
from middleware.deliverable_context import (
    clear_context,
    set_pipeline_step,
    start_deliverable,
)
from middleware.pipeline_runner import run_with_gates
from middleware.quality_scorer import score_poster_batch
from middleware.trace_exporter import (
    check_anomalies,
    export_trace,
    log_anomaly,
    notify_anomaly,
)
from scripts.visual.screenshot_html import run as screenshot_run

logger = structlog.get_logger(__name__)

_PIPELINE_NAME = "poster_batch"
_PIPELINE_VERSION = "2.0"

_INPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "template_path": {"type": "string", "required": False},
    "data_path": {"type": "string", "required": True},
    "output_dir": {"type": "string", "required": False},
    "client_id": {"type": "string", "required": False},
}

_OUTPUT_SCHEMA: dict[str, dict[str, Any]] = {
    "posters": {"type": "array", "required": True},
    "count": {"type": "integer", "required": True},
    "status": {"type": "string", "required": True},
}

_GRADIENT_FALLBACK = "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)"


def _generate_image_prompt(headline: str, style_hint: str | None) -> str:
    """Ask LLM for an image generation prompt based on content.

    Args:
        headline: The poster headline text.
        style_hint: Optional style direction from CSV data.

    Returns:
        An image generation prompt string.
    """
    set_pipeline_step("image_prompt", _PIPELINE_NAME, _PIPELINE_VERSION)
    context = style_hint or headline
    result = llm_chat(
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate a short image prompt for an AI image generator. "
                    "The image will be used as a poster background. Rules:\n"
                    "- No text in the image\n"
                    "- Photography style, suitable as background\n"
                    "- Soft lighting, shallow depth of field\n"
                    "- Output ONLY the prompt, nothing else"
                ),
            },
            {"role": "user", "content": f"Context: {context}"},
        ],
        max_tokens=100,
        strip_preamble=True,
    )
    return result or f"professional photography, {context}, soft lighting, shallow depth of field"


def _generate_ai_background(prompt: str, output_path: str) -> str | None:
    """Generate AI background via fal.ai.

    Args:
        prompt: Image generation prompt.
        output_path: Local path to write the generated image.

    Returns:
        Path to saved image, or None on failure.
    """
    try:
        ensure_env()
        from scripts.visual.generate_image import run as fal_run  # noqa: PLC0415

        result = fal_run(
            prompt=prompt,
            output_path=output_path,
            width=800,
            height=600,
        )
        return result["file_path"]
    except (
        RuntimeError,
        httpx.HTTPError,
        httpx.TimeoutException,
        KeyError,
        FileNotFoundError,
        OSError,
    ) as exc:
        logger.warning("AI background generation failed: %s", exc)
        return None


def _encode_background(image_path: str | None) -> str:
    """Encode image as base64 data URI, or return CSS gradient fallback.

    Args:
        image_path: Path to local PNG image, or None.

    Returns:
        Base64 data URI string or CSS gradient string.
    """
    if image_path is None:
        return _GRADIENT_FALLBACK
    try:
        image_bytes = Path(image_path).read_bytes()
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except (FileNotFoundError, OSError):
        return _GRADIENT_FALLBACK


def _csv_string(row: dict[str, Any], key: str, default: str = "") -> str:
    """Read a CSV cell as a string with NaN treated as missing."""
    value = row.get(key)
    if value is None:
        return default
    if pd.isna(value):
        return default
    return str(value)


def _csv_object(row: dict[str, Any], key: str) -> dict[str, str] | None:
    """Read a CSV JSON object cell if present."""
    value = row.get(key)
    if value is None or pd.isna(value):
        return None
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    return None


def _pipeline_fn(inputs: dict[str, Any]) -> dict[str, Any]:
    """Core pipeline logic for poster batch production.

    Args:
        inputs: Validated input dict with template_path, data_path, etc.

    Returns:
        Dict with posters, count, status, and deliverable_id keys.
    """
    template_path: str | None = inputs.get("template_path")
    data_path: str = inputs["data_path"]
    output_dir: str = inputs.get("output_dir", "output/posters")
    client_id: str | None = inputs.get("client_id")

    did = start_deliverable(client_id=client_id)

    try:
        data_file = Path(data_path)
        if not data_file.exists():
            msg = f"Data file not found: {data_path}"
            raise FileNotFoundError(msg)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        df = pd.read_csv(data_file)
        rows = df.to_dict(orient="records")

        if not rows:
            return {
                "posters": [],
                "count": 0,
                "status": "completed",
                "deliverable_id": did,
            }

        posters: list[str] = []
        if client_id:
            from pipelines.poster_generate import run as generate_poster_run

            for idx, row in enumerate(rows):
                headline = _csv_string(row, "headline")
                body = _csv_string(row, "body")
                if not headline or not body:
                    msg = f"CSV row {idx} requires headline and body for client batch rendering"
                    raise ValueError(msg)

                poster_path = str(out / f"poster_{idx:04d}.png")
                result = generate_poster_run(
                    headline=headline,
                    body=body,
                    cta=_csv_string(row, "cta", "Learn More"),
                    image_prompt=_csv_string(row, "image_prompt") or _csv_string(row, "style_hint"),
                    style_reference=_csv_string(row, "style_reference"),
                    template_name=_csv_string(row, "template_name"),
                    image_mode=_csv_string(row, "image_mode"),
                    output_path=poster_path,
                    brand_name=_csv_string(row, "brand_name"),
                    logo_mark=_csv_string(row, "logo_mark"),
                    brand_css=_csv_object(row, "brand_css"),
                    client_id=client_id,
                    palette=_csv_object(row, "palette"),
                    fonts=_csv_object(row, "fonts"),
                )
                rendered_path = str(result["poster_path"])
                posters.append(rendered_path)

                poster_score = score_poster_batch(Path(rendered_path))
                logger.info(
                    "Poster %d/%d rendered (score: %.1f): %s",
                    idx + 1,
                    len(rows),
                    poster_score.score,
                    rendered_path,
                )
        else:
            if not template_path:
                msg = "template_path is required when client_id is not provided"
                raise ValueError(msg)

            tmpl_file = Path(template_path)
            if not tmpl_file.exists():
                msg = f"Template not found: {template_path}"
                raise FileNotFoundError(msg)

            template_text = tmpl_file.read_text(encoding="utf-8")
            env = SandboxedEnvironment()
            template = env.from_string(template_text)

            for idx, row in enumerate(rows):
                headline = str(row.get("headline", ""))
                style_hint = row.get("style_hint")

                # Step 1: Generate image prompt
                image_prompt = _generate_image_prompt(headline, style_hint)

                # Step 2: Generate AI background
                bg_path = str(out / f"bg_{idx:04d}.png")
                ai_image = _generate_ai_background(image_prompt, bg_path)

                # Step 3: Encode as base64 and render template
                background_image = _encode_background(ai_image)
                html = template.render(
                    background_image=background_image,
                    accent_color=row.get("accent_color", "#e94560"),
                    **row,
                )

                # Step 4: Screenshot
                poster_path = str(out / f"poster_{idx:04d}.png")
                result = screenshot_run(
                    html_content=html,
                    output_path=poster_path,
                    viewport_width=800,
                    viewport_height=600,
                    full_page=False,
                )
                posters.append(result["file_path"])

                poster_score = score_poster_batch(Path(result["file_path"]))
                logger.info(
                    "Poster %d/%d rendered (score: %.1f): %s",
                    idx + 1,
                    len(rows),
                    poster_score.score,
                    poster_path,
                )

        # Record quality from last poster
        if posters:
            final_score = score_poster_batch(Path(posters[-1]))
            record_quality(did, final_score.score, final_score.passed)

        _check_and_export(did, client_id)

        return {
            "posters": posters,
            "count": len(posters),
            "status": "completed",
            "deliverable_id": did,
        }
    finally:
        clear_context()


def run(
    *,
    template_path: str | None = None,
    data_path: str | None = None,
    output_dir: str = "output/posters",
    client_id: str | None = None,
) -> dict[str, Any]:
    """Run poster batch pipeline with quality gates.

    Args:
        template_path: Path to Jinja2 HTML template. Required only for legacy
            non-client batch rendering.
        data_path: Path to CSV with one row per poster (required).
        output_dir: Directory for output PNG files.
        client_id: Optional client identifier for cost rollup.

    Returns:
        Dict with posters, count, status, deliverable_id, and quality_report.
    """
    if not data_path:
        msg = "data_path is required"
        raise ValueError(msg)
    if client_id is None and not template_path:
        msg = "template_path is required when client_id is not provided"
        raise ValueError(msg)

    inputs: dict[str, Any] = {
        "data_path": data_path,
        "output_dir": output_dir,
    }
    if template_path is not None:
        inputs["template_path"] = template_path
    if client_id is not None:
        inputs["client_id"] = client_id

    return run_with_gates(
        pipeline_fn=_pipeline_fn,
        inputs=inputs,
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        pipeline_name=_PIPELINE_NAME,
    )


def _check_and_export(did: str, client_id: str | None) -> None:
    """Check anomalies and export trace if needed.

    Args:
        did: Deliverable ID to check.
        client_id: Client ID for anomaly logging.
    """
    anomaly = check_anomalies(did)
    if anomaly["is_anomaly"]:
        trace_path = export_trace(did)
        log_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
        notify_anomaly(did, client_id, _PIPELINE_NAME, anomaly["reasons"], trace_path)
