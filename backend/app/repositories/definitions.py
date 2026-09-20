from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from utils.db_manager import DB_PATH


def list_definitions(active_only: bool = True) -> list[dict[str, Any]]:
    query = "SELECT * FROM reconciliation_definitions"
    params: tuple[Any, ...] = ()
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY name COLLATE NOCASE"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = json.loads(item.pop("config_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["config"] = {}
        item["is_active"] = bool(item.get("is_active"))
        result.append(item)
    return result


def get_definition(definition_id: int) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM reconciliation_definitions WHERE id = ?",
            (int(definition_id),),
        ).fetchone()

    if not row:
        return None

    item = dict(row)
    try:
        item["config"] = json.loads(item.pop("config_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        item["config"] = {}
    item["is_active"] = bool(item.get("is_active"))
    return item


def save_definition(
    *,
    name: str,
    description: str,
    config: dict[str, Any],
    username: str,
    definition_id: int | None = None,
) -> tuple[bool, str, int | None]:
    now = datetime.now().isoformat()
    clean_name = str(name or "").strip()
    if not clean_name:
        return False, "Название шаблона обязательно", None

    config_json = json.dumps(config or {}, ensure_ascii=False, default=str)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            if definition_id is None:
                cursor.execute(
                    """
                    INSERT INTO reconciliation_definitions (
                        name, description, config_json, created_by,
                        created_at, updated_at, is_active
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                    """,
                    (
                        clean_name,
                        str(description or "").strip(),
                        config_json,
                        str(username or ""),
                        now,
                        now,
                    ),
                )
                record_id = int(cursor.lastrowid)
                message = f"Шаблон «{clean_name}» сохранён."
            else:
                cursor.execute(
                    """
                    UPDATE reconciliation_definitions
                    SET name = ?, description = ?, config_json = ?,
                        updated_at = ?, is_active = 1
                    WHERE id = ?
                    """,
                    (
                        clean_name,
                        str(description or "").strip(),
                        config_json,
                        now,
                        int(definition_id),
                    ),
                )
                if cursor.rowcount == 0:
                    return False, "Шаблон не найден", None
                record_id = int(definition_id)
                message = f"Шаблон «{clean_name}» обновлён."

            conn.commit()
            return True, message, record_id
        except sqlite3.IntegrityError:
            return False, f"Шаблон с названием «{clean_name}» уже существует", None


def deactivate_definition(definition_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reconciliation_definitions
            SET is_active = 0, updated_at = ?
            WHERE id = ? AND is_active = 1
            """,
            (datetime.now().isoformat(), int(definition_id)),
        )
        conn.commit()
        return cursor.rowcount > 0
