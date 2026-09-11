import sqlite3
import os
from datetime import datetime
import hashlib

def init_user_db():
    conn = sqlite3.connect("database/reconcile_hub.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)
    # Создаем дефолтного администратора, если таблица пустая
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        default_pass = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute("INSERT INTO users VALUES (?, ?, ?)", ("admin", default_pass, "admin"))
    conn.commit()
    conn.close()

def verify_user(username, password):
    conn = sqlite3.connect("database/reconcile_hub.db")
    cursor = conn.cursor()
    pass_hash = hashlib.sha256(password.encode()).hexdigest()
    cursor.execute("SELECT role FROM users WHERE username = ? AND password_hash = ?", (username, pass_hash))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None
def hash_password(password: str) -> str:
    """Создает SHA-256 хеш пароля."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(password: str, hashed_password: str) -> bool:
    """Проверяет совпадение пароля с хешем."""
    return hash_password(password) == hashed_password

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

# Немного модифицируем вашу функцию init_db(), чтобы она создавала админа:
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # ... (здесь ваш код создания таблиц users, epos_registry, audit_logs) ...
        
        # Проверяем, есть ли пользователи. Если нет — создаем дефолтного админа
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            admin_hash = hash_password("admin123") # Дефолтный пароль
            cursor.execute('''
                INSERT INTO users (username, password_hash, role) 
                VALUES (?, ?, ?)
            ''', ("admin", admin_hash, "admin"))
            
        conn.commit()

DB_PATH = "database/reconcile_hub.db"

def init_db():
    """Инициализирует локальную БД и создает таблицы, если их нет."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей и ролей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')
        
        # Реестр EPOS терминалов
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
        
        # Логирование действий (Audit Log)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                username TEXT,
                action TEXT,
                details TEXT
            )
        ''')
        
        conn.commit()

def log_action(username: str, action: str, details: str = ""):
    """Записывает критичное действие пользователя в системный лог."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO audit_logs (timestamp, username, action, details) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), username, action, details)
        )
        conn.commit()

import pandas as pd

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

if __name__ == "__main__":
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        print("Пользователи в базе:", conn.execute("SELECT * FROM users").fetchall())
def save_reconciliation(user, bank_name, tot_our, tot_bank, diff, matched_c, mismatch_c, only_our_c, only_bank_c):
    """Сохраняет метаданные сверки в системный архив (БД)."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Создаем таблицу архива, если её еще нет (на всякий случай)
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