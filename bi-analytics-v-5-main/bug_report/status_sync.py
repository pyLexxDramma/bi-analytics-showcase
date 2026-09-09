"""Синхронизация client_status из колонки Trello + уведомления."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from bug_report.client_status import (
    CLIENT_STATUS_IN_PROGRESS,
    CLIENT_STATUS_ON_HOLD,
    CLIENT_STATUS_READY,
    map_trello_list_to_client_status,
)
from bug_report.notify import notify_client
from bug_report.settings import get_bug_report_settings
from bug_report.storage import list_bug_reports_with_trello, update_bug_report
from bug_report.trello_client import TRELLO_API, _auth_params

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _fetch_card_list_name(card_id: str) -> str | None:
    settings = get_bug_report_settings()
    if not settings.trello_configured:
        return None
    try:
        resp = requests.get(
            f"{TRELLO_API}/cards/{card_id}",
            params={**_auth_params(settings), "fields": "idList,name"},
            timeout=(3.0, 12.0),
        )
        resp.raise_for_status()
        data = resp.json()
        list_id = str(data.get("idList") or "")
        if not list_id:
            return None
        resp2 = requests.get(
            f"{TRELLO_API}/lists/{list_id}",
            params={**_auth_params(settings), "fields": "name"},
            timeout=(3.0, 12.0),
        )
        resp2.raise_for_status()
        return str(resp2.json().get("name") or "")
    except Exception as exc:
        logger.warning("bug_report sync: card %s: %s", card_id, exc)
        return None


def sync_one_report(row: dict[str, Any]) -> dict[str, Any]:
    """Обновить client_status одной заявки; при смене — in_progress/ready/on_hold."""
    card_id = str(row.get("trello_card_id") or "").strip()
    if not card_id:
        return {"id": row.get("id"), "changed": False, "reason": "no_card"}
    list_name = _fetch_card_list_name(card_id)
    if list_name is None:
        return {"id": row.get("id"), "changed": False, "reason": "fetch_failed"}
    new_status = map_trello_list_to_client_status(list_name)
    old_status = str(row.get("client_status") or "accepted")
    if new_status == old_status:
        return {"id": row.get("id"), "changed": False, "status": new_status}

    update_bug_report(int(row["id"]), client_status=new_status)
    row = {**row, "client_status": new_status}
    notified = None
    now = _utc_now_iso()
    if new_status == CLIENT_STATUS_IN_PROGRESS and not row.get("notified_in_progress_at"):
        if notify_client(row, kind="in_progress"):
            update_bug_report(int(row["id"]), notified_in_progress_at=now)
            notified = "in_progress"
    elif new_status == CLIENT_STATUS_READY and not row.get("notified_ready_at"):
        if notify_client(row, kind="ready"):
            update_bug_report(int(row["id"]), notified_ready_at=now)
            notified = "ready"
    elif new_status == CLIENT_STATUS_ON_HOLD and not row.get("notified_on_hold_at"):
        if notify_client(row, kind="on_hold"):
            update_bug_report(int(row["id"]), notified_on_hold_at=now)
            notified = "on_hold"
    return {
        "id": row.get("id"),
        "changed": True,
        "from": old_status,
        "to": new_status,
        "list": list_name,
        "notified": notified,
    }


def sync_all_open_reports(*, limit: int = 300) -> dict[str, Any]:
    rows = list_bug_reports_with_trello(limit=limit)
    results = []
    changed = 0
    for row in rows:
        # Не трогаем уже «ready» без нужды — всё равно сверим колонку
        info = sync_one_report(row)
        results.append(info)
        if info.get("changed"):
            changed += 1
    return {"ok": True, "checked": len(rows), "changed": changed, "items": results}
