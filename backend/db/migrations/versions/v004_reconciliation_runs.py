from __future__ import annotations

import json
import sqlite3
from datetime import datetime

VERSION = 4
NAME = "generic_reconciliation_runs"


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id TEXT NOT NULL,
            run_id TEXT,
            status TEXT NOT NULL DEFAULT 'COMPLETED',
            period_month TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            created_by TEXT NOT NULL,
            source_files_json TEXT NOT NULL DEFAULT '[]',
            summary_json TEXT NOT NULL DEFAULT '{}',
            payload_json TEXT NOT NULL DEFAULT '{}',
            review_status TEXT NOT NULL DEFAULT 'OPEN',
            legacy_id INTEGER
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_module_period "
        "ON reconciliation_runs(module_id, period_month)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_runs_created_at "
        "ON reconciliation_runs(created_at)"
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reconciliation_runs_module_run
        ON reconciliation_runs(module_id, run_id)
        WHERE run_id IS NOT NULL AND run_id <> ''
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reconciliation_runs_legacy
        ON reconciliation_runs(module_id, legacy_id)
        WHERE legacy_id IS NOT NULL
        """
    )

    if not _table_exists(conn, "reconciliation_archive"):
        return

    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM reconciliation_archive ORDER BY id").fetchall()

    for row in rows:
        record = dict(row)
        try:
            terminals = json.loads(record.get("terminals_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            terminals = []
        try:
            config = json.loads(record.get("config_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            config = {}

        payload = {
            "bank_name": record.get("bank_name") or "Не указан",
            "total_our": float(record.get("total_our") or 0),
            "total_bank": float(record.get("total_bank") or 0),
            "difference": float(record.get("difference") or 0),
            "matched_count": int(record.get("matched_count") or 0),
            "mismatch_count": int(record.get("mismatch_count") or 0),
            "only_our_count": int(record.get("only_our_count") or 0),
            "only_bank_count": int(record.get("only_bank_count") or 0),
            "period_month": record.get("period_month"),
            "total_commission": float(record.get("total_commission") or 0),
            "terminals_summary": terminals,
            "run_id": record.get("run_id"),
            "source_our_name": record.get("source_our_name") or "",
            "source_bank_name": record.get("source_bank_name") or "",
            "config": config,
            "assigned_terminal_id": record.get("assigned_terminal_id"),
        }
        source_files = [
            value
            for value in [
                record.get("source_our_name"),
                record.get("source_bank_name"),
            ]
            if value
        ]
        summary = {
            "total_our": payload["total_our"],
            "total_bank": payload["total_bank"],
            "difference": payload["difference"],
            "matched_count": payload["matched_count"],
            "mismatch_count": payload["mismatch_count"],
            "only_our_count": payload["only_our_count"],
            "only_bank_count": payload["only_bank_count"],
        }
        timestamp = record.get("timestamp") or datetime.now().isoformat()

        conn.execute(
            """
            INSERT OR IGNORE INTO reconciliation_runs (
                module_id, run_id, status, period_month, created_at, updated_at,
                created_by, source_files_json, summary_json, payload_json,
                review_status, legacy_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "bank_rrn",
                record.get("run_id"),
                "COMPLETED",
                record.get("period_month"),
                timestamp,
                timestamp,
                record.get("username") or "",
                json.dumps(source_files, ensure_ascii=False),
                json.dumps(summary, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False, default=str),
                "OPEN",
                record.get("id"),
            ),
        )

    conn.row_factory = None
