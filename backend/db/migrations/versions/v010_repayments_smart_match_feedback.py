from __future__ import annotations

import sqlite3

VERSION = 10
NAME = "repayments_smart_match_feedback"


def upgrade(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1])
        for row in conn.execute(
            "PRAGMA table_info(reconciliation_row_reviews)"
        ).fetchall()
    }

    if "smart_match_decision" not in columns:
        conn.execute(
            "ALTER TABLE reconciliation_row_reviews "
            "ADD COLUMN smart_match_decision TEXT"
        )
    if "smart_match_candidate" not in columns:
        conn.execute(
            "ALTER TABLE reconciliation_row_reviews "
            "ADD COLUMN smart_match_candidate TEXT"
        )
