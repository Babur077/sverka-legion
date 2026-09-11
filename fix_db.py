import sqlite3
import hashlib
import os

DB_PATH = "database/reconcile_hub.db"

def force_create_admin():
    # Создаем папку, если ее вдруг нет
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Гарантируем наличие таблицы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')
        
        # Генерируем правильный хеш для admin123
        admin_hash = hashlib.sha256("admin123".encode('utf-8')).hexdigest()
        
        # Очищаем возможные зависшие записи и вставляем админа
        cursor.execute("DELETE FROM users WHERE username = 'admin'")
        cursor.execute('''
            INSERT INTO users (username, password_hash, role) 
            VALUES (?, ?, ?)
        ''', ("admin", admin_hash, "admin"))
        
        conn.commit()
        
        # Проверяем результат
        cursor.execute("SELECT id, username, role FROM users")
        print("✅ Успешно! Пользователи в базе:", cursor.fetchall())

if __name__ == "__main__":
    force_create_admin()