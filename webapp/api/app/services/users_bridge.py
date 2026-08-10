from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.config import (
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_ADMIN_USERNAME,
    USERS_DB_PATH,
)
from app.services.core_bridge import prepare_core_env

_prepared = False


def _patch_db_path() -> None:
    import config  # type: ignore

    path = str(USERS_DB_PATH.resolve())
    USERS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.DB_PATH = path


def ensure_users_db(*, seed: bool = True) -> None:
    global _prepared
    prepare_core_env()
    _patch_db_path()
    import auth  # type: ignore

    before_user_ids: set[int] = set()
    if USERS_DB_PATH.is_file():
        try:
            with sqlite3.connect(str(USERS_DB_PATH)) as conn:
                before_user_ids = {
                    int(row[0]) for row in conn.execute("SELECT id FROM users").fetchall()
                }
        except sqlite3.Error:
            before_user_ids = set()

    auth.init_db(quiet=True)
    with sqlite3.connect(str(USERS_DB_PATH)) as conn:
        after_user_ids = {
            int(row[0]) for row in conn.execute("SELECT id FROM users").fetchall()
        }
        generated_ids = after_user_ids - before_user_ids
        if generated_ids:
            placeholders = ",".join("?" for _ in generated_ids)
            conn.execute(
                f"DELETE FROM users WHERE id IN ({placeholders})",
                tuple(sorted(generated_ids)),
            )
            conn.commit()
        count = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    if seed and count == 0 and len(BOOTSTRAP_ADMIN_PASSWORD) >= 16:
        auth.create_user(
            BOOTSTRAP_ADMIN_USERNAME,
            BOOTSTRAP_ADMIN_PASSWORD,
            "superadmin",
            None,
            "system",
        )
    if not _prepared:
        _prepared = True


def import_auth() -> Any:
    ensure_users_db()
    import auth  # type: ignore

    return auth


def import_filters() -> Any:
    ensure_users_db()
    import filters  # type: ignore

    # На холодном импорте dashboards может быть недоступен → AVAILABLE_REPORTS=[].
    # Подтягиваем список отчётов лениво после prepare_core_env.
    if not getattr(filters, "AVAILABLE_REPORTS", None):
        try:
            from dashboards import get_all_report_names  # type: ignore

            filters.AVAILABLE_REPORTS = list(get_all_report_names() or [])
        except Exception:
            try:
                from app.services.ask_ai_reports import SCREENS

                filters.AVAILABLE_REPORTS = [str(m["title"]) for m in SCREENS.values()]
            except Exception:
                filters.AVAILABLE_REPORTS = []
    return filters


def import_logger() -> Any:
    ensure_users_db()
    import logger  # type: ignore

    return logger


def import_settings_module() -> Any:
    ensure_users_db()
    import settings as settings_mod  # type: ignore

    return settings_mod


def format_russian_datetime(dt_str: str | None) -> str:
    if not dt_str or dt_str in ("-", None, ""):
        return "-"
    try:
        import pytz

        dt_str_clean = str(dt_str).split(".")[0]
        dt = datetime.fromisoformat(dt_str_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        moscow_tz = pytz.timezone("Europe/Moscow")
        dt = dt.astimezone(moscow_tz)
        months_ru = [
            "янв.",
            "фев.",
            "мар.",
            "апр.",
            "май",
            "июн.",
            "июл.",
            "авг.",
            "сен.",
            "окт.",
            "ноя.",
            "дек.",
        ]
        month = months_ru[dt.month - 1]
        nbsp = "\u00a0"
        return f"{dt.day}{nbsp}{month}{nbsp}{dt.year},{nbsp}{dt:%H:%M}"
    except Exception:
        return str(dt_str)


def user_payload(user: dict, auth_mod: Any) -> dict:
    return {
        "username": user["username"],
        "role": user["role"],
        "role_label": auth_mod.get_user_role_display(user["role"]),
        "email": user.get("email"),
    }
