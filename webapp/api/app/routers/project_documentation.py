from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.project_documentation import build_project_documentation_payload

router = APIRouter(prefix="/api/project-documentation", tags=["project-documentation"], dependencies=[Depends(require_report_access("project-documentation"))])


@router.get("")
def project_documentation_report(
    user: dict = Depends(require_report_access("project-documentation")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    section: Optional[str] = Query(None, description="Вид раздела"),
    period: Optional[str] = Query(None, description="Период (месяцы через | или Все месяцы)"),
    granularity: Optional[str] = Query("week", description="day|week|month"),
    report_date: Optional[str] = Query(None, description="Отчётная дата YYYY-MM-DD"),
    view_mode: Optional[str] = Query("project", description="project|section"),
    tab: Optional[str] = Query("main", description="main|delay"),
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
    return build_project_documentation_payload(
        project=project_arg,
        section=section,
        period=period,
        granularity=granularity,
        report_date=report_date,
        view_mode=view_mode,
        tab=tab,
    )
