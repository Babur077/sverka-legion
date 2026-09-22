from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import utils.db_manager as db


def _json(value: Any, fallback: Any) -> str:
    if value is None:
        value = fallback
    return json.dumps(value, ensure_ascii=False, default=str)


def cache_run_result(
    module_id: str,
    run_id: str,
    username: str,
    result_payload: dict[str, Any],
    *,
    params: dict[str, Any] | None = None,
    source_files: list[str] | None = None,
) -> None:
    now = datetime.now().isoformat()
    with sqlite3.connect(db.DB_PATH) as conn:
        existing = conn.execute(
            """
            SELECT id, created_by, created_at
            FROM reconciliation_run_results
            WHERE module_id = ? AND run_id = ?
            """,
            (str(module_id), str(run_id)),
        ).fetchone()

        if existing:
            if str(existing[1] or "") != str(username or ""):
                raise PermissionError("run_id уже принадлежит другому пользователю")
            conn.execute(
                """
                UPDATE reconciliation_run_results
                SET updated_at = ?, result_json = ?, params_json = ?, source_files_json = ?
                WHERE id = ?
                """,
                (
                    now,
                    _json(result_payload, {}),
                    _json(params, {}),
                    _json(source_files, []),
                    int(existing[0]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO reconciliation_run_results (
                    module_id, run_id, created_by, created_at, updated_at,
                    result_json, params_json, source_files_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(module_id),
                    str(run_id),
                    str(username or ""),
                    now,
                    now,
                    _json(result_payload, {}),
                    _json(params, {}),
                    _json(source_files, []),
                ),
            )
        conn.commit()


def get_run_result(
    module_id: str,
    run_id: str,
    username: str,
    *,
    allow_owner_override: bool = False,
) -> dict[str, Any] | None:
    query = """
        SELECT module_id, run_id, created_by, created_at, updated_at,
               result_json, params_json, source_files_json
        FROM reconciliation_run_results
        WHERE module_id = ? AND run_id = ?
    """
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(query, (str(module_id), str(run_id))).fetchone()

    if not row:
        return None

    raw = dict(row)
    if (
        str(raw.get("created_by") or "") != str(username or "")
        and not allow_owner_override
    ):
        return None

    def decode(name: str, fallback: Any) -> Any:
        try:
            return json.loads(raw.get(name) or json.dumps(fallback))
        except (TypeError, json.JSONDecodeError):
            return fallback

    return {
        "module_id": raw["module_id"],
        "run_id": raw["run_id"],
        "created_by": raw["created_by"],
        "created_at": raw["created_at"],
        "updated_at": raw["updated_at"],
        "result": decode("result_json", {}),
        "params": decode("params_json", {}),
        "source_files": decode("source_files_json", []),
    }
