"""Trello bug report через модуль [main]/bug_report (ai.conall.ru prod)."""

from __future__ import annotations

import base64
import logging
from typing import Any

from app.services.core_bridge import ensure_core_path

logger = logging.getLogger(__name__)


def trello_bug_report_configured() -> bool:
    try:
        ensure_core_path()
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
    ensure_core_path()
    from bug_report.service import submit_bug_report

    reporter = str(payload.get("reporter") or "").strip()
    username = reporter.split("(")[0].strip() if reporter else "anonymous"
    browser = str(payload.get("browser") or "")
    theme = "dark" if "тёмн" in browser.lower() else "light"

    text = _compose_text(payload) or str(payload.get("actual") or "Bug report").strip()
    result = submit_bug_report(
        user_text=text,
        username=username,
        user_role=str(payload.get("role") or ""),
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
