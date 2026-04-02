"""Repo preflight checks for the pinned Hermes submodule setup."""
from __future__ import annotations

import configparser
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

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


def _detect_repo_python(project_root: Path) -> Path | None:
    """Return the repo-managed virtualenv Python if present."""
    candidates = [
        project_root / ".venv" / "bin" / "python",
        project_root / "venv" / "bin" / "python",
        project_root / ".venv" / "Scripts" / "python.exe",
        project_root / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    current = Path(sys.executable)
    return current if current.is_file() else None


def _run_python_snippet(python_path: Path, cwd: Path, code: str) -> str:
    """Run a short Python snippet and return stdout."""
    result = subprocess.run(
        [str(python_path), "-c", code],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "unknown python error"
        raise RuntimeError(detail)
    return result.stdout.strip()


def _parse_last_json_value(raw_output: str) -> Any:
    """Parse the last JSON object/array found in process output."""
    for line in reversed(raw_output.splitlines()):
        text = line.strip()
        if not text:
            continue
        if not text.startswith(("{", "[")):
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    raise RuntimeError("No JSON payload found in process output")


def _run_pip_check(python_path: Path, cwd: Path) -> tuple[bool, str]:
    """Run ``pip check`` and return ``(passed, detail)``."""
    result = subprocess.run(
        [str(python_path), "-m", "pip", "check"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    detail = (result.stdout or result.stderr).strip()
    return (result.returncode == 0, detail or "No dependency conflicts detected")


def _probe_shared_imports(python_path: Path, project_root: Path) -> dict[str, str]:
    """Check that the shared repo Python can import core Hermes modules."""
    code = """
import importlib
import json

results = {}
for name in ("hermes_cli.main", "gateway.run", "model_tools"):
    try:
        importlib.import_module(name)
        results[name] = "ok"
    except Exception as exc:
        results[name] = f"{type(exc).__name__}: {exc}"

print(json.dumps(results))
"""
    output = _run_python_snippet(python_path, project_root, code)
    parsed = _parse_last_json_value(output)
    if not isinstance(parsed, dict):
        raise RuntimeError("Shared import probe did not return a JSON object")
    return {str(key): str(value) for key, value in parsed.items()}


def _probe_plugin_loads(python_path: Path, hermes_path: Path) -> list[dict[str, Any]]:
    """Return Hermes plugin-manager results from the shared repo Python."""
    code = """
import json
import logging
import warnings

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

from hermes_cli.plugins import get_plugin_manager

manager = get_plugin_manager()
manager.discover_and_load()
print(json.dumps(manager.list_plugins()))
"""
    output = _run_python_snippet(python_path, hermes_path, code)
    parsed = _parse_last_json_value(output)
    if not isinstance(parsed, list):
        raise RuntimeError("Plugin probe did not return a JSON array")
    return [dict(item) for item in parsed]


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

    repo_python = _detect_repo_python(root)
    if repo_python is None:
        checks.append(
            DoctorCheck(
                name="repo_python",
                status="warn",
                detail="Repo virtualenv Python could not be detected",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                name="repo_python",
                status="ok",
                detail=f"Using repo Python at {repo_python}",
            )
        )

        pip_ok, pip_detail = _run_pip_check(repo_python, root)
        checks.append(
            DoctorCheck(
                name="dependency_conflicts",
                status="ok" if pip_ok else "fail",
                detail=pip_detail,
            )
        )

        try:
            import_results = _probe_shared_imports(repo_python, root)
            failures = {
                name: result
                for name, result in import_results.items()
                if result != "ok"
            }
            if failures:
                checks.append(
                    DoctorCheck(
                        name="shared_runtime_imports",
                        status="fail",
                        detail=f"Hermes imports failed in repo venv: {failures}",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="shared_runtime_imports",
                        status="ok",
                        detail="Repo venv can import Hermes runtime modules",
                    )
                )
        except RuntimeError as exc:
            checks.append(
                DoctorCheck(
                    name="shared_runtime_imports",
                    status="fail",
                    detail=f"Unable to probe shared Hermes imports: {exc}",
                )
            )

        try:
            plugin_results = _probe_plugin_loads(repo_python, hermes_path)
            broken_plugins = [
                plugin["name"]
                for plugin in plugin_results
                if plugin.get("error") and plugin.get("error") != "disabled via config"
            ]
            if broken_plugins:
                checks.append(
                    DoctorCheck(
                        name="plugin_runtime",
                        status="fail",
                        detail=f"Plugins failed to load: {', '.join(broken_plugins)}",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="plugin_runtime",
                        status="ok",
                        detail=f"Loaded {len(plugin_results)} Hermes plugins without errors",
                    )
                )
        except RuntimeError as exc:
            checks.append(
                DoctorCheck(
                    name="plugin_runtime",
                    status="fail",
                    detail=f"Unable to inspect Hermes plugins: {exc}",
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
