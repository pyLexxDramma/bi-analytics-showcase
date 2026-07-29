from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.deviation_reasons import build_deviation_reasons_payload

router = APIRouter(prefix="/api/deviation-reasons", tags=["deviation-reasons"])


@router.get("")
def deviation_reasons_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    block: Optional[str] = Query(None, description="Функциональный блок"),
    reason: Optional[str] = Query(None, description="Причина отклонения"),
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD)"),
):
    return build_deviation_reasons_payload(
        project=project,
        block=block,
        reason=reason,
        date_from=date_from,
        date_to=date_to,
    )
