import sqlite3

from backend.db.migrations.runner import get_applied_migrations, run_migrations


def test_migrations_apply_in_order_and_only_once(tmp_path):
    db_path = tmp_path / "reconcile_hub.db"

    applied = run_migrations(str(db_path))
    assert applied == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]

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
        "reconciliation_definition_versions",
        "reconciliation_run_results",
        "reconciliation_row_reviews",
        "test_vorona_import_batches",
        "test_vorona_records",
    }.issubset(tables)

    with sqlite3.connect(db_path) as conn:
        review_columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(reconciliation_row_reviews)"
            ).fetchall()
        }
    assert {"smart_match_decision", "smart_match_candidate"}.issubset(review_columns)

    assert run_migrations(str(db_path)) == []
    assert [item["version"] for item in get_applied_migrations(str(db_path))] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]


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



def test_template_versioning_migration_backfills_existing_definition(tmp_path):
    db_path = tmp_path / "definitions_legacy.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE reconciliation_definitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            INSERT INTO reconciliation_definitions (
                name, description, config_json, created_by,
                created_at, updated_at, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "Legacy template",
                "Before versions",
                '{"amount_tolerance": 100}',
                "tester",
                "2026-09-01T10:00:00",
                "2026-09-01T10:00:00",
            ),
        )
        conn.commit()

    run_migrations(str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        definition = conn.execute(
            """
            SELECT active_version_id, current_version_number
            FROM reconciliation_definitions
            WHERE name = 'Legacy template'
            """
        ).fetchone()
        version = conn.execute(
            """
            SELECT version_number, status, name_snapshot, config_json
            FROM reconciliation_definition_versions
            WHERE definition_id = 1
            """
        ).fetchone()

    assert definition["active_version_id"] is not None
    assert definition["current_version_number"] == 1
    assert version["version_number"] == 1
    assert version["status"] == "ACTIVE"
    assert version["name_snapshot"] == "Legacy template"
    assert '"amount_tolerance": 100' in version["config_json"]
