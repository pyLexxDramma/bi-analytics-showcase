from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access

from app.services.debit_credit import build_debit_credit_payload

router = APIRouter(prefix="/api/debit-credit", tags=["debit-credit"], dependencies=[Depends(require_report_access("debit-credit"))])


@router.get("")
def debit_credit_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    contractor: Optional[str] = Query(None, description="Фильтр подрядчика"),
    contract_q: Optional[str] = Query(None, description="Частичный поиск № договора"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    display_view: str = Query("Без группировки", description="Вид отображения графика"),
):
    return build_debit_credit_payload(
        project=project,
        contractor=contractor,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
        display_view=display_view,
    )
