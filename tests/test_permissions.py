import json
import sqlite3

import utils.permissions as permissions


def test_legacy_permission_list_is_treated_as_additive():
    effective = permissions.resolve_permissions(
        "auditor",
        json.dumps(["bank_rrn.run"]),
    )

    assert "bank_rrn.view" in effective
    assert "bank_rrn.run" in effective
    assert "audit.view" in effective


def test_allow_and_deny_override_role_template():
    effective = permissions.resolve_permissions(
        "accountant_acquiring",
        {
            "allow": ["audit.view"],
            "deny": ["bank_rrn.run", "epos.view"],
        },
    )

    assert "bank_rrn.view" in effective
    assert "bank_rrn.export" in effective
    assert "audit.view" in effective
    assert "bank_rrn.run" not in effective
    assert "epos.view" not in effective


def test_admin_role_always_resolves_to_full_access():
    effective = permissions.resolve_permissions(
        "admin",
        {"deny": ["bank_rrn.run"], "allow": []},
    )

    assert effective == ["*"]


def test_update_user_access_persists_overrides(tmp_path, monkeypatch):
    db_path = tmp_path / "access.db"
    monkeypatch.setattr(permissions, "DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role, permissions) VALUES (?, ?, ?, ?)",
            ("worker", "hash", "accountant_acquiring", ""),
        )
        conn.commit()

    ok, message, access = permissions.update_user_access(
        user_id=1,
        role="auditor",
        allow=["bank_rrn.run"],
        deny=["audit.view"],
    )

    assert ok is True
    assert "обновлён" in message
    assert access is not None
    assert access["role"] == "auditor"
    assert access["permission_overrides"] == {
        "allow": ["bank_rrn.run"],
        "deny": ["audit.view"],
    }
    assert "bank_rrn.run" in access["permissions"]
    assert "audit.view" not in access["permissions"]


def test_root_admin_access_cannot_be_restricted(tmp_path, monkeypatch):
    db_path = tmp_path / "access.db"
    monkeypatch.setattr(permissions, "DB_PATH", str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                permissions TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role, permissions) VALUES (?, ?, ?, ?)",
            ("admin", "hash", "admin", ""),
        )
        conn.commit()

    ok, message, access = permissions.update_user_access(
        user_id=1,
        role="auditor",
        allow=[],
        deny=[],
    )

    assert ok is False
    assert "полный доступ" in message
    assert access is None



def _create_audit_table(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE audit_events (
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
        conn.executemany(
            """
            INSERT INTO audit_events
            (timestamp, user_id, action, module_id, object_type, object_id, status, ip_address, duration_ms, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2026-09-17T10:00:00", "alice", "RECONCILIATION_RUN", "bank_rrn", "RunResult", "run-a", "SUCCESS", "10.0.0.1", 120.0, "first run"),
                ("2026-09-18T11:00:00", "bob", "UPDATE_USER_ACCESS", None, "User", "7", "SUCCESS", "10.0.0.2", 0.0, "changed access"),
                ("2026-09-18T12:00:00", "alice", "RECONCILIATION_RUN_FAILED", "bank_rrn", None, None, "FAILED", "10.0.0.1", 80.0, "broken file"),
            ],
        )
        conn.commit()


def test_query_audit_events_supports_date_status_and_search_filters(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(permissions, "DB_PATH", str(db_path))
    _create_audit_table(db_path)

    result = permissions.query_audit_events(
        status="FAILED",
        date_from="2026-09-18T00:00:00",
        date_to="2026-09-19T00:00:00",
        search="broken",
    )

    assert result["total"] == 1
    assert result["items"][0]["action"] == "RECONCILIATION_RUN_FAILED"
    assert result["items"][0]["user_id"] == "alice"


def test_audit_filter_options_are_global_not_page_dependent(tmp_path, monkeypatch):
    db_path = tmp_path / "audit.db"
    monkeypatch.setattr(permissions, "DB_PATH", str(db_path))
    _create_audit_table(db_path)

    options = permissions.get_audit_filter_options()

    assert options["users"] == ["alice", "bob"]
    assert options["actions"] == [
        "RECONCILIATION_RUN",
        "RECONCILIATION_RUN_FAILED",
        "UPDATE_USER_ACCESS",
    ]
    assert options["modules"] == ["bank_rrn"]
    assert options["statuses"] == ["FAILED", "SUCCESS"]
