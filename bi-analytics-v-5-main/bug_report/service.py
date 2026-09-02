"""Оркестрация: классификация → Trello / локальная очередь."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bug_report.categories import TrelloTarget, resolve_trello_target
from bug_report.classifier import ClassificationResult, classify_bug_report
from bug_report.settings import get_bug_report_settings
from bug_report.storage import insert_bug_report, update_bug_report
from bug_report.trello_client import create_bug_report_card, resolve_inbox_list_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubmitResult:
    ok: bool
    report_id: int
    message: str
    category: str
    priority: str
    title: str
    trello_card_url: str = ""
    ai_source: str = ""
    dry_run: bool = False


def _build_context(
    *,
    username: str,
    user_role: str,
    first_name: str,
    last_name: str,
    report_tab: str,
    page_url: str,
    theme: str,
    version_id: int | None,
    app_build: str,
    report_id: int | None = None,
) -> dict[str, Any]:
    return {
        "username": username,
        "user_role": user_role,
        "first_name": first_name,
        "last_name": last_name,
        "report_tab": report_tab,
        "page_url": page_url,
        "theme": theme,
        "version_id": version_id,
        "app_build": app_build,
        "report_id": report_id,
    }


def submit_bug_report(
    *,
    user_text: str,
    username: str,
    user_role: str,
    first_name: str = "",
    last_name: str = "",
    report_tab: str = "",
    page_url: str = "",
    theme: str = "",
    version_id: int | None = None,
    app_build: str = "",
    attachment: tuple[str, bytes, str] | None = None,
    attachments: list[tuple[str, bytes, str]] | None = None,
) -> SubmitResult:
    settings = get_bug_report_settings()
    text = (user_text or "").strip()
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    if not first_name or not last_name:
        return SubmitResult(
            ok=False,
            report_id=0,
            message="Укажите имя и фамилию.",
            category="other",
            priority="medium",
            title="",
        )
    if not text:
        return SubmitResult(
            ok=False,
            report_id=0,
            message="Введите описание проблемы.",
            category="other",
            priority="medium",
            title="",
        )

    context = _build_context(
        username=username,
        user_role=user_role,
        first_name=first_name,
        last_name=last_name,
        report_tab=report_tab,
        page_url=page_url,
        theme=theme,
        version_id=version_id,
        app_build=app_build,
    )
    classification: ClassificationResult = classify_bug_report(text, context)
    report_id = insert_bug_report(
        {
            **context,
            "user_text": text,
            "category": classification.category,
            "priority": classification.priority,
            "ai_title": classification.title,
            "ai_summary": classification.summary,
            "ai_confidence": classification.confidence,
            "ai_source": classification.source,
            "status": "classified",
            "raw_ai_response": classification.raw_response,
        }
    )
    context["report_id"] = report_id

    classification_dict = {
        "category": classification.category,
        "priority": classification.priority,
        "title": classification.title,
        "summary": classification.summary,
        "confidence": classification.confidence,
        "source": classification.source,
    }

    if settings.dry_run or not settings.trello_configured:
        update_bug_report(report_id, status="queued")
        if settings.dry_run:
            msg = (
                f"DRY RUN: репорт #{report_id} сохранён. "
                f"Категория: {classification.category}, источник AI: {classification.source}."
            )
        else:
            msg = (
                f"Репорт #{report_id} сохранён локально (Trello не настроен). "
                f"Категория: {classification.category}."
            )
        return SubmitResult(
            ok=True,
            report_id=report_id,
            message=msg,
            category=classification.category,
            priority=classification.priority,
            title=classification.title,
            ai_source=classification.source,
            dry_run=settings.dry_run,
        )

    target = resolve_trello_target(classification.category, settings)
    try:
        inbox_list = resolve_inbox_list_id(settings)
        if inbox_list:
            target = TrelloTarget(list_id=inbox_list, label_ids=target.label_ids)
        card = create_bug_report_card(
            settings=settings,
            target=target,
            title=classification.title,
            user_text=text,
            context=context,
            classification=classification_dict,
            attachment=attachment,
            attachments=attachments,
        )
        update_bug_report(
            report_id,
            status="sent",
            trello_card_id=card.card_id,
            trello_card_url=card.card_url,
        )
        msg = f"Отправлено в Trello: {classification.title}"
        if card.card_url:
            msg += f" ({card.card_url})"
        return SubmitResult(
            ok=True,
            report_id=report_id,
            message=msg,
            category=classification.category,
            priority=classification.priority,
            title=classification.title,
            trello_card_url=card.card_url,
            ai_source=classification.source,
        )
    except Exception as exc:
        logger.exception("bug_report Trello failed for #%s", report_id)
        update_bug_report(report_id, status="failed", error_message=str(exc))
        return SubmitResult(
            ok=False,
            report_id=report_id,
            message=f"Репорт #{report_id} сохранён, но Trello недоступен: {exc}",
            category=classification.category,
            priority=classification.priority,
            title=classification.title,
            ai_source=classification.source,
        )
