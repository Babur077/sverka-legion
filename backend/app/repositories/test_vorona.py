from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import utils.db_manager as db


def _period_key(source_type: str, year: int | None, month: int | None) -> str:
    if source_type == "partners":
        return "GLOBAL"
    if source_type == "opening_balances":
        if not year:
            raise ValueError("Для начального сальдо нужен год")
        return f"{int(year):04d}"
    if not year or not month:
        raise ValueError("Для помесячного источника нужны год и месяц")
    return f"{int(year):04d}-{int(month):02d}"


def get_active_batch(
    source_type: str,
    year: int | None,
    month: int | None,
) -> dict[str, Any] | None:
    period_key = _period_key(source_type, year, month)
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM test_vorona_import_batches
            WHERE source_type = ? AND period_key = ? AND is_active = 1
            LIMIT 1
            """,
            (source_type, period_key),
        ).fetchone()
    return dict(row) if row else None


def find_same_file_batch(
    source_type: str,
    year: int | None,
    month: int | None,
    file_hash: str,
) -> dict[str, Any] | None:
    period_key = _period_key(source_type, year, month)
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM test_vorona_import_batches
            WHERE source_type = ? AND period_key = ? AND file_hash = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_type, period_key, file_hash),
        ).fetchone()
    return dict(row) if row else None


def save_import_batch(
    *,
    source_type: str,
    year: int | None,
    month: int | None,
    filename: str,
    file_hash: str,
    records: list[dict[str, Any]],
    username: str,
    replace_existing: bool,
) -> dict[str, Any]:
    period_key = _period_key(source_type, year, month)
    now = datetime.now().isoformat()

    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")

        duplicate = cursor.execute(
            """
            SELECT *
            FROM test_vorona_import_batches
            WHERE source_type = ? AND period_key = ? AND file_hash = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (source_type, period_key, file_hash),
        ).fetchone()
        if duplicate:
            conn.rollback()
            return {
                "state": "duplicate",
                "batch": dict(duplicate),
                "message": "Этот файл для выбранного периода уже загружался.",
            }

        current = cursor.execute(
            """
            SELECT *
            FROM test_vorona_import_batches
            WHERE source_type = ? AND period_key = ? AND is_active = 1
            LIMIT 1
            """,
            (source_type, period_key),
        ).fetchone()

        if current and not replace_existing:
            conn.rollback()
            return {
                "state": "conflict",
                "batch": dict(current),
                "message": "Для этого источника и периода уже есть активная загрузка.",
            }

        cursor.execute(
            """
            INSERT INTO test_vorona_import_batches (
                source_type, period_key, year, month, filename, file_hash,
                rows_count, status, is_active, uploaded_by, uploaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
            """,
            (
                source_type,
                period_key,
                year,
                month,
                filename,
                file_hash,
                len(records),
                username,
                now,
            ),
        )
        batch_id = int(cursor.lastrowid)

        if current:
            cursor.execute(
                """
                UPDATE test_vorona_import_batches
                SET is_active = 0, status = 'replaced', replaced_by_batch_id = ?
                WHERE id = ?
                """,
                (batch_id, int(current["id"])),
            )

        cursor.executemany(
            """
            INSERT INTO test_vorona_records (
                batch_id, source_type, row_index, operation_date, year, month,
                inn, vid, partner, amount, commission, status, service, side,
                raw_json, row_hash
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    batch_id,
                    source_type,
                    int(record.get("row_index") or index + 1),
                    record.get("date"),
                    record.get("year", year),
                    record.get("month", month),
                    str(record.get("inn") or ""),
                    str(record.get("vid") or ""),
                    str(record.get("partner") or ""),
                    float(record.get("amount") or 0),
                    float(record.get("commission") or 0),
                    str(record.get("status") or ""),
                    str(record.get("service") or ""),
                    str(record.get("side") or ""),
                    json.dumps(record.get("raw") or {}, ensure_ascii=False, default=str),
                    str(record.get("row_hash") or ""),
                )
                for index, record in enumerate(records)
            ],
        )

        conn.commit()

    return {
        "state": "saved",
        "batch": {
            "id": batch_id,
            "source_type": source_type,
            "period_key": period_key,
            "year": year,
            "month": month,
            "filename": filename,
            "file_hash": file_hash,
            "rows_count": len(records),
            "status": "active",
            "is_active": 1,
            "uploaded_by": username,
            "uploaded_at": now,
        },
        "replaced_batch_id": int(current["id"]) if current else None,
        "message": (
            "Период заменён новой версией."
            if current
            else "Данные успешно добавлены в базу."
        ),
    }


def list_import_batches(
    *,
    year: int | None = None,
    month: int | None = None,
    include_replaced: bool = True,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if year is not None:
        clauses.append("(year = ? OR source_type = 'partners')")
        params.append(int(year))
    if month is not None:
        clauses.append("(month = ? OR month IS NULL)")
        params.append(int(month))
    if not include_replaced:
        clauses.append("is_active = 1")

    query = "SELECT * FROM test_vorona_import_batches"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY uploaded_at DESC, id DESC"

    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()

    return [dict(row) for row in rows]


def load_active_records(
    *,
    year: int,
    through_month: int | None = None,
    source_type: str | None = None,
    vid: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["b.is_active = 1"]
    params: list[Any] = []

    if source_type:
        clauses.append("r.source_type = ?")
        params.append(source_type)

    clauses.append(
        "(r.source_type = 'partners' OR r.year = ? OR (r.source_type = 'opening_balances' AND r.year = ?))"
    )
    params.extend([int(year), int(year)])

    if through_month is not None:
        clauses.append("(r.month IS NULL OR r.month <= ?)")
        params.append(int(through_month))

    if vid:
        clauses.append("r.vid = ?")
        params.append(str(vid))

    query = f"""
        SELECT
            r.id, r.batch_id, r.source_type, r.row_index, r.operation_date,
            r.year, r.month, r.inn, r.vid, r.partner, r.amount, r.commission,
            r.status, r.service, r.side, r.raw_json,
            b.filename, b.period_key, b.uploaded_at
        FROM test_vorona_records r
        JOIN test_vorona_import_batches b ON b.id = r.batch_id
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(r.year, 0), COALESCE(r.month, 0), r.batch_id, r.row_index
    """

    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["raw"] = json.loads(item.pop("raw_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["raw"] = {}
        result.append(item)
    return result


def load_active_datasets(
    *,
    year: int,
    through_month: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    records = load_active_records(year=year, through_month=through_month)
    datasets: dict[str, list[dict[str, Any]]] = {
        "sales": [],
        "bank": [],
        "faktura": [],
        "partners": [],
        "opening_balances": [],
        "one_c": [],
    }
    for record in records:
        source = str(record.get("source_type") or "")
        if source not in datasets:
            continue
        datasets[source].append({
            "date": record.get("operation_date"),
            "year": record.get("year"),
            "month": record.get("month"),
            "inn": record.get("inn") or "",
            "vid": record.get("vid") or "",
            "partner": record.get("partner") or "",
            "amount": float(record.get("amount") or 0),
            "commission": float(record.get("commission") or 0),
            "Status": record.get("status") or "",
            "Service": record.get("service") or "",
            "side": record.get("side") or "",
            "batch_id": record.get("batch_id"),
            "source_file": record.get("filename"),
        })
    return datasets
