from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import clamp_project_pipe, clamp_projects_list

from app.services.approved_budget import build_approved_budget_payload

router = APIRouter(prefix="/api/approved-budget", tags=["approved-budget"], dependencies=[Depends(require_report_access("approved-budget"))])


@router.get("")
def approved_budget_report(
    user: dict = Depends(require_report_access("approved-budget")),
    project: Optional[str] = Query(None, description="Устарело: один проект"),
    projects: Optional[list[str]] = Query(None, description="Проекты; пусто = все"),
    fiz: Optional[str] = Query(None, description="ФИЗ / организация / юрлицо"),
    hide_zero: Optional[bool] = Query(None, description="Скрыть пустые месяцы"),
    show_deviation: bool = Query(False, description="Показывать отклонение на графике"),
):
    selected = [item for item in (projects or []) if item and item.strip()]
    if not selected and project and project.strip() and project != "Все":
        selected = [project.strip()]
    selected = clamp_projects_list(user, selected)
    return build_approved_budget_payload(
        projects=selected,
        fiz=fiz,
        hide_zero=hide_zero,
        show_deviation=show_deviation,
    )
