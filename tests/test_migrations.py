import sqlite3

from backend.db.migrations.runner import get_applied_migrations, run_migrations


def test_migrations_apply_in_order_and_only_once(tmp_path):
    db_path = tmp_path / "reconcile_hub.db"

    applied = run_migrations(str(db_path))
    assert applied == [1, 2, 3, 4, 5, 6]

    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert {
        "schema_migrations",
        "users",
        "epos_registry",
        "app_settings",
        "reconciliation_archive",
        "audit_events",
        "auth_sessions",
        "reconciliation_runs",
        "reconciliation_definitions",
        "reconciliation_jobs",
    }.issubset(tables)

    assert run_migrations(str(db_path)) == []
    assert [item["version"] for item in get_applied_migrations(str(db_path))] == [1, 2, 3, 4, 5, 6]


def test_migrations_upgrade_existing_minimal_database(tmp_path):
    db_path = tmp_path / "legacy.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE reconciliation_archive (
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
                only_bank_count INTEGER
            )
            """
        )
        conn.commit()

    run_migrations(str(db_path))

    with sqlite3.connect(db_path) as conn:
        user_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        archive_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(reconciliation_archive)"
            ).fetchall()
        }

    assert "permissions" in user_columns
    assert "assigned_terminal_id" in archive_columns
    assert "period_month" in archive_columns
