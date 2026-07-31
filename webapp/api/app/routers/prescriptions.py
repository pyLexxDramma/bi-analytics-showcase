from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.prescriptions import build_prescriptions_payload

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


@router.get("")
def prescriptions_report(
    projects: Optional[str] = Query(None, description="Проекты через запятую"),
    contractors: Optional[str] = Query(None, description="Подрядчики через запятую"),
    contract_q: Optional[str] = Query(None, description="Частичный поиск № договора"),
    date_from: Optional[date] = Query(None, description="Дата выдачи с"),
    date_to: Optional[date] = Query(None, description="Дата выдачи по"),
    hide_resolved: bool = Query(False, description="Скрыть снятые (KrStateID=13)"),
):
    """Предписания по подрядчикам (TESSA id + task)."""
    return build_prescriptions_payload(
        projects=projects,
        contractors=contractors,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
        hide_resolved=hide_resolved,
    )
