from __future__ import annotations

import sqlite3

VERSION = 6
NAME = "reconciliation_jobs"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'QUEUED',
            progress INTEGER NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'В очереди',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            run_id TEXT,
            error TEXT,
            cancel_requested BOOLEAN NOT NULL DEFAULT 0,
            request_json TEXT NOT NULL DEFAULT '{}',
            files_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_jobs_status "
        "ON reconciliation_jobs(status, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_jobs_user "
        "ON reconciliation_jobs(created_by, created_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reconciliation_jobs_module "
        "ON reconciliation_jobs(module_id, created_at)"
    )
