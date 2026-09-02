"""Клиент Trello REST API для карточек баг-репорта."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from bug_report.categories import category_display, priority_display, TrelloTarget
from bug_report.settings import BugReportSettings

logger = logging.getLogger(__name__)

TRELLO_API = "https://api.trello.com/1"


@dataclass(frozen=True)
class TrelloCardResult:
    card_id: str
    card_url: str


def _auth_params(settings: BugReportSettings) -> dict[str, str]:
    return {"key": settings.trello_api_key, "token": settings.trello_token}


def _format_description(
    *,
    user_text: str,
    context: dict[str, Any],
    classification: dict[str, Any],
) -> str:
    fio = f"{(context.get('first_name') or '').strip()} {(context.get('last_name') or '').strip()}".strip()
    lines = [
        "## Описание от пользователя",
        user_text.strip() or "—",
        "",
        "## Автоклассификация",
        f"- Категория: **{category_display(classification.get('category', 'other'))}**",
        f"- Приоритет: **{priority_display(classification.get('priority', 'medium'))}**",
        f"- Уверенность AI: {classification.get('confidence', '—')}",
        f"- Источник: {classification.get('source', '—')}",
        "",
        f"**{classification.get('title', '')}**",
        "",
        classification.get("summary", ""),
        "",
        "## Контекст",
        f"- ФИО: {fio or '—'}",
        f"- Логин: {context.get('username', '—')} ({context.get('user_role', '—')})",
        f"- Вкладка: {context.get('report_tab', '—')}",
        f"- Тема: {context.get('theme', '—')}",
        f"- URL: {context.get('page_url', '—')}",
        f"- version_id: {context.get('version_id', '—')}",
        f"- Сборка: {context.get('app_build', '—')}",
        f"- report_id локальный: #{context.get('report_id', '—')}",
    ]
    return "\n".join(lines)


def create_bug_report_card(
    *,
    settings: BugReportSettings,
    target: TrelloTarget,
    title: str,
    user_text: str,
    context: dict[str, Any],
    classification: dict[str, Any],
    attachment: tuple[str, bytes, str] | None = None,
) -> TrelloCardResult:
    if not target.list_id:
        raise ValueError("Trello list_id is not configured")
    params: dict[str, Any] = {
        **_auth_params(settings),
        "idList": target.list_id,
        "name": title[:160],
        "desc": _format_description(
            user_text=user_text,
            context=context,
            classification=classification,
        ),
    }
    if target.label_ids:
        params["idLabels"] = ",".join(target.label_ids)
    resp = requests.post(
        f"{TRELLO_API}/cards",
        params=params,
        timeout=(3.0, 20.0),
    )
    resp.raise_for_status()
    data = resp.json()
    card_id = str(data.get("id", ""))
    card_url = str(data.get("url", "") or data.get("shortUrl", ""))
    if attachment and card_id:
        filename, content, mime = attachment
        try:
            requests.post(
                f"{TRELLO_API}/cards/{card_id}/attachments",
                params=_auth_params(settings),
                files={"file": (filename, content, mime or "application/octet-stream")},
                timeout=(3.0, 30.0),
            ).raise_for_status()
        except requests.RequestException as exc:
            logger.warning("bug_report Trello attachment failed for %s: %s", card_id, exc)
    if not card_id:
        raise ValueError("Trello returned empty card id")
    return TrelloCardResult(card_id=card_id, card_url=card_url)
