from typing import Any, Dict, Optional

import pytest

from modules.base import BaseReconciliationModule, ModuleManifest, ReconResult, ValidationResult
from modules.registry import ModuleRegistry


class DummyModule(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="dummy_recon",
            name="Dummy reconciliation",
            version="0.1.0",
            description="Test-only reconciliation module",
            category="Tests",
            icon="Layers",
            author="Tests",
            workspace=None,
            required_permissions=["dummy_recon.view", "dummy_recon.run"],
            required_files=[],
        )

    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        return ValidationResult(is_valid=True)

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        raise NotImplementedError

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {}

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""


class BadPermissionModule(DummyModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="bad_module",
            name="Bad permissions",
            version="0.1.0",
            description="Invalid test module",
            category="Tests",
            icon="Layers",
            author="Tests",
            required_permissions=["other.view"],
            required_files=[],
        )


class DuplicateFileKeyModule(DummyModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="duplicate_files",
            name="Duplicate file keys",
            version="0.1.0",
            description="Invalid test module",
            category="Tests",
            icon="Layers",
            author="Tests",
            required_permissions=["duplicate_files.view"],
            required_files=[
                {"key": "source", "label": "Source A"},
                {"key": "source", "label": "Source B"},
            ],
        )


def test_registry_auto_discovers_only_production_bank_module():
    registry = ModuleRegistry()

    manifests = registry.list_manifests()

    assert [manifest.id for manifest in manifests] == ["bank_rrn"]
    assert manifests[0].workspace == "bank_rrn"
    assert registry.discovery_errors == {}


def test_registry_accepts_new_modules_without_core_changes():
    registry = ModuleRegistry(auto_discover=False)
    registry.register(DummyModule())

    all_ids = [manifest.id for manifest in registry.list_manifests()]
    visible_ids = [
        manifest.id
        for manifest in registry.list_manifests(user_permissions=["dummy_recon.view"])
    ]

    assert all_ids == ["dummy_recon"]
    assert visible_ids == ["dummy_recon"]


def test_registry_rejects_duplicate_module_ids():
    registry = ModuleRegistry(auto_discover=False)
    registry.register(DummyModule())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(DummyModule())


def test_registry_rejects_permissions_from_another_module_prefix():
    registry = ModuleRegistry(auto_discover=False)

    with pytest.raises(ValueError, match="must start with"):
        registry.register(BadPermissionModule())


def test_registry_rejects_duplicate_required_file_keys():
    registry = ModuleRegistry(auto_discover=False)

    with pytest.raises(ValueError, match="duplicate required file keys"):
        registry.register(DuplicateFileKeyModule())
