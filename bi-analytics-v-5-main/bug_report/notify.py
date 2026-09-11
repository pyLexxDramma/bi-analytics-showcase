"""Уведомления клиенту по email."""

from __future__ import annotations

import logging
import re
import smtplib
from email.message import EmailMessage
from typing import Any

from bug_report.client_status import client_status_label
from bug_report.settings import BugReportSettings, get_bug_report_settings

logger = logging.getLogger(__name__)


def status_page_url(token: str, settings: BugReportSettings | None = None) -> str:
    settings = settings or get_bug_report_settings()
    base = (settings.public_base_url or "").rstrip("/")
    tok = (token or "").strip()
    if not base or not tok:
        return ""
    return f"{base}/bug-status/{tok}"


def _send_smtp(settings: BugReportSettings, *, to_email: str, subject: str, body: str) -> bool:
    host = (settings.smtp_host or "").strip()
    if not host or not to_email:
        logger.info("bug_report notify: SMTP not configured, skip email to %s", to_email)
        return False
    port = int(settings.smtp_port or 587)
    from_addr = (settings.smtp_from or settings.smtp_user or "noreply@localhost").strip()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_email.strip()
    msg.set_content(body)
    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                if settings.smtp_starttls:
                    smtp.starttls()
                    smtp.ehlo()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        return True
    except Exception as exc:
        logger.warning("bug_report notify email failed: %s", exc)
        return False


def _plain(text: str) -> str:
    """Убрать лёгкий markdown (**bold**) для читаемого plain-text письма."""
    t = (text or "").strip()
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    return t.strip()


def _ticket_brief_block(row: dict[str, Any]) -> str:
    """Блоки КРАТКО / ОПИСАНИЕ — как на странице статуса."""
    title = _plain(str(row.get("ai_title") or row.get("title") or "").strip())
    summary = _plain(str(row.get("ai_summary") or "").strip())
    user_text = _plain(str(row.get("user_text") or "").strip())
    description = summary or user_text
    if len(description) > 1500:
        description = description[:1500].rstrip() + "…"
    parts: list[str] = []
    if title:
        parts.append(f"КРАТКО:\n{title}")
    if description:
        parts.append(f"ОПИСАНИЕ:\n{description}")
    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts) + "\n"


def _append_team_comment(body: str, comment: str | None) -> str:
    text = (comment or "").strip()
    if not text:
        return body
    return body.rstrip() + f"\n\nКомментарий команды:\n{text}\n"


def notify_client(
    row: dict[str, Any],
    *,
    kind: str,
    comment: str | None = None,
    settings: BugReportSettings | None = None,
) -> bool:
    """kind: accepted | in_progress | ready | on_hold. True если письмо ушло."""
    settings = settings or get_bug_report_settings()
    report_id = row.get("id")
    ticket_no = row.get("user_seq") or report_id
    token = str(row.get("public_token") or "")
    link = status_page_url(token, settings)
    email = str(row.get("contact_email") or "").strip()
    brief = _ticket_brief_block(row)

    if kind == "accepted":
        subject = f"Заявка №{ticket_no} принята"
        body = (
            f"Заявка №{ticket_no} принята.\n"
            "Напишем, когда будет готово к проверке или если понадобятся уточнения.\n"
        )
        body += brief
        if link:
            body += f"\nСтатус заявки: {link}\n"
    elif kind == "in_progress":
        subject = f"Заявка №{ticket_no} взята в работу"
        body = (
            f"Заявка №{ticket_no} взята в работу.\n"
            "Напишем, когда будет готово к проверке "
            "или если понадобятся уточнения.\n"
        )
        body += brief
        if link:
            body += f"\nСтатус заявки: {link}\n"
        body = _append_team_comment(body, comment)
    elif kind == "ready":
        subject = f"Заявка №{ticket_no} готова, можно проверить"
        body = f"Заявка №{ticket_no} готова, можно проверить.\n"
        body += brief
        if link:
            body += f"\nОткрыть статус: {link}\n"
        body = _append_team_comment(body, comment)
        body += (
            "\nЕсли после проверки что-то не так — оформите новую заявку "
            f"и укажите номер старой (№{ticket_no}).\n"
        )
    elif kind == "on_hold":
        subject = f"Заявка №{ticket_no}: ждём вас / данные"
        body = (
            f"По заявке №{ticket_no} нужна информация с вашей стороны "
            f"(статус: {client_status_label('on_hold')}).\n"
            "Пожалуйста, ответьте команде BI или оформите уточнение.\n"
        )
        body += brief
        if link:
            body += f"\nСтатус: {link}\n"
        body = _append_team_comment(body, comment)
    else:
        return False

    if not email:
        logger.warning("bug_report notify: no email kind=%s report=%s", kind, report_id)
        return False
    ok = _send_smtp(settings, to_email=email, subject=subject, body=body)
    if ok:
        logger.info(
            "bug_report notify: email OK kind=%s report=%s to_domain=%s",
            kind,
            report_id,
            email.split("@")[-1] if "@" in email else "?",
        )
    else:
        logger.warning(
            "bug_report notify: email FAILED kind=%s report=%s to_domain=%s",
            kind,
            report_id,
            email.split("@")[-1] if "@" in email else "?",
        )
    return ok
