"""Repo preflight checks for the pinned Hermes submodule setup."""
from __future__ import annotations

import configparser
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from adapter.hermes_registry import load_hermes_registry

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SUBMODULE_NAME = "hermes-agent"
_EXPECTED_UPSTREAM_URL = "git@github.com:NousResearch/hermes-agent.git"


@dataclass(frozen=True)
class DoctorCheck:
    """A single doctor check result."""

    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    """Full report for the Hermes submodule setup."""

    project_root: str
    hermes_path: str
    pinned_sha: str | None
    checked_out_sha: str | None
    checks: list[DoctorCheck]

    @property
    def has_failures(self) -> bool:
        return any(check.status == "fail" for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_status": "fail" if self.has_failures else "ok",
            "project_root": self.project_root,
            "hermes_path": self.hermes_path,
            "pinned_sha": self.pinned_sha,
            "checked_out_sha": self.checked_out_sha,
            "checks": [asdict(check) for check in self.checks],
        }


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "unknown git error"
        raise RuntimeError(detail)
    return result.stdout.rstrip("\n")


def _load_submodule_config(project_root: Path) -> dict[str, str]:
    """Load expected submodule settings from .gitmodules."""
    parser = configparser.ConfigParser()
    gitmodules_path = project_root / ".gitmodules"
    if not gitmodules_path.is_file():
        return {}
    parser.read(gitmodules_path)
    section = 'submodule "hermes-agent"'
    if section not in parser:
        return {}
    return {
        "path": parser.get(section, "path", fallback=_SUBMODULE_NAME),
        "url": parser.get(section, "url", fallback=""),
        "branch": parser.get(section, "branch", fallback=""),
    }


def _parse_submodule_status(raw_status: str) -> tuple[str, str | None]:
    """Parse ``git submodule status`` output."""
    line = raw_status.splitlines()[0].rstrip("\n")
    if not line:
        return ("?", None)
    status_flag = line[0]
    sha = line[1:].split()[0] if len(line) > 1 else None
    return (status_flag, sha)


def run_doctor(project_root: Path | None = None) -> DoctorReport:
    """Run Hermes submodule setup checks for this repo."""
    root = (project_root or _PROJECT_ROOT).resolve()
    submodule_config = _load_submodule_config(root)
    hermes_rel_path = submodule_config.get("path", _SUBMODULE_NAME)
    hermes_path = root / hermes_rel_path
    expected_origin = submodule_config.get("url", "")
    preferred_branch = submodule_config.get("branch", "")

    checks: list[DoctorCheck] = []
    pinned_sha: str | None = None
    checked_out_sha: str | None = None

    if not hermes_path.exists():
        checks.append(
            DoctorCheck(
                name="submodule_present",
                status="fail",
                detail=f"Missing submodule path: {hermes_path}",
            )
        )
        return DoctorReport(
            project_root=str(root),
            hermes_path=str(hermes_path),
            pinned_sha=None,
            checked_out_sha=None,
            checks=checks,
        )

    try:
        submodule_status = _run_git(
            ["submodule", "status", "--", hermes_rel_path],
            cwd=root,
        )
        status_flag, pinned_sha = _parse_submodule_status(submodule_status)
        if status_flag == " ":
            checks.append(
                DoctorCheck(
                    name="pinned_commit",
                    status="ok",
                    detail=f"Submodule is pinned and checked out at {pinned_sha}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="pinned_commit",
                    status="fail",
                    detail=(
                        "Submodule is not aligned with the repo-pinned commit "
                        f"(status '{status_flag}', sha {pinned_sha})"
                    ),
                )
            )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="pinned_commit",
                status="fail",
                detail=f"Unable to inspect submodule status: {exc}",
            )
        )

    try:
        checked_out_sha = _run_git(["rev-parse", "HEAD"], cwd=hermes_path)
        checks.append(
            DoctorCheck(
                name="git_repo",
                status="ok",
                detail=f"Hermes git repo available at {checked_out_sha[:12]}",
            )
        )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="git_repo",
                status="fail",
                detail=f"Hermes path is not a healthy git repo: {exc}",
            )
        )

    try:
        origin_url = _run_git(["remote", "get-url", "origin"], cwd=hermes_path)
        if expected_origin and origin_url == expected_origin:
            checks.append(
                DoctorCheck(
                    name="origin_remote",
                    status="ok",
                    detail=f"Origin matches fork URL {origin_url}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="origin_remote",
                    status="fail",
                    detail=(
                        f"Origin remote mismatch: expected {expected_origin!r}, "
                        f"got {origin_url!r}"
                    ),
                )
            )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="origin_remote",
                status="fail",
                detail=f"Origin remote unavailable: {exc}",
            )
        )

    try:
        upstream_url = _run_git(["remote", "get-url", "upstream"], cwd=hermes_path)
        if upstream_url == _EXPECTED_UPSTREAM_URL:
            checks.append(
                DoctorCheck(
                    name="upstream_remote",
                    status="ok",
                    detail=f"Upstream remote matches {_EXPECTED_UPSTREAM_URL}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="upstream_remote",
                    status="fail",
                    detail=(
                        "Upstream remote mismatch: expected "
                        f"{_EXPECTED_UPSTREAM_URL!r}, got {upstream_url!r}"
                    ),
                )
            )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="upstream_remote",
                status="fail",
                detail=f"Upstream remote unavailable: {exc}",
            )
        )

    try:
        branch = _run_git(["branch", "--show-current"], cwd=hermes_path)
        if not branch:
            checks.append(
                DoctorCheck(
                    name="maintenance_branch",
                    status="ok",
                    detail="Detached HEAD at the repo-pinned commit",
                )
            )
        elif preferred_branch and branch == preferred_branch:
            checks.append(
                DoctorCheck(
                    name="maintenance_branch",
                    status="ok",
                    detail=f"Checked out on preferred maintenance branch {branch}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="maintenance_branch",
                    status="warn",
                    detail=(
                        f"Checked out on {branch!r}; preferred branch is "
                        f"{preferred_branch!r}"
                    ),
                )
            )
    except RuntimeError as exc:
        checks.append(
            DoctorCheck(
                name="maintenance_branch",
                status="warn",
                detail=f"Unable to inspect current branch: {exc}",
            )
        )

    registry = load_hermes_registry(root)
    if registry is None or not hasattr(registry, "register"):
        checks.append(
            DoctorCheck(
                name="registry_loadable",
                status="fail",
                detail="Hermes registry could not be loaded from the submodule",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="registry_loadable",
                status="ok",
                detail="Hermes registry is importable and exposes register()",
            )
        )

    return DoctorReport(
        project_root=str(root),
        hermes_path=str(hermes_path),
        pinned_sha=pinned_sha,
        checked_out_sha=checked_out_sha,
        checks=checks,
    )


def main() -> None:
    """CLI entry point for repo doctor."""
    report = run_doctor()
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    raise SystemExit(1 if report.has_failures else 0)


if __name__ == "__main__":  # pragma: no cover
    main()
