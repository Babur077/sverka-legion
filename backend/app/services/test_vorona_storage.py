from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import pandas as pd

from backend.app.repositories.test_vorona import (
    load_active_records,
    save_import_batch,
)
from modules.test_vorona.engine import (
    MONTHS,
    _clean_columns,
    _first_present,
    _identifier,
    _number,
    _safe,
    _text,
    _vid,
)

MONTH_NAMES = {value: key for key, value in MONTHS.items()}
SOURCE_TYPES = {
    "sales",
    "bank",
    "faktura",
    "one_c",
    "partners",
    "opening_balances",
}
MONTHLY_SOURCES = {"sales", "bank", "faktura", "one_c"}


def _row_hash(record: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            key: record.get(key)
            for key in (
                "date",
                "year",
                "month",
                "inn",
                "vid",
                "partner",
                "amount",
                "commission",
                "status",
                "service",
                "side",
            )
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read_workbook(content: bytes) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=object)
    return {
        str(name): _clean_columns(frame).dropna(how="all").copy()
        for name, frame in sheets.items()
    }


def _pick_month_frame(
    sheets: dict[str, pd.DataFrame],
    month: int,
) -> tuple[str, pd.DataFrame]:
    month_name = MONTH_NAMES.get(int(month))
    if month_name and month_name in sheets:
        return month_name, sheets[month_name]

    non_empty = [(name, frame) for name, frame in sheets.items() if not frame.empty]
    if len(non_empty) == 1:
        return non_empty[0]

    raise ValueError(
        f"Не найден лист {month_name or month}. "
        "Если файл содержит несколько листов, название месяца должно совпадать с форматом Vorona."
    )


def _partner_lookup(year: int) -> dict[str, str]:
    records = load_active_records(year=year, source_type="partners")
    return {
        str(row.get("inn") or ""): str(row.get("vid") or "")
        for row in records
        if row.get("inn") and row.get("vid")
    }


def _parse_monthly_source(
    *,
    source_type: str,
    content: bytes,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    sheets = _read_workbook(content)
    _, frame = _pick_month_frame(sheets, month)
    id_map = _partner_lookup(year)

    if source_type == "sales":
        inn_columns = ("INN/PINFL", "INN")
        partner_columns = ("Merchant", "Partner")
        amount_column = "Sales"
    elif source_type == "bank":
        inn_columns = ("INN", "INN/PINFL")
        partner_columns = ("Partner", " ")
        amount_column = "Summ"
    elif source_type == "faktura":
        inn_columns = ("INN/PINFL", "INN")
        partner_columns = ("Partner", "Merchant")
        amount_column = "Summ"
    else:
        raise ValueError(f"Неподдерживаемый помесячный источник: {source_type}")

    records: list[dict[str, Any]] = []
    for index, raw in frame.iterrows():
        inn = _identifier(_first_present(raw, *inn_columns))
        vid = _vid(raw.get("VID")) or id_map.get(inn, "")
        partner = _text(_first_present(raw, *partner_columns))
        amount = _number(raw.get(amount_column))
        date = _safe(_first_present(raw, "Data", "Date", "Дата"))

        commission = _number(raw.get("Komissiya")) if source_type == "sales" else 0.0
        status = _text(raw.get("Status")) if source_type == "sales" else ""
        service = _text(raw.get("Service")) if source_type == "sales" else ""

        if not any([inn, vid, partner, amount, commission, date]):
            continue

        record = {
            "row_index": int(index) + 2,
            "date": date,
            "year": int(year),
            "month": int(month),
            "inn": inn,
            "vid": vid,
            "partner": partner,
            "amount": amount,
            "commission": commission,
            "status": status,
            "service": service,
            "side": "",
            "raw": {
                str(key): _safe(value)
                for key, value in raw.to_dict().items()
            },
        }
        record["row_hash"] = _row_hash(record)
        records.append(record)

    return records


def _parse_partners(content: bytes) -> list[dict[str, Any]]:
    sheets = _read_workbook(content)
    frame = sheets.get("INNvsPINFL")
    if frame is None:
        non_empty = [item for item in sheets.values() if not item.empty]
        if len(non_empty) != 1:
            raise ValueError("В справочнике не найден лист INNvsPINFL")
        frame = non_empty[0]

    required = {"Partner", "INNvsPINFL", "Vorona Code"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("В справочнике отсутствуют колонки: " + ", ".join(missing))

    records: list[dict[str, Any]] = []
    for index, raw in frame.iterrows():
        vid = _vid(raw.get("Vorona Code"))
        inn = _identifier(raw.get("INNvsPINFL"))
        partner = _text(raw.get("Partner"))
        if not any([vid, inn, partner]):
            continue
        record = {
            "row_index": int(index) + 2,
            "date": None,
            "year": None,
            "month": None,
            "inn": inn,
            "vid": vid,
            "partner": partner,
            "amount": 0.0,
            "commission": 0.0,
            "status": "",
            "service": "",
            "side": "",
            "raw": {
                str(key): _safe(value)
                for key, value in raw.to_dict().items()
            },
        }
        record["row_hash"] = _row_hash(record)
        records.append(record)
    return records


def _parse_opening_balances(
    content: bytes,
    year: int,
) -> list[dict[str, Any]]:
    sheets = _read_workbook(content)
    preferred = f"Saldo {int(year) - 1}"
    frame = sheets.get(preferred)

    if frame is None:
        candidates = [
            frame
            for name, frame in sheets.items()
            if str(name).casefold().startswith("saldo") and not frame.empty
        ]
        if len(candidates) == 1:
            frame = candidates[0]
        else:
            non_empty = [item for item in sheets.values() if not item.empty]
            if len(non_empty) == 1:
                frame = non_empty[0]

    if frame is None:
        raise ValueError("Не удалось определить лист начального сальдо")

    saldo_columns = [
        str(column)
        for column in frame.columns
        if str(column).strip().casefold().startswith("saldo")
    ]
    if not saldo_columns:
        raise ValueError("В файле начального сальдо не найдена колонка Saldo")
    saldo_column = saldo_columns[-1]

    records: list[dict[str, Any]] = []
    for index, raw in frame.iterrows():
        vid = _vid(raw.get("VID"))
        inn = _identifier(raw.get("INN"))
        partner = _text(raw.get("Partner"))
        amount = _number(raw.get(saldo_column))
        if not any([vid, inn, partner, amount]):
            continue
        record = {
            "row_index": int(index) + 2,
            "date": None,
            "year": int(year),
            "month": None,
            "inn": inn,
            "vid": vid,
            "partner": partner,
            "amount": amount,
            "commission": 0.0,
            "status": "",
            "service": "",
            "side": "opening",
            "raw": {
                str(key): _safe(value)
                for key, value in raw.to_dict().items()
            },
        }
        record["row_hash"] = _row_hash(record)
        records.append(record)
    return records


def _parse_one_c(
    content: bytes,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    sheets = _read_workbook(content)
    frame = sheets.get("1C")
    if frame is None:
        _, frame = _pick_month_frame(sheets, month)

    records: list[dict[str, Any]] = []
    for index, raw in frame.iterrows():
        values = list(raw.values)

        left_vid = _vid(values[0] if len(values) > 0 else None)
        left_partner = _text(values[1] if len(values) > 1 else None)
        left_inn = _identifier(values[2] if len(values) > 2 else None)
        left_amount = _number(values[3] if len(values) > 3 else None)
        if any([left_vid, left_partner, left_inn, left_amount]):
            record = {
                "row_index": int(index) + 1,
                "date": None,
                "year": int(year),
                "month": int(month),
                "inn": left_inn,
                "vid": left_vid,
                "partner": left_partner,
                "amount": left_amount,
                "commission": 0.0,
                "status": "",
                "service": "",
                "side": "4890 / 4010",
                "raw": {},
            }
            record["row_hash"] = _row_hash(record)
            records.append(record)

        right_vid = _vid(values[5] if len(values) > 5 else None)
        right_partner = _text(values[6] if len(values) > 6 else None)
        right_inn = _identifier(values[7] if len(values) > 7 else None)
        right_amount = _number(values[8] if len(values) > 8 else None)
        if any([right_vid, right_partner, right_inn, right_amount]):
            record = {
                "row_index": int(index) + 1,
                "date": None,
                "year": int(year),
                "month": int(month),
                "inn": right_inn,
                "vid": right_vid,
                "partner": right_partner,
                "amount": right_amount,
                "commission": 0.0,
                "status": "",
                "service": "",
                "side": "6990 / 6310",
                "raw": {},
            }
            record["row_hash"] = _row_hash(record)
            records.append(record)

    return records


def parse_test_vorona_import(
    *,
    source_type: str,
    content: bytes,
    year: int | None,
    month: int | None,
) -> list[dict[str, Any]]:
    source_type = str(source_type or "").strip()
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Неизвестный источник: {source_type}")

    if source_type in MONTHLY_SOURCES and (not year or not month):
        raise ValueError("Для помесячной загрузки выберите год и месяц")

    if source_type in {"sales", "bank", "faktura"}:
        return _parse_monthly_source(
            source_type=source_type,
            content=content,
            year=int(year),
            month=int(month),
        )
    if source_type == "one_c":
        return _parse_one_c(content, int(year), int(month))
    if source_type == "partners":
        return _parse_partners(content)
    if source_type == "opening_balances":
        if not year:
            raise ValueError("Для начального сальдо выберите год")
        return _parse_opening_balances(content, int(year))

    raise ValueError(f"Не удалось обработать источник {source_type}")


def import_test_vorona_file(
    *,
    source_type: str,
    content: bytes,
    filename: str,
    year: int | None,
    month: int | None,
    username: str,
    replace_existing: bool = False,
) -> dict[str, Any]:
    records = parse_test_vorona_import(
        source_type=source_type,
        content=content,
        year=year,
        month=month,
    )
    if not records:
        raise ValueError("В выбранном файле не найдено строк для импорта")

    return save_import_batch(
        source_type=source_type,
        year=year,
        month=month,
        filename=filename,
        file_hash=_file_hash(content),
        records=records,
        username=username,
        replace_existing=replace_existing,
    )
