from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.bdr import build_bdr_payload

router = APIRouter(prefix="/api/bdr", tags=["bdr"])


@router.get("")
def bdr_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$"),
):
    return build_bdr_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        view=view,
    )
