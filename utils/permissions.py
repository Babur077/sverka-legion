"""
RBAC service for ReconcileHub.

Roles are permission templates. Individual users may then add or deny concrete
permissions without creating a new Python role for every reconciliation module.

The users.permissions column supports two formats:
- legacy JSON list: ["bank_rrn.view"] -> treated as additional permissions;
- current object: {"allow": [...], "deny": [...]}.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from utils.db_manager import DB_PATH


DEFAULT_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": ["*"],
    "finance_manager": [
        "bank_rrn.view",
        "bank_rrn.run",
        "bank_rrn.export",
        "epos.view",
        "epos.manage",
        "analytics.view_all",
        "audit.view",
        "archive.view",
    ],
    "accountant_acquiring": [
        "bank_rrn.view",
        "bank_rrn.run",
        "bank_rrn.export",
        "epos.view",
    ],
    "auditor": [
        "bank_rrn.view",
        "analytics.view_all",
        "audit.view",
        "archive.view",
    ],
}

VALID_ROLES = tuple(DEFAULT_ROLE_PERMISSIONS.keys())


def _unique_permissions(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen = set()
    for value in values:
        permission = str(value or "").strip()
        if permission and permission not in seen:
            seen.add(permission)
            result.append(permission)
    return result


def normalize_permission_overrides(raw: Any) -> Dict[str, List[str]]:
    """Normalize legacy/additive permissions and current allow/deny overrides."""
    if raw in (None, ""):
        return {"allow": [], "deny": []}

    value = raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"allow": [], "deny": []}

    if isinstance(value, list):
        return {"allow": _unique_permissions(value), "deny": []}

    if isinstance(value, dict):
        allow = _unique_permissions(value.get("allow"))
        deny = _unique_permissions(value.get("deny"))
        deny_set = set(deny)
        return {
            "allow": [permission for permission in allow if permission not in deny_set],
            "deny": deny,
        }

    return {"allow": [], "deny": []}


def resolve_permissions(role: str, overrides: Any = None) -> List[str]:
    """Resolve effective permissions from a role template and per-user overrides."""
    base = list(DEFAULT_ROLE_PERMISSIONS.get(role, []))
    if "*" in base:
        return ["*"]

    normalized = normalize_permission_overrides(overrides)
    denied = set(normalized["deny"])

    effective: List[str] = []
    seen = set()
    for permission in [*base, *normalized["allow"]]:
        if permission in denied or permission in seen:
            continue
        seen.add(permission)
        effective.append(permission)
    return effective


def init_permissions_db():
    """Create audit storage and migrate the optional users.permissions column."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
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
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        cursor.execute(
            "UPDATE users SET role = ? WHERE role = ?",
            ("accountant_acquiring", "accountant"),
        )
        conn.commit()


def get_user_permissions(username: str) -> List[str]:
    """Return effective permissions for one user."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, permissions FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return []
        return resolve_permissions(str(row[0] or ""), row[1])


def get_user_access(username: str) -> Optional[Dict[str, Any]]:
    """Return role, overrides and effective permissions for administration UI."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, role, permissions FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        overrides = normalize_permission_overrides(row[3])
        return {
            "id": int(row[0]),
            "username": str(row[1]),
            "role": str(row[2]),
            "permission_overrides": overrides,
            "permissions": resolve_permissions(str(row[2]), overrides),
        }


def update_user_access(
    user_id: int,
    role: str,
    allow: List[str],
    deny: List[str],
) -> tuple[bool, str, Optional[Dict[str, Any]]]:
    """Update the role template and per-user permission overrides atomically."""
    if role not in VALID_ROLES:
        return False, "Недопустимая роль пользователя", None

    normalized = normalize_permission_overrides({"allow": allow, "deny": deny})
    if role == "admin":
        normalized = {"allow": [], "deny": []}

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT username FROM users WHERE id = ?",
            (user_id,),
        )
        row = cursor.fetchone()
        if not row:
            return False, "Пользователь не найден", None

        username = str(row[0])
        if username == "admin":
            if role != "admin" or normalized["allow"] or normalized["deny"]:
                return False, "Главный пользователь admin всегда имеет полный доступ", None

        cursor.execute(
            "UPDATE users SET role = ?, permissions = ? WHERE id = ?",
            (
                role,
                json.dumps(normalized, ensure_ascii=False),
                user_id,
            ),
        )
        conn.commit()

    access = get_user_access(username)
    return True, f"Доступ пользователя '{username}' обновлён", access



def query_audit_events(
    *,
    limit: int = 100,
    offset: int = 0,
    user: Optional[str] = None,
    action: Optional[str] = None,
    module_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Return paginated audit events with server-side filters."""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    conditions: List[str] = []
    params: List[Any] = []

    if user:
        conditions.append("user_id = ?")
        params.append(user)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if module_id:
        conditions.append("module_id = ?")
        params.append(module_id)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if date_from:
        conditions.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("timestamp < ?")
        params.append(date_to)
    if search:
        conditions.append(
            "(user_id LIKE ? OR action LIKE ? OR module_id LIKE ? OR object_type LIKE ? OR object_id LIKE ? OR details LIKE ?)"
        )
        q = f"%{search}%"
        params.extend([q, q, q, q, q, q])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM audit_events {where}", params)
        total = int(cur.fetchone()[0])
        cur.execute(
            f"SELECT * FROM audit_events {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        items = [dict(row) for row in cur.fetchall()]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


def get_audit_filter_options() -> Dict[str, List[str]]:
    """Return complete distinct filter values, independent of current page."""
    def distinct_values(cursor: sqlite3.Cursor, column: str) -> List[str]:
        cursor.execute(
            f"SELECT DISTINCT {column} FROM audit_events "
            f"WHERE {column} IS NOT NULL AND TRIM({column}) != '' ORDER BY {column}"
        )
        return [str(row[0]) for row in cursor.fetchall()]

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        return {
            "users": distinct_values(cursor, "user_id"),
            "actions": distinct_values(cursor, "action"),
            "modules": distinct_values(cursor, "module_id"),
            "statuses": distinct_values(cursor, "status"),
        }

def has_permission(user_permissions: List[str], required_perm: str) -> bool:
    if "*" in user_permissions:
        return True
    return required_perm in user_permissions


def record_audit_event(
    user_id: str,
    action: str,
    module_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    status: str = "SUCCESS",
    ip_address: Optional[str] = None,
    duration_ms: Optional[float] = None,
    details: Optional[str] = None,
):
    """Write one immutable audit event."""
    from datetime import datetime

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_events
            (timestamp, user_id, action, module_id, object_type, object_id, status, ip_address, duration_ms, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                user_id,
                action,
                module_id,
                object_type,
                object_id,
                status,
                ip_address or "127.0.0.1",
                duration_ms or 0.0,
                details or "",
            ),
        )
        conn.commit()
