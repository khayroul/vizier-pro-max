"""Git watcher — detects commits and updates Hermes MEMORY.md.

Invoked by post-commit hook (immediate) and launchd cron (5-min fallback).
Idempotent — safe to call multiple times for the same commits.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path

import structlog  # type: ignore[import-untyped]

logger = structlog.get_logger(__name__)

_SKIP_AUTHORS = {"aider", "hermes"}
_STATE_FILE = Path.home() / ".vizier-pro-max" / "watcher-state.json"
_MEMORY_LOCK = threading.Lock()
_FUNC_PATTERN = re.compile(r"^[+-](async )?def (\w+)")
_CLASS_PATTERN = re.compile(r"^[+-]class (\w+)")


def _validate_sha(sha: str) -> bool:
    """Return True if sha is a valid 40-hex-char git SHA."""
    return bool(re.match(r"^[0-9a-f]{40}$", sha))


def detect_new_commits(last_sha: str, repo_path: Path) -> list[dict[str, str]]:
    """Detect commits made after last_sha in the given repo.

    Args:
        last_sha: The SHA of the last processed commit.
        repo_path: Path to the git repository root.

    Returns:
        List of commit dicts with keys ``sha``, ``subject``, ``author``.
        Authors in ``_SKIP_AUTHORS`` are excluded. Returns ``[]`` on error.
    """
    if not _validate_sha(last_sha):
        logger.warning("Invalid last_sha %r — treating as fresh start", last_sha)
        return []

    try:
        result = subprocess.run(
            ["git", "log", "--format=%H%x00%s%x00%an", f"{last_sha}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        logger.warning("git log failed: %s", exc.stderr)
        return []

    commits: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\x00", 2)
        if len(parts) != 3:
            continue
        sha, subject, author = parts
        if author.lower() in _SKIP_AUTHORS:
            continue
        commits.append({"sha": sha, "subject": subject, "author": author})

    return commits


def extract_changes(last_sha: str, repo_path: Path) -> dict[str, list[str]]:
    """Extract file and symbol-level changes since last_sha.

    Args:
        last_sha: The SHA of the last processed commit.
        repo_path: Path to the git repository root.

    Returns:
        Dict with keys: ``files_modified``, ``files_added``, ``files_deleted``,
        ``functions_added``, ``functions_removed``, ``classes_added``,
        ``classes_removed``. Values are deduplicated lists of strings.
    """
    empty_result: dict[str, list[str]] = {
        "files_modified": [],
        "files_added": [],
        "files_deleted": [],
        "functions_added": [],
        "functions_removed": [],
        "classes_added": [],
        "classes_removed": [],
    }
    if not _validate_sha(last_sha):
        logger.warning(
            "Invalid last_sha %r in extract_changes"
            " — returning empty",
            last_sha,
        )
        return empty_result

    files_modified: list[str] = []
    files_added: list[str] = []
    files_deleted: list[str] = []

    try:
        name_status = subprocess.run(
            ["git", "diff", "--name-status", f"{last_sha}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        for line in name_status.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, filepath = parts[0], parts[1]
            if status.startswith("M"):
                files_modified.append(filepath)
            elif status.startswith("A"):
                files_added.append(filepath)
            elif status.startswith("D"):
                files_deleted.append(filepath)
    except subprocess.CalledProcessError as exc:
        logger.warning("git diff --name-status failed: %s", exc.stderr)

    functions_added: set[str] = set()
    functions_removed: set[str] = set()
    classes_added: set[str] = set()
    classes_removed: set[str] = set()

    try:
        unified_diff = subprocess.run(
            ["git", "diff", "--unified=0", f"{last_sha}..HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        for line in unified_diff.stdout.splitlines():
            func_match = _FUNC_PATTERN.match(line)
            if func_match:
                name = func_match.group(2)
                if line.startswith("+"):
                    functions_added.add(name)
                else:
                    functions_removed.add(name)
                continue

            class_match = _CLASS_PATTERN.match(line)
            if class_match:
                name = class_match.group(1)
                if line.startswith("+"):
                    classes_added.add(name)
                else:
                    classes_removed.add(name)
    except subprocess.CalledProcessError as exc:
        logger.warning("git diff --unified=0 failed: %s", exc.stderr)

    return {
        "files_modified": files_modified,
        "files_added": files_added,
        "files_deleted": files_deleted,
        "functions_added": list(functions_added),
        "functions_removed": list(functions_removed),
        "classes_added": list(classes_added),
        "classes_removed": list(classes_removed),
    }


def format_memory_entry(
    commits: list[dict[str, str]],
    changes: dict[str, list[str]],
) -> str:
    """Format commits and changes into a MEMORY.md entry block.

    Args:
        commits: List of commit dicts with ``sha``, ``subject``, ``author``.
        changes: Dict from :func:`extract_changes`.

    Returns:
        Markdown-formatted entry string starting with a ``###`` heading.
    """
    now_utc = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    authors = sorted({c["author"] for c in commits})
    authors_joined = ", ".join(authors)

    lines: list[str] = [f"### {now_utc} — {authors_joined}"]

    for filepath in changes.get("files_modified", []):
        lines.append(f"- Modified `{filepath}`")
    for filepath in changes.get("files_added", []):
        lines.append(f"- Created `{filepath}`")
    for filepath in changes.get("files_deleted", []):
        lines.append(f"- Deleted `{filepath}`")

    funcs_added = changes.get("functions_added", [])
    if funcs_added:
        names = ", ".join(f"`{n}`" for n in sorted(funcs_added))
        lines.append(f"- Added functions: {names}")

    funcs_removed = changes.get("functions_removed", [])
    if funcs_removed:
        names = ", ".join(f"`{n}`" for n in sorted(funcs_removed))
        lines.append(f"- Removed functions: {names}")

    classes_added = changes.get("classes_added", [])
    if classes_added:
        names = ", ".join(f"`{n}`" for n in sorted(classes_added))
        lines.append(f"- Added classes: {names}")

    classes_removed = changes.get("classes_removed", [])
    if classes_removed:
        names = ", ".join(f"`{n}`" for n in sorted(classes_removed))
        lines.append(f"- Removed classes: {names}")

    for commit in commits:
        sha_short = commit["sha"][:7]
        lines.append(f'- Commit: {sha_short} "{commit["subject"]}"')

    return "\n".join(lines) + "\n"


def update_memory_md(memory_path: Path, entry: str, max_entries: int = 50) -> None:
    """Prepend a new entry to the ## Git Activity section in MEMORY.md.

    Creates the section if absent. Trims to ``max_entries`` total entries.
    All other sections are preserved unchanged.

    Args:
        memory_path: Path to the MEMORY.md file. Created fresh if missing.
        entry: Formatted markdown entry (starts with ``###``).
        max_entries: Maximum number of ``###`` entries to retain.
    """
    with _MEMORY_LOCK:
        if memory_path.exists():
            content = memory_path.read_text(encoding="utf-8")
        else:
            content = "# Hermes Memory\n"

        git_activity_header = "## Git Activity"

        if git_activity_header in content:
            # Split on the section header
            before, _, after = content.partition(git_activity_header)
            # Find where the next ## section starts (if any)
            next_section_match = re.search(r"\n## ", after)
            if next_section_match:
                section_body = after[: next_section_match.start()]
                rest = after[next_section_match.start() :]
            else:
                section_body = after
                rest = ""

            # Split existing entries on ### boundaries
            raw_entries = _split_entries(section_body)
            # Prepend new entry, trim to max
            all_entries = [entry] + raw_entries
            all_entries = all_entries[:max_entries]

            new_section = "\n".join(e.rstrip("\n") for e in all_entries)
            new_content = (
                before.rstrip("\n")
                + f"\n{git_activity_header}\n\n"
                + new_section
                + "\n"
                + rest
            )
        else:
            # Append the section at the end
            new_content = (
                content.rstrip("\n") + f"\n\n{git_activity_header}\n\n" + entry
            )

        memory_path.write_text(new_content, encoding="utf-8")


def _split_entries(section_body: str) -> list[str]:
    """Split a Git Activity section body into individual ### entries.

    Args:
        section_body: The text content after the ## Git Activity header.

    Returns:
        List of entry strings, each starting with ``###``.
    """
    entries: list[str] = []
    current: list[str] = []

    for line in section_body.splitlines():
        if line.startswith("### "):
            if current:
                entries.append("\n".join(current) + "\n")
                current = []
            current.append(line)
        elif current:
            current.append(line)

    if current:
        entries.append("\n".join(current) + "\n")

    return entries


def _load_state() -> dict[str, str]:
    """Load watcher state from _STATE_FILE.

    Returns:
        Parsed JSON dict, or ``{}`` if the file is missing or unreadable.
    """
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load watcher state: %s", exc)
        return {}


def _save_state(state: dict[str, str]) -> None:
    """Persist watcher state to _STATE_FILE (atomic via temp + rename).

    Args:
        state: Dict to serialise as JSON.
    """
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_STATE_FILE.parent), suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp_path, str(_STATE_FILE))
    except BaseException:
        with _suppress_os_error():
            os.unlink(tmp_path)
        raise


class _suppress_os_error:
    """Context manager that suppresses OSError (for cleanup paths)."""

    def __enter__(self) -> None:
        pass

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        return isinstance(exc_val, OSError)


def run(repo_path: Path | None = None) -> None:
    """Main entry point — detect new commits and update MEMORY.md.

    Args:
        repo_path: Path to the git repo. Defaults to the directory containing
            this file's grandparent (i.e. the repo root).
    """
    if repo_path is None:
        repo_path = Path(__file__).parent.parent

    state = _load_state()
    last_sha = state.get("last_sha", "")

    if not last_sha:
        # First run — record HEAD and exit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            head_sha = result.stdout.strip()
        except subprocess.CalledProcessError as exc:
            logger.warning("git rev-parse HEAD failed: %s", exc.stderr)
            return
        _save_state({"last_sha": head_sha, "last_run": _now_iso()})
        return

    commits = detect_new_commits(last_sha, repo_path)
    if not commits:
        _save_state({**state, "last_run": _now_iso()})
        return

    changes = extract_changes(last_sha, repo_path)
    entry = format_memory_entry(commits, changes)

    memory_path = repo_path / "hermes-workspace" / "memory" / "MEMORY.md"
    if memory_path.exists():
        update_memory_md(memory_path, entry)
    else:
        logger.info("MEMORY.md not found at %s — skipping write", memory_path)

    # Get current HEAD for new state
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        new_head = result.stdout.strip()
    except subprocess.CalledProcessError as exc:
        logger.warning("git rev-parse HEAD failed after processing: %s", exc.stderr)
        new_head = commits[0]["sha"]  # Use newest commit SHA as fallback

    _save_state({"last_sha": new_head, "last_run": _now_iso()})


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)
    run()
