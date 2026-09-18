"""
Paynet / Payme reconciliation module.

Reconciles internal billing with a provider registry by Transaction ID and amount.
Optional status and provider commission columns are supported without changing the
platform contract.
"""
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import polars as pl

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ValidationResult,
    ReconResult,
    ReconSummary,
)
from core.parsers import load_file_polars, clean_amount_polars


class PaynetModule(BaseReconciliationModule):
    """Reconciliation of payment aggregators against internal billing."""

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="paynet",
            name="Сверка платежных систем (Paynet / Payme)",
            version="1.1.0",
            description="Сверка реестров платежных систем с внутренним биллингом по Transaction ID, суммам, статусам и комиссии.",
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
        if not files.get("billing_file"):
            errors.append("Не передан файл биллинга")
        if not files.get("agent_file"):
            errors.append("Не передан реестр платежного агента")

        required_params = [
            ("billing_id_col", "Transaction ID в биллинге"),
            ("billing_amount_col", "Сумма в биллинге"),
            ("agent_id_col", "Transaction ID у провайдера"),
            ("agent_amount_col", "Сумма у провайдера"),
        ]
        for key, label in required_params:
            if not str(params.get(key, "")).strip():
                errors.append(f"Не указана обязательная колонка: {label}")

        return ValidationResult(is_valid=not errors, errors=errors)

    @staticmethod
    def _as_float(value: Any, default: float = 0.01) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _normalise_id(column: str) -> pl.Expr:
        return (
            pl.col(column)
            .cast(pl.Utf8, strict=False)
            .fill_null("")
            .str.strip_chars()
            .str.replace(r"\.0$", "")
            .alias("transaction_id")
        )

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        t_start = time.time()
        run_id = str(uuid.uuid4())[:8]

        billing_raw = load_file_polars(
            files["billing_file"],
            params.get("billing_file_filename", "billing.xlsx"),
        )
        agent_raw = load_file_polars(
            files["agent_file"],
            params.get("agent_file_filename", "agent.xlsx"),
        )
        if billing_raw is None or agent_raw is None:
            raise ValueError("Не удалось распознать один из файлов.")

        billing_id_col = str(params["billing_id_col"])
        billing_amount_col = str(params["billing_amount_col"])
        billing_status_col = str(params.get("billing_status_col") or "")
        agent_id_col = str(params["agent_id_col"])
        agent_amount_col = str(params["agent_amount_col"])
        agent_status_col = str(params.get("agent_status_col") or "")
        agent_commission_col = str(params.get("agent_commission_col") or "")
        provider_name = str(params.get("provider_name") or "Paynet / Payme").strip()
        tolerance = max(0.0, self._as_float(params.get("tolerance"), 0.01))

        required_billing = [billing_id_col, billing_amount_col]
        required_agent = [agent_id_col, agent_amount_col]
        missing_billing = [c for c in required_billing if c not in billing_raw.columns]
        missing_agent = [c for c in required_agent if c not in agent_raw.columns]
        if missing_billing:
            raise ValueError("В биллинге не найдены колонки: " + ", ".join(missing_billing))
        if missing_agent:
            raise ValueError("В реестре провайдера не найдены колонки: " + ", ".join(missing_agent))

        billing_exprs = [
            self._normalise_id(billing_id_col),
            clean_amount_polars(billing_amount_col).alias("billing_amount"),
        ]
        if billing_status_col and billing_status_col in billing_raw.columns:
            billing_exprs.append(
                pl.col(billing_status_col).cast(pl.Utf8, strict=False).fill_null("").alias("billing_status")
            )
        else:
            billing_exprs.append(pl.lit("").alias("billing_status"))

        agent_exprs = [
            self._normalise_id(agent_id_col),
            clean_amount_polars(agent_amount_col).alias("agent_amount"),
        ]
        if agent_status_col and agent_status_col in agent_raw.columns:
            agent_exprs.append(
                pl.col(agent_status_col).cast(pl.Utf8, strict=False).fill_null("").alias("agent_status")
            )
        else:
            agent_exprs.append(pl.lit("").alias("agent_status"))
        if agent_commission_col and agent_commission_col in agent_raw.columns:
            agent_exprs.append(clean_amount_polars(agent_commission_col).alias("agent_commission"))
        else:
            agent_exprs.append(pl.lit(0.0).alias("agent_commission"))

        billing = (
            billing_raw.select(billing_exprs)
            .filter(pl.col("transaction_id") != "")
            .with_columns([
                pl.lit(True).alias("_billing_present"),
                pl.col("transaction_id").cum_count().over("transaction_id").alias("_dup_idx"),
            ])
        )
        agent = (
            agent_raw.select(agent_exprs)
            .filter(pl.col("transaction_id") != "")
            .with_columns([
                pl.lit(True).alias("_agent_present"),
                pl.col("transaction_id").cum_count().over("transaction_id").alias("_dup_idx"),
            ])
        )

        billing_dups = (
            billing.group_by("transaction_id")
            .len()
            .filter(pl.col("len") > 1)
            .sort("len", descending=True)
        )
        agent_dups = (
            agent.group_by("transaction_id")
            .len()
            .filter(pl.col("len") > 1)
            .sort("len", descending=True)
        )

        merged = billing.join(
            agent,
            on=["transaction_id", "_dup_idx"],
            how="full",
            coalesce=True,
        ).with_columns([
            pl.col("_billing_present").fill_null(False),
            pl.col("_agent_present").fill_null(False),
            (pl.col("agent_amount").fill_null(0.0) - pl.col("billing_amount").fill_null(0.0)).alias("amount_diff"),
        ])

        both = pl.col("_billing_present") & pl.col("_agent_present")
        status_diff = (
            both
            & (pl.col("billing_status").fill_null("") != "")
            & (pl.col("agent_status").fill_null("") != "")
            & (pl.col("billing_status").fill_null("") != pl.col("agent_status").fill_null(""))
        )
        amount_diff = both & (pl.col("amount_diff").abs() > tolerance)
        problem = amount_diff | status_diff

        only_billing = merged.filter(pl.col("_billing_present") & ~pl.col("_agent_present"))
        only_agent = merged.filter(~pl.col("_billing_present") & pl.col("_agent_present"))
        amount_mismatches = merged.filter(amount_diff)
        status_mismatches = merged.filter(status_diff)
        problem_rows = merged.filter(problem)

        both_count = merged.filter(both).height
        matched_count = max(0, both_count - problem_rows.height)
        discrepancy_count = only_billing.height + only_agent.height + problem_rows.height

        total_billing = float(billing["billing_amount"].sum()) if billing.height else 0.0
        total_agent = float(agent["agent_amount"].sum()) if agent.height else 0.0
        total_commission = float(agent["agent_commission"].sum()) if agent.height else 0.0
        match_percentage = round((matched_count / max(billing.height, 1)) * 100, 2)
        duration_ms = round((time.time() - t_start) * 1000, 2)

        def rows(frame: pl.DataFrame) -> list[dict]:
            return frame.drop([
                col for col in ["_billing_present", "_agent_present", "_dup_idx"]
                if col in frame.columns
            ]).to_dicts()

        discrepancy_rows = []
        for item in rows(problem_rows):
            reasons = []
            if abs(float(item.get("amount_diff") or 0.0)) > tolerance:
                reasons.append("Расхождение суммы")
            if (
                item.get("billing_status")
                and item.get("agent_status")
                and item.get("billing_status") != item.get("agent_status")
            ):
                reasons.append("Расхождение статуса")
            item["reason"] = ", ".join(reasons) or "Расхождение"
            discrepancy_rows.append(item)

        return ReconResult(
            run_id=run_id,
            module_id="paynet",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="COMPLETED" if discrepancy_count == 0 else "WARNING",
            summary=ReconSummary(
                total_records_a=billing.height,
                total_records_b=agent.height,
                total_sum_a=round(total_billing, 2),
                total_sum_b=round(total_agent, 2),
                matched_count=matched_count,
                discrepancy_count=discrepancy_count,
                diff_sum=round(total_agent - total_billing, 2),
                match_percentage=match_percentage,
                execution_time_ms=duration_ms,
            ),
            discrepancies=discrepancy_rows,
            custom_metrics={
                "paynet": {
                    "provider_name": provider_name,
                    "only_billing": rows(only_billing),
                    "only_agent": rows(only_agent),
                    "amount_mismatches": rows(amount_mismatches),
                    "status_mismatches": rows(status_mismatches),
                    "billing_duplicates": billing_dups.to_dicts(),
                    "agent_duplicates": agent_dups.to_dicts(),
                    "total_commission": round(total_commission, 2),
                    "tolerance": tolerance,
                }
            },
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "module": "paynet",
            "run_id": run_id,
            "metrics": {},
            "source": "archive",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""
