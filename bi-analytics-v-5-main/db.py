"""
Единая точка входа для подключения к БД и инициализации всех таблиц.
"""
import sqlite3
import hashlib
from typing import Optional
from contextlib import contextmanager

from config import DB_PATH

# Для создания дефолтного суперадмина (без циклического импорта auth)
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


@contextmanager
def get_connection():
    """Контекстный менеджер для подключения к SQLite."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_all_tables(st_callback=None):
    """
    Создание всех таблиц приложения в одном месте.
    st_callback: опционально вызывается с сообщением для отображения в Streamlit (например, о создании дефолтного пользователя).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    """)

    # Таблица токенов для восстановления пароля
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    # Таблица настроек путей к файлам (legacy)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_paths_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_key TEXT UNIQUE NOT NULL,
            setting_value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT
        )
    """)

    # Таблица логов действий пользователей
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    # Таблица прав доступа к проектам (единая схема: created_at, granted_by)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            granted_by TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, project_name)
        )
    """)

    # Таблица фильтров по умолчанию для ролей и отчетов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS default_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            report_name TEXT NOT NULL,
            filter_key TEXT NOT NULL,
            filter_value TEXT,
            filter_type TEXT DEFAULT 'string',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            UNIQUE(role, report_name, filter_key)
        )
    """)

    # Таблица параметров отчетов для аналитиков
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_name TEXT NOT NULL,
            parameter_key TEXT NOT NULL,
            parameter_value TEXT,
            parameter_type TEXT DEFAULT 'string',
            description TEXT,
            is_editable_by_analyst INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by TEXT,
            UNIQUE(report_name, parameter_key)
        )
    """)

    # Таблица настроек (settings)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT,
            description TEXT,
            updated_at TEXT,
            updated_by TEXT
        )
    """)

    # Persistent-сессии: токен в URL ?sid=... позволяет восстановить логин
    # при разрыве websocket Streamlit (длинная обработка → сессия пересоздаётся
    # → пользователя «выкидывает»). Срок хранения по умолчанию — 7 дней.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)"
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bug_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            user_role TEXT,
            first_name TEXT,
            last_name TEXT,
            report_tab TEXT,
            page_url TEXT,
            theme TEXT,
            version_id INTEGER,
            app_build TEXT,
            user_text TEXT NOT NULL,
            category TEXT,
            priority TEXT,
            ai_title TEXT,
            ai_summary TEXT,
            ai_confidence REAL,
            ai_source TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            trello_card_id TEXT,
            trello_card_url TEXT,
            error_message TEXT,
            raw_ai_response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    bug_cols = {row[1] for row in cursor.execute("PRAGMA table_info(bug_reports)").fetchall()}
    if "first_name" not in bug_cols:
        cursor.execute("ALTER TABLE bug_reports ADD COLUMN first_name TEXT")
    if "last_name" not in bug_cols:
        cursor.execute("ALTER TABLE bug_reports ADD COLUMN last_name TEXT")

    conn.commit()

    # Дефолтный суперадминистратор (учитываем только активных — как в create_user).
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE role = ? AND is_active = 1",
        ("superadmin",),
    )
    if cursor.fetchone()[0] == 0:
        default_password = _hash_password("admin123")
        cursor.execute(
            "INSERT INTO users (username, password_hash, role, email) VALUES (?, ?, ?, ?)",
            ("admin", default_password, "superadmin", "admin@example.com"),
        )
        conn.commit()
        if st_callback:
            st_callback("⚠️ Создан дефолтный пользователь: admin / admin123")

    # В БД может остаться более одного superadmin после старых правок — оставляем одного (минимальный id).
    cursor.execute(
        """
        SELECT id FROM users
        WHERE role = 'superadmin' AND is_active = 1
        ORDER BY id ASC
        """
    )
    sa_ids = [r[0] for r in cursor.fetchall()]
    if len(sa_ids) > 1:
        for uid in sa_ids[1:]:
            cursor.execute(
                "UPDATE users SET role = 'admin' WHERE id = ?",
                (uid,),
            )
        conn.commit()

    conn.close()
