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
