"""Локальная очередь и журнал баг-репортов (SQLite)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from config import DB_PATH


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
                username, user_role, report_tab, page_url, theme, version_id, app_build,
                user_text, category, priority, ai_title, ai_summary, ai_confidence, ai_source,
                status, trello_card_id, trello_card_url, error_message, raw_ai_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("username"),
                row.get("user_role"),
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


def dump_row_for_debug(report_id: int) -> str:
    row = get_bug_report(report_id)
    return json.dumps(row, ensure_ascii=False, indent=2, default=str) if row else ""
