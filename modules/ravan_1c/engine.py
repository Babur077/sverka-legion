"""Ravan ↔ 1C reconciliation produced from Sayfulloh Abdusalomov's workflow."""

from __future__ import annotations

import csv
import io
import math
import re
import time
import uuid
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


LEGAL_FORMS = (
    "mchj",
    "mchs",
    "llc",
    "ooo",
    "ооо",
    "xk",
    "xs",
    "ok",
    "yatt",
    "aj",
    "qk",
    "sp",
    "ltd",
)

LEGAL_PHRASES = (
    "xususiy korxona",
    "xususiy korxonasi",
    "хусусий корхона",
    "хусусий корхонаси",
    "masuliyati cheklangan jamiyat",
    "masuliyati cheklangan jamiyati",
    "mas'uliyati cheklangan jamiyat",
    "mas'uliyati cheklangan jamiyati",
    "масъулияти чекланган жамият",
    "масъулияти чекланган жамияти",
    "частное предприятие",
)

FUZZY_NAME_THRESHOLD = 0.88


def clean_company_name(value: Any) -> str:
    """Normalize legal names before exact/fuzzy comparison."""
    name = str(value)
    name = name.lower()
    for quote in ('"', "'", "“", "”", "«", "»", "`"):
        name = name.replace(quote, "")

    for phrase in LEGAL_PHRASES:
        name = re.sub(rf"\b{re.escape(phrase)}\b", "", name)

    for form in LEGAL_FORMS:
        name = re.sub(rf"\b{re.escape(form)}\b", "", name)

    name = re.sub(r"[^a-zа-яё0-9]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def company_name_similarity(left: Any, right: Any) -> float:
    """Return conservative name similarity in [0, 1]."""
    a = clean_company_name(left)
    b = clean_company_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    direct = SequenceMatcher(None, a, b).ratio()
    token_sorted = SequenceMatcher(
        None,
        " ".join(sorted(a.split())),
        " ".join(sorted(b.split())),
    ).ratio()
    return max(direct, token_sorted)


def _apply_fuzzy_name_matches(result: pd.DataFrame) -> pd.DataFrame:
    """Pair only mutually-best unmatched rows above a high similarity threshold."""
    if result.empty:
        return result

    result = result.copy()
    both_present = result["Partner_Ravan"].notna() & result["Partner_C"].notna()
    result["Match_Type"] = "unmatched"
    result.loc[both_present, "Match_Type"] = "exact"
    result["Name_Similarity"] = None
    result.loc[both_present, "Name_Similarity"] = 100.0
    result["Needs_Review"] = False
    result["Match_Confirmed"] = False

    ravan_only = result.index[
        result["Partner_Ravan"].notna() & result["Partner_C"].isna()
    ].tolist()
    c_only = result.index[
        result["Partner_Ravan"].isna() & result["Partner_C"].notna()
    ].tolist()
    if not ravan_only or not c_only:
        return result

    candidates: list[tuple[float, int, int]] = []
    for r_idx in ravan_only:
        r_key = result.at[r_idx, "Company_Key"]
        if len(str(r_key or "")) < 5:
            continue
        for c_idx in c_only:
            c_key = result.at[c_idx, "Company_Key"]
            if len(str(c_key or "")) < 5:
                continue
            score = company_name_similarity(r_key, c_key)
            if score >= FUZZY_NAME_THRESHOLD:
                candidates.append((score, r_idx, c_idx))

    if not candidates:
        return result

    best_for_ravan: dict[int, tuple[float, int]] = {}
    best_for_c: dict[int, tuple[float, int]] = {}
    for score, r_idx, c_idx in candidates:
        if r_idx not in best_for_ravan or score > best_for_ravan[r_idx][0]:
            best_for_ravan[r_idx] = (score, c_idx)
        if c_idx not in best_for_c or score > best_for_c[c_idx][0]:
            best_for_c[c_idx] = (score, r_idx)

    paired_c: set[int] = set()
    for r_idx, (score, c_idx) in best_for_ravan.items():
        reverse = best_for_c.get(c_idx)
        if not reverse or reverse[1] != r_idx or c_idx in paired_c:
            continue

        for column in ("Partner_C", "Kolvo_C", "Summ_C"):
            result.at[r_idx, column] = result.at[c_idx, column]
        result.at[r_idx, "Match_Type"] = "fuzzy"
        result.at[r_idx, "Name_Similarity"] = round(score * 100, 1)
        result.at[r_idx, "Needs_Review"] = True
        result.at[r_idx, "Match_Confirmed"] = False
        paired_c.add(c_idx)

    if paired_c:
        result = result.drop(index=list(paired_c))

    return result.reset_index(drop=True)


def _read_source(
    content: bytes,
    filename: str,
    *,
    header: int | None,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    lower = str(filename or "").lower()
    if lower.endswith(".csv"):
        # A wrong separator can parse successfully as one column. Detect it
        # explicitly, including quoted delimiters, before reading the source.
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("cp1251")
        try:
            dialect = csv.Sniffer().sniff(text[:65536], delimiters=";,\t")
        except csv.Error as exc:
            raise ValueError("Не удалось определить разделитель CSV: ожидается ; , или табуляция") from exc
        return pd.read_csv(io.StringIO(text), sep=dialect.delimiter, header=header, dtype=object)

    return pd.read_excel(
        io.BytesIO(content),
        sheet_name=sheet_name if sheet_name not in ("", None) else 0,
        header=header,
        dtype=object,
    )


def _number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if pd.isna(value):
        return None
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
        {str(key): _safe(value) for key, value in record.items()}
        for record in frame.to_dict(orient="records")
    ]


class Ravan1CModule(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="ravan_1c",
            name="Сверка 2910",
            version="1.0.1",
            description=(
                "Сверка 2910: Ravan с 1C по очищенному названию контрагента, количеству "
                "и скорректированной сумме с учетом NDS."
            ),
            category="Бухгалтерия",
            icon="Building2",
            author="Sayfulloh Abdusalomov",
            status="active",
            workspace="ravan_1c",
            required_permissions=["ravan_1c.view", "ravan_1c.run"],
            available_permissions=[
                "ravan_1c.view",
                "ravan_1c.run",
                "ravan_1c.export",
            ],
            required_files=[
                {"key": "ravan_file", "label": "Ravan (Excel/CSV)"},
                {"key": "c_file", "label": "1C (Excel/CSV, 3 колонки без заголовков)"},
            ],
        )

    def validate_inputs(
        self,
        files: Dict[str, bytes],
        params: Dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        if not files.get("ravan_file"):
            errors.append("Не загружен файл Ravan")
        if not files.get("c_file"):
            errors.append("Не загружен файл 1C")

        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=[],
            columns_found={},
        )

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        started = time.time()
        run_id = str(uuid.uuid4())[:8]

        # The source workflow defines a fixed SUM_TOLERANCE = 1.
        tolerance = 1.0

        ravan_sheet = params.get("ravan_sheet_name") or 0
        c_sheet = params.get("c_sheet_name") or 0
        try:
            ravan_header_row = max(1, int(params.get("ravan_header_row") or 1))
        except (TypeError, ValueError):
            ravan_header_row = 1

        ravan = _read_source(
            files["ravan_file"],
            params.get("ravan_file_filename", "Ravan.xlsx"),
            header=ravan_header_row - 1,
            sheet_name=ravan_sheet,
        )
        c = _read_source(
            files["c_file"],
            params.get("c_file_filename", "1C.xlsx"),
            header=None,
            sheet_name=c_sheet,
        )

        required_ravan = ["Partner", "NDS", "Kolvo", "Summ"]
        missing = [column for column in required_ravan if column not in ravan.columns]
        if missing:
            raise ValueError(
                "В Ravan отсутствуют обязательные столбцы: " + ", ".join(missing)
            )

        if c.shape[1] != 3:
            raise ValueError(
                "Файл 1C должен содержать ровно 3 колонки без строки заголовков: "
                "Partner, Kolvo, Summ"
            )

        # The original workflow assigns all three 1C columns directly.
        c = c.copy()
        c.columns = ["Partner", "Kolvo", "Summ"]

        ravan = ravan.copy()
        ravan["NDS"] = _number(ravan["NDS"])
        ravan["Kolvo"] = _number(ravan["Kolvo"])
        ravan["Summ"] = _number(ravan["Summ"])
        c["Kolvo"] = _number(c["Kolvo"])
        c["Summ"] = _number(c["Summ"])

        ravan["Company_Key"] = ravan["Partner"].apply(clean_company_name)
        c["Company_Key"] = c["Partner"].apply(clean_company_name)

        # Source formula:
        # Summ 1C = Summ Ravan * (112 - NDS) / 112
        ravan["Summ_Corrected"] = ravan["Summ"] * (112 - ravan["NDS"]) / 112

        ravan_compare = ravan[
            ["Company_Key", "Partner", "NDS", "Kolvo", "Summ", "Summ_Corrected"]
        ].copy()
        ravan_compare = ravan_compare.rename(
            columns={
                "Partner": "Partner_Ravan",
                "Kolvo": "Kolvo_Ravan",
                "Summ": "Summ_Ravan",
            }
        )

        c_compare = c[["Company_Key", "Partner", "Kolvo", "Summ"]].copy()
        c_compare = c_compare.rename(
            columns={
                "Partner": "Partner_C",
                "Kolvo": "Kolvo_C",
                "Summ": "Summ_C",
            }
        )

        result = pd.merge(
            ravan_compare,
            c_compare,
            on="Company_Key",
            how="outer",
        )
        result = _apply_fuzzy_name_matches(result)

        result["Kolvo_Difference"] = (
            result["Kolvo_C"].fillna(0) - result["Kolvo_Ravan"].fillna(0)
        )
        result["Summ_Difference"] = (
            result["Summ_C"].fillna(0) - result["Summ_Corrected"].fillna(0)
        )

        def get_status(row: pd.Series) -> str:
            if pd.isna(row["Partner_C"]):
                return "Нет в !C"
            if pd.isna(row["Partner_Ravan"]):
                return "Нет в Ravan"

            kolvo_ok = abs(float(row["Kolvo_Difference"])) == 0
            summ_ok = abs(float(row["Summ_Difference"])) <= tolerance

            if kolvo_ok and summ_ok:
                return "OK"
            if not kolvo_ok and not summ_ok:
                return "Ошибка Kolvo + Summ"
            if not kolvo_ok:
                return "Ошибка Kolvo"
            if not summ_ok:
                return "Ошибка Summ"
            return "Ошибка"

        result["Status"] = result.apply(get_status, axis=1)

        for column in (
            "Summ_Ravan",
            "Summ_Corrected",
            "Summ_C",
            "Summ_Difference",
        ):
            result[column] = pd.to_numeric(result[column], errors="coerce").round(2)

        # Put unresolved fuzzy name matches first so users can review them immediately.
        result = result.sort_values(
            by=["Needs_Review"],
            ascending=[False],
            kind="stable",
        ).reset_index(drop=True)
        result["Row_ID"] = [f"{run_id}-{index + 1}" for index in range(len(result))]

        status_order = [
            "OK",
            "Ошибка Kolvo",
            "Ошибка Summ",
            "Ошибка Kolvo + Summ",
            "Нет в !C",
            "Нет в Ravan",
            "Ошибка",
        ]
        status_counts = {
            status: int((result["Status"] == status).sum())
            for status in status_order
            if int((result["Status"] == status).sum()) > 0
        }

        total_companies = len(result)
        ok_count = int((result["Status"] == "OK").sum())
        discrepancy_count = total_companies - ok_count
        # Totals describe the uploaded sources. The original outer merge can
        # repeat source rows when a normalized company occurs more than once.
        corrected_sum = float(ravan["Summ_Corrected"].sum())
        c_sum = float(c["Summ"].sum())
        diff_sum = c_sum - corrected_sum
        match_percentage = (
            round(ok_count / total_companies * 100, 2)
            if total_companies
            else 0.0
        )

        display = result.drop(columns=["Company_Key"]).copy()
        discrepancies = display.loc[display["Status"] != "OK"].copy()

        duration_ms = round((time.time() - started) * 1000, 2)

        return ReconResult(
            run_id=run_id,
            module_id="ravan_1c",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="COMPLETED" if discrepancy_count == 0 else "WARNING",
            summary=ReconSummary(
                total_records_a=len(ravan),
                total_records_b=len(c),
                total_sum_a=round(corrected_sum, 2),
                total_sum_b=round(c_sum, 2),
                matched_count=ok_count,
                discrepancy_count=discrepancy_count,
                diff_sum=round(diff_sum, 2),
                match_percentage=match_percentage,
                execution_time_ms=duration_ms,
            ),
            by_category=[
                {"status": status, "count": count}
                for status, count in status_counts.items()
            ],
            discrepancies=_records(discrepancies),
            custom_metrics={
                "ravan_1c": {
                    "producer": "Sayfulloh Abdusalomov",
                    "sum_tolerance": tolerance,
                    "status_counts": status_counts,
                    "rows": _records(display),
                    "source_ravan_rows": len(ravan),
                    "source_1c_rows": len(c),
                    "source_files": [
                        params.get("ravan_file_filename", "Ravan.xlsx"),
                        params.get("c_file_filename", "1C.xlsx"),
                    ],
                    "fuzzy_review_count": int(result["Needs_Review"].sum()),
                    "fuzzy_name_threshold": FUZZY_NAME_THRESHOLD,
                }
            },
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "module": "ravan_1c",
            "run_id": run_id,
            "metrics": {},
            "source": "archive",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""


MODULE_CLASS = Ravan1CModule
