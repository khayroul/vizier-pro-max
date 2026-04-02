"""Extract YouTube transcripts with optional yt-dlp auto-caption fallback."""
from __future__ import annotations

import httpx
import structlog

logger = structlog.get_logger(__name__)


def _yt_dlp_auto_sub(video_id: str, languages: list[str]) -> dict[str, object] | None:
    """Fallback to yt-dlp auto-generated subtitles."""
    try:
        import yt_dlp  # type: ignore[import-untyped]
    except ImportError:
        return None

    preferred = languages[0] if languages else "en"
    ydl_opts: dict[str, object] = {
        "writeautomaticsub": True,
        "subtitleslangs": [preferred],
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:  # type: ignore[reportUnknownVariableType]
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)

    if not isinstance(info, dict):
        return None
    auto_subs = info.get("automatic_captions", {})
    if not isinstance(auto_subs, dict):
        return None
    language_entries = auto_subs.get(preferred, [])
    if not isinstance(language_entries, list):
        return None

    segments: list[dict[str, object]] = []
    for entry in language_entries:
        if not isinstance(entry, dict) or entry.get("ext") != "json3" or not entry.get("url"):
            continue
        response = httpx.get(str(entry["url"]), timeout=10)
        response.raise_for_status()
        payload = response.json()
        for event in payload.get("events", []):
            if not isinstance(event, dict):
                continue
            segs = event.get("segs", [])
            if not isinstance(segs, list):
                continue
            text = "".join(str(seg.get("utf8", "")) for seg in segs if isinstance(seg, dict)).strip()
            if text:
                segments.append(
                    {
                        "start": float(event.get("tStartMs", 0)) / 1000,
                        "duration": float(event.get("dDurationMs", 0)) / 1000,
                        "text": text,
                    }
                )
        break

    if not segments:
        return None

    return {
        "video_id": video_id,
        "language": preferred,
        "segments": segments,
        "full_text": " ".join(str(segment["text"]) for segment in segments),
        "source": "auto",
    }


def run(
    *,
    video_ids: list[str],
    languages: list[str] | None = None,
    fallback_auto: bool = True,
) -> dict[str, object]:
    """Fetch transcripts for one or more YouTube videos."""
    if not video_ids:
        msg = "video_ids is required"
        raise ValueError(msg)

    import youtube_transcript_api as transcript_api  # type: ignore[import-untyped]

    preferred_languages = languages or ["en", "ms"]
    transcripts = []
    failed = []

    for video_id in video_ids:
        try:
            raw_segments = transcript_api.YouTubeTranscriptApi.get_transcript(
                video_id,
                languages=preferred_languages,
            )
            segments = [
                {
                    "start": float(segment.get("start", 0.0)),
                    "duration": float(segment.get("duration", 0.0)),
                    "text": str(segment.get("text", "")),
                }
                for segment in raw_segments
            ]
            transcripts.append(
                {
                    "video_id": video_id,
                    "language": preferred_languages[0],
                    "segments": segments,
                    "full_text": " ".join(segment["text"] for segment in segments),
                    "source": "manual",
                }
            )
        except (transcript_api.NoTranscriptFound, transcript_api.TranscriptsDisabled):
            fallback = _yt_dlp_auto_sub(video_id, preferred_languages) if fallback_auto else None
            if fallback is not None:
                transcripts.append(fallback)
            else:
                failed.append({"video_id": video_id, "reason": "No transcript available"})
        except Exception as exc:  # noqa: BLE001
            logger.warning("Transcript fetch failed", video_id=video_id, error=str(exc))
            failed.append({"video_id": video_id, "reason": str(exc)})

    return {"transcripts": transcripts, "failed": failed}
