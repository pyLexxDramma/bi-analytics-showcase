"""Баг-репорт: submit, публичный статус, реестр «мои заявки», sync Trello."""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import BUG_FORM_KEY, BUG_FORM_SUBMIT_URL
from app.services.auth_context import require_active_user, require_admin_user
from app.services.bug_report_trello import (
    list_mine_payload,
    public_status_payload,
    run_status_sync,
    submit_bug_report_trello,
    trello_bug_report_configured,
)

router = APIRouter(prefix="/api/bugform", tags=["bugform"])


@router.post("/submit")
async def submit_bug(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Некорректный JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Ожидался объект JSON")

    if trello_bug_report_configured():
        try:
            return submit_bug_report_trello(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not BUG_FORM_SUBMIT_URL:
        raise HTTPException(status_code=503, detail="BUG_FORM_SUBMIT_URL не настроен")

    if not (payload.get("key") or "").strip():
        payload = {**payload, "key": BUG_FORM_KEY}

    try:
        async with httpx.AsyncClient(timeout=90.0, verify=False) as client:
            resp = await client.post(
                BUG_FORM_SUBMIT_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось связаться с формой баг-репортов: {exc}",
        ) from exc

    try:
        data = resp.json()
    except Exception:
        data = {"error": (resp.text or "")[:400]}

    if resp.status_code >= 400:
        detail = data.get("error") or data.get("detail") or f"upstream {resp.status_code}"
        raise HTTPException(status_code=resp.status_code, detail=detail)

    if not isinstance(data, dict):
        return {"ok": True, "raw": data}
    return data


@router.get("/status/{token}")
def bug_status(token: str) -> dict[str, Any]:
    data = public_status_payload(token)
    if not data:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    return data


@router.get("/mine")
def my_bugs(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = require_active_user(authorization)
    username = str(user.get("username") or "").strip()
    return list_mine_payload(username)


@router.post("/sync-statuses")
def sync_statuses(
    authorization: str | None = Header(default=None),
    x_bug_sync_key: str | None = Header(default=None, alias="X-Bug-Sync-Key"),
) -> dict[str, Any]:
    """Синхронизация статусов из Trello. Admin bearer или BUG_REPORT_SYNC_KEY."""
    sync_key = (os.environ.get("BUG_REPORT_SYNC_KEY") or "").strip()
    header_key = (x_bug_sync_key or "").strip()
    if sync_key and header_key and header_key == sync_key:
        return run_status_sync()
    require_admin_user(authorization)
    return run_status_sync()
