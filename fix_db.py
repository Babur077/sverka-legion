import os
import sqlite3

from utils.db_manager import DB_PATH, hash_password


def force_create_admin():
    """Аварийный сброс пароля администратора.

    ИСПРАВЛЕНО: раньше скрипт запускался без каких-либо подтверждений и
    молча пересоздавал admin/admin123 — случайный `python fix_db.py` на
    проде мог тихо сбросить пароль администратора. Теперь требуется явное
    подтверждение через переменную окружения.
    """
    if os.environ.get("ALLOW_ADMIN_RESET") != "1":
        print(
            "⛔ Отказано. Это аварийный сброс пароля администратора.\n"
            "   Если вы точно этого хотите, запустите:\n"
            "   ALLOW_ADMIN_RESET=1 python fix_db.py"
        )
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')

        admin_hash = hash_password("admin123")

        cursor.execute("DELETE FROM users WHERE username = 'admin'")
        cursor.execute('''
            INSERT INTO users (username, password_hash, role)
            VALUES (?, ?, ?)
        ''', ("admin", admin_hash, "admin"))

        conn.commit()

        cursor.execute("SELECT id, username, role FROM users")
        print("✅ Успешно! Пользователи в базе:", cursor.fetchall())
        print("⚠️  Смените пароль admin123 сразу после входа в систему.")


if __name__ == "__main__":
    force_create_admin()
