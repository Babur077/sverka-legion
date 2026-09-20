from __future__ import annotations

import sqlite3

VERSION = 2
NAME = "rbac_and_audit"


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def upgrade(conn: sqlite3.Connection) -> None:
    if "permissions" not in _column_names(conn, "users"):
        conn.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT ''")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            module_id TEXT,
            object_type TEXT,
            object_id TEXT,
            status TEXT DEFAULT 'SUCCESS',
            ip_address TEXT,
            duration_ms REAL,
            details TEXT
        )
        """
    )

    conn.execute(
        "UPDATE users SET role = ? WHERE role = ?",
        ("accountant_acquiring", "accountant"),
    )
