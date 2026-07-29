from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.services.debit_credit import build_debit_credit_payload

router = APIRouter(prefix="/api/debit-credit", tags=["debit-credit"])


@router.get("")
def debit_credit_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    contractor: Optional[str] = Query(None, description="Фильтр подрядчика"),
    contract_q: Optional[str] = Query(None, description="Частичный поиск № договора"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
):
    """Пилот: дебиторская / кредиторская задолженность подрядчиков."""
    return build_debit_credit_payload(
        project=project,
        contractor=contractor,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
    )
