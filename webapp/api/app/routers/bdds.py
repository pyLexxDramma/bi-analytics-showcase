from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.bdds import build_bdds_payload

router = APIRouter(prefix="/api/bdds", tags=["bdds"])


@router.get("")
def bdds_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    view: str = Query("monthly", pattern="^(monthly|cumulative)$"),
):
    return build_bdds_payload(
        project=project,
        date_from=date_from,
        date_to=date_to,
        view=view,
    )
