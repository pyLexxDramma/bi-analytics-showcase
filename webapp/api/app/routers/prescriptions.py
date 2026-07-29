from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.prescriptions import build_prescriptions_payload

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


@router.get("")
def prescriptions_report(
    project: Optional[str] = Query(None, description="Фильтр проекта (ObjectName)"),
    contractor: Optional[str] = Query(None, description="Фильтр подрядчика (CONTR)"),
    contract_q: Optional[str] = Query(None, description="Частичный поиск № договора"),
    date_from: Optional[date] = Query(None, description="Дата выдачи с"),
    date_to: Optional[date] = Query(None, description="Дата выдачи по"),
    hide_resolved: bool = Query(False, description="Скрыть снятые (KrStateID=13)"),
):
    """Предписания по подрядчикам (TESSA id + task)."""
    return build_prescriptions_payload(
        project=project,
        contractor=contractor,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
        hide_resolved=hide_resolved,
    )
