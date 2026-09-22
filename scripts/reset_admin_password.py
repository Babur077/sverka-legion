from __future__ import annotations

import sqlite3
import sys
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.auth_sessions import revoke_user_sessions
from utils.db_manager import DB_PATH, hash_password, init_db


def main() -> int:
    print("ReconcileHub admin password reset")
    print(f"Database: {DB_PATH}")
    print()

    init_db()

    password = getpass("Новый пароль admin: ")
    if len(password) < 8:
        print("Ошибка: пароль должен содержать минимум 8 символов.")
        return 1

    confirmation = getpass("Повторите новый пароль: ")
    if password != confirmation:
        print("Ошибка: пароли не совпадают.")
        return 1

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ?, role = 'admin' WHERE username = 'admin'",
            (hash_password(password),),
        )
        if cursor.rowcount == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", hash_password(password), "admin"),
            )
        conn.commit()

    revoke_user_sessions("admin")
    print()
    print("Пароль admin обновлён. Все старые admin-сессии завершены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
