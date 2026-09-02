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


# Колонка для новых клиентских заявок (разбор / апрув).
INBOX_LIST_NAMES = ("анализ", "analysis", "triage", "на разбор")


def resolve_inbox_list_id(settings: BugReportSettings) -> str:
    """id колонки «Анализ» на доске: сначала по имени, иначе TRELLO_LIST_TRIAGE."""
    fallback = (settings.trello_list_triage or "").strip()
    board_id = (settings.trello_board_id or "").strip()
    if not board_id:
        return fallback
    try:
        resp = requests.get(
            f"{TRELLO_API}/boards/{board_id}/lists",
            params={**_auth_params(settings), "fields": "name,id,closed"},
            timeout=(3.0, 12.0),
        )
        resp.raise_for_status()
        lists = resp.json()
    except requests.RequestException as exc:
        logger.warning("bug_report: cannot list Trello columns: %s", exc)
        return fallback
    if not isinstance(lists, list):
        return fallback
    open_lists = [x for x in lists if isinstance(x, dict) and not x.get("closed")]
    by_norm = {
        str(x.get("name") or "").strip().casefold(): str(x.get("id") or "").strip()
        for x in open_lists
    }
    for want in INBOX_LIST_NAMES:
        found = by_norm.get(want)
        if found:
            if fallback and found != fallback:
                logger.info(
                    "bug_report: inbox list «%s» id=%s (env TRIAGE was %s)",
                    want,
                    found,
                    fallback,
                )
            return found
    # Частичное совпадение: «Анализ заявок», «1. Анализ» и т.п.
    for name, lid in by_norm.items():
        if any(want in name for want in INBOX_LIST_NAMES) and lid:
            return lid
    logger.warning(
        "bug_report: column «Анализ» not found on board; using TRELLO_LIST_TRIAGE=%s",
        fallback or "(empty)",
    )
    return fallback


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


def _normalize_attachments(
    attachment: tuple[str, bytes, str] | None,
    attachments: list[tuple[str, bytes, str]] | None,
) -> list[tuple[str, bytes, str]]:
    items: list[tuple[str, bytes, str]] = []
    if attachments:
        items.extend(attachments)
    elif attachment:
        items.append(attachment)
    return items


def create_bug_report_card(
    *,
    settings: BugReportSettings,
    target: TrelloTarget,
    title: str,
    user_text: str,
    context: dict[str, Any],
    classification: dict[str, Any],
    attachment: tuple[str, bytes, str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> TrelloCardResult:
    list_id = (target.list_id or "").strip() or resolve_inbox_list_id(settings)
    if not list_id:
        raise ValueError(
            "Trello list_id is not configured (нужна колонка «Анализ» или TRELLO_LIST_TRIAGE)"
        )
    params: dict[str, Any] = {
        **_auth_params(settings),
        "idList": list_id,
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
    if not card_id:
        raise ValueError("Trello returned empty card id")
    for filename, content, mime in _normalize_attachments(attachment, attachments):
        try:
            requests.post(
                f"{TRELLO_API}/cards/{card_id}/attachments",
                params=_auth_params(settings),
                files={"file": (filename, content, mime or "application/octet-stream")},
                timeout=(3.0, 30.0),
            ).raise_for_status()
        except requests.RequestException as exc:
            logger.warning(
                "bug_report Trello attachment failed for %s (%s): %s",
                card_id,
                filename,
                exc,
            )
    return TrelloCardResult(card_id=card_id, card_url=card_url)
