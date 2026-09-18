import sqlite3
import os
import hashlib
import secrets
import json
import warnings
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


def _bootstrap_admin_password() -> str:
    """Return the bootstrap admin password with a safe production default."""
    configured = os.getenv("RECONCILEHUB_ADMIN_PASSWORD", "").strip()
    if configured:
        return configured

    environment = os.getenv("RECONCILEHUB_ENV", "development").strip().lower()
    if environment in {"prod", "production"}:
        raise RuntimeError(
            "RECONCILEHUB_ADMIN_PASSWORD must be set before creating a production database"
        )

    warnings.warn(
        "Using development bootstrap password 'admin123'. "
        "Set RECONCILEHUB_ADMIN_PASSWORD for non-local deployments.",
        RuntimeWarning,
        stacklevel=2,
    )
    return "admin123"


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
                only_bank_count INTEGER,
                period_month TEXT,
                total_commission REAL DEFAULT 0.0,
                terminals_json TEXT,
                run_id TEXT,
                source_our_name TEXT,
                source_bank_name TEXT,
                config_json TEXT
            )
        ''')

        # Миграция колонок для существующих баз данных
        for col_name, col_type in [
            ("period_month", "TEXT"),
            ("total_commission", "REAL DEFAULT 0.0"),
            ("terminals_json", "TEXT"),
            ("run_id", "TEXT"),
            ("source_our_name", "TEXT"),
            ("source_bank_name", "TEXT"),
            ("config_json", "TEXT")
        ]:
            try:
                cursor.execute(f"ALTER TABLE reconciliation_archive ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError:
                pass  # Колонка уже существует

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
            admin_hash = hash_password(_bootstrap_admin_password())
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("admin", admin_hash, "admin"),
            )

        cursor.execute("SELECT COUNT(*) FROM epos_registry")
        if cursor.fetchone()[0] == 0:
            default_banks = [
                ('98234001', 'MID_ALOQA_01', 'Aloqa Bank', '', 1.2, 1),
                ('98234002', 'MID_OPEN_01', 'Open Bank', '', 1.0, 1),
                ('98234003', 'MID_SADERAT_01', 'Saderat Bank', '', 1.5, 1),
                ('98234004', 'MID_DAVR_01', 'Davr Bank', '', 1.0, 1),
                ('98234005', 'MID_HAMKOR_01', 'Hamkor Bank', '', 1.2, 1),
            ]
            cursor.executemany(
                "INSERT INTO epos_registry (terminal_id, merchant_id, bank_acquirer, legal_entity, commission_pct, is_active) VALUES (?, ?, ?, ?, ?, ?)",
                default_banks
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
                if "$" not in db_hash:
                    cursor.execute(
                        "UPDATE users SET password_hash = ? WHERE username = ?",
                        (hash_password(password), username),
                    )
                    conn.commit()
                return True, role
    return False, None


def get_user_id(username: str) -> int:
    """Возвращает ID пользователя по логину."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        return int(row[0]) if row else 0


def log_action(username: str, action: str, details: str = ""):
    """Записывает критичное действие пользователя в системный лог."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (timestamp, username, action, details) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), username, action, details)
        )
        conn.commit()


def add_epos_terminal(tid, mid, bank, entity="", com_pct=0.0):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO epos_registry (terminal_id, merchant_id, bank_acquirer, legal_entity, commission_pct, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (tid, mid, bank, entity, com_pct))
            conn.commit()
            return True, "Терминал/банк успешно добавлен!"
        except sqlite3.IntegrityError:
            return False, f"Ошибка: Терминал с TID {tid} уже существует!"
        except Exception as e:
            return False, f"Системная ошибка: {e}"


def delete_epos_terminal(tid: str):
    """Удаляет терминал по его TID."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM epos_registry WHERE terminal_id = ?", (tid,))
        conn.commit()
        return True, f"Терминал {tid} удалён"


def update_epos_terminal(tid: str, bank: str, mid: str, com_pct: float, is_active: bool):
    """Обновляет параметры терминала."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE epos_registry 
            SET bank_acquirer = ?, merchant_id = ?, commission_pct = ?, is_active = ?
            WHERE terminal_id = ?
        ''', (bank, mid, com_pct, 1 if is_active else 0, tid))
        conn.commit()
        return True, "Данные терминала обновлены"


def bulk_upsert_epos(records: list[dict]):
    """Пакетно вставляет или обновляет терминалы (для импорта из Excel/JSON)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        count = 0
        for r in records:
            tid = str(r.get("terminal_id") or r.get("TID") or "").strip()
            if not tid:
                continue
            bank = str(r.get("bank_acquirer") or r.get("Банк") or "Неизвестный банк").strip()
            mid = str(r.get("merchant_id") or r.get("MID") or f"MID_{tid}").strip()
            entity = str(r.get("legal_entity") or r.get("Юр. лицо") or "").strip()
            try:
                raw_pct = r.get("commission_pct") or r.get("Комиссия (%)") or r.get("Комиссия") or 0.0
                com_pct = float(str(raw_pct).replace("%", "").replace(",", ".").strip() or 0.0)
            except (ValueError, TypeError):
                com_pct = 0.0
            is_active = 1 if r.get("is_active", True) in (True, 1, "1", "true", "True") else 0

            cursor.execute('''
                INSERT INTO epos_registry (terminal_id, merchant_id, bank_acquirer, legal_entity, commission_pct, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(terminal_id) DO UPDATE SET
                    merchant_id = excluded.merchant_id,
                    bank_acquirer = excluded.bank_acquirer,
                    legal_entity = CASE WHEN excluded.legal_entity != '' THEN excluded.legal_entity ELSE epos_registry.legal_entity END,
                    commission_pct = excluded.commission_pct,
                    is_active = excluded.is_active
            ''', (tid, mid, bank, entity, com_pct, is_active))
            count += 1
        conn.commit()
        return count


def get_active_banks() -> list[str]:
    """Возвращает уникальный список активных банков из реестра."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT bank_acquirer FROM epos_registry WHERE is_active = 1 ORDER BY bank_acquirer")
        banks = [row[0] for row in cursor.fetchall() if row[0]]
        if not banks:
            banks = ["Aloqa Bank", "Open Bank", "Saderat Bank", "Davr Bank", "Hamkor Bank"]
        return banks


def get_epos_registry() -> pd.DataFrame:
    """Возвращает весь реестр в виде DataFrame для удобного отображения."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query("SELECT * FROM epos_registry", conn)


def delete_user(user_id: int):
    """Удаляет пользователя по ID (кроме главного admin)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "Пользователь не найден"
        if row[0] == "admin":
            return False, "Нельзя удалить главного администратора 'admin'!"
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True, f"Пользователь '{row[0]}' удалён"


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


def save_reconciliation(
    user,
    bank_name,
    tot_our,
    tot_bank,
    diff,
    matched_c,
    mismatch_c,
    only_our_c,
    only_bank_c,
    period_month=None,
    total_commission=0.0,
    terminals_data=None,
    run_id=None,
    source_our_name=None,
    source_bank_name=None,
    config_data=None,
):
    """Сохраняет или обновляет результат сверки по run_id.

    Повторное сохранение того же запуска обновляет запись вместо создания
    дубликата, что позволяет безопасно фиксировать ручные исключения повторно.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            if not period_month:
                period_month = datetime.now().strftime("%Y-%m")

            terminals_json = ""
            if terminals_data is not None:
                if isinstance(terminals_data, pd.DataFrame):
                    terminals_json = terminals_data.to_json(orient="records", date_format="iso")
                elif isinstance(terminals_data, (list, dict)):
                    terminals_json = json.dumps(terminals_data, ensure_ascii=False)
                elif isinstance(terminals_data, str):
                    terminals_json = terminals_data

            config_json = ""
            if config_data is not None:
                if isinstance(config_data, str):
                    config_json = config_data
                else:
                    config_json = json.dumps(config_data, ensure_ascii=False, default=str)

            now = datetime.now().isoformat()
            normalized_run_id = str(run_id or "").strip() or None
            existing_id = None
            if normalized_run_id:
                cursor.execute(
                    "SELECT id FROM reconciliation_archive WHERE run_id = ? ORDER BY id DESC LIMIT 1",
                    (normalized_run_id,),
                )
                row = cursor.fetchone()
                existing_id = int(row[0]) if row else None

            values = (
                now, user, bank_name,
                float(tot_our), float(tot_bank), float(diff), int(matched_c), int(mismatch_c),
                int(only_our_c), int(only_bank_c), str(period_month), float(total_commission or 0.0),
                str(terminals_json), normalized_run_id, str(source_our_name or ""), str(source_bank_name or ""),
                str(config_json),
            )

            if existing_id:
                cursor.execute('''
                    UPDATE reconciliation_archive
                    SET timestamp = ?, username = ?, bank_name = ?, total_our = ?, total_bank = ?,
                        difference = ?, matched_count = ?, mismatch_count = ?, only_our_count = ?,
                        only_bank_count = ?, period_month = ?, total_commission = ?, terminals_json = ?,
                        run_id = ?, source_our_name = ?, source_bank_name = ?, config_json = ?
                    WHERE id = ?
                ''', values + (existing_id,))
                message = f"Сверка #{existing_id} обновлена в системном архиве."
            else:
                cursor.execute('''
                    INSERT INTO reconciliation_archive
                    (timestamp, username, bank_name, total_our, total_bank, difference, matched_count, mismatch_count,
                     only_our_count, only_bank_count, period_month, total_commission, terminals_json, run_id,
                     source_our_name, source_bank_name, config_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', values)
                message = f"Сверка #{cursor.lastrowid} сохранена в системный архив."

            conn.commit()
            return True, message
        except Exception as e:
            return False, f"Ошибка при сохранении: {e}"


def get_archive_data() -> pd.DataFrame:
    """Возвращает историю всех сверок из БД."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            "SELECT * FROM reconciliation_archive ORDER BY timestamp DESC",
            conn
        )


def delete_archive_record(record_id: int):
    """Удаляет запись из архива."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reconciliation_archive WHERE id = ?", (record_id,))
        conn.commit()


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
