"""Load YAML manifests and register tools into Hermes via registry.register()."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from adapter.executor import execute_tool
from adapter.schemas import ManifestConfig, manifest_to_openai_schema, parse_manifest

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _get_registry() -> object | None:
    """Lazy import of Hermes tool registry.

    Returns:
        Registry object if available, None otherwise.
    """
    try:
        from tools.registry import registry  # type: ignore[import-not-found]

        return registry
    except ImportError:
        logger.warning("Hermes registry not available — tools will not be registered")
        return None


def load_all_manifests(manifests_dir: Path) -> list[ManifestConfig]:
    """Glob all YAML manifests under the given directory.

    Args:
        manifests_dir: Root directory to search for *.yaml files.

    Returns:
        List of validated ManifestConfig instances. Invalid files are skipped.
    """
    if not manifests_dir.is_dir():
        logger.warning("Manifests directory not found: %s", manifests_dir)
        return []

    manifests: list[ManifestConfig] = []

    for yaml_path in sorted(manifests_dir.rglob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue

        try:
            content = yaml_path.read_text(encoding="utf-8")
            config = parse_manifest(content)
            manifests.append(config)
            logger.info(
                "Loaded manifest: %s (toolset: %s)", config.name, config.toolset
            )
        except (ValueError, OSError) as exc:
            logger.warning("Skipping invalid manifest %s: %s", yaml_path, exc)

    return manifests


def register_manifest(manifest: ManifestConfig) -> None:
    """Register a single manifest as a Hermes tool.

    Args:
        manifest: Validated ManifestConfig to register.
    """
    registry = _get_registry()
    if registry is None:
        return

    schema = manifest_to_openai_schema(manifest)

    registry.register(  # type: ignore[union-attr]
        name=manifest.name,
        toolset=manifest.toolset,
        schema=schema,
        handler=lambda args, **kw: execute_tool(manifest, args),
        check_fn=lambda: True,
        description=manifest.description,
    )

    logger.info("Registered tool: %s -> toolset %s", manifest.name, manifest.toolset)


def register_all(manifests_dir: Path) -> int:
    """Load all manifests and register them into Hermes.

    Args:
        manifests_dir: Root directory containing manifest YAML files.

    Returns:
        Number of tools successfully registered.
    """
    manifests = load_all_manifests(manifests_dir)
    registered = 0

    for manifest in manifests:
        try:
            register_manifest(manifest)
            registered += 1
        except Exception as exc:
            logger.warning("Failed to register %s: %s", manifest.name, exc)

    logger.info(
        "Registered %d/%d tools from manifests", registered, len(manifests)
    )
    return registered
