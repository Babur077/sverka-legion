from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from utils.db_manager import DB_PATH


def _now() -> str:
    return datetime.now().isoformat()


def _json_load(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _decode_definition(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["config"] = _json_load(item.pop("config_json", "{}"))
    item["is_active"] = bool(item.get("is_active"))
    if item.get("active_version_id") is not None:
        item["active_version_id"] = int(item["active_version_id"])
    item["current_version_number"] = int(item.get("current_version_number") or 0)
    return item


def _decode_version(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["config"] = _json_load(item.pop("config_json", "{}"))
    item["id"] = int(item["id"])
    item["definition_id"] = int(item["definition_id"])
    item["version_number"] = int(item["version_number"])
    if item.get("based_on_version_id") is not None:
        item["based_on_version_id"] = int(item["based_on_version_id"])
    if item.get("restored_from_version_id") is not None:
        item["restored_from_version_id"] = int(item["restored_from_version_id"])
    return item


def list_definitions(active_only: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT d.*,
               v.created_by AS version_created_by,
               v.created_at AS version_created_at,
               v.change_note AS version_change_note
        FROM reconciliation_definitions d
        LEFT JOIN reconciliation_definition_versions v
          ON v.id = d.active_version_id
    """
    params: tuple[Any, ...] = ()
    if active_only:
        query += " WHERE d.is_active = 1"
    query += " ORDER BY d.name COLLATE NOCASE"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    return [
        item
        for item in (_decode_definition(row) for row in rows)
        if item is not None
    ]


def get_definition(definition_id: int) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT d.*,
                   v.created_by AS version_created_by,
                   v.created_at AS version_created_at,
                   v.change_note AS version_change_note
            FROM reconciliation_definitions d
            LEFT JOIN reconciliation_definition_versions v
              ON v.id = d.active_version_id
            WHERE d.id = ?
            """,
            (int(definition_id),),
        ).fetchone()
    return _decode_definition(row)


def list_definition_versions(definition_id: int) -> list[dict[str, Any]]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT *
            FROM reconciliation_definition_versions
            WHERE definition_id = ?
            ORDER BY version_number DESC
            """,
            (int(definition_id),),
        ).fetchall()
    return [
        item
        for item in (_decode_version(row) for row in rows)
        if item is not None
    ]


def get_definition_version(
    definition_id: int,
    version_id: int,
) -> dict[str, Any] | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM reconciliation_definition_versions
            WHERE definition_id = ? AND id = ?
            """,
            (int(definition_id), int(version_id)),
        ).fetchone()
    return _decode_version(row)


def save_definition(
    *,
    name: str,
    description: str,
    config: dict[str, Any],
    username: str,
    definition_id: int | None = None,
    change_note: str = "",
) -> tuple[bool, str, int | None]:
    now = _now()
    clean_name = str(name or "").strip()
    clean_description = str(description or "").strip()
    clean_note = str(change_note or "").strip()
    if not clean_name:
        return False, "Название шаблона обязательно", None

    config_json = json.dumps(config or {}, ensure_ascii=False, default=str)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN")

            if definition_id is None:
                cursor.execute(
                    """
                    INSERT INTO reconciliation_definitions (
                        name, description, config_json, created_by,
                        created_at, updated_at, is_active, current_version_number
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, 0)
                    """,
                    (
                        clean_name,
                        clean_description,
                        config_json,
                        str(username or ""),
                        now,
                        now,
                    ),
                )
                record_id = int(cursor.lastrowid)
                cursor.execute(
                    """
                    INSERT INTO reconciliation_definition_versions (
                        definition_id, version_number, name_snapshot,
                        description_snapshot, config_json, status,
                        created_by, created_at, change_note
                    )
                    VALUES (?, 1, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                    """,
                    (
                        record_id,
                        clean_name,
                        clean_description,
                        config_json,
                        str(username or ""),
                        now,
                        clean_note or "Создан шаблон",
                    ),
                )
                version_id = int(cursor.lastrowid)
                cursor.execute(
                    """
                    UPDATE reconciliation_definitions
                    SET active_version_id = ?, current_version_number = 1
                    WHERE id = ?
                    """,
                    (version_id, record_id),
                )
                message = f"Шаблон «{clean_name}» сохранён как v1."
            else:
                current = cursor.execute(
                    """
                    SELECT id, active_version_id, current_version_number
                    FROM reconciliation_definitions
                    WHERE id = ?
                    """,
                    (int(definition_id),),
                ).fetchone()
                if current is None:
                    conn.rollback()
                    return False, "Шаблон не найден", None

                record_id = int(definition_id)
                previous_version_id = (
                    int(current["active_version_id"])
                    if current["active_version_id"] is not None
                    else None
                )
                next_number = int(current["current_version_number"] or 0) + 1

                cursor.execute(
                    """
                    UPDATE reconciliation_definition_versions
                    SET status = 'ARCHIVED'
                    WHERE definition_id = ? AND status = 'ACTIVE'
                    """,
                    (record_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO reconciliation_definition_versions (
                        definition_id, version_number, name_snapshot,
                        description_snapshot, config_json, status,
                        created_by, created_at, change_note, based_on_version_id
                    )
                    VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        next_number,
                        clean_name,
                        clean_description,
                        config_json,
                        str(username or ""),
                        now,
                        clean_note or f"Обновление до v{next_number}",
                        previous_version_id,
                    ),
                )
                version_id = int(cursor.lastrowid)

                cursor.execute(
                    """
                    UPDATE reconciliation_definitions
                    SET name = ?, description = ?, config_json = ?,
                        updated_at = ?, is_active = 1,
                        active_version_id = ?, current_version_number = ?
                    WHERE id = ?
                    """,
                    (
                        clean_name,
                        clean_description,
                        config_json,
                        now,
                        version_id,
                        next_number,
                        record_id,
                    ),
                )
                message = f"Создана версия v{next_number} шаблона «{clean_name}»."

            conn.commit()
            return True, message, record_id
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, f"Шаблон с названием «{clean_name}» уже существует", None
        except Exception as exc:
            conn.rollback()
            return False, f"Не удалось сохранить версию шаблона: {exc}", None


def restore_definition_version(
    *,
    definition_id: int,
    version_id: int,
    username: str,
    change_note: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    now = _now()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN")
            definition = cursor.execute(
                """
                SELECT id, active_version_id, current_version_number
                FROM reconciliation_definitions
                WHERE id = ? AND is_active = 1
                """,
                (int(definition_id),),
            ).fetchone()
            if definition is None:
                conn.rollback()
                return False, "Шаблон не найден", None

            source = cursor.execute(
                """
                SELECT *
                FROM reconciliation_definition_versions
                WHERE id = ? AND definition_id = ?
                """,
                (int(version_id), int(definition_id)),
            ).fetchone()
            if source is None:
                conn.rollback()
                return False, "Версия шаблона не найдена", None

            previous_version_id = (
                int(definition["active_version_id"])
                if definition["active_version_id"] is not None
                else None
            )
            next_number = int(definition["current_version_number"] or 0) + 1

            cursor.execute(
                """
                UPDATE reconciliation_definition_versions
                SET status = 'ARCHIVED'
                WHERE definition_id = ? AND status = 'ACTIVE'
                """,
                (int(definition_id),),
            )

            cursor.execute(
                """
                INSERT INTO reconciliation_definition_versions (
                    definition_id, version_number, name_snapshot,
                    description_snapshot, config_json, status,
                    created_by, created_at, change_note,
                    based_on_version_id, restored_from_version_id
                )
                VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?)
                """,
                (
                    int(definition_id),
                    next_number,
                    source["name_snapshot"],
                    source["description_snapshot"] or "",
                    source["config_json"] or "{}",
                    str(username or ""),
                    now,
                    str(change_note or "").strip()
                    or f"Восстановлено из v{int(source['version_number'])}",
                    previous_version_id,
                    int(source["id"]),
                ),
            )
            new_version_id = int(cursor.lastrowid)

            cursor.execute(
                """
                UPDATE reconciliation_definitions
                SET name = ?, description = ?, config_json = ?,
                    updated_at = ?, active_version_id = ?,
                    current_version_number = ?, is_active = 1
                WHERE id = ?
                """,
                (
                    source["name_snapshot"],
                    source["description_snapshot"] or "",
                    source["config_json"] or "{}",
                    now,
                    new_version_id,
                    next_number,
                    int(definition_id),
                ),
            )

            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            return False, "Не удалось восстановить версию: имя шаблона конфликтует", None
        except Exception as exc:
            conn.rollback()
            return False, f"Не удалось восстановить версию: {exc}", None

    item = get_definition(int(definition_id))
    return (
        True,
        f"Создана v{next_number} на основе v{int(source['version_number'])}.",
        item,
    )


def deactivate_definition(definition_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE reconciliation_definitions
            SET is_active = 0, updated_at = ?
            WHERE id = ? AND is_active = 1
            """,
            (_now(), int(definition_id)),
        )
        conn.commit()
        return cursor.rowcount > 0
