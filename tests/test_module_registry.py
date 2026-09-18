from typing import Any, Dict, Optional

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
            required_permissions=["dummy.view", "dummy.run"],
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


def test_registry_contains_only_production_bank_module_by_default():
    registry = ModuleRegistry()
    ids = [manifest.id for manifest in registry.list_manifests()]
    assert ids == ["bank_rrn"]


def test_registry_accepts_new_modules_without_core_changes():
    registry = ModuleRegistry()
    registry.register(DummyModule())

    all_ids = [manifest.id for manifest in registry.list_manifests()]
    visible_ids = [
        manifest.id
        for manifest in registry.list_manifests(user_permissions=["dummy.view"])
    ]

    assert "dummy_recon" in all_ids
    assert visible_ids == ["dummy_recon"]
