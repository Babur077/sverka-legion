from __future__ import annotations

from typing import Any, Dict, Optional

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ReconResult,
    ValidationResult,
)


class VoronaModule(BaseReconciliationModule):
    """Registry adapter for Diyorbek Allayarov's existing Vorona application.

    The reconciliation business logic remains in VORONA_upload/app.py and the
    PostgreSQL VORONA database. This class only makes that workspace visible to
    ReconcileHub's module registry and RBAC catalog.
    """

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="vorona",
            name="Сверка Vorona",
            version="1.0.0",
            description=(
                "Сверка взаиморасчётов по данным продаж, оплат, счетов-фактур, "
                "начального сальдо и 1С. Расчётная логика оригинальной Vorona сохранена."
            ),
            category="Взаиморасчёты",
            icon="Building2",
            author="Diyorbek Allayarov",
            status="active",
            workspace="vorona",
            required_permissions=[
                "vorona.view",
                "vorona.run",
                "vorona.manage",
            ],
            available_permissions=[
                "vorona.view",
                "vorona.run",
                "vorona.manage",
            ],
            required_files=[],
        )

    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            is_valid=True,
            warnings=[
                "Vorona работает с собственной PostgreSQL-базой VORONA; "
                "файлы загружаются внутри рабочего места модуля."
            ],
        )

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        raise RuntimeError(
            "Сверка Vorona запускается из специализированного рабочего места и PostgreSQL-базы VORONA."
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "module_id": "vorona",
            "storage": "PostgreSQL VORONA",
            "business_logic": "VORONA_upload/app.py",
            "status": "workspace_managed",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        raise RuntimeError("Экспорт выполняется внутри рабочего места Сверка Vorona.")


MODULE_CLASS = VoronaModule
