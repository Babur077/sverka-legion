from __future__ import annotations

import sqlite3
from datetime import datetime

VERSION = 7
NAME = "reconciliation_definition_versions"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def upgrade(conn: sqlite3.Connection) -> None:
    columns = _columns(conn, "reconciliation_definitions")
    if "active_version_id" not in columns:
        conn.execute(
            "ALTER TABLE reconciliation_definitions ADD COLUMN active_version_id INTEGER"
        )
    if "current_version_number" not in columns:
        conn.execute(
            "ALTER TABLE reconciliation_definitions "
            "ADD COLUMN current_version_number INTEGER NOT NULL DEFAULT 0"
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reconciliation_definition_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            definition_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            name_snapshot TEXT NOT NULL,
            description_snapshot TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'ARCHIVED',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            change_note TEXT NOT NULL DEFAULT '',
            based_on_version_id INTEGER,
            restored_from_version_id INTEGER,
            FOREIGN KEY(definition_id) REFERENCES reconciliation_definitions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_definition_versions_number
        ON reconciliation_definition_versions(definition_id, version_number)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_definition_versions_definition
        ON reconciliation_definition_versions(definition_id, created_at DESC)
        """
    )

    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, name, description, config_json, created_by, created_at,
               active_version_id, current_version_number
        FROM reconciliation_definitions
        ORDER BY id
        """
    ).fetchall()

    for row in rows:
        definition_id = int(row["id"])
        existing = conn.execute(
            """
            SELECT id, version_number
            FROM reconciliation_definition_versions
            WHERE definition_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (definition_id,),
        ).fetchone()

        if existing is None:
            created_at = row["created_at"] or datetime.now().isoformat()
            cursor = conn.execute(
                """
                INSERT INTO reconciliation_definition_versions (
                    definition_id, version_number, name_snapshot,
                    description_snapshot, config_json, status,
                    created_by, created_at, change_note
                )
                VALUES (?, 1, ?, ?, ?, 'ACTIVE', ?, ?, ?)
                """,
                (
                    definition_id,
                    row["name"],
                    row["description"] or "",
                    row["config_json"] or "{}",
                    row["created_by"] or "",
                    created_at,
                    "Исходная версия до включения версионности",
                ),
            )
            version_id = int(cursor.lastrowid)
            conn.execute(
                """
                UPDATE reconciliation_definitions
                SET active_version_id = ?, current_version_number = 1
                WHERE id = ?
                """,
                (version_id, definition_id),
            )
        elif not row["active_version_id"] or int(row["current_version_number"] or 0) <= 0:
            conn.execute(
                """
                UPDATE reconciliation_definition_versions
                SET status = 'ARCHIVED'
                WHERE definition_id = ?
                """,
                (definition_id,),
            )
            conn.execute(
                """
                UPDATE reconciliation_definition_versions
                SET status = 'ACTIVE'
                WHERE id = ?
                """,
                (int(existing["id"]),),
            )
            conn.execute(
                """
                UPDATE reconciliation_definitions
                SET active_version_id = ?, current_version_number = ?
                WHERE id = ?
                """,
                (
                    int(existing["id"]),
                    int(existing["version_number"]),
                    definition_id,
                ),
            )

    conn.row_factory = None
