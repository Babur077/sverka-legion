"""
ReconcileHub reconciliation-module registry.

Production modules are discovered by convention:
  modules/<module_id>/engine.py -> MODULE_CLASS

A broken optional module must not prevent the platform from starting. Discovery
errors are recorded and logged while healthy modules remain available.
"""
from __future__ import annotations

import importlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Type

from modules.base import BaseReconciliationModule, ModuleManifest

logger = logging.getLogger(__name__)
MODULES_DIR = Path(__file__).resolve().parent


def discover_module_classes() -> tuple[list[Type[BaseReconciliationModule]], dict[str, str]]:
    classes: list[Type[BaseReconciliationModule]] = []
    errors: dict[str, str] = {}

    for child in sorted(MODULES_DIR.iterdir(), key=lambda path: path.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if not (child / "engine.py").exists():
            continue

        import_path = f"modules.{child.name}.engine"
        try:
            engine_module = importlib.import_module(import_path)
            module_class = getattr(engine_module, "MODULE_CLASS", None)
            if module_class is None:
                raise RuntimeError(
                    f"{import_path} must export MODULE_CLASS pointing to a BaseReconciliationModule subclass"
                )
            if not isinstance(module_class, type) or not issubclass(module_class, BaseReconciliationModule):
                raise TypeError(f"{import_path}.MODULE_CLASS is not a BaseReconciliationModule subclass")
            classes.append(module_class)
        except Exception as exc:
            errors[child.name] = str(exc)
            logger.exception("Failed to discover reconciliation module %s", child.name)

    return classes, errors


class ModuleRegistry:
    """Central registry for reconciliation modules."""

    def __init__(self, auto_discover: bool = True):
        self._modules: Dict[str, BaseReconciliationModule] = {}
        self.discovery_errors: Dict[str, str] = {}

        if auto_discover:
            module_classes, errors = discover_module_classes()
            self.discovery_errors.update(errors)
            for module_class in module_classes:
                try:
                    self.register(module_class())
                except Exception as exc:
                    module_name = getattr(module_class, "__name__", "unknown")
                    self.discovery_errors[module_name] = str(exc)
                    logger.exception("Failed to register reconciliation module %s", module_name)

    @staticmethod
    def _validate_manifest(manifest: ModuleManifest) -> None:
        module_id = manifest.id.strip()
        if not module_id:
            raise ValueError("Module manifest id cannot be empty")
        if module_id != manifest.id or not re.fullmatch(r"[a-z][a-z0-9_]*", module_id):
            raise ValueError(
                "Module id must start with a lowercase ASCII letter and contain only "
                f"lowercase letters, digits and underscores (received: {manifest.id!r})"
            )

        permission_prefix = f"{module_id}."
        declared_permissions = [
            *manifest.required_permissions,
            *manifest.available_permissions,
        ]
        invalid_permissions = [
            permission
            for permission in declared_permissions
            if not permission.startswith(permission_prefix)
        ]
        if invalid_permissions:
            raise ValueError(
                f"Permissions for module {module_id!r} must start with {permission_prefix!r}: "
                + ", ".join(invalid_permissions)
            )

        if len(manifest.available_permissions) != len(set(manifest.available_permissions)):
            raise ValueError(f"Module {module_id!r} has duplicate available permissions")

        file_keys = [str(item.get("key", "")).strip() for item in manifest.required_files]
        if any(not key for key in file_keys):
            raise ValueError(f"Module {module_id!r} has a required file without a key")
        if len(file_keys) != len(set(file_keys)):
            raise ValueError(f"Module {module_id!r} has duplicate required file keys")

    def register(self, module: BaseReconciliationModule) -> None:
        """Register one module and reject accidental id collisions."""
        if not isinstance(module, BaseReconciliationModule):
            raise TypeError("module must implement BaseReconciliationModule")

        manifest = module.manifest
        self._validate_manifest(manifest)

        if manifest.id in self._modules:
            raise ValueError(f"Reconciliation module {manifest.id!r} is already registered")

        self._modules[manifest.id] = module

    def get_module(self, module_id: str) -> Optional[BaseReconciliationModule]:
        return self._modules.get(module_id)

    def list_manifests(self, user_permissions: Optional[List[str]] = None) -> List[ModuleManifest]:
        manifests = [module.manifest for module in self._modules.values()]

        if user_permissions is None or "*" in user_permissions:
            return manifests

        return [
            manifest
            for manifest in manifests
            if manifest.status == "active"
            and any(permission in user_permissions for permission in manifest.required_permissions)
        ]


module_registry = ModuleRegistry()
