"""Session-scoped Telegram poster intake and revision state."""
from __future__ import annotations

import hashlib
import json
import os
import re
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


_SUPPORTED_POSTER_REFERENCE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
_SUPPORTED_POSTER_REFERENCE_LABEL = "PNG, JPG, or JPEG"
_CURRENT_POSTER_TURN: ContextVar["PosterTurnSignals | None"] = ContextVar(
    "vizier_current_poster_turn",
    default=None,
)

_IMAGE_URL_PATH_RE = re.compile(r"image_url:\s*(/[^]\n~]+)")
_ABSOLUTE_PATH_RE = re.compile(r"(/[^\n\]]+\.[A-Za-z0-9]+)")
_UNSUPPORTED_DOCUMENT_RE = re.compile(
    r"Unsupported document type '([^']+)'",
    flags=re.IGNORECASE,
)
_REFERENCE_INTENT_PATTERNS = (
    r"\buse this\b",
    r"\buse the sample\b",
    r"\buse the reference\b",
    r"\bmatch this\b",
    r"\bbased on this\b",
    r"\blike this\b",
    r"\bthis style\b",
    r"\bthis sample\b",
    r"\bthis reference\b",
    r"\bmake my poster\b",
    r"\brev(?:ise|ision)\b",
    r"\bupdate the poster\b",
)
_CRITIQUE_PATTERNS = (
    r"\bfeedback\b",
    r"\bcritique\b",
    r"\breview\b",
    r"\bwhat do you think\b",
    r"\bthoughts on\b",
    r"\bgive notes\b",
)
_REVISION_PATTERNS = (
    r"\brev(?:ise|ision)\b",
    r"\bupdate\b",
    r"\bchange\b",
    r"\bmake\b",
    r"\bremove\b",
    r"\bclean up\b",
    r"\bcleaner\b",
    r"\bbigger\b",
    r"\bsmaller\b",
    r"\bmore visible\b",
    r"\bmore premium\b",
    r"\bless empty\b",
    r"\bfix\b",
)
_ACTION_OVERRIDE_PATTERNS = (
    r"\buse\b",
    r"\bmake\b",
    r"\brev(?:ise|ision)\b",
    r"\bchange\b",
    r"\bupdate\b",
    r"\bapply\b",
)
_POSTER_CUE_PATTERNS = (
    r"\bposter\b",
    r"\bflyer\b",
    r"\bbanner\b",
    r"\bheadline\b",
    r"\blogo\b",
    r"\bbrand\b",
    r"\bmark\b",
    r"\blayout\b",
    r"\bhierarchy\b",
    r"\bheadline\b",
)


@dataclass(frozen=True)
class PosterSessionState:
    """Small session-scoped poster state for Telegram flows."""

    session_key: str = ""
    latest_generated_poster_path: str = ""
    latest_generated_trace_path: str = ""
    latest_generated_tool: str = ""
    latest_reference_image_path: str = ""
    latest_reference_source: str = ""
    latest_brief: str = ""
    latest_feedback_note: str = ""
    latest_poster_args: dict[str, Any] = field(default_factory=dict)
    latest_poster_result: dict[str, Any] = field(default_factory=dict)
    latest_revision_plan: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""


@dataclass(frozen=True)
class PosterTurnSignals:
    """Ephemeral cues derived from the current Telegram turn."""

    session_key: str = ""
    state: PosterSessionState = field(default_factory=PosterSessionState)
    gateway_text: str = ""
    user_text: str = ""
    reference_image_path: str = ""
    reference_image_updated: bool = False
    reference_source: str = ""
    unsupported_reference_extension: str = ""
    has_poster_context: bool = False
    critique_only: bool = False
    revision_candidate: bool = False
    reference_request: bool = False


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _session_state_root() -> Path:
    hermes_home = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes")))
    return hermes_home / "state" / "vizier" / "poster_sessions"


def _session_state_path(session_key: str) -> Path:
    digest = hashlib.sha256(session_key.encode("utf-8")).hexdigest()[:24]
    return _session_state_root() / f"{digest}.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _normalize_session_key(session_key: str | None = None) -> str:
    value = str(session_key or os.getenv("HERMES_SESSION_KEY", "")).strip()
    return value


def _is_telegram_session() -> bool:
    return os.getenv("HERMES_SESSION_PLATFORM", "").strip().lower() == "telegram"


def load_poster_session_state(session_key: str | None = None) -> PosterSessionState:
    """Load the session-scoped Telegram poster state from disk."""
    normalized = _normalize_session_key(session_key)
    if not normalized:
        return PosterSessionState()
    path = _session_state_path(normalized)
    if not path.is_file():
        return PosterSessionState(session_key=normalized)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return PosterSessionState(session_key=normalized)
    if not isinstance(payload, dict):
        return PosterSessionState(session_key=normalized)
    return PosterSessionState(
        session_key=normalized,
        latest_generated_poster_path=str(payload.get("latest_generated_poster_path", "")),
        latest_generated_trace_path=str(payload.get("latest_generated_trace_path", "")),
        latest_generated_tool=str(payload.get("latest_generated_tool", "")),
        latest_reference_image_path=str(payload.get("latest_reference_image_path", "")),
        latest_reference_source=str(payload.get("latest_reference_source", "")),
        latest_brief=str(payload.get("latest_brief", "")),
        latest_feedback_note=str(payload.get("latest_feedback_note", "")),
        latest_poster_args=dict(payload.get("latest_poster_args") or {}),
        latest_poster_result=dict(payload.get("latest_poster_result") or {}),
        latest_revision_plan=dict(payload.get("latest_revision_plan") or {}),
        updated_at=str(payload.get("updated_at", "")),
    )


def save_poster_session_state(state: PosterSessionState) -> PosterSessionState:
    """Persist a Telegram poster session state snapshot."""
    if not state.session_key:
        return state
    payload = asdict(state)
    _atomic_write_json(_session_state_path(state.session_key), payload)
    return state


def _update_state(
    state: PosterSessionState,
    **changes: Any,
) -> PosterSessionState:
    updated = replace(
        state,
        updated_at=_utcnow(),
        **changes,
    )
    return save_poster_session_state(updated)


def _clean_json_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    return json.loads(json.dumps(dict(value), ensure_ascii=False, default=str))


def _poster_state_payload(state: PosterSessionState) -> dict[str, Any]:
    return asdict(state)


def get_current_poster_turn_signals() -> PosterTurnSignals | None:
    return _CURRENT_POSTER_TURN.get()


def clear_current_poster_turn_signals() -> None:
    _CURRENT_POSTER_TURN.set(None)


def _set_current_poster_turn_signals(signals: PosterTurnSignals | None) -> None:
    _CURRENT_POSTER_TURN.set(signals)


def _ensure_supported_image_documents() -> None:
    """Allow PNG/JPG/JPEG Telegram image documents through Hermes."""
    try:
        from gateway.platforms.base import SUPPORTED_DOCUMENT_TYPES
    except Exception:
        return
    for extension, mime_type in _SUPPORTED_POSTER_REFERENCE_TYPES.items():
        SUPPORTED_DOCUMENT_TYPES.setdefault(extension, mime_type)


def _strip_gateway_notes(text: str) -> str:
    if not text:
        return ""
    stripped = re.sub(r"\[[^\]]+\]", " ", text, flags=re.DOTALL)
    return " ".join(stripped.split()).strip()


def _extract_local_paths(text: str) -> list[str]:
    paths: list[str] = []
    for match in _IMAGE_URL_PATH_RE.finditer(text):
        candidate = match.group(1).strip()
        if candidate:
            paths.append(candidate)
    for match in _ABSOLUTE_PATH_RE.finditer(text):
        candidate = match.group(1).strip()
        if candidate and candidate not in paths:
            paths.append(candidate)
    return paths


def _path_extension(path: str) -> str:
    return Path(path).suffix.lower().strip()


def _supported_reference_path(path: str) -> bool:
    return _path_extension(path) in _SUPPORTED_POSTER_REFERENCE_TYPES


def _guess_reference_source(path: str, gateway_text: str) -> str:
    if "image_url:" in gateway_text and path in gateway_text:
        return "telegram_photo"
    if Path(path).name.startswith("doc_"):
        return "telegram_image_document"
    return "telegram_image"


def record_reference_image(
    reference_image_path: str,
    *,
    source: str,
    session_key: str | None = None,
) -> PosterSessionState:
    """Store the active Telegram poster reference image for this session."""
    normalized_session_key = _normalize_session_key(session_key)
    state = load_poster_session_state(normalized_session_key)
    if not normalized_session_key or not reference_image_path.strip():
        return state
    return _update_state(
        state,
        latest_reference_image_path=reference_image_path.strip(),
        latest_reference_source=source.strip(),
    )


def record_feedback_note(
    feedback: str,
    *,
    session_key: str | None = None,
    revision_plan: Mapping[str, Any] | None = None,
) -> PosterSessionState:
    """Persist the latest poster feedback note for this Telegram session."""
    normalized_session_key = _normalize_session_key(session_key)
    state = load_poster_session_state(normalized_session_key)
    if not normalized_session_key or not feedback.strip():
        return state
    return _update_state(
        state,
        latest_feedback_note=feedback.strip(),
        latest_revision_plan=_clean_json_mapping(revision_plan),
    )


def record_poster_result(
    *,
    tool_name: str,
    tool_args: Mapping[str, Any],
    result_payload: Mapping[str, Any],
    session_key: str | None = None,
) -> PosterSessionState:
    """Track the latest generated or revised poster for a session."""
    normalized_session_key = _normalize_session_key(session_key)
    state = load_poster_session_state(normalized_session_key)
    if not normalized_session_key:
        return state

    poster_path = str(result_payload.get("poster_path", "")).strip()
    if not poster_path:
        return state

    creative_brief = result_payload.get("creative_brief") or {}
    latest_brief = str(
        tool_args.get("brief")
        or creative_brief.get("raw_brief")
        or state.latest_brief
    ).strip()
    revision_plan = result_payload.get("revision_plan") or state.latest_revision_plan
    return _update_state(
        state,
        latest_generated_poster_path=poster_path,
        latest_generated_trace_path=str(result_payload.get("trace_path", "")).strip(),
        latest_generated_tool=tool_name,
        latest_brief=latest_brief,
        latest_poster_args=_clean_json_mapping(tool_args),
        latest_poster_result=_clean_json_mapping(result_payload),
        latest_revision_plan=_clean_json_mapping(revision_plan),
    )


def record_pipeline_posters(
    result_payload: Mapping[str, Any],
    *,
    session_key: str | None = None,
) -> PosterSessionState:
    """Best-effort poster tracking for run_pipeline outputs that emit posters."""
    normalized_session_key = _normalize_session_key(session_key)
    state = load_poster_session_state(normalized_session_key)
    if not normalized_session_key:
        return state
    operational_assets = result_payload.get("operational_assets") or {}
    client_posters = list(operational_assets.get("client_poster_paths") or [])
    latest_path = str(client_posters[-1]).strip() if client_posters else ""
    if not latest_path:
        return state
    return _update_state(
        state,
        latest_generated_poster_path=latest_path,
        latest_generated_tool="run_pipeline",
        latest_poster_result=_clean_json_mapping(result_payload),
    )


def resolve_reference_image_path(explicit_path: str = "") -> str:
    """Resolve the active session reference image for Telegram poster work."""
    explicit = explicit_path.strip()
    if explicit:
        return explicit
    state = load_poster_session_state()
    return state.latest_reference_image_path


def poster_session_payload() -> dict[str, Any]:
    return _poster_state_payload(load_poster_session_state())


def _has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _reference_request(text: str, has_reference: bool) -> bool:
    if not has_reference:
        return False
    return _has_pattern(text, _REFERENCE_INTENT_PATTERNS)


def _critique_only(text: str, has_poster_context: bool) -> bool:
    if not has_poster_context:
        return False
    if not _has_pattern(text, _CRITIQUE_PATTERNS):
        return False
    return not _has_pattern(text, _ACTION_OVERRIDE_PATTERNS)


def _revision_candidate(text: str, state: PosterSessionState, has_reference: bool) -> bool:
    if not (state.latest_generated_poster_path or has_reference):
        return False
    return _has_pattern(text, _REVISION_PATTERNS)


def _poster_context(text: str, state: PosterSessionState, has_reference: bool) -> bool:
    if has_reference:
        return True
    if state.latest_generated_poster_path or state.latest_reference_image_path:
        return True
    return _has_pattern(text, _POSTER_CUE_PATTERNS)


def observe_telegram_poster_turn(
    *,
    user_message: str,
    conversation_history: list[dict[str, Any]] | None = None,
    platform: str = "",
    **_: Any,
) -> PosterTurnSignals | None:
    """Prime poster session state from the current Telegram turn."""
    del conversation_history  # currently unused, reserved for future session work
    if platform.strip().lower() != "telegram":
        clear_current_poster_turn_signals()
        return None

    _ensure_supported_image_documents()

    gateway_text = user_message or ""
    user_text = _strip_gateway_notes(gateway_text).lower()
    session_key = _normalize_session_key()
    state = load_poster_session_state(session_key)

    supported_reference_path = ""
    reference_source = ""
    for path in reversed(_extract_local_paths(gateway_text)):
        if not _supported_reference_path(path):
            continue
        supported_reference_path = path
        reference_source = _guess_reference_source(path, gateway_text)
        state = record_reference_image(path, source=reference_source, session_key=session_key)
        break

    has_reference = bool(supported_reference_path or state.latest_reference_image_path)
    has_poster_context = _poster_context(user_text, state, has_reference)
    reference_request = _reference_request(user_text, has_reference)
    critique_only = _critique_only(user_text, has_poster_context)
    revision_candidate = _revision_candidate(user_text, state, has_reference)

    unsupported_extension = ""
    for path in reversed(_extract_local_paths(gateway_text)):
        extension = _path_extension(path)
        if extension and extension not in _SUPPORTED_POSTER_REFERENCE_TYPES:
            if has_poster_context or reference_request:
                unsupported_extension = extension
                break
    if not unsupported_extension:
        match = _UNSUPPORTED_DOCUMENT_RE.search(gateway_text)
        if match and (has_poster_context or reference_request):
            unsupported_extension = match.group(1).strip().lower()

    if (revision_candidate or critique_only or reference_request) and user_text:
        state = record_feedback_note(user_text, session_key=session_key)

    signals = PosterTurnSignals(
        session_key=session_key,
        state=state,
        gateway_text=gateway_text,
        user_text=user_text,
        reference_image_path=supported_reference_path or state.latest_reference_image_path,
        reference_image_updated=bool(supported_reference_path),
        reference_source=reference_source,
        unsupported_reference_extension=unsupported_extension,
        has_poster_context=has_poster_context,
        critique_only=critique_only,
        revision_candidate=revision_candidate,
        reference_request=reference_request,
    )
    _set_current_poster_turn_signals(signals)
    return signals


def build_telegram_poster_context(
    *,
    platform: str = "",
    **_: Any,
) -> str:
    """Inject Telegram poster-state guidance into the current turn."""
    if platform.strip().lower() != "telegram":
        return ""
    signals = get_current_poster_turn_signals()
    if signals is None:
        return ""

    lines: list[str] = []
    if signals.reference_image_updated and signals.reference_image_path:
        lines.append(
            "A supported Telegram image from this turn has been stored as the active session poster reference."
        )
        lines.append(
            f"Active reference image path: {signals.reference_image_path}"
        )
        lines.append(
            "If the user only sent the image, briefly acknowledge that it is stored and say it can be used for critique, a new poster, or a revision."
        )
    if signals.unsupported_reference_extension:
        lines.append(
            f"The user tried to provide an unsupported poster reference file ({signals.unsupported_reference_extension})."
        )
        lines.append(
            f"Do not pretend to have used it. Ask for a {_SUPPORTED_POSTER_REFERENCE_LABEL} poster image instead."
        )
    if signals.revision_candidate and signals.state.latest_generated_poster_path:
        lines.append(
            "This looks like a poster revision turn tied to the latest generated poster in this session."
        )
        lines.append(
            "Prefer revise_poster over generate_poster so the revision is grounded in the prior poster state, prior copy, and any stored reference image."
        )
        lines.append(
            "Summarize the requested changes calmly, then explain what changed after the revision."
        )
        lines.append(
            "Do not say 'fixed' or 'done' unless every requested self-check item clearly passed."
        )
    if signals.critique_only:
        lines.append(
            "The user may only want critique or feedback on the poster. Keep this in assistant mode unless they explicitly ask you to make changes."
        )
    if not lines:
        return ""
    return "Telegram poster session support is active.\n- " + "\n- ".join(lines)


def post_tool_call(
    *,
    tool_name: str,
    args: Mapping[str, Any],
    result: Any,
    **_: Any,
) -> None:
    """Persist poster session state after relevant tool calls."""
    if not _is_telegram_session():
        return
    if not _normalize_session_key():
        return

    payload: dict[str, Any] | None = None
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            payload = parsed
    elif isinstance(result, Mapping):
        payload = dict(result)

    if not isinstance(payload, dict):
        return

    if tool_name == "run_pipeline":
        record_pipeline_posters(payload)


def register(ctx: Any) -> None:
    """Register Telegram poster session hooks and startup mutations."""
    _ensure_supported_image_documents()
    ctx.register_hook("pre_tool_resolution", observe_telegram_poster_turn)
    ctx.register_hook("pre_llm_call", build_telegram_poster_context)
    ctx.register_hook("post_tool_call", post_tool_call)
