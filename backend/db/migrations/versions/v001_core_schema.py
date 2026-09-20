from __future__ import annotations

import sqlite3

VERSION = 1
NAME = "core_schema"


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    name: str,
    definition: str,
) -> None:
    if name not in _column_names(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def upgrade(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS epos_registry (
            terminal_id TEXT PRIMARY KEY,
            merchant_id TEXT,
            bank_acquirer TEXT,
            legal_entity TEXT,
            commission_pct REAL DEFAULT 0.0,
            is_active BOOLEAN DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    # Legacy Bank RRN archive is retained temporarily as a migration source.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            username TEXT,
            bank_name TEXT,
            total_our REAL,
            total_bank REAL,
            difference REAL,
            matched_count INTEGER,
            mismatch_count INTEGER,
            only_our_count INTEGER,
            only_bank_count INTEGER,
            period_month TEXT,
            total_commission REAL DEFAULT 0.0,
            terminals_json TEXT,
            run_id TEXT,
            source_our_name TEXT,
            source_bank_name TEXT,
            config_json TEXT,
            assigned_terminal_id TEXT
        )
        """
    )

    for name, definition in [
        ("period_month", "TEXT"),
        ("total_commission", "REAL DEFAULT 0.0"),
        ("terminals_json", "TEXT"),
        ("run_id", "TEXT"),
        ("source_our_name", "TEXT"),
        ("source_bank_name", "TEXT"),
        ("config_json", "TEXT"),
        ("assigned_terminal_id", "TEXT"),
    ]:
        _add_column_if_missing(conn, "reconciliation_archive", name, definition)
