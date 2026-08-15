from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.debit_credit import build_debit_credit_payload

router = APIRouter(prefix="/api/debit-credit", tags=["debit-credit"], dependencies=[Depends(require_report_access("debit-credit"))])


@router.get("")
def debit_credit_report(
    user: dict = Depends(require_report_access("debit-credit")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    contractor: Optional[str] = Query(None, description="Фильтр подрядчика"),
    contract_q: Optional[str] = Query(None, description="Частичный поиск № договора"),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    display_view: str = Query("Без группировки", description="Вид отображения графика"),
):
    selected = [item for item in (projects or []) if item and item.strip() and item.strip() != "Все"]
    if not selected and project and project.strip() and project.strip() != "Все":
        selected = parse_project_pipe(project) or [project.strip()]
    selected = clamp_projects_list(user, selected)
    allowed = allowed_projects_for_user(user)
    if allowed is not None and not selected and not allowed:
        project_arg = "__no_access__"
    else:
        project_arg = "|".join(selected) if selected else None
    return build_debit_credit_payload(
        project=project_arg,
        contractor=contractor,
        contract_q=contract_q,
        date_from=date_from,
        date_to=date_to,
        display_view=display_view,
    )
