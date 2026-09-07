"""Локальная очередь и журнал баг-репортов (SQLite)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from config import DB_PATH

_EXTRA_COLUMNS: tuple[tuple[str, str], ...] = (
    ("first_name", "TEXT"),
    ("last_name", "TEXT"),
    ("contact_email", "TEXT"),
    ("contact_telegram", "TEXT"),
    ("public_token", "TEXT"),
    ("client_status", "TEXT"),
    ("related_report_id", "INTEGER"),
    ("notified_accepted_at", "TEXT"),
    ("notified_ready_at", "TEXT"),
    ("notified_on_hold_at", "TEXT"),
    ("user_seq", "INTEGER"),
)


def ensure_bug_reports_table(conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    if own:
        conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
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
            """
        )
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(bug_reports)").fetchall()
        }
        for name, decl in _EXTRA_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE bug_reports ADD COLUMN {name} {decl}")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bug_reports_public_token "
            "ON bug_reports(public_token) WHERE public_token IS NOT NULL AND public_token != ''"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_bug_reports_user_seq "
            "ON bug_reports(username, user_seq) "
            "WHERE user_seq IS NOT NULL"
        )
        _backfill_user_seq(conn)
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def _backfill_user_seq(conn: sqlite3.Connection) -> None:
    """Пронумеровать старые заявки по username (порядок id)."""
    missing = conn.execute(
        "SELECT COUNT(1) FROM bug_reports WHERE user_seq IS NULL OR user_seq = 0"
    ).fetchone()[0]
    if not missing:
        return
    rows = conn.execute(
        "SELECT id, username FROM bug_reports ORDER BY username ASC, id ASC"
    ).fetchall()
    counters: dict[str, int] = {}
    for rid, username in rows:
        key = (username or "").strip() or "_"
        counters[key] = counters.get(key, 0) + 1
        conn.execute(
            "UPDATE bug_reports SET user_seq = ? WHERE id = ? AND (user_seq IS NULL OR user_seq = 0)",
            (counters[key], rid),
        )


def next_user_seq(conn: sqlite3.Connection, username: str) -> int:
    key = (username or "").strip()
    row = conn.execute(
        "SELECT COALESCE(MAX(user_seq), 0) FROM bug_reports WHERE username = ?",
        (key,),
    ).fetchone()
    return int(row[0] or 0) + 1


def display_ticket_no(row: dict[str, Any] | None) -> int:
    if not row:
        return 0
    seq = row.get("user_seq")
    try:
        if seq is not None and int(seq) > 0:
            return int(seq)
    except (TypeError, ValueError):
        pass
    try:
        return int(row.get("id") or 0)
    except (TypeError, ValueError):
        return 0


def resolve_related_report_id(username: str, raw: str | int | None) -> int | None:
    """Номер из формы: сначала user_seq текущего пользователя, иначе глобальный id."""
    if raw is None or raw == "":
        return None
    try:
        num = int(str(raw).strip())
    except ValueError:
        return None
    if num <= 0:
        return None
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        by_seq = conn.execute(
            "SELECT id FROM bug_reports WHERE username = ? AND user_seq = ?",
            ((username or "").strip(), num),
        ).fetchone()
        if by_seq:
            return int(by_seq["id"])
        by_id = conn.execute("SELECT id FROM bug_reports WHERE id = ?", (num,)).fetchone()
        return int(by_id["id"]) if by_id else None
    finally:
        conn.close()


def insert_bug_report(row: dict[str, Any]) -> int:
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    try:
        username = str(row.get("username") or "").strip()
        user_seq = row.get("user_seq")
        if not user_seq:
            user_seq = next_user_seq(conn, username)
        cur = conn.execute(
            """
            INSERT INTO bug_reports (
                username, user_role, first_name, last_name, report_tab, page_url, theme,
                version_id, app_build, user_text, category, priority, ai_title, ai_summary,
                ai_confidence, ai_source, status, trello_card_id, trello_card_url,
                error_message, raw_ai_response,
                contact_email, contact_telegram, public_token, client_status,
                related_report_id, notified_accepted_at, notified_ready_at, notified_on_hold_at,
                user_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                row.get("user_role"),
                row.get("first_name"),
                row.get("last_name"),
                row.get("report_tab"),
                row.get("page_url"),
                row.get("theme"),
                row.get("version_id"),
                row.get("app_build"),
                row.get("user_text"),
                row.get("category"),
                row.get("priority"),
                row.get("ai_title"),
                row.get("ai_summary"),
                row.get("ai_confidence"),
                row.get("ai_source"),
                row.get("status", "queued"),
                row.get("trello_card_id"),
                row.get("trello_card_url"),
                row.get("error_message"),
                row.get("raw_ai_response"),
                row.get("contact_email"),
                row.get("contact_telegram"),
                row.get("public_token"),
                row.get("client_status", "accepted"),
                row.get("related_report_id"),
                row.get("notified_accepted_at"),
                row.get("notified_ready_at"),
                row.get("notified_on_hold_at"),
                int(user_seq),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_bug_report(report_id: int, **fields: Any) -> None:
    if not fields:
        return
    ensure_bug_reports_table()
    cols = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [report_id]
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(f"UPDATE bug_reports SET {cols} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def get_bug_report(report_id: int) -> dict[str, Any] | None:
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM bug_reports WHERE id = ?", (report_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_bug_report_by_token(token: str) -> dict[str, Any] | None:
    token = (token or "").strip()
    if not token:
        return None
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM bug_reports WHERE public_token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_bug_reports_for_user(username: str, *, limit: int = 200) -> list[dict[str, Any]]:
    username = (username or "").strip()
    if not username:
        return []
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM bug_reports
            WHERE username = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (username, max(1, min(limit, 500))),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_bug_reports_with_trello(*, limit: int = 500) -> list[dict[str, Any]]:
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT * FROM bug_reports
            WHERE trello_card_id IS NOT NULL AND TRIM(trello_card_id) != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 2000)),),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def dump_row_for_debug(report_id: int) -> str:
    row = get_bug_report(report_id)
    return json.dumps(row, ensure_ascii=False, indent=2, default=str) if row else ""
