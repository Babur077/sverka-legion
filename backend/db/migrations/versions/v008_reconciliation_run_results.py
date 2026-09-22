from __future__ import annotations

import sqlite3

VERSION = 8
NAME = "reconciliation_run_results"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_run_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            result_json TEXT NOT NULL,
            params_json TEXT NOT NULL DEFAULT '{}',
            source_files_json TEXT NOT NULL DEFAULT '[]',
            UNIQUE(module_id, run_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_results_owner "
        "ON reconciliation_run_results(created_by, updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_run_results_module "
        "ON reconciliation_run_results(module_id, updated_at)"
    )
