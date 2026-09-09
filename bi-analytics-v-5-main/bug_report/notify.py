"""Уведомления клиенту: email (обязательный канал) + опционально Telegram."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import requests

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


def _send_telegram(settings: BugReportSettings, *, chat_ref: str, text: str) -> bool:
    token = (settings.telegram_bot_token or "").strip()
    chat_ref = (chat_ref or "").strip()
    if not token or not chat_ref:
        return False
    # Только числовой chat_id (бот не шлёт по @username без /start).
    chat_id = chat_ref.lstrip("@") if chat_ref.lstrip("@").isdigit() else ""
    if not chat_id and chat_ref.lstrip("-").isdigit():
        chat_id = chat_ref
    if not chat_id:
        logger.info("bug_report notify: telegram skipped (need numeric chat_id), got %r", chat_ref)
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning("bug_report telegram HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("bug_report telegram failed: %s", exc)
        return False


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
    """kind: accepted | in_progress | ready | on_hold. True если хотя бы один канал отработал."""
    settings = settings or get_bug_report_settings()
    report_id = row.get("id")
    ticket_no = row.get("user_seq") or report_id
    token = str(row.get("public_token") or "")
    link = status_page_url(token, settings)
    email = str(row.get("contact_email") or "").strip()
    tg = str(row.get("contact_telegram") or "").strip()

    if kind == "accepted":
        subject = f"Заявка №{ticket_no} принята"
        body = (
            f"Заявка №{ticket_no} принята.\n"
            f"Напишем, когда будет готово к проверке"
            f"{' или если понадобятся уточнения' if True else ''}.\n"
        )
        if link:
            body += f"\nСтатус заявки: {link}\n"
    elif kind == "in_progress":
        subject = f"Заявка №{ticket_no} взята в работу"
        body = (
            f"Заявка №{ticket_no} взята в работу.\n"
            "Напишем, когда будет готово к проверке "
            "или если понадобятся уточнения.\n"
        )
        if link:
            body += f"\nСтатус заявки: {link}\n"
        body = _append_team_comment(body, comment)
    elif kind == "ready":
        subject = f"Заявка №{ticket_no} готова, можно проверить"
        body = f"Заявка №{ticket_no} готова, можно проверить.\n"
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
        if link:
            body += f"\nСтатус: {link}\n"
        body = _append_team_comment(body, comment)
    else:
        return False

    ok_mail = _send_smtp(settings, to_email=email, subject=subject, body=body) if email else False
    ok_tg = _send_telegram(settings, chat_ref=tg, text=f"{subject}\n\n{body}") if tg else False
    if email and not ok_mail:
        logger.warning(
            "bug_report notify: email FAILED kind=%s report=%s to_domain=%s",
            kind,
            report_id,
            email.split("@")[-1] if "@" in email else "?",
        )
    elif ok_mail:
        logger.info(
            "bug_report notify: email OK kind=%s report=%s to_domain=%s",
            kind,
            report_id,
            email.split("@")[-1] if "@" in email else "?",
        )
    # Письмо — основной канал; TG только дополняет. Не считаем успехом один TG без почты.
    if email:
        return bool(ok_mail)
    return bool(ok_tg)
