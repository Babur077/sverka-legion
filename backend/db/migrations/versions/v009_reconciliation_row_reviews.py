from __future__ import annotations

import sqlite3

VERSION = 9
NAME = "reconciliation_row_reviews"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_row_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            row_key TEXT NOT NULL,
            comment TEXT NOT NULL DEFAULT '',
            is_reviewed BOOLEAN NOT NULL DEFAULT 0,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_by TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(module_id, run_id, row_key)
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_reconciliation_row_reviews_run
        ON reconciliation_row_reviews(module_id, run_id, updated_at)
        """
    )
