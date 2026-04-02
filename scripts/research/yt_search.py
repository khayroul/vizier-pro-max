"""Search YouTube video metadata via yt-dlp."""
from __future__ import annotations

from datetime import datetime, timedelta

import structlog

logger = structlog.get_logger(__name__)

_DATE_FILTER_MAP = {
    "today": 1,
    "this_week": 7,
    "this_month": 30,
    "this_year": 365,
}


def _safe_int(value: object, default: int = 0) -> int:
    """Convert a loosely typed value to int safely."""
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def run(
    *,
    query: str,
    max_results: int = 20,
    date_filter: str = "",
    min_duration: int = 60,
    max_duration: int = 3600,
) -> dict[str, object]:
    """Search YouTube and return filtered metadata."""
    if not query:
        msg = "query is required"
        raise ValueError(msg)

    import yt_dlp  # type: ignore[import-untyped]

    ydl_opts: dict[str, object] = {
        "extract_flat": True,
        "quiet": True,
        "no_warnings": True,
    }

    search_url = f"ytsearch{max_results}:{query}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[reportUnknownVariableType]
        info = ydl.extract_info(search_url, download=False)

    entries = info.get("entries", []) if isinstance(info, dict) else []
    cutoff = None
    if date_filter:
        days = _DATE_FILTER_MAP.get(date_filter)
        if days is None:
            msg = f"Unsupported date_filter: {date_filter}"
            raise ValueError(msg)
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    results = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        duration = _safe_int(entry.get("duration"), 0)
        upload_date = str(entry.get("upload_date", ""))
        if duration < min_duration or duration > max_duration:
            continue
        if cutoff and upload_date and upload_date < cutoff:
            continue
        results.append(
            {
                "video_id": str(entry.get("id", "")),
                "title": str(entry.get("title", "")),
                "channel": str(entry.get("channel", entry.get("uploader", ""))),
                "upload_date": upload_date,
                "view_count": _safe_int(entry.get("view_count"), 0),
                "duration": duration,
                "description": str(entry.get("description", "")),
                "url": str(entry.get("url", entry.get("webpage_url", ""))),
            }
        )

    logger.info("YouTube search complete", query=query, result_count=len(results))
    return {"results": results, "query": query, "result_count": len(results)}
