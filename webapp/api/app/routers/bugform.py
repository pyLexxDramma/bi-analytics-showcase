"""Прокси отправки баг-репорта на winbot (CORS / same-origin для UI)."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.config import BUG_FORM_KEY, BUG_FORM_SUBMIT_URL

router = APIRouter(prefix="/api/bugform", tags=["bugform"])


@router.post("/submit")
async def submit_bug(request: Request) -> dict[str, Any]:
    if not BUG_FORM_SUBMIT_URL:
        raise HTTPException(status_code=503, detail="BUG_FORM_SUBMIT_URL не настроен")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Некорректный JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Ожидался объект JSON")

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
