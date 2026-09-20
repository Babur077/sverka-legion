"""Deterministic universal reconciliation module used by the visual constructor."""

from __future__ import annotations

import json
import math
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from core.parsers import load_file_polars
from modules.base import (
    BaseReconciliationModule,
    ModuleManifest,
    ReconResult,
    ReconSummary,
    ValidationResult,
)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return None if not math.isfinite(value) else value
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
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


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_key(value: Any, mode: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    if mode == "text":
        return re.sub(r"\s+", " ", text).casefold()

    if mode == "numeric":
        normalized = (
            text.replace("\u00a0", "")
            .replace(" ", "")
            .replace(",", ".")
        )
        try:
            number = float(normalized)
            if number.is_integer():
                return str(int(number))
            return format(number, ".12g")
        except ValueError:
            return text.casefold()

    return text


def _parse_amount(value: Any) -> Optional[float]:
    text = _clean_text(value)
    if not text:
        return None

    cleaned = re.sub(r"[^\d,\.\-]", "", text)
    if not cleaned:
        return None

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.fullmatch(r"-?\d+,\d{1,2}", cleaned):
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")

    try:
        value = float(cleaned)
        return value if math.isfinite(value) else None
    except ValueError:
        return None


def _parse_date(value: Any, dayfirst: bool) -> Optional[pd.Timestamp]:
    if value is None or _clean_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=dayfirst)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def _load_pairs(raw: Any) -> list[dict[str, str]]:
    if isinstance(raw, list):
        value = raw
    else:
        try:
            value = json.loads(str(raw or "[]"))
        except (TypeError, json.JSONDecodeError):
            return []

    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        left = str(item.get("left") or "").strip()
        right = str(item.get("right") or "").strip()
        mode = str(item.get("mode") or "text").strip().lower()
        if left and right:
            result.append({
                "left": left,
                "right": right,
                "mode": mode if mode in {"exact", "text", "numeric"} else "text",
            })
    return result


class ReconciliationBuilderModule(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="reconciliation_builder",
            name="Конструктор сверок",
            version="0.1.0",
            description=(
                "Универсальная детерминированная сверка двух Excel/CSV: "
                "сопоставление ключей, сумм и дат с сохраняемыми шаблонами."
            ),
            category="Универсальные",
            icon="Wrench",
            author="ReconcileHub Platform",
            status="active",
            workspace="reconciliation_builder",
            required_permissions=[
                "reconciliation_builder.view",
                "reconciliation_builder.run",
            ],
            available_permissions=[
                "reconciliation_builder.view",
                "reconciliation_builder.run",
                "reconciliation_builder.manage",
                "reconciliation_builder.export",
            ],
            required_files=[
                {"key": "source_a", "label": "Источник A (Excel/CSV)"},
                {"key": "source_b", "label": "Источник B (Excel/CSV)"},
            ],
        )

    def validate_inputs(
        self,
        files: Dict[str, bytes],
        params: Dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        if not files.get("source_a"):
            errors.append("Не загружен источник A")
        if not files.get("source_b"):
            errors.append("Не загружен источник B")

        pairs = _load_pairs(params.get("key_pairs"))
        if not pairs:
            errors.append("Добавьте хотя бы одну пару ключевых колонок")

        return ValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=[],
            columns_found={},
        )

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}

    def run(self, files: Dict[str, bytes], params: Dict[str, Any]) -> ReconResult:
        started = time.time()
        run_id = str(uuid.uuid4())[:8]

        pairs = _load_pairs(params.get("key_pairs"))
        amount_a = str(params.get("amount_a_col") or "").strip()
        amount_b = str(params.get("amount_b_col") or "").strip()
        date_a = str(params.get("date_a_col") or "").strip()
        date_b = str(params.get("date_b_col") or "").strip()
        amount_tolerance = max(0.0, float(params.get("amount_tolerance") or 0))
        date_tolerance_days = max(0, int(float(params.get("date_tolerance_days") or 0)))
        ignore_empty_keys = self._as_bool(params.get("ignore_empty_keys"), True)
        dayfirst = self._as_bool(params.get("dayfirst"), True)

        frame_a_pl = load_file_polars(
            files["source_a"],
            params.get("source_a_filename", "source_a.xlsx"),
        )
        frame_b_pl = load_file_polars(
            files["source_b"],
            params.get("source_b_filename", "source_b.xlsx"),
        )
        if frame_a_pl is None or frame_b_pl is None:
            raise ValueError("Не удалось распознать один из файлов")

        frame_a = frame_a_pl.to_pandas()
        frame_b = frame_b_pl.to_pandas()

        required_a = [pair["left"] for pair in pairs]
        required_b = [pair["right"] for pair in pairs]
        if amount_a:
            required_a.append(amount_a)
        if amount_b:
            required_b.append(amount_b)
        if date_a:
            required_a.append(date_a)
        if date_b:
            required_b.append(date_b)

        missing_a = sorted({column for column in required_a if column not in frame_a.columns})
        missing_b = sorted({column for column in required_b if column not in frame_b.columns})
        if missing_a or missing_b:
            details = []
            if missing_a:
                details.append("Источник A: " + ", ".join(missing_a))
            if missing_b:
                details.append("Источник B: " + ", ".join(missing_b))
            raise ValueError("Не найдены выбранные колонки. " + "; ".join(details))

        def key_for(row: pd.Series, side: str) -> tuple[str, ...]:
            values: list[str] = []
            for pair in pairs:
                column = pair["left"] if side == "a" else pair["right"]
                values.append(_normalize_key(row.get(column), pair["mode"]))
            return tuple(values)

        rows_a = [
            {
                "index": int(index),
                "row": row,
                "key": key_for(row, "a"),
                "amount": _parse_amount(row.get(amount_a)) if amount_a else None,
                "date": _parse_date(row.get(date_a), dayfirst) if date_a else None,
            }
            for index, row in frame_a.iterrows()
        ]
        rows_b = [
            {
                "index": int(index),
                "row": row,
                "key": key_for(row, "b"),
                "amount": _parse_amount(row.get(amount_b)) if amount_b else None,
                "date": _parse_date(row.get(date_b), dayfirst) if date_b else None,
            }
            for index, row in frame_b.iterrows()
        ]

        groups_b: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for item in rows_b:
            groups_b[item["key"]].append(item)

        used_b: set[int] = set()
        matched: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        only_a: list[dict[str, Any]] = []

        def candidate_metrics(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
            amount_delta = None
            amount_ok = True
            if amount_a and amount_b:
                if a["amount"] is None or b["amount"] is None:
                    amount_ok = False
                else:
                    amount_delta = abs(float(a["amount"]) - float(b["amount"]))
                    amount_ok = amount_delta <= amount_tolerance

            date_delta = None
            date_ok = True
            if date_a and date_b:
                if a["date"] is None or b["date"] is None:
                    date_ok = False
                else:
                    date_delta = abs(int((a["date"] - b["date"]).days))
                    date_ok = date_delta <= date_tolerance_days

            score = (amount_delta if amount_delta is not None else 0.0) + (
                float(date_delta or 0) * max(amount_tolerance, 1.0)
            )
            return {
                "amount_delta": amount_delta,
                "amount_ok": amount_ok,
                "date_delta_days": date_delta,
                "date_ok": date_ok,
                "qualifies": amount_ok and date_ok,
                "score": score,
            }

        def render_pair(
            a: dict[str, Any],
            b: dict[str, Any],
            metrics: dict[str, Any],
            reason: str = "",
        ) -> dict[str, Any]:
            return {
                "key": " | ".join(a["key"]),
                "row_a": a["index"] + 2,
                "row_b": b["index"] + 2,
                "amount_a": a["amount"],
                "amount_b": b["amount"],
                "amount_delta": metrics["amount_delta"],
                "date_a": a["date"].date().isoformat() if a["date"] is not None else None,
                "date_b": b["date"].date().isoformat() if b["date"] is not None else None,
                "date_delta_days": metrics["date_delta_days"],
                "reason": reason,
                "source_a": _safe(a["row"].to_dict()),
                "source_b": _safe(b["row"].to_dict()),
            }

        for a in rows_a:
            empty_key = any(not value for value in a["key"])
            if ignore_empty_keys and empty_key:
                only_a.append({
                    "key": " | ".join(a["key"]),
                    "row_a": a["index"] + 2,
                    "reason": "Пустой ключ",
                    "source_a": _safe(a["row"].to_dict()),
                })
                continue

            candidates = [
                b
                for b in groups_b.get(a["key"], [])
                if b["index"] not in used_b
            ]

            if not candidates:
                only_a.append({
                    "key": " | ".join(a["key"]),
                    "row_a": a["index"] + 2,
                    "reason": "Нет строки с таким ключом в источнике B",
                    "source_a": _safe(a["row"].to_dict()),
                })
                continue

            evaluated = [(b, candidate_metrics(a, b)) for b in candidates]
            qualifying = [item for item in evaluated if item[1]["qualifies"]]

            if qualifying:
                selected_b, metrics = min(
                    qualifying,
                    key=lambda item: (item[1]["score"], item[0]["index"]),
                )
                used_b.add(selected_b["index"])
                matched.append(render_pair(a, selected_b, metrics))
                continue

            selected_b, metrics = min(
                evaluated,
                key=lambda item: (item[1]["score"], item[0]["index"]),
            )
            used_b.add(selected_b["index"])
            reasons = []
            if not metrics["amount_ok"]:
                reasons.append(
                    "Сумма вне допуска"
                    if metrics["amount_delta"] is not None
                    else "Сумма не распознана"
                )
            if not metrics["date_ok"]:
                reasons.append(
                    "Дата вне допуска"
                    if metrics["date_delta_days"] is not None
                    else "Дата не распознана"
                )
            mismatches.append(
                render_pair(a, selected_b, metrics, "; ".join(reasons) or "Расхождение")
            )

        only_b = []
        for b in rows_b:
            if b["index"] in used_b:
                continue
            empty_key = any(not value for value in b["key"])
            reason = (
                "Пустой ключ"
                if ignore_empty_keys and empty_key
                else "Нет строки с таким ключом в источнике A"
            )
            only_b.append({
                "key": " | ".join(b["key"]),
                "row_b": b["index"] + 2,
                "reason": reason,
                "source_b": _safe(b["row"].to_dict()),
            })

        total_sum_a = sum(
            value for value in (item["amount"] for item in rows_a)
            if value is not None
        ) if amount_a else 0.0
        total_sum_b = sum(
            value for value in (item["amount"] for item in rows_b)
            if value is not None
        ) if amount_b else 0.0

        scope = len(matched) + len(mismatches) + len(only_a) + len(only_b)
        match_percentage = (len(matched) / scope * 100) if scope else 0.0
        duration_ms = round((time.time() - started) * 1000, 2)

        custom = {
            "generic": {
                "definition_id": params.get("definition_id") or None,
                "definition_name": str(params.get("definition_name") or "").strip(),
                "key_pairs": pairs,
                "amount_mapping": {
                    "left": amount_a or None,
                    "right": amount_b or None,
                    "tolerance": amount_tolerance,
                },
                "date_mapping": {
                    "left": date_a or None,
                    "right": date_b or None,
                    "tolerance_days": date_tolerance_days,
                },
                "matched": matched,
                "mismatches": mismatches,
                "only_a": only_a,
                "only_b": only_b,
                "columns_a": [str(column) for column in frame_a.columns],
                "columns_b": [str(column) for column in frame_b.columns],
            }
        }

        return ReconResult(
            run_id=run_id,
            module_id="reconciliation_builder",
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            status="COMPLETED" if not mismatches and not only_a and not only_b else "WARNING",
            summary=ReconSummary(
                total_records_a=len(frame_a),
                total_records_b=len(frame_b),
                total_sum_a=round(float(total_sum_a), 2),
                total_sum_b=round(float(total_sum_b), 2),
                matched_count=len(matched),
                discrepancy_count=len(mismatches) + len(only_a) + len(only_b),
                diff_sum=round(float(total_sum_b - total_sum_a), 2),
                match_percentage=round(match_percentage, 2),
                execution_time_ms=duration_ms,
            ),
            by_date=[],
            by_category=[],
            discrepancies=mismatches,
            custom_metrics=custom,
        )

    def get_analytics(self, run_id: Optional[str] = None) -> Dict[str, Any]:
        return {
            "module": "reconciliation_builder",
            "run_id": run_id,
            "metrics": {},
            "source": "archive",
        }

    def export(self, run_id: str, format: str = "xlsx") -> bytes:
        return b""


MODULE_CLASS = ReconciliationBuilderModule
