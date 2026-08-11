from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access

from app.services.project_documentation import build_project_documentation_payload

router = APIRouter(prefix="/api/project-documentation", tags=["project-documentation"], dependencies=[Depends(require_report_access("project-documentation"))])


@router.get("")
def project_documentation_report(
    project: Optional[str] = Query(None, description="Фильтр проекта"),
    section: Optional[str] = Query(None, description="Вид раздела"),
    period: Optional[str] = Query(None, description="Период (месяцы через | или Все месяцы)"),
    granularity: Optional[str] = Query("week", description="day|week|month"),
    report_date: Optional[str] = Query(None, description="Отчётная дата YYYY-MM-DD"),
    view_mode: Optional[str] = Query("project", description="project|section"),
    tab: Optional[str] = Query("main", description="main|delay"),
):
    return build_project_documentation_payload(
        project=project,
        section=section,
        period=period,
        granularity=granularity,
        report_date=report_date,
        view_mode=view_mode,
        tab=tab,
    )
