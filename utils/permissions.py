"""
Сервис авторизации, ролей и прав доступа (RBAC) ReconcileHub.
Поддерживает детальные права на уровне конкретных модулей (bank_rrn.view, bank_rrn.run и т.д.).
"""
import sqlite3
import json
from typing import List, Dict, Any, Optional
from utils.db_manager import DB_PATH, verify_password, hash_password, log_action

# Список стандартных ролей и их дефолтные разрешения
DEFAULT_ROLE_PERMISSIONS: Dict[str, List[str]] = {
    "admin": [
        "*",  # Полный доступ ко всем модулям и настройкам
    ],
    "finance_manager": [
        "bank_rrn.view", "bank_rrn.run", "bank_rrn.export",
        "paynet.view", "paynet.run", "paynet.export",
        "epos.manage", "analytics.view_all", "audit.view", "archive.view",
    ],
    "accountant_acquiring": [
        "bank_rrn.view", "bank_rrn.run", "bank_rrn.export",
        "epos.view",
    ],
    "accountant_paynet": [
        "paynet.view", "paynet.run", "paynet.export",
    ],
    "auditor": [
        "bank_rrn.view", "paynet.view",
        "analytics.view_all", "audit.view", "archive.view",
    ],
}


def init_permissions_db():
    """Добавляет колонку permissions в таблицу users, если её еще нет."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
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
        ''')
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN permissions TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # уже добавлено
        conn.commit()


def get_user_permissions(username: str) -> List[str]:
    """Возвращает полный список эффективных разрешений пользователя."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role, permissions FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return []

        role, custom_perms_json = row
        # Базовые права из роли
        effective_perms = list(DEFAULT_ROLE_PERMISSIONS.get(role, []))

        # Если заданы кастомные права в JSON
        if custom_perms_json:
            try:
                custom = json.loads(custom_perms_json)
                if isinstance(custom, list):
                    effective_perms.extend(custom)
            except Exception:
                pass

        return list(set(effective_perms))


def has_permission(user_permissions: List[str], required_perm: str) -> bool:
    """Проверяет, есть ли у пользователя нужное право."""
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
    """Банковский аудит-лог каждого действия"""
    from datetime import datetime
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO audit_events 
            (timestamp, user_id, action, module_id, object_type, object_id, status, ip_address, duration_ms, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
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
        ))
        conn.commit()
