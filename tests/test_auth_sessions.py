import sqlite3

import utils.auth_sessions as auth_sessions


def _create_users_table(db_path):
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
            ("alice", "hash", "auditor"),
        )
        conn.commit()


def test_session_round_trip_and_revoke(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    monkeypatch.setattr(auth_sessions, "DB_PATH", str(db_path))
    _create_users_table(db_path)
    auth_sessions.init_auth_sessions_db()

    token, expires_at = auth_sessions.create_session("alice")

    assert token
    assert expires_at
    assert auth_sessions.get_session_user(token) == "alice"

    auth_sessions.revoke_session(token)

    assert auth_sessions.get_session_user(token) is None


def test_session_token_is_not_stored_in_plaintext(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    monkeypatch.setattr(auth_sessions, "DB_PATH", str(db_path))
    _create_users_table(db_path)
    auth_sessions.init_auth_sessions_db()

    token, _ = auth_sessions.create_session("alice")

    with sqlite3.connect(db_path) as conn:
        stored = conn.execute("SELECT token_hash FROM auth_sessions").fetchone()[0]

    assert stored != token
    assert len(stored) == 64


def test_expired_session_is_rejected(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    monkeypatch.setattr(auth_sessions, "DB_PATH", str(db_path))
    _create_users_table(db_path)
    auth_sessions.init_auth_sessions_db()

    token, _ = auth_sessions.create_session("alice")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE auth_sessions SET expires_at = ?",
            ("2000-01-01T00:00:00+00:00",),
        )
        conn.commit()

    assert auth_sessions.get_session_user(token) is None


def test_session_is_invalid_after_user_is_deleted(tmp_path, monkeypatch):
    db_path = tmp_path / "sessions.db"
    monkeypatch.setattr(auth_sessions, "DB_PATH", str(db_path))
    _create_users_table(db_path)
    auth_sessions.init_auth_sessions_db()

    token, _ = auth_sessions.create_session("alice")
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM users WHERE username = ?", ("alice",))
        conn.commit()

    assert auth_sessions.get_session_user(token) is None
