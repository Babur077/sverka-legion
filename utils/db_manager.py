import sqlite3
import os
import hashlib
import secrets
import json
import warnings
from datetime import datetime

import pandas as pd

from backend.db.migrations.runner import run_migrations

DB_PATH = os.getenv("RECONCILEHUB_DB_PATH", "database/reconcile_hub.db")

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
    """Apply versioned schema migrations and bootstrap reference data."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    run_migrations(DB_PATH)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

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
                ("98234001", "MID_ALOQA_01", "Aloqa Bank", "", 1.2, 1),
                ("98234002", "MID_OPEN_01", "Open Bank", "", 1.0, 1),
                ("98234003", "MID_SADERAT_01", "Saderat Bank", "", 1.5, 1),
                ("98234004", "MID_DAVR_01", "Davr Bank", "", 1.0, 1),
                ("98234005", "MID_HAMKOR_01", "Hamkor Bank", "", 1.2, 1),
            ]
            cursor.executemany(
                """
                INSERT INTO epos_registry (
                    terminal_id, merchant_id, bank_acquirer, legal_entity,
                    commission_pct, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                default_banks,
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




def _json_text(value, fallback):
    if value is None:
        value = fallback
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def save_reconciliation_run(module_id: str, user: str, payload: dict):
    """Create/update one module run in the shared reconciliation journal."""
    normalized_module_id = str(module_id or "").strip()
    if not normalized_module_id:
        return False, "module_id обязателен", None

    payload = dict(payload or {})
    now = datetime.now().isoformat()
    run_id = str(payload.get("run_id") or "").strip() or None
    period_month = str(payload.get("period_month") or "").strip() or None
    status = str(payload.get("status") or "COMPLETED").strip().upper() or "COMPLETED"
    review_status = str(payload.get("review_status") or "OPEN").strip().upper() or "OPEN"

    source_files = payload.get("source_files")
    if not isinstance(source_files, list):
        source_files = [
            value
            for value in [
                payload.get("source_our_name"),
                payload.get("source_bank_name"),
            ]
            if value
        ]

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {
            key: payload.get(key)
            for key in (
                "total_our",
                "total_bank",
                "difference",
                "matched_count",
                "mismatch_count",
                "only_our_count",
                "only_bank_count",
                "total_commission",
            )
            if key in payload
        }

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            existing = None
            if run_id:
                existing = cursor.execute(
                    """
                    SELECT id, created_at
                    FROM reconciliation_runs
                    WHERE module_id = ? AND run_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (normalized_module_id, run_id),
                ).fetchone()

            values = (
                normalized_module_id,
                run_id,
                status,
                period_month,
                existing[1] if existing else now,
                now,
                str(user or ""),
                _json_text(source_files, []),
                _json_text(summary, {}),
                _json_text(payload, {}),
                review_status,
            )

            if existing:
                record_id = int(existing[0])
                cursor.execute(
                    """
                    UPDATE reconciliation_runs
                    SET module_id = ?, run_id = ?, status = ?, period_month = ?,
                        created_at = ?, updated_at = ?, created_by = ?,
                        source_files_json = ?, summary_json = ?, payload_json = ?,
                        review_status = ?
                    WHERE id = ?
                    """,
                    values + (record_id,),
                )
                message = f"Сверка #{record_id} обновлена в системном журнале."
            else:
                cursor.execute(
                    """
                    INSERT INTO reconciliation_runs (
                        module_id, run_id, status, period_month, created_at, updated_at,
                        created_by, source_files_json, summary_json, payload_json,
                        review_status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                record_id = int(cursor.lastrowid)
                message = f"Сверка #{record_id} сохранена в системный журнал."

            conn.commit()
            return True, message, record_id
        except Exception as exc:
            return False, f"Ошибка при сохранении: {exc}", None


def get_reconciliation_runs(module_id: str | None = None) -> list[dict]:
    """Return shared reconciliation runs, optionally filtered by module."""
    query = """
        SELECT id, module_id, run_id, status, period_month, created_at, updated_at,
               created_by, source_files_json, summary_json, payload_json,
               review_status
        FROM reconciliation_runs
    """
    params: tuple = ()
    if module_id:
        query += " WHERE module_id = ?"
        params = (str(module_id),)
    query += " ORDER BY updated_at DESC, id DESC"

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()

    records: list[dict] = []
    for row in rows:
        raw = dict(row)
        try:
            payload = json.loads(raw.get("payload_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        try:
            source_files = json.loads(raw.get("source_files_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            source_files = []
        try:
            summary = json.loads(raw.get("summary_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            summary = {}

        record = dict(payload) if isinstance(payload, dict) else {}
        record.update({
            "id": raw["id"],
            "module_id": raw["module_id"],
            "run_id": raw["run_id"] or record.get("run_id"),
            "status": raw["status"],
            "period_month": raw["period_month"] or record.get("period_month"),
            # Compatibility with the existing Bank RRN archive UI.
            "timestamp": raw["updated_at"],
            "created_at": raw["created_at"],
            "updated_at": raw["updated_at"],
            "username": raw["created_by"],
            "created_by": raw["created_by"],
            "source_files": source_files,
            "summary": summary,
            "review_status": raw["review_status"],
        })
        records.append(record)

    return records


def delete_reconciliation_run(module_id: str, record_id: int) -> bool:
    """Delete exactly one run from one module archive."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM reconciliation_runs WHERE id = ? AND module_id = ?",
            (int(record_id), str(module_id)),
        )
        conn.commit()
        return cursor.rowcount > 0


# Compatibility wrappers for Bank RRN while the frontend keeps its existing model.
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
    assigned_terminal_id=None,
):
    payload = {
        "bank_name": bank_name,
        "total_our": float(tot_our),
        "total_bank": float(tot_bank),
        "difference": float(diff),
        "matched_count": int(matched_c),
        "mismatch_count": int(mismatch_c),
        "only_our_count": int(only_our_c),
        "only_bank_count": int(only_bank_c),
        "period_month": period_month or datetime.now().strftime("%Y-%m"),
        "total_commission": float(total_commission or 0),
        "terminals_summary": terminals_data or [],
        "run_id": run_id,
        "source_our_name": source_our_name or "",
        "source_bank_name": source_bank_name or "",
        "config": config_data or {},
        "assigned_terminal_id": assigned_terminal_id,
    }
    ok, message, _ = save_reconciliation_run("bank_rrn", user, payload)
    return ok, message


def get_archive_data() -> pd.DataFrame:
    records = get_reconciliation_runs("bank_rrn")
    compatible = []
    for record in records:
        item = dict(record)
        item["terminals_json"] = json.dumps(
            item.get("terminals_summary") or [],
            ensure_ascii=False,
            default=str,
        )
        item["config_json"] = json.dumps(
            item.get("config") or {},
            ensure_ascii=False,
            default=str,
        )
        compatible.append(item)
    return pd.DataFrame(compatible)


def delete_archive_record(record_id: int):
    return delete_reconciliation_run("bank_rrn", record_id)


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
