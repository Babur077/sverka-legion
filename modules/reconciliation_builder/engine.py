"""Deterministic universal reconciliation engine for the visual constructor."""

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


def _apply_key_transform(value: Any, transform: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    transform = str(transform or "none").strip().lower()
    if transform == "remove_spaces":
        return re.sub(r"\s+", "", text)
    if transform == "digits_only":
        return re.sub(r"\D+", "", text)
    if transform == "strip_leading_zeros":
        stripped = text.lstrip("0")
        return stripped or "0"
    if transform == "alnum":
        return re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "", text)
    return text


def _normalize_key(value: Any, mode: str, transform: str = "none") -> str:
    text = _apply_key_transform(value, transform)
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
        number = float(cleaned)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def _transform_amount(value: Optional[float], transform: str) -> Optional[float]:
    if value is None:
        return None
    transform = str(transform or "as_is").strip().lower()
    if transform == "invert":
        return -value
    if transform == "absolute":
        return abs(value)
    return value


def _parse_date(value: Any, dayfirst: bool) -> Optional[pd.Timestamp]:
    if value is None or _clean_text(value) == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=dayfirst)
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).normalize()


def _load_json_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        value = raw
    else:
        try:
            value = json.loads(str(raw or "[]"))
        except (TypeError, json.JSONDecodeError):
            return []
    return [item for item in value if isinstance(item, dict)]


def _load_pairs(raw: Any) -> list[dict[str, str]]:
    result = []
    for item in _load_json_list(raw):
        left = str(item.get("left") or "").strip()
        right = str(item.get("right") or "").strip()
        mode = str(item.get("mode") or "text").strip().lower()
        left_transform = str(item.get("left_transform") or "none").strip().lower()
        right_transform = str(item.get("right_transform") or "none").strip().lower()

        if left and right:
            result.append({
                "left": left,
                "right": right,
                "mode": mode if mode in {"exact", "text", "numeric"} else "text",
                "left_transform": left_transform
                if left_transform in {"none", "remove_spaces", "digits_only", "strip_leading_zeros", "alnum"}
                else "none",
                "right_transform": right_transform
                if right_transform in {"none", "remove_spaces", "digits_only", "strip_leading_zeros", "alnum"}
                else "none",
            })
    return result


def _load_filters(raw: Any) -> list[dict[str, str]]:
    allowed_operators = {
        "equals",
        "not_equals",
        "contains",
        "not_contains",
        "empty",
        "not_empty",
        "gt",
        "gte",
        "lt",
        "lte",
    }
    result = []
    for item in _load_json_list(raw):
        side = str(item.get("side") or "").strip().lower()
        column = str(item.get("column") or "").strip()
        operator = str(item.get("operator") or "equals").strip().lower()
        value = str(item.get("value") or "")
        if side in {"a", "b"} and column and operator in allowed_operators:
            result.append({
                "side": side,
                "column": column,
                "operator": operator,
                "value": value,
            })
    return result


def _filter_matches(value: Any, operator: str, expected: str) -> bool:
    text = _clean_text(value)
    normalized = text.casefold()
    expected_text = str(expected or "").strip()
    expected_normalized = expected_text.casefold()

    if operator == "empty":
        return text == ""
    if operator == "not_empty":
        return text != ""
    if operator == "equals":
        return normalized == expected_normalized
    if operator == "not_equals":
        return normalized != expected_normalized
    if operator == "contains":
        return expected_normalized in normalized
    if operator == "not_contains":
        return expected_normalized not in normalized

    actual_number = _parse_amount(value)
    expected_number = _parse_amount(expected_text)
    if actual_number is None or expected_number is None:
        return False
    if operator == "gt":
        return actual_number > expected_number
    if operator == "gte":
        return actual_number >= expected_number
    if operator == "lt":
        return actual_number < expected_number
    if operator == "lte":
        return actual_number <= expected_number
    return False


def _apply_filters(
    frame: pd.DataFrame,
    filters: list[dict[str, str]],
    side: str,
) -> pd.DataFrame:
    filtered = frame
    for rule in filters:
        if rule["side"] != side:
            continue
        column = rule["column"]
        if column not in filtered.columns:
            raise ValueError(
                f"Фильтр источника {side.upper()}: колонка «{column}» не найдена"
            )
        mask = filtered[column].map(
            lambda value: _filter_matches(
                value,
                rule["operator"],
                rule.get("value", ""),
            )
        )
        filtered = filtered.loc[mask]
    return filtered


class ReconciliationBuilderModule(BaseReconciliationModule):
    @property
    def manifest(self) -> ModuleManifest:
        return ModuleManifest(
            id="reconciliation_builder",
            name="Конструктор сверок",
            version="0.2.0",
            description=(
                "Универсальная детерминированная сверка двух Excel/CSV: "
                "фильтры, преобразования, 1↔1 / 1↔N / N↔1, суммы и даты."
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

        if not _load_pairs(params.get("key_pairs")):
            errors.append("Добавьте хотя бы одну пару ключевых колонок")

        matching_mode = str(params.get("matching_mode") or "one_to_one")
        if matching_mode not in {"one_to_one", "one_to_many", "many_to_one"}:
            errors.append("Неизвестный режим сопоставления")

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
        filters = _load_filters(params.get("filters"))
        matching_mode = str(params.get("matching_mode") or "one_to_one").strip()
        amount_a = str(params.get("amount_a_col") or "").strip()
        amount_b = str(params.get("amount_b_col") or "").strip()
        amount_a_transform = str(params.get("amount_a_transform") or "as_is").strip()
        amount_b_transform = str(params.get("amount_b_transform") or "as_is").strip()
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
        original_count_a = len(frame_a)
        original_count_b = len(frame_b)

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
        required_a.extend(rule["column"] for rule in filters if rule["side"] == "a")
        required_b.extend(rule["column"] for rule in filters if rule["side"] == "b")

        missing_a = sorted({column for column in required_a if column not in frame_a.columns})
        missing_b = sorted({column for column in required_b if column not in frame_b.columns})
        if missing_a or missing_b:
            details = []
            if missing_a:
                details.append("Источник A: " + ", ".join(missing_a))
            if missing_b:
                details.append("Источник B: " + ", ".join(missing_b))
            raise ValueError("Не найдены выбранные колонки. " + "; ".join(details))

        frame_a = _apply_filters(frame_a, filters, "a")
        frame_b = _apply_filters(frame_b, filters, "b")

        def key_for(row: pd.Series, side: str) -> tuple[str, ...]:
            values: list[str] = []
            for pair in pairs:
                column = pair["left"] if side == "a" else pair["right"]
                transform = pair["left_transform"] if side == "a" else pair["right_transform"]
                values.append(_normalize_key(row.get(column), pair["mode"], transform))
            return tuple(values)

        def build_row(index: Any, row: pd.Series, side: str) -> dict[str, Any]:
            amount_column = amount_a if side == "a" else amount_b
            amount_transform = amount_a_transform if side == "a" else amount_b_transform
            date_column = date_a if side == "a" else date_b
            parsed_amount = _parse_amount(row.get(amount_column)) if amount_column else None
            return {
                "index": int(index),
                "row": row,
                "key": key_for(row, side),
                "amount": _transform_amount(parsed_amount, amount_transform),
                "date": _parse_date(row.get(date_column), dayfirst) if date_column else None,
            }

        rows_a = [build_row(index, row, "a") for index, row in frame_a.iterrows()]
        rows_b = [build_row(index, row, "b") for index, row in frame_b.iterrows()]

        groups_a: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        groups_b: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        for item in rows_a:
            groups_a[item["key"]].append(item)
        for item in rows_b:
            groups_b[item["key"]].append(item)

        used_a: set[int] = set()
        used_b: set[int] = set()
        matched: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []
        only_a: list[dict[str, Any]] = []
        only_b: list[dict[str, Any]] = []

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
                "grouped_rows_a": [a["index"] + 2],
                "grouped_rows_b": [b["index"] + 2],
                "match_type": "1↔1",
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

        def aggregate_metrics(
            left_rows: list[dict[str, Any]],
            right_rows: list[dict[str, Any]],
        ) -> dict[str, Any]:
            left_amounts = [row["amount"] for row in left_rows]
            right_amounts = [row["amount"] for row in right_rows]
            left_total = None
            right_total = None
            amount_delta = None
            amount_ok = True

            if amount_a and amount_b:
                if any(value is None for value in left_amounts + right_amounts):
                    amount_ok = False
                else:
                    left_total = sum(float(value) for value in left_amounts)
                    right_total = sum(float(value) for value in right_amounts)
                    amount_delta = abs(left_total - right_total)
                    amount_ok = amount_delta <= amount_tolerance

            date_delta = None
            date_ok = True
            if date_a and date_b:
                left_dates = [row["date"] for row in left_rows]
                right_dates = [row["date"] for row in right_rows]
                if any(value is None for value in left_dates + right_dates):
                    date_ok = False
                else:
                    date_delta = max(
                        abs(int((left_date - right_date).days))
                        for left_date in left_dates
                        for right_date in right_dates
                    )
                    date_ok = date_delta <= date_tolerance_days

            return {
                "left_total": left_total,
                "right_total": right_total,
                "amount_delta": amount_delta,
                "amount_ok": amount_ok,
                "date_delta_days": date_delta,
                "date_ok": date_ok,
                "qualifies": amount_ok and date_ok,
            }

        def render_group(
            left_rows: list[dict[str, Any]],
            right_rows: list[dict[str, Any]],
            metrics: dict[str, Any],
            match_type: str,
            reason: str = "",
        ) -> dict[str, Any]:
            first_a = left_rows[0]
            first_b = right_rows[0]
            return {
                "key": " | ".join(first_a["key"]),
                "row_a": first_a["index"] + 2 if len(left_rows) == 1 else None,
                "row_b": first_b["index"] + 2 if len(right_rows) == 1 else None,
                "grouped_rows_a": [row["index"] + 2 for row in left_rows],
                "grouped_rows_b": [row["index"] + 2 for row in right_rows],
                "match_type": match_type,
                "amount_a": metrics["left_total"],
                "amount_b": metrics["right_total"],
                "amount_delta": metrics["amount_delta"],
                "date_a": first_a["date"].date().isoformat() if first_a["date"] is not None else None,
                "date_b": first_b["date"].date().isoformat() if first_b["date"] is not None else None,
                "date_delta_days": metrics["date_delta_days"],
                "reason": reason,
                "source_a": {
                    "rows": [_safe(row["row"].to_dict()) for row in left_rows],
                },
                "source_b": {
                    "rows": [_safe(row["row"].to_dict()) for row in right_rows],
                },
            }

        # Stage 1: deterministic qualifying 1↔1 matches inside each key.
        for key in sorted(set(groups_a) & set(groups_b)):
            left_group = groups_a[key]
            right_group = groups_b[key]
            if ignore_empty_keys and any(not value for value in key):
                continue

            for a in left_group:
                if a["index"] in used_a:
                    continue
                candidates = [
                    b for b in right_group
                    if b["index"] not in used_b
                ]
                if not candidates:
                    break

                evaluated = [(b, candidate_metrics(a, b)) for b in candidates]
                qualifying = [item for item in evaluated if item[1]["qualifies"]]
                if not qualifying:
                    continue

                selected_b, metrics = min(
                    qualifying,
                    key=lambda item: (item[1]["score"], item[0]["index"]),
                )
                used_a.add(a["index"])
                used_b.add(selected_b["index"])
                matched.append(render_pair(a, selected_b, metrics))

        # Stage 2: optional grouped matching for rows that remain under the same key.
        if matching_mode in {"one_to_many", "many_to_one"}:
            for key in sorted(set(groups_a) & set(groups_b)):
                if ignore_empty_keys and any(not value for value in key):
                    continue

                left_remaining = [
                    row for row in groups_a[key]
                    if row["index"] not in used_a
                ]
                right_remaining = [
                    row for row in groups_b[key]
                    if row["index"] not in used_b
                ]
                if not left_remaining or not right_remaining:
                    continue

                is_supported = (
                    matching_mode == "one_to_many"
                    and len(left_remaining) == 1
                    and len(right_remaining) >= 1
                ) or (
                    matching_mode == "many_to_one"
                    and len(left_remaining) >= 1
                    and len(right_remaining) == 1
                )
                if not is_supported:
                    continue

                metrics = aggregate_metrics(left_remaining, right_remaining)
                match_type = "1↔N" if matching_mode == "one_to_many" else "N↔1"
                if metrics["qualifies"]:
                    matched.append(
                        render_group(
                            left_remaining,
                            right_remaining,
                            metrics,
                            match_type,
                        )
                    )
                else:
                    reasons = []
                    if not metrics["amount_ok"]:
                        reasons.append(
                            "Сумма группы вне допуска"
                            if metrics["amount_delta"] is not None
                            else "Сумма группы не распознана"
                        )
                    if not metrics["date_ok"]:
                        reasons.append(
                            "Дата группы вне допуска"
                            if metrics["date_delta_days"] is not None
                            else "Дата группы не распознана"
                        )
                    mismatches.append(
                        render_group(
                            left_remaining,
                            right_remaining,
                            metrics,
                            match_type,
                            "; ".join(reasons) or "Групповое расхождение",
                        )
                    )

                used_a.update(row["index"] for row in left_remaining)
                used_b.update(row["index"] for row in right_remaining)

        # Stage 3: pair remaining single rows with same key as mismatches.
        for key in sorted(set(groups_a) & set(groups_b)):
            if ignore_empty_keys and any(not value for value in key):
                continue
            left_remaining = [
                row for row in groups_a[key]
                if row["index"] not in used_a
            ]
            right_remaining = [
                row for row in groups_b[key]
                if row["index"] not in used_b
            ]

            while left_remaining and right_remaining:
                a = left_remaining.pop(0)
                evaluated = [(b, candidate_metrics(a, b)) for b in right_remaining]
                selected_b, metrics = min(
                    evaluated,
                    key=lambda item: (item[1]["score"], item[0]["index"]),
                )
                right_remaining = [
                    row for row in right_remaining
                    if row["index"] != selected_b["index"]
                ]
                used_a.add(a["index"])
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
                    render_pair(
                        a,
                        selected_b,
                        metrics,
                        "; ".join(reasons) or "Расхождение",
                    )
                )

        for a in rows_a:
            if a["index"] in used_a:
                continue
            empty_key = any(not value for value in a["key"])
            only_a.append({
                "key": " | ".join(a["key"]),
                "row_a": a["index"] + 2,
                "grouped_rows_a": [a["index"] + 2],
                "match_type": "1↔1",
                "reason": (
                    "Пустой ключ"
                    if ignore_empty_keys and empty_key
                    else "Нет подходящей строки в источнике B"
                ),
                "source_a": _safe(a["row"].to_dict()),
            })

        for b in rows_b:
            if b["index"] in used_b:
                continue
            empty_key = any(not value for value in b["key"])
            only_b.append({
                "key": " | ".join(b["key"]),
                "row_b": b["index"] + 2,
                "grouped_rows_b": [b["index"] + 2],
                "match_type": "1↔1",
                "reason": (
                    "Пустой ключ"
                    if ignore_empty_keys and empty_key
                    else "Нет подходящей строки в источнике A"
                ),
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
                "matching_mode": matching_mode,
                "key_pairs": pairs,
                "filters": filters,
                "filter_stats": {
                    "source_a_before": original_count_a,
                    "source_a_after": len(frame_a),
                    "source_b_before": original_count_b,
                    "source_b_after": len(frame_b),
                },
                "amount_mapping": {
                    "left": amount_a or None,
                    "right": amount_b or None,
                    "tolerance": amount_tolerance,
                    "left_transform": amount_a_transform,
                    "right_transform": amount_b_transform,
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
