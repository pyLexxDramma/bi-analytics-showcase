from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Depends
from app.services.auth_context import require_report_access
from app.services.project_scope import (
    allowed_projects_for_user,
    clamp_projects_list,
    parse_project_pipe,
)

from app.services.documentation import build_working_documentation_payload

router = APIRouter(prefix="/api/working-documentation", tags=["working-documentation"], dependencies=[Depends(require_report_access("working-documentation"))])


@router.get("")
def working_documentation_report(
    user: dict = Depends(require_report_access("working-documentation")),
    project: Optional[str] = Query(None, description="Legacy: один проект или A|B"),
    projects: Optional[list[str]] = Query(None, description="Multiselect; пусто = все"),
    section: Optional[str] = Query(None, description="Разделы (шифр+имя) через |"),
    status: Optional[str] = Query(None, description="Статусы через |"),
    period_mode: Optional[str] = Query(
        "Весь период (за всё время)",
        description="Весь период (за всё время) | Выбор диапазона дат",
    ),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    metric_mode: Optional[str] = Query(
        "Количество разделов",
        description="Количество разделов | % от общего объёма",
    ),
    show_forecast: Optional[bool] = Query(True, description="Показать прогнозную дату"),
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
    return build_working_documentation_payload(
        project=project_arg,
        section=section,
        status=status,
        period_mode=period_mode,
        date_from=date_from,
        date_to=date_to,
        metric_mode=metric_mode,
        show_forecast=show_forecast,
        view_mode=view_mode,
        tab=tab,
    )
