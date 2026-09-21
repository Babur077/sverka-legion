from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

import utils.db_manager as db


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}


def _now() -> str:
    return datetime.now().isoformat()


def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for field in ("request_json", "files_json"):
        try:
            item[field[:-5] if field.endswith("_json") else field] = json.loads(item.get(field) or "{}")
        except (TypeError, json.JSONDecodeError):
            item[field[:-5] if field.endswith("_json") else field] = {}
        item.pop(field, None)
    item["cancel_requested"] = bool(item.get("cancel_requested"))
    return item


def create_job(
    module_id: str,
    username: str,
    request_payload: dict[str, Any],
    status: str = "QUEUED",
) -> int:
    now = _now()
    normalized_status = str(status or "QUEUED").upper()
    stage = "Подготовка загрузки" if normalized_status == "STAGING" else "В очереди"
    with sqlite3.connect(db.DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO reconciliation_jobs (
                module_id, status, progress, stage, created_by,
                created_at, updated_at, request_json, files_json
            )
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, '{}')
            """,
            (
                module_id,
                normalized_status,
                stage,
                username,
                now,
                now,
                json.dumps(request_payload or {}, ensure_ascii=False, default=str),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def queue_job(job_id: int) -> None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'QUEUED',
                progress = 0,
                stage = 'В очереди',
                updated_at = ?
            WHERE id = ? AND status = 'STAGING'
            """,
            (_now(), int(job_id)),
        )
        conn.commit()


def set_job_request(job_id: int, request_payload: dict[str, Any]) -> None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            "UPDATE reconciliation_jobs SET request_json = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(request_payload or {}, ensure_ascii=False, default=str),
                _now(),
                int(job_id),
            ),
        )
        conn.commit()


def set_job_files(job_id: int, files_payload: dict[str, Any]) -> None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            "UPDATE reconciliation_jobs SET files_json = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(files_payload or {}, ensure_ascii=False, default=str),
                _now(),
                int(job_id),
            ),
        )
        conn.commit()


def get_job(job_id: int) -> dict[str, Any] | None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM reconciliation_jobs WHERE id = ?",
            (int(job_id),),
        ).fetchone()
    return _decode(row)


def list_jobs(
    username: str,
    module_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses = ["created_by = ?"]
    params: list[Any] = [username]
    if module_id:
        clauses.append("module_id = ?")
        params.append(module_id)
    params.append(max(1, min(int(limit), 100)))

    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM reconciliation_jobs
            WHERE {' AND '.join(clauses)}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_decode(row) or {} for row in rows]


def recover_interrupted_jobs() -> None:
    now = _now()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'QUEUED',
                progress = 0,
                stage = 'Возобновление после перезапуска',
                started_at = NULL,
                updated_at = ?
            WHERE status = 'RUNNING' AND cancel_requested = 0
            """,
            (now,),
        )
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'CANCELLED',
                progress = 0,
                stage = 'Отменено',
                finished_at = ?,
                updated_at = ?
            WHERE status IN ('QUEUED', 'RUNNING') AND cancel_requested = 1
            """,
            (now, now),
        )
        conn.commit()


def claim_next_job() -> dict[str, Any] | None:
    """Claim one queued job globally.

    BEGIN IMMEDIATE serializes competing worker processes. We intentionally allow
    at most one RUNNING job in the SQLite MVP to protect memory on large files.
    """
    with sqlite3.connect(db.DB_PATH, timeout=30) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")

        running = conn.execute(
            "SELECT 1 FROM reconciliation_jobs WHERE status = 'RUNNING' LIMIT 1"
        ).fetchone()
        if running:
            conn.rollback()
            return None

        row = conn.execute(
            """
            SELECT * FROM reconciliation_jobs
            WHERE status = 'QUEUED' AND cancel_requested = 0
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            conn.rollback()
            return None

        now = _now()
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'RUNNING',
                progress = 5,
                stage = 'Подготовка',
                started_at = COALESCE(started_at, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, int(row["id"])),
        )
        conn.commit()

    return get_job(int(row["id"]))


def update_job_progress(job_id: int, progress: int, stage: str) -> None:
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET progress = ?, stage = ?, updated_at = ?
            WHERE id = ? AND status = 'RUNNING'
            """,
            (
                max(0, min(int(progress), 99)),
                str(stage or ""),
                _now(),
                int(job_id),
            ),
        )
        conn.commit()


def is_cancel_requested(job_id: int) -> bool:
    with sqlite3.connect(db.DB_PATH) as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM reconciliation_jobs WHERE id = ?",
            (int(job_id),),
        ).fetchone()
    return bool(row and row[0])


def request_cancel(job_id: int, username: str) -> tuple[bool, str]:
    now = _now()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, created_by FROM reconciliation_jobs WHERE id = ?",
            (int(job_id),),
        ).fetchone()
        if not row or str(row["created_by"]) != username:
            return False, "Задача не найдена"

        status = str(row["status"])
        if status in TERMINAL_STATUSES:
            return False, f"Задача уже завершена со статусом {status}"

        if status == "QUEUED":
            conn.execute(
                """
                UPDATE reconciliation_jobs
                SET status = 'CANCELLED',
                    cancel_requested = 1,
                    stage = 'Отменено',
                    finished_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, int(job_id)),
            )
            conn.commit()
            return True, "Задача отменена"

        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET cancel_requested = 1,
                stage = 'Отмена запрошена',
                updated_at = ?
            WHERE id = ?
            """,
            (now, int(job_id)),
        )
        conn.commit()
        return True, "Отмена запрошена"


def complete_job(job_id: int, run_id: str) -> None:
    now = _now()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'COMPLETED',
                progress = 100,
                stage = 'Готово',
                run_id = ?,
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (run_id, now, now, int(job_id)),
        )
        conn.commit()


def fail_job(job_id: int, error: str) -> None:
    now = _now()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'FAILED',
                stage = 'Ошибка',
                error = ?,
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (str(error or "")[:4000], now, now, int(job_id)),
        )
        conn.commit()


def cancel_running_job(job_id: int) -> None:
    now = _now()
    with sqlite3.connect(db.DB_PATH) as conn:
        conn.execute(
            """
            UPDATE reconciliation_jobs
            SET status = 'CANCELLED',
                stage = 'Отменено',
                finished_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, int(job_id)),
        )
        conn.commit()
