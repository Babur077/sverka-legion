"""Test Vorona partner-settlement reconciliation."""

from __future__ import annotations

import io
import math
import re
import time
import uuid
from collections import Counter
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ReconResult,
    ReconSummary,
    ValidationResult,
)

MONTHS = {
    "Yanvar": 1,
    "Fevral": 2,
    "Mart": 3,
    "Aprel": 4,
    "May": 5,
    "Iyun": 6,
    "Iyul": 7,
    "Avgust": 8,
    "Sentabr": 9,
    "Oktyabr": 10,
    "Noyabr": 11,
    "Dekabr": 12,
}

DIFF_TOLERANCE = 1.0


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


def _clean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [
        str(column).replace("\u00a0", " ").strip()
        for column in result.columns
    ]
    return result


def _identifier(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = str(value).replace("\u00a0", " ").strip().strip('"').strip("'")
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]

    digits = re.sub(r"\D", "", text)
    return digits or text


def _vid(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).replace("\u00a0", " ").strip().upper()


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).replace("\u00a0", " ").strip().strip('"').strip()


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass

    if isinstance(value, (int, float)):
        return float(value)

    text = (
        str(value)
        .replace("\u00a0", "")
        .replace(" ", "")
        .replace(",", ".")
        .strip()
    )
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def _first_present(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name not in row.index:
            continue
        value = row.get(name)
        if _text(value):
            return value
    return None


def _monthly_frames(content: bytes) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=object)
    result: dict[str, pd.DataFrame] = {}
    for sheet_name, frame in sheets.items():
        if sheet_name not in MONTHS:
            continue
        frame = _clean_columns(frame).dropna(how="all").copy()
        result[sheet_name] = frame
    return result


def _sum_by_vid(rows: list[dict[str, Any]], field: str = "amount") -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in rows:
        vid = str(row.get("vid") or "")
        if not vid:
            continue
        totals[vid] = totals.get(vid, 0.0) + _number(row.get(field))
    return totals


class TestVoronaModule(BaseReconciliationModule):
    def __init__(self) -> None:
        self._last_result: ReconResult | None = None

    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="test_vorona",
            name="Тестовая ворона",
            version="0.2.0",
            description=(
                "Контроль взаиморасчётов с партнёрами: продажи, комиссии, "
                "банковские оплаты, фактуры, начальное сальдо и данные 1С."
            ),
            category="Бухгалтерия",
            icon="Bird",
            author="ReconcileHub",
            status="active",
            workspace="test_vorona",
            required_permissions=["test_vorona.view", "test_vorona.run"],
            available_permissions=[
                "test_vorona.view",
                "test_vorona.run",
                "test_vorona.export",
            ],
            required_files=[
                {"key": "baza_file", "label": "VBAZA.xlsx — продажи и комиссия"},
                {"key": "bank_file", "label": "VBANK.xlsx — оплаты"},
                {"key": "faktura_file", "label": "VFAKTURA.xlsx — фактуры"},
                {"key": "vipp_file", "label": "VIPP.xlsx — справочник партнёров"},
                {"key": "vorona_file", "label": "VORONA 2026.xlsx — сальдо и 1С"},
            ],
        )

    def validate_inputs(
        self,
        files: Dict[str, bytes],
        params: Dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        labels = {
            "baza_file": "VBAZA",
            "bank_file": "VBANK",
            "faktura_file": "VFAKTURA",
            "vipp_file": "VIPP",
            "vorona_file": "VORONA",
        }
        for key, label in labels.items():
            if not files.get(key):
                errors.append(f"Не загружен файл {label}")

        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=[],
            columns_found={},
        )

    def _normalize_monthly(
        self,
        content: bytes,
        *,
        id_map: dict[str, str],
        inn_columns: tuple[str, ...],
        partner_columns: tuple[str, ...],
        amount_column: str,
        extra_columns: tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for sheet_name, frame in _monthly_frames(content).items():
            for _, raw in frame.iterrows():
                inn = _identifier(_first_present(raw, *inn_columns))
                vid = _vid(raw.get("VID")) or id_map.get(inn, "")
                partner = _text(_first_present(raw, *partner_columns))
                amount = _number(raw.get(amount_column))
                raw_date = raw.get("Data")
                date = _safe(raw_date)

                if not any([inn, vid, partner, amount, date]):
                    continue

                item: dict[str, Any] = {
                    "month": sheet_name,
                    "month_num": MONTHS[sheet_name],
                    "date": date,
                    "inn": inn,
                    "vid": vid,
                    "partner": partner,
                    "amount": amount,
                }
                for column in extra_columns:
                    item[column] = _text(raw.get(column))
                rows.append(item)

        return rows

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        started = time.perf_counter()
        run_id = str(uuid.uuid4())[:8]

        try:
            year = int(params.get("year") or datetime.now().year)
        except (TypeError, ValueError):
            year = datetime.now().year

        # Partner dictionary: INN/PINFL -> Vorona Code.
        vipp_sheets = pd.read_excel(
            io.BytesIO(files["vipp_file"]),
            sheet_name=None,
            dtype=object,
        )
        if "INNvsPINFL" not in vipp_sheets:
            raise ValueError("В VIPP отсутствует лист INNvsPINFL")

        partners = _clean_columns(vipp_sheets["INNvsPINFL"]).dropna(how="all").copy()
        required_partner_columns = {"Partner", "INNvsPINFL", "Vorona Code"}
        missing_partner_columns = sorted(required_partner_columns - set(partners.columns))
        if missing_partner_columns:
            raise ValueError(
                "В VIPP отсутствуют колонки: " + ", ".join(missing_partner_columns)
            )

        partners["VID"] = partners["Vorona Code"].map(_vid)
        partners["INN"] = partners["INNvsPINFL"].map(_identifier)
        partners["PartnerName"] = partners["Partner"].map(_text)
        partners = partners.loc[partners["VID"] != ""].copy()

        id_to_vid = {
            row.INN: row.VID
            for row in partners.itertuples()
            if row.INN
        }
        vid_to_partner = {
            row.VID: row.PartnerName
            for row in partners.itertuples()
            if row.PartnerName
        }
        vid_to_inn = {
            row.VID: row.INN
            for row in partners.itertuples()
            if row.INN
        }

        sales = self._normalize_monthly(
            files["baza_file"],
            id_map=id_to_vid,
            inn_columns=("INN/PINFL", "INN"),
            partner_columns=("Merchant", "Partner"),
            amount_column="Sales",
            extra_columns=("Status", "Service"),
        )

        # Commission is a second amount from the same VBAZA rows.
        sales_frames = _monthly_frames(files["baza_file"])
        sales_index = 0
        for _, frame in sales_frames.items():
            for _, raw in frame.iterrows():
                inn = _identifier(_first_present(raw, "INN/PINFL", "INN"))
                vid = _vid(raw.get("VID")) or id_to_vid.get(inn, "")
                partner = _text(_first_present(raw, "Merchant", "Partner"))
                amount = _number(raw.get("Sales"))
                date = _safe(raw.get("Data"))
                if not any([inn, vid, partner, amount, date]):
                    continue
                if sales_index < len(sales):
                    sales[sales_index]["commission"] = _number(raw.get("Komissiya"))
                sales_index += 1

        bank = self._normalize_monthly(
            files["bank_file"],
            id_map=id_to_vid,
            inn_columns=("INN", "INN/PINFL"),
            partner_columns=("Partner", " "),
            amount_column="Summ",
        )
        faktura = self._normalize_monthly(
            files["faktura_file"],
            id_map=id_to_vid,
            inn_columns=("INN/PINFL", "INN"),
            partner_columns=("Partner", "Merchant"),
            amount_column="Summ",
        )

        # VORONA workbook remains a source only for opening balance and 1C in MVP.
        vorona_sheets = pd.read_excel(
            io.BytesIO(files["vorona_file"]),
            sheet_name=None,
            dtype=object,
        )
        if "Saldo 2025" not in vorona_sheets:
            raise ValueError("В VORONA отсутствует лист Saldo 2025")
        if "1C" not in vorona_sheets:
            raise ValueError("В VORONA отсутствует лист 1C")

        active_vids: set[str] = set()
        metadata: dict[str, dict[str, str]] = {}

        def register_meta(vid: str, partner: str = "", inn: str = "") -> None:
            if not vid:
                return
            active_vids.add(vid)
            item = metadata.setdefault(vid, {})
            if partner and not item.get("partner"):
                item["partner"] = partner
            if inn and not item.get("inn"):
                item["inn"] = inn

        for source in (sales, bank, faktura):
            for row in source:
                register_meta(
                    str(row.get("vid") or ""),
                    str(row.get("partner") or ""),
                    str(row.get("inn") or ""),
                )

        opening_frame = _clean_columns(vorona_sheets["Saldo 2025"]).dropna(how="all")
        opening_rows: list[dict[str, Any]] = []
        opening_by_vid: dict[str, float] = {}
        for _, raw in opening_frame.iterrows():
            vid = _vid(raw.get("VID"))
            if not vid:
                continue
            partner = _text(raw.get("Partner"))
            inn = _identifier(raw.get("INN"))
            amount = _number(raw.get("Saldo 2024"))
            register_meta(vid, partner, inn)
            opening_by_vid[vid] = opening_by_vid.get(vid, 0.0) + amount
            opening_rows.append({
                "vid": vid,
                "partner": partner,
                "inn": inn,
                "amount": amount,
            })

        # 1C contains two accounting sides:
        # A:D = 4890/4010, F:I = 6990/6310.
        one_c_raw = vorona_sheets["1C"].dropna(how="all").copy()
        one_c_rows: list[dict[str, Any]] = []
        one_c_left: dict[str, float] = {}
        one_c_right: dict[str, float] = {}

        for _, raw in one_c_raw.iterrows():
            values = list(raw.values)

            left_vid = _vid(values[0] if len(values) > 0 else None)
            left_partner = _text(values[1] if len(values) > 1 else None)
            left_inn = _identifier(values[2] if len(values) > 2 else None)
            left_sum = _number(values[3] if len(values) > 3 else None)
            if left_vid:
                register_meta(left_vid, left_partner, left_inn)
                one_c_left[left_vid] = one_c_left.get(left_vid, 0.0) + left_sum
                one_c_rows.append({
                    "side": "4890 / 4010",
                    "vid": left_vid,
                    "partner": left_partner,
                    "inn": left_inn,
                    "amount": left_sum,
                })

            right_vid = _vid(values[5] if len(values) > 5 else None)
            right_partner = _text(values[6] if len(values) > 6 else None)
            right_inn = _identifier(values[7] if len(values) > 7 else None)
            right_sum = _number(values[8] if len(values) > 8 else None)
            if right_vid:
                register_meta(right_vid, right_partner, right_inn)
                one_c_right[right_vid] = one_c_right.get(right_vid, 0.0) + right_sum
                one_c_rows.append({
                    "side": "6990 / 6310",
                    "vid": right_vid,
                    "partner": right_partner,
                    "inn": right_inn,
                    "amount": right_sum,
                })

        # Excel logic:
        # Payment = VBAZA.Sales where Status != REVERTED
        # Bank = VBANK.Summ
        # Faktura = VFAKTURA.Summ
        # Komissiya = VBAZA.Komissiya
        # Saldo = Payment - Bank - Faktura + opening balance
        # Difference = Faktura - Komissiya
        # 1C = (6990/6310) - (4890/4010)
        # Difference 1C = Saldo - 1C
        payment_by_vid: dict[str, float] = {}
        commission_by_vid: dict[str, float] = {}
        for row in sales:
            vid = str(row.get("vid") or "")
            if not vid:
                continue
            if str(row.get("Status") or "").strip().upper() != "REVERTED":
                payment_by_vid[vid] = payment_by_vid.get(vid, 0.0) + _number(row.get("amount"))
            commission_by_vid[vid] = (
                commission_by_vid.get(vid, 0.0)
                + _number(row.get("commission"))
            )

        bank_by_vid = _sum_by_vid(bank)
        faktura_by_vid = _sum_by_vid(faktura)

        rows: list[dict[str, Any]] = []
        for vid in sorted(
            active_vids,
            key=lambda value: (
                int(re.sub(r"\D", "", value) or 10**9),
                value,
            ),
        ):
            payment = payment_by_vid.get(vid, 0.0)
            bank_total = bank_by_vid.get(vid, 0.0)
            faktura_total = faktura_by_vid.get(vid, 0.0)
            commission = commission_by_vid.get(vid, 0.0)
            opening_balance = opening_by_vid.get(vid, 0.0)

            saldo = payment - bank_total - faktura_total + opening_balance
            one_c = one_c_right.get(vid, 0.0) - one_c_left.get(vid, 0.0)
            difference = faktura_total - commission
            difference_1c = saldo - one_c

            has_difference = abs(difference) > DIFF_TOLERANCE
            has_difference_1c = abs(difference_1c) > DIFF_TOLERANCE

            if has_difference and has_difference_1c:
                status = "Есть оба расхождения"
            elif has_difference:
                status = "Есть Difference"
            elif has_difference_1c:
                status = "Есть Difference 1C"
            else:
                status = "Без расхождений"

            fallback = metadata.get(vid, {})
            rows.append({
                "partner": (
                    vid_to_partner.get(vid)
                    or fallback.get("partner")
                    or "—"
                ),
                "inn": vid_to_inn.get(vid) or fallback.get("inn") or "",
                "vid": vid,
                "payment": payment,
                "bank": bank_total,
                "faktura": faktura_total,
                "komissiya": commission,
                "opening_balance": opening_balance,
                "saldo": saldo,
                "one_c": one_c,
                "difference": difference,
                "difference_1c": difference_1c,
                "status": status,
            })

        status_counts = Counter(row["status"] for row in rows)
        matched_count = sum(
            1 for row in rows if row["status"] == "Без расхождений"
        )
        discrepancy_count = len(rows) - matched_count

        total_fields = (
            "payment",
            "bank",
            "faktura",
            "komissiya",
            "opening_balance",
            "saldo",
            "one_c",
            "difference",
            "difference_1c",
        )
        totals = {
            field: sum(float(row[field]) for row in rows)
            for field in total_fields
        }

        datasets = {
            "sales": sales,
            "bank": bank,
            "faktura": faktura,
            "partners": [
                {
                    "vid": row.VID,
                    "partner": row.PartnerName,
                    "inn": row.INN,
                }
                for row in partners.itertuples()
            ],
            "opening_balances": opening_rows,
            "one_c": one_c_rows,
        }

        result = ReconResult(
            run_id=run_id,
            module_id="test_vorona",
            timestamp=datetime.now().isoformat(),
            status="COMPLETED" if discrepancy_count == 0 else "WARNING",
            summary=ReconSummary(
                total_records_a=len(rows),
                total_records_b=(
                    len(sales) + len(bank) + len(faktura)
                    + len(opening_rows) + len(one_c_rows)
                ),
                total_sum_a=totals["saldo"],
                total_sum_b=totals["one_c"],
                matched_count=matched_count,
                discrepancy_count=discrepancy_count,
                diff_sum=totals["difference_1c"],
                match_percentage=(
                    round(matched_count / len(rows) * 100, 2)
                    if rows
                    else 100.0
                ),
                execution_time_ms=round(
                    (time.perf_counter() - started) * 1000,
                    2,
                ),
            ),
            by_category=[
                {"status": status, "count": count}
                for status, count in status_counts.items()
            ],
            discrepancies=[
                row for row in rows
                if row["status"] != "Без расхождений"
            ],
            custom_metrics={
                "test_vorona": {
                    "year": year,
                    "tolerance": DIFF_TOLERANCE,
                    "rows": rows,
                    "status_counts": dict(status_counts),
                    "totals": totals,
                    "datasets": datasets,
                    "source_counts": {
                        key: len(value)
                        for key, value in datasets.items()
                    },
                }
            },
        )
        self._last_result = result
        return result

    def run_from_records(
        self,
        datasets: Dict[str, list[dict[str, Any]]],
        *,
        year: int,
        through_month: int | None = None,
    ) -> ReconResult:
        """Run reconciliation from the persistent Test Vorona database."""
        started = time.perf_counter()
        run_id = str(uuid.uuid4())[:8]

        sales = list(datasets.get("sales") or [])
        bank = list(datasets.get("bank") or [])
        faktura = list(datasets.get("faktura") or [])
        partners = list(datasets.get("partners") or [])
        opening_rows = list(datasets.get("opening_balances") or [])
        one_c_rows = list(datasets.get("one_c") or [])

        vid_to_partner: dict[str, str] = {}
        vid_to_inn: dict[str, str] = {}
        active_vids: set[str] = set()
        metadata: dict[str, dict[str, str]] = {}

        def register_meta(vid: str, partner: str = "", inn: str = "") -> None:
            normalized_vid = _vid(vid)
            if not normalized_vid:
                return
            active_vids.add(normalized_vid)
            item = metadata.setdefault(normalized_vid, {})
            partner_text = _text(partner)
            inn_text = _identifier(inn)
            if partner_text and not item.get("partner"):
                item["partner"] = partner_text
            if inn_text and not item.get("inn"):
                item["inn"] = inn_text

        for partner_row in partners:
            vid = _vid(partner_row.get("vid"))
            if not vid:
                continue
            partner_name = _text(partner_row.get("partner"))
            inn = _identifier(partner_row.get("inn"))
            if partner_name:
                vid_to_partner[vid] = partner_name
            if inn:
                vid_to_inn[vid] = inn

        for source in (sales, bank, faktura, opening_rows, one_c_rows):
            for row in source:
                register_meta(
                    str(row.get("vid") or ""),
                    str(row.get("partner") or ""),
                    str(row.get("inn") or ""),
                )

        opening_by_vid: dict[str, float] = {}
        for row in opening_rows:
            vid = _vid(row.get("vid"))
            if not vid:
                continue
            opening_by_vid[vid] = (
                opening_by_vid.get(vid, 0.0)
                + _number(row.get("amount"))
            )

        one_c_left: dict[str, float] = {}
        one_c_right: dict[str, float] = {}
        for row in one_c_rows:
            vid = _vid(row.get("vid"))
            if not vid:
                continue
            amount = _number(row.get("amount"))
            side = _text(row.get("side"))
            if side == "4890 / 4010":
                one_c_left[vid] = one_c_left.get(vid, 0.0) + amount
            elif side == "6990 / 6310":
                one_c_right[vid] = one_c_right.get(vid, 0.0) + amount

        payment_by_vid: dict[str, float] = {}
        commission_by_vid: dict[str, float] = {}
        for row in sales:
            vid = _vid(row.get("vid"))
            if not vid:
                continue
            if str(row.get("Status") or row.get("status") or "").strip().upper() != "REVERTED":
                payment_by_vid[vid] = (
                    payment_by_vid.get(vid, 0.0)
                    + _number(row.get("amount"))
                )
            commission_by_vid[vid] = (
                commission_by_vid.get(vid, 0.0)
                + _number(row.get("commission"))
            )

        bank_by_vid = _sum_by_vid(bank)
        faktura_by_vid = _sum_by_vid(faktura)

        rows: list[dict[str, Any]] = []
        for vid in sorted(
            active_vids,
            key=lambda value: (
                int(re.sub(r"\D", "", value) or 10**9),
                value,
            ),
        ):
            payment = payment_by_vid.get(vid, 0.0)
            bank_total = bank_by_vid.get(vid, 0.0)
            faktura_total = faktura_by_vid.get(vid, 0.0)
            commission = commission_by_vid.get(vid, 0.0)
            opening_balance = opening_by_vid.get(vid, 0.0)

            saldo = payment - bank_total - faktura_total + opening_balance
            one_c = one_c_right.get(vid, 0.0) - one_c_left.get(vid, 0.0)
            difference = faktura_total - commission
            difference_1c = saldo - one_c

            has_difference = abs(difference) > DIFF_TOLERANCE
            has_difference_1c = abs(difference_1c) > DIFF_TOLERANCE

            if has_difference and has_difference_1c:
                status = "Есть оба расхождения"
            elif has_difference:
                status = "Есть Difference"
            elif has_difference_1c:
                status = "Есть Difference 1C"
            else:
                status = "Без расхождений"

            fallback = metadata.get(vid, {})
            rows.append({
                "partner": (
                    vid_to_partner.get(vid)
                    or fallback.get("partner")
                    or "—"
                ),
                "inn": vid_to_inn.get(vid) or fallback.get("inn") or "",
                "vid": vid,
                "payment": payment,
                "bank": bank_total,
                "faktura": faktura_total,
                "komissiya": commission,
                "opening_balance": opening_balance,
                "saldo": saldo,
                "one_c": one_c,
                "difference": difference,
                "difference_1c": difference_1c,
                "status": status,
            })

        status_counts = Counter(row["status"] for row in rows)
        matched_count = sum(
            1 for row in rows if row["status"] == "Без расхождений"
        )
        discrepancy_count = len(rows) - matched_count

        total_fields = (
            "payment",
            "bank",
            "faktura",
            "komissiya",
            "opening_balance",
            "saldo",
            "one_c",
            "difference",
            "difference_1c",
        )
        totals = {
            field: sum(float(row[field]) for row in rows)
            for field in total_fields
        }

        result = ReconResult(
            run_id=run_id,
            module_id="test_vorona",
            timestamp=datetime.now().isoformat(),
            status="COMPLETED" if discrepancy_count == 0 else "WARNING",
            summary=ReconSummary(
                total_records_a=len(rows),
                total_records_b=(
                    len(sales) + len(bank) + len(faktura)
                    + len(opening_rows) + len(one_c_rows)
                ),
                total_sum_a=totals["saldo"],
                total_sum_b=totals["one_c"],
                matched_count=matched_count,
                discrepancy_count=discrepancy_count,
                diff_sum=totals["difference_1c"],
                match_percentage=(
                    round(matched_count / len(rows) * 100, 2)
                    if rows
                    else 100.0
                ),
                execution_time_ms=round(
                    (time.perf_counter() - started) * 1000,
                    2,
                ),
            ),
            by_category=[
                {"status": status, "count": count}
                for status, count in status_counts.items()
            ],
            discrepancies=[
                row for row in rows
                if row["status"] != "Без расхождений"
            ],
            custom_metrics={
                "test_vorona": {
                    "year": int(year),
                    "through_month": through_month,
                    "tolerance": DIFF_TOLERANCE,
                    "storage_mode": "persistent",
                    "rows": rows,
                    "status_counts": dict(status_counts),
                    "totals": totals,
                    "datasets": {
                        "sales": sales,
                        "bank": bank,
                        "faktura": faktura,
                        "partners": partners,
                        "opening_balances": opening_rows,
                        "one_c": one_c_rows,
                    },
                    "source_counts": {
                        "sales": len(sales),
                        "bank": len(bank),
                        "faktura": len(faktura),
                        "partners": len(partners),
                        "opening_balances": len(opening_rows),
                        "one_c": len(one_c_rows),
                    },
                }
            },
        )
        self._last_result = result
        return result

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        if not self._last_result:
            return {
                "module": "test_vorona",
                "message": "Сверка ещё не запускалась.",
            }
        if run_id and self._last_result.run_id != run_id:
            return {
                "module": "test_vorona",
                "message": f"Run {run_id} не находится в памяти процесса.",
            }
        return self._last_result.custom_metrics.get("test_vorona", {})

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        if format.lower() != "xlsx":
            raise ValueError("Тестовая ворона пока поддерживает только XLSX экспорт")
        if not self._last_result or self._last_result.run_id != run_id:
            raise ValueError("Результат запуска не найден")

        rows = (
            self._last_result.custom_metrics
            .get("test_vorona", {})
            .get("rows", [])
        )
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(
                writer,
                sheet_name="Сверка",
                index=False,
            )
            pd.DataFrame(
                self._last_result.discrepancies
            ).to_excel(
                writer,
                sheet_name="Расхождения",
                index=False,
            )
        return buffer.getvalue()


MODULE_CLASS = TestVoronaModule
