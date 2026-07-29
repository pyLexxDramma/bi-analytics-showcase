from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.documentation import build_working_documentation_payload

router = APIRouter(prefix="/api/working-documentation", tags=["working-documentation"])


@router.get("")
def working_documentation_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    section: Optional[str] = Query(None, description="Шифр раздела"),
    granularity: Optional[str] = Query("week", description="day|week|month"),
    report_date: Optional[str] = Query(None, description="Отчётная дата YYYY-MM-DD"),
):
    return build_working_documentation_payload(
        project=project,
        section=section,
        granularity=granularity,
        report_date=report_date,
    )
