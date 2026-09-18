import hashlib
import sqlite3

import pytest

import utils.db_manager as db_manager


def test_production_bootstrap_requires_explicit_password(monkeypatch):
    monkeypatch.delenv("RECONCILEHUB_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("RECONCILEHUB_ENV", "production")

    with pytest.raises(RuntimeError, match="RECONCILEHUB_ADMIN_PASSWORD"):
        db_manager._bootstrap_admin_password()


def test_configured_bootstrap_password_is_used(monkeypatch):
    monkeypatch.setenv("RECONCILEHUB_ADMIN_PASSWORD", "strong-bootstrap-secret")
    monkeypatch.setenv("RECONCILEHUB_ENV", "production")

    assert db_manager._bootstrap_admin_password() == "strong-bootstrap-secret"


def test_legacy_sha256_password_is_rehashed_after_successful_login(tmp_path, monkeypatch):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(db_manager, "DB_PATH", str(db_path))

    password = "legacy-pass"
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("legacy", legacy_hash, "auditor"),
        )
        conn.commit()

    success, role = db_manager.authenticate_user("legacy", password)

    assert success is True
    assert role == "auditor"

    with sqlite3.connect(db_path) as conn:
        upgraded_hash = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            ("legacy",),
        ).fetchone()[0]

    assert "$" in upgraded_hash
    assert upgraded_hash != legacy_hash
    assert db_manager.verify_password(password, upgraded_hash)
