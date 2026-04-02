"""Prepare and inspect packet-specific worktrees for the v6.2 build program."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT / "config" / "bootstrap" / "parallel_work_packets.yaml"
)


@dataclass(frozen=True)
class ProgramConfig:
    """Top-level configuration for the parallel build program."""

    id: str
    slug: str
    name: str
    spec_path: str
    plan_path: str
    worktree_root: str
    branch_prefix: str
    default_base_ref: str
    session_dir: str
    session_note_file: str
    session_prompt_file: str
    packet_order: list[str]


@dataclass(frozen=True)
class PacketConfig:
    """One work packet in the parallel implementation program."""

    id: str
    slug: str
    title: str
    wave: str
    tranche: str
    priority: int
    summary: str
    depends_on: list[str]
    owned_paths: list[str]
    read_paths: list[str]
    outputs: list[str]
    acceptance: list[str]
    do_not_touch: list[str]
    verification_commands: list[str]
    launch_prompt: str


@dataclass(frozen=True)
class PacketRegistry:
    """Complete program configuration loaded from YAML."""

    program: ProgramConfig
    packets: list[PacketConfig]


@dataclass(frozen=True)
class PreparedPacket:
    """Filesystem and branch information for one prepared packet."""

    packet_id: str
    branch: str
    worktree_path: Path
    created: bool
    note_path: Path
    prompt_path: Path


GitRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a git command and return the completed process."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> PacketRegistry:
    """Load the packet registry from YAML."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    program = ProgramConfig(**data["program"])
    packets = [PacketConfig(**packet) for packet in data["packets"]]
    return PacketRegistry(program=program, packets=packets)


def packet_map(registry: PacketRegistry) -> dict[str, PacketConfig]:
    """Index packets by their stable packet ID."""
    return {packet.id: packet for packet in registry.packets}


def ordered_packets(registry: PacketRegistry) -> list[PacketConfig]:
    """Return packets in the program's declared preferred order."""
    packets = packet_map(registry)
    return [packets[packet_id] for packet_id in registry.program.packet_order]


def filter_packets(
    registry: PacketRegistry,
    packet_ids: list[str] | None = None,
    wave: str | None = None,
    include_all: bool = False,
) -> list[PacketConfig]:
    """Select packets by ID, wave, or all."""
    packets = ordered_packets(registry)
    if include_all:
        return packets
    if packet_ids:
        packets_by_id = packet_map(registry)
        return [packets_by_id[packet_id] for packet_id in packet_ids]
    if wave:
        return [packet for packet in packets if packet.wave == wave]
    raise ValueError("Specify packet IDs, --wave, or --all.")


def branch_name_for(program: ProgramConfig, packet: PacketConfig) -> str:
    """Compute the branch name for a packet."""
    return f"{program.branch_prefix}-{packet.slug}"


def worktree_path_for(
    project_root: Path,
    program: ProgramConfig,
    packet: PacketConfig,
) -> Path:
    """Compute the worktree path for a packet."""
    return project_root / program.worktree_root / packet.slug


def ensure_exclude_entry(exclude_path: Path, entry: str) -> None:
    """Append a local ignore entry if it is not already present."""
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    if exclude_path.exists():
        existing = exclude_path.read_text(encoding="utf-8").splitlines()
    else:
        existing = []
    if entry not in existing:
        content = "\n".join([*existing, entry]).strip() + "\n"
        exclude_path.write_text(content, encoding="utf-8")


def render_packet_markdown(
    project_root: Path,
    registry: PacketRegistry,
    packet: PacketConfig,
) -> str:
    """Render the packet instructions saved inside a worktree."""
    spec_path = project_root / registry.program.spec_path
    plan_path = project_root / registry.program.plan_path
    lines = [
        f"# {packet.title}",
        "",
        f"- Packet ID: `{packet.id}`",
        f"- Wave: `{packet.wave}`",
        f"- Tranche: `{packet.tranche}`",
        f"- Summary: {packet.summary}",
        f"- Spec: `{spec_path}`",
        f"- Plan: `{plan_path}`",
        "",
        "## Dependencies",
    ]
    if packet.depends_on:
        lines.extend([f"- `{packet_id}`" for packet_id in packet.depends_on])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Owned Paths",
            *[f"- `{path}`" for path in packet.owned_paths],
            "",
            "## Read Paths",
            *[f"- `{path}`" for path in packet.read_paths],
            "",
            "## Outputs",
            *[f"- {item}" for item in packet.outputs],
            "",
            "## Acceptance",
            *[f"- {item}" for item in packet.acceptance],
            "",
            "## Do Not Touch",
            *[f"- `{item}`" for item in packet.do_not_touch],
            "",
            "## Verification Commands",
            *[f"- `{command}`" for command in packet.verification_commands],
            "",
            "## Operating Rule",
            "Only edit the owned paths for this packet. If you need an interface from another packet, consume the shared contract or wait for that packet to land instead of inventing a new interface.",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def render_packet_prompt(
    project_root: Path,
    registry: PacketRegistry,
    packet: PacketConfig,
) -> str:
    """Render the prompt that a new coding session should start from."""
    spec_path = project_root / registry.program.spec_path
    plan_path = project_root / registry.program.plan_path
    owned = "\n".join(f"- {path}" for path in packet.owned_paths)
    blocked = "\n".join(f"- {path}" for path in packet.do_not_touch)
    verify = "\n".join(f"- {command}" for command in packet.verification_commands)

    return (
        f"Implement packet `{packet.id}` ({packet.title}) for the Vizier v6.2 architecture.\n\n"
        f"Reference spec: {spec_path}\n"
        f"Reference plan: {plan_path}\n\n"
        f"Packet summary:\n{packet.summary}\n\n"
        f"Owned paths:\n{owned}\n\n"
        f"Do not touch:\n{blocked}\n\n"
        f"Acceptance:\n"
        + "\n".join(f"- {item}" for item in packet.acceptance)
        + "\n\nVerification commands:\n"
        + verify
        + "\n\nSpecial instruction:\n"
        + packet.launch_prompt.strip()
        + "\n"
    )


def write_session_files(
    worktree_path: Path,
    registry: PacketRegistry,
    packet: PacketConfig,
) -> tuple[Path, Path]:
    """Write local-only session guidance files inside a prepared worktree."""
    session_dir = worktree_path / registry.program.session_dir
    session_dir.mkdir(parents=True, exist_ok=True)

    note_path = session_dir / registry.program.session_note_file
    prompt_path = session_dir / registry.program.session_prompt_file
    packet_json_path = session_dir / "packet.json"

    note_path.write_text(
        render_packet_markdown(PROJECT_ROOT, registry, packet),
        encoding="utf-8",
    )
    prompt_path.write_text(
        render_packet_prompt(PROJECT_ROOT, registry, packet),
        encoding="utf-8",
    )
    packet_json_path.write_text(
        json.dumps(
            {
                "packet_id": packet.id,
                "title": packet.title,
                "wave": packet.wave,
                "tranche": packet.tranche,
                "owned_paths": packet.owned_paths,
                "depends_on": packet.depends_on,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return note_path, prompt_path


def prepare_packet(
    registry: PacketRegistry,
    packet: PacketConfig,
    *,
    project_root: Path = PROJECT_ROOT,
    base_ref: str | None = None,
    dry_run: bool = False,
    git_runner: GitRunner = _run_git,
) -> PreparedPacket:
    """Create or reuse a packet worktree and emit local session instructions."""
    program = registry.program
    branch = branch_name_for(program, packet)
    worktree_path = worktree_path_for(project_root, program, packet)
    base = base_ref or program.default_base_ref
    created = False

    if not worktree_path.exists():
        created = True
        if not dry_run:
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            git_runner(
                ["worktree", "add", "-b", branch, str(worktree_path), base],
                project_root,
            )

    if dry_run:
        note_path = worktree_path / program.session_dir / program.session_note_file
        prompt_path = (
            worktree_path / program.session_dir / program.session_prompt_file
        )
        return PreparedPacket(
            packet_id=packet.id,
            branch=branch,
            worktree_path=worktree_path,
            created=created,
            note_path=note_path,
            prompt_path=prompt_path,
        )

    exclude_path_text = git_runner(
        ["rev-parse", "--git-path", "info/exclude"],
        worktree_path,
    ).stdout.strip()
    exclude_path = Path(exclude_path_text)
    if not exclude_path.is_absolute():
        exclude_path = worktree_path / exclude_path
    ensure_exclude_entry(exclude_path, f"/{program.session_dir}/")

    note_path, prompt_path = write_session_files(worktree_path, registry, packet)
    return PreparedPacket(
        packet_id=packet.id,
        branch=branch,
        worktree_path=worktree_path,
        created=created,
        note_path=note_path,
        prompt_path=prompt_path,
    )


def packet_status(
    registry: PacketRegistry,
    packet: PacketConfig,
    *,
    project_root: Path = PROJECT_ROOT,
    git_runner: GitRunner = _run_git,
) -> dict[str, str]:
    """Collect current status information for one packet worktree."""
    worktree_path = worktree_path_for(project_root, registry.program, packet)
    note_path = worktree_path / registry.program.session_dir / registry.program.session_note_file
    prompt_path = (
        worktree_path / registry.program.session_dir / registry.program.session_prompt_file
    )

    if not worktree_path.exists():
        return {
            "packet_id": packet.id,
            "wave": packet.wave,
            "branch": "-",
            "status": "not-prepared",
            "worktree": str(worktree_path),
            "notes": "missing",
        }

    branch = git_runner(["branch", "--show-current"], worktree_path).stdout.strip()
    dirty_output = git_runner(["status", "--short"], worktree_path).stdout.strip()
    return {
        "packet_id": packet.id,
        "wave": packet.wave,
        "branch": branch or "-",
        "status": "dirty" if dirty_output else "clean",
        "worktree": str(worktree_path),
        "notes": "ready" if note_path.exists() and prompt_path.exists() else "missing",
    }


def _print_packet_list(registry: PacketRegistry) -> None:
    """Render a compact packet table."""
    print(f"{registry.program.name}")
    print()
    for packet in ordered_packets(registry):
        depends = ", ".join(packet.depends_on) if packet.depends_on else "-"
        print(
            f"{packet.id:26} {packet.wave:6} {packet.tranche:9} "
            f"depends: {depends}"
        )
        print(f"  {packet.summary}")


def _print_packet_show(registry: PacketRegistry, packet_id: str) -> None:
    """Render detailed information for a single packet."""
    packet = packet_map(registry)[packet_id]
    print(render_packet_markdown(PROJECT_ROOT, registry, packet))
    print("## Launch Prompt")
    print()
    print(render_packet_prompt(PROJECT_ROOT, registry, packet))


def _print_status(registry: PacketRegistry) -> None:
    """Render status lines for all packets."""
    for packet in ordered_packets(registry):
        row = packet_status(registry, packet)
        print(
            f"{row['packet_id']:26} {row['wave']:6} {row['status']:12} "
            f"{row['branch']:30} notes={row['notes']}"
        )


def _prepare_packets(
    registry: PacketRegistry,
    packets: list[PacketConfig],
    *,
    base_ref: str | None,
    dry_run: bool,
) -> None:
    """Prepare one or more packet worktrees and print the result."""
    for packet in packets:
        prepared = prepare_packet(
            registry,
            packet,
            base_ref=base_ref,
            dry_run=dry_run,
        )
        action = "Would prepare" if dry_run else "Prepared"
        print(f"{action} `{packet.id}`")
        print(f"  branch:   {prepared.branch}")
        print(f"  worktree: {prepared.worktree_path}")
        print(f"  prompt:   {prepared.prompt_path}")
        print(f"  notes:    {prepared.note_path}")


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Prepare packet-specific worktrees for the Vizier v6.2 program."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List all work packets.")

    show_parser = subparsers.add_parser("show", help="Show one work packet.")
    show_parser.add_argument("packet_id")

    status_parser = subparsers.add_parser(
        "status", help="Show worktree status for all packets."
    )
    status_parser.set_defaults(command="status")

    prepare_parser = subparsers.add_parser(
        "prepare", help="Prepare worktrees for packet sessions."
    )
    prepare_parser.add_argument("packet_ids", nargs="*")
    prepare_parser.add_argument("--wave", default=None)
    prepare_parser.add_argument("--all", action="store_true")
    prepare_parser.add_argument("--base-ref", default=None)
    prepare_parser.add_argument("--dry-run", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    registry = load_registry()

    if args.command == "list":
        _print_packet_list(registry)
        return

    if args.command == "show":
        _print_packet_show(registry, args.packet_id)
        return

    if args.command == "status":
        _print_status(registry)
        return

    if args.command == "prepare":
        packets = filter_packets(
            registry,
            packet_ids=args.packet_ids,
            wave=args.wave,
            include_all=args.all,
        )
        _prepare_packets(
            registry,
            packets,
            base_ref=args.base_ref,
            dry_run=args.dry_run,
        )
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":  # pragma: no cover
    main()
