"""
web_schema.py — схема SQLite для хранения данных из папки web/.

БД: data/web_data.db (отдельно от users.db)

Таблицы:
- web_versions   — версии загрузки (каждый запуск парсинга = новая версия)
- web_files      — файлы, вошедшие в версию (метаданные)
- web_data       — сами данные (строки из всех файлов)
"""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Путь к БД (читаем env на каждый connect — иначе showcase может «залипнуть» на prod).
_BASE_DIR = Path(__file__).resolve().parent


def get_web_db_path() -> str:
    """Актуальный путь к web_data.db (учитывает WEB_DB_PATH из showcase bootstrap)."""
    explicit = os.environ.get("WEB_DB_PATH", "").strip()
    if explicit:
        return explicit
    return str(_BASE_DIR / "data" / "web_data.db")


def __getattr__(name: str):
    if name == "WEB_DB_PATH":
        return get_web_db_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


@contextmanager
def get_web_connection():
    """Контекстный менеджер подключения к web_data.db."""
    conn = sqlite3.connect(get_web_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_web_schema():
    """
    Создаёт все таблицы если их нет.
    Безопасно вызывать при каждом старте приложения.
    """
    # Убедимся что папка data/ существует
    Path(get_web_db_path()).parent.mkdir(parents=True, exist_ok=True)

    with get_web_connection() as conn:
        cur = conn.cursor()

        # ── Версии загрузки ──────────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS web_versions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                label       TEXT,           -- опциональная метка, например 'декабрь 2025'
                status      TEXT    NOT NULL DEFAULT 'pending',
                                            -- pending | success | partial | error
                files_count INTEGER DEFAULT 0,
                rows_count  INTEGER DEFAULT 0,
                error_log   TEXT,
                is_active   INTEGER DEFAULT 0   -- 1 = текущая активная версия
            )
        """)

        # ── Файлы внутри версии ──────────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS web_files (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id  INTEGER NOT NULL REFERENCES web_versions(id),
                file_name   TEXT    NOT NULL,   -- 'sample_project_data_fixed.csv'
                rel_path    TEXT    NOT NULL,   -- 'MSProject/Dmitrovsky/file.csv'
                file_type   TEXT    NOT NULL,   -- 'project' | 'resources' | 'technique' | 'budget' | 'debit_credit' | 'unknown'
                rows_count  INTEGER DEFAULT 0,
                loaded_at   TEXT    DEFAULT (datetime('now'))
            )
        """)

        # ── Данные (строки из всех файлов) ───────────────────────────────────
        # Храним как JSON-строку — гибко, не нужно менять схему при добавлении колонок.
        # source_file нужен для будущих правил приоритета по имени файла.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS web_data (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id  INTEGER NOT NULL REFERENCES web_versions(id),
                file_id     INTEGER NOT NULL REFERENCES web_files(id),
                file_type   TEXT    NOT NULL,
                source_file TEXT    NOT NULL,   -- имя файла-источника (для правил приоритета)
                row_data    TEXT    NOT NULL    -- JSON строки данных
            )
        """)

        # Индексы для быстрых выборок по версии
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_data_version
            ON web_data(version_id, file_type)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_web_files_version
            ON web_files(version_id)
        """)


def get_active_version_id() -> int | None:
    """Возвращает id активной версии.

    Политика:
    1) явно помеченная `is_active=1` — но только если её статус `success`
       (чтобы случайно оставшаяся активной `partial`-версия не блокировала
        показ последней корректной загрузки);
       Страховка: если активна последняя по id success, но она строго «беднее»
       предыдущей success (меньше и files_count, и rows_count), возвращаем
       предыдущую — исправляет уже записанные в БД случаи до правки web_loader.
    2) иначе — последняя `status='success'`;
    3) в крайнем случае — последняя любая (включая `partial`).
    """
    with get_web_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, status, files_count, rows_count FROM web_versions WHERE is_active = 1 "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row and row["status"] == "success":
            aid = int(row["id"])
            max_s = cur.execute(
                "SELECT id, files_count, rows_count FROM web_versions "
                "WHERE status='success' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if max_s and int(max_s["id"]) == aid:
                prev = cur.execute(
                    "SELECT id, files_count, rows_count FROM web_versions "
                    "WHERE status='success' AND id < ? ORDER BY id DESC LIMIT 1",
                    (aid,),
                ).fetchone()
                if prev:
                    af, ar = int(row["files_count"] or 0), int(row["rows_count"] or 0)
                    pf, pr = int(prev["files_count"] or 0), int(prev["rows_count"] or 0)
                    if af < pf and ar < pr:
                        pid = int(prev["id"])
                        cur.execute("UPDATE web_versions SET is_active=0")
                        cur.execute("UPDATE web_versions SET is_active=1 WHERE id=?", (pid,))
                        return pid
            return aid
        last_success = cur.execute(
            "SELECT id FROM web_versions WHERE status='success' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if last_success:
            return last_success["id"]
        if row:  # активная partial — лучше, чем ничего
            return row["id"]
        row = cur.execute(
            "SELECT id FROM web_versions WHERE status IN ('success','partial') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None


def get_all_versions() -> list[dict]:
    """Возвращает все версии для селектора в UI (новые сверху)."""
    with get_web_connection() as conn:
        cur = conn.cursor()
        rows = cur.execute("""
            SELECT id, created_at, label, status, files_count, rows_count, is_active
            FROM web_versions
            ORDER BY id DESC
            LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]


def activate_version(version_id: int):
    """Делает указанную версию активной, сбрасывает флаг у остальных."""
    with get_web_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE web_versions SET is_active = 0")
        cur.execute("UPDATE web_versions SET is_active = 1 WHERE id = ?", (version_id,))


def _keep_versions_limit() -> int:
    """Сколько последних снимков хранить (архив выбора версии). 0/неположит. = без очистки."""
    import os

    try:
        n = int(os.environ.get("BI_ANALYTICS_KEEP_VERSIONS", "10") or "10")
    except (TypeError, ValueError):
        n = 10
    return max(0, n)


def prune_old_versions(keep: int | None = None, *, cur=None) -> list[int]:
    """Удаляет старые снимки сверх ``keep`` последних (по id), не трогая активную.

    Возвращает список удалённых version_id. Каскад web_data/web_files делаем вручную
    (FK без ON DELETE). Если передан ``cur`` — работаем в текущей транзакции
    (вызов из load_all_from_web до commit), иначе открываем свою.
    """
    if keep is None:
        keep = _keep_versions_limit()
    if not keep or keep <= 0:
        return []

    def _do(c) -> list[int]:
        rows = c.execute(
            "SELECT id, is_active FROM web_versions ORDER BY id DESC"
        ).fetchall()
        if len(rows) <= keep:
            return []
        keep_ids: set[int] = set()
        for r in rows[:keep]:
            keep_ids.add(int(r["id"]))
        for r in rows:
            if int(r["is_active"] or 0) == 1:
                keep_ids.add(int(r["id"]))
        to_delete = [int(r["id"]) for r in rows if int(r["id"]) not in keep_ids]
        if not to_delete:
            return []
        placeholders = ",".join("?" for _ in to_delete)
        c.execute(f"DELETE FROM web_data WHERE version_id IN ({placeholders})", to_delete)
        c.execute(f"DELETE FROM web_files WHERE version_id IN ({placeholders})", to_delete)
        c.execute(f"DELETE FROM web_versions WHERE id IN ({placeholders})", to_delete)
        return to_delete

    if cur is not None:
        return _do(cur)
    with get_web_connection() as conn:
        return _do(conn.cursor())
