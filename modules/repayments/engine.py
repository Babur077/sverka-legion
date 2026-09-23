"""1C ↔ Meta repayment reconciliation based on the supplied accounting workflow."""

from __future__ import annotations

import csv
import io
import math
import re
import time
import uuid
from bisect import bisect_left, bisect_right
from decimal import Decimal, InvalidOperation
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Dict, Optional

import pandas as pd

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ReconResult,
    ReconSummary,
    ValidationResult,
)


SUM_TOLERANCE = 1.0
RECOGNITION_ZERO_EPSILON = 1e-9

SMART_MATCH_VERSION = "rules_v1"
SMART_MATCH_MIN_SCORE = 70
SMART_MATCH_MIN_MARGIN = 8
SMART_MATCH_MAX_AMOUNT_GAP_RATIO = 0.03

STATUS_ORDER = [
    "Правильно",
    "Не верная сумма",
    "Не верная дата",
    "Не верно",
    "Не опознано",
    "Нет в системе",
    "Нет в 1С",
]

ONE_C_REQUIRED_COLUMNS = ("Вх.номер", "Дата", "Сумма")
META_REQUIRED_COLUMNS = (
    "withdraw_unique_id",
    "bank_date",
    "bank_amount",
    "our_system_date",
    "our_system_amount_success",
    "contract_number",
)

META_PURPOSE_ALIASES = (
    "bank_purpose_of_payment",
    "payment_purpose",
    "purpose",
    "payment_details",
    "payment_description",
    "details",
)


def _read_source(
    content: bytes,
    filename: str,
    *,
    header_row: int,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """Read Excel/CSV with a user-selectable one-based header row."""
    lower = str(filename or "").lower()
    header_index = max(0, int(header_row) - 1)

    if lower.endswith(".csv"):
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1251")

        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=";,\t")
            separator = dialect.delimiter
        except csv.Error:
            separator = ";"

        return pd.read_csv(
            io.StringIO(text),
            sep=separator,
            header=header_index,
            dtype=object,
        )

    return pd.read_excel(
        io.BytesIO(content),
        sheet_name=sheet_name if sheet_name not in ("", None) else 0,
        header=header_index,
        dtype=object,
    )


def clean_payment_number(value: Any) -> Optional[str]:
    """Normalize payment numbers without converting strings through float.

    The original script used float(value), which can silently lose precision for
    long identifiers. We preserve the intended behavior (numeric integers become
    plain digit strings and leading zero padding is normalized) using Decimal.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return str(value).strip()

    text = str(value).replace("\u00a0", " ").strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None

    # Excel numeric cells often arrive as 12345.0. Decimal avoids float-based
    # precision loss for string identifiers while keeping the source semantics.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", text):
        try:
            number = Decimal(text)
            if number.is_finite() and number == number.to_integral_value():
                return format(number.to_integral_value(), "f")
        except (InvalidOperation, ValueError):
            pass

    return text


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True).dt.normalize()


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        try:
            return _safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return str(value)


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {str(key): _safe(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _find_optional_column(frame: pd.DataFrame, aliases: tuple[str, ...]) -> str | None:
    normalized = {
        str(column).replace("\u00a0", " ").strip().casefold(): str(column)
        for column in frame.columns
    }
    for alias in aliases:
        match = normalized.get(alias.replace("\u00a0", " ").strip().casefold())
        if match:
            return match
    return None


def _unique_text(values: pd.Series) -> str:
    items: list[str] = []
    for raw in values:
        try:
            if pd.isna(raw):
                continue
        except (TypeError, ValueError):
            pass
        text = str(raw).replace("\u00a0", " ").strip()
        if text and text not in items:
            items.append(text)
    return "\n".join(items)


def _header_row(params: Dict[str, Any], key: str) -> int:
    try:
        return max(1, min(200, int(params.get(key) or 1)))
    except (TypeError, ValueError):
        return 1


def _normalized_similarity(left: Any, right: Any) -> float:
    """Return a conservative 0..1 similarity for identifiers or payment text."""
    def normalize(value: Any) -> str:
        text = str(value or "").replace("\\u00a0", " ").casefold()
        text = re.sub(r"[^\\w\\s]+", " ", text, flags=re.UNICODE)
        return re.sub(r"\\s+", " ", text).strip()

    left_text = normalize(left)
    right_text = normalize(right)
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _nearest_date_gap_days(one_c_date: Any, bank_dates: list[Any]) -> int | None:
    if pd.isna(one_c_date) or not bank_dates:
        return None

    gaps: list[int] = []
    for raw in bank_dates:
        if pd.isna(raw):
            continue
        try:
            gaps.append(abs((pd.Timestamp(raw) - pd.Timestamp(one_c_date)).days))
        except (TypeError, ValueError):
            continue
    return min(gaps) if gaps else None


def _smart_match_score(
    one_c_payment: str,
    one_c_info: dict[str, Any],
    meta_payment: str,
    meta_info: dict[str, Any],
) -> tuple[int, str]:
    """Score one possible 1C ↔ Meta pair without changing reconciliation truth."""
    amount_1c = abs(float(one_c_info.get("amount") or 0))
    amount_meta = abs(float(meta_info.get("bank_amount") or 0))
    amount_gap = abs(amount_meta - amount_1c)
    amount_base = max(amount_1c, amount_meta, 1.0)
    amount_ratio = amount_gap / amount_base

    if amount_gap <= SUM_TOLERANCE:
        amount_points = 50
    elif amount_ratio <= 0.001:
        amount_points = 45
    elif amount_ratio <= 0.005:
        amount_points = 38
    elif amount_ratio <= 0.01:
        amount_points = 30
    elif amount_ratio <= SMART_MATCH_MAX_AMOUNT_GAP_RATIO:
        amount_points = 18
    else:
        amount_points = 0

    date_gap = _nearest_date_gap_days(
        one_c_info.get("date"),
        list(meta_info.get("bank_dates") or []),
    )
    if date_gap == 0:
        date_points = 25
    elif date_gap == 1:
        date_points = 22
    elif date_gap is not None and date_gap <= 3:
        date_points = 16
    elif date_gap is not None and date_gap <= 7:
        date_points = 8
    else:
        date_points = 0

    purpose_similarity = _normalized_similarity(
        one_c_info.get("payment_purpose"),
        meta_info.get("payment_purpose"),
    )
    purpose_points = round(purpose_similarity * 15) if purpose_similarity >= 0.45 else 0

    id_similarity = _normalized_similarity(one_c_payment, meta_payment)
    id_points = round(id_similarity * 10) if id_similarity >= 0.50 else 0

    score = int(min(100, amount_points + date_points + purpose_points + id_points))

    reasons: list[str] = []
    if amount_gap <= SUM_TOLERANCE:
        reasons.append("сумма совпадает")
    else:
        reasons.append(
            f"разница суммы {amount_gap:,.2f} ({amount_ratio * 100:.2f}%)"
            .replace(",", " ")
        )

    if date_gap == 0:
        reasons.append("дата совпадает")
    elif date_gap is not None:
        reasons.append(f"разница дат {date_gap} дн.")

    if purpose_similarity >= 0.60:
        reasons.append(f"назначение похоже на {round(purpose_similarity * 100)}%")
    if id_similarity >= 0.60:
        reasons.append(f"номер похож на {round(id_similarity * 100)}%")

    return score, "; ".join(reasons)


def _build_smart_matches(
    one_c_data: dict[str, dict[str, Any]],
    meta_data: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build conservative one-to-one suggestions for records missing on one side."""
    only_1c = sorted(set(one_c_data) - set(meta_data))
    only_meta = sorted(set(meta_data) - set(one_c_data))
    if not only_1c or not only_meta:
        return {}

    # Block candidates by amount first so the helper stays practical on large files.
    meta_by_amount = sorted(
        (
            abs(float(meta_data[payment].get("bank_amount") or 0)),
            payment,
        )
        for payment in only_meta
    )
    meta_amounts = [item[0] for item in meta_by_amount]

    pairs: list[dict[str, Any]] = []
    for one_c_payment in only_1c:
        one_c_info = one_c_data[one_c_payment]
        amount = abs(float(one_c_info.get("amount") or 0))
        if amount <= RECOGNITION_ZERO_EPSILON:
            continue

        window = max(SUM_TOLERANCE, amount * SMART_MATCH_MAX_AMOUNT_GAP_RATIO)
        start = bisect_left(meta_amounts, max(0.0, amount - window))
        end = bisect_right(meta_amounts, amount + window)

        for _, meta_payment in meta_by_amount[start:end]:
            score, reason = _smart_match_score(
                one_c_payment,
                one_c_info,
                meta_payment,
                meta_data[meta_payment],
            )
            if score >= SMART_MATCH_MIN_SCORE:
                pairs.append({
                    "one_c": one_c_payment,
                    "meta": meta_payment,
                    "score": score,
                    "reason": reason,
                })

    if not pairs:
        return {}

    by_one_c: dict[str, list[dict[str, Any]]] = {}
    by_meta: dict[str, list[dict[str, Any]]] = {}
    for pair in pairs:
        by_one_c.setdefault(pair["one_c"], []).append(pair)
        by_meta.setdefault(pair["meta"], []).append(pair)

    def clear_winner(items: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked = sorted(items, key=lambda item: (-int(item["score"]), item["one_c"], item["meta"]))
        if not ranked:
            return None
        if len(ranked) > 1 and int(ranked[0]["score"]) - int(ranked[1]["score"]) < SMART_MATCH_MIN_MARGIN:
            return None
        return ranked[0]

    best_one_c = {
        payment: clear_winner(items)
        for payment, items in by_one_c.items()
    }
    best_meta = {
        payment: clear_winner(items)
        for payment, items in by_meta.items()
    }

    suggestions: dict[str, dict[str, Any]] = {}
    for one_c_payment, pair in best_one_c.items():
        if not pair:
            continue
        meta_payment = str(pair["meta"])
        reverse = best_meta.get(meta_payment)
        if not reverse or str(reverse["one_c"]) != one_c_payment:
            continue

        score = int(pair["score"])
        reason = str(pair["reason"])
        suggestions[one_c_payment] = {
            "candidate": meta_payment,
            "score": score,
            "reason": reason,
            "side": "1C",
        }
        suggestions[meta_payment] = {
            "candidate": one_c_payment,
            "score": score,
            "reason": reason,
            "side": "Meta",
        }

    return suggestions


class RepaymentsModule(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="repayments",
            name="Сверка Погашений",
            version="1.1.0",
            description=(
                "Сверка 1С и Meta по номеру платежа: сумма банка, дата банка, "
                "сумма опознания и договоры."
            ),
            category="Бухгалтерия",
            icon="Receipt",
            author="ReconcileHub",
            status="active",
            workspace="repayments",
            required_permissions=["repayments.view", "repayments.run"],
            available_permissions=[
                "repayments.view",
                "repayments.run",
                "repayments.export",
            ],
            required_files=[
                {"key": "one_c_file", "label": "1C Погашение (Excel/CSV)"},
                {"key": "meta_file", "label": "Meta Погашение (Excel/CSV)"},
            ],
        )

    def validate_inputs(
        self,
        files: Dict[str, bytes],
        params: Dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        if not files.get("one_c_file"):
            errors.append("Не загружен файл 1C Погашение")
        if not files.get("meta_file"):
            errors.append("Не загружен файл Meta Погашение")
        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=[],
            columns_found={},
        )

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        started = time.time()
        run_id = str(uuid.uuid4())[:8]

        one_c_header = _header_row(params, "one_c_header_row")
        meta_header = _header_row(params, "meta_header_row")
        one_c_sheet = params.get("one_c_sheet_name") or 0
        meta_sheet = params.get("meta_sheet_name") or 0

        one_c = _read_source(
            files["one_c_file"],
            params.get("one_c_file_filename", "1C Погашение.xlsx"),
            header_row=one_c_header,
            sheet_name=one_c_sheet,
        )
        meta = _read_source(
            files["meta_file"],
            params.get("meta_file_filename", "Meta Погашение.xlsx"),
            header_row=meta_header,
            sheet_name=meta_sheet,
        )

        missing_one_c = [column for column in ONE_C_REQUIRED_COLUMNS if column not in one_c.columns]
        if missing_one_c:
            raise ValueError(
                "В файле 1C отсутствуют обязательные столбцы: "
                + ", ".join(missing_one_c)
            )

        missing_meta = [column for column in META_REQUIRED_COLUMNS if column not in meta.columns]
        if missing_meta:
            raise ValueError(
                "В файле Meta отсутствуют обязательные столбцы: "
                + ", ".join(missing_meta)
            )

        # Назначение платежа для этого модуля берём только из Meta.
        # В рабочем файле поле называется bank_purpose_of_payment.
        meta_purpose_column = _find_optional_column(meta, META_PURPOSE_ALIASES)

        one_c = one_c.rename(columns={
            "Вх.номер": "Номер платежа",
            "Дата": "Дата",
            "Сумма": "Сумма",
        }).copy()
        meta = meta.rename(columns={
            "withdraw_unique_id": "Номер платежа",
            "bank_date": "bank_date",
            "bank_amount": "bank_amount",
            "our_system_date": "our_system_date",
            "our_system_amount_success": "our_system_amount_success",
            "contract_number": "contract_number",
        }).copy()

        one_c["Номер платежа"] = one_c["Номер платежа"].apply(clean_payment_number)
        meta["Номер платежа"] = meta["Номер платежа"].apply(clean_payment_number)

        one_c["Дата"] = _dates(one_c["Дата"])
        meta["bank_date"] = _dates(meta["bank_date"])
        meta["our_system_date"] = _dates(meta["our_system_date"])

        one_c["Сумма"] = _number(one_c["Сумма"])
        meta["bank_amount"] = _number(meta["bank_amount"])
        meta["our_system_amount_success"] = _number(meta["our_system_amount_success"])

        one_c_source_rows = len(one_c)
        meta_source_rows = len(meta)

        # A missing payment number cannot be reconciled. The original script
        # attempted to skip None groups; filtering explicitly handles both None
        # and pandas NaN consistently.
        one_c_valid = one_c.loc[one_c["Номер платежа"].notna()].copy()
        meta_valid = meta.loc[meta["Номер платежа"].notna()].copy()

        meta_data: dict[str, dict[str, Any]] = {}
        for payment_number, group in meta_valid.groupby("Номер платежа", sort=False):
            bank_dates = group["bank_date"].dropna().tolist()
            system_dates = group["our_system_date"].dropna().tolist()

            contracts: list[str] = []
            for raw_contract in group["contract_number"]:
                if pd.isna(raw_contract):
                    continue
                contract = str(raw_contract).strip()
                if contract and contract not in contracts:
                    contracts.append(contract)

            meta_data[str(payment_number)] = {
                "bank_amount": float(group["bank_amount"].sum()),
                "recognition_amount": float(group["our_system_amount_success"].sum()),
                "bank_dates": bank_dates,
                "system_date": max(system_dates) if system_dates else pd.NaT,
                "contracts": ", ".join(contracts),
                "payment_purpose": (
                    _unique_text(group[meta_purpose_column])
                    if meta_purpose_column and meta_purpose_column in group.columns
                    else ""
                ),
            }

        one_c_data: dict[str, dict[str, Any]] = {}
        for payment_number, group in one_c_valid.groupby("Номер платежа", sort=False):
            dates = group["Дата"].dropna().tolist()
            one_c_data[str(payment_number)] = {
                "date": min(dates) if dates else pd.NaT,
                "amount": float(group["Сумма"].sum()),
                # В 1С назначения платежа нет; источник назначения — Meta.
                "payment_purpose": "",
            }

        numbers_1c = set(one_c_data)
        numbers_meta = set(meta_data)
        all_numbers = numbers_1c | numbers_meta
        smart_matches = _build_smart_matches(one_c_data, meta_data)

        result_rows: list[dict[str, Any]] = []
        for payment_number in all_numbers:
            in_1c = payment_number in one_c_data
            in_meta = payment_number in meta_data

            if in_1c:
                date_1c = one_c_data[payment_number]["date"]
                amount_1c = float(one_c_data[payment_number]["amount"])
                payment_purpose_1c = str(one_c_data[payment_number].get("payment_purpose") or "")
            else:
                date_1c = pd.NaT
                amount_1c = 0.0
                payment_purpose_1c = ""

            if in_meta:
                meta_info = meta_data[payment_number]
                bank_amount = float(meta_info["bank_amount"])
                recognition_amount = float(meta_info["recognition_amount"])
                bank_dates = list(meta_info["bank_dates"])
                system_date = meta_info["system_date"]
                contracts = str(meta_info["contracts"])
                payment_purpose_meta = str(meta_info.get("payment_purpose") or "")
            else:
                bank_amount = 0.0
                recognition_amount = 0.0
                bank_dates = []
                system_date = pd.NaT
                contracts = ""
                payment_purpose_meta = ""

            payment_purpose = payment_purpose_meta

            comparison_date = pd.NaT
            if bank_dates:
                if in_1c and pd.notna(date_1c):
                    matching_dates = [value for value in bank_dates if value == date_1c]
                    comparison_date = matching_dates[0] if matching_dates else max(bank_dates)
                else:
                    comparison_date = max(bank_dates)

            if not in_meta:
                comment = "Нет в системе"
            elif not in_1c:
                comment = "Нет в 1С"
            elif abs(recognition_amount) <= RECOGNITION_ZERO_EPSILON:
                comment = "Не опознано"
            else:
                amount_correct = abs(amount_1c - bank_amount) <= SUM_TOLERANCE
                date_correct = (
                    pd.notna(date_1c)
                    and pd.notna(comparison_date)
                    and date_1c == comparison_date
                )
                if amount_correct and date_correct:
                    comment = "Правильно"
                elif not amount_correct and date_correct:
                    comment = "Не верная сумма"
                elif amount_correct and not date_correct:
                    comment = "Не верная дата"
                else:
                    comment = "Не верно"

            smart_match = smart_matches.get(payment_number)

            result_rows.append({
                "Номер платежа": payment_number,
                "Дата": date_1c,
                "Сумма": round(amount_1c, 2),
                "Дата Meta": comparison_date,
                "Сумма Meta": round(bank_amount, 2),
                "Дата в системе": system_date,
                "Сумма опознание": round(recognition_amount, 2),
                "Номер договора опознание": contracts,
                "Назначение платежа": payment_purpose,
                "Комментарий": comment,
                "Δ суммы": round(bank_amount - amount_1c, 2),
                "Smart Match кандидат": (
                    str(smart_match["candidate"]) if smart_match else ""
                ),
                "Smart Match уверенность": (
                    int(smart_match["score"]) if smart_match else None
                ),
                "Smart Match причина": (
                    str(smart_match["reason"]) if smart_match else ""
                ),
            })

        result = pd.DataFrame(result_rows)
        if result.empty:
            result = pd.DataFrame(columns=[
                "Номер платежа",
                "Дата",
                "Сумма",
                "Дата Meta",
                "Сумма Meta",
                "Дата в системе",
                "Сумма опознание",
                "Номер договора опознание",
                "Назначение платежа",
                "Комментарий",
                "Δ суммы",
                "Smart Match кандидат",
                "Smart Match уверенность",
                "Smart Match причина",
            ])
        else:
            result = result.sort_values(
                by=["Дата", "Номер платежа"],
                na_position="last",
                kind="stable",
            ).reset_index(drop=True)

        for column in ("Дата", "Дата Meta", "Дата в системе"):
            result[column] = pd.to_datetime(
                result[column],
                errors="coerce",
            ).dt.strftime("%d.%m.%Y")

        status_counts = {
            status: int((result["Комментарий"] == status).sum())
            for status in STATUS_ORDER
            if int((result["Комментарий"] == status).sum()) > 0
        }

        matched_count = int((result["Комментарий"] == "Правильно").sum())
        total_unique = len(result)
        discrepancy_count = total_unique - matched_count
        total_1c = round(float(sum(item["amount"] for item in one_c_data.values())), 2)
        total_meta = round(float(sum(item["bank_amount"] for item in meta_data.values())), 2)
        diff_sum = round(total_meta - total_1c, 2)
        match_percentage = (
            round(matched_count / total_unique * 100, 2)
            if total_unique
            else 0.0
        )

        discrepancies = result.loc[result["Комментарий"] != "Правильно"].copy()
        duration_ms = round((time.time() - started) * 1000, 2)

        return ReconResult(
            run_id=run_id,
            module_id="repayments",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="COMPLETED" if discrepancy_count == 0 else "WARNING",
            summary=ReconSummary(
                total_records_a=one_c_source_rows,
                total_records_b=meta_source_rows,
                total_sum_a=total_1c,
                total_sum_b=total_meta,
                matched_count=matched_count,
                discrepancy_count=discrepancy_count,
                diff_sum=diff_sum,
                match_percentage=match_percentage,
                execution_time_ms=duration_ms,
            ),
            by_category=[
                {"status": status, "count": count}
                for status, count in status_counts.items()
            ],
            discrepancies=_records(discrepancies),
            custom_metrics={
                "repayments": {
                    "sum_tolerance": SUM_TOLERANCE,
                    "status_counts": status_counts,
                    "rows": _records(result),
                    "source_1c_rows": one_c_source_rows,
                    "source_meta_rows": meta_source_rows,
                    "unique_1c": len(numbers_1c),
                    "unique_meta": len(numbers_meta),
                    "unique_total": total_unique,
                    "smart_match_version": SMART_MATCH_VERSION,
                    "smart_match_pair_count": len(smart_matches) // 2,
                    "smart_match_row_count": len(smart_matches),
                    "source_files": [
                        params.get("one_c_file_filename", "1C Погашение.xlsx"),
                        params.get("meta_file_filename", "Meta Погашение.xlsx"),
                    ],
                    "header_rows": {
                        "one_c": one_c_header,
                        "meta": meta_header,
                    },
                    "payment_purpose_source": (
                        f"Meta:{meta_purpose_column}"
                        if meta_purpose_column
                        else None
                    ),
                }
            },
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "module": "repayments",
            "run_id": run_id,
            "metrics": {},
            "source": "archive",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""


MODULE_CLASS = RepaymentsModule
