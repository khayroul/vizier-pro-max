"""Helpers for loading Hermes registry objects from the pinned submodule."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_MODULE_NAME = "_vizier_hermes_tools_registry"


def hermes_registry_path(project_root: Path | None = None) -> Path:
    """Return the on-disk path to Hermes' registry module."""
    root = project_root or _PROJECT_ROOT
    return root / "hermes-agent" / "tools" / "registry.py"


def load_hermes_registry(project_root: Path | None = None) -> object | None:
    """Load Hermes' tool registry from the pinned submodule path.

    This repo also has a first-party ``tools`` package, so importing
    ``tools.registry`` directly is ambiguous. Loading Hermes' registry from
    its pinned file path avoids package shadowing and keeps integration stable.
    """
    path = hermes_registry_path(project_root).resolve()
    if not path.is_file():
        logger.warning("Hermes registry file not found: %s", path)
        return None

    cached_module = sys.modules.get(_REGISTRY_MODULE_NAME)
    if cached_module is not None:
        cached_path = getattr(cached_module, "__file__", "")
        if cached_path and Path(cached_path).resolve() == path:
            registry = getattr(cached_module, "registry", None)
            if registry is not None:
                return registry

    spec = importlib.util.spec_from_file_location(_REGISTRY_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        logger.warning("Cannot load Hermes registry spec from: %s", path)
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[_REGISTRY_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop(_REGISTRY_MODULE_NAME, None)
        logger.warning("Failed to import Hermes registry from %s: %s", path, exc)
        return None

    registry = getattr(module, "registry", None)
    if registry is None:
        logger.warning("Hermes registry module has no 'registry': %s", path)
        return None
    return registry
