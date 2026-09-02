"""Trello bug report через модуль [main]/bug_report (ai.conall.ru prod)."""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from app.services.core_bridge import ensure_core_path

logger = logging.getLogger(__name__)


def _prepare_bug_report_db() -> None:
    """В Docker core смонтирован :ro — пишем bug_reports в BI_USERS_DB."""
    ensure_core_path()
    users_db = os.environ.get("BI_USERS_DB", "").strip()
    if not users_db:
        return
    import config as core_config

    core_config.DB_PATH = users_db
    from bug_report.storage import ensure_bug_reports_table

    ensure_bug_reports_table()


def trello_bug_report_configured() -> bool:
    try:
        _prepare_bug_report_db()
        from bug_report.settings import get_bug_report_settings

        return get_bug_report_settings().trello_configured
    except Exception as exc:
        logger.warning("bug_report settings: %s", exc)
        return False


def _compose_text(payload: dict[str, Any]) -> str:
    lines = [
        f"**{payload.get('title', '').strip()}**" if payload.get("title") else "",
        f"Тип: {payload.get('btype', '')} / {payload.get('subtype', '')}",
        f"Серьёзность: {payload.get('severity', '')}",
        "",
        "**Фактическое поведение**",
        (payload.get("actual") or "").strip(),
        "",
        "**Ожидаемое**",
        (payload.get("expected") or "").strip(),
        "",
        "**Шаги воспроизведения**",
        (payload.get("steps") or "").strip(),
    ]
    return "\n".join(x for x in lines if x is not None).strip()


def _first_attachment(payload: dict[str, Any]) -> tuple[str, bytes, str] | None:
    items = payload.get("attachments")
    if not isinstance(items, list) or not items:
        return None
    raw = items[0]
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "screenshot.png")
    b64 = str(raw.get("data") or raw.get("content") or "")
    if not b64:
        return None
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    try:
        content = base64.b64decode(b64)
    except Exception:
        return None
    mime = str(raw.get("type") or raw.get("mime") or "image/png")
    return name, content, mime


def submit_bug_report_trello(payload: dict[str, Any]) -> dict[str, Any]:
    _prepare_bug_report_db()
    from bug_report.service import submit_bug_report

    reporter = str(payload.get("reporter") or "").strip()
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise ValueError("Укажите имя и фамилию.")
    username_raw = str(payload.get("username") or reporter or "anonymous").strip()
    username = username_raw.split("(")[0].strip() if username_raw else "anonymous"
    browser = str(payload.get("browser") or "")
    theme = "dark" if "тёмн" in browser.lower() else "light"

    text = _compose_text(payload) or str(payload.get("actual") or "Bug report").strip()
    result = submit_bug_report(
        user_text=text,
        username=username,
        user_role=str(payload.get("role") or ""),
        first_name=first_name,
        last_name=last_name,
        report_tab=f"{payload.get('menugroup', '')} / {payload.get('report', '')}".strip(" /"),
        page_url=str(payload.get("filters") or ""),
        theme=theme,
        app_build=str(payload.get("contour") or "webapp"),
        attachment=_first_attachment(payload),
    )
    if not result.ok:
        raise RuntimeError(result.message)
    return {
        "ok": True,
        "bug_id": str(result.report_id),
        "category": result.category,
        "trello_url": result.trello_card_url,
        "message": result.message,
    }
