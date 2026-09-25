from __future__ import annotations

import sqlite3

VERSION = 11
NAME = "test_vorona_persistent_data"


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS test_vorona_import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            period_key TEXT NOT NULL,
            year INTEGER,
            month INTEGER,
            filename TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            rows_count INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            uploaded_by TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            replaced_by_batch_id INTEGER,
            FOREIGN KEY(replaced_by_batch_id)
                REFERENCES test_vorona_import_batches(id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_test_vorona_batch_file
        ON test_vorona_import_batches(source_type, period_key, file_hash)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_test_vorona_active_period
        ON test_vorona_import_batches(source_type, period_key)
        WHERE is_active = 1
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_test_vorona_batches_period
        ON test_vorona_import_batches(year, month, source_type, is_active)
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS test_vorona_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            row_index INTEGER NOT NULL,
            operation_date TEXT,
            year INTEGER,
            month INTEGER,
            inn TEXT,
            vid TEXT,
            partner TEXT,
            amount REAL NOT NULL DEFAULT 0,
            commission REAL NOT NULL DEFAULT 0,
            status TEXT,
            service TEXT,
            side TEXT,
            raw_json TEXT NOT NULL DEFAULT '{}',
            row_hash TEXT NOT NULL,
            FOREIGN KEY(batch_id)
                REFERENCES test_vorona_import_batches(id)
                ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_test_vorona_records_batch
        ON test_vorona_records(batch_id, row_index)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_test_vorona_records_partner
        ON test_vorona_records(source_type, year, month, vid, inn)
        """
    )
