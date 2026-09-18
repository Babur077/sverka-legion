"""Server-side session management for ReconcileHub.

Browser clients receive an opaque bearer token after password authentication.
Only a SHA-256 digest of that token is persisted in SQLite. API requests resolve
that token back to a real user before the existing RBAC layer is evaluated.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.db_manager import DB_PATH


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _session_ttl_hours() -> int:
    raw = os.getenv("RECONCILEHUB_SESSION_TTL_HOURS", "12")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 12
    return max(1, min(value, 24 * 7))


def init_auth_sessions_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_username ON auth_sessions(username)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at)"
        )
        conn.commit()


def create_session(username: str) -> tuple[str, str]:
    """Create a new opaque bearer token and return (token, expires_at)."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=_session_ttl_hours())
    token = secrets.token_urlsafe(32)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO auth_sessions (token_hash, username, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                _token_hash(token),
                username,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()

    return token, expires_at.isoformat()


def get_session_user(token: str) -> Optional[str]:
    """Resolve a valid, non-expired token to an existing username."""
    if not token:
        return None

    now = datetime.now(timezone.utc).isoformat()
    digest = _token_hash(token)

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT s.username
            FROM auth_sessions AS s
            INNER JOIN users AS u ON u.username = s.username
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (digest, now),
        ).fetchone()

        if row:
            return str(row[0])

        conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash = ? OR expires_at <= ?",
            (digest, now),
        )
        conn.commit()

    return None


def revoke_session(token: str) -> None:
    if not token:
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
        conn.commit()


def revoke_user_sessions(username: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM auth_sessions WHERE username = ?", (username,))
        conn.commit()
