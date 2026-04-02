"""Tests for the parallel session bootstrap helper."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.bootstrap.parallel_sessions import (
    DEFAULT_REGISTRY_PATH,
    PacketConfig,
    PreparedPacket,
    branch_name_for,
    ensure_exclude_entry,
    filter_packets,
    load_registry,
    packet_map,
    packet_status,
    prepare_packet,
    render_packet_markdown,
    render_packet_prompt,
    worktree_path_for,
)


def test_load_registry_reads_expected_packets() -> None:
    """The registry loads the expected program and packet IDs."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    ids = [packet.id for packet in registry.packets]
    assert registry.program.slug == "v6-2"
    assert "contracts-ledger" in ids
    assert "clone-designspec" in ids


def test_filter_packets_by_wave() -> None:
    """Wave filters return only packets in that wave."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packets = filter_packets(registry, wave="wave1")
    assert packets
    assert all(packet.wave == "wave1" for packet in packets)


def test_branch_name_and_worktree_path_are_deterministic(tmp_path: Path) -> None:
    """Branch names and worktree paths are derived from program and packet slug."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["contracts-ledger"]
    assert branch_name_for(registry.program, packet) == "codex/v6-2-contracts-ledger"
    assert worktree_path_for(tmp_path, registry.program, packet) == (
        tmp_path / ".worktrees" / "v6_2" / "contracts-ledger"
    )


def test_render_packet_markdown_contains_key_sections() -> None:
    """The session note includes ownership and verification sections."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["selfbuild-gate"]
    content = render_packet_markdown(Path("/repo"), registry, packet)
    assert "# Selfbuild Promotion Gate" in content
    assert "## Owned Paths" in content
    assert "## Verification Commands" in content
    assert "augments/selfbuild/gate.py" in content


def test_render_packet_prompt_contains_summary_and_verification() -> None:
    """The generated prompt includes the packet summary and commands."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["bridge-capture"]
    content = render_packet_prompt(Path("/repo"), registry, packet)
    assert "Implement packet `bridge-capture`" in content
    assert "bridge/build_capture.py" in content
    assert "python3 -m pytest" in content


def test_ensure_exclude_entry_is_idempotent(tmp_path: Path) -> None:
    """Local ignore entries should not duplicate across repeated calls."""
    exclude_path = tmp_path / "info" / "exclude"
    ensure_exclude_entry(exclude_path, "/.codex-session/")
    ensure_exclude_entry(exclude_path, "/.codex-session/")
    lines = exclude_path.read_text(encoding="utf-8").splitlines()
    assert lines == ["/.codex-session/"]


def test_prepare_packet_dry_run_skips_git_and_writes_nothing(tmp_path: Path) -> None:
    """Dry-run mode reports the target worktree without calling git."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["contracts-ledger"]
    calls: list[tuple[list[str], Path]] = []

    def fake_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    prepared = prepare_packet(
        registry,
        packet,
        project_root=tmp_path,
        dry_run=True,
        git_runner=fake_git,
    )
    assert isinstance(prepared, PreparedPacket)
    assert calls == []
    assert not prepared.worktree_path.exists()


def test_prepare_packet_creates_session_files(tmp_path: Path) -> None:
    """Preparing a packet writes the local work order and prompt files."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["contracts-ledger"]
    worktree = worktree_path_for(tmp_path, registry.program, packet)

    def fake_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["worktree", "add", "-b"]:
            Path(args[3]).mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        if args == ["rev-parse", "--git-path", "info/exclude"]:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=str(worktree / ".git-info" / "exclude"),
                stderr="",
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    prepared = prepare_packet(
        registry,
        packet,
        project_root=tmp_path,
        dry_run=False,
        git_runner=fake_git,
    )

    assert prepared.worktree_path.exists()
    assert prepared.note_path.exists()
    assert prepared.prompt_path.exists()
    assert ".codex-session" in str(prepared.note_path)
    exclude = worktree / ".git-info" / "exclude"
    assert "/.codex-session/" in exclude.read_text(encoding="utf-8")


def test_packet_status_reports_clean_and_ready(tmp_path: Path) -> None:
    """Status includes branch, cleanliness, and note readiness."""
    registry = load_registry(DEFAULT_REGISTRY_PATH)
    packet = packet_map(registry)["bridge-capture"]
    worktree = worktree_path_for(tmp_path, registry.program, packet)
    session_dir = worktree / registry.program.session_dir
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / registry.program.session_note_file).write_text("note", encoding="utf-8")
    (session_dir / registry.program.session_prompt_file).write_text("prompt", encoding="utf-8")

    def fake_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="codex/v6-2-bridge-capture\n", stderr="")
        if args == ["status", "--short"]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected git args: {args}")

    row = packet_status(
        registry,
        packet,
        project_root=tmp_path,
        git_runner=fake_git,
    )
    assert row["status"] == "clean"
    assert row["notes"] == "ready"
    assert row["branch"] == "codex/v6-2-bridge-capture"
