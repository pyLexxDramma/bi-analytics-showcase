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
        if own:
            conn.commit()
    finally:
        if own:
            conn.close()


def insert_bug_report(row: dict[str, Any]) -> int:
    ensure_bug_reports_table()
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute(
            """
            INSERT INTO bug_reports (
                username, user_role, first_name, last_name, report_tab, page_url, theme,
                version_id, app_build, user_text, category, priority, ai_title, ai_summary,
                ai_confidence, ai_source, status, trello_card_id, trello_card_url,
                error_message, raw_ai_response,
                contact_email, contact_telegram, public_token, client_status,
                related_report_id, notified_accepted_at, notified_ready_at, notified_on_hold_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("username"),
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
