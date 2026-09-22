"""
Модуль сверки банковского эквайринга по кодам RRN.
Оборачивает канонический RRN-движок в стандартный контракт BaseReconciliationModule.
"""
import json
import math
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ValidationResult,
    ReconResult,
    ReconSummary,
)
from core.parsers import load_file_polars
from core.recon_engine import run_rrn_reconciliation
from utils.db_manager import get_epos_registry


class BankRrnModule(BaseReconciliationModule):
    """Модуль сверки банковского эквайринга (RRN, суммы, комиссии)."""

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="bank_rrn",
            name="Сверка эквайринга (RRN)",
            version="1.5.0",
            description="Потранзакционная сверка 1С / АБС с выписками банков по номерам RRN, суммам и комиссиям.",
            category="Эквайринг",
            icon="CreditCard",
            author="Отдел эквайринга и безналичных расчетов",
            status="active",
            workspace="bank_rrn",
            required_permissions=["bank_rrn.view", "bank_rrn.run"],
            available_permissions=["bank_rrn.view", "bank_rrn.run", "bank_rrn.export"],
            required_files=[
                {"key": "our_file", "label": "Реестр операций 1С / Базы данных (Excel/CSV)"},
                {"key": "bank_file", "label": "Банковская выписка эквайринга (Excel/CSV)"},
            ],
        )

    def validate_inputs(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ValidationResult:
        errors = []
        warnings = []

        if "our_file" not in files or not files["our_file"]:
            errors.append("Не загружен файл нашей базы (our_file)")
        if "bank_file" not in files or not files["bank_file"]:
            errors.append("Не загружен файл банковской выписки (bank_file)")

        required_params = [
            ("our_date_col", "Дата (наша сторона)"),
            ("our_rrn_col", "RRN (наша сторона)"),
            ("our_amt_col", "Сумма (наша сторона)"),
            ("bank_date_col", "Дата (банк)"),
            ("bank_rrn_col", "RRN (банк)"),
            ("bank_amt_col", "Сумма (банк)"),
        ]
        for key, label in required_params:
            if not str(params.get(key, "")).strip():
                errors.append(f"Не указана обязательная колонка: {label}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            columns_found={},
        )

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}

    @staticmethod
    def _records(value: Any) -> list[dict]:
        """Return JSON-safe records for FastAPI responses.

        Pandas/Polars frames may contain Timestamp, NaN and NumPy scalar values.
        Returning those objects directly can make response serialization fail
        after the reconciliation itself has already completed.
        """
        if value is None:
            return []
        if hasattr(value, "to_json"):
            try:
                return json.loads(value.to_json(orient="records", date_format="iso"))
            except (TypeError, ValueError, OverflowError):
                pass
        if hasattr(value, "to_dict"):
            records = value.to_dict(orient="records")
        elif isinstance(value, list):
            records = value
        else:
            return []

        def safe(value: Any) -> Any:
            if value is None or isinstance(value, (str, bool, int)):
                return value
            if isinstance(value, float):
                return None if not math.isfinite(value) else value
            if isinstance(value, dict):
                return {str(key): safe(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [safe(item) for item in value]
            if hasattr(value, "item"):
                try:
                    return safe(value.item())
                except (TypeError, ValueError):
                    pass
            if hasattr(value, "isoformat"):
                try:
                    return value.isoformat()
                except (TypeError, ValueError):
                    pass
            return str(value)

        return [safe(record) for record in records]

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        t_start = time.time()
        run_id = str(uuid.uuid4())[:8]

        rev_words_raw = params.get(
            "rev_words",
            "reversed, возврат, refund, отказ, ошибка",
        )
        rev_words = [word.strip() for word in str(rev_words_raw).split(",") if word.strip()]

        cfg = {
            "our_date": str(params.get("our_date_col", "Дата")).strip(),
            "our_rrn": str(params.get("our_rrn_col", "RRN")).strip(),
            "our_amt": str(params.get("our_amt_col", "")).strip() or None,
            "our_status": str(params.get("our_status_col", "")).strip() or None,
            "bank_date": str(params.get("bank_date_col", "Дата")).strip(),
            "bank_rrn": str(params.get("bank_rrn_col", "RRN")).strip(),
            "bank_amt": str(params.get("bank_amt_col", "")).strip() or None,
            "bank_status": str(params.get("bank_status_col", "")).strip() or None,
            "bank_tid": str(params.get("bank_tid_col", "")).strip() or None,
            "rev_words": rev_words,
            "our_rev": str(params.get("our_rev_action", "Минусовать сумму")),
            "bank_rev": str(params.get("bank_rev_action", "Удалить approved")),
            "dup_action": str(params.get("dup_action", "Ничего не делать (оставить все)")),
            "unbind_mismatches": self._as_bool(params.get("unbind_mismatches", False)),
            "tolerance": max(0.0, float(params.get("tolerance", 0.01))),
            "deduct_commission": self._as_bool(params.get("deduct_commission", False)),
            # The API response never exposes the full joined transaction table.
            # Keeping it in Polars avoids a very expensive to_pandas() on large files.
            "include_merged": False,
        }

        pl_our = load_file_polars(
            files["our_file"],
            params.get("our_filename", "our.xlsx"),
            sheet_name=params.get("our_sheet_name") or 0,
            header_row=params.get("our_header_row") or 1,
        )
        pl_bank = load_file_polars(
            files["bank_file"],
            params.get("bank_filename", "bank.xlsx"),
            sheet_name=params.get("bank_sheet_name") or 0,
            header_row=params.get("bank_header_row") or 1,
        )

        if pl_our is None or pl_bank is None:
            raise ValueError("Не удалось распознать формат переданных файлов.")

        result = run_rrn_reconciliation(
            pl_our_raw=pl_our,
            pl_bank_raw=pl_bank,
            cfg=cfg,
            epos_registry=get_epos_registry(),
        )

        summary_df = result["summary"]
        # core.recon_engine appends a display-only total row; totals for the
        # canonical API summary must be calculated from the actual date rows.
        base_summary_df = summary_df.iloc[:-1] if len(summary_df) else summary_df
        total_our = float(base_summary_df["Сумма_у_нас"].sum()) if not base_summary_df.empty else 0.0
        total_bank = float(base_summary_df["Сумма_в_банке"].sum()) if not base_summary_df.empty else 0.0
        total_records_our = int(base_summary_df["Кол_во_у_нас"].sum()) if not base_summary_df.empty else 0
        total_records_bank = int(base_summary_df["Кол_во_в_банке"].sum()) if not base_summary_df.empty else 0

        mismatch_count = int(result.get("mismatch_count", 0))
        only_our_count = len(result.get("only_our", []))
        only_bank_count = len(result.get("only_bank", []))
        matched_count = int(result.get("matched_count", 0))
        rrn_found_count = int(result.get("rrn_found_count", matched_count))
        amount_mismatch_count_before_unbind = int(
            result.get("amount_mismatch_count_before_unbind", mismatch_count)
        )
        only_our_count_before_unbind = int(
            result.get("only_our_count_before_unbind", only_our_count)
        )
        only_bank_count_before_unbind = int(
            result.get("only_bank_count_before_unbind", only_bank_count)
        )
        unbound_mismatch_count = int(result.get("unbound_mismatch_count", 0))
        exact_matched_count = max(
            0,
            rrn_found_count - amount_mismatch_count_before_unbind,
        )
        reconciliation_scope = (
            rrn_found_count
            + only_our_count_before_unbind
            + only_bank_count_before_unbind
        )
        diff_sum = round(total_bank - total_our, 2)
        match_percentage = round(
            (exact_matched_count / reconciliation_scope) * 100,
            2,
        ) if reconciliation_scope else 0.0
        data_quality = result.get("data_quality", {})
        data_quality_issue_count = sum(
            int(value or 0)
            for side in ("our", "bank")
            for value in (data_quality.get(side, {}) or {}).values()
        )
        duration_ms = round((time.time() - t_start) * 1000, 2)

        rich_result = {
            "only_our": self._records(result.get("only_our")),
            "only_bank": self._records(result.get("only_bank")),
            "amt_mismatches": self._records(result.get("amt_mismatches")),
            "dups_our": self._records(result.get("dups_our")),
            "dups_bank": self._records(result.get("dups_bank")),
            "dup_our_c": int(result.get("dup_our_c", 0)),
            "dup_bank_c": int(result.get("dup_bank_c", 0)),
            "dup_our_rrn_c": int(result.get("dup_our_rrn_c", 0)),
            "dup_bank_rrn_c": int(result.get("dup_bank_rrn_c", 0)),
            "dup_removed_our_c": int(result.get("dup_removed_our_c", 0)),
            "dup_removed_bank_c": int(result.get("dup_removed_bank_c", 0)),
            "matched_count": matched_count,
            "mismatch_count": mismatch_count,
            "rrn_found_count": rrn_found_count,
            "amount_mismatch_count_before_unbind": amount_mismatch_count_before_unbind,
            "only_our_count_before_unbind": only_our_count_before_unbind,
            "only_bank_count_before_unbind": only_bank_count_before_unbind,
            "unbound_mismatch_count": unbound_mismatch_count,
            "comm_only_diff_count": int(result.get("comm_only_diff_count", 0)),
            "amount_mismatch_net_delta": float(result.get("amount_mismatch_net_delta", 0.0)),
            "amount_mismatch_abs_delta": float(result.get("amount_mismatch_abs_delta", 0.0)),
            "amount_mismatch_positive_delta": float(result.get("amount_mismatch_positive_delta", 0.0)),
            "amount_mismatch_negative_delta": float(result.get("amount_mismatch_negative_delta", 0.0)),
            "amount_mismatch_invalid_delta_count": int(result.get("amount_mismatch_invalid_delta_count", 0)),
            "deduct_commission": bool(result.get("deduct_commission", False)),
            "terminal_summary": self._records(result.get("terminal_summary")),
            "total_commission": float(result.get("total_commission", 0.0)),
            "effective_commission_rate": float(result.get("effective_commission_rate", 0.0)),
            "data_quality": data_quality,
            "detected_months": result.get("detected_months", []),
            "dup_action": result.get("dup_action", cfg["dup_action"]),
        }

        return ReconResult(
            run_id=run_id,
            module_id="bank_rrn",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status=(
                "COMPLETED"
                if mismatch_count == 0
                and only_our_count == 0
                and only_bank_count == 0
                and data_quality_issue_count == 0
                else "WARNING"
            ),
            summary=ReconSummary(
                total_records_a=total_records_our,
                total_records_b=total_records_bank,
                total_sum_a=round(total_our, 2),
                total_sum_b=round(total_bank, 2),
                matched_count=matched_count,
                discrepancy_count=only_our_count + only_bank_count + mismatch_count,
                diff_sum=diff_sum,
                match_percentage=match_percentage,
                execution_time_ms=duration_ms,
            ),
            by_date=self._records(result.get("summary")),
            by_category=rich_result["terminal_summary"],
            discrepancies=rich_result["amt_mismatches"],
            custom_metrics={"rrn": rich_result},
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Module analytics are built from the server archive in the React workspace."""
        return {
            "module": "bank_rrn",
            "run_id": run_id,
            "metrics": {},
            "source": "archive",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        # Export is currently generated client-side from the visible result set.
        return b""


# Convention used by modules.registry auto-discovery.
MODULE_CLASS = BankRrnModule
