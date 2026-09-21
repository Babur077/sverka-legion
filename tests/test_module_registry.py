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


class DraftModule(DummyModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="draft_recon",
            name="Draft reconciliation",
            version="0.1.0",
            description="Draft test module",
            category="Tests",
            icon="Layers",
            author="Tests",
            status="draft",
            required_permissions=["draft_recon.view", "draft_recon.run"],
            required_files=[],
        )


class InvalidIdModule(DummyModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="Bad-Module",
            name="Invalid id",
            version="0.1.0",
            description="Invalid test module",
            category="Tests",
            icon="Layers",
            author="Tests",
            required_permissions=["Bad-Module.view"],
            required_files=[],
        )


def test_registry_auto_discovers_production_modules():
    registry = ModuleRegistry()

    manifests = registry.list_manifests()
    by_id = {manifest.id: manifest for manifest in manifests}

    assert set(by_id) == {"bank_rrn", "ravan_1c", "reconciliation_builder"}
    assert by_id["bank_rrn"].workspace == "bank_rrn"
    assert "bank_rrn.export" in by_id["bank_rrn"].available_permissions
    assert by_id["reconciliation_builder"].workspace == "reconciliation_builder"
    assert "reconciliation_builder.manage" in by_id["reconciliation_builder"].available_permissions
    assert by_id["ravan_1c"].workspace == "ravan_1c"
    assert by_id["ravan_1c"].author == "Sayfulloh Abdusalomov"
    assert "ravan_1c.export" in by_id["ravan_1c"].available_permissions
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


def test_regular_users_do_not_see_draft_modules_but_admin_can():
    registry = ModuleRegistry(auto_discover=False)
    registry.register(DummyModule())
    registry.register(DraftModule())

    regular_ids = [
        manifest.id
        for manifest in registry.list_manifests(
            user_permissions=["dummy_recon.view", "draft_recon.view"]
        )
    ]
    admin_ids = [
        manifest.id
        for manifest in registry.list_manifests(user_permissions=["*"])
    ]

    assert regular_ids == ["dummy_recon"]
    assert admin_ids == ["dummy_recon", "draft_recon"]


def test_registry_rejects_invalid_module_id_format():
    registry = ModuleRegistry(auto_discover=False)

    with pytest.raises(ValueError, match="lowercase ASCII letter"):
        registry.register(InvalidIdModule())
