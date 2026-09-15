"""
Пример модуля сверки от коллеги: Сверка платежных систем и агрегаторов (Paynet / Click / Payme).
Демонстрирует, насколько легко коллегам добавлять свои сверки без изменения ядра.
"""
import uuid
import time
from datetime import datetime
from typing import Dict, Any, Optional

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ValidationResult,
    ReconResult,
    ReconSummary,
)


class PaynetModule(BaseReconciliationModule):
    """Сверка платежных агентов и электронных денег по Transaction ID / Номеру заказа"""

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="paynet_agents",
            name="Сверка платежных систем (Paynet / Payme)",
            version="1.0.1",
            description="Сверка агентских отчетов с внутренним биллингом по Transaction ID, комиссиям агентов и статусам холда.",
            category="Платежные системы",
            icon="Receipt",
            author="Отдел электронной коммерции",
            status="active",
            required_permissions=["paynet.view", "paynet.run"],
            required_files=[
                {"key": "billing_file", "label": "Выгрузка биллинга / Orders (Excel/CSV)"},
                {"key": "agent_file", "label": "Реестр операций провайдера (Excel/CSV)"},
            ],
        )

    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        errors = []
        if "billing_file" not in files:
            errors.append("Не передан файл биллинга")
        if "agent_file" not in files:
            errors.append("Не передан реестр платежного агента")
        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        # Быстрая демонстрационная логика на время разработки
        t_start = time.time()
        run_id = str(uuid.uuid4())[:8]

        summary = ReconSummary(
            total_records_a=14200,
            total_records_b=14185,
            total_sum_a=185000000.0,
            total_sum_b=184850000.0,
            matched_count=14180,
            discrepancy_count=25,
            diff_sum=150000.0,
            match_percentage=99.86,
            execution_time_ms=round((time.time() - t_start) * 1000, 2),
        )

        return ReconResult(
            run_id=run_id,
            module_id="paynet_agents",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="WARNING",
            summary=summary,
            discrepancies=[
                {"order_id": "ORD-99124", "diff": 50000, "status": "Pending Agent Payout"},
                {"order_id": "ORD-99155", "diff": 100000, "status": "Cancel by user"},
            ],
            custom_metrics={"agent_commission_withheld": 1850000.0},
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Аналитика специфичная для платежных систем"""
        return {
            "module": "paynet_agents",
            "metrics": {
                "success_payment_rate": 99.86,
                "agent_commission_avg": "1.0%",
                "disputed_orders_count": 5,
                "top_providers": [
                    {"name": "Payme", "volume": 95000000.0, "share_pct": 51.3},
                    {"name": "Click", "volume": 68000000.0, "share_pct": 36.8},
                    {"name": "Paynet", "volume": 22000000.0, "share_pct": 11.9},
                ],
            },
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b"Paynet Excel Report"
