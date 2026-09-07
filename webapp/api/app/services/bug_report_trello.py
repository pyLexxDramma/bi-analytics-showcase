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
    ]
    related = str(payload.get("related_report_id") or "").strip()
    if related:
        lines.extend(["", f"**Связана с заявкой №{related}** (повтор после проверки)"])
    steps = (payload.get("steps") or "").strip()
    if steps:
        lines.extend(["", "**Шаги воспроизведения**", steps])
    repro = (payload.get("repro") or "").strip()
    if repro:
        lines.append(f"Воспроизводится: {repro}")
    conditions = (payload.get("conditions") or "").strip()
    if conditions:
        lines.append(f"Условия: {conditions}")
    filedesc = (payload.get("filedesc") or "").strip()
    if filedesc:
        lines.extend(["", "**Вложения**", filedesc])
    return "\n".join(x for x in lines if x is not None).strip()


def _decode_attachment(raw: dict[str, Any]) -> tuple[str, bytes, str] | None:
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


def _all_attachments(payload: dict[str, Any]) -> list[tuple[str, bytes, str]]:
    items = payload.get("attachments")
    if not isinstance(items, list) or not items:
        return []
    out: list[tuple[str, bytes, str]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        decoded = _decode_attachment(raw)
        if decoded:
            out.append(decoded)
    return out


def _parse_related_id(payload: dict[str, Any], username: str) -> int | None:
    raw = payload.get("related_report_id")
    if raw is None or raw == "":
        return None
    from bug_report.storage import resolve_related_report_id

    return resolve_related_report_id(username, raw)


def submit_bug_report_trello(payload: dict[str, Any]) -> dict[str, Any]:
    _prepare_bug_report_db()
    from bug_report.service import submit_bug_report

    reporter = str(payload.get("reporter") or "").strip()
    first_name = str(payload.get("first_name") or "").strip()
    last_name = str(payload.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise ValueError("Укажите имя и фамилию.")
    contact_email = str(payload.get("contact_email") or payload.get("email") or "").strip()
    if not contact_email or "@" not in contact_email:
        raise ValueError("Укажите корректный email для уведомлений.")
    contact_telegram = str(payload.get("contact_telegram") or payload.get("telegram") or "").strip()
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
        attachments=_all_attachments(payload),
        contact_email=contact_email,
        contact_telegram=contact_telegram,
        related_report_id=_parse_related_id(payload, username),
    )
    if not result.ok:
        raise RuntimeError(result.message)
    return {
        "ok": True,
        "bug_id": str(result.user_seq or result.report_id),
        "internal_id": str(result.report_id),
        "user_seq": result.user_seq or result.report_id,
        "category": result.category,
        "trello_url": result.trello_card_url,
        "message": result.message,
        "public_token": result.public_token,
        "status_url": result.status_url,
        "client_status": result.client_status,
    }


def public_status_payload(token: str) -> dict[str, Any] | None:
    _prepare_bug_report_db()
    from bug_report.client_status import client_status_label
    from bug_report.status_sync import sync_one_report
    from bug_report.storage import display_ticket_no, get_bug_report, get_bug_report_by_token

    row = get_bug_report_by_token(token)
    if not row:
        return None
    if row.get("trello_card_id"):
        try:
            sync_one_report(row)
            row = get_bug_report_by_token(token) or row
        except Exception as exc:
            logger.warning("status sync on read: %s", exc)
    title = (row.get("ai_title") or "").strip()
    summary = (row.get("ai_summary") or "").strip()
    user_text = (row.get("user_text") or "").strip()
    preview = summary or (user_text[:400] + ("…" if len(user_text) > 400 else ""))
    status = str(row.get("client_status") or "accepted")
    ticket_no = display_ticket_no(row)
    related_no = None
    related_id = row.get("related_report_id")
    if related_id:
        related_row = get_bug_report(int(related_id))
        related_no = display_ticket_no(related_row) if related_row else int(related_id)
    return {
        "ok": True,
        "bug_id": ticket_no,
        "internal_id": row.get("id"),
        "user_seq": ticket_no,
        "username": row.get("username") or "",
        "status": status,
        "status_label": client_status_label(status),
        "title": title,
        "preview": preview,
        "created_at": row.get("created_at"),
        "related_report_id": related_no,
        "report_tab": row.get("report_tab") or "",
    }


def list_mine_payload(username: str) -> dict[str, Any]:
    _prepare_bug_report_db()
    from bug_report.client_status import client_status_label
    from bug_report.notify import status_page_url
    from bug_report.storage import display_ticket_no, list_bug_reports_for_user

    items = []
    for row in list_bug_reports_for_user(username):
        status = str(row.get("client_status") or "accepted")
        token = str(row.get("public_token") or "")
        ticket_no = display_ticket_no(row)
        items.append(
            {
                "bug_id": ticket_no,
                "user_seq": ticket_no,
                "internal_id": row.get("id"),
                "created_at": row.get("created_at"),
                "title": (row.get("ai_title") or "").strip() or f"Заявка №{ticket_no}",
                "status": status,
                "status_label": client_status_label(status),
                "report_tab": row.get("report_tab") or "",
                "status_url": status_page_url(token) if token else "",
                "public_token": token,
            }
        )
    return {"ok": True, "items": items, "username": username}


def run_status_sync() -> dict[str, Any]:
    _prepare_bug_report_db()
    from bug_report.status_sync import sync_all_open_reports

    return sync_all_open_reports()
