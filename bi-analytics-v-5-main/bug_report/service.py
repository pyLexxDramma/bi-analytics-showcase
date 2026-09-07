"""Оркестрация: классификация → Trello / локальная очередь + клиентский статус."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bug_report.categories import TrelloTarget, resolve_trello_target
from bug_report.classifier import ClassificationResult, classify_bug_report
from bug_report.client_status import CLIENT_STATUS_ACCEPTED
from bug_report.notify import notify_client, status_page_url
from bug_report.settings import get_bug_report_settings
from bug_report.storage import display_ticket_no, get_bug_report, insert_bug_report, update_bug_report
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
    public_token: str = ""
    status_url: str = ""
    client_status: str = CLIENT_STATUS_ACCEPTED
    user_seq: int = 0


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
    contact_email: str = "",
    contact_telegram: str = "",
    related_report_id: int | None = None,
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
        "contact_email": contact_email,
        "contact_telegram": contact_telegram,
        "related_report_id": related_report_id,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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
    contact_email: str = "",
    contact_telegram: str = "",
    related_report_id: int | None = None,
) -> SubmitResult:
    settings = get_bug_report_settings()
    text = (user_text or "").strip()
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    contact_email = (contact_email or "").strip()
    contact_telegram = (contact_telegram or "").strip()
    if not first_name or not last_name:
        return SubmitResult(
            ok=False,
            report_id=0,
            message="Укажите имя и фамилию.",
            category="other",
            priority="medium",
            title="",
        )
    if not contact_email or "@" not in contact_email:
        return SubmitResult(
            ok=False,
            report_id=0,
            message="Укажите корректный email для уведомлений о статусе.",
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

    public_token = secrets.token_urlsafe(24)
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
        contact_email=contact_email,
        contact_telegram=contact_telegram,
        related_report_id=related_report_id,
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
            "public_token": public_token,
            "client_status": CLIENT_STATUS_ACCEPTED,
        }
    )
    saved = get_bug_report(report_id) or {}
    user_seq = display_ticket_no(saved)
    context["report_id"] = report_id
    context["user_seq"] = user_seq
    status_url = status_page_url(public_token, settings)

    classification_dict = {
        "category": classification.category,
        "priority": classification.priority,
        "title": classification.title,
        "summary": classification.summary,
        "confidence": classification.confidence,
        "source": classification.source,
    }

    def _finish_ok(
        *,
        message: str,
        trello_url: str = "",
        dry_run: bool = False,
        pipeline_status: str = "queued",
    ) -> SubmitResult:
        row = {
            "id": report_id,
            "user_seq": user_seq,
            "public_token": public_token,
            "contact_email": contact_email,
            "contact_telegram": contact_telegram,
            "client_status": CLIENT_STATUS_ACCEPTED,
        }
        notified_at = None
        if notify_client(row, kind="accepted", settings=settings):
            notified_at = _utc_now_iso()
            update_bug_report(report_id, notified_accepted_at=notified_at)
        if pipeline_status == "queued":
            update_bug_report(report_id, status="queued")
        return SubmitResult(
            ok=True,
            report_id=report_id,
            message=message,
            category=classification.category,
            priority=classification.priority,
            title=classification.title,
            trello_card_url=trello_url,
            ai_source=classification.source,
            dry_run=dry_run,
            public_token=public_token,
            status_url=status_url,
            client_status=CLIENT_STATUS_ACCEPTED,
            user_seq=user_seq,
        )

    if settings.dry_run or not settings.trello_configured:
        if settings.dry_run:
            msg = (
                f"DRY RUN: репорт №{user_seq} (#{report_id}) сохранён. "
                f"Категория: {classification.category}, источник AI: {classification.source}."
            )
        else:
            msg = (
                f"Репорт №{user_seq} (#{report_id}) сохранён локально (Trello не настроен). "
                f"Категория: {classification.category}."
            )
        return _finish_ok(message=msg, dry_run=settings.dry_run, pipeline_status="queued")

    target = resolve_trello_target(classification.category, settings)
    try:
        inbox_list = resolve_inbox_list_id(settings)
        if inbox_list:
            target = TrelloTarget(list_id=inbox_list, label_ids=target.label_ids)
        # related note in context for card body
        if related_report_id:
            context["related_report_id"] = related_report_id
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
        return _finish_ok(
            message=msg,
            trello_url=card.card_url,
            pipeline_status="sent",
        )
    except Exception as exc:
        logger.exception("bug_report Trello failed for #%s", report_id)
        update_bug_report(report_id, status="failed", error_message=str(exc))
        # всё равно выдаём токен статуса и пытаемся уведомить
        row = {
            "id": report_id,
            "user_seq": user_seq,
            "public_token": public_token,
            "contact_email": contact_email,
            "contact_telegram": contact_telegram,
        }
        if notify_client(row, kind="accepted", settings=settings):
            update_bug_report(report_id, notified_accepted_at=_utc_now_iso())
        return SubmitResult(
            ok=False,
            report_id=report_id,
            message=f"Репорт №{user_seq} сохранён, но Trello недоступен: {exc}",
            category=classification.category,
            priority=classification.priority,
            title=classification.title,
            ai_source=classification.source,
            public_token=public_token,
            status_url=status_url,
            client_status=CLIENT_STATUS_ACCEPTED,
            user_seq=user_seq,
        )
