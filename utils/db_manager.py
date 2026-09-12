import sqlite3
import os
import hashlib
import secrets
from datetime import datetime

import pandas as pd

DB_PATH = "database/reconcile_hub.db"

# ─────────────────────────────────────────────────────────────
# Пароли: PBKDF2-HMAC-SHA256 с уникальной солью на пользователя.
# Хранится в password_hash в формате "<salt_hex>$<hash_hex>".
# verify_password() также умеет проверять СТАРЫЙ несоленый sha256-хеш,
# чтобы существующая база (созданная предыдущей версией кода) не сломалась —
# при следующем успешном входе пароль можно перехешировать в новый формат.
# ─────────────────────────────────────────────────────────────
_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, salt: str | None = None) -> str:
    """Создаёт соленый PBKDF2-HMAC-SHA256 хеш пароля.
    Возвращает строку вида '<salt_hex>$<hash_hex>'."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt),
        _PBKDF2_ITERATIONS,
    )
    return f"{salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Проверяет пароль против сохранённого значения.
    Поддерживает новый формат 'salt$hash' и старый несоленый sha256
    (для плавной миграции существующих баз без соли)."""
    if "$" in stored:
        salt, _ = stored.split("$", 1)
        return hash_password(password, salt) == stored
    # legacy: старый формат — простой sha256 без соли
    legacy_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return legacy_hash == stored


def init_db():
    """Инициализирует локальную БД и создаёт все таблицы, если их нет.
    Создаёт дефолтного администратора только если пользователей ещё нет."""
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS epos_registry (
                terminal_id TEXT PRIMARY KEY,
                merchant_id TEXT,
                bank_acquirer TEXT,
                legal_entity TEXT,
                commission_pct REAL DEFAULT 0.0,
                is_active BOOLEAN DEFAULT 1
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                username TEXT,
                action TEXT,
                details TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reconciliation_archive (
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
        ''')

        # Общесистемные настройки (единые для ВСЕХ пользователей,
        # а не только для сессии одного браузера, как было раньше).
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            admin_hash = hash_password("admin123")  # Дефолтный пароль — сменить сразу после первого входа!
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", admin_hash, "admin"),
            )

        conn.commit()


def authenticate_user(username, password):
    """Проверяет логин и пароль. Возвращает (успех, роль)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash, role FROM users WHERE username = ?", (username,))
        result = cursor.fetchone()

        if result:
            db_hash, role = result
            if verify_password(password, db_hash):
                return True, role
    return False, None


def log_action(username: str, action: str, details: str = ""):
    """Записывает критичное действие пользователя в системный лог."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (timestamp, username, action, details) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), username, action, details)
        )
        conn.commit()


def add_epos_terminal(tid, mid, bank, entity, com_pct):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO epos_registry (terminal_id, merchant_id, bank_acquirer, legal_entity, commission_pct, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (tid, mid, bank, entity, com_pct))
            conn.commit()
            return True, "Терминал успешно добавлен!"
        except sqlite3.IntegrityError:
            return False, f"Ошибка: Терминал с TID {tid} уже существует!"
        except Exception as e:
            return False, f"Системная ошибка: {e}"


def get_epos_registry() -> pd.DataFrame:
    """Возвращает весь реестр в виде DataFrame для удобного отображения."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM epos_registry", conn)


def add_user(username, password, role):
    """Добавляет нового пользователя в базу."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, hash_password(password), role)
            )
            conn.commit()
            return True, "Пользователь успешно добавлен!"
        except sqlite3.IntegrityError:
            return False, f"Пользователь с логином '{username}' уже существует!"
        except Exception as e:
            return False, f"Системная ошибка: {e}"


def get_all_users() -> pd.DataFrame:
    """Возвращает список всех пользователей (без паролей)."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT id, username, role FROM users", conn)


def get_audit_logs(limit=100) -> pd.DataFrame:
    """Возвращает последние записи из журнала действий."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT timestamp, username, action, details FROM audit_logs ORDER BY id DESC LIMIT ?",
            conn, params=(limit,)
        )


def save_reconciliation(user, bank_name, tot_our, tot_bank, diff, matched_c, mismatch_c, only_our_c, only_bank_c):
    """Сохраняет метаданные сверки в системный архив (БД)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO reconciliation_archive
                (timestamp, username, bank_name, total_our, total_bank, difference, matched_count, mismatch_count, only_our_count, only_bank_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().isoformat(), user, bank_name,
                tot_our, tot_bank, diff, matched_c, mismatch_c, only_our_c, only_bank_c
            ))
            conn.commit()
            return True, "Сверка успешно сохранена в системный архив!"
        except Exception as e:
            return False, f"Ошибка при сохранении: {e}"


def get_archive_data() -> pd.DataFrame:
    """Возвращает историю всех сверок из БД."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT * FROM reconciliation_archive ORDER BY timestamp DESC",
            conn
        )


# ─────────────────────────────────────────────────────────────
# Общесистемные настройки (раньше жили только в st.session_state,
# из-за чего "сохранённые" настройки видел только тот же браузер/сессия).
# ─────────────────────────────────────────────────────────────
_DEFAULT_SETTINGS = {"amount_tolerance": 0.01, "currency": "UZS", "dayfirst": True}


def get_settings() -> dict:
    """Читает общесистемные настройки из БД, дополняя значениями по умолчанию."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM app_settings")
        rows = dict(cursor.fetchall())

    settings = dict(_DEFAULT_SETTINGS)
    if "amount_tolerance" in rows:
        settings["amount_tolerance"] = float(rows["amount_tolerance"])
    if "currency" in rows:
        settings["currency"] = rows["currency"]
    if "dayfirst" in rows:
        settings["dayfirst"] = rows["dayfirst"] == "1"
    return settings


def save_settings(settings: dict):
    """Сохраняет общесистемные настройки в БД — видны сразу всем пользователям."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        for key in ("amount_tolerance", "currency", "dayfirst"):
            if key in settings:
                value = settings[key]
                if isinstance(value, bool):
                    value = "1" if value else "0"
                cursor.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value))
                )
        conn.commit()


if __name__ == "__main__":
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        print("Пользователи в базе:", conn.execute("SELECT id, username, role FROM users").fetchall())
