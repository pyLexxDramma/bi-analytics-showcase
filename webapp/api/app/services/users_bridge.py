from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from app.config import DEMO_ADMIN_PASSWORD, USERS_DB_PATH
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

    auth.init_db(quiet=True)
    if seed:
        conn = sqlite3.connect(str(USERS_DB_PATH))
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = int(cur.fetchone()[0])
            if count == 0:
                auth.create_user(
                    "admin",
                    DEMO_ADMIN_PASSWORD,
                    "superadmin",
                    "admin@example.com",
                    "system",
                )
            else:
                ok, _ = auth.authenticate("admin", DEMO_ADMIN_PASSWORD)
                if not ok:
                    cur.execute(
                        "SELECT id FROM users WHERE username = ?",
                        ("admin",),
                    )
                    if cur.fetchone():
                        ph = auth.hash_password(DEMO_ADMIN_PASSWORD)
                        cur.execute(
                            "UPDATE users SET password_hash = ? WHERE username = ?",
                            (ph, "admin"),
                        )
                        conn.commit()
        finally:
            conn.close()
    if not _prepared:
        _prepared = True


def import_auth() -> Any:
    ensure_users_db()
    import auth  # type: ignore

    return auth


def import_filters() -> Any:
    ensure_users_db()
    import filters  # type: ignore

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
